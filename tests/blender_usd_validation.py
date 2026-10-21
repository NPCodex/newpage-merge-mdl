"""Optional real Blender USD author/export check; all samples are self-authored.

Usage: python tests/blender_usd_validation.py COMPILER BLENDER NEW_OUTPUT_DIR
Runs Blender in factory-startup background mode without opening user documents.
Requires Blender's USD exporter and Python pxr bindings. Not part of normal CI.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys


def author(output):
    import bpy
    from pxr import Usd, UsdGeom

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    top = bpy.data.objects.new('Parent', None)
    scene.collection.objects.link(top)
    top.location = (3, -2, 5)
    top.rotation_euler = (.2, 0, .35)
    nested = bpy.data.objects.new('Nested', None)
    scene.collection.objects.link(nested)
    nested.parent = top
    nested.location = (1, 2, -1)
    nested.rotation_euler = (0, .25, -.4)
    nested.scale = (1.2, .7, 1.6)
    mesh = bpy.data.meshes.new('AsymmetricTetra')
    mesh.from_pydata([(0, 0, 0), (2, 0, 0), (.3, 1.4, 0), (.2, .1, 2.3)], [],
                     [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)])
    mesh.update()
    for name, location, scale in [('First', (-2, 1, 0), (1, 1, 1)),
                                  ('Linked', (8, 0, 0), (-1.3, .8, 1))]:
        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)
        obj.parent = nested
        obj.location = location
        obj.scale = scale
        obj.rotation_euler = (.2, .4, 0)
    collection = bpy.data.collections.new('InstancedAssembly')
    prototype = bpy.data.objects.new('PrototypeTetra', mesh)
    collection.objects.link(prototype)
    prototype.location = (.5, -.2, 1)
    for name, location in [('AssemblyOne', (-7, 10, 0)), ('AssemblyTwo', (2, 11, -1))]:
        instance = bpy.data.objects.new(name, None)
        scene.collection.objects.link(instance)
        instance.instance_type = 'COLLECTION'
        instance.instance_collection = collection
        instance.parent = top
        instance.location = location
        instance.rotation_euler = (0, .15, .7)
    bpy.ops.mesh.primitive_cube_add(size=2, location=(-4, 3, 1))
    bevel = bpy.context.object
    bevel.name = 'EvaluatedBevel'
    bevel.parent = top
    modifier = bevel.modifiers.new('AuthoredBevel', 'BEVEL')
    modifier.width = .23
    modifier.segments = 2
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    expected = []
    objects = []
    for instance in depsgraph.object_instances:
        obj = instance.object
        if obj.type != 'MESH':
            continue
        evaluated = obj.to_mesh()
        points = [list(instance.matrix_world @ vertex.co) for vertex in evaluated.vertices]
        expected.extend(points)
        objects.append(dict(name=obj.name, vertices=len(points), polygons=len(evaluated.polygons)))
        obj.to_mesh_clear()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'authored.blend'), check_existing=False)
    cases = []
    for instancing in (False, True):
        for suffix in ('usda', 'usdc'):
            filename = ('instances' if instancing else 'expanded') + '.' + suffix
            bpy.ops.wm.usd_export(filepath=str(output / filename), check_existing=False,
                export_animation=False, export_materials=False, export_lights=False,
                export_cameras=False, use_instancing=instancing, export_subdivision='TESSELLATE',
                convert_orientation=False, root_prim_path='/World', xform_op_mode='MAT')
            stage = Usd.Stage.Open(str(output / filename))
            cases.append(dict(file=filename, expected=expected,
                source='Blender native USD exporter',
                references=sum(prim.HasAuthoredReferences() for prim in stage.TraverseAll()),
                instances=sum(prim.IsInstance() for prim in stage.TraverseAll())))
            if instancing and not cases[-1]['instances']:
                raise RuntimeError('Exporter did not produce actual USD instances')
    # Composition opinions are authored explicitly with OpenUSD. Geometry and its
    # full nested transform hierarchy remain the actual Blender-exported layer.
    stage = Usd.Stage.CreateNew(str(output / 'selected-variant.usda'))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    holder = UsdGeom.Xform.Define(stage, '/Asset')
    stage.SetDefaultPrim(holder.GetPrim())
    holder.AddTranslateOp().Set((12, -3, 2))
    variants = holder.GetPrim().GetVariantSets().AddVariantSet('geometry')
    for variant, source in [('expanded', 'expanded.usda'), ('instanced', 'instances.usdc')]:
        variants.AddVariant(variant)
        variants.SetVariantSelection(variant)
        with variants.GetVariantEditContext():
            holder.GetPrim().GetReferences().AddReference(source, '/World')
    variants.SetVariantSelection('instanced')
    stage.GetRootLayer().Save()
    cases.append(dict(file='selected-variant.usda',
        source='OpenUSD selected variant referencing native Blender layer',
        expected=[[p[0]+12, p[1]-3, p[2]+2] for p in expected]))
    for case in list(cases):
        stage = Usd.Stage.Open(str(output / case['file']))
        cache = UsdGeom.XformCache()
        usd_world = []
        for prim in stage.Traverse(Usd.TraverseInstanceProxies()):
            if prim.IsA(UsdGeom.Mesh):
                transform = cache.GetLocalToWorldTransform(prim)
                usd_world.extend(list(transform.Transform(point))
                    for point in UsdGeom.Mesh(prim).GetPointsAttr().Get())
        case['openusd_reference_error'] = max(distance(usd_world, case['expected']),
                                               distance(case['expected'], usd_world))
        if case['openusd_reference_error'] > .0001:
            raise RuntimeError('Exported USD disagrees with Blender evaluated world vertices')
        flattened = Path(case['file']).stem + '-' + Path(case['file']).suffix[1:] + '-flattened.usdc'
        stage.Flatten().Export(str(output / flattened))
        cases.append(dict(file=flattened, source='OpenUSD Flatten of '+case['file'],
                          expected=case['expected']))
    report = dict(blender=bpy.app.version_string,
        blender_build_hash=bpy.app.build_hash.decode(), openusd_version=Usd.GetVersion(),
        objects=objects, cases=cases)
    (output / 'author-reference.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


def positions(path):
    data = path.read_bytes()
    if data[:4] != b'IDSV':
        raise ValueError('Unexpected VVD header')
    count = struct.unpack_from('<i', data, 16)[0]
    start = struct.unpack_from('<i', data, 56)[0]
    if count < 0 or start < 0 or start + count * 48 > len(data):
        raise ValueError('Invalid VVD vertex table')
    return [struct.unpack_from('<3f', data, start + i * 48 + 16) for i in range(count)]


def distance(a, b):
    # Position coverage ignores exporter-created per-corner UV/normal splits.
    return max(min(math.dist(point, other) for other in b) for point in a)


def validate(compiler, blender, output):
    output.mkdir(parents=True, exist_ok=False)
    result = subprocess.run([str(blender), '--background', '--factory-startup', '--python',
        str(Path(__file__).resolve()), '--', '--author', str(output)], capture_output=True,
        text=True, errors='replace', timeout=180)
    (output / 'blender.log').write_text(result.stdout+result.stderr, encoding='utf-8')
    if result.returncode or not (output/'author-reference.json').is_file():
        raise RuntimeError('Blender author/export failed; inspect '+str(output/'blender.log'))
    reference = json.loads((output/'author-reference.json').read_text())
    report = dict(schema=1, compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),
        blender=reference['blender'], blender_build_hash=reference['blender_build_hash'],
        openusd_version=reference['openusd_version'], cases=[],
        scope='World-position coverage, not topology, shading, animation or game-runtime parity')
    for index, case in enumerate(reference['cases']):
        name = f'blender{index}'
        qc = output/(name+'.qc')
        qc.write_text('$modelname '+name+'\n$UpAxis z assimp\n$body m "'+case['file']+'"\n', encoding='utf-8')
        result = subprocess.run([str(compiler), str(qc), '-nodefaultargs', '-game', str(output),
            '-OutDir', str(output/'compiled')], capture_output=True, text=True,
            errors='replace', timeout=60)
        (output/(name+'.log')).write_text(result.stdout+result.stderr, encoding='utf-8')
        checked = dict(file=case['file'], source=case['source'], exit_code=result.returncode,
            input_sha256=hashlib.sha256((output/case['file']).read_bytes()).hexdigest())
        if result.returncode == 0:
            from validate_outputs import validate as validate_model
            validate_model(output/'compiled/models'/(name+'.mdl'))
            actual = positions(output/'compiled/models'/(name+'.vvd'))
            expected = case['expected']
            a, b = distance(actual, expected), distance(expected, actual)
            checked.update(actual_vertices=len(actual), reference_vertices=len(expected),
                max_actual_to_reference=a, max_reference_to_actual=b, tolerance=.0001,
                passed=max(a,b) <= .0001)
        else:
            checked['passed'] = False
        report['cases'].append(checked)
    report['passed'] = all(case['passed'] for case in report['cases'])
    (output/'results.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    if '--author' in sys.argv:
        author(Path(sys.argv[sys.argv.index('--author')+1]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('compiler', type=Path)
        parser.add_argument('blender', type=Path)
        parser.add_argument('output', type=Path)
        arguments = parser.parse_args()
        raise SystemExit(validate(arguments.compiler.resolve(), arguments.blender.resolve(), arguments.output.resolve()))
