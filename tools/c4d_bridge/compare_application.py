"""Compare an authored Cinema 4D application reference with bridge GLB output.

This accepts the bounded polygon fixture schema written by author_fixtures.py;
it is not a general scene or Cinema 4D conformance validator.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct


IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
CONVERSION = [.01, 0, 0, 0, 0, .01, 0, 0, 0, 0, -.01, 0, 0, 0, 0, 1]


def multiply(a, b):
    return [sum(a[k * 4 + row] * b[col * 4 + k] for k in range(4))
            for col in range(4) for row in range(4)]


def from_c4d(matrix):
    return [value for index, column in enumerate(matrix) for value in (*column, 1 if index == 3 else 0)]


def point(matrix, value):
    return [sum(matrix[k * 4 + row] * value[k] for k in range(3)) + matrix[12 + row]
            for row in range(3)]


def error(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def glb(path):
    data = path.read_bytes()
    if data[:4] != b'glTF':
        raise ValueError('Expected GLB')
    chunks = {}
    offset = 12
    while offset < len(data):
        size, kind = struct.unpack_from('<II', data, offset)
        chunks[kind] = data[offset + 8:offset + 8 + size]
        offset += 8 + size
    doc, binary = json.loads(chunks[0x4e4f534a]), chunks[0x004e4942]

    def accessor(index):
        item = doc['accessors'][index]
        view = doc['bufferViews'][item['bufferView']]
        count = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[item['type']]
        fmt = '<' + str(count) + {5121: 'B', 5123: 'H', 5125: 'I', 5126: 'f'}[item['componentType']]
        start = view.get('byteOffset', 0) + item.get('byteOffset', 0)
        return [struct.unpack_from(fmt, binary, start + i * view.get('byteStride', struct.calcsize(fmt)))
                for i in range(item['count'])]
    return doc, accessor


def compare(reference, converted):
    authored = json.loads(reference.read_text(encoding='utf-8'))
    doc, accessor = glb(converted)
    expected = {node['name']: node for node in authored['reference'] if 'polygons' in node}
    source = {node['name']: node for node in authored['hierarchy']}
    result = {'schema': 1, 'application_version': authored['version'], 'meshes': [],
              'source_hierarchy_nodes_checked': 0, 'max_world_position_error_m': 0.,
              'max_local_position_error_cm': 0., 'max_uv_error': 0., 'max_normal_component_error': 0.,
              'diffuse_colors_checked': 0, 'success': False}
    visited, mesh_names, source_names = set(), [], []

    def visit(index, parent, world):
        if index in visited:
            raise ValueError('Repeated/cyclic GLB node')
        visited.add(index)
        node = doc['nodes'][index]
        name = node.get('name', '')
        local = node.get('matrix', IDENTITY)
        world = multiply(world, local)
        if name in source:
            original = source[name]
            if error(local, from_c4d(original['local'])) > 1e-5:
                raise ValueError('Local hierarchy transform differs: ' + name)
            expected_parent = original['parent'] or '<C4DRoot>'
            if parent != expected_parent:
                raise ValueError('Source hierarchy parent differs: ' + name)
            result['source_hierarchy_nodes_checked'] += 1
            source_names.append(name)
        if 'mesh' in node:
            mesh = doc['meshes'][node['mesh']]
            name = mesh['name']
            if name not in expected:
                raise ValueError('Unexpected mesh: ' + name)
            mesh_names.append(name)
            ref = expected[name]
            reference_world = multiply(CONVERSION, from_c4d(ref['world']))
            corners = []
            for pi, polygon in enumerate(ref['polygons']):
                if len(set(polygon)) != 4:
                    raise ValueError('Authored comparison expects nondegenerate quads')
                for corner, key in enumerate('abcd'):
                    corners.append((pi, corner, ref['points'][polygon[corner]],
                                    ref['uv'][pi][key][:2], ref['normals'][4 * pi + corner]))
            counts = Counter()
            used = {pi: set() for pi in range(len(ref['polygons']))}
            triangles = 0
            for primitive in mesh['primitives']:
                if primitive.get('mode', 4) != 4:
                    raise ValueError('Expected triangles')
                material = doc['materials'][primitive['material']]
                # This authored fixture has a single unrestricted texture tag.
                if len(ref['materials']) != 1 or ref['materials'][0]['restriction']:
                    raise ValueError('Unsupported reference material assignment')
                matref = ref['materials'][0]
                if material['name'] != matref['material']:
                    raise ValueError('Material assignment differs: ' + name)
                if matref.get('diffuse') is not None:
                    if error(material['pbrMetallicRoughness']['baseColorFactor'], matref['diffuse'] + [1]) > 1e-6:
                        raise ValueError('Diffuse color differs: ' + name)
                    result['diffuse_colors_checked'] += 1
                attrs = primitive['attributes']
                positions, normals, uvs = (accessor(attrs[key]) for key in ('POSITION', 'NORMAL', 'TEXCOORD_0'))
                if not (len(positions) == len(normals) == len(uvs)):
                    raise ValueError('Corner attribute counts differ')
                matches = []
                for position, normal, uv in zip(positions, normals, uvs):
                    candidates = [c for c in corners if error(position, c[2]) <= 1e-5
                                  and error(uv, c[3]) <= 1e-6 and error(normal, c[4]) <= 1e-5]
                    if not candidates:
                        raise ValueError('Position, UV or normal corner differs: ' + name)
                    best = min(candidates, key=lambda c: error(position, c[2]) + error(uv, c[3]) + error(normal, c[4]))
                    world_error = error(point(world, position), point(reference_world, best[2]))
                    if world_error > 1e-6:
                        raise ValueError('Evaluated world transform differs: ' + name)
                    for key, value in [('max_local_position_error_cm', error(position, best[2])),
                                       ('max_world_position_error_m', world_error),
                                       ('max_uv_error', error(uv, best[3])),
                                       ('max_normal_component_error', error(normal, best[4]))]:
                        result[key] = max(result[key], value)
                    matches.append(candidates)
                indices = [i[0] for i in accessor(primitive['indices'])]
                if len(indices) % 3:
                    raise ValueError('Incomplete triangle')
                for offset in range(0, len(indices), 3):
                    vertices = [matches[i] for i in indices[offset:offset + 3]]
                    polygons = set.intersection(*({c[0] for c in vertex} for vertex in vertices))
                    if len(polygons) != 1:
                        raise ValueError('Triangle does not belong to one reference polygon')
                    polygon = polygons.pop()
                    corner_ids = {next(c[1] for c in vertex if c[0] == polygon) for vertex in vertices}
                    if len(corner_ids) != 3:
                        raise ValueError('Degenerate triangle')
                    counts[polygon] += 1
                    used[polygon].update(corner_ids)
                    triangles += 1
            if any(counts[pi] != 2 or len(used[pi]) != 4 for pi in range(len(ref['polygons']))):
                raise ValueError('Missing or duplicate evaluated geometry: ' + name)
            result['meshes'].append({'name': name, 'reference_quads': len(ref['polygons']), 'triangles': triangles})
        for child in node.get('children', []):
            visit(child, node.get('name', ''), world)

    for index in doc['scenes'][doc.get('scene', 0)]['nodes']:
        visit(index, None, IDENTITY)
    if Counter(mesh_names) != Counter(expected.keys()) or Counter(source_names) != Counter(source.keys()):
        raise ValueError('Source hierarchy or evaluated meshes are missing/duplicated')
    result['success'] = True
    return result


def assess_skin(reference):
    """Check this script's two-joint bind/weight contract against three C4D poses.

    The source script supplies weights 0/.5/1; this assessment does not read
    weights from a C4D document or establish skeletal import support.
    """
    authored = json.loads(reference.read_text(encoding='utf-8'))
    if [sample['frame'] for sample in authored['samples']] != [0, 15, 30]:
        raise ValueError('Expected the three authored skin samples')
    frames = []
    maximum = 0.
    for sample in authored['samples']:
        nodes = {node['name']: node for node in sample['hierarchy']}
        mesh = nodes['AnimatedSkin']
        tip = from_c4d(nodes['SkinTip']['world'])
        ref = next(node for node in sample['reference'] if node['name'] == 'AnimatedSkin')
        if len(mesh['points']) != 6 or len(ref['points']) != 6:
            raise ValueError('Expected the authored six-point strip')
        sample_error = 0.
        for index, vertex in enumerate(mesh['points']):
            weight = 0. if index < 2 else .5 if index < 4 else 1.
            # In this fixture root bind is identity and tip bind is (0,100,0).
            transformed = point(tip, [vertex[0], vertex[1] - 100, vertex[2]])
            predicted = [(1 - weight) * a + weight * b for a, b in zip(vertex, transformed)]
            sample_error = max(sample_error, error(predicted, ref['points'][index]))
        if sample_error > .0002:
            raise ValueError('Authored linear blend differs from C4D evaluated pose')
        maximum = max(maximum, sample_error)
        frames.append({'frame': sample['frame'], 'max_position_error_cm': sample_error})
    return {'application_version': authored['version'], 'fps': authored['fps'], 'frames': frames,
            'max_position_error_cm': maximum, 'tolerance_cm': .0002,
            'scope': 'Assessment of authored bind/weight model; skeletal import remains unsupported'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('converted', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--skin-reference', type=Path)
    args = parser.parse_args()
    result = compare(args.reference, args.converted)
    if args.skin_reference:
        result['skin_assessment'] = assess_skin(args.skin_reference)
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
