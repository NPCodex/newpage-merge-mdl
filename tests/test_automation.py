"""Offline tests for update detection, release gating and distributable contents."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('upstream_release', ROOT / '.github/scripts/upstream_release.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def asset(name='tools.zip', identifier=1):
    return dict(id=identifier, name=name, size=3, updated_at='2026-01-01',
                url='https://api.github.com/repos/official/releases/assets/' + str(identifier),
                browser_download_url='https://github.com/official/releases/download/v1/' + name)


class AutomationTests(unittest.TestCase):
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
            for name in ('main.cpp', '.git/config', 'build/compiler.exe', '__pycache__/test.pyc', 'automation/compatibility.patch'):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('content')
            sync.source_archive(argparse.Namespace(source=source, output=root / 'source.zip'))
            with zipfile.ZipFile(root / 'source.zip') as archive:
                self.assertEqual(set(archive.namelist()), {'NewPageMergeMDL/main.cpp', 'NewPageMergeMDL/automation/compatibility.patch'})

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

    def test_binary_package_contains_provenance_and_licenses(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist, source = root / 'dist', root / 'source'
            dist.mkdir(); source.mkdir()
            for name in ('NewPageMergeMDL.exe', 'NewPageMergeMDL-Decompiler.exe', 'NewPageVRMLtoX3D.exe', 'NewPageMergeMDL-C4D.exe'):
                (dist / name).write_bytes(b'binary')
            (dist / 'subtools').mkdir()
            for name in ('l4d_animswap', 'meshtool', 'vmd2valvebiped'):
                (dist / 'subtools' / (name + '.exe')).write_bytes(b'binary')
            for name in ('LICENSE', 'README.md', 'README.en.md', 'INSTALL.md', 'COMPATIBILITY.md', 'BINARY_ANALYSIS.md', 'AUTOMATION.md', 'RESEARCH.md', 'VALIDATION.md', 'IMPROVEMENTS.md', 'FEATURE_MATRIX.md'):
                (source / name).write_text(name)
            (source / 'libs/vendor').mkdir(parents=True)
            (source / 'libs/vendor/LICENSE').write_text('vendor notice')
            (source / 'libs/nvtristrip').mkdir()
            for name in ('README.txt', 'SOURCE.md'):
                (source / 'libs/nvtristrip' / name).write_text('dependency provenance')
            (source / 'libs/meshoptimizer').mkdir()
            for name in ('LICENSE.md', 'SOURCE.md'):
                (source / 'libs/meshoptimizer' / name).write_text('meshopt provenance')
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
                for name in ('README.txt', 'SOURCE.md'):
                    self.assertIn('NewPageMergeMDL/libs/nvtristrip/' + name, archive.namelist())
                for name in ('LICENSE.md', 'SOURCE.md'):
                    self.assertIn('NewPageMergeMDL/libs/meshoptimizer/' + name, archive.namelist())
                self.assertFalse(any('StudioMDL-CE' in name for name in archive.namelist()))

            for name in ('NewPageMergeMDL', 'NewPageMergeMDL-Decompiler', 'NewPageVRMLtoX3D',
                         'subtools/l4d_animswap', 'subtools/meshtool', 'subtools/vmd2valvebiped'):
                (dist / name).write_bytes(b'\x7fELFfixture')
            sync.package(argparse.Namespace(dist=dist, source=source, output=root / 'linux.zip',
                                            platform='linux64', manifest=root / 'manifest.json'))
            with zipfile.ZipFile(root / 'linux.zip') as archive:
                for name in ('NewPageMergeMDL', 'subtools/meshtool'):
                    info = archive.getinfo('NewPageMergeMDL/' + name)
                    self.assertEqual(info.create_system, 3)
                    self.assertEqual((info.external_attr >> 16) & 0o777, 0o755)

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



class PackageValidationTests(unittest.TestCase):
    def make_package(self, root, extra=None, manifest=None):
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
                'FIVE_COMPILER_COMPLETION.md','O5_FORMAT_IMPORTS.md','MESH_STATE_WORKFLOW.md','VRM_RUNTIME.md',
                'integration/gmod/newpage_vertexanim.lua','integration/gmod/newpage_meshstates.lua',
                'integration/gmod/newpage_vrm.lua','integration/gmod/newpage_vrm_materials.lua',
                'tools/mesh_states.py','tools/vrm_runtime.py','tools/vrml_import.py',
                'tools/vrml_converter/CMakeLists.txt','tools/vrml_converter/main.cpp',
                'tools/vrml_converter/meshlab/Parser.cpp','tools/vrml_converter/meshlab/Parser.h',
                'tools/vrml_converter/meshlab/Scanner.cpp','tools/vrml_converter/meshlab/Scanner.h',
                'tools/vrml_converter/meshlab/LICENSE','tools/vrml_converter/meshlab/SOURCE.md',
                'libs/assimp/contrib/pugixml/src/pugixml.cpp','libs/assimp/contrib/pugixml/src/pugixml.hpp',
                'libs/assimp/contrib/pugixml/src/pugiconfig.hpp','libs/assimp/contrib/pugixml/LICENSE.md',
                'libs/tinyusdz/LICENSE','libs/tinyusdz/LICENSE-APACHE-2.0',
            ):z.writestr('NewPageMergeMDL/'+name,'fixture')
            for name in ('NewPageMergeMDL','NewPageMergeMDL-Decompiler','NewPageVRMLtoX3D'):
                z.writestr('NewPageMergeMDL/'+name+suffix,binary)
            if suffix:z.writestr('NewPageMergeMDL/NewPageMergeMDL-C4D.exe',binary)
            for name in ('l4d_animswap', 'meshtool', 'vmd2valvebiped'):
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
            self.assertTrue(self.verifier().verify(archive,{'project_version':'1.2.6'},root/'extracted').exists())

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
