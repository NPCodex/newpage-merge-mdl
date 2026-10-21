import sys
import tempfile
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.github/scripts'))
import manual_release as release


class Revisions(unittest.TestCase):
    head = 'a' * 40

    def test_drafts_without_tags_reserve_revisions(self):
        drafts = [dict(tag_name='v1.2.38-r7', draft=True, target_commitish='b' * 40)]
        self.assertEqual(release.choose_revision('1.2.38', self.head, {'v1.2.38-r2': self.head}, drafts), 'v1.2.38-r8')

    def test_retry_only_resumes_exact_source_draft(self):
        drafts = [dict(tag_name='v1.2.38-r7', draft=True, target_commitish=self.head)]
        self.assertEqual(release.choose_revision('1.2.38', self.head, {}, drafts), 'v1.2.38-r7')
        self.assertEqual(release.choose_revision('1.2.38', self.head, {'v1.2.38-r7': 'b' * 40}, drafts), 'v1.2.38-r8')
        drafts[0]['draft'] = False
        self.assertEqual(release.choose_revision('1.2.38', self.head, {}, drafts), 'v1.2.38-r8')

    def test_collision_is_rejected_before_upload(self):
        foreign = dict(draft=True, target_commitish='b' * 40)
        for item in (foreign, dict(draft=False, target_commitish=self.head)):
            with patch.object(release, 'find_release', return_value=item), patch.object(release.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'retry allocation'):
                    release.ensure_draft('o/r', 'v1.2.38-r1', self.head, 'notes')
                run.assert_not_called()

    def test_retry_has_no_creation_side_effect(self):
        with patch.object(release, 'find_release', return_value=dict(draft=True, target_commitish=self.head)), patch.object(release.subprocess, 'run') as run:
            release.ensure_draft('o/r', 'v1.2.38-r1', self.head, 'notes')
            run.assert_not_called()

    def test_workflow_upload_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = [Path(directory) / name for name in ('windows.zip', 'linux.zip')]
            for asset in assets:
                asset.write_bytes(asset.name.encode())
            current = dict(assets=[dict(name=p.name, digest='sha256:' + hashlib.sha256(p.read_bytes()).hexdigest()) for p in assets])
            argv = ['manual_release.py', 'upload', '--repo', 'o/r', '--head', self.head,
                    '--tag', 'v1.2.38-r1', '--notes', 'notes.md', '--', *map(str, assets)]
            with patch.object(sys, 'argv', argv), patch.object(release, 'ensure_draft') as draft, \
                    patch.object(release, 'find_release', return_value=current), patch.object(release.subprocess, 'run') as run:
                release.main()
                draft.assert_called_once_with('o/r', 'v1.2.38-r1', self.head, 'notes.md')
                self.assertEqual(run.call_args_list[0].args[0][-2:], list(map(str, assets)))

    def test_workflow_upload_with_separate_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = [Path(directory) / name for name in
                      ('windows.zip', 'linux.zip', 'windows-symbols.zip', 'linux-symbols.zip')]
            for asset in assets:
                asset.write_bytes(asset.name.encode())
            current = dict(assets=[dict(name=p.name, digest='sha256:' + hashlib.sha256(p.read_bytes()).hexdigest()) for p in assets])
            argv = ['manual_release.py', 'upload', '--repo', 'o/r', '--head', self.head,
                    '--tag', 'v1.2.38-r1', '--notes', 'notes.md', '--symbols', *map(str, assets[2:]),
                    '--', *map(str, assets[:2])]
            with patch.object(sys, 'argv', argv), patch.object(release, 'ensure_draft'), \
                    patch.object(release, 'find_release', return_value=current), patch.object(release.subprocess, 'run') as run:
                release.main()
                self.assertEqual(run.call_args_list[0].args[0][-4:], list(map(str, assets)))


if __name__ == '__main__':
    unittest.main()
