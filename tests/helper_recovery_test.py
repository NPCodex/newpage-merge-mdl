"""Kill real helper writers at publication/recovery boundaries, then restart."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


CHILD = r'''
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from output_transaction import Publication
root, phase = Path(sys.argv[2]), sys.argv[3]
replace = os.replace
counts = {}
def stop(kind):
    counts[kind] = counts.get(kind, 0) + 1
    if phase in (kind, kind + ':' + str(counts[kind])):
        (root/'stopped').write_text(kind)
        while True: time.sleep(60)
def checkpoint(source, target):
    result = replace(source, target)
    source, target = Path(source), Path(target)
    if target.name.startswith('.newpage-helper-old-'): stop('backup')
    if source.name.startswith('.newpage-helper-new-'): stop('new')
    if source.name.startswith('.newpage-helper-old-'): stop('recover')
    if target.name.startswith('.newpage-helper-transaction-') and json.loads(target.read_text()).get('committed'):
        stop('committed')
    return result
os.replace = checkpoint
with Publication() as publication:
    if phase.startswith('recover'):
        publication.reserve(root/'b.json')
    else:
        for name in ('a.mdl', 'c.side'):
            staged = publication.work/name; staged.write_bytes(('new '+name).encode())
            publication.add(staged, root/name)
        publication.reserve(root/'b.json')['remove'] = True
        publication.commit()
'''


class HelperRecovery(unittest.TestCase):
    tools = Path(__file__).resolve().parents[1]/'tools'

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='helper-durable-')
        self.root = Path(self.temporary.name).resolve()
        (self.root/'a.mdl').write_bytes(b'old model')
        (self.root/'b.json').write_bytes(b'old metadata')

    def tearDown(self):
        self.temporary.cleanup()

    def interrupted(self, phase):
        marker = self.root/'stopped'
        if marker.exists(): marker.unlink()
        with (self.root/'child.log').open('w') as log:
            child = subprocess.Popen([sys.executable, '-c', CHILD, str(self.tools), str(self.root), phase],
                                     stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 15
                while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(marker.exists(), (self.root/'child.log').read_text())
            finally:
                if child.poll() is None: child.kill()
                child.wait(timeout=10)

    def recover(self):
        # Import using the caller's actual package tools when this suite is
        # included by verify_package's helper-publication checks.
        sys.path.insert(0, str(self.tools))
        import output_transaction
        with output_transaction.Publication() as publication:
            publication.reserve(self.root/'b.json')

    def old_outputs(self):
        self.assertEqual((self.root/'a.mdl').read_bytes(), b'old model')
        self.assertEqual((self.root/'b.json').read_bytes(), b'old metadata')
        self.assertFalse((self.root/'c.side').exists())
        self.assertFalse(list(self.root.glob('*.newpage-helper-journal')))
        self.assertFalse(list(self.root.glob('.newpage-helper-*')))

    def test_killed_backup_and_partial_publication_restore_complete_set(self):
        for phase in ('backup:1', 'backup:2', 'new:1', 'new:2'):
            with self.subTest(phase=phase):
                self.interrupted(phase)
                self.recover()
                self.old_outputs()

    def test_recovery_can_itself_be_killed_and_restarted(self):
        self.interrupted('new:2')
        self.interrupted('recover:1')
        self.recover()
        self.old_outputs()

    def test_killed_committed_cleanup_keeps_complete_new_outputs(self):
        self.interrupted('committed')
        self.recover()
        self.assertEqual((self.root/'a.mdl').read_bytes(), b'new a.mdl')
        self.assertEqual((self.root/'c.side').read_bytes(), b'new c.side')
        self.assertFalse((self.root/'b.json').exists())
        self.assertFalse(list(self.root.glob('*.newpage-helper-journal')))
        self.assertFalse(list(self.root.glob('.newpage-helper-*')))

    def test_external_edit_stops_whole_recovery_without_consuming_backups(self):
        self.interrupted('new:2')
        (self.root/'a.mdl').write_bytes(b'external edit')
        backups = {p.name:p.read_bytes() for p in self.root.glob('.newpage-helper-old-*')}
        with self.assertRaisesRegex(OSError, 'recovery needs attention'):
            self.recover()
        self.assertEqual((self.root/'a.mdl').read_bytes(), b'external edit')
        self.assertEqual({p.name:p.read_bytes() for p in self.root.glob('.newpage-helper-old-*')}, backups)
        self.assertTrue(list(self.root.glob('*.newpage-helper-journal')))

    def test_conflicting_writer_blocks_recovery_of_every_member(self):
        self.interrupted('new:2')
        sys.path.insert(0, str(self.tools))
        import output_transaction
        with output_transaction.Publication() as active:
            active._acquire(self.root/'a.mdl')
            with self.assertRaisesRegex(ValueError, 'another helper'):
                self.recover()
            self.assertEqual((self.root/'a.mdl').read_bytes(), b'new a.mdl')
        self.recover()
        self.old_outputs()

    def test_directory_flush_failure_after_commit_never_restores_old_outputs(self):
        sys.path.insert(0, str(self.tools))
        import output_transaction
        original = output_transaction._sync_parent
        def fail_committed(path):
            if Path(path).name.startswith('.newpage-helper-transaction-') and json.loads(Path(path).read_text()).get('committed'):
                raise OSError('injected directory flush failure after committed marker rename')
            return original(path)
        with output_transaction.Publication() as publication:
            staged = publication.work/'new'; staged.write_bytes(b'new model')
            publication.add(staged, self.root/'a.mdl')
            with patch.object(output_transaction, '_sync_parent', fail_committed):
                publication.commit()
        self.assertEqual((self.root/'a.mdl').read_bytes(), b'new model')
        self.assertTrue(list(self.root.glob('*.newpage-helper-journal')))
        with output_transaction.Publication() as publication:
            publication.reserve(self.root/'a.mdl')
        self.assertEqual((self.root/'a.mdl').read_bytes(), b'new model')
        self.assertFalse(list(self.root.glob('.newpage-helper-*')))


if __name__ == '__main__':
    unittest.main()
