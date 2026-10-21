"""Exercise the mutation harness with isolated, authored child processes."""
import json
from pathlib import Path
import random
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import bounded_mutation as runner


class ProcessClassification(unittest.TestCase):
    def run_program(self, source, **limits):
        with tempfile.TemporaryDirectory() as directory:
            return runner.run([sys.executable, '-c', source], Path(directory),
                              limits.pop('timeout', 5), **limits)

    def test_normal_acceptance_and_parser_rejection(self):
        for code, expected in ((0, 'accepted'), (1, 'rejected'), (2, 'rejected'), (17, 'crash')):
            with self.subTest(code=code):
                result = self.run_program(f'raise SystemExit({code})')
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['exit_code'], code)

    def test_sanitizer_diagnostics_override_normal_exit_and_normalize_addresses(self):
        for exit_code in (0, 1, 86):
            result = self.run_program("print('==12345==ERROR: AddressSanitizer: heap-buffer-overflow at 0xabcdef'); "
                                      f'raise SystemExit({exit_code})')
            self.assertEqual(result['status'], 'sanitizer')
            self.assertEqual(result['signature'], ['sanitizer', None,
                             '==PID==ERROR: AddressSanitizer: heap-buffer-overflow at <address>'])

    def test_timeout_reaps_child(self):
        result = self.run_program('import time; time.sleep(20)', timeout=.15)
        self.assertEqual(result['status'], 'timeout')
        self.assertLess(result['seconds'], 5)

    def test_log_budget_reaps_noisy_child(self):
        result = self.run_program("import sys,time; print('x'*8192,flush=True); time.sleep(20)", log_limit=1024)
        self.assertEqual(result['status'], 'log-budget')
        self.assertLessEqual(len(result['log'].encode()), 1024)
        fast = self.run_program("print('x'*8192)", log_limit=1024)
        self.assertEqual(fast['status'], 'log-budget')

    def test_resident_memory_budget_reaps_child(self):
        # Use a deterministic measured-RSS boundary, without allocating excessive
        # RAM on the user's machine or depending on sanitizer shadow mappings.
        with patch.object(runner, 'memory_bytes', return_value=2 * 1024 ** 3):
            result = self.run_program('import time; time.sleep(20)', memory_mb=64)
        self.assertEqual(result['status'], 'memory-budget')


class ReductionAndEvidence(unittest.TestCase):
    def test_minimization_keeps_failure_and_saved_repro_is_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed, runs = root / 'seed', root / 'runs'
            seed.mkdir(); runs.mkdir()
            (seed / 'payload.bin').write_bytes(b'valid')
            (seed / 'support.txt').write_text('required companion')
            script = ("from pathlib import Path; "
                      "assert Path('support.txt').read_text() == 'required companion'; "
                      "raise SystemExit(17 if b'BOOM' in Path('payload.bin').read_bytes() else 1)")
            case = dict(name='authored', folder=seed, target='payload.bin',
                        command=[sys.executable, '-c', script])
            original = b'prefix' * 8 + b'BOOM' + b'suffix' * 8
            first = runner.execute_case(case, original, runs, 5, 128)
            self.assertEqual(first['status'], 'crash')
            reduced, attempts = runner.minimize(case, original, first['signature'], runs,
                                               5, 128, time.monotonic() + 20, 64)
            self.assertIn(b'BOOM', reduced)
            self.assertLess(len(reduced), len(original))
            finding = runner.preserve(root, case, original, reduced, first, 'authored-marker', 0, attempts)
            record = json.loads((root / finding / 'finding.json').read_text())
            self.assertEqual(record['minimized_sha256'], runner.digest(reduced))
            self.assertEqual((root / finding / 'repro/payload.bin').read_bytes(), reduced)
            repro = dict(case, folder=root / finding / 'repro')
            self.assertEqual(runner.execute_case(repro, reduced, runs, 5, 128)['signature'], first['signature'])
            self.assertEqual(list(runs.iterdir()), [])
            self.assertEqual((seed / 'payload.bin').read_bytes(), b'valid')

    def test_seeded_mutations_repeat_without_modifying_original(self):
        payload = b'version 1\n0 1 2 3 4 5 6\n' * 8
        def samples():
            rng = random.Random(1238)
            return [runner.mutate(payload, rng, index, 'dmx') for index in range(18)]
        self.assertEqual(samples(), samples())
        self.assertEqual(payload, b'version 1\n0 1 2 3 4 5 6\n' * 8)


if __name__ == '__main__':
    unittest.main()
