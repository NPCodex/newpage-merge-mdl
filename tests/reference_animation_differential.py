"""Compare decoded animation poses with a locally supplied StudioMDL++.

Unsupported reference syntax is reported separately from pose differences.
Reference programs and user models are never included in release packages.
"""
import argparse
import json
import struct
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler')
    parser.add_argument('--reference', required=True)
    parser.add_argument('--decompiler', required=True)
    parser.add_argument('--work', required=True)
    args = parser.parse_args()
    root = Path(args.work).resolve()
    root.mkdir(parents=True, exist_ok=True)
    header = 'version 1\nnodes\n0 "root" -1\nend\nskeleton\n'
    for name, positions in [('source', [(10, .5), (20, 1)]), ('destination', [(-5, 0), (-10, 0)])]:
        (root / (name + '.smd')).write_text(header + ''.join(f'time {i}\n0 {x} 0 0 0 0 {rot}\n' for i, (x, rot) in enumerate(positions)) + 'end\n')
    (root / 'mesh.smd').write_text(header + 'time 0\n0 0 0 0 0 0 0\nend\ntriangles\nmaterial\n0 0 0 0 0 0 1 0 0\n0 1 0 0 0 0 1 1 0\n0 0 1 0 0 0 1 0 1\nend\n')
    cases = {'copy': 'copy source full', 'copy_half': 'copy source half', 'copy_zero': 'copy source zero', 'match_pos': 'match source pos', 'match_rot': 'match source rot', 'conditional': 'if 0 == 1 { fps 12 } else if 1 == 1 { fps 24 } else { fps 60 }', 'reverse': 'reverse'}
    report = {'schema': 1, 'cases': []}
    for name, command in cases.items():
        qc = root / (name + '.qc')
        qc.write_text(f'$modelname {name}\n$definebone root "" 0 0 0 0 0 0 0 0 0 0 0 0\n$body m mesh.smd\n$weightlist full {{ root 1 }}\n$weightlist half {{ root .5 }}\n$weightlist zero {{ root 0 }}\n$animation source source.smd\n$animation dest destination.smd {{\n{command}\n}}\n$sequence original source\n$sequence result dest\n')
        case = {'name': name, 'command': command, 'outputs': {}}
        for label, compiler in [('project', args.compiler), ('reference', args.reference)]:
            game = root / label
            game.mkdir(exist_ok=True)
            (game / 'gameinfo.txt').write_text('GameInfo { game fixture FileSystem { SteamAppId 220 SearchPaths { Game "|gameinfo_path|." } } }')
            result = subprocess.run([str(Path(compiler).resolve()), '-game', str(game), str(qc)], capture_output=True, timeout=90)
            (root / (name + '-' + label + '.log')).write_bytes(result.stdout + result.stderr)
            mdl = game / 'models' / (name + '.mdl')
            output = {'returncode': result.returncode}
            case['outputs'][label] = output
            if result.returncode or not mdl.exists():
                continue
            data=mdl.read_bytes();count,offset=struct.unpack_from('<2i',data,180)
            for i in range(count):
                desc=offset+i*100;nameoff=desc+struct.unpack_from('<i',data,desc+4)[0]
                if data[nameoff:data.index(b'\0',nameoff)]==b'dest':output['fps']=struct.unpack_from('<f',data,desc+8)[0]
            directory = game / 'decoded' / name
            result = subprocess.run([str(Path(args.decompiler).resolve()), str(mdl), '-smdanimation', '-outdir', str(directory)], capture_output=True, timeout=90)
            (root / (name + '-' + label + '-decode.log')).write_bytes(result.stdout + result.stderr)
            files = list(directory.rglob('dest.smd'))
            if result.returncode or len(files) != 1:
                output['decode_error'] = True
                continue
            frames = []
            skeleton = False
            for line in files[0].read_text().splitlines():
                if line == 'skeleton': skeleton = True
                elif line == 'end': skeleton = False
                elif skeleton:
                    values = line.split()
                    if len(values) == 7 and values[0] == '0': frames.append([float(x) for x in values[1:]])
            output['frames'] = frames
        x, y = (case['outputs'][label] for label in ('project', 'reference'))
        if 'frames' not in x or 'frames' not in y:
            case['status'] = 'compile_or_decode_rejected'
        else:
            case['max_pose_error'] = max((abs(u-v) for a,b in zip(x['frames'],y['frames']) for u,v in zip(a,b)), default=0)
            case['status'] = 'match' if len(x['frames']) == len(y['frames']) and case['max_pose_error'] < .01 and abs(x['fps']-y['fps'])<.001 else 'different'
        report['cases'].append(case)
    (root / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
