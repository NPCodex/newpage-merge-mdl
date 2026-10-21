"""Optional real Blender humanoid author/export and VMD geometry validation.

Usage: python tests/blender_vmd_validation.py COMPILER VMD_TOOL BLENDER NEW_OUTPUT_DIR
All assets are self-authored. Blender runs factory-startup in background. This
checks bind geometry and sampled joint motion; it is not game/skin visual QA.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys


ROLES = ['Pelvis', 'Head1', 'L_Thigh', 'L_Calf', 'L_Foot', 'R_Thigh', 'R_Calf', 'R_Foot']
NAMES = ['hip core', 'head tip', 'leg L upper', 'leg L knee', 'leg L ankle',
         'leg R upper', 'leg R knee', 'leg R ankle']


def author(output):
    import bpy
    from mathutils import Vector
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    data = bpy.data.armatures.new('AsymmetricAuthorRig')
    rig = bpy.data.objects.new('AsymmetricAuthorRig', data)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    heads = [(0, 0, 40), (0, 0, 65), (6, 0, 38), (6, -4, 22), (6, 0, 4),
             (-5, 0, 39), (-5, -3, 19), (-5, 0, 3)]
    tails = [(0, 0, 50), (0, 0, 71), heads[3], heads[4], (6, -7, 4),
             heads[6], heads[7], (-5, -6, 3)]
    parents = [-1, 0, 0, 2, 3, 0, 5, 6]
    for i, name in enumerate(NAMES):
        bone = data.edit_bones.new(name)
        bone.head, bone.tail = heads[i], tails[i]
        bone.roll = .13 * (i + 1)
        if parents[i] >= 0:
            bone.parent = data.edit_bones[NAMES[parents[i]]]
    bpy.ops.object.mode_set(mode='OBJECT')
    vertices, faces, groups = [], [], []
    for name in NAMES:
        bone = data.bones[name]
        start = len(vertices)
        # A box spans each bone; skinning and nontrivial bone axes are authored
        # by Blender, not by manufacturing a binary MDL table.
        length = bone.length
        vertices += [list(bone.matrix_local @ Vector((x, y, z)))
                     for x, y, z in [(-1, .1, -1), (1, .1, -1), (1, length, -1),
                                     (-1, length, -1), (-1, .1, 1), (1, .1, 1),
                                     (1, length, 1), (-1, length, 1)]]
        faces += [tuple(start+i for i in face) for face in
                  [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                   (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]]
        groups.append((name, list(range(start, start+8))))
    mesh = bpy.data.meshes.new('AuthoredWeightedBody')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    body = bpy.data.objects.new('AuthoredWeightedBody', mesh)
    bpy.context.collection.objects.link(body)
    body.parent = rig
    modifier = body.modifiers.new('Skin', 'ARMATURE')
    modifier.object = rig
    for name, indices in groups:
        body.vertex_groups.new(name=name).add(indices, 1, 'REPLACE')
    material = bpy.data.materials.new('AuthoredNeutral')
    body.data.materials.append(material)
    bpy.context.view_layer.update()
    evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    evaluated_mesh = evaluated.to_mesh()
    expected = [list(evaluated.matrix_world @ vertex.co) for vertex in evaluated_mesh.vertices]
    evaluated.to_mesh_clear()
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'authored.blend'), check_existing=False)
    bpy.ops.export_scene.gltf(filepath=str(output/'authored.glb'), check_existing=False,
        export_format='GLB', export_yup=False, export_animations=False, export_skins=True)
    reference = dict(blender=bpy.app.version_string, blender_build_hash=bpy.app.build_hash.decode(),
        bones={name: list(heads[i]) for i, name in enumerate(NAMES)}, world_vertices=expected,
        vertices=len(vertices), faces=len(faces), asymmetric_leg_lengths=True,
        per_bone_roll_radians=[.13*(i+1) for i in range(8)])
    (output/'author-reference.json').write_text(json.dumps(reference, indent=2)+'\n')


def motion(kind):
    tracks = []
    for frame in range(31):
        root_x = .3*math.sin(math.pi*frame/30) if kind == 'planted' else 0
        root_y = -.12*math.sin(math.pi*frame/30) if kind == 'planted' else 0
        angle = .4*frame/30 if kind == 'fk' else 0
        for name, pos, quat in [
            ('下半身', (root_x, root_y, 0), (0, 0, 0, 1)),
            ('左足ＩＫ', ((.2*frame/30) if kind == 'left-step' else 0, 0, 0), (0, 0, 0, 1)),
            ('右足ＩＫ', (0, 0, 0), (0, 0, 0, 1)),
            ('左足', (0, 0, 0), (math.sin(angle/2), 0, 0, math.cos(angle/2)))]:
            tracks.append(name.encode('shift_jis').ljust(15, b'\0') +
                struct.pack('<I7f', frame, *pos, *quat) + bytes(64))
    return (b'Vocaloid Motion Data 0002'.ljust(30, b'\0') + b'authored rig'.ljust(20, b'\0') +
            struct.pack('<I', len(tracks)) + b''.join(tracks) + struct.pack('<II', 0, 0))


def inspect(output):
    from mathutils import Matrix, Quaternion, Vector
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from dmx_keys import channels, sample
    from blender_usd_validation import positions, distance
    reference = json.loads((output/'author-reference.json').read_text())
    data = (output/'compiled/models/author.mdl').read_bytes()
    count, table = struct.unpack_from('<2i', data, 156)
    bones = []
    for index in range(count):
        at = table + index*216
        name_at = at + struct.unpack_from('<i', data, at)[0]
        name = data[name_at:data.index(b'\0', name_at)].decode()
        parent = struct.unpack_from('<i', data, at+4)[0]
        values = struct.unpack_from('<12f', data, at+96)
        inverse_bind = Matrix([values[i:i+4] for i in range(0, 12, 4)] + [(0,0,0,1)])
        bones.append(dict(name=name, parent=parent, bind=inverse_bind.inverted()))
    by_name = {bone['name']: bone for bone in bones}
    joint_error = max((by_name[name]['bind'].translation-Vector(point)).length
                      for name, point in reference['bones'].items())
    actual = positions(output/'compiled/models/author.vvd')
    vertex_error = max(distance(actual, reference['world_vertices']),
                       distance(reference['world_vertices'], actual))
    checks = dict(bind_joint_position_error=joint_error, bind_mesh_position_error=vertex_error)
    worlds = {}
    for kind in ['bind', 'planted', 'left-step', 'fk']:
        tracks = channels(output/(kind+'.dmx'))
        frames = []
        for frame in range(31):
            current = {}
            for bone in bones:
                name = bone['name']
                pos = sample(tracks[name+'_p'], frame/30)
                quat = sample(tracks[name+'_o'], frame/30)
                local = Quaternion((quat[3], *quat[:3])).to_matrix().to_4x4()
                local.translation = Vector(pos)
                parent = bone['parent']
                current[name] = current[bones[parent]['name']] @ local if parent >= 0 else local
            frames.append(current)
        worlds[kind] = frames
    checks['bind_retarget_joint_error'] = max(
        (worlds['bind'][0][name].translation-by_name[name]['bind'].translation).length for name in NAMES)
    checks['planted_foot_max_drift'] = max(
        (frame[name].translation-by_name[name]['bind'].translation).length
        for frame in worlds['planted'] for name in [NAMES[4], NAMES[7]])
    checks['planted_pelvis_displacement'] = (
        worlds['planted'][15][NAMES[0]].translation-worlds['planted'][0][NAMES[0]].translation).length
    checks['left_step_x_displacement'] = (worlds['left-step'][-1][NAMES[4]].translation -
                                         worlds['left-step'][0][NAMES[4]].translation).x
    checks['left_step_right_foot_drift'] = max(
        (frame[NAMES[7]].translation-by_name[NAMES[7]]['bind'].translation).length
        for frame in worlds['left-step'])
    checks['minimum_knee_forward_offset'] = min(-frame[name].translation.y
        for frame in worlds['planted'] for name in [NAMES[3], NAMES[6]])
    checks['fk_left_foot_displacement'] = (worlds['fk'][-1][NAMES[4]].translation -
                                          worlds['fk'][0][NAMES[4]].translation).length
    checks['fk_right_foot_drift'] = max(
        (frame[NAMES[7]].translation-by_name[NAMES[7]]['bind'].translation).length
        for frame in worlds['fk'])
    checks['maximum_segment_length_error'] = max(
        abs((frame[NAMES[a]].translation-frame[NAMES[b]].translation).length -
            (by_name[NAMES[a]]['bind'].translation-by_name[NAMES[b]]['bind'].translation).length)
        for frames in worlds.values() for frame in frames for a,b in [(2,3),(3,4),(5,6),(6,7)])
    source_length = math.dist((.9,10.9,.1), (.9,6,-.1)) + math.dist((.9,6,-.1), (.9,1.1,.4))
    target_length = sum((by_name[NAMES[a]]['bind'].translation-by_name[NAMES[b]]['bind'].translation).length
                        for a,b in [(2,3),(3,4)])
    scale = target_length/source_length
    checks['planted_root_trajectory_error'] = max(
        (frame[NAMES[0]].translation-by_name[NAMES[0]]['bind'].translation -
         Vector((.3*math.sin(math.pi*i/30), 0, -.12*math.sin(math.pi*i/30)))*scale).length
        for i,frame in enumerate(worlds['planted']))
    checks['left_step_trajectory_error'] = max(
        (frame[NAMES[4]].translation-by_name[NAMES[4]]['bind'].translation -
         Vector((.2*i/30*scale, 0, 0))).length
        for i,frame in enumerate(worlds['left-step']))
    # MMD X/Y/Z maps to target X/Z/Y. Conjugating source X rotation by
    # this reflection gives a negative target X rotation (independent oracle).
    fk_rotation = Matrix.Rotation(-.4, 4, 'X')
    checks['fk_world_rotation_error_degrees'] = max(math.degrees(
        (fk_rotation @ by_name[name]['bind']).to_quaternion().rotation_difference(
            worlds['fk'][-1][name].to_quaternion()).angle) for name in NAMES[2:5])
    vvd = (output/'compiled/models/author.vvd').read_bytes()
    vertex_count, = struct.unpack_from('<i', vvd, 16)
    vertex_start, = struct.unpack_from('<i', vvd, 56)
    skin_error = 0
    wrong_bindings = 0
    for index in range(vertex_count):
        at = vertex_start+48*index
        weights = struct.unpack_from('<3f', vvd, at)
        bone_ids = vvd[at+12:at+15]
        active = vvd[at+15]
        point = Vector(struct.unpack_from('<3f', vvd, at+16))
        closest = min(range(len(reference['world_vertices'])),
                      key=lambda i: (point-Vector(reference['world_vertices'][i])).length)
        author_bone = NAMES[closest//8]
        wrong_bindings += int(active != 1 or abs(weights[0]-1) > .0001 or
                              bones[bone_ids[0]]['name'] != author_bone)
        deformed = Vector((0,0,0))
        for slot in range(active):
            bone = bones[bone_ids[slot]]
            deformed += weights[slot]*(worlds['fk'][-1][bone['name']] @ bone['bind'].inverted() @ point)
        expected = Vector(reference['world_vertices'][closest])
        if author_bone in NAMES[2:5]:
            pivot = Vector(reference['bones'][NAMES[2]])
            expected = pivot + fk_rotation.to_3x3() @ (expected-pivot)
        skin_error = max(skin_error, (deformed-expected).length)
    checks['incorrect_skin_bindings'] = wrong_bindings
    checks['fk_skinned_mesh_reference_error'] = skin_error
    checks['passed'] = all(checks[key] < .001 for key in [
        'bind_joint_position_error', 'bind_mesh_position_error', 'bind_retarget_joint_error',
        'planted_foot_max_drift', 'left_step_right_foot_drift', 'fk_right_foot_drift',
        'maximum_segment_length_error', 'planted_root_trajectory_error',
        'left_step_trajectory_error', 'fk_skinned_mesh_reference_error']) and \
        checks['fk_world_rotation_error_degrees'] < .01 and wrong_bindings == 0 and \
        all(checks[key] > .1 for key in [
        'planted_pelvis_displacement', 'left_step_x_displacement',
        'minimum_knee_forward_offset', 'fk_left_foot_displacement'])
    (output/'geometry-checks.json').write_text(json.dumps(checks, indent=2)+'\n')


def validate(compiler, tool, blender, output):
    output.mkdir(parents=True, exist_ok=False)
    def run(command, log, timeout=120):
        result = subprocess.run(list(map(str, command)), capture_output=True, text=True,
                                errors='replace', timeout=timeout)
        (output/log).write_text(result.stdout+result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError('Failed: '+str(output/log))
    run([blender, '--background', '--factory-startup', '--python', Path(__file__).resolve(),
         '--', '--author', output], 'blender-author.log')
    qc = output/'author.qc'
    qc.write_text('$modelname author\n$UpAxis z gltf\n$transformmodel angles 0 0 -90\n'
                  '$bonecullmethod none\n$body body authored.glb\n')
    run([compiler, qc, '-nodefaultargs', '-game', output, '-OutDir', output/'compiled'], 'compiler.log')
    from validate_outputs import validate as validate_model
    validate_model(output/'compiled/models/author.mdl')
    for kind in ['bind', 'planted', 'left-step', 'fk']:
        (output/(kind+'.vmd')).write_bytes(motion(kind))
        profile = output/(kind+'.map')
        profile.write_text('vmd_humanoid_mapping 1\nleg_mode '+('fk' if kind == 'fk' else 'ik')+
            '\nupright keep\nbasis 1 0 0 0 0 1\n'+
            ''.join(f'role {role} "{name}"\n' for role,name in zip(ROLES,NAMES)))
        run([tool, '-mdl', output/'compiled/models/author.mdl', '-vmd', output/(kind+'.vmd'),
             '-mapping', profile, '-dmxencoding', 'keyvalues2', '-o', output/(kind+'.dmx')], kind+'.log')
    run([blender, '--background', '--factory-startup', '--python', Path(__file__).resolve(),
         '--', '--inspect', output], 'blender-inspect.log')
    report = dict(schema=1, compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),
        vmd_tool_sha256=hashlib.sha256(tool.read_bytes()).hexdigest(),
        input_sha256={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in sorted(output.iterdir()) if path.suffix in ['.glb', '.vmd', '.map', '.qc']},
        tolerances=dict(position_model_units=.001, world_rotation_degrees=.01, incorrect_bindings=0),
        author=json.loads((output/'author-reference.json').read_text()),
        checks=json.loads((output/'geometry-checks.json').read_text()),
        scope='Self-authored real Blender meshed asymmetric rig: bind geometry/weights, sampled joints, '
              'planted feet, FK direction and numeric skinned vertex reference. Not production/game/visual certification.')
    (output/'results.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report['checks'], indent=2))
    return 0 if report['checks']['passed'] else 1


if __name__ == '__main__':
    if '--author' in sys.argv:
        author(Path(sys.argv[sys.argv.index('--author')+1]))
    elif '--inspect' in sys.argv:
        inspect(Path(sys.argv[sys.argv.index('--inspect')+1]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        for name in ['compiler', 'tool', 'blender', 'output']:
            parser.add_argument(name, type=Path)
        args = parser.parse_args()
        raise SystemExit(validate(args.compiler.resolve(), args.tool.resolve(),
                                  args.blender.resolve(), args.output.resolve()))
