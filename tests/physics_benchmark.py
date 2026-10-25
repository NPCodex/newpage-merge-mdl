"""Bounded closed-box collision benchmark; compare two same-configuration builds.

Usage: python tests/physics_benchmark.py BASELINE CANDIDATE OUTPUT_DIRECTORY
Produces isolated authored inputs, native timing reports and decoded PHY evidence.
This measures these fixtures, not arbitrary models or in-game physics performance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import struct
import subprocess
import time
import unittest

from physics_extra_cases import PhysicsExtraCases


class Fixture(PhysicsExtraCases, unittest.TestCase):
    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_case(root, count, bones, tolerance):
    obj = Fixture()
    obj.root = root
    obj.extra_boxes('render.smd', [(0, 0, 0, 2, 2, 2)])
    obj.extra_boxes('collision.smd', [(i * 4, 0, 0, i * 4 + 2, 2, 2)
                                      for i in range(count)])
    if bones > 1:
        text = (root / 'collision.smd').read_text()
        nodes = ''.join(f'{i} "bone{i}" {0 if i else -1}\n' for i in range(bones))
        poses = ''.join(f'{i} 0 0 0 0 0 0\n' for i in range(bones))
        text = text.replace('0 "root" -1\n', nodes).replace('0 0 0 0 0 0 0\n', poses)
        lines = text.splitlines()
        for i, line in enumerate(lines):
            fields = line.split()
            if len(fields) == 9:
                # x lies at either endpoint of an isolated box.
                fields[0] = str((int(float(fields[1])) // 4) % bones)
                lines[i] = ' '.join(fields)
        obj.write('collision.smd', '\n'.join(lines) + '\n')
        obj.write('render.smd', (root / 'render.smd').read_text().replace('"root"', '"bone0"'))
    collision = '$collisionjoints' if bones > 1 else '$collisionmodel'
    concave = '$concaveperjoint' if bones > 1 else '$concave'
    obj.write('case.qc', '$modelname case\n$origin 0 0 0 -90\n$bonecullmethod none\n'
              f'$body m render.smd\n{collision} collision.smd '
              f'{{ $mass 100 {concave} $weldposition {tolerance} }}\n')
    return obj


def snapshot(obj, expected_bones):
    data = (obj.root / 'models/case.phy').read_bytes()
    solids = []
    for solid in range(expected_bones):
        _, hulls, volumes = obj.extra_phy_hulls('case', solid, expected_bones)
        solids.append({'hulls': len(hulls), 'vertices': sum(map(len, hulls)),
                       'volume': sum(abs(v) for v in volumes),
                       'bounds': [[min(p[i] for h in hulls for p in h),
                                   max(p[i] for h in hulls for p in h)] for i in range(3)]})
    return {'physics_sha256_except_model_checksum': hashlib.sha256(data[:12] + data[16:]).hexdigest(),
            'solids': solids}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--runs', type=int, default=5)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = {'baseline': {'path': str(args.baseline), 'sha256': digest(args.baseline)},
              'candidate': {'path': str(args.candidate), 'sha256': digest(args.candidate)},
              'runs': args.runs, 'warmups': 1, 'cases': {}}
    for name, count, bones, tolerance in [('default-cube', 1, 1, 0),
                                          ('islands-1024', 1024, 1, 0),
                                          ('tolerance-islands-1024', 1024, 1, .25),
                                          ('ragdoll-64x8', 512, 64, 0)]:
        obj = make_case(args.output / name, count, bones, tolerance)
        case = {'boxes': count, 'input_vertices': count * 8, 'input_triangles': count * 12,
                'bones': bones, 'tolerance': tolerance, 'baseline': [], 'candidate': []}
        input_hashes = {p.name: digest(p) for p in obj.root.iterdir() if p.is_file()}
        reference = None
        for run in range(args.runs + 1):
            for label, compiler in [('baseline', args.baseline), ('candidate', args.candidate)][::1 if run % 2 else -1]:
                report = obj.root / f'{label}-{run}.json'
                start = time.perf_counter()
                proc = subprocess.run([str(compiler), str(obj.root / 'case.qc'), '-game', str(obj.root),
                                       '-perfjson', str(report)], capture_output=True, timeout=120)
                wall_ms = (time.perf_counter() - start) * 1000
                (obj.root / f'{label}-{run}.log').write_bytes(proc.stdout + proc.stderr)
                if proc.returncode:
                    raise RuntimeError(f'{name} {label} failed; see log')
                raw = json.loads(report.read_text())
                output = snapshot(obj, bones)
                if reference is None:
                    reference = output
                elif output != reference:
                    raise AssertionError(f'{name}: decoded or binary PHY output changed ({label}, {run})')
                if run:
                    case[label].append({'wall_ms': wall_ms,
                                        'collision_ms': next(s['ms'] for s in raw['stages']
                                                             if s['name'] == 'BuildCollisionModel'),
                                        'compile_ms': raw['compile_ms'],
                                        'peak_working_set_bytes': raw['peak_working_set_bytes']})
        case['output'] = reference
        case['inputs_sha256'] = input_hashes
        case['median'] = {label: {key: statistics.median(row[key] for row in case[label])
                                  for key in case[label][0]} for label in ('baseline', 'candidate')}
        result['cases'][name] = case
        (args.output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(name, json.dumps(case['median']), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
