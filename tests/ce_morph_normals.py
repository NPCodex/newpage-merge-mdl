"""Combined DMX normal regressions; inputs are self-authored, outputs inspected.

Usage: python tests/ce_morph_normals.py <NewPageMergeMDL.exe>
Optional --reference <cestudiomdl.exe> refreshes the bounded reference snapshot.
No reference executable, game assets, or generated MDL is kept in the repository.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re
import struct
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / 'fixtures/ce-combined-normals.json'
OPTIONS = None


def field(name, kind, values):
    text = ', '.join('"' + (' '.join(f'{v:.9g}' for v in x) if isinstance(x, (list, tuple)) else str(x)) + '"' for x in values)
    return f'"{name}" "{kind}_array" [ {text} ]\n'


def replace_array(text, name, kind, values):
    return re.sub(r'"' + re.escape(name) + r'" "' + kind + r'_array"\s*\[.*?\]',
                  lambda _: field(name, kind, values).strip(), text, count=1, flags=re.S)


def guid(n):
    return f'a100bebc-a100-bebc-00be-{n:012x}'


def block(kind, n, name, body):
    return f'"{kind}"\n{{\n"id" "elementid" "{guid(n)}"\n"name" "string" "{name}"\n{body}\n}}\n'


def unit(v):
    length = math.sqrt(sum(x*x for x in v))
    return [x / length for x in v]


def make_fixture(case):
    text = (HERE / 'fixtures/ce-facial.dmx').read_text().split('"DmeVertexDeltaData"')[0]
    seam = case in ('seam_subsets', 'authored_seam')
    positions = [[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]]
    if case == 'unequal_faces':
        positions = [[0, 0, 0], [4, 0, 0], [2, 2, .4], [0, 1, 0]]
    corners = [0, 1, 2, 0, 2, 3]
    normals = [[0, 0, 1]]*4 if not seam else [[0, 0, 1]]*3 + [[.6, 0, .8]]*3
    uv = [[0, 0], [1, 0], [1, 1], [0, 1]] if not seam else [[0, 0], [1, 0], [1, 1], [.1, .1], [.9, .9], [.1, .9]]
    ni = corners if not seam else list(range(6))
    for name, kind, values in [('positions', 'vector3', positions), ('positionsIndices', 'int', corners),
                               ('normals', 'vector3', normals), ('normalsIndices', 'int', ni),
                               ('textureCoordinates', 'vector2', uv), ('textureCoordinatesIndices', 'int', ni),
                               ('jointWeights', 'float', [1]*4), ('jointIndices', 'int', [0]*4),
                               ('faces', 'int', [0, 1, 2, -1, 3, 4, 5, -1])]:
        text = replace_array(text, name, kind, values)
    deltas = {
        'A': [[0, 0, .2], [0, 0, .07], [0, 0, 0], [0, 0, 0]],
        'B': [[.11, -.04, .13], [0, 0, 0], [0, 0, .18], [0, 0, 0]],
        'C': [[-.06, .08, -.09], [0, 0, 0], [0, 0, 0], [0, 0, .23]],
        'A_B_C': [[0, 0, 0]]*4,
    }
    if case in ('unordered_subsets', 'seam_subsets'):
        deltas = {'C_B_A': [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, .08]],
                  'A_B': [[0, 0, .08], [0, 0, 0], [0, 0, 0], [.04, 0, .025]],
                  'B_C': [[0, -.06, 0], [0, 0, 0], [0, 0, -.04], [0, 0, 0]],
                  'C': deltas['C'], 'B': deltas['B'], 'A': deltas['A']}
    elif case == 'zero_independent':
        deltas['D'] = deltas.pop('A_B_C')
    elif case in ('threshold_below', 'threshold_above'):
        z = .0282 if case == 'threshold_below' else .0284
        deltas = {'A': [[0, 0, z], [0, 0, 0], [0, 0, 0], [0, 0, 0]]}
    controls = [x for x in ('A', 'B', 'C', 'D') if x in deltas]
    names = list(deltas)
    text = replace_array(text, 'deltaStateWeights', 'vector2', [[0, 0]]*len(names))
    text = re.sub(r'("deltaStates" "element_array"\s*\[).*?(\])',
                  lambda m: m[1] + ',\n'.join('"element" "' + guid(0x20+i) + '"' for i in range(len(names))) + m[2], text, flags=re.S)
    for i, name in enumerate(names):
        authored = []
        for j, n in enumerate(normals):
            target = unit([n[0]+(.24-.05*i)*(1+.12*j), n[1]+(-.07+.03*i)*(1+.12*j), n[2]+.03])
            authored.append([target[k]-n[k] for k in range(3)])
        body = field('vertexFormat', 'string', ['positions', 'normals'])
        body += field('positions', 'vector3', deltas[name]) + field('positionsIndices', 'int', range(4))
        body += field('normals', 'vector3', authored) + field('normalsIndices', 'int', range(len(normals)))
        text += block('DmeVertexDeltaData', 0x20+i, name, body)
    body = '"controls" "element_array" [ ' + ', '.join('"element" "' + guid(0x30+i) + '"' for i in range(len(controls))) + ' ]\n'
    text += block('DmeCombinationOperator', 0xf, 'mesh', body + '"targets" "element_array" [ "element" "' + guid(9) + '" ]')
    for i, name in enumerate(controls):
        text += block('DmeCombinationInputControl', 0x30+i, name,
                      field('rawControlNames', 'string', [name]) + field('wrinkleScales', 'float', [0]) + '"stereo" "bool" "0"\n"eyelid" "bool" "0"')
    return text, names, positions, deltas


def parse_model(path):
    data = path.read_bytes()
    vvd = path.with_suffix('.vvd').read_bytes()
    integer = lambda offset: struct.unpack_from('<i', data, offset)[0]
    string = lambda offset: data[offset:data.index(b'\0', offset)].decode('utf8')
    desc = [string(integer(264)+i*4+integer(integer(264)+i*4)) for i in range(integer(260))]
    body = integer(236)
    model = body + integer(body+12)
    start = struct.unpack_from('<i', vvd, 56)[0]
    keys, vertices = [], {}
    for i in range(integer(model+80)):
        p = start + i*48
        position = struct.unpack_from('<3f', vvd, p+16)
        uv = struct.unpack_from('<2f', vvd, p+40)
        key = ','.join(f'{v:.6f}' for v in position + uv)
        assert key not in vertices, 'ambiguous position/UV vertex identity'
        keys.append(key)
        vertices[key] = {'position': position, 'normal': struct.unpack_from('<3f', vvd, p+28)}
    flex = {}
    for i in range(integer(model+72)):
        mesh = model + integer(model+76) + i*116
        for j in range(integer(mesh+16)):
            p = mesh + integer(mesh+20) + j*60
            records = flex.setdefault(desc[integer(p)], {})
            stride = 18 if data[p+32] else 16
            for k in range(integer(p+20)):
                q = p + integer(p+24) + k*stride
                key = keys[integer(mesh+12)+struct.unpack_from('<H', data, q)[0]]
                records[key] = struct.unpack_from('<6e', data, q+4)
    return {'vertices': vertices, 'flex': flex}


def compile_fixture(executable, case, folder, profile='ce', reference=False, local=False):
    text, names, positions, deltas = make_fixture(case)
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'face.dmx').write_text(text, encoding='utf8')
    (folder/'idle.smd').write_text('version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\n')
    (folder/'gameinfo.txt').write_text('GameInfo { game fixture FileSystem { SteamAppId 220 SearchPaths { game "|gameinfo_path|." } } }')
    options = '' if case.startswith('authored') or local else '$ComputeDeltaNormals\n'
    rules = '\n'.join('%' + name + ' = ' + ' * '.join(name.split('_')) for name in names)
    qc = ('' if reference else '$dmxcompatibility ' + profile + '\n') + '$modelname face\n' + options
    qc += '$model face face.dmx ' + ('ComputeDeltaNormals ' if local else '') + '{\n' + rules + '\n}\n$sequence idle idle.smd\n'
    path = folder/'face.qc'
    path.write_text(qc)
    run = subprocess.run([str(executable), '-game', str(folder), str(path)], cwd=folder,
                         input=b'\n', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
    assert run.returncode == 0, run.stdout.decode(errors='replace')
    result = parse_model(folder/'models/face.mdl')
    return result, hashlib.sha256(text.encode('utf8')).hexdigest()


CASES = ['zero_corrective', 'zero_independent', 'unordered_subsets', 'seam_subsets',
         'unequal_faces', 'threshold_below', 'threshold_above', 'authored_seam']


class CombinedNormalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='newpage-ce-normals-')
        cls.root = Path(cls.temp.name)
        cls.reference = json.loads(SNAPSHOT.read_text(encoding='utf8'))
        cls.outputs = {}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def output(self, case, profile='ce', local=False):
        key = (case, profile, local)
        if key not in self.outputs:
            self.outputs[key] = compile_fixture(OPTIONS.compiler, case, self.root/('_'.join(map(str, key))), profile, local=local)
        return self.outputs[key]

    def test_reference_serialized_normals_positions_and_seams(self):
        for case in CASES:
            with self.subTest(case=case):
                actual, digest = self.output(case)
                frozen = self.reference['cases'][case]
                self.assertEqual(digest, frozen['input_sha256'])
                expected = frozen['model']
                self.assertEqual(set(actual['vertices']), set(expected['vertices']))
                self.assertEqual(set(actual['flex']), set(expected['flex']))
                for key in actual['vertices']:
                    for a, b in zip(actual['vertices'][key]['normal'], expected['vertices'][key]['normal']):
                        self.assertAlmostEqual(a, b, delta=2e-6)
                for name, records in actual['flex'].items():
                    self.assertEqual(set(records), set(expected['flex'][name]))
                    for key, record in records.items():
                        for a, b in zip(record, expected['flex'][name][key]):
                            self.assertAlmostEqual(a, b, delta=0.00015)

    def test_zero_corrective_reconstructs_geometry_in_both_profiles(self):
        _, _, positions, deltas = make_fixture('zero_corrective')
        posed = [[p[k] + sum(d[i][k] for d in deltas.values()) for k in range(3)] for i, p in enumerate(positions)]
        a, b, c = (posed[i] for i in (0, 2, 3))
        u, v = ([b[k]-a[k] for k in range(3)], [c[k]-a[k] for k in range(3)])
        target = unit([u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]])
        for profile in ('ce', 'native'):
            with self.subTest(profile=profile):
                actual, _ = self.output('zero_corrective', profile)
                key = next(k for k, v in actual['vertices'].items() if v['position'] == (0, 2, 0))
                residual = actual['flex']['A_B_C'][key]
                self.assertEqual(residual[:3], (0, 0, 0))
                self.assertGreater(sum(x*x for x in residual[3:]), .0001)
                normal = [actual['vertices'][key]['normal'][k] + sum(f.get(key, [0]*6)[k+3] for f in actual['flex'].values()) for k in range(3)]
                self.assertAlmostEqual(math.sqrt(sum(x*x for x in normal)), 1, delta=.0002)
                for a, b in zip(unit(normal), target): self.assertAlmostEqual(a, b, delta=.00015)

    def test_unordered_intermediate_subsets_reconstruct_geometry_native(self):
        actual, _ = self.output('unordered_subsets', 'native')
        _, _, positions, deltas = make_fixture('unordered_subsets')
        posed = [[p[k] + sum(d[i][k] for d in deltas.values()) for k in range(3)] for i, p in enumerate(positions)]
        a, b, c = (posed[i] for i in (0, 2, 3))
        u, v = ([b[k]-a[k] for k in range(3)], [c[k]-a[k] for k in range(3)])
        target = unit([u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]])
        key = next(k for k, v in actual['vertices'].items() if v['position'] == (0, 2, 0))
        normal = [actual['vertices'][key]['normal'][k] + sum(f.get(key, [0]*6)[k+3] for f in actual['flex'].values()) for k in range(3)]
        for a, b in zip(unit(normal), target): self.assertAlmostEqual(a, b, delta=.00015)

    def test_local_switch_matches_global(self):
        self.assertEqual(self.output('zero_corrective')[0], self.output('zero_corrective', local=True)[0])

    def test_ce_threshold_and_zero_independent(self):
        below, _ = self.output('threshold_below')
        above, _ = self.output('threshold_above')
        # A moving vertex survives the subsequent MDL flex cull independently
        # of its normal, so this isolates the earlier CE generation threshold.
        key = next(k for k, v in below['vertices'].items() if v['position'] == (0, 0, 0))
        self.assertEqual(below['flex']['A'].get(key, (0,)*6)[3:], (0, 0, 0))
        self.assertGreater(sum(x*x for x in above['flex']['A'][key][3:]), .0001)
        self.assertNotIn('D', self.output('zero_independent')[0]['flex'])

    def test_native_preserves_area_weighting(self):
        native, _ = self.output('unequal_faces', 'native')
        ce, _ = self.output('unequal_faces')
        key = next(k for k, v in ce['vertices'].items() if v['position'] == (0, 0, 0))
        # The two face crosses are (0,-1.6,8) and (-.4,0,2).
        expected = unit([-.4, -1.6, 10])
        for a, b in zip(native['vertices'][key]['normal'], expected): self.assertAlmostEqual(a, b, delta=2e-6)
        self.assertGreater(max(abs(a-b) for a, b in zip(ce['vertices'][key]['normal'], expected)), .01)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('compiler', type=Path)
    parser.add_argument('--reference', type=Path)
    OPTIONS, rest = parser.parse_known_args()
    OPTIONS.compiler = OPTIONS.compiler.resolve()
    if OPTIONS.reference:
        reference = OPTIONS.reference.resolve()
        snapshot = {'reference': {'name': 'StudioMDL-CE 0.3.0 Preview', 'sha256': hashlib.sha256(reference.read_bytes()).hexdigest()},
                    'scope': 'Self-authored two-triangle DMX; serialized base/delta normals and positions, no game-rendering assertion.', 'cases': {}}
        with tempfile.TemporaryDirectory(prefix='ce-normal-reference-') as directory:
            for case in CASES:
                model, digest = compile_fixture(reference, case, Path(directory)/case, reference=True)
                snapshot['cases'][case] = {'input_sha256': digest, 'model': model}
        SNAPSHOT.write_text(json.dumps(snapshot, indent=2)+'\n', encoding='utf8')
    else:
        unittest.main(argv=[__file__]+rest)
