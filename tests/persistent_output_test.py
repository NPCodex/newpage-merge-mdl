"""External process-kill, locking and edited-output recovery tests.

Build persistent_output_harness.cpp separately; add -municode on MinGW.
No production executable contains these pause/throw checkpoints.
"""
from pathlib import Path
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest

HARNESS = str(Path(sys.argv.pop(1)).resolve())
FILES = ('model.vmdl', 'sources/anims/proportions.dmx', 'sources/graphs/world.vnmgraph',
         'game/anims/proportions.vnmclip_c', 'game/graphs/world.vnmgraph_c',
         'game/graphs/ui.vnmgraph_c', 'sources/debug/report.kv3', 'unrelated.txt')


class PersistentOutputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'Unicode Ü 模型 output'
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def seed(self, kind, first=False):
        if kind == 'ag2':
            names = ('model.vmdl',) if first else FILES
        else:
            names = () if first else ('decompiled model/model.qc', 'decompiled model/meshes/body.dmx',
                                      'decompiled model/user notes.txt', 'decompiled model/empty/.keep')
        for name in names:
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(('old ' + name).encode())

    def files(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*')
                if p.is_file() and not any(x.startswith('.newpage-output-') for x in p.parts)
                and '.newpage-txn-' not in p.name
                and not any('.newpage-txn-' in x for x in p.parts)}

    def run_tool(self, kind, operation='new', hook='', code=0, directory=None):
        p = subprocess.run([HARNESS, str(directory or self.root), kind, operation, hook],
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)
        self.assertEqual(p.returncode, code, p.stdout + p.stderr)
        return p.stdout + p.stderr

    def pause(self, kind, hook='', operation='new', directory=None):
        p = subprocess.Popen([HARNESS, str(directory or self.root), kind, operation, hook],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding='utf-8', errors='replace')
        messages = queue.Queue()
        def read():
            for line in p.stdout:
                messages.put(line)
            messages.put(None)
        threading.Thread(target=read, daemon=True).start()
        captured = []
        try:
            for _ in range(30):
                line = messages.get(timeout=10)
                if line is None:
                    self.fail('process exited before checkpoint: ' + ''.join(captured))
                captured.append(line)
                if line.startswith('PAUSED '):
                    return p
            self.fail('checkpoint not reached')
        except BaseException:
            p.kill(); p.wait(timeout=10); p.stdout.close(); raise

    def kill(self, p):
        p.kill()  # TerminateProcess / SIGKILL: no destructors or exception cleanup
        p.wait(timeout=10)
        p.stdout.close()

    def clean(self):
        self.assertFalse(list(self.root.rglob('intent')))
        self.assertFalse(list(self.root.rglob('commit')))
        self.assertFalse(list(self.root.rglob('work')))
        self.assertFalse([p for p in self.root.rglob('*') if '.newpage-txn-' in p.name])

    def test_ag2_kill_at_each_file_backup_publish_and_prepare_restores_old_set(self):
        self.seed('ag2'); old = self.files()
        hooks = ['begin:0', 'journal:0', 'ready:0']
        hooks += [f'{phase}:{i}' for phase in ('prepared', 'backed_up', 'published') for i in range(8)]
        for hook in hooks:
            with self.subTest(hook=hook):
                self.kill(self.pause('ag2', 'pause:' + hook))
                self.run_tool('ag2', 'recover'); self.assertEqual(self.files(), old); self.clean()
                self.run_tool('ag2', 'recover'); self.assertEqual(self.files(), old)

    def test_directory_kill_before_and_after_rename_restores_user_files(self):
        self.seed('directory'); old = self.files()
        for hook in ('begin:0', 'journal:0', 'prepared:0', 'ready:0', 'backed_up:0', 'published:0'):
            with self.subTest(hook=hook):
                self.kill(self.pause('directory', 'pause:' + hook))
                self.run_tool('directory', 'recover'); self.assertEqual(self.files(), old); self.clean()

    def test_kill_after_commit_preserves_new_set(self):
        for kind in ('ag2', 'directory'):
            with self.subTest(kind=kind):
                self.seed(kind)
                self.kill(self.pause(kind, 'pause:committed:0'))
                new = self.files()
                self.run_tool(kind, 'recover'); self.assertEqual(self.files(), new); self.clean()

    def test_first_publication_kill_removes_new_outputs_and_first_backup(self):
        for kind in ('ag2', 'directory'):
            with self.subTest(kind=kind):
                self.seed(kind, first=True); old = self.files()
                index = 6 if kind == 'ag2' else 0
                self.kill(self.pause(kind, f'pause:published:{index}'))
                self.run_tool(kind, 'recover'); self.assertEqual(self.files(), old); self.clean()

    def test_concurrent_target_is_rejected_and_process_kill_releases_lock(self):
        for kind in ('ag2', 'directory'):
            with self.subTest(kind=kind):
                self.seed(kind); old = self.files(); p = self.pause(kind, operation='hold')
                try:
                    self.assertIn('locked by another process', self.run_tool(kind, code=1))
                    self.assertEqual(self.files(), old)
                finally:
                    self.kill(p)
                self.run_tool(kind, 'recover'); self.assertEqual(self.files(), old); self.clean()

    @unittest.skipUnless(os.name == 'nt', 'Windows Unicode case aliases')
    def test_unicode_case_aliases_share_same_lock_and_recovery(self):
        self.seed('ag2'); old = self.files(); alias = str(self.root).upper()
        p = self.pause('ag2', operation='hold')
        try:
            self.assertIn('locked by another process', self.run_tool('ag2', directory=alias, code=1))
        finally:
            self.kill(p)
        self.kill(self.pause('ag2', 'pause:backed_up:0', directory=alias))
        self.run_tool('ag2', 'recover'); self.assertEqual(self.files(), old); self.clean()

    def test_external_file_edit_blocks_whole_recovery_and_retains_backups(self):
        self.seed('ag2')
        self.kill(self.pause('ag2', 'pause:published:5'))
        changed = self.root / 'game/graphs/world.vnmgraph_c'
        changed.write_bytes(b'external user edit')
        before = self.files()
        self.assertIn('changed since transaction', self.run_tool('ag2', 'recover', code=1))
        self.assertEqual(self.files(), before)
        self.assertTrue(list(self.root.rglob('*.backup')))
        self.assertTrue(list(self.root.rglob('intent')))

    def test_external_directory_edit_blocks_recovery_and_preserves_user_addition(self):
        self.seed('directory'); self.kill(self.pause('directory', 'pause:published:0'))
        (self.root / 'decompiled model/new user file.txt').write_bytes(b'external edit')
        before = self.files()
        self.assertIn('changed since transaction', self.run_tool('directory', 'recover', code=1))
        self.assertEqual(self.files(), before)
        self.assertTrue(list(self.root.rglob('*.backup')))

    def test_kill_during_recovery_is_idempotent(self):
        self.seed('ag2'); old = self.files()
        self.kill(self.pause('ag2', 'pause:published:6'))
        self.kill(self.pause('ag2', 'pause:recovered:4', operation='recover'))
        self.run_tool('ag2', 'recover'); self.assertEqual(self.files(), old); self.clean()

    def test_exception_and_generation_failure_restore_outputs(self):
        for kind in ('ag2', 'directory'):
            self.seed(kind); old = self.files()
            self.run_tool(kind, operation='generation_failure', code=1)
            self.assertEqual(self.files(), old); self.clean()
            self.run_tool(kind, hook='throw:published:0', code=1)
            self.assertEqual(self.files(), old); self.clean()

    def test_kill_during_directory_disposal_and_restore_can_resume(self):
        self.seed('directory')
        for hook in ('discarded:0', 'cleanup:0', 'discard_child:0', 'discard_root:0'):
            with self.subTest(rollback_hook=hook):
                old = self.files()
                self.kill(self.pause('directory', 'pause:published:0'))
                self.kill(self.pause('directory', 'pause:' + hook, operation='recover'))
                self.run_tool('directory', 'recover')
                self.assertEqual(self.files(), old); self.clean()
        for hook in ('cleanup:0', 'discard_child:0', 'discard_root:0'):
            with self.subTest(committed_hook=hook):
                self.kill(self.pause('directory', 'pause:' + hook))
                new = self.files()
                self.run_tool('directory', 'recover')
                self.assertEqual(self.files(), new); self.clean()

    def test_external_edit_during_generation_prevents_publication(self):
        for kind in ('ag2', 'directory'):
            with self.subTest(kind=kind):
                self.seed(kind)
                p = self.pause(kind, 'wait:generated:0')
                changed = self.root / ('model.vmdl' if kind == 'ag2' else 'decompiled model/user notes.txt')
                try:
                    changed.write_bytes(b'external edit during generation')
                    expected = self.files()
                    (self.root / '.continue').touch()
                    self.assertEqual(p.wait(timeout=15), 1)
                finally:
                    if p.poll() is None: self.kill(p)
                    else: p.stdout.close()
                    (self.root / '.continue').unlink(missing_ok=True)
                self.assertEqual(self.files(), expected); self.clean()

    def test_backup_edit_blocks_recovery(self):
        self.seed('ag2'); self.kill(self.pause('ag2', 'pause:published:0'))
        backup = next(self.root.glob('model.vmdl.newpage-txn-*.backup'))
        backup.write_bytes(b'external backup edit')
        before = self.files()
        self.assertIn('changed since transaction', self.run_tool('ag2', 'recover', code=1))
        self.assertEqual(backup.read_bytes(), b'external backup edit')
        self.assertEqual(self.files(), before)

    def test_journal_destination_outside_whitelist_is_refused(self):
        self.seed('ag2'); self.kill(self.pause('ag2', 'pause:published:0'))
        intent = next(self.root.rglob('intent'))
        outside = Path(self.temp.name) / 'user file.txt'
        outside.write_bytes(b'user data')
        text = intent.read_text(encoding='utf-8')
        expected = (self.root / 'model.vmdl').as_posix()
        self.assertIn(expected, text)
        intent.write_text(text.replace(expected, outside.as_posix(), 1), encoding='utf-8')
        before = self.files()
        self.assertIn('unsafe output recovery destination', self.run_tool('ag2', 'recover', code=1))
        self.assertEqual(outside.read_bytes(), b'user data')
        self.assertEqual(self.files(), before)

    def test_reserved_output_names_are_rejected_before_staging(self):
        for kind, name in (('reserved_journal', '.newpage-output-transactions'),
                           ('reserved_lock', '.newpage-output-locks')):
            with self.subTest(name=name):
                target = self.root / name
                target.mkdir()
                marker = target / 'user-file'
                marker.write_bytes(b'keep user data')
                self.assertIn('reserved transaction storage', self.run_tool(kind, code=1))
                self.assertEqual(list(target.iterdir()), [marker])
                self.assertEqual(marker.read_bytes(), b'keep user data')

    def test_existing_first_backup_is_preserved(self):
        self.seed('ag2')
        (self.root / 'model.vmdl.bak').write_bytes(b'first original model')
        self.run_tool('ag2')
        self.assertEqual((self.root / 'model.vmdl.bak').read_bytes(), b'first original model')
        self.clean()


if __name__ == '__main__':
    unittest.main()
