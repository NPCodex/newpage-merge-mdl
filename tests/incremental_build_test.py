"""Exercise cache decisions against the actual compiler and real dependencies."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument('--compiler', required=True, type=Path)
parser.add_argument('--tools-dir', type=Path)
args, rest = parser.parse_known_args(); sys.argv = [sys.argv[0], *rest]
COMPILER = args.compiler.resolve()
TOOLS = (args.tools_dir or Path(__file__).resolve().parents[1]/'tools').resolve()
sys.path.insert(0, str(TOOLS))
import incremental_build

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


class IncrementalBuild(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='incremental-models-')
        self.root = Path(self.temporary.name).resolve()
        (self.root/'game').mkdir()
        (self.root/'game/gameinfo.txt').write_text('GameInfo { FileSystem { SteamAppId 220 SearchPaths { Game "|gameinfo_path|." } } }')
        self.jobs = []
        for name in ('a', 'b'):
            folder = self.root/'sources'/name; folder.mkdir(parents=True)
            (folder/'mesh.smd').write_text(SMD)
            (folder/'body.qci').write_text('$body body mesh.smd\n')
            (folder/'model.qc').write_text('$modelname fixture\n$include body.qci\n$sequence idle mesh.smd\n')
            self.jobs.append(dict(id=name, qc=f'sources/{name}/model.qc', game='game', output=f'build/{name}',
                                  watch_roots=['sources', 'game'], complete_search_roots=True))
        self.plan = self.root/'plan.json'; self.write_plan()
        self.cache = self.root/'.newpage-batch'; self.report = self.cache/'batch-report.json'

    def tearDown(self): self.temporary.cleanup()
    def write_plan(self): self.plan.write_text(json.dumps(dict(schema=1, jobs=self.jobs)))
    def run_batch(self, expected=0, *extra):
        result = incremental_build.main([str(self.plan), '--compiler', str(COMPILER), *extra])
        report = json.loads(self.report.read_text()) if self.report.is_file() else {}
        self.assertEqual(result, expected, json.dumps(report, indent=2))
        return report
    def statuses(self, report): return [row['status'] for row in report['jobs']]
    def assert_cached(self, report):
        self.assertTrue(all(row['cacheable'] for row in report['jobs']), json.dumps(report, indent=2))

    def test_cold_unchanged_and_content_change_only_rebuild_dependent_job(self):
        report = self.run_batch(); self.assertEqual(self.statuses(report), ['built', 'built']); self.assert_cached(report)
        self.assertEqual(self.statuses(self.run_batch()), ['skipped', 'skipped'])
        path = self.root/'sources/a/mesh.smd'; path.write_text(SMD.replace('0 1 0 0 0 0 1 1 0', '0 2 0 0 0 0 1 1 0'))
        self.assertEqual(self.statuses(self.run_batch()), ['built', 'skipped'])
        self.assertEqual(self.statuses(self.run_batch()), ['skipped', 'skipped'])

    def test_new_search_entry_invalidates_declared_shared_search_roots(self):
        self.assert_cached(self.run_batch())
        (self.root/'sources/new-higher-priority.smd').write_text(SMD)
        report = self.run_batch(); self.assertEqual(self.statuses(report), ['built', 'built'])
        self.assertTrue(all('entries changed' in row['reason'] for row in report['jobs']))
        self.assertEqual(self.statuses(self.run_batch()), ['skipped', 'skipped'])

    def test_missing_or_tampered_outputs_force_rebuild(self):
        self.assert_cached(self.run_batch())
        (self.root/'build/a/models/fixture.vvd').unlink()
        self.assertEqual(self.statuses(self.run_batch()), ['built', 'skipped'])
        model = self.root/'build/b/models/fixture.mdl'; model.write_bytes(model.read_bytes()+b'corruption')
        self.assertEqual(self.statuses(self.run_batch()), ['skipped', 'built'])

    def test_undeclared_or_incomplete_search_coverage_compiles_but_never_skips(self):
        self.jobs[0].pop('complete_search_roots'); self.jobs[1]['watch_roots'] = ['sources']; self.write_plan()
        for _ in range(2):
            report = self.run_batch(); self.assertEqual(self.statuses(report), ['built', 'built'])
            self.assertFalse(any(row['cacheable'] for row in report['jobs']))
            self.assertIn('complete_search_roots', ' '.join(report['jobs'][0]['uncacheable_reasons']))
            self.assertIn('outside watched', ' '.join(report['jobs'][1]['uncacheable_reasons']))

    def test_partial_failure_preserves_existing_model_and_reports_native_error(self):
        self.assert_cached(self.run_batch())
        old = (self.root/'build/a/models/fixture.mdl').read_bytes()
        (self.root/'sources/a/mesh.smd').write_text('corrupted SMD')
        path = self.root/'sources/b/mesh.smd'; path.write_text(SMD.replace('0 1 0 0 0 0 1 1 0', '0 3 0 0 0 0 1 1 0'))
        report = self.run_batch(2); self.assertEqual(self.statuses(report), ['failed', 'built'])
        self.assertEqual((self.root/'build/a/models/fixture.mdl').read_bytes(), old)
        codes = [entry['code'] for native in report['jobs'][0]['diagnostics'] for entry in native.get('diagnostics', [])]
        self.assertTrue(codes, report); self.assertTrue(all(code.startswith('NP') for code in codes))
        self.assertIn('stderr_tail', report['jobs'][0])

    def test_settings_and_helper_identity_invalidate(self):
        extra = self.root/'helper.bin'; extra.write_bytes(b'version one')
        self.jobs[0]['toolchain_files'] = ['helper.bin']; self.write_plan()
        self.assert_cached(self.run_batch())
        extra.write_bytes(b'version two')
        self.assertEqual(self.statuses(self.run_batch()), ['built', 'skipped'])
        self.jobs[1]['args'] = ['-nodx80']; self.write_plan()
        self.assertEqual(self.statuses(self.run_batch()), ['skipped', 'built'])

    def test_external_gltf_buffer_is_tracked_and_only_its_job_rebuilds(self):
        source = self.root/'sources/a'
        blob = b''.join(struct.pack('<3f', *p) for p in ((0,0,0),(1,0,0),(0,1,0)))
        (source/'geometry.bin').write_bytes(blob)
        doc = dict(asset={'version':'2.0'}, buffers=[dict(uri='geometry.bin', byteLength=len(blob))],
                   bufferViews=[dict(buffer=0, byteLength=len(blob))],
                   accessors=[dict(bufferView=0, componentType=5126, count=3, type='VEC3')],
                   meshes=[dict(primitives=[dict(attributes={'POSITION':0})])],
                   nodes=[dict(mesh=0, name='mesh')], scenes=[dict(nodes=[0])], scene=0)
        (source/'mesh.gltf').write_text(json.dumps(doc))
        (source/'body.qci').write_text('$body body mesh.gltf\n')
        self.assert_cached(self.run_batch())
        self.assertEqual(self.statuses(self.run_batch()), ['skipped', 'skipped'])
        changed = bytearray(blob); struct.pack_into('<f', changed, 12, 2.0); (source/'geometry.bin').write_bytes(changed)
        self.assertEqual(self.statuses(self.run_batch()), ['built', 'skipped'])

    def test_overlapping_outputs_and_input_report_are_rejected_before_compile(self):
        self.jobs[1]['output'] = 'build/a/nested'; self.write_plan()
        self.assertEqual(incremental_build.main([str(self.plan), '--compiler', str(COMPILER)]), 2)
        self.assertFalse((self.root/'build').exists())
        self.jobs[1]['output'] = 'build/b'; self.write_plan()
        before = self.plan.read_bytes()
        self.assertEqual(incremental_build.main([str(self.plan), '--compiler', str(COMPILER), '--report', str(self.plan)]), 2)
        self.assertEqual(self.plan.read_bytes(), before)

    def test_parallel_compilers_overlap_preserve_order_and_reuse_outputs(self):
        original = incremental_build.build_job
        rendezvous = threading.Barrier(2)
        def overlap(*values):
            rendezvous.wait(timeout=15)
            return original(*values)
        with patch.object(incremental_build, 'build_job', side_effect=overlap):
            report = self.run_batch(0, '--jobs', '2')
        self.assertEqual([r['id'] for r in report['jobs']], ['a', 'b'])
        self.assertEqual(self.statuses(report), ['built', 'built'])
        self.assert_cached(report)
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in (self.root/'build').rglob('*') if p.is_file()}
        self.assertEqual(self.statuses(self.run_batch(0, '--jobs', '2')), ['skipped', 'skipped'])
        self.run_batch(0, '--jobs', '1', '--force')
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in (self.root/'build').rglob('*') if p.is_file()})

    def test_parallel_failure_keeps_previous_model_and_other_job_completes(self):
        self.run_batch()
        model = self.root/'build/a/models/fixture.mdl'; before = model.read_bytes()
        (self.root/'sources/a/mesh.smd').write_text('broken input')
        report = self.run_batch(2, '--jobs', '2', '--force')
        self.assertEqual(self.statuses(report), ['failed', 'built'])
        self.assertEqual(model.read_bytes(), before)

    def test_parallel_budget_serializes_and_invalid_budgets_fail_before_output(self):
        original = incremental_build.build_job
        active = 0; peak = 0; lock = threading.Lock()
        def counted(*values):
            nonlocal active, peak
            with lock:
                active += 1; peak = max(active, peak)
            try: return original(*values)
            finally:
                with lock: active -= 1
        with patch.object(incremental_build, 'build_job', side_effect=counted):
            report = self.run_batch(0, '--jobs', '2', '--memory-budget-mib', '512', '--job-memory-mib', '512')
        self.assertEqual(peak, 1)
        self.assertEqual(report['scheduling']['effective_jobs'], 1)
        self.assertFalse(report['scheduling']['memory_limit_enforced'])
        before = self.report.read_bytes()
        for options in (['--jobs', '0'], ['--jobs', '65'], ['--job-memory-mib', '0'], ['--memory-budget-mib', '511']):
            with self.subTest(options=options):
                self.assertEqual(incremental_build.main([str(self.plan), '--compiler', str(COMPILER), *options]), 2)
                self.assertEqual(self.report.read_bytes(), before)

    def test_parallel_requires_independent_declared_input_roots(self):
        self.jobs[0]['complete_search_roots'] = False; self.write_plan()
        self.assertEqual(incremental_build.main([str(self.plan), '--compiler', str(COMPILER), '--jobs', '2']), 2)
        self.assertFalse((self.root/'build').exists())
        self.jobs[0]['complete_search_roots'] = True
        self.jobs[0]['watch_roots'].append('build/b'); self.write_plan()
        self.assertEqual(incremental_build.main([str(self.plan), '--compiler', str(COMPILER), '--jobs', '2']), 2)
        self.assertFalse((self.root/'build').exists())

    def test_parallel_rejects_link_into_other_job_output_before_compilation(self):
        target = self.root/'build/b'; target.mkdir(parents=True)
        sentinel = target/'existing.txt'; sentinel.write_text('preserve previous output')
        link = self.root/'sources/a/generated'
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != 'nt': raise
            # Directory junctions need no elevated privileges. Exercise the
            # same race when Windows policy disallows unprivileged symlinks.
            made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
            self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
        try:
            with patch.object(incremental_build, 'build_job') as worker:
                self.assertEqual(incremental_build.main([str(self.plan), '--compiler', str(COMPILER), '--jobs', '2']), 2)
                worker.assert_not_called()
            self.assertFalse(self.cache.exists())
            self.assertFalse((self.root/'build/a').exists())
            self.assertEqual(sentinel.read_text(), 'preserve previous output')
        finally:
            if link.is_symlink(): link.unlink()
            else: link.rmdir()


if __name__ == '__main__': unittest.main()
