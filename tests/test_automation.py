"""Offline tests for update detection, release gating and distributable contents."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('upstream_release', ROOT / '.github/scripts/upstream_release.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)
spec = importlib.util.spec_from_file_location('publish_release', ROOT / '.github/scripts/publish_release.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
spec = importlib.util.spec_from_file_location('release_notes', ROOT / '.github/scripts/release-notes.py')
notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notes)


def asset(name='tools.zip', identifier=1):
    return dict(id=identifier, name=name, size=3, updated_at='2026-01-01',
                url='https://api.github.com/repos/official/releases/assets/' + str(identifier),
                browser_download_url='https://github.com/official/releases/download/v1/' + name)


class AutomationTests(unittest.TestCase):
    def test_maintained_package_prevents_redundant_scheduled_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'automation').mkdir()
            config = dict(project_version='1.2.36', pulsemodel='official/pulse', pulse_base='pulse',
                          studiomdl_ce='official/ce', tools_repository='official/tools', tools_tag='v1',
                          tools_assets=['tools.zip'])
            (root / 'automation/upstreams.json').write_text(json.dumps(config))
            (root / 'automation/compatibility.patch').write_text('maintained patch')
            (root / 'CMakeLists.txt').write_text('project(NewPageMergeMDL VERSION 1.2.36 LANGUAGES CXX C)')
            manifest = root / 'manifest.json'
            with patch.dict(os.environ, GITHUB_SHA='controller'):
                sync.maintained_manifest(argparse.Namespace(source=root, output=manifest, tag='v1.2.36'))
            previous = json.loads(manifest.read_text())
            canonical = sync.source_state(config, 'controller', 'pulse', root)
            self.assertEqual(previous['fingerprint'], canonical['fingerprint'])
            self.assertEqual(previous['version_base'], '1.2.36')
            self.assertNotEqual(previous['fingerprint'], sync.source_state(config, 'new-code', 'pulse', root)['fingerprint'])
            self.assertNotEqual(previous['fingerprint'], sync.source_state(config, 'controller', 'new-pulse', root)['fingerprint'])
            cache = root / 'CMakeCache.txt'
            cache.write_text('CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/g++\nCMAKE_INTERPROCEDURAL_OPTIMIZATION:BOOL=OFF\n')
            sync.record_build(argparse.Namespace(manifest=manifest, cache=cache, configuration='MinSizeRel'))
            recorded = json.loads(manifest.read_text())
            self.assertEqual(recorded['fingerprint'], previous['fingerprint'])
            with patch.object(sync, 'ROOT', root), patch.dict(os.environ, GITHUB_SHA='controller', GITHUB_REPOSITORY='o/r'), \
                 patch.object(sync, 'latest_commit', return_value='pulse'), \
                 patch.object(sync, 'published_manifest', return_value=recorded), \
                 patch.object(sync, 'fetch') as fetch, patch.object(sync, 'create_source') as merge, \
                 patch.object(sync, 'emit') as emit:
                sync.prepare(argparse.Namespace(work=root / 'work', force=False))
            emit.assert_called_once_with(changed=False, tag='v1.2.36')
            fetch.assert_not_called()
            merge.assert_not_called()
            self.assertFalse((root / 'work').exists())

    def test_release_notes_only_describe_changes_since_previous_package(self):
        old = dict(controller_sha='old', pulsemodel=dict(sha='pulse'))
        new = dict(controller_sha='new', pulsemodel=dict(repo='official/pulse', sha='pulse'),
                   studiomdl_ce=dict(sha='new-reference'), studiomdl_plusplus=dict(tag='v2'))
        comparison = dict(status='ahead', total_commits=2, commits=[
            {'commit': {'message': 'Fix output recovery\n\nImplementation details'}},
            {'commit': {'message': 'Correct release checksums'}}])
        with patch.object(sync, 'api', return_value=comparison) as api:
            changes = sync.release_changes(new, old, 'owner/project')
        api.assert_called_once_with('repos/owner/project/compare/old...new?per_page=100')
        body = sync.concise_release_notes(changes)
        self.assertIn('Fix output recovery', body)
        self.assertIn('Correct release checksums', body)
        self.assertIn('https://github.com/owner/project/compare/old...new', body)
        for text in ('Implementation details', 'PulseModel', 'StudioMDL', 'Tools++', 'automatic build'):
            self.assertNotIn(text, body)

    def test_release_notes_do_not_label_source_commits_as_stable_or_preview_releases(self):
        old = dict(controller_sha='same', pulsemodel=dict(sha='old'))
        new = dict(controller_sha='same', pulsemodel=dict(repo='official/pulse', sha='new'))
        comparison = dict(status='ahead', total_commits=1, commits=[
            {'commit': {'message': 'Fix [mesh] <format>'}}])
        with patch.object(sync, 'api', return_value=comparison):
            body = sync.concise_release_notes(sync.release_changes(new, old, 'owner/project'))
        self.assertIn('PulseModel 默认分支源码', body)
        self.assertIn(r'Fix \[mesh\] \<format\>', body)
        self.assertNotIn('稳定版', body)
        self.assertNotIn('预发布', body)

    def test_release_notes_bound_large_deltas_and_keep_comparison_link(self):
        change = dict(label='NewPage', status='ahead', url='https://github.com/o/r/compare/a...b',
                      total_commits=99, subjects=['Fix ' + str(index) for index in range(20)])
        body = sync.concise_release_notes([change])
        self.assertIn('Fix 4', body)
        self.assertNotIn('Fix 5', body)
        self.assertIn('99', body)
        self.assertIn(change['url'], body)
        self.assertLess(len(body), 500)

    def test_release_note_lookup_failure_and_missing_baseline_are_not_no_changes(self):
        new = dict(controller_sha='new', pulsemodel=dict(repo='official/pulse', sha='pulse'))
        old = dict(controller_sha='old', pulsemodel=dict(sha='pulse'))
        with patch.object(sync, 'api', side_effect=urllib.error.URLError('offline')):
            failed = sync.release_changes(new, old, 'owner/project')
        self.assertIn('暂未核实', sync.concise_release_notes(failed))
        with patch.object(sync, 'api') as api:
            initial = sync.release_changes(new, None, 'owner/project')
        api.assert_not_called()
        self.assertIn('无法确认', sync.concise_release_notes(initial))
        with patch.object(sync, 'api') as api:
            unchanged = sync.release_changes(new, new, 'owner/project')
        api.assert_not_called()
        self.assertIn('没有新增源码提交', sync.concise_release_notes(unchanged))

    def test_manual_release_notes_keep_subtools_platform_and_plain_commits(self):
        body = notes.render('\0Fix toolchain\n\nmdlcompiler:\n- Fix bones\n'
                            'subtools:\n- Recover VMD batches\nplatform:\n- Test Clang\n'
                            'Internal:\n- private implementation note\n'
                            '\0Fix checksum filenames\n')
        for text in ('Fix bones', 'Recover VMD batches', 'Test Clang', 'Fix checksum filenames'):
            self.assertIn(text, body)
        self.assertNotIn('private implementation note', body)
        self.assertNotIn('- Fix toolchain', body)

    def test_replacement_notes_preserve_changes_but_replace_old_zip_checksums(self):
        old = ('## Original fixes\r\n\r\n- Keep this fix.\r\n\r\nZIP SHA-256:\r\n\r\n```text\r\n'
               + 'a' * 64 + '  newpage-merge-mdl-win64.zip\r\n```\r\n\r\n'
               '## Later fixes\n\n- Keep this other fix.\n\nZIP SHA256:\n```text\n'
               + 'b' * 64 + '  newpage-merge-mdl-linux64.zip\n```\n')
        new = '- Recover interrupted output.\n\nZIP SHA256:\n```text\n' + 'c' * 64 + '  newpage-merge-mdl-win64.zip\n```\n'
        merged = sync.append_release_notes(old, new, 'v1.2.36')
        for text in ('Keep this fix.', 'Keep this other fix.', 'Recover interrupted output.', 'c' * 64):
            self.assertIn(text, merged)
        self.assertNotIn('a' * 64, merged)
        self.assertNotIn('b' * 64, merged)
        self.assertEqual(merged.count('ZIP SHA'), 1)
        self.assertEqual(sync.append_release_notes('', new, 'v1.2.36'), new)

    def test_build_manifest_records_actual_ipo_setting(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest, cache = root / 'manifest.json', root / 'CMakeCache.txt'
            for ipo in ('ON', 'OFF'):
                manifest.write_text('{"project_version":"1.2.36","build":"requested IPO"}')
                cache.write_text('CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/clang++\n'
                                 'CMAKE_C_COMPILER:FILEPATH=/usr/bin/clang\n'
                                 f'CMAKE_INTERPROCEDURAL_OPTIMIZATION:BOOL={ipo}\n')
                sync.record_build(argparse.Namespace(manifest=manifest, cache=cache, configuration='MinSizeRel'))
                recorded = json.loads(manifest.read_text())
                self.assertEqual(recorded['project_version'], '1.2.36')
                self.assertEqual(recorded['build']['interprocedural_optimization'], ipo == 'ON')
                self.assertEqual(recorded['build']['cxx_compiler'], '/usr/bin/clang++')
            cache.write_text('NEWPAGE_BUILD_CXX_COMPILER:INTERNAL=C:/VS/cl.exe\n'
                             'NEWPAGE_BUILD_CXX_COMPILER_ID:INTERNAL=MSVC\n'
                             'NEWPAGE_BUILD_CXX_COMPILER_VERSION:INTERNAL=19.51\n'
                             'CMAKE_INTERPROCEDURAL_OPTIMIZATION:UNINITIALIZED=ON\n')
            sync.record_build(argparse.Namespace(manifest=manifest, cache=cache, configuration='MinSizeRel'))
            recorded = json.loads(manifest.read_text())
            self.assertEqual(recorded['build']['cxx_compiler'], 'C:/VS/cl.exe')
            self.assertEqual(recorded['build']['compiler_id'], 'MSVC')
            cache.write_text('CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/clang++\n')
            before = manifest.read_bytes()
            with self.assertRaises(ValueError):
                sync.record_build(argparse.Namespace(manifest=manifest, cache=cache, configuration='MinSizeRel'))
            self.assertEqual(manifest.read_bytes(), before)

    def test_release_versions_increment_and_respect_manual_floor(self):
        self.assertEqual(sync.release_version('1.2.0', None, 'new'), ('1.2.0', 'v1.2.0'))
        old = dict(project_version='1.1', fingerprint='old')
        self.assertEqual(sync.release_version('1.2.0', old, 'new'), ('1.2.0', 'v1.2.0'))
        old['project_version'] = '1.2.8'
        self.assertEqual(sync.release_version('1.2.0', old, 'new'), ('1.2.9', 'v1.2.9'))
        self.assertEqual(sync.release_version('1.3.0', old, 'new'), ('1.3.0', 'v1.3.0'))

    def test_retry_reuses_published_version_and_tag(self):
        old = dict(project_version='1.2.8', fingerprint='same', release_tag='v1.2.8')
        self.assertEqual(sync.release_version('1.2.0', old, 'same'), ('1.2.8', 'v1.2.8'))
        with self.assertRaises(ValueError):
            sync.release_version('invalid', None, 'new')

    def test_versioned_release_manifest_is_recognized(self):
        for tag in ('v1.1-auto-abcdef', 'v1.2.0', 'v1.2.25-r1'):
            release = dict(draft=False, tag_name=tag, assets=[asset('upstream-manifest.json')])
            with patch.object(sync, 'api', return_value=[release]), patch.object(sync, 'fetch', return_value=b'{}'):
                self.assertEqual(sync.published_manifest('o/r')['release_tag'], tag)

    def test_single_package_embedded_manifest_drives_update_detection(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as archive:
            archive.writestr('NewPageMergeMDL/upstream-manifest.json',
                             json.dumps(dict(project_version='1.2.25', fingerprint='built')))
        release = dict(draft=False, tag_name='v1.2.25-r1', assets=[
            asset('newpage-v1.2.25-r1-win64.zip', 1), asset('newpage-v1.2.25-r1-linux64.zip', 2)])
        with patch.object(sync, 'api', return_value=[release]), patch.object(sync, 'fetch', return_value=payload.getvalue()) as download:
            manifest = sync.published_manifest('o/r')
            self.assertEqual(manifest['fingerprint'], 'built')
            self.assertEqual(sync.release_version('1.2.25', manifest, 'built'), ('1.2.25', 'v1.2.25-r1'))
            download.assert_called_once_with(asset(identifier=2)['url'], accept='application/octet-stream')

    def test_legacy_package_without_manifest_falls_back_to_older_release(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as archive:
            archive.writestr('NewPageMergeMDL/README.md', 'legacy')
        releases = [dict(draft=False, tag_name='v1.2.25-r1', published_at='2026-10-10',
                         assets=[asset('old-win64.zip')]),
                    dict(draft=False, tag_name='v1.2.24', published_at='2026-10-09',
                         assets=[asset('upstream-manifest.json')])]
        with patch.object(sync, 'api', return_value=releases), patch.object(sync, 'fetch', side_effect=[payload.getvalue(), b'{}']):
            self.assertEqual(sync.published_manifest('o/r')['release_tag'], 'v1.2.24')

    def test_source_archive_versions_match_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'automation').mkdir()
            (root / 'CMakeLists.txt').write_text('project(NewPageMergeMDL VERSION 1.2.0 LANGUAGES CXX C)\n')
            for name in ('README.md', 'README.en.md', 'AUTOMATION.md'):
                (root / name).write_text('NewPageMergeMDL v1.2.0\n', encoding='utf-8')
            (root / 'automation/upstreams.json').write_text('{"project_version":"1.2.0"}')
            sync.stamp_version(root, '1.2.0', '1.2.9')
            self.assertIn('VERSION 1.2.9', (root / 'CMakeLists.txt').read_text())
            self.assertEqual(json.loads((root / 'automation/upstreams.json').read_text())['project_version'], '1.2.9')
            self.assertIn('v1.2.9', (root / 'README.en.md').read_text())
    def test_reference_metadata_records_replaced_assets_even_at_same_tag(self):
        old = sync.select_tools({'assets': [asset()]}, ['tools.zip'])
        new = sync.select_tools({'assets': [asset(identifier=2)]}, ['tools.zip'])
        self.assertNotEqual(old, new)

    def test_missing_or_ambiguous_asset_fails(self):
        for assets in ([], [asset(), asset()]):
            with self.assertRaises(ValueError):
                sync.select_tools({'assets': assets}, ['tools.zip'])

    def test_fingerprint_is_stable_across_key_order(self):
        self.assertEqual(sync.fingerprint({'a': 1, 'b': 2}), sync.fingerprint({'b': 2, 'a': 1}))

    def test_published_state_ignores_drafts_but_accepts_prereleases(self):
        releases = [dict(draft=True, tag_name='newpage-auto-draft', assets=[asset('upstream-manifest.json')]),
                    dict(draft=False, prerelease=True, tag_name='newpage-auto-ready',
                         assets=[asset('upstream-manifest.json')])]
        with patch.object(sync, 'api', return_value=releases), patch.object(sync, 'fetch', return_value=b'{"fingerprint":"ready"}') as download:
            self.assertEqual(sync.published_manifest('owner/repo')['fingerprint'], 'ready')
            download.assert_called_once()
            download.assert_called_once_with(asset()['url'], accept='application/octet-stream')

    def test_published_state_uses_publication_time_instead_of_api_order(self):
        releases = [dict(draft=False, tag_name='newpage-auto-old', published_at='2026-10-06T04:00:00Z',
                         assets=[asset('upstream-manifest.json', 1)]),
                    dict(draft=False, tag_name='newpage-auto-new', published_at='2026-10-06T05:00:00Z',
                         assets=[asset('upstream-manifest.json', 2)])]
        with patch.object(sync, 'api', return_value=releases), patch.object(sync, 'fetch', return_value=b'{"fingerprint":"new"}') as download:
            self.assertEqual(sync.published_manifest('owner/repo')['fingerprint'], 'new')
            download.assert_called_once_with(asset(identifier=2)['url'], accept='application/octet-stream')

    def test_download_redirect_strips_credentials_on_host_change(self):
        request = urllib.request.Request('https://api.github.com/repos/o/r/releases/assets/1',
                                         headers={'Authorization': 'Bearer test-only'})
        redirected = sync.GitHubRedirect().redirect_request(request, None, 302, 'Found', {},
                                                            'https://release-assets.githubusercontent.com/file')
        self.assertIsNone(redirected.get_header('Authorization'))
        with self.assertRaises(ValueError):
            sync.GitHubRedirect().redirect_request(request, None, 302, 'Found', {}, 'https://unrelated.example/file')

    def test_unchanged_versions_skip_download_and_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'automation').mkdir()
            config = dict(pulsemodel='p/p', studiomdl_ce='c/c', tools_repository='t/t', tools_tag='v1', tools_assets=['tools.zip'])
            (root / 'automation/upstreams.json').write_text(json.dumps(config))
            (root / 'automation/compatibility.patch').write_text('patch')
            with patch.object(sync, 'ROOT', root), patch.dict(os.environ, GITHUB_SHA='controller', GITHUB_REPOSITORY='o/r'), \
                 patch.object(sync, 'latest_commit', return_value='sha') as commits, patch.object(sync, 'api') as api, \
                 patch.object(sync, 'fingerprint', return_value='unchanged'), patch.object(sync, 'published_manifest', return_value={'fingerprint': 'unchanged', 'project_version': '1.2.3', 'release_tag': 'v1.2.3'}), \
                 patch.object(sync, 'fetch') as download, patch.object(sync, 'create_source') as merge, patch.object(sync, 'emit') as emit:
                sync.prepare(argparse.Namespace(work=root / 'work', force=False))
                download.assert_not_called()
                merge.assert_not_called()
                emit.assert_called_once_with(changed=False, tag='v1.2.3')
                self.assertFalse((root / 'work').exists())
                commits.assert_called_once_with('p/p')
                api.assert_not_called()

    def test_candidate_refuses_existing_directory(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sync, 'run') as git:
            with self.assertRaises(ValueError):
                sync.create_source(folder, 'p/p', 'sha', 'base', 'patch')
            git.assert_not_called()

    def test_source_archive_excludes_git_and_build_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source'
            for name in ('main.cpp', '.git/config', 'build/compiler.exe', '__pycache__/test.pyc', 'automation/compatibility.patch',
                         'libs/tinyusdz/src/tinyusdz.cc', 'libs/tinyusdz/src/tydra/tydra.png'):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('content')
            sync.source_archive(argparse.Namespace(source=source, output=root / 'source.zip'))
            with zipfile.ZipFile(root / 'source.zip') as archive:
                self.assertEqual(set(archive.namelist()), {'NewPageMergeMDL/main.cpp', 'NewPageMergeMDL/automation/compatibility.patch',
                                                         'NewPageMergeMDL/libs/tinyusdz/src/tinyusdz.cc',
                                                         'NewPageMergeMDL/libs/tinyusdz/src/tydra/tydra.png'})

    def test_package_requires_both_compiler_and_decompiler(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                sync.package(argparse.Namespace(dist=folder, output=Path(folder) / 'out.zip', platform='win64'))

    def test_windows_package_requires_c4d_helper(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('NewPageMergeMDL', 'NewPageMergeMDL-Decompiler', 'NewPageVRMLtoX3D'):
                (root / (name + '.exe')).write_bytes(b'MZfixture')
            with self.assertRaisesRegex(ValueError, 'NewPageMergeMDL-C4D'):
                sync.package(argparse.Namespace(dist=root, output=root / 'out.zip', platform='win64'))

    def test_package_requires_ag2proportions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('NewPageMergeMDL', 'NewPageMergeMDL-Decompiler', 'NewPageVRMLtoX3D',
                         'NewPageMergeMDL-C4D'):
                (root / (name + '.exe')).write_bytes(b'MZfixture')
            (root / 'subtools').mkdir()
            for name in ('l4d_animswap', 'meshtool', 'vmd2valvebiped'):
                (root / 'subtools' / (name + '.exe')).write_bytes(b'MZfixture')
            with self.assertRaisesRegex(ValueError, 'subtools/ag2proportions'):
                sync.package(argparse.Namespace(dist=root, output=root / 'out.zip', platform='win64'))

    def test_package_requires_nonempty_ag2proportions_licenses(self):
        for platform in ('win64', 'linux64'):
            for missing in ('zstd.txt', 'ValveResourceFormat.txt'):
                for empty in (False, True):
                    with self.subTest(platform=platform, license=missing, empty=empty), tempfile.TemporaryDirectory() as folder:
                        root = Path(folder)
                        extension = '.exe' if platform == 'win64' else ''
                        (root / 'subtools/licenses').mkdir(parents=True)
                        for name in ('NewPageMergeMDL', 'NewPageMergeMDL-Decompiler', 'NewPageVRMLtoX3D',
                                     'NewPageMergeMDL-C4D', 'subtools/ag2proportions', 'subtools/l4d_animswap',
                                     'subtools/meshtool', 'subtools/vmd2valvebiped'):
                            (root / (name + extension)).write_bytes(b'fixture')
                        for name in ('zstd.txt', 'ValveResourceFormat.txt'):
                            if name != missing:
                                (root / 'subtools/licenses' / name).write_text('third-party notice')
                            elif empty:
                                (root / 'subtools/licenses' / name).write_bytes(b'')
                        archive = root / 'out.zip'
                        archive.write_bytes(b'previous package')
                        with self.assertRaisesRegex(ValueError, re.escape(missing)):
                            sync.package(argparse.Namespace(dist=root, output=archive, platform=platform))
                        self.assertEqual(archive.read_bytes(), b'previous package')

    def test_binary_package_contains_provenance_and_licenses(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist, source = root / 'dist', root / 'source'
            dist.mkdir(); source.mkdir()
            for name in ('NewPageMergeMDL.exe', 'NewPageMergeMDL-Decompiler.exe', 'NewPageVRMLtoX3D.exe', 'NewPageMergeMDL-C4D.exe'):
                (dist / name).write_bytes(b'binary')
            (dist / 'subtools').mkdir()
            for name in ('ag2proportions', 'l4d_animswap', 'meshtool', 'vmd2valvebiped'):
                (dist / 'subtools' / (name + '.exe')).write_bytes(b'binary')
            (dist / 'subtools/licenses').mkdir()
            for name in ('zstd.txt', 'ValveResourceFormat.txt'):
                (dist / 'subtools/licenses' / name).write_text('AG2 dependency notice: ' + name)
            for name in ('LICENSE', 'README.md', 'README.en.md', 'INSTALL.md', 'COMPATIBILITY.md', 'BINARY_ANALYSIS.md', 'AUTOMATION.md', 'RESEARCH.md', 'VALIDATION.md', 'IMPROVEMENTS.md', 'FEATURE_MATRIX.md'):
                (source / name).write_text(name)
            (source / 'subtools/meshtool').mkdir(parents=True)
            (source / 'subtools/meshtool/PROTOCOL.md').write_text('Binary protocol limits')
            branding = ('.github/images/newpage-compiler.png', '.github/images/newpage-decompiler.png',
                        'assets/branding/NewPage-logo.png', 'assets/branding/generate_icons.py',
                        'assets/branding/README.md')
            for name in branding:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(('brand fixture: ' + name).encode())
            (source / 'libs/vendor').mkdir(parents=True)
            (source / 'libs/vendor/LICENSE').write_text('vendor notice')
            (source / 'libs/nvtristrip').mkdir()
            for name in ('README.txt', 'SOURCE.md'):
                (source / 'libs/nvtristrip' / name).write_text('dependency provenance')
            (source / 'libs/meshoptimizer').mkdir()
            for name in ('LICENSE.md', 'SOURCE.md'):
                (source / 'libs/meshoptimizer' / name).write_text('meshopt provenance')
            (source / 'libs/tinyusdz/src/tydra').mkdir(parents=True)
            for name in ('LICENSE', 'LICENSE-APACHE-2.0', 'SOURCE.md', 'THIRD_PARTY_NOTICES.md'):
                (source / 'libs/tinyusdz' / name).write_text('USD dependency notice: ' + name)
            (source / 'libs/tinyusdz/src/tinyusdz.cc').write_text('development source')
            (source / 'libs/tinyusdz/src/tydra/tydra.png').write_bytes(b'development image')
            (source / 'tools/vrml_converter/meshlab').mkdir(parents=True)
            (source / 'tools/vrml_converter/meshlab/Parser.cpp').write_text('GPL corresponding source')
            (source / 'libs/assimp/contrib/pugixml/src').mkdir(parents=True)
            (source / 'libs/assimp/contrib/pugixml/src/pugixml.cpp').write_text('converter dependency source')
            (root / 'manifest.json').write_text('{}')
            with zipfile.ZipFile(root / 'source.zip', 'w') as archive:
                archive.writestr('NewPageMergeMDL/main.cpp', 'exact merged input')
            (source / 'integration/gmod').mkdir(parents=True)
            (source / 'integration/gmod/newpage_vertexanim.lua').write_text('playback helper')
            (root / 'StudioMDL-CE.exe').write_text('reference only')
            sync.package(argparse.Namespace(dist=dist, source=source, output=root / 'out.zip',
                                            platform='win64', manifest=root / 'manifest.json', source_archive=root / 'source.zip'))
            with zipfile.ZipFile(root / 'out.zip') as archive:
                self.assertEqual(archive.read('NewPageMergeMDL/sources/NewPageMergeMDL-source.zip'), (root / 'source.zip').read_bytes())
                self.assertEqual(archive.read('NewPageMergeMDL/subtools/meshtool-protocol.md'), b'Binary protocol limits')
                for name in branding:
                    self.assertEqual(archive.read('NewPageMergeMDL/' + name), (source / name).read_bytes())
                self.assertIn('NewPageMergeMDL/INSTALL.md', archive.namelist())
                inventory = dict(line.split('  ', 1)[::-1] for line in archive.read('NewPageMergeMDL/SHA256SUMS.txt').decode().splitlines())
                self.assertEqual(set(inventory), {n.removeprefix('NewPageMergeMDL/') for n in archive.namelist()} - {'SHA256SUMS.txt'})
                for name, digest in inventory.items():
                    self.assertEqual(hashlib.sha256(archive.read('NewPageMergeMDL/' + name)).hexdigest(), digest)
                self.assertIn('NewPageMergeMDL/upstream-manifest.json', archive.namelist())
                self.assertIn('NewPageMergeMDL/BINARY_ANALYSIS.md', archive.namelist())
                self.assertIn('NewPageMergeMDL/README.en.md', archive.namelist())
                self.assertIn('NewPageMergeMDL/VALIDATION.md', archive.namelist())
                self.assertIn('NewPageMergeMDL/FEATURE_MATRIX.md', archive.namelist())
                self.assertIn('NewPageMergeMDL/integration/gmod/newpage_vertexanim.lua', archive.namelist())
                self.assertIn('NewPageMergeMDL/libs/vendor/LICENSE', archive.namelist())
                for name in ('zstd.txt', 'ValveResourceFormat.txt'):
                    self.assertEqual(archive.read('NewPageMergeMDL/subtools/licenses/' + name),
                                     ('AG2 dependency notice: ' + name).encode())
                for name in ('README.txt', 'SOURCE.md'):
                    self.assertIn('NewPageMergeMDL/libs/nvtristrip/' + name, archive.namelist())
                for name in ('LICENSE.md', 'SOURCE.md'):
                    self.assertIn('NewPageMergeMDL/libs/meshoptimizer/' + name, archive.namelist())
                for name in ('LICENSE', 'LICENSE-APACHE-2.0', 'SOURCE.md', 'THIRD_PARTY_NOTICES.md'):
                    self.assertEqual(archive.read('NewPageMergeMDL/libs/tinyusdz/' + name),
                                     ('USD dependency notice: ' + name).encode())
                self.assertFalse(any(name.startswith('NewPageMergeMDL/libs/tinyusdz/src/') for name in archive.namelist()))
                self.assertEqual(archive.read('NewPageMergeMDL/tools/vrml_converter/meshlab/Parser.cpp'), b'GPL corresponding source')
                self.assertEqual(archive.read('NewPageMergeMDL/libs/assimp/contrib/pugixml/src/pugixml.cpp'), b'converter dependency source')
                self.assertFalse(any('StudioMDL-CE' in name for name in archive.namelist()))

            for name in ('NewPageMergeMDL', 'NewPageMergeMDL-Decompiler', 'NewPageVRMLtoX3D',
                         'subtools/ag2proportions', 'subtools/l4d_animswap', 'subtools/meshtool', 'subtools/vmd2valvebiped'):
                (dist / name).write_bytes(b'\x7fELFfixture')
            sync.package(argparse.Namespace(dist=dist, source=source, output=root / 'linux.zip',
                                            platform='linux64', manifest=root / 'manifest.json'))
            with zipfile.ZipFile(root / 'linux.zip') as archive:
                self.assertEqual(archive.read('NewPageMergeMDL/subtools/meshtool-protocol.md'), b'Binary protocol limits')
                for name in branding:
                    self.assertEqual(archive.read('NewPageMergeMDL/' + name), (source / name).read_bytes())
                for name in ('NewPageMergeMDL', 'subtools/ag2proportions', 'subtools/meshtool'):
                    info = archive.getinfo('NewPageMergeMDL/' + name)
                    self.assertEqual(info.create_system, 3)
                    self.assertEqual((info.external_attr >> 16) & 0o777, 0o755)
                for name in ('zstd.txt', 'ValveResourceFormat.txt'):
                    self.assertEqual(archive.read('NewPageMergeMDL/subtools/licenses/' + name),
                                     ('AG2 dependency notice: ' + name).encode())

    def test_checksums_verify_actual_artifacts_and_are_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'a.zip').write_bytes(b'actual artifact')
            args = argparse.Namespace(folder=root)
            sync.checksums(args)
            expected = hashlib.sha256(b'actual artifact').hexdigest() + '  a.zip\n'
            self.assertEqual((root / 'SHA256SUMS.txt').read_text(), expected)
            sync.checksums(args)
            self.assertEqual((root / 'SHA256SUMS.txt').read_text(), expected)

    def test_tinyusdz_binary_notices_preserve_inline_and_dependency_terms(self):
        usd = ROOT / 'libs/tinyusdz'
        notices = (usd / 'THIRD_PARTY_NOTICES.md').read_text(encoding='utf-8')
        # These have no standalone license files. Removing src/ used to remove
        # their sole copy of binary redistribution terms and attribution.
        for name in ('stream-reader.hh', 'stream-writer.hh', 'texture-types.hh', 'external/half-edge.hh'):
            original = (usd / 'src' / name).read_text(encoding='utf-8')
            self.assertIn(re.search(r'/\*(.*?)\*/', original, re.S)[1].strip(), notices)
        for name in ('external/stb_image.h', 'external/stb_image_write.h', 'external/stb_image_resize2.h'):
            original = (usd / 'src' / name).read_text(encoding='utf-8')
            mit = original[original.rfind('ALTERNATIVE A - MIT License'):].split('------------------------------------------------------------------------------')[0]
            self.assertIn(mit.strip(), notices)
        for name in ('lz4/LICENSE', 'external/fast_float/LICENSE-MIT', 'external/filesystem/LICENSE',
                     'external/glob/LICENSE', 'external/dtoa_milo.LICENSE', 'external/jeaiii_to_text.LICENSE',
                     'external/mapbox/earcut/LICENSE', 'external/mapbox/eternal/LICENSE.md'):
            self.assertIn((usd / 'src' / name).read_text(encoding='utf-8').strip(), notices)
        for attribution in ('Project Nayuki', 'Martin Moene', 'John Maddock', 'Denilson das Mercês Amorim',
                            'Copyright 2016 Pixar', 'Copyright 2017 Pixar', 'Section 6. Trademarks.',
                            'Alexey Chernov', 'ArangoDB GmbH', 'Georgi Gerganov'):
            self.assertIn(attribution, notices)



class ReleasePublishingTests(unittest.TestCase):
    @staticmethod
    def api_response(data, status=200):
        return argparse.Namespace(returncode=0 if status == 200 else 1,
                                  stdout=f'HTTP/2.0 {status} Status\r\nContent-Type: application/json\r\n\r\n' + json.dumps(data))

    @classmethod
    def response(cls, status=200, tag='v1.2.30', **fields):
        data = dict(id=123, tag_name=tag, draft=False, prerelease=False)
        data.update(fields)
        return cls.api_response(data, status)

    def test_new_release_without_latest_publishes_stable_and_latest(self):
        with patch.object(publisher.subprocess, 'run', side_effect=[
                self.response(draft=True), self.response(status=404), None]) as run:
            publisher.publish('owner/repo', 'v1.2.30', 'notes.md')
        self.assertEqual(run.call_args_list[-1].args[0], [
            'gh', 'release', 'edit', 'v1.2.30', '--repo', 'owner/repo',
            '--draft=false', '--prerelease=false', '--latest=true', '--notes-file', 'notes.md'])

    def test_same_tag_retry_never_downgrades_stable_release(self):
        for prerelease in (False, True):
            with self.subTest(prerelease=prerelease), patch.object(publisher.subprocess, 'run', side_effect=[
                    self.response(prerelease=prerelease), self.response(), None]) as run:
                publisher.publish('owner/repo', 'v1.2.30', 'notes.md')
            command = run.call_args_list[-1].args[0]
            self.assertIn('--prerelease=false', command)
            self.assertIn('--latest=true', command)

    def test_latest_uses_numeric_project_version_and_revision_order(self):
        for tag, latest, promote in (
                ('v1.2.9', 'v1.2.30', False),
                ('v1.2.30', 'v1.3.0', False),
                ('v1.2.30', 'v2.0.0', False),
                ('v1.2.30', 'v1.2.30-r1', False),
                ('v1.2.30-r2', 'v1.2.30-r10', False),
                ('v1.2.30-r1', 'v1.2.30', True),
                ('v1.2.30-r10', 'v1.2.30-r2', True),
                ('v1.2.31', 'v1.2.30-r100', True)):
            with self.subTest(tag=tag, latest=latest), patch.object(publisher.subprocess, 'run', side_effect=[
                    self.response(tag=tag), self.response(tag=latest), None]) as run:
                publisher.publish('owner/repo', tag, 'notes.md')
            command = run.call_args_list[-1].args[0]
            self.assertIn('--latest=' + str(promote).lower(), command)
            self.assertIn('--prerelease=false', command)

    def test_latest_query_errors_stop_before_any_release_edit(self):
        failures = [self.response(status=code) for code in (401, 403, 429, 500, 503)]
        failures.extend([
            argparse.Namespace(returncode=1, stdout='', stderr='network failure'),
            argparse.Namespace(returncode=1, stdout='{"status":"404"}', stderr='no HTTP response'),
            argparse.Namespace(returncode=0, stdout='HTTP/2.0 200 OK\n\nnot JSON'),
            argparse.Namespace(returncode=0, stdout='HTTP/2.0 200 OK\n\n{}'),
            self.api_response(None)])
        for failed in failures:
            with self.subTest(response=failed.stdout), patch.object(publisher.subprocess, 'run', side_effect=[
                    self.response(), failed]) as run:
                with self.assertRaises((ValueError, RuntimeError)):
                    publisher.publish('owner/repo', 'v1.2.30', 'notes.md')
                self.assertEqual(run.call_count, 2)
                self.assertTrue(all(call.args[0][1] == 'api' for call in run.call_args_list))

    def test_unknown_tags_fail_without_guessing_latest(self):
        for tag in ('1.2.30', 'v1.2', 'v1.2.30-preview', 'v1.2.30-r', 'newpage-auto-old'):
            with self.subTest(tag=tag), patch.object(publisher.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    publisher.publish('owner/repo', tag, 'notes.md')
                run.assert_not_called()
        with patch.object(publisher.subprocess, 'run', side_effect=[
                self.response(), self.response(tag='unrecognized-latest')]) as run:
            with self.assertRaises(ValueError):
                publisher.publish('owner/repo', 'v1.2.30', 'notes.md')
            self.assertEqual(run.call_count, 2)

    def test_draft_creation_is_not_prerelease_and_retries_do_not_edit(self):
        with patch.object(publisher.subprocess, 'run', side_effect=[
                self.response(status=404), self.api_response([]), None]) as run:
            publisher.create_draft('owner/repo', 'v1.2.30', 'commit', 'notes.md')
        command = run.call_args_list[-1].args[0]
        self.assertIn('--draft', command)
        self.assertFalse(any(value.startswith('--prerelease') for value in command))
        for draft in (False, True):
            with self.subTest(draft=draft), patch.object(publisher.subprocess, 'run', return_value=self.response(draft=draft)) as run:
                publisher.create_draft('owner/repo', 'v1.2.30', 'commit', 'notes.md')
                self.assertEqual(run.call_count, 1)
        with patch.object(publisher.subprocess, 'run', return_value=self.response(status=403)) as run:
            with self.assertRaises(RuntimeError):
                publisher.create_draft('owner/repo', 'v1.2.30', 'commit', 'notes.md')
            self.assertEqual(run.call_count, 1)

    def test_missing_or_mismatched_target_cannot_publish(self):
        for responses in ([self.response(status=404), self.api_response([])],
                          [self.response(tag='v1.2.29')]):
            with patch.object(publisher.subprocess, 'run', side_effect=responses) as run:
                with self.assertRaises((ValueError, RuntimeError)):
                    publisher.publish('owner/repo', 'v1.2.30', 'notes.md')
                self.assertEqual(run.call_count, len(responses))

    def test_draft_tag_404_falls_back_to_paginated_list_and_verified_id(self):
        first_page = [dict(id=index + 1, tag_name='v1.2.29-r' + str(index)) for index in range(100)]
        draft = dict(id=410761664, tag_name='v1.2.30', draft=True, prerelease=False)
        responses = [self.response(status=404), self.api_response(first_page),
                     self.api_response([draft]), self.api_response(draft)]
        with patch.object(publisher.subprocess, 'run', side_effect=responses) as run:
            publisher.create_draft('owner/repo', 'v1.2.30', 'commit', 'notes.md')
        self.assertEqual([call.args[0][-1] for call in run.call_args_list], [
            'repos/owner/repo/releases/tags/v1.2.30',
            'repos/owner/repo/releases?per_page=100&page=1',
            'repos/owner/repo/releases?per_page=100&page=2',
            'repos/owner/repo/releases/410761664'])
        with patch.object(publisher.subprocess, 'run', side_effect=responses + [
                self.response(tag='v1.2.29'), None]) as run:
            publisher.publish('owner/repo', 'v1.2.30', 'notes.md')
        self.assertIn('--draft=false', run.call_args_list[-1].args[0])
        self.assertIn('--prerelease=false', run.call_args_list[-1].args[0])
        self.assertIn('--latest=true', run.call_args_list[-1].args[0])

    def test_draft_lookup_failures_stop_before_creating_or_publishing(self):
        draft = dict(id=123, tag_name='v1.2.30')
        invalid_lookups = [
            [self.response(status=403)],
            [self.api_response(None)],
            [self.api_response({})],
            [self.api_response([{}])],
            [self.api_response([dict(draft, id='123')])],
            [self.api_response([dict(draft, id=True)])],
            [self.api_response([dict(draft, id=-1)])],
            [self.api_response([draft]), self.response(status=404)],
            [self.api_response([draft]), self.response(id=456)],
            [self.api_response([draft]), self.response(tag='v1.2.29')]]
        for operation in ('draft', 'publish'):
            for lookup in invalid_lookups:
                responses = [self.response(status=404)] + lookup
                with self.subTest(operation=operation, responses=responses), patch.object(
                        publisher.subprocess, 'run', side_effect=responses) as run:
                    with self.assertRaises((ValueError, RuntimeError)):
                        if operation == 'draft':
                            publisher.create_draft('owner/repo', 'v1.2.30', 'commit', 'notes.md')
                        else:
                            publisher.publish('owner/repo', 'v1.2.30', 'notes.md')
                    self.assertEqual(run.call_count, len(responses))
                    self.assertTrue(all(call.args[0][1] == 'api' for call in run.call_args_list))


class PackageValidationTests(unittest.TestCase):
    def make_package(self, root, extra=None, manifest=None, omit=None, empty=None):
        suffix='.exe' if os.name=='nt' else ''
        binary=b'MZfixture' if os.name=='nt' else b'\x7fELFfixture'
        archive=root/'package.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('NewPageMergeMDL/upstream-manifest.json',json.dumps(manifest or {'project_version':'1.2.6'}))
            # This fixture checks archive validation only; executables are
            # magic-byte stubs and support files model the complete release
            # layout, including the standalone GPL converter's source.
            for name in (
                'README.md','README.en.md','INSTALL.md','VALIDATION.md','IMPROVEMENTS.md',
                '.github/images/newpage-compiler.png','.github/images/newpage-decompiler.png',
                'assets/branding/NewPage-logo.png','assets/branding/generate_icons.py','assets/branding/README.md',
                'FIVE_COMPILER_COMPLETION.md','O5_FORMAT_IMPORTS.md','MESH_STATE_WORKFLOW.md','VRM_RUNTIME.md',
                'integration/gmod/newpage_vertexanim.lua','integration/gmod/newpage_meshstates.lua',
                'integration/gmod/newpage_vrm.lua','integration/gmod/newpage_vrm_materials.lua',
                'tools/mesh_states.py','tools/vrm_runtime.py','tools/vrml_import.py','tools/output_transaction.py',
                'tools/vrml_converter/CMakeLists.txt','tools/vrml_converter/main.cpp',
                'tools/vrml_converter/meshlab/Parser.cpp','tools/vrml_converter/meshlab/Parser.h',
                'tools/vrml_converter/meshlab/Scanner.cpp','tools/vrml_converter/meshlab/Scanner.h',
                'tools/vrml_converter/meshlab/LICENSE','tools/vrml_converter/meshlab/SOURCE.md',
                'libs/assimp/contrib/pugixml/src/pugixml.cpp','libs/assimp/contrib/pugixml/src/pugixml.hpp',
                'libs/assimp/contrib/pugixml/src/pugiconfig.hpp','libs/assimp/contrib/pugixml/LICENSE.md',
                'libs/tinyusdz/LICENSE','libs/tinyusdz/LICENSE-APACHE-2.0',
                'libs/tinyusdz/SOURCE.md','libs/tinyusdz/THIRD_PARTY_NOTICES.md',
                'subtools/licenses/zstd.txt','subtools/licenses/ValveResourceFormat.txt',
                'subtools/meshtool-protocol.md',
            ):
                if name != omit:
                    z.writestr('NewPageMergeMDL/'+name, '' if name == empty else 'fixture')
            for name in ('NewPageMergeMDL','NewPageMergeMDL-Decompiler','NewPageVRMLtoX3D'):
                z.writestr('NewPageMergeMDL/'+name+suffix,binary)
            if suffix:z.writestr('NewPageMergeMDL/NewPageMergeMDL-C4D.exe',binary)
            for name in ('ag2proportions', 'l4d_animswap', 'meshtool', 'vmd2valvebiped'):
                z.writestr('NewPageMergeMDL/subtools/'+name+suffix,binary)
            sync.write_inventory(z)
            if extra:z.writestr(extra,'unexpected')
        return archive

    def verifier(self):
        spec=importlib.util.spec_from_file_location('verify_package',ROOT/'tests/verify_package.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def test_packaged_provenance_and_runtime_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=self.make_package(root)
            compiler = self.verifier().verify(archive,{'project_version':'1.2.6'},root/'extracted')
            self.assertTrue(compiler.exists())
            if os.name != 'nt':
                self.assertEqual((compiler.parent/'subtools/ag2proportions').stat().st_mode & 0o777, 0o755)

    def test_missing_or_empty_support_files_fail_before_extracting(self):
        for name in ('subtools/licenses/zstd.txt', 'subtools/licenses/ValveResourceFormat.txt',
                     '.github/images/newpage-compiler.png', '.github/images/newpage-decompiler.png',
                     'assets/branding/NewPage-logo.png', 'assets/branding/generate_icons.py',
                     'assets/branding/README.md', 'subtools/meshtool-protocol.md'):
            for mode in ('omit', 'empty'):
                with self.subTest(file=name, mode=mode), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    archive = self.make_package(root, **{mode: name})
                    # The inventory is correct for the incomplete archive, so
                    # only the required-file gate can reject it.
                    with zipfile.ZipFile(archive) as package:
                        self.verifier().verify_inventory(package)
                    with self.assertRaisesRegex(ValueError, re.escape(name)):
                        self.verifier().verify(archive, {'project_version': '1.2.6'}, root/'extracted')
                    self.assertFalse((root/'extracted').exists())

    def test_ag2_version_must_equal_manifest_version(self):
        verifier = self.verifier()
        compiler = Path('fixture') / ('NewPageMergeMDL.exe' if os.name == 'nt' else 'NewPageMergeMDL')
        for version in ('1.2.28', '0.3.7', '1.2.280', '1.2.28-extra', 'unknown'):
            with self.subTest(version=version):
                banner = ('-------------------------------\n'
                          'NewPageMergeMDL [AG2 Proportions]\n'
                          'version:   ' + version + '\n'
                          'developer: ToppiOfficial\n'
                          '-------------------------------\n')
                responses = [argparse.Namespace(stdout=(
                                'CS2 AnimGraph2 proportion wrapper (experimental)\n'
                                'Usage:\n'
                                '--generate-only\n'
                                'Existing generated assets are not compiled; compile the sources before use.\n')),
                             argparse.Namespace(stdout=banner + 'ag2proportions ' + version + '\n')]
                with patch.object(verifier.subprocess, 'run', side_effect=responses) as run:
                    if version == '1.2.28':
                        verifier.exercise_packaged_ag2proportions(compiler, '1.2.28')
                    else:
                        with self.assertRaisesRegex(ValueError, 'version does not match'):
                            verifier.exercise_packaged_ag2proportions(compiler, '1.2.28')
                self.assertEqual(run.call_args_list[0].args[0][-1], '--help')
                self.assertEqual(run.call_args_list[1].args[0][-1], '--version')

    def test_tampered_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=self.make_package(root,manifest={'project_version':'wrong'})
            with self.assertRaisesRegex(ValueError,'provenance'):self.verifier().verify(archive,{'project_version':'1.2.6'},root/'extracted')

    def test_unlisted_payload_is_rejected_before_extracting(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=self.make_package(root,extra='NewPageMergeMDL/unlisted.txt')
            with self.assertRaisesRegex(ValueError,'cover'):self.verifier().verify(archive,{'project_version':'1.2.6'},root/'extracted')
            self.assertFalse((root/'extracted').exists())

    def test_modified_payload_is_rejected_before_extracting(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);original=self.make_package(root);changed=root/'changed.zip'
            with zipfile.ZipFile(original) as source, zipfile.ZipFile(changed,'w') as output:
                for entry in source.infolist():
                    output.writestr(entry, b'changed' if entry.filename=='NewPageMergeMDL/README.md' else source.read(entry))
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):self.verifier().verify(changed,{'project_version':'1.2.6'},root/'extracted')
            self.assertFalse((root/'extracted').exists())

    def test_package_traversal_is_rejected_before_extracting(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=self.make_package(root,extra='NewPageMergeMDL/../../outside')
            with self.assertRaisesRegex(ValueError,'Unsafe'):self.verifier().verify(archive,{'project_version':'1.2.6'},root/'extracted')
            self.assertFalse((root/'extracted').exists())

    def test_duplicate_package_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning);archive=self.make_package(root,extra='NewPageMergeMDL/README.md')
            with self.assertRaisesRegex(ValueError,'Duplicate'):self.verifier().verify(archive,{'project_version':'1.2.6'},root/'extracted')

if __name__ == '__main__':
    unittest.main()
