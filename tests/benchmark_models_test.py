"""Guard against accepting performance comparisons with unequal inputs/builds."""
import copy
import tempfile
import unittest
from pathlib import Path

from benchmark_models import compare, fixture_identity


def report():
    return dict(schema=3, machine={'node': 'fixture'}, runs=5, warmup=1, instrumentation='perfjson',
                first_process_runs=1,
                build_configuration={'configuration': 'MinSizeRel', 'CXX_compiler_sha256': 'same'},
                cases=[dict(qc='small.qc', qc_sha256='qc', input_sha256={'small.qc': 'qc', 'mesh.smd': 'mesh'},
                            metrics_schema=1, median_wall_ms=100, median_total_ms=100, median_peak_bytes=1000)])


class BenchmarkComparisonTests(unittest.TestCase):
    def test_identical_configuration_accepts_threshold_boundary(self):
        baseline = report()
        candidate = copy.deepcopy(baseline)
        candidate['cases'][0].update(median_wall_ms=120, median_total_ms=120, median_peak_bytes=1150)
        self.assertEqual(compare(candidate, baseline, .20, .15), [])

    def test_regression_identifies_metric(self):
        baseline = report()
        candidate = copy.deepcopy(baseline)
        candidate['cases'][0]['median_peak_bytes'] = 1200
        failures = compare(candidate, baseline, .20, .15)
        self.assertEqual([entry['metric'] for entry in failures], ['median_peak_bytes'])

    def test_post_measurement_report_cost_is_not_hidden(self):
        baseline = report()
        candidate = copy.deepcopy(baseline)
        candidate['cases'][0]['median_wall_ms'] = 150
        failures = compare(candidate, baseline, .20, .15)
        self.assertEqual([entry['metric'] for entry in failures], ['median_wall_ms'])

    def test_plain_mode_compares_wall_and_cannot_mix_with_report_mode(self):
        baseline = report()
        candidate = copy.deepcopy(baseline)
        candidate['instrumentation'] = 'none'
        with self.assertRaisesRegex(ValueError, 'instrumentation modes'):
            compare(candidate, baseline, .20, .15)
        baseline['instrumentation'] = 'none'
        for value in [baseline, candidate]:
            value['cases'][0].update(metrics_schema=None, median_total_ms=None, median_peak_bytes=None)
        self.assertEqual(compare(candidate, baseline, .20, .15), [])

    def test_unequal_or_missing_build_identity_is_not_a_pass(self):
        for configuration in [None, {'configuration': 'Release', 'CXX_compiler_sha256': 'same'},
                              {'configuration': 'MinSizeRel', 'CXX_compiler_sha256': 'different'}]:
            with self.subTest(configuration=configuration):
                baseline = report()
                baseline['build_configuration'] = configuration
                with self.assertRaises(ValueError):
                    compare(report(), baseline, .20, .15)

    def test_changed_mesh_is_rejected_even_when_qc_is_unchanged(self):
        baseline = report()
        baseline['cases'][0]['input_sha256']['mesh.smd'] = 'old mesh'
        with self.assertRaisesRegex(ValueError, 'dependencies differ'):
            compare(report(), baseline, .20, .15)

    def test_different_schemas_are_not_compared_silently(self):
        for change in ['harness', 'compiler']:
            with self.subTest(change=change):
                baseline = report()
                if change == 'harness':
                    baseline['schema'] = 2
                else:
                    baseline['cases'][0]['metrics_schema'] = 2
                with self.assertRaises(ValueError):
                    compare(report(), baseline, .20, .15)

    def test_missing_case_and_duplicate_names_are_rejected(self):
        for cases in [[], [report()['cases'][0], report()['cases'][0]]]:
            with self.subTest(cases=cases):
                baseline = report()
                baseline['cases'] = cases
                with self.assertRaises(ValueError):
                    compare(report(), baseline, .20, .15)

    def test_sampling_protocol_must_match(self):
        baseline = report()
        baseline['warmup'] = 0
        with self.assertRaisesRegex(ValueError, 'sampling protocols'):
            compare(report(), baseline, .20, .15)

    def test_fixture_identity_covers_nested_dependency_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            qc = root / 'small.qc'
            qc.write_text('$body body nested/mesh.smd\n')
            mesh = root / 'nested' / 'mesh.smd'
            mesh.parent.mkdir()
            mesh.write_text('first')
            before = fixture_identity(qc)
            mesh.write_text('second')
            after = fixture_identity(qc)
            self.assertEqual(before['small.qc'], after['small.qc'])
            self.assertNotEqual(before['nested/mesh.smd'], after['nested/mesh.smd'])


if __name__ == '__main__':
    unittest.main()
