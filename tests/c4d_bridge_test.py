"""Windows Cineware bridge contracts; no licensed SDK is needed to run these.

Usage: python tests/c4d_bridge_test.py path/to/NewPageMergeMDL.exe
The released C4D helper must be beside the compiler. The fixture is self-authored
by tools/c4d_bridge/fixture.cpp, rather than taken from Cineware's examples.
"""
from pathlib import Path
import json
import math
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
MATERIAL_FIXTURE = Path(__file__).parent / 'fixtures/cineware-materials.c4d'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/c4d_bridge'))
from compare_application import compare as compare_application


def read_glb(path):
    data = path.read_bytes()
    if data[:4] != b'glTF': raise ValueError('not a GLB')
    offset, doc, binary = 12, None, None
    while offset < len(data):
        size, kind = struct.unpack_from('<2I', data, offset)
        value = data[offset+8:offset+8+size]
        if kind == 0x4e4f534a: doc = json.loads(value)
        elif kind == 0x004e4942: binary = value
        offset += size+8
    def accessor(index):
        item = doc['accessors'][index]
        view = doc['bufferViews'][item['bufferView']]
        count = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[item['type']]
        fmt = '<' + str(count) + {5121: 'B', 5123: 'H', 5125: 'I', 5126: 'f'}[item['componentType']]
        start = view.get('byteOffset', 0)+item.get('byteOffset', 0)
        stride = view.get('byteStride', struct.calcsize(fmt))
        return [struct.unpack_from(fmt, binary, start+i*stride) for i in range(item['count'])]
    return doc, accessor


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

    def test_cinema4d_2027_saved_caches_match_application_geometry(self):
        source = FIXTURE.parent / 'cineware-app-cache-2027.c4d'
        reference = FIXTURE.parent / 'cineware-app-cache-2027-reference.json'
        output = self.root / 'application-caches.glb'
        self.run_process([HELPER, source.resolve(), output])
        comparison = compare_application(reference, output)
        self.assertTrue(comparison['success'])
        self.assertEqual(comparison['source_hierarchy_nodes_checked'], 4)
        self.assertEqual(sum(mesh['triangles'] for mesh in comparison['meshes']), 224)
        # The generating script authors this diffuse color; the independent
        # application JSON supplies the mesh, corner and transform references.
        doc, _ = read_glb(output)
        self.assertEqual(len(doc['materials']), 1)
        for actual, expected in zip(doc['materials'][0]['pbrMetallicRoughness']['baseColorFactor'], (.2, .4, .8, 1)):
            self.assertAlmostEqual(actual, expected, places=6)

    def test_cinema4d_2027_animated_skin_is_explicitly_rejected(self):
        source = FIXTURE.parent / 'cineware-app-animated-skin-2027.c4d'
        output = self.root / 'application-skin.glb'
        text = self.run_process([HELPER, source.resolve(), output], success=False)
        self.assertIn('animated C4D object is not supported', text)
        self.assertFalse(output.exists())
        self.compile()
        original = self.outputs()
        self.compile(source=source.resolve(), success=False)
        self.assertEqual(self.outputs(), original)

    def test_missing_cache_animation_skin_and_corrupt_geometry_fail_without_output(self):
        expected = {
            'missing-cache': 'missing saved polygon cache or unsupported C4D object/plugin',
            'invalid-index': 'polygon point index out of range',
            'short-uv': 'UV tag count does not match polygon count',
            'skin': 'skin weights are not supported',
            'animated': 'animated C4D object is not supported',
        }
        self.compile()
        original = self.outputs()
        for mode, diagnostic in expected.items():
            with self.subTest(mode=mode):
                source = FIXTURE.parent / ('cineware-reject-' + mode + '.c4d')
                output = self.root / (mode + '.glb')
                text = self.run_process([HELPER, source.resolve(), output], success=False)
                self.assertIn(diagnostic, text)
                self.assertFalse(output.exists())
                text = self.compile(source=source.resolve(), success=False)
                self.assertIn('C4D conversion failed', text)
                self.assertEqual(self.outputs(), original)

    def material_scene(self):
        output = self.root / 'materials.glb'
        self.run_process([HELPER, MATERIAL_FIXTURE.resolve(), output])
        return read_glb(output)

    def test_polygon_selections_and_texture_tag_order_preserve_face_materials(self):
        doc, values = self.material_scene()
        expected = {
            'SmoothStrip': ['FixtureBlue', 'FixtureRed', 'FixtureGreen', 'FixtureBlue'],
            'AuthoredStrip': ['FixtureBlue', 'FixtureRed', 'FixtureGreen', 'FixtureBlue'],
            'RestrictedOnly': ['DefaultMaterial', 'FixtureRed', 'FixtureGreen', 'DefaultMaterial'],
            'LastUnrestricted': ['FixtureBlue']*4,
        }
        parent = next(n for n in doc['nodes'] if n['name'] == 'MaterialParent')
        self.assertEqual(parent['matrix'][12:15], [200, 300, 400])
        self.assertEqual({doc['nodes'][n]['name'] for n in parent['children']}, set(expected))
        for name, assignment in expected.items():
            with self.subTest(node=name):
                node = next(n for n in doc['nodes'] if n['name'] == name)
                if name != 'SmoothStrip':
                    self.assertEqual(node['matrix'][13], list(expected).index(name)*200)
                polygons = [0]*4
                for primitive in doc['meshes'][node['mesh']]['primitives']:
                    material = doc['materials'][primitive['material']]['name']
                    positions = values(primitive['attributes']['POSITION'])
                    indices = [i[0] for i in values(primitive['indices'])]
                    self.assertEqual(len(indices) % 3, 0)
                    for i in range(0, len(indices), 3):
                        center = sum(positions[j][0] for j in indices[i:i+3])/3
                        polygon = int(center // 100)
                        polygons[polygon] += 1
                        self.assertEqual(material, assignment[polygon])
                self.assertEqual(polygons, [2]*4)

    def test_material_splits_preserve_uv_authored_normals_and_smoothing(self):
        doc, values = self.material_scene()
        smooth_boundary = []
        expected_smooth = (-.18910752, 0, .98195639)
        for name in ('SmoothStrip', 'AuthoredStrip'):
            node = next(n for n in doc['nodes'] if n['name'] == name)
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                attributes = primitive['attributes']
                for position, normal, uv in zip(values(attributes['POSITION']), values(attributes['NORMAL']), values(attributes['TEXCOORD_0'])):
                    self.assertAlmostEqual(uv[0], position[0]/400, places=6)
                    self.assertAlmostEqual(uv[1], position[1]/100, places=6)
                    self.assertAlmostEqual(math.sqrt(sum(x*x for x in normal)), 1, places=5)
                    if name == 'AuthoredStrip':
                        for a, b in zip(normal, (0, .6, .8)): self.assertAlmostEqual(a, b, places=4)
                    elif position[0] in (100, 200):
                        smooth_boundary.append(normal)
                        for a, b in zip(normal, expected_smooth): self.assertAlmostEqual(a, b, places=5)
        self.assertEqual(len(smooth_boundary), 8) # each side of both material boundaries

    def test_multimaterial_binary_c4d_compiles_with_geometry_and_materials(self):
        self.compile(source=MATERIAL_FIXTURE.resolve(), selection='InNode SmoothStrip')
        mdl = (self.root/'models/c4d.mdl').read_bytes()
        count, offset = struct.unpack_from('<2i', mdl, 204)
        names = []
        for i in range(count):
            start = offset+i*64
            name = start+struct.unpack_from('<i', mdl, start)[0]
            names.append(mdl[name:mdl.index(b'\0', name)].decode())
        self.assertEqual(set(names), {'FixtureBlue', 'FixtureRed', 'FixtureGreen'})
        vvd = (self.root/'models/c4d.vvd').read_bytes()
        count = struct.unpack_from('<i', vvd, 16)[0]
        offset = struct.unpack_from('<i', vvd, 56)[0]
        vertices = [struct.unpack_from('<8f', vvd, offset+i*48+16) for i in range(count)]
        expected = {(2+x, 4+(.4 if x>=2 else 0), 3+y) for x in range(5) for y in range(2)}
        self.assertEqual({tuple(round(v, 4) for v in p[:3]) for p in vertices}, expected)
        for p in vertices:
            self.assertAlmostEqual(p[6], (p[0]-2)/4, places=5)
            self.assertAlmostEqual(p[7], p[2]-3, places=5)
            if round(p[0], 5) in (3, 4):
                for a, b in zip(p[3:6], (-.18910752, .98195639, 0)): self.assertAlmostEqual(a, b, places=5)


if __name__ == '__main__':
    unittest.main()
