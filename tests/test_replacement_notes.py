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


if __name__ == '__main__':
    unittest.main()
