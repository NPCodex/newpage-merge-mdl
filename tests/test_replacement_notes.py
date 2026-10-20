"""Replacement notes resume from packaged source rather than an unmoved tag."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

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


if __name__ == '__main__':
    unittest.main()
