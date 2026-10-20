"""Replacement notes resume from packaged source rather than an unmoved tag."""
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'.github/scripts'))
import replacement_notes
import upstream_release as sync
from upstream_release import append_release_notes
spec = importlib.util.spec_from_file_location('release_notes', ROOT/'.github/scripts/release-notes.py')
notes = importlib.util.module_from_spec(spec); spec.loader.exec_module(notes)


class ReplacementNotes(unittest.TestCase):
    def test_render_deduplicates_commit_ids_and_filters_ci_flags(self):
        log = '\0'+'a'*40+'\x1fFix helpers [skip ci]\n\0'+'a'*40+'\x1fFix helpers [skip ci]\n'
        self.assertEqual(notes.render(log), '- Fix helpers')
        self.assertEqual(notes.render(log, ['a'*40]), 'No changes.')

    def test_replacement_uses_packaged_source_commit_and_retry_is_idempotent(self):
        old, head = 'a'*40, 'b'*40
        calls = []
        def git(command):
            calls.append(command)
            return ('\0'+head+'\x1fRecover helper outputs [skip ci]\n').encode() if command[1]=='log' and command[-1]!=head+'..'+head else b''
        release = dict(tag_name='v1.2.36', body='- Existing fix')
        text = replacement_notes.incremental_notes(release, {'controller_sha':old}, head, 'c'*64+'  linux.zip', git)
        self.assertIn(old+'..'+head, calls[-1])
        self.assertEqual(text.count('- Recover helper outputs'), 1)
        self.assertNotIn('[skip ci]', text)
        again = replacement_notes.incremental_notes(dict(release, body=text), {'controller_sha':head}, head, 'd'*64+'  linux.zip', git)
        self.assertEqual(again.count('- Recover helper outputs'), 1)
        self.assertEqual(again.count('## v1.2.36 后续更新'), 1)
        self.assertNotIn('c'*64, again)
        self.assertIn('d'*64, again)

    def test_body_edit_failure_resumes_its_previous_source_range(self):
        old, head = 'a'*40, 'b'*40
        release = dict(tag_name='v1.2.36', body='- Earlier fix\n\n<!-- newpage-source:'+old+' -->')
        calls=[]
        def git(command):
            calls.append(command)
            return ('\0'+head+'\x1fNext fix\n').encode() if command[1]=='log' else b''
        text=replacement_notes.incremental_notes(release,{'controller_sha':head},head,'c'*64+'  win.zip',git)
        self.assertIn(old+'..'+head,calls[-1]);self.assertIn('Next fix',text)

    def test_existing_bullets_are_not_repeated_across_replacement_runs(self):
        previous='- Old fix\n\n## v1.2.36 后续更新\n\n**subtools:**\n- Recover outputs'
        result=append_release_notes(previous,'**subtools:**\n- Recover outputs\n\n**platform:**\n- Fix linking','v1.2.36')
        self.assertEqual(result.count('- Recover outputs'),1)
        self.assertIn('Fix linking',result)

    def test_missing_manifest_commit_fails_without_using_tag(self):
        def git(command):
            self.fail('no Git fallback is allowed for an unknown previous build')
        with self.assertRaisesRegex(ValueError, 'Invalid release source commit'):
            replacement_notes.incremental_notes(dict(tag_name='v1.2.36',body='Reviewed changes'), {}, 'b'*40, '', git)

    def test_body_marker_cannot_hide_missing_package_provenance(self):
        def git(command):
            self.fail('body markers cannot replace a missing package source commit')
        with self.assertRaisesRegex(ValueError, 'Invalid release source commit'):
            replacement_notes.incremental_notes(dict(tag_name='v1.2.36',body='<!-- newpage-source:'+'a'*40+' -->'), {}, 'b'*40, '', git)

    def test_unmarked_current_package_does_not_fall_back_to_old_tag(self):
        head='b'*40
        def git(command):
            self.assertNotIn('rev-parse', command)
            if command[1]=='log':self.assertEqual(command[-1],head+'..'+head)
            return b''
        text=replacement_notes.incremental_notes(dict(tag_name='v1.2.36',body='Reviewed changes'),
                                                {'controller_sha':head},head,'c'*64+'  win.zip',git)
        self.assertIn('Reviewed changes',text)
        self.assertNotIn('No changes.',text)
        self.assertNotIn('后续更新',text)

    def test_hidden_commit_tracking_does_not_add_empty_visible_update_section(self):
        previous='- Existing fix'
        current='<!-- newpage-commit:'+'a'*40+' -->\n\nZIP SHA256:\n```text\n'+'b'*64+'  win.zip\n```'
        text=append_release_notes(previous,current,'v1.2.36','c'*40)
        self.assertNotIn('后续更新',text)
        self.assertIn('<!-- newpage-commit:',text)


class ReplacementStates(unittest.TestCase):
    """Real commit ancestry and actual ZIP manifests across interrupted uploads."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='release-notes-states-')
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        self.old = self.commit('Old package')
        self.head = self.commit('Preserve helper outputs [skip ci]')
        self.payloads = {}

    def git(self, command):
        return subprocess.check_output(['git', '-C', str(self.repo), *command[1:]], stderr=subprocess.PIPE)

    def commit(self, message):
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Release test',
                        '-c', 'user.email=release-test@example.invalid', 'commit', '-q',
                        '--allow-empty', '-m', message], check=True)
        return self.git(['git', 'rev-parse', 'HEAD']).decode().strip()

    def asset(self, platform, sha, fingerprint=None):
        data = io.BytesIO()
        manifest = dict(controller_sha=sha, project_version='1.2.37', fingerprint=fingerprint or sha)
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('NewPageMergeMDL/upstream-manifest.json', json.dumps(manifest))
        payload = data.getvalue()
        url = 'asset:' + platform + ':' + sha + ':' + manifest['fingerprint']
        self.payloads[url] = payload
        return dict(name='newpage-merge-mdl-' + platform + '.zip', url=url, size=len(payload),
                    digest='sha256:' + hashlib.sha256(payload).hexdigest())

    def manifest(self, release):
        with patch.object(replacement_notes, 'fetch', side_effect=lambda url, **_: self.payloads[url]):
            return replacement_notes.manifest_for_release(release)

    def test_packages_override_stale_standalone_manifest(self):
        stale = dict(name='upstream-manifest.json', url='stale')
        self.payloads['stale'] = json.dumps(dict(controller_sha='f'*40)).encode()
        release = dict(body='', assets=[stale, self.asset('win64', self.old), self.asset('linux64', self.old)])
        with patch.object(replacement_notes, 'fetch', side_effect=lambda url, **_: self.payloads[url]) as fetch:
            manifest = replacement_notes.manifest_for_release(release)
        self.assertEqual(manifest['controller_sha'], self.old)
        self.assertEqual({call.args[0] for call in fetch.call_args_list}, {a['url'] for a in release['assets'][1:]})

    def test_initial_checkpoint_recovers_partial_upload_and_failed_body_edit(self):
        original = '原有日志\n\n- Existing reviewed fix\n'
        release = dict(tag_name='v1.2.37', body=original,
                       assets=[self.asset('win64', self.old), self.asset('linux64', self.old)])
        manifest = self.manifest(release)
        expected = replacement_notes.incremental_notes(release, manifest, self.head, 'a'*64+'  win.zip', self.git)
        checkpoint = replacement_notes.checkpoint_body(release, manifest, self.head, self.git)
        self.assertTrue(checkpoint.startswith(original))
        self.assertNotIn('Preserve helper outputs', checkpoint)
        self.assertEqual(replacement_notes.checkpoint_body(dict(release, body=checkpoint), manifest, self.head, self.git), checkpoint)
        release['body'] = checkpoint
        # The first upload succeeded, the second failed. Both manifests must be
        # read, and the saved old source (not whichever ZIP is smaller) wins.
        release['assets'][0] = self.asset('win64', self.head)
        partial = replacement_notes.incremental_notes(release, self.manifest(release), self.head, 'a'*64+'  win.zip', self.git)
        self.assertEqual(partial.count('- Preserve helper outputs'), 1)
        release['assets'][1] = self.asset('linux64', self.head)
        # Now both uploads succeeded, but editing the final body failed.
        retry = replacement_notes.incremental_notes(release, self.manifest(release), self.head, 'a'*64+'  win.zip', self.git)
        self.assertEqual(retry.count('- Preserve helper outputs'), 1)
        self.assertIn('- Existing reviewed fix', retry)
        self.assertNotIn('[skip ci]', retry)
        release['body'] = retry
        again = replacement_notes.incremental_notes(release, self.manifest(release), self.head, 'b'*64+'  win.zip', self.git)
        self.assertEqual(again.count('- Preserve helper outputs'), 1)
        self.assertNotIn('a'*64, again)
        self.assertIn('b'*64, again)
        self.assertIn('- Preserve helper outputs', expected)

    def test_mixed_packages_without_checkpoint_fail(self):
        release = dict(body='Old notes', assets=[self.asset('win64', self.old), self.asset('linux64', self.head)])
        with self.assertRaisesRegex(ValueError, 'sources differ'):
            self.manifest(release)

    def test_checkpoint_must_precede_every_package(self):
        release = dict(body='<!-- newpage-source:'+self.head+' -->',
                       assets=[self.asset('win64', self.old), self.asset('linux64', self.head)])
        with self.assertRaises(subprocess.CalledProcessError):
            replacement_notes.source_base(release, self.manifest(release), self.head, self.git)

    def test_same_commit_with_different_source_fingerprints_fails(self):
        release = dict(body='<!-- newpage-source:'+self.old+' -->',
                       assets=[self.asset('win64', self.old, 'first'), self.asset('linux64', self.old, 'second')])
        with self.assertRaisesRegex(ValueError, 'source identities differ'):
            self.manifest(release)

    def test_bad_package_is_not_hidden_by_legacy_manifest_or_checkpoint(self):
        bad = self.asset('win64', self.old); bad['digest'] = 'sha256:'+'0'*64
        release = dict(body='<!-- newpage-source:'+self.old+' -->', assets=[bad,
                       dict(name='upstream-manifest.json', url='stale')])
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            self.manifest(release)


class PackageProvenance(unittest.TestCase):
    """Historical manifest hashes are reconciled only against actual source ZIPs."""
    controller = 'a' * 40

    @staticmethod
    def refresh_fingerprint(manifest):
        payload = {key: manifest[key] for key in (
            'schema', 'controller_sha', 'overlay_sha256', 'configuration_sha256', 'pulsemodel', 'integration')}
        payload['project_version'] = manifest.get('version_base', manifest['project_version'])
        manifest['fingerprint'] = sync.fingerprint(payload)

    def fixture(self, *, crlf=False, automatic=False):
        config = dict(project_version='1.2.34', pulsemodel='official/pulse', pulse_base='b' * 40)
        overlay = b'--- a/source.cpp\n+++ b/source.cpp\n'
        configuration = (json.dumps(config, indent=2) + '\n').encode()
        declared_overlay = overlay.replace(b'\n', b'\r\n') if crlf else overlay
        declared_config = configuration.replace(b'\n', b'\r\n') if crlf else configuration
        manifest = dict(schema=1, controller_sha=self.controller, project_version='1.2.36',
                        version_base='1.2.34', pulsemodel=dict(repo=config['pulsemodel'], sha=config['pulse_base']),
                        integration=dict(pulsemodel='source patch overlay'),
                        overlay_sha256=hashlib.sha256(declared_overlay).hexdigest(),
                        configuration_sha256=hashlib.sha256(declared_config).hexdigest())
        if automatic:
            manifest['pulsemodel']['sha'] = 'c' * 40
            config['project_version'] = '1.2.36'
            configuration = (json.dumps(config, indent=2) + '\n').encode()
            overlay += b'@@ refreshed after version stamping @@\n'
            build_overlay = overlay.replace(b'\n', b'\r\n') if crlf else overlay
            manifest['build_overlay_sha256'] = hashlib.sha256(build_overlay).hexdigest()
        else:
            manifest['source_kind'] = 'maintained checkout'
        self.refresh_fingerprint(manifest)
        files = {'automation/compatibility.patch': overlay, 'automation/upstreams.json': configuration,
                 'CMakeLists.txt': b'project(NewPageMergeMDL VERSION 1.2.36 LANGUAGES CXX C)\n',
                 'source.cpp': b'int main() { return 0; }\n', 'data.bin': b'\x00\r\n\xff'}
        return manifest, files

    def package(self, manifest, files, *, comment=None):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as package:
            package.writestr('NewPageMergeMDL/upstream-manifest.json', json.dumps(manifest))
            if files is not None:
                source_data = io.BytesIO()
                with zipfile.ZipFile(source_data, 'w') as source:
                    source.comment = (self.controller if comment is None else comment).encode()
                    for name, content in files.items():
                        source.writestr('NewPageMergeMDL/' + name, content)
                package.writestr('NewPageMergeMDL/sources/NewPageMergeMDL-source.zip', source_data.getvalue())
        return data.getvalue()

    def read_pair(self, first, second):
        payloads = dict(win64=first, linux64=second)
        assets = [dict(name='newpage-merge-mdl-' + platform + '.zip', url=platform,
                       digest='sha256:' + hashlib.sha256(data).hexdigest()) for platform, data in payloads.items()]
        release = dict(tag_name='v1.2.36', body='', draft=False, published_at='2026-10-20', assets=assets)
        with patch.object(replacement_notes, 'fetch', side_effect=lambda url, **_: payloads[url]):
            replacement = replacement_notes.manifest_for_release(release)
        with patch.object(sync, 'api', return_value=[release]), \
                patch.object(sync, 'fetch', side_effect=lambda url, **_: payloads[url]):
            published = sync.published_manifest('official/project')
        self.assertEqual(sync.package_source_identity(replacement), sync.package_source_identity(published))
        return published

    def assert_pair_rejected(self, first, second, pattern):
        payloads = dict(win64=first, linux64=second)
        release = dict(tag_name='v1.2.36', body='', draft=False, assets=[
            dict(name='newpage-merge-mdl-' + platform + '.zip', url=platform)
            for platform in payloads])
        with patch.object(replacement_notes, 'fetch', side_effect=lambda url, **_: payloads[url]), \
                self.assertRaisesRegex(ValueError, pattern):
            replacement_notes.manifest_for_release(release)
        with patch.object(sync, 'api', return_value=[release]), \
                patch.object(sync, 'fetch', side_effect=lambda url, **_: payloads[url]), \
                self.assertRaisesRegex(ValueError, pattern):
            sync.published_manifest('official/project')

    def test_historical_crlf_hashes_match_exact_lf_source_archive(self):
        windows, files = self.fixture(crlf=True)
        linux, linux_files = self.fixture()
        self.assertEqual(files, linux_files)
        self.assertNotEqual(windows['fingerprint'], linux['fingerprint'])
        result = self.read_pair(self.package(windows, files), self.package(linux, linux_files))
        self.assertEqual(result['fingerprint'], linux['fingerprint'])
        self.assertEqual(result['overlay_sha256'], hashlib.sha256(files['automation/compatibility.patch']).hexdigest())
        self.assertEqual(result['version_base'], '1.2.34')
        self.assertEqual(result['project_version'], '1.2.36')

    def test_only_known_overlay_and_config_allow_source_newline_equivalence(self):
        windows, files = self.fixture(crlf=True)
        linux, linux_files = self.fixture()
        for name in ('automation/compatibility.patch', 'automation/upstreams.json'):
            files[name] = files[name].replace(b'\n', b'\r\n')
        self.read_pair(self.package(windows, files), self.package(linux, linux_files))

    def test_maintained_config_checks_base_version_and_cmake_checks_build_version(self):
        original, original_files = self.fixture()
        good = self.package(original, original_files)
        for name, content, pattern in (
                ('automation/upstreams.json', original_files['automation/upstreams.json'].replace(b'1.2.34', b'1.2.36'), 'configuration'),
                ('CMakeLists.txt', original_files['CMakeLists.txt'].replace(b'1.2.36', b'1.2.34'), 'CMake version')):
            with self.subTest(name=name):
                manifest, files = self.fixture()
                files[name] = content
                if name.endswith('.json'):
                    manifest['configuration_sha256'] = hashlib.sha256(content).hexdigest()
                    self.refresh_fingerprint(manifest)
                self.assert_pair_rejected(good, self.package(manifest, files), pattern)

    def test_corrupt_declared_fields_and_fingerprint_are_rejected(self):
        original, files = self.fixture()
        good = self.package(original, files)
        for field in ('overlay_sha256', 'configuration_sha256', 'fingerprint'):
            for refresh in (False, True):
                if refresh and field == 'fingerprint':
                    continue
                with self.subTest(field=field, refresh=refresh):
                    manifest = dict(original, **{field: '0' * 64})
                    if refresh:
                        self.refresh_fingerprint(manifest)
                    self.assert_pair_rejected(good, self.package(manifest, files), 'fingerprint|declared')

    def test_corrupt_source_overlay_and_config_are_rejected(self):
        manifest, original_files = self.fixture()
        good = self.package(manifest, original_files)
        for name in ('automation/compatibility.patch', 'automation/upstreams.json'):
            with self.subTest(name=name):
                files = dict(original_files, **{name: original_files[name] + b'changed'})
                self.assert_pair_rejected(good, self.package(manifest, files), 'declared')

    def test_other_source_and_binary_contents_are_compared_as_raw_bytes(self):
        manifest, original_files = self.fixture()
        good = self.package(manifest, original_files)
        for name in ('source.cpp', 'data.bin'):
            with self.subTest(name=name):
                files = dict(original_files)
                files[name] = files[name].replace(b'\r\n', b'\n') if name.endswith('.bin') else files[name].replace(b'\n', b'\r\n')
                self.assert_pair_rejected(good, self.package(manifest, files), 'source identities')

    def test_source_comment_controller_and_required_files_are_verified(self):
        manifest, files = self.fixture()
        good = self.package(manifest, files)
        self.assert_pair_rejected(good, self.package(manifest, files, comment='d' * 40), 'comment')
        self.assert_pair_rejected(good, self.package(dict(manifest, controller_sha='invalid'), files), 'controller')
        missing = dict(files)
        del missing['automation/compatibility.patch']
        self.assert_pair_rejected(good, self.package(manifest, missing), 'missing required')

    def test_missing_source_archive_cannot_justify_historical_hash_mismatch(self):
        windows, _ = self.fixture(crlf=True)
        linux, _ = self.fixture()
        self.assert_pair_rejected(self.package(windows, None), self.package(linux, None), 'source identities')

    def test_automatic_stamped_snapshot_preserves_original_controller_identity(self):
        linux, files = self.fixture(automatic=True)
        windows = dict(linux, build_overlay_sha256=hashlib.sha256(
            files['automation/compatibility.patch'].replace(b'\n', b'\r\n')).hexdigest())
        result = self.read_pair(self.package(windows, files, comment=''), self.package(linux, files, comment=''))
        for field in ('overlay_sha256', 'configuration_sha256', 'fingerprint'):
            self.assertEqual(result[field], linux[field])
        self.assertNotEqual(result['overlay_sha256'], hashlib.sha256(files['automation/compatibility.patch']).hexdigest())
        self.assertNotEqual(result['configuration_sha256'], hashlib.sha256(files['automation/upstreams.json']).hexdigest())
        self.assertEqual(result['build_overlay_sha256'], hashlib.sha256(files['automation/compatibility.patch']).hexdigest())

    def test_automatic_declared_inputs_and_actual_build_overlay_must_agree(self):
        original, files = self.fixture(automatic=True)
        good = self.package(original, files, comment='')
        for field in ('overlay_sha256', 'configuration_sha256', 'build_overlay_sha256', 'fingerprint'):
            with self.subTest(field=field):
                manifest = dict(original, **{field: '0' * 64})
                self.assert_pair_rejected(good, self.package(manifest, files, comment=''), 'fingerprint|declared')
        # A self-consistent but different controller input cannot be justified by
        # the stamped candidate's overlay/configuration, even with identical ZIPs.
        changed = dict(original, configuration_sha256='0' * 64)
        self.refresh_fingerprint(changed)
        self.assert_pair_rejected(good, self.package(changed, files, comment=''), 'source identities')


if __name__ == '__main__':
    unittest.main()
