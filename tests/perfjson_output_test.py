"""Actual compiler probes: report aliases must never truncate source or output."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER = Path(sys.argv.pop(1)).resolve()
SMD = '''version 1
nodes
0 "root" -1
end
skeleton
time 0
0 0 0 0 0 0 0
end
triangles
material
0 0 0 0 0 0 1 0 0
0 1 0 0 0 0 1 1 0
0 0 1 0 0 0 1 0 1
end
'''


class ReportProtection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='newpage-report-')
        self.root = Path(self.tmp.name)
        self.qc = self.root / 'fixture.qc'
        self.qc.write_text('$modelname fixture\n$include body.qci\n$sequence idle mesh.smd\n')
        (self.root / 'body.qci').write_text('$body body mesh.smd\n')
        (self.root / 'mesh.smd').write_text(SMD)
        (self.root / 'gameinfo.txt').write_text('GameInfo { FileSystem { SteamAppId 220 SearchPaths { Game "|gameinfo_path|." } } }')
        (self.root / 'cfg').mkdir()
        (self.root / 'cfg/commandline.cfg').write_text('commandline { fixture { studiomdl "-nodx80" } }')
        self.run_compiler()

    def tearDown(self):
        self.tmp.cleanup()

    def run_compiler(self, *args, success=True):
        result = subprocess.run([str(COMPILER), str(self.qc), '-game', str(self.root), *map(str, args)],
                                capture_output=True, text=True, errors='replace', timeout=90)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def originals(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*')
                if p.is_file() and not any(part.startswith('.newpage-') for part in p.parts)}

    def test_aliases_preserve_inputs_and_outputs(self):
        for name in ('fixture.qc', 'mesh.smd', 'body.qci', 'gameinfo.txt', 'cfg/commandline.cfg',
                     'models/fixture.mdl', 'models/fixture.vvd', 'models/fixture.dx90.vtx',
                     'models/fixture.vertexanim.json', 'models/fixture.phy'):
            with self.subTest(name=name):
                before = self.originals()
                text = self.run_compiler('-perfjson', self.root / name, success=False)
                self.assertIn('report output aliases', text)
                self.assertEqual(before, self.originals())

    def test_hardlink_alias(self):
        alias = self.root / 'report.json'
        try:
            os.link(self.qc, alias)
        except OSError as error:
            self.skipTest(str(error))
        before = self.originals()
        self.run_compiler('-perfjson', alias, success=False)
        self.assertEqual(before, self.originals())

    @unittest.skipUnless(os.name == 'nt', 'Windows path case semantics')
    def test_case_alias(self):
        before = self.originals()
        self.run_compiler('-perfjson', str(self.qc).upper(), success=False)
        self.assertEqual(before, self.originals())

    def test_failure_keeps_previous_report(self):
        report = self.root / 'perf.json'
        report.write_bytes(b'previous report')
        (self.root / 'mesh.smd').write_bytes(b'broken input')
        before = self.originals()
        self.run_compiler('-perfjson', report, success=False)
        self.assertEqual(before, self.originals())

    def test_normal_report_is_valid_and_complete(self):
        report = self.root / 'reports/perf.json'
        self.run_compiler('-perfjson', report)
        data = json.loads(report.read_text())
        self.assertGreaterEqual(data['total_ms'], data['compile_ms'])
        self.assertEqual(data['vertices'], 3)
        self.assertTrue(data['stages'])

    def test_dependency_report_includes_defaults_and_source_outputs(self):
        report = self.root / 'dependencies.json'
        text = self.run_compiler('-dependencyjson', report, '-diagnosticsjson')
        data = json.loads(report.read_text())
        self.assertTrue(data['cacheable'])
        paths = {Path(item['path']).name for item in data['dependencies']}
        self.assertTrue({'fixture.qc', 'mesh.smd', 'body.qci', 'gameinfo.txt', 'commandline.cfg'} <= paths)
        outputs = {Path(item['path']).name for item in data['outputs']}
        self.assertIn('fixture.mdl', outputs)
        self.assertIn('fixture.vvd', outputs)
        summary = json.loads(next(line.removeprefix('@diagnostic ') for line in text.splitlines() if line.startswith('@diagnostic ')))
        self.assertTrue(summary['success'])

    def test_dependency_report_alias_and_structured_failure(self):
        before = self.originals()
        text = self.run_compiler('-dependencyjson', self.qc, '-diagnosticsjson', success=False)
        self.assertEqual(before, self.originals())
        summary = json.loads(next(line.removeprefix('@diagnostic ') for line in text.splitlines() if line.startswith('@diagnostic ')))
        self.assertFalse(summary['success'])
        self.assertEqual(summary['diagnostics'][0]['code'], 'NP1402')
        report = self.root / 'same.json'
        self.run_compiler('-perfjson', report, '-dependencyjson', report, success=False)
        self.assertFalse(report.exists())

    def test_structured_location_identifies_include(self):
        include = self.root / 'body.qci'
        include.write_text('// first line\n$definitely_invalid\n')
        text = self.run_compiler('-diagnosticsjson', success=False)
        summary = json.loads(next(line.removeprefix('@diagnostic ') for line in text.splitlines() if line.startswith('@diagnostic ')))
        error = summary['diagnostics'][0]
        self.assertEqual(error['code'], 'NP1100')
        self.assertEqual(Path(error['source']).name, 'body.qci')
        self.assertEqual(error['line'], 2)


if __name__ == '__main__':
    unittest.main()
