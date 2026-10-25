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
        count = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[item['type']]
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


def trs_matrix(translation, rotation, scale):
    x, y, z, w = rotation
    return [(1-2*(y*y+z*z))*scale[0], (2*(x*y+z*w))*scale[0], (2*(x*z-y*w))*scale[0], 0,
            (2*(x*y-z*w))*scale[1], (1-2*(x*x+z*z))*scale[1], (2*(y*z+x*w))*scale[1], 0,
            (2*(x*z+y*w))*scale[2], (2*(y*z-x*w))*scale[2], (1-2*(x*x+y*y))*scale[2], 0,
            *translation, 1]


def compare_skin(reference, converted):
    """Evaluate the exported skin and compare independent saved C4D poses.

    Weights/inverse binds are read from GLB, not reconstructed from the author's
    known weight recipe. The reference is an application-authored historical
    document; running this function does not run Cinema 4D again.
    """
    authored = json.loads(reference.read_text(encoding='utf-8'))
    doc, accessor = glb(converted)
    if len(doc.get('skins', [])) != 1 or len(doc.get('animations', [])) != 1:
        raise ValueError('Expected one exported skin and timeline')
    skin, animation = doc['skins'][0], doc['animations'][0]
    binds = accessor(skin['inverseBindMatrices'])
    if len(binds) != len(skin['joints']):
        raise ValueError('Joint/bind matrix count differs')
    if {doc['nodes'][j]['name'] for j in skin['joints']} != {'SkinRoot', 'SkinTip'}:
        raise ValueError('Joint links differ')
    frames, maximum, maximum_joint = [], 0., 0.
    for sample in authored['samples']:
        time = sample['frame'] / authored['fps']
        overrides = {}
        for channel in animation['channels']:
            sampler = animation['samplers'][channel['sampler']]
            times, values = accessor(sampler['input']), accessor(sampler['output'])
            # These reference poses are authored keys; do not introduce another
            # interpolation implementation into the independent comparison.
            matches = [i for i, value in enumerate(times) if abs(value[0]-time) < 1e-6]
            if len(matches) != 1:
                raise ValueError('Expected exactly one exported sample at reference time')
            overrides.setdefault(channel['target']['node'], {})[channel['target']['path']] = values[matches[0]]
        worlds = {}
        def visit(index, parent):
            node = doc['nodes'][index]
            if index in overrides:
                if 'matrix' in node:
                    raise ValueError('Animated GLB node must use TRS')
                v = dict(translation=node.get('translation', [0, 0, 0]),
                         rotation=node.get('rotation', [0, 0, 0, 1]), scale=node.get('scale', [1, 1, 1]))
                v.update(overrides[index]); local = trs_matrix(**v)
            else:
                local = node.get('matrix', trs_matrix(node.get('translation', [0, 0, 0]),
                    node.get('rotation', [0, 0, 0, 1]), node.get('scale', [1, 1, 1])))
            worlds[index] = multiply(parent, local)
            for child in node.get('children', []): visit(child, worlds[index])
        for root in doc['scenes'][doc.get('scene', 0)]['nodes']: visit(root, IDENTITY)
        original = {n['name']: n for n in sample['hierarchy']}
        for joint in skin['joints']:
            expected = multiply(CONVERSION, from_c4d(original[doc['nodes'][joint]['name']]['world']))
            maximum_joint = max(maximum_joint, error(worlds[joint], expected))
        ref = next(n for n in sample['reference'] if n['name'] == 'AnimatedSkin')
        source = original['AnimatedSkin']
        expected_world = multiply(CONVERSION, from_c4d(ref['world']))
        node = next(n for n in doc['nodes'] if n.get('name') == 'AnimatedSkin')
        if node.get('skin') != 0: raise ValueError('Mesh does not reference exported skin')
        seen, corner_count, maximum_frame = set(), 0, 0.
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            attrs = primitive['attributes']
            for vertex, uv, joints, weights in zip(*(accessor(attrs[k]) for k in
                    ('POSITION', 'TEXCOORD_0', 'JOINTS_0', 'WEIGHTS_0'))):
                matches = [i for i, p in enumerate(source['points']) if error(vertex, p) < 1e-5]
                if len(matches) != 1: raise ValueError('Bind point differs or evaluated cache was exported')
                point_index = matches[0]; seen.add(point_index); corner_count += 1
                valid_uv = [source['uv'][pi][key][:2] for pi, polygon in enumerate(source['polygons'])
                            for key, index in zip('abcd', polygon) if index == point_index]
                if not any(error(uv, expected) < 1e-6 for expected in valid_uv):
                    raise ValueError('Skin split corner lost UV')
                if abs(sum(weights)-1) > 1e-6: raise ValueError('Skin weights are not normalized')
                result = [0., 0., 0.]
                for joint, weight in zip(joints, weights):
                    if not weight: continue
                    transform = multiply(worlds[skin['joints'][joint]], binds[joint])
                    transformed = point(transform, vertex)
                    result = [a+weight*b for a, b in zip(result, transformed)]
                maximum_frame = max(maximum_frame, error(result, point(expected_world, ref['points'][point_index])))
        if len(seen) != len(source['points']) or corner_count != 6:
            raise ValueError('Missing/duplicated bind points or split corners')
        if maximum_frame > 2e-6 or maximum_joint > 2e-6:
            raise ValueError('Exported skin or joint animation differs from C4D evaluated reference')
        frames.append({'frame': sample['frame'], 'max_world_position_error_m': maximum_frame})
        maximum = max(maximum, maximum_frame)
    return {'success': True, 'application_version': authored['version'], 'frames': frames,
            'max_world_position_error_m': maximum, 'max_joint_matrix_error': maximum_joint,
            'vertices_checked_per_pose': 6,
            'scope': 'Imported joints, inverse binds, weights, UV corners and linear timeline vs preserved 2027 application poses'}


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
