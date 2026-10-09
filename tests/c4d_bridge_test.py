"""Windows Cineware bridge contracts; no licensed SDK is needed to run these.

Usage: python tests/c4d_bridge_test.py path/to/NewPageMergeMDL.exe
The released C4D helper must be beside the compiler. The fixture is self-authored
by tools/c4d_bridge/fixture.cpp, rather than taken from Cineware's examples.
"""
from pathlib import Path
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

COMPILER = Path(sys.argv.pop(1)).resolve()
HELPER = COMPILER.with_name('NewPageMergeMDL-C4D.exe')
FIXTURE = Path(__file__).parent / 'fixtures/cineware-static.c4d'


@unittest.skipUnless(os.name == 'nt', 'Cineware 22 bridge uses the Windows MSVC ABI')
class C4dBridge(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.is_file(), 'Install the released C4D helper beside the compiler')
        self.temp = tempfile.TemporaryDirectory(prefix='c4d-contract-')
        self.root = Path(self.temp.name)
        self.source = self.root / 'scene.c4d'
        shutil.copyfile(FIXTURE, self.source)

    def tearDown(self):
        self.temp.cleanup()

    def run_process(self, args, success=True, **kwargs):
        result = subprocess.run(list(map(str, args)), capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=30, **kwargs)
        text = result.stdout + result.stderr
        self.assertEqual(result.returncode == 0, success, text)
        return text

    def compile(self, source=None, selection='', compiler=COMPILER, **kwargs):
        qc = self.root / 'scene.qc'
        qc.write_text('$modelname c4d\n$body body "' + (source or self.source).as_posix()
                      + '" ' + selection + '\n', encoding='utf-8')
        return self.run_process([compiler, qc, '-game', self.root, '-dumpdependencies'], **kwargs)

    def outputs(self):
        return {p.name: p.read_bytes() for p in (self.root / 'models').glob('c4d.*')}

    def test_static_model_preserves_transformed_geometry_normals_uv_material(self):
        self.compile()
        vvd = (self.root / 'models/c4d.vvd').read_bytes()
        count = struct.unpack_from('<i', vvd, 16)[0]
        offset = struct.unpack_from('<i', vvd, 56)[0]
        self.assertEqual(count, 4)
        vertices = [struct.unpack_from('<8f', vvd, offset + 48 * i + 16) for i in range(count)]
        actual = {tuple(round(x, 5) for x in v[:3]) for v in vertices}
        # C4D centimeters and left handedness become meters/right handedness;
        # the compiler then rotates the Y-up imported scene into Source Z-up.
        self.assertEqual(actual, {(2., 4., 3.), (3., 4., 3.), (3., 4., 4.), (2., 4., 4.)})
        for vertex in vertices:
            for actual, expected in zip(vertex[3:6], (0., 1., 0.)):
                self.assertAlmostEqual(actual, expected, places=5)
            self.assertAlmostEqual(vertex[6], vertex[0] - 2, places=5)
            self.assertAlmostEqual(vertex[7], vertex[2] - 3, places=5)
        mdl = (self.root / 'models/c4d.mdl').read_bytes()
        count, offset = struct.unpack_from('<2i', mdl, 204)
        self.assertEqual(count, 1)
        name = offset + struct.unpack_from('<i', mdl, offset)[0]
        self.assertEqual(mdl[name:mdl.index(b'\0', name)], b'FixtureBlue')

    def test_helper_preserves_material_color_and_node_hierarchy(self):
        output = self.root / 'scene.glb'
        self.run_process([HELPER, self.source, output])
        data = output.read_bytes()
        self.assertEqual(data[:4], b'glTF')
        size, kind = struct.unpack_from('<2I', data, 12)
        self.assertEqual(kind, 0x4e4f534a)
        doc = json.loads(data[20:20 + size])
        material = doc['materials'][0]
        self.assertEqual(material['name'], 'FixtureBlue')
        for actual, expected in zip(material['pbrMetallicRoughness']['baseColorFactor'], (.2, .4, .8, 1)):
            self.assertAlmostEqual(actual, expected, places=6)
        parent = next(node for node in doc['nodes'] if node['name'] == 'FixtureParent')
        child = doc['nodes'][parent['children'][0]]
        self.assertEqual(child['name'], 'FixtureQuad')
        self.assertIn('mesh', child)
        self.assertNotIn('animations', doc)

    def test_dependencies_and_temp_cleanup_use_original_c4d(self):
        temp_root = self.root / 'private temp'; temp_root.mkdir()
        unrelated = temp_root / 'newpage-c4d-unrelated'; unrelated.mkdir()
        marker = unrelated / 'keep.txt'; marker.write_text('unrelated')
        env = os.environ.copy(); env['TEMP'] = env['TMP'] = str(temp_root)
        text = self.compile(env=env)
        sources = [line for line in text.splitlines() if line.startswith('@dep source ')]
        self.assertEqual(len(sources), 1, text)
        self.assertEqual(Path(sources[0].split(' ', 3)[3]), self.source)
        self.assertNotIn('.glb', '\n'.join(line for line in text.splitlines() if line.startswith('@dep ')))
        self.assertEqual(set(temp_root.iterdir()), {unrelated})
        self.assertEqual(marker.read_text(), 'unrelated')

    def test_innode_selects_child_and_rejects_missing_node(self):
        self.compile(selection='InNode FixtureQuad')
        old = self.outputs()
        text = self.compile(selection='InNode Missing', success=False)
        self.assertIn('InNode not found', text)
        self.assertEqual(self.outputs(), old)

    def test_invalid_documents_preserve_previous_model(self):
        self.compile(); old = self.outputs()
        for data in (b'', b'not a Cinema 4D document', FIXTURE.read_bytes()[:32]):
            with self.subTest(size=len(data)):
                self.source.write_bytes(data)
                text = self.compile(success=False)
                self.assertIn('C4D conversion failed', text)
                self.assertEqual(self.outputs(), old)

    def test_unicode_spaces_in_executable_source_and_output_paths(self):
        directory = self.root / '\u4e2d\u6587 tools'; directory.mkdir()
        compiler = directory / COMPILER.name
        shutil.copyfile(COMPILER, compiler); shutil.copyfile(HELPER, directory / HELPER.name)
        source = directory / '\u6a21\u578b with spaces.c4d'; shutil.copyfile(FIXTURE, source)
        self.compile(source=source, compiler=compiler)
        output = directory / '\u8f93\u51fa with spaces.glb'
        self.run_process([directory / HELPER.name, source, output])
        self.assertTrue(output.is_file())

    def test_helper_refuses_existing_output(self):
        output = self.root / 'keep.glb'; output.write_bytes(b'previous scene')
        text = self.run_process([HELPER, self.source, output], success=False)
        self.assertIn('Refusing to overwrite', text)
        self.assertEqual(output.read_bytes(), b'previous scene')


if __name__ == '__main__':
    unittest.main()
