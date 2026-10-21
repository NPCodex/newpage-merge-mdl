"""Black-box regressions from the v1.2.36 compiler input/timing audit."""
import os
import math
import struct
import base64
import copy
import json
import re
from pathlib import Path
from dmx_dependency_cases import Document, log_fixture
from scene_integration_cases import fbx_bind_fixture, collada_curve_fixture
from scene_fixtures import scene_bytes
from cloth_cases import cloth_dmx


def animated_scale_fbx(dynamic=True):
    text=fbx_bind_fixture().replace('3,"Lcl Translation"','3,"Lcl Scaling"').replace('"AnimCurveNode::T"','"AnimCurveNode::S"')
    for start in (10,20):
        text=text.replace(f'"d|X", "Number", "", "A", {start}','"d|X", "Number", "", "A", 1').replace(f'Default: {start}','Default: 1')
    for axis in ('Y','Z'):text=text.replace(f'"d|{axis}", "Number", "", "A", 0',f'"d|{axis}", "Number", "", "A", 1')
    for old in ('10,14','20,22'):text=text.replace('a: '+old,'a: 1,'+('2' if dynamic else '1'))
    return text


def clip_collision(second='walk'):
    d=Document();text=log_fixture(values=[(1,0,0),(2,0,0)]).replace('"name" "string" "motion"','"name" "string" "Walk"')
    text=text.replace(d.elements('animations',[7]),d.elements('animations',[7,27]))
    d.element(27,'DmeChannelsClip',second,f'"frameRate" "int" "4" "timeFrame" {d.ref(8)} '+d.elements('channels',[29]))
    d.element(29,'DmeChannel','second',f'"toElement" {d.ref(4)} "toAttribute" "string" "position" "log" {d.ref(30)}')
    d.element(30,'DmeVector3Log','log2',d.elements('layers',[31]))
    d.element(31,'DmeVector3LogLayer','layer2',d.array('times','int',[0,10000])+d.array('values','vector3',['10 0 0','20 0 0']))
    return text+'\n'.join(d.rows)


class CompilerInputCases:
    def usd_triangle(self,name='Triangle',height=0,width=1):
        return f'''def Mesh "{name}" {{
    int[] faceVertexCounts = [3]
    int[] faceVertexIndices = [0, 1, 2]
    point3f[] points = [(0, 0, {height}), ({width}, 0, {height}), (0, 1, {height})]
    uniform token subdivisionScheme = "none"
}}\n'''

    def test_usd_nested_references_keep_instances_local_children_and_dependencies(self):
        self.write('parts/mesh.usda','#usda 1.0\n(defaultPrim = "Template")\ndef Xform "Template" {\n'+self.usd_triangle()+'}\n')
        self.write('parts/middle.usda','#usda 1.0\n(defaultPrim = "Link")\ndef Xform "Link" (prepend references = @mesh.usda@) {}\n')
        source='''#usda 1.0
(upAxis = "Z")
def Xform "First" (prepend references = @parts/middle.usda@
    instanceable = false) {
    double3 xformOp:translate = (2, 3, 4)
    uniform token[] xformOpOrder = ["xformOp:translate"]
'''+self.usd_triangle('LocalExtra',2)+'''}
def Xform "Second" (prepend references = @parts/middle.usda@
    instanceable = true) {
    double3 xformOp:translate = (12, 3, 4)
    double3 xformOp:scale = (-2, 3, 1)
    uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
}
'''
        self.write('instances.usda',source)
        self.scene_qc('$modelname usdrefs\n$UpAxis z assimp\n$body m instances.usda\n','-dependencyjson',str(self.root/'usd-deps.json'))
        expected=[(2,3,4),(3,3,4),(2,4,4),(2,3,6),(3,3,6),(2,4,6),(12,3,4),(10,3,4),(12,6,4)]
        self.assertEqual(sorted(tuple(round(x,4) for x in p) for p in self.scene_positions('usdrefs')),sorted(expected))
        dependencies=json.loads((self.root/'usd-deps.json').read_text())['dependencies']
        names={os.path.basename(item['path']) for item in dependencies}
        self.assertTrue({'instances.usda','middle.usda','mesh.usda'}<=names)
        # Full paths disambiguate the repeated mesh leaf name for InNode.
        self.scene_qc('$modelname usdselect\n$UpAxis z assimp\n$body m instances.usda InNode /Second/Triangle\n')
        self.assertEqual(len(self.scene_positions('usdselect')),3)

    def test_usd_instanceable_references_ignore_direct_local_child_opinions(self):
        self.test_usd_nested_references_keep_instances_local_children_and_dependencies()
        original=(self.root/'instances.usda').read_text()
        self.write('instances.usda',original.replace('instanceable = false','instanceable = true'))
        self.scene_qc('$modelname usdinstance\n$UpAxis z assimp\n$body m instances.usda\n')
        expected=[(2,3,4),(3,3,4),(2,4,4),(12,3,4),(10,3,4),(12,6,4)]
        self.assertEqual(sorted(tuple(round(x,4) for x in p) for p in self.scene_positions('usdinstance')),sorted(expected))

    def test_usd_inherited_instanceable_and_local_false_override(self):
        self.write('prototype.usda','#usda 1.0\n(defaultPrim = "Prototype")\ndef Xform "Prototype" (instanceable = true) {\n'+self.usd_triangle()+'}\n')
        root='#usda 1.0\ndef Xform "Reference" (references = @prototype.usda@\n%s) {\n'+self.usd_triangle('LocalExtra',2)+'}\n'
        for value,count in [('',3),('instanceable = false',6),('instanceable = true',3)]:
            self.write('inherited.usda',root%value)
            self.scene_qc('$modelname inheritedusd\n$UpAxis z assimp\n$body m inherited.usda\n')
            self.assertEqual(len(self.scene_positions('inheritedusd')),count)

    def test_usd_variant_selection_and_internal_reference_transform(self):
        asset='''#usda 1.0
(defaultPrim = "Template")
def Xform "Template" (
    variants = {string shape = "narrow"}
    prepend variantSets = "shape"
) {
    variantSet "shape" = {
        "narrow" {
'''+self.usd_triangle(width=1)+'''
        }
        "wide" {
'''+self.usd_triangle(width=3)+'''
        }
    }
}
'''
        self.write('variant.usda',asset)
        self.write('selected.usda','''#usda 1.0
def Xform "Chosen" (
    prepend references = @variant.usda@
    variants = {string shape = "wide"}
) {
    double3 xformOp:translate = (2, 0, 0)
    uniform token[] xformOpOrder = ["xformOp:translate"]
}
''')
        self.scene_qc('$modelname variant\n$UpAxis z assimp\n$body m selected.usda\n')
        self.assertEqual(sorted(tuple(round(x,4) for x in p) for p in self.scene_positions('variant')),[(2,0,0),(2,1,0),(5,0,0)])
        internal='#usda 1.0\ndef Xform "Original" {\n'+self.usd_triangle()+'}\n'+'''def Xform "Copy" (prepend references = </Original>
    instanceable = true) {
    double3 xformOp:translate = (8, 0, 0)
    uniform token[] xformOpOrder = ["xformOp:translate"]
}
'''
        self.write('internal.usda',internal)
        self.scene_qc('$modelname internal\n$UpAxis z assimp\n$body m internal.usda\n')
        self.assertEqual(sorted(tuple(round(x,4) for x in p) for p in self.scene_positions('internal')),[(0,0,0),(0,1,0),(1,0,0),(8,0,0),(8,1,0),(9,0,0)])

    def test_usd_incomplete_composition_fails_without_replacing_output(self):
        self.write('good.usda','#usda 1.0\n'+self.usd_triangle())
        self.scene_qc('$modelname guardedusd\n$body m good.usda\n');old=self.mdl('guardedusd')
        self.write('a.usda','#usda 1.0\n(defaultPrim = "A")\ndef Xform "A" (references = @b.usda@) {}\n')
        self.write('b.usda','#usda 1.0\n(defaultPrim = "B")\ndef Xform "B" (references = @a.usda@) {}\n')
        cases=[('references = @missing.usda@','referenced asset not found'),
               ('references = @good.usda@</Absent>','referenced prim not found'),
               ('references = @good.usda@','explicit prim path or defaultPrim'),
               ('references = @a.usda@','cyclic reference'),
               ('payload = @good.usda@','unsupported payload'),
               ('variants = {string absent = "value"}','selected variant set not found')]
        for metadata,expected in cases:
            self.write('bad.usda','#usda 1.0\ndef Xform "Bad" ('+metadata+') {}\n')
            output=self.scene_qc('$modelname guardedusd\n$body m bad.usda\n',success=False)
            self.assertIn(expected,output);self.assertEqual(self.mdl('guardedusd'),old)

    def test_usd_variant_set_authored_order_controls_strength(self):
        source='''#usda 1.0
def Xform "Variants" (
    variants = {
        string zFirst = "selected"
        string aSecond = "selected"
    }
    prepend variantSets = ["zFirst", "aSecond"]
) {
    variantSet "zFirst" = {
        "selected" {
'''+self.usd_triangle(width=2)+'''
        }
    }
    variantSet "aSecond" = {
        "selected" {
'''+self.usd_triangle(width=7)+'''
        }
    }
}
'''
        self.write('ordered-variants.usda',source)
        self.scene_qc('$modelname orderedusd\n$UpAxis z assimp\n$body m ordered-variants.usda\n')
        self.assertEqual(sorted(tuple(round(x,4) for x in p) for p in self.scene_positions('orderedusd')),[(0,0,0),(0,1,0),(2,0,0)])

    def test_usd_reference_active_and_extended_variant_selection(self):
        self.write('inactive.usda','#usda 1.0\n(defaultPrim = "Asset")\ndef Xform "Asset" (active = false) {\n'+self.usd_triangle()+'}\n')
        self.write('reactivate.usda','#usda 1.0\ndef Xform "Instance" (references = @inactive.usda@\nactive = true) {}\n'+self.usd_triangle('Sentinel',10))
        self.scene_qc('$modelname reactivateusd\n$UpAxis z assimp\n$body m reactivate.usda\n')
        self.assertEqual(len(self.scene_positions('reactivateusd')),6)
        self.write('inherited-inactive.usda','#usda 1.0\ndef Xform "Instance" (references = @inactive.usda@) {\n'+self.usd_triangle('Local',5)+'}\n'+self.usd_triangle('Sentinel',10))
        self.scene_qc('$modelname inheritedinactiveusd\n$UpAxis z assimp\n$body m inherited-inactive.usda\n')
        self.assertEqual(sorted(tuple(round(x,4) for x in p) for p in self.scene_positions('inheritedinactiveusd')),[(0,0,10),(0,1,10),(1,0,10)])
        self.test_usd_variant_selection_and_internal_reference_transform()
        self.write('extended.usda','''#usda 1.0
def Xform "Instance" (
 references = @variant.usda@
 variants = {string shape = "wide"}
 prepend variantSets = "shape"
) {
 variantSet "shape" = {
 "wide" {
'''+self.usd_triangle('Extra',10)+'''}
 }
}
''')
        self.scene_qc('$modelname extendedusd\n$UpAxis z assimp\n$body m extended.usda\n')
        self.assertEqual(sorted(tuple(round(x,4) for x in p) for p in self.scene_positions('extendedusd')),[(0,0,0),(0,0,10),(0,1,0),(0,1,10),(1,0,10),(3,0,0)])

    def test_usd_add_references_expand_undefined_prototypes_once(self):
        self.write('prototype.usda','#usda 1.0\nover "Prototype" {\n'+self.usd_triangle()+'}\n'+'''def Xform "Instance" (
 instanceable = true
 add references = </Prototype>
) {
 double3 xformOp:translate = (4, 0, 0)
 uniform token[] xformOpOrder = ["xformOp:translate"]
}
''')
        self.scene_qc('$modelname prototypeusd\n$UpAxis z assimp\n$body m prototype.usda\n')
        self.assertEqual(sorted(tuple(round(x,4) for x in p) for p in self.scene_positions('prototypeusd')),[(4,0,0),(4,1,0),(5,0,0)])
        # OpenUSD's Crate writer retains over/def/class specifiers. The bundled
        # Layer parser used to discard them and misdefine the hidden prototypes.
        fixture=Path(__file__).parent/'fixtures/usd/flattened-instances.usdc'
        (self.root/'flattened.usdc').write_bytes(fixture.read_bytes())
        self.scene_qc('$modelname binaryprototypeusd\n$UpAxis z assimp\n$body m flattened.usdc\n')
        self.assertEqual(sorted(tuple(round(x,4) for x in p) for p in self.scene_positions('binaryprototypeusd')),[(4,0,0),(4,1,0),(5,0,0)])

    def test_usd_unsupported_descendant_overrides_and_multiple_contributions_fail(self):
        self.write('plain.usda','#usda 1.0\n(defaultPrim = "Asset")\ndef Xform "Asset" {\n'+self.usd_triangle()+'}\n')
        self.scene_qc('$modelname usdguard\n$body m plain.usda\n');old=self.mdl('usdguard')
        self.write('child.usda','#usda 1.0\ndef Xform "Root" (references = @plain.usda@) {\nover "Triangle" (active = false) {}\n}\n')
        self.write('multiple.usda','''#usda 1.0
def Xform "Root" (
 references = @plain.usda@
 variants = {string shape = "selected"}
 prepend variantSets = "shape"
) {
 variantSet "shape" = {
 "selected" (references = @plain.usda@) {}
 }
}
''')
        for file,diagnostic in [('child.usda','overlapping referenced child opinions'),('multiple.usda','multiple contributed reference opinions')]:
            output=self.scene_qc('$modelname usdguard\n$body m '+file+'\n',success=False)
            self.assertIn(diagnostic,output);self.assertEqual(self.mdl('usdguard'),old)

    def test_usd_reference_reset_transform_stack_is_world_relative(self):
        self.write('reset-mesh.usda','#usda 1.0\n(defaultPrim = "Template")\ndef Xform "Template" {\n'+self.usd_triangle()+'}\n')
        self.write('reset.usda','''#usda 1.0
def Xform "Parent" {
    double3 xformOp:translate = (100, 0, 0)
    uniform token[] xformOpOrder = ["xformOp:translate"]
    def Xform "Reset" (references = @reset-mesh.usda@) {
        double3 xformOp:translate = (5, 0, 0)
        uniform token[] xformOpOrder = ["!resetXformStack!", "xformOp:translate"]
    }
}
''')
        self.scene_qc('$modelname resetusd\n$UpAxis z assimp\n$body m reset.usda\n')
        self.assertEqual(sorted(tuple(round(x,4) for x in p) for p in self.scene_positions('resetusd')),[(5,0,0),(5,1,0),(6,0,0)])

    def test_scene_cache_budget_and_session_lifetime_preserve_geometry(self):
        self.scene_fixture()
        body='$body a scene.gltf InNode MeshA\n$body b scene.gltf InNode MeshB\n'
        observations={}
        for budget in (256,0,1):
            self.scene_qc(f'$modelname cached\n$SceneCacheMiB {budget}\n'+body,'-perfjson',str(self.root/'cache.json'))
            stats=json.loads((self.root/'cache.json').read_text())['scene_cache'];observations[budget]=stats
            self.assertEqual(stats['budget_bytes'],budget*1024*1024)
            self.assertEqual(stats['estimated_retained_bytes'],0)
            self.assertLessEqual(stats['estimated_peak_retained_bytes'],stats['budget_bytes'])
            if budget:
                self.assertEqual(stats['misses'],1);self.assertEqual(stats['hits'],1)
                self.assertGreater(stats['estimated_peak_retained_bytes'],0)
            else:
                self.assertEqual(stats['misses'],2);self.assertEqual(stats['hits'],0);self.assertEqual(stats['bypasses'],2)
            geometry=(self.root/'models/cached.vvd').read_bytes()
            if budget==256:baseline=geometry
            else:self.assertEqual(geometry,baseline)
        # Shrinking after an import must evict the retained scene, and a later
        # compile starts with the default budget rather than previous QC state.
        self.scene_qc('$modelname shrink\n$body a scene.gltf InNode MeshA\n$SceneCacheMiB 0\n$body b scene.gltf InNode MeshB\n','-perfjson',str(self.root/'cache.json'))
        stats=json.loads((self.root/'cache.json').read_text())['scene_cache'];self.assertEqual(stats['evictions'],1)
        self.scene_qc('$modelname reset\n'+body,'-perfjson',str(self.root/'cache.json'))
        self.assertEqual(json.loads((self.root/'cache.json').read_text())['scene_cache']['budget_bytes'],256*1024*1024)
        for value in ('-1','16385','banana'):
            self.scene_qc('$modelname invalid\n$SceneCacheMiB '+value+'\n'+body,success=False)

    def test_adaptive_bake_reduces_linear_samples_and_retains_cubic_error(self):
        for interpolation in ('LINEAR','CUBICSPLINE'):
            self.scene_fixture(interpolation=interpolation)
            for backend in ('','$NoFastGltf\n'):
                self.scene_qc('$modelname adaptive\n'+backend+'$body m scene.gltf InNode MeshA BakeSceneAnimation Move SceneSampleRate 16 BakeSceneTolerance 0.02 0.1\n')
                clip=json.loads((self.root/'models/adaptive.vertexanim.json').read_text())['clips'][0]
                self.assertEqual((clip['times'][0],clip['times'][-1]),(0,1));check=clip['sample_checks'][0]
                self.assertEqual(check['scope'],'sampled_reference');self.assertEqual(check['source_frames'],17)
                self.assertTrue(check['reduction_applied']);self.assertLessEqual(check['max_position_error'],.020001)
                self.assertLessEqual(check['max_normal_error_degrees'],.100001)
                if interpolation=='LINEAR':self.assertEqual(clip['times'],[0,1])
                else:
                    self.assertGreater(len(clip['times']),2);self.assertLess(len(clip['times']),17)
                    # Independent authored Hermite translation x(t)=2+8t-4t^2.
                    for index in range(17):
                        t=index/16;times=clip['times'];hi=next((i for i,v in enumerate(times) if v>=t),len(times)-1);lo=max(0,hi-1)
                        a,b=times[lo],times[hi];u=(t-a)/(b-a) if b>a else 0
                        actual=2+8*t-4*t*t;linear=(1-u)*(2+8*a-4*a*a)+u*(2+8*b-4*b*b)
                        self.assertLessEqual(abs(actual-linear),.02001)

    def test_adaptive_bake_preserves_step_and_rejects_bad_tolerances(self):
        self.scene_fixture(interpolation='STEP')
        for backend in ('','$NoFastGltf\n'):
            qc='$modelname step\n'+backend+'$body m scene.gltf InNode MeshA BakeSceneAnimation Move SceneSampleRate 8 BakeSceneTolerance 100 180\n'
            output=self.scene_qc(qc);clip=json.loads((self.root/'models/step.vertexanim.json').read_text())['clips'][0]
            self.assertEqual(clip['times'],[i/8 for i in range(9)]);self.assertFalse(clip['sample_checks'][0]['reduction_applied'])
            self.assertIn('retaining every frame',output)
        old=self.mdl('step')
        for tolerance in ('-1 1','1 -1','1 181','NaN 1','1 inf','1'):
            self.scene_qc('$modelname step\n$body m scene.gltf BakeSceneAnimation Move BakeSceneTolerance '+tolerance+'\n',success=False)
            self.assertEqual(self.mdl('step'),old)
        self.assertIn('requires BakeSceneAnimation',self.scene_qc('$modelname step\n$body m scene.gltf BakeSceneTolerance .1 1\n',success=False))

    def test_adaptive_bake_bounds_normal_only_deformation(self):
        doc=json.loads(scene_bytes());blob=bytearray(base64.b64decode(doc['buffers'][0]['uri'].split(',')[1]))
        target=doc['meshes'][0]['primitives'][0]['targets'][0]
        for semantic,values in [('POSITION',[0,0,0]*3),('NORMAL',[.7,0,-.3]*3)]:
            view=doc['bufferViews'][doc['accessors'][target[semantic]]['bufferView']];struct.pack_into('<9f',blob,view['byteOffset'],*values)
        offset=len(blob);blob.extend(struct.pack('<2f',0,1));doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':8})
        doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,'componentType':5126,'count':2,'type':'SCALAR'})
        doc['animations'][0]['samplers'][0]['output']=len(doc['accessors'])-1;doc['animations'][0]['channels'][0]['target']['path']='weights'
        doc['buffers'][0]={'byteLength':len(blob),'uri':'data:application/octet-stream;base64,'+base64.b64encode(blob).decode()}
        self.write('normal.gltf',json.dumps(doc))
        for backend in ('','$NoFastGltf\n'):
            self.scene_qc('$modelname normalbake\n'+backend+'$body m normal.gltf InNode MeshA BakeSceneAnimation Move SceneSampleRate 16 BakeSceneTolerance 0 .1\n')
            clip=json.loads((self.root/'models/normalbake.vertexanim.json').read_text())['clips'][0];times=clip['times'];self.assertGreater(len(times),2)
            self.assertLess(len(times),17);self.assertLessEqual(clip['sample_checks'][0]['max_normal_error_degrees'],.100001)
            def normal(t):
                vector=(.7*t,0,1-.3*t);length=math.sqrt(sum(x*x for x in vector));return tuple(x/length for x in vector)
            for frame in range(17):
                t=frame/16;hi=next((i for i,v in enumerate(times) if v>=t),len(times)-1);lo=max(0,hi-1)
                a,b=times[lo],times[hi];u=(t-a)/(b-a) if b>a else 0
                interpolated=tuple((1-u)*x+u*y for x,y in zip(normal(a),normal(b)));length=math.sqrt(sum(x*x for x in interpolated))
                cosine=sum(x*y/length for x,y in zip(interpolated,normal(t)))
                self.assertLessEqual(math.degrees(math.acos(min(1,max(-1,cosine)))),.10001)

    def test_scene_cache_evicts_lru_within_budget(self):
        doc=json.loads(scene_bytes())
        for index in range(500):
            doc['nodes'][0]['children'].append(len(doc['nodes']));doc['nodes'].append({'name':f'empty_{index}'})
        self.write('first.gltf',json.dumps(doc));self.write('second.gltf',json.dumps(doc))
        qc='$modelname lru\n$SceneCacheMiB 1\n'+''.join(f'$body body{index} {name}.gltf InNode MeshA\n' for index,name in enumerate(('first','second','first')))
        self.scene_qc(qc,'-perfjson',str(self.root/'lru.json'))
        stats=json.loads((self.root/'lru.json').read_text())['scene_cache']
        self.assertEqual(stats['bypasses'],0);self.assertEqual(stats['misses'],3);self.assertEqual(stats['hits'],0);self.assertEqual(stats['evictions'],2)
        self.assertLessEqual(stats['estimated_peak_retained_bytes'],1024*1024);self.assertEqual(stats['estimated_retained_bytes'],0)

    def test_scene_cache_shares_geometry_across_sample_rates(self):
        # The animation-only reader must retain the geometry reader's generated
        # names, including the differing native/Assimp unnamed-node conventions.
        for unnamed in (False,True):
            doc=json.loads(scene_bytes())
            if unnamed:doc['nodes'][1].pop('name')
            self.write('scene.gltf',json.dumps(doc))
            for backend in ('','$NoFastGltf\n'):
                previous=None
                for budget in (0,256):
                    qc=f'$modelname multirate\n$SceneCacheMiB {budget}\n'+backend+'$animationcullmethod none\n$body m scene.gltf\n'
                    for rate in (15,30,60):qc+=f'$animation a{rate} scene.gltf Pick Move SampleRate {rate}\n$sequence s{rate} a{rate}\n'
                    self.scene_qc(qc,'-perfjson',str(self.root/'cache.json'))
                    stats=json.loads((self.root/'cache.json').read_text())['scene_cache']
                    self.assertEqual(stats['estimated_retained_bytes'],0)
                    if budget:
                        self.assertEqual(stats['geometry_imports'],1);self.assertEqual(stats['geometry_reuses'],2)
                        self.assertEqual(stats['peak_entries'],3)
                    else:self.assertEqual(stats['geometry_reuses'],0)
                    outputs={p.name:p.read_bytes() for p in (self.root/'models').glob('multirate.*')}
                    if previous is not None:self.assertEqual(outputs,previous)
                    previous=outputs

    def test_scene_cache_counts_shared_geometry_once_and_shrinks(self):
        doc=json.loads(scene_bytes())
        for index in range(500):
            doc['nodes'][0]['children'].append(len(doc['nodes']));doc['nodes'].append({'name':f'empty_{index}'})
        self.write('scene.gltf',json.dumps(doc))
        qc='$modelname shared\n$SceneCacheMiB 1\n$body a scene.gltf InNode MeshA\n'
        qc+='$body b scene.gltf InNode MeshB SceneSampleRate 60\n'
        self.scene_qc(qc,'-perfjson',str(self.root/'cache.json'))
        stats=json.loads((self.root/'cache.json').read_text())['scene_cache']
        self.assertEqual(stats['geometry_imports'],1);self.assertEqual(stats['geometry_reuses'],1)
        self.assertEqual(stats['evictions'],0);self.assertEqual(stats['peak_entries'],2)
        self.assertLessEqual(stats['estimated_peak_retained_bytes'],1024*1024)
        self.scene_qc(qc+'$SceneCacheMiB 0\n$body c scene.gltf InNode MeshB SceneSampleRate 120\n','-perfjson',str(self.root/'cache.json'))
        stats=json.loads((self.root/'cache.json').read_text())['scene_cache']
        self.assertEqual(stats['evictions'],2);self.assertEqual(stats['bypasses'],1)
        self.assertEqual(stats['estimated_retained_bytes'],0)

    def test_scene_cache_resamples_authoritative_compressed_animation(self):
        doc=json.loads((Path(__file__).parent/'fixtures/meshopt-triangles.gltf').read_text())
        blob=bytearray(base64.b64decode(doc['buffers'][0]['uri'].split(',')[1]))
        # The required compressed accessor is authoritative. Deliberately give
        # its uncompressed fallback different values, so skipping decode is visible.
        struct.pack_into('<6f',blob,152,100,0,0,200,0,0)
        doc['buffers'][0]['uri']='data:application/octet-stream;base64,'+base64.b64encode(blob).decode()
        self.write('compressed.gltf',json.dumps(doc))
        previous=None
        for budget in (0,256):
            qc=f'$modelname compressed\n$SceneCacheMiB {budget}\n$animationcullmethod none\n$UpAxis z gltf\n$body m compressed.gltf InNode MeshA\n'
            for rate in (15,60):qc+=f'$animation a{rate} compressed.gltf Pick Move SampleRate {rate}\n$sequence s{rate} a{rate}\n'
            self.scene_qc(qc,'-perfjson',str(self.root/'cache.json'))
            for rate in (15,60):
                frames=self.scene_bone_animation('compressed',f'a{rate}','MeshA')
                self.assertEqual(len(frames),rate+1)
                self.assertAlmostEqual(frames[-1][0],6,delta=.005)
            outputs={p.name:p.read_bytes() for p in (self.root/'models').glob('compressed.*')}
            if previous is not None:self.assertEqual(outputs,previous)
            previous=outputs

    def source_timing(self,name):
        data=self.mdl(name);index=struct.unpack_from('<i',data,184)[0]
        return struct.unpack_from('<f',data,index+8)[0],struct.unpack_from('<i',data,index+16)[0]

    def test_smd_all_numeric_records_reject_corruption_and_preserve_output(self):
        base=(self.root/'mesh.smd').read_text();self.scene_qc('$modelname guarded\n$body m mesh.smd\n');before=self.mdl('guarded')
        pairs=[('time 0','time'),('time 0','time OOPS'),('time 0','time 0garbage'),('time 0','time -1'),
               ('0 0 0 0 0 0 0\n','0 0 0 0 0 0 0oops\n'),('"root" -1','"root" -1oops'),('version 1','version 1oops'),
               ('1 "unused_child"','2147483647 "unused_child"'),('0 0 0 0 0 0 0\n','0 0 0 0 0 0 0 trailing\n'),('time 0','time 0\ntime 2147483647')]
        for old,new in pairs:
            with self.subTest(new=new):
                self.write('bad.smd',base.replace(old,new));output=self.scene_qc('$modelname guarded\n$body m bad.smd\n',success=False)
                self.assertRegex(output,r'bad\.smd:\d+:');self.assertEqual(self.mdl('guarded'),before)
        self.write('comments.smd',base.replace('time 0','time 0 // bind').replace('"unused_child" 0','"unused_child" 0 // child'))
        self.scene_qc('$modelname comments\n$body m comments.smd\n');self.assertEqual(self.mdl_bones('comments'),self.mdl_bones('guarded'))

    def test_vta_numeric_records_are_strict(self):
        base='version 1\nvertexanimation\ntime 0 # basis\n0 0 0 0 0 0 1\n1 1 0 0 0 0 1\n2 0 1 0 0 0 1\ntime 1\n0 0 0 1 0 0 1\nend\n'
        qc='$modelname face\n$model m mesh.smd {\nflexfile face.vta {\ndefaultflex frame 0\nflex smile frame 1\n}\nflexcontroller test range 0 1 strength\n%smile = strength\n}\n'
        self.write('face.vta',base);self.scene_qc(qc);before=self.mdl('face')
        for old,new in [('version 1','version 1oops'),('time 1','time 1garbage'),('time 1','time OOPS'),('time 1','time -1'),('0 0 0 1 0 0 1','0 0 0 1 0 0 1oops'),('0 0 0 0 0 0 1','2147483647 0 0 0 0 0 1')]:
            with self.subTest(new=new):
                self.write('face.vta',base.replace(old,new));output=self.scene_qc(qc,success=False)
                self.assertRegex(output,r'face\.vta:\d+:');self.assertEqual(self.mdl('face'),before)

    def test_dmx_clip_names_follow_case_insensitive_selection(self):
        qc='$modelname clips\n$body m mesh.smd\n$origin 0 0 0 -90\n$animationcullmethod none\n$sequence first motion.dmx blockname Walk\n$sequence second motion.dmx blockname Run\n'
        self.write('motion.dmx',clip_collision('Run'));self.scene_qc(qc);before=self.mdl('clips')
        self.assertAlmostEqual(math.dist(self.animation_poses('clips','first')[0][:3],(0,0,0)),1,places=2);self.assertAlmostEqual(math.dist(self.animation_poses('clips','second')[0][:3],(0,0,0)),10,places=2)
        for name in ('walk','WALK','bindpose'):
            self.write('motion.dmx',clip_collision(name));output=self.scene_qc(qc,success=False)
            self.assertIn('duplicate or reserved animation name',output);self.assertEqual(self.mdl('clips'),before)

    def test_scene_clip_names_follow_selection_namespace_on_both_gltf_backends(self):
        doc=json.loads(scene_bytes());doc['animations'][0]['name']='Walk'
        second=copy.deepcopy(doc['animations'][0]);second['name']='Run';doc['animations'].append(second)
        # Two genuinely different motions, rather than two aliases of one sampler.
        blob=bytearray(base64.b64decode(doc['buffers'][0]['uri'].split(',')[1]));offset=len(blob)
        blob.extend(struct.pack('<6f',20,0,0,60,0,0))
        doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':24})
        doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,'componentType':5126,'count':2,'type':'VEC3'})
        second['samplers'][0]['output']=len(doc['accessors'])-1
        doc['buffers'][0]={'byteLength':len(blob),'uri':'data:application/octet-stream;base64,'+base64.b64encode(blob).decode()}
        for backend in ('','$NoFastGltf\n'):
            qc='$modelname clips\n'+backend+'$body m source.gltf\n$animationcullmethod none\n$animation a source.gltf Pick Walk SampleRate 2\n$animation b source.gltf Pick Run SampleRate 2\n$sequence first a\n$sequence second b\n'
            self.write('source.gltf',json.dumps(doc));self.scene_qc(qc);before=self.mdl('clips')
            for first,last in [('Walk','walk'),('Walk','Walk'),('BindPose','Run'),('bindpose','Run'),('','animation_0')]:
                bad=copy.deepcopy(doc);bad['animations'][0]['name']=first;bad['animations'][1]['name']=last
                self.write('source.gltf',json.dumps(bad));output=self.scene_qc(qc,success=False)
                self.assertIn('duplicate or reserved animation name',output);self.assertIn('source.gltf',output)
                self.assertEqual(self.mdl('clips'),before)

    def test_fbx_clip_names_follow_selection_namespace_on_both_backends(self):
        original=fbx_bind_fixture()
        for backend in ('','$fbxcompatibility neko\n'):
            qc='$modelname clips\n'+backend+'$body m source.fbx\n$animation a source.fbx Pick Walk SampleRate 2\n$sequence first a\n'
            self.write('source.fbx',original);self.scene_qc(qc);before=self.mdl('clips')
            for name in ('walk','Walk','BindPose','bindpose'):
                self.write('source.fbx',original.replace('AnimStack::Run','AnimStack::'+name))
                output=self.scene_qc(qc,success=False)
                self.assertIn('duplicate or reserved animation name',output);self.assertIn('source.fbx',output)
                self.assertEqual(self.mdl('clips'),before)

    def test_source_bone_names_reject_case_aliases_before_global_merge(self):
        original_smd=(self.root/'mesh.smd').read_text()
        for kind,good,bad,backends in [
            ('smd',original_smd,original_smd.replace('unused_child','ROOT'),['']),
            ('fbx',fbx_bind_fixture(),fbx_bind_fixture().replace('Model::Tip','Model::root'),['','$fbxcompatibility neko\n']),
            ('dmx',cloth_dmx(),cloth_dmx().replace('"flap"','"ROOT"'),[''])]:
            for backend in backends:
                name='bones.'+kind;qc='$modelname guarded\n'+backend+'$body m '+name+'\n'
                self.write(name,good);self.scene_qc(qc);before=self.mdl('guarded')
                self.write(name,bad);output=self.scene_qc(qc,success=False)
                self.assertIn('ambiguous source bone name',output);self.assertEqual(self.mdl('guarded'),before)
        for backend in ('','$NoFastGltf\n'):
            doc=json.loads(scene_bytes());doc['nodes'][1]['name']='Hand';doc['nodes'][2]['name']='Other'
            qc='$modelname guarded\n'+backend+'$body m bones.gltf\n'
            self.write('bones.gltf',json.dumps(doc));self.scene_qc(qc);before=self.mdl('guarded')
            doc['nodes'][2]['name']='hand';self.write('bones.gltf',json.dumps(doc))
            output=self.scene_qc(qc,success=False);self.assertIn('ambiguous source bone name',output)
            self.assertEqual(self.mdl('guarded'),before)
        # Names intentionally shared across files must continue to map to one rig.
        self.write('other.smd',original_smd)
        self.scene_qc('$modelname shared\n$body first mesh.smd\n$body second other.smd\n$sequence idle other.smd\n')
        self.assertEqual(len(self.mdl_bones('shared')),1)

    def test_dmx_declared_skinning_rejects_corrupt_streams_and_unmapped_joints(self):
        original=cloth_dmx();qc='$modelname skinned\n$body m skin.dmx\n'
        self.write('skin.dmx',original);self.scene_qc(qc);before=self.mdl('skinned');bones=self.mdl_bones('skinned')
        def stream(text,name,kind,values):
            return re.sub(r'"'+name+'" "'+kind+r'_array" \[[^\]]*\]',
                          Document().array(name,kind,values),text)
        bad=[original.replace('"jointCount" "int" "1"','"jointCount" "int" "-1"'),
             original.replace('"jointCount" "int" "1"','"jointCount" "float" "1"'),
             original.replace('"jointCount" "int" "1"','"jointCount" "int" "0"'),
             original.replace('"jointWeights"','"missingWeights"'),
             original.replace('"jointIndices"','"missingIndices"'),
             stream(original,'jointWeights','float',[1]*5),
             stream(original,'jointIndices','int',[0]*7),
             stream(original,'jointIndices','int',[0,0,99,1,1,1]),
             stream(original,'jointIndices','int',[0,0,-1,1,1,1]),
             stream(original,'jointWeights','float',[1,1,-.1,1,1,1]),
             stream(original,'jointWeights','float',[1,1,0,1,1,1]),
             original.replace('"children" "element_array" [ "element" "cc100000-0000-0000-0000-000000000008" ]','"children" "element_array" []')]
        for text in bad:
            self.write('skin.dmx',text);output=self.scene_qc(qc,success=False)
            self.assertIn('DMX skinning',output);self.assertEqual(self.mdl('skinned'),before)
        # Padding with zero weight may retain an exporter sentinel index.
        padded=original.replace('"jointCount" "int" "1"','"jointCount" "int" "2"')
        padded=stream(padded,'jointWeights','float',[1,0]*6)
        padded=stream(padded,'jointIndices','int',[v for bone in [0,0,1,1,1,1] for v in (bone,-1)])
        self.write('skin.dmx',padded);self.scene_qc(qc)
        self.assertEqual(self.mdl_bones('skinned'),bones)
        huge=stream(padded,'jointWeights','float',[3e38,3e38]*6)
        huge=stream(huge,'jointIndices','int',[0,1]*6)
        self.write('skin.dmx',huge);self.scene_qc(qc) # normalization cannot overflow to zero/NaN
        vvd=(self.root/'models/skinned.vvd').read_bytes();start=struct.unpack_from('<i',vvd,56)[0]
        self.assertEqual(struct.unpack_from('<3f',vvd,start),(.5,.5,0))
        # Explicitly unskinned geometry remains supported.
        unskinned=re.sub(r'"jointCount" "int" "1"','"jointCount" "int" "0"',original)
        for name,kind in [('jointWeights','float'),('jointIndices','int')]:unskinned=stream(unskinned,name,kind,[])
        self.write('skin.dmx',unskinned);self.scene_qc(qc)

    def test_import_dependencies_include_external_buffers_images_and_material_libraries(self):
        doc=json.loads(scene_bytes());blob=base64.b64decode(doc['buffers'][0]['uri'].split(',')[1])
        (self.root/'geometry buffer.bin').write_bytes(blob);doc['buffers'][0]['uri']='geometry%20buffer.bin'
        (self.root/'surface texture.png').write_bytes(b'not-decoded-by-geometry-import')
        doc['images']=[{'uri':'surface%20texture.png'}]
        self.write('source.gltf',json.dumps(doc))
        for backend in ('','$NoFastGltf\n'):
            output=self.scene_qc('$modelname deps\n'+backend+'$body m source.gltf\n','-dumpdependencies')
            self.assertIn('geometry buffer.bin',output);self.assertIn('surface texture.png',output)
        self.write('surface.mtl','newmtl Original\nKd 1 1 1\n')
        self.write('source.obj','mtllib surface.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl Original\nf 1 2 3\n')
        output=self.scene_qc('$modelname deps\n$body m source.obj\n','-dumpdependencies')
        self.assertIn('surface.mtl',output)

    def test_dmx_skeleton_and_mesh_dag_cycles_and_depth_are_diagnostic(self):
        for mesh in (False,True):
            for mode in ('valid','cycle','depth','duplicate'):
                with self.subTest(mesh=mesh,mode=mode):
                    d=Document();d.element(1,'DmElement','document',f'"skeleton" {d.ref(2)} "model" {d.ref(1000 if mesh else 2)}')
                    d.element(2,'DmeModel','skeleton',d.elements('children',[3]))
                    d.element(3,'DmeJoint','root',f'"transform" {d.ref(4)} '+d.elements('children',[] if mesh else [3] if mode=='cycle' else [10,10] if mode=='duplicate' else [10]))
                    d.element(4,'DmeTransform','root','"position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1"')
                    if mesh:d.element(1000,'DmeModel','mesh containers',d.elements('children',[10,10] if mode=='duplicate' else [10]))
                    count=257 if mode=='depth' else 3
                    for i in range(count):d.element(10+i,'DmeDag','container'+str(i),d.elements('children',[10+i+1] if i+1<count else [10] if mode=='cycle' else []))
                    self.write('graph.dmx',d.text());output=self.scene_qc('$modelname graph\n$body m graph.dmx\n$sequence idle mesh.smd\n',success=mode=='valid')
                    if mode!='valid':self.assertIn('DMX DAG '+('multiple parents' if mode=='duplicate' else mode),output)

    def test_native_fbx_scale_animation_is_not_silently_discarded(self):
        qc='$modelname scaling\n$body m source.fbx\n$animationcullmethod none\n$animation move source.fbx Pick Walk SampleRate 2\n$sequence idle move\n'
        self.write('source.fbx',animated_scale_fbx(False));self.scene_qc(qc);before=self.mdl('scaling');self.write('source.fbx',animated_scale_fbx())
        for backend in ('','$fbxcompatibility neko\n'):
            output=self.scene_qc(backend+qc,success=False);self.assertIn('scaling',output);self.assertIn('bake',output);self.assertEqual(self.mdl('scaling'),before)

    def test_native_fbx_duration_rejected_before_integer_conversion(self):
        qc='$modelname duration\n$body m source.fbx\n';self.write('source.fbx',fbx_bind_fixture());self.scene_qc(qc);before=self.mdl('duration')
        for seconds in (1000,100000000):
            self.write('source.fbx',fbx_bind_fixture().replace('46186158000',str(46186158000*seconds)));output=self.scene_qc(qc,success=False)
            self.assertIn('exceeds frame limit',output);self.assertEqual(self.mdl('duration'),before)

    def test_imported_animation_default_playback_preserves_source_timing(self):
        for fps in (24,30,60):
            self.write('timing.fbx',fbx_bind_fixture(fps=fps));self.scene_qc('$modelname timing\n$body m timing.fbx\n$animationcullmethod none\n$animation move timing.fbx Pick Walk\n$sequence idle move\n')
            self.assertEqual(self.source_timing('timing'),(fps,fps+1))
        self.scene_fixture()
        for backend in ('','$NoFastGltf\n'):
            self.scene_qc('$modelname timing\n'+backend+'$body m scene.gltf\n$animationcullmethod none\n$animation move scene.gltf Pick Move SampleRate 4\n$sequence idle move\n');self.assertEqual(self.source_timing('timing'),(4,5))
        self.write('timing.dae',collada_curve_fixture('LINEAR'));self.scene_qc('$modelname timing\n$body m timing.dae\n$animationcullmethod none\n$animation move timing.dae Pick Move SampleRate 2\n$sequence idle move\n');self.assertEqual(self.source_timing('timing'),(2,3))
        self.write('timing.dmx',log_fixture(values=[(0,0,0),(1,0,0)],fps=4));self.scene_qc('$modelname timing\n$sequence idle timing.dmx\n');self.assertEqual(self.source_timing('timing'),(4,5))

    def test_authored_playback_overrides_survive_source_fps_inheritance(self):
        self.write('timing.fbx',fbx_bind_fixture(fps=60))
        for prefix,option,expected in [('', 'fps 15',(15,61)),('$defaultfps 12\n','',(12,13)),('$FPS 12\n','SampleRate 4',(12,5)),('', 'SampleRate 4 fps 10',(10,5))]:
            self.scene_qc('$modelname timing\n'+prefix+'$body m timing.fbx\n$animationcullmethod none\n$animation move timing.fbx Pick Walk '+option+'\n$sequence idle move\n');self.assertEqual(self.source_timing('timing'),expected)
        self.scene_qc('$modelname timing\n$sequence idle timing.fbx blockname Walk fps 20\n');self.assertEqual(self.source_timing('timing'),(20,61))
        self.scene_qc('$modelname timing\n$sequence idle mesh.smd\n');self.assertEqual(self.source_timing('timing'),(30,1))

    def test_resource_conditions_apply_platform_negation_and_boolean_operators(self):
        win=os.name=='nt'
        cases=[('[$WIN32]',win),('[!$WIN32]',not win),('[$LINUX]',not win),('[!$LINUX]',win),('[ !$WIN32 ]',not win),('[!($WIN32 || $LINUX)]',False),('[$WIN32 || $LINUX]',True),('[$WIN32 && !$LINUX]',win),('[$X360]',False)]
        for i,(condition,enabled) in enumerate(cases):
            self.write('first/pick.qci',f'$modelname first{i}\n');self.write('fallback/pick.qci',f'$modelname fallback{i}\n')
            self.write('gameinfo.txt','GameInfo { FileSystem { SearchPaths { Game "|gameinfo_path|first" '+condition+' Game "|gameinfo_path|fallback" } } }')
            self.scene_qc('$include pick.qci\n$body m mesh.smd\n')
            self.assertTrue((self.root/f'models/{"first" if enabled else "fallback"}{i}.mdl').exists());self.assertFalse((self.root/f'models/{"fallback" if enabled else "first"}{i}.mdl').exists())
        for condition in ('[!$WIN32','[$WIN32 && ]','[$WIN32 junk]'):
            self.write('gameinfo.txt','GameInfo { FileSystem { SearchPaths { Game "first" '+condition+' } } }')
            self.assertIn('KeyValues condition',self.scene_qc('$modelname malformed\n$body m mesh.smd\n',success=False))
