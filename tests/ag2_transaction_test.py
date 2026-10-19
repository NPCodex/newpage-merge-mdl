"""Run with a separately built ag2_transaction_harness.cpp.

Tests exception/file-error rollback only, not hard-kill or power-loss recovery.
The released AG2 executable contains no fault-injection environment variables.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

HARNESS = str(Path(sys.argv.pop(1)).resolve())
OLD = (
    'model.vmdl', 'content/anims/proportions.dmx', 'content/graphs/world.vnmgraph',
    'game/anims/proportions.vnmclip_c', 'game/graphs/world.vnmgraph_c',
    'content/debug/report.kv3', 'unrelated.txt',
)


class Ag2Transaction(unittest.TestCase):
    @staticmethod
    def path_forms(path):
        """Return path spellings Windows may use for one filesystem object."""
        raw = os.path.normpath(str(path))
        forms = {raw, raw.replace('\\', '/')}
        if os.name == 'nt':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            for function_name in ('GetLongPathNameW', 'GetShortPathNameW'):
                function = getattr(kernel32, function_name)
                function.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
                function.restype = ctypes.c_uint32
                buffer = ctypes.create_unicode_buffer(32768)
                length = function(raw, buffer, len(buffer))
                if length and length < len(buffer):
                    forms.update((buffer.value, buffer.value.replace('\\', '/')))
        return forms

    def assert_path_in(self, path, text):
        self.assertTrue(any(form in text for form in self.path_forms(path)),
                        f'{path!s} not found in {text!r}')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'outputs'
        self.tmp = Path(self.temp.name) / 'stage'
        self.tmp.mkdir()
        for name in OLD:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('old ' + name).encode())

    def tearDown(self):
        self.temp.cleanup()

    def run_tool(self, mode, code=1):
        env = os.environ.copy()
        env.update(TEMP=str(self.tmp), TMP=str(self.tmp), TMPDIR=str(self.tmp))
        result = subprocess.run([HARNESS, str(self.root), mode], env=env,
                                capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def files(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()
                and not any(x.startswith('.newpage-output-') or '.newpage-txn-' in x for x in p.parts)}

    def assert_clean(self):
        self.assertEqual(list(self.tmp.iterdir()), [])
        self.assertFalse([p for p in self.root.rglob('*') if '.newpage-txn-' in p.name])
        self.assertFalse(list(self.root.rglob('intent')))
        self.assertFalse(list(self.root.rglob('work')))

    def test_success_updates_complete_set_and_removes_obsolete_debug(self):
        self.run_tool('new', code=0)
        files = self.files()
        self.assertNotIn('content/debug/report.kv3', files)
        self.assertEqual(files['unrelated.txt'], b'old unrelated.txt')
        for name in set(OLD) - {'unrelated.txt', 'content/debug/report.kv3'}:
            self.assertEqual(files[name], ('new ' + name).encode())
        self.assertEqual(files['model.vmdl.bak'], b'new model.vmdl.bak')
        self.assert_clean()

    def test_every_prepare_backup_and_publish_checkpoint_restores_whole_set(self):
        old = self.files()
        for phase in ('prepared', 'backed_up', 'published'):
            for index in range(7):
                with self.subTest(phase=phase, index=index):
                    self.run_tool(f'{phase}:{index}')
                    self.assertEqual(self.files(), old)
                    self.assert_clean()

    def test_failed_staging_and_actual_publish_error_preserve_all_outputs(self):
        old = self.files()
        for mode in ('staging_failure', 'publish_io_failure', 'duplicate'):
            with self.subTest(mode=mode):
                self.run_tool(mode)
                self.assertEqual(self.files(), old)
                self.assert_clean()

    def test_failed_first_publication_removes_new_files_and_directories(self):
        self.root = self.root / 'new model output'
        for phase in ('prepared', 'backed_up', 'published'):
            for index in range(6):
                with self.subTest(phase=phase, index=index):
                    self.run_tool(f'{phase}:{index}')
                    self.assertEqual(self.files(), {})
                    self.assert_clean()

    def test_existing_first_backup_is_not_replaced(self):
        backup = self.root / 'model.vmdl.bak'
        backup.write_bytes(b'first original model')
        self.run_tool('new', code=0)
        self.assertEqual(backup.read_bytes(), b'first original model')
        self.assert_clean()

    def test_backup_appearing_during_generation_aborts_publication(self):
        old = self.files()
        self.assertIn('output appeared during transaction', self.run_tool('backup_race'))
        old['model.vmdl.bak'] = b'first backup created concurrently'
        self.assertEqual(self.files(), old)
        self.assert_clean()

    def test_rollback_error_reports_and_preserves_recovery_evidence(self):
        output = self.run_tool('rollback_failure')
        self.assertIn('Recovery retained', output)
        manifests = list(self.root.rglob('intent'))
        self.assertEqual(len(manifests), 1)
        self.assert_path_in(manifests[0].parent, output)
        backups = list(self.root.rglob('*.backup'))
        self.assertTrue(any(p.read_bytes() == b'old model.vmdl' for p in backups))
        self.assertEqual((self.root / 'model.vmdl/obstruction').read_bytes(), b'keep this evidence')


if __name__ == '__main__':
    unittest.main()
