"""Generate three deterministic, self-authored performance fixtures (no game assets)."""
import argparse
import math
from pathlib import Path


def generate(root):
    root.mkdir(parents=True, exist_ok=True)
    header = 'version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\n'
    for name, side, morphs, clips in [('small', 2, 0, 1), ('large-grid', 100, 0, 1), ('clips-morphs', 20, 16, 24)]:
        folder = root / name
        folder.mkdir(exist_ok=True)
        vertices = [(x, y, .1 * math.sin(x * .1) * math.sin(y * .1)) for y in range(side + 1) for x in range(side + 1)]
        mesh = header + 'triangles\n'
        for y in range(side):
            for x in range(side):
                a = y * (side + 1) + x
                for triangle in ((a, a + 1, a + side + 1), (a + 1, a + side + 2, a + side + 1)):
                    mesh += 'material\n'
                    for i in triangle:
                        px, py, pz = vertices[i]
                        mesh += f'0 {px} {py} {pz:.9f} 0 0 1 {px / side:.9f} {py / side:.9f}\n'
        (folder / 'mesh.smd').write_text(mesh + 'end\n')
        qc = f'$modelname benchmark/{name}\n$definebone root "" 0 0 0 0 0 0 0 0 0 0 0 0\n'
        if morphs:
            vta = 'version 1\nnodes\n0 "root" -1\nend\nskeleton\n' + ''.join(f'time {i}\n0 0 0 0 0 0 0\n' for i in range(morphs + 1)) + 'end\nvertexanimation\n'
            for frame in range(morphs + 1):
                vta += f'time {frame}\n'
                for i, (x, y, z) in enumerate(vertices):
                    vta += f'{i} {x} {y} {z + .1 * frame * math.sin(x * .2):.9f} 0 0 1\n'
            (folder / 'face.vta').write_text(vta + 'end\n')
            qc += '$model body mesh.smd {\nflexfile face.vta\ndefaultflex frame 0\n'
            for frame in range(1, morphs + 1):
                qc += f'flex shape{frame} frame {frame}\nflexcontroller test range 0 1 control{frame}\n%shape{frame} = control{frame}\n'
            qc += '}\n'
        else:
            qc += '$body body mesh.smd\n'
        for clip in range(clips):
            motion = 'version 1\nnodes\n0 "root" -1\nend\nskeleton\n'
            for frame in range(120 if clips > 1 else 1):
                motion += f'time {frame}\n0 {math.sin(frame * .05 + clip) * 2:.9f} 0 0 0 0 {math.sin(frame * .07) * .1:.9f}\n'
            (folder / f'clip{clip}.smd').write_text(motion + 'end\n')
            qc += f'$sequence clip{clip} clip{clip}.smd fps 30\n'
        path = folder / f'{name}.qc'
        path.write_text(qc)
        print(path)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    generate(p.parse_args().directory)
