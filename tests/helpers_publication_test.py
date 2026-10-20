"""Authoring helpers preserve complete previous outputs on publication failure."""
import argparse
import ctypes
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument('--bin-dir', type=Path, required=True)
parser.add_argument('--tools-dir', type=Path)
args, rest = parser.parse_known_args()
sys.argv = [sys.argv[0], *rest]
BIN = args.bin_dir.resolve()
TOOLS = (args.tools_dir or BIN / 'tools').resolve()
sys.path.insert(0, str(TOOLS))
import mesh_states
import vrm_runtime
import output_transaction
from integration_vrm_cases import IntegrationVrmCases

SUFFIX = '.exe' if os.name == 'nt' else ''
COMPILER = BIN / ('NewPageMergeMDL' + SUFFIX)
MESH = ('version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n'
        '0 0 0 0 0 0 0\nend\ntriangles\nmaterial\n'
        '0 0 0 0 0 0 1 0 0\n0 1 0 0 0 0 1 1 0\n0 0 1 0 0 0 1 0 1\nend\n')


class HelperPublication(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='helper-publication-')
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for name in ('out', 'game') for p in (self.root / name).rglob('*') if p.is_file()}

    def blocked_publication(self, target, call):
        old = self.snapshot()
        replace = os.replace
        failed = []

        def inject(source, destination):
            if Path(destination) == target and '.newpage-helper-new-' in str(source) and not failed:
                failed.append(True)
                raise PermissionError('injected runtime JSON publication failure')
            return replace(source, destination)

        with patch.object(output_transaction.os, 'replace', side_effect=inject):
            self.assertEqual(call(), 2)
        self.assertTrue(failed, 'failure must occur during publication, after actual compilation')
        self.assertEqual(self.snapshot(), old, 'all old generated inputs/model/JSON must survive')

    def test_mesh_state_publication_failure_restores_model_and_json(self):
        (self.root / 'mesh.smd').write_text(MESH)
        source = self.root / 'states.json'
        spec = dict(modelname='audit/states', states=[dict(name='one', source='mesh.smd')], fps=1)
        source.write_text(json.dumps(spec))
        argv = [str(source), '--out', str(self.root/'out'), '--compiler', str(COMPILER), '--game', str(self.root/'game')]
        self.assertEqual(mesh_states.main(argv), 0)
        spec['states'].append(dict(name='hidden', blank=True)); source.write_text(json.dumps(spec))
        self.blocked_publication(self.root/'game/models/audit/states.meshstates.json', lambda: mesh_states.main(argv))
        self.assertEqual(mesh_states.main(argv), 0)
        self.assertEqual(len(json.loads((self.root/'game/models/audit/states.meshstates.json').read_text())['states']), 2)

    def test_vrm_publication_failure_restores_generated_sources_and_model(self):
        source = self.root/'input.gltf'
        doc = IntegrationVrmCases().vrm_fixture(); source.write_text(json.dumps(doc))
        argv = [str(source), '--out', str(self.root/'out'), '--compiler', str(COMPILER), '--game', str(self.root/'game'), '--scale', '1']
        self.assertEqual(vrm_runtime.main(argv), 0)
        del doc['extensions']['VRMC_vrm']['expressions']['preset']['blink']; source.write_text(json.dumps(doc))
        self.blocked_publication(self.root/'game/models/vrm/avatar.vrm.json', lambda: vrm_runtime.main(argv))
        self.assertEqual(vrm_runtime.main(argv), 0)
        self.assertNotIn('blink', json.loads((self.root/'game/models/vrm/avatar.vrm.json').read_text())['expressions'])

    def test_vrm_input_aliases_are_rejected_without_writing(self):
        original = json.dumps(IntegrationVrmCases().vrm_fixture())
        source = self.root/'avatar.gltf'; source.write_text(original)
        self.assertEqual(vrm_runtime.main([str(source), '--out', str(self.root)]), 2)
        self.assertEqual(source.read_text(), original)
        self.assertFalse((self.root/'avatar.qc').exists())
        linked = self.root/'input.gltf'; os.link(source, linked)
        self.assertEqual(vrm_runtime.main([str(linked), '--out', str(self.root)]), 2)
        self.assertEqual(source.read_text(), original)

    def test_vrml_failed_compile_preserves_converted_output_and_no_qc(self):
        source = self.root/'triangle.wrl'
        source.write_text('#VRML V2.0 utf8\nShape { geometry IndexedFaceSet { coord Coordinate { point [0 0 0,1 0 0,0 1 0] } coordIndex [0 1 2 -1] } }')
        target = self.root/'scene.x3d'; target.write_bytes(b'previous scene')
        result = subprocess.run([sys.executable, str(TOOLS/'vrml_import.py'), str(source), '--output', str(target),
                                 '--converter', str(BIN/('NewPageVRMLtoX3D'+SUFFIX)), '--compiler', str(self.root/'missing-compiler'),
                                 '--game', str(self.root/'game')], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_bytes(), b'previous scene')
        self.assertFalse(target.with_suffix('.qc').exists())

    def test_external_change_and_concurrent_writer_are_rejected(self):
        target = self.root/'model.json'; target.write_bytes(b'old')
        with output_transaction.Publication() as first:
            source = first.work/'new'; source.write_bytes(b'new'); first.add(source, target)
            with output_transaction.Publication() as second:
                with self.assertRaisesRegex(ValueError, 'another helper'):
                    second.reserve(target)
            target.write_bytes(b'external edit')
            with self.assertRaisesRegex(ValueError, 'changed during generation'):
                first.commit()
        self.assertEqual(target.read_bytes(), b'external edit')

    def test_input_alias_protection_applies_to_every_reserved_output(self):
        source = self.root/'source.bin'; source.write_bytes(b'original')
        target = self.root/'model.vvd'; os.link(source, target)
        with output_transaction.Publication([source]) as publication:
            with self.assertRaisesRegex(ValueError, 'input and generated output'):
                publication.reserve(target)
        self.assertEqual(source.read_bytes(), b'original')

    def test_sync_failure_happens_before_old_outputs_change(self):
        target = self.root/'model.json'; target.write_bytes(b'old')
        with output_transaction.Publication() as publication:
            source = publication.work/'new'; source.write_bytes(b'new'); publication.add(source, target)
            with patch.object(output_transaction.os, 'fsync', side_effect=OSError('injected flush failure')):
                with self.assertRaisesRegex(OSError, 'injected flush failure'):
                    publication.commit()
        self.assertEqual(target.read_bytes(), b'old')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['model.json'])

    def test_cleanup_failure_after_commit_keeps_success_and_new_outputs(self):
        target = self.root/'model.json'; target.write_bytes(b'old')
        unlink = Path.unlink
        def fail_old(path, *args, **kwargs):
            if path.name.startswith('.newpage-helper-old-'):
                raise PermissionError('injected backup cleanup failure')
            return unlink(path, *args, **kwargs)
        with output_transaction.Publication() as publication:
            source = publication.work/'new'; source.write_bytes(b'new'); publication.add(source, target)
            with patch.object(Path, 'unlink', fail_old):
                publication.commit()
        self.assertEqual(target.read_bytes(), b'new')
        backups = list(self.root.glob('.newpage-helper-old-*'))
        self.assertEqual(len(backups), 1); self.assertEqual(backups[0].read_bytes(), b'old')

    def test_failed_rollback_keeps_old_bytes_and_recovery_mapping(self):
        target = self.root/'model.json'; target.write_bytes(b'old')
        replace = os.replace
        def inject(source, destination):
            if Path(source).name.startswith(('.newpage-helper-new-', '.newpage-helper-old-')):
                raise PermissionError('injected publication and rollback failure')
            return replace(source, destination)
        publication = output_transaction.Publication()
        try:
            with self.assertRaisesRegex(OSError, 'rollback needs attention'):
                with publication:
                    source = publication.work/'new'; source.write_bytes(b'new'); publication.add(source, target)
                    with patch.object(output_transaction.os, 'replace', side_effect=inject):
                        publication.commit()
            recovery = json.loads((publication.work/'recovery.json').read_text())
            self.assertEqual(recovery[0]['destination'], str(target))
            self.assertEqual(Path(recovery[0]['backup']).read_bytes(), b'old')
            self.assertEqual(Path(recovery[0]['staged']).read_bytes(), b'new')
        finally:
            shutil.rmtree(publication.work)


if __name__ == '__main__':
    unittest.main()
