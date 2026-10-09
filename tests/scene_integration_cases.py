"""Self-authored import contracts for the fixed five-compiler integration audit."""
import base64
import json
import struct
from pathlib import Path


def fbx_bind_fixture(fps=30, y_up=False, conflict=False):
    """Two joints, scene pose != bind, mesh pose != geometry bind, two takes."""
    def matrix(x=0):
        return ','.join(str(v) for v in (1,0,0,0,0,1,0,0,0,0,1,0,x,0,0,1))
    properties = lambda x: f'''Version: 232
        Properties70: {{
            P: "Lcl Translation", "Lcl Translation", "", "A", {x},0,0
            P: "Lcl Rotation", "Lcl Rotation", "", "A", 0,0,0
            P: "Lcl Scaling", "Lcl Scaling", "", "A", 1,1,1
        }}'''
    objects = [f'''Geometry: 1, "Geometry::Triangle", "Mesh" {{
        Vertices: *9 {{ a: 0,0,0,1,0,0,0,1,0 }}
        PolygonVertexIndex: *3 {{ a: 0,1,-3 }}
    }}''', f'Model: 2, "Model::Mesh", "Mesh" {{ {properties(20)} }}',
        f'Model: 3, "Model::Root", "LimbNode" {{ {properties(10)} }}',
        f'Model: 4, "Model::Tip", "LimbNode" {{ {properties(5)} }}',
        'Deformer: 10, "Deformer::Skin", "Skin" { Version: 101 }']
    links = ['C: "OO", 1,2', 'C: "OO", 2,0', 'C: "OO", 3,0',
             'C: "OO", 4,3', 'C: "OO", 10,1']
    for cluster, joint, bind, indices in ((11,3,2,'0,1'), (12,4,7,'2')):
        count = len(indices.split(','))
        objects.append(f'''Deformer: {cluster}, "Deformer::Cluster{cluster}", "Cluster" {{
            Version: 100
            Indexes: *{count} {{ a: {indices} }}
            Weights: *{count} {{ a: {','.join(['1']*count)} }}
            Transform: *16 {{ a: {matrix(-bind + (1 if conflict and cluster==12 else 0))} }}
            TransformLink: *16 {{ a: {matrix(bind)} }}
        }}''')
        links += [f'C: "OO", {cluster},10', f'C: "OO", {joint},{cluster}']
    for index, name, start, end in ((0,'Walk',10,14),(1,'Run',20,22)):
        stack, layer, curve_node, curve = (100+index*10+n for n in range(4))
        objects += [f'''AnimationStack: {stack}, "AnimStack::{name}", "" {{
            Properties70: {{
                P: "LocalStart", "KTime", "Time", "", 0
                P: "LocalStop", "KTime", "Time", "", 46186158000
                P: "ReferenceStart", "KTime", "Time", "", 0
                P: "ReferenceStop", "KTime", "Time", "", 46186158000
            }}
        }}''', f'AnimationLayer: {layer}, "AnimLayer::Base", "" {{ }}',
        f'''AnimationCurveNode: {curve_node}, "AnimCurveNode::T", "" {{
            Properties70: {{
                P: "d|X", "Number", "", "A", {start}
                P: "d|Y", "Number", "", "A", 0
                P: "d|Z", "Number", "", "A", 0
            }}
        }}''', f'''AnimationCurve: {curve}, "AnimCurve::X", "" {{
            Default: {start}
            KeyVer: 4008
            KeyTime: *2 {{ a: 0,46186158000 }}
            KeyValueFloat: *2 {{ a: {start},{end} }}
            KeyAttrFlags: *2 {{ a: 24836,24836 }}
            KeyAttrDataFloat: *8 {{ a: 0,0,0,0,0,0,0,0 }}
            KeyAttrRefCount: *2 {{ a: 1,1 }}
        }}''']
        links += [f'C: "OO", {layer},{stack}', f'C: "OO", {curve_node},{layer}',
                  f'C: "OP", {curve_node},3,"Lcl Translation"', f'C: "OP", {curve},{curve_node},"d|X"']
    return f'''; Self-authored bind-pose and animation regression.
FBXHeaderExtension: {{ FBXHeaderVersion: 1003
    FBXVersion: 7400
}}
GlobalSettings: {{ Version: 1000
    Properties70: {{
        P: "UpAxis", "int", "Integer", "", {1 if y_up else 2}
        P: "UpAxisSign", "int", "Integer", "", 1
        P: "FrontAxis", "int", "Integer", "", {2 if y_up else 1}
        P: "FrontAxisSign", "int", "Integer", "", {-1 if y_up else -1}
        P: "CoordAxis", "int", "Integer", "", 0
        P: "CoordAxisSign", "int", "Integer", "", 1
        P: "TimeMode", "enum", "", "", { {24:11,30:6,60:3}[fps] }
        P: "UnitScaleFactor", "double", "Number", "", 1
    }}
}}
Objects: {{
{chr(10).join(objects)}
}}
Connections: {{
{chr(10).join(links)}
}}
'''


def assbin_boundary_fixture(behaviour):
    """ASSBIN stores channel pre/post state; its v1 keys have no interpolation field."""
    pack = lambda fmt,*values: struct.pack('<'+fmt,*values)
    string = lambda text: pack('I',len(text.encode()))+text.encode()
    chunk = lambda kind,data: pack('II',kind,len(data))+data
    matrix = [1,0,0,9,0,1,0,0,0,0,1,0,0,0,0,1]
    node = chunk(0x123c,string('Boundary')+pack('16f',*matrix)+pack('4I',0,1,0,0))
    mesh = chunk(0x1237,pack('6I',4,3,1,0,0,3)+
                 pack('9f',0,0,0,1,0,0,0,1,0)+pack('9f',*([0,0,1]*3))+pack('4H',3,0,1,2))
    material = chunk(0x123d,pack('I',0))
    keys = b''.join(pack('d3f',t,x,0,0) for t,x in [(1,2),(2,4)])
    channel = chunk(0x1238,string('Boundary')+pack('5I',2,0,0,behaviour,behaviour)+keys)
    animation = chunk(0x123b,string('Move')+pack('ddI',3,1,1)+channel)
    scene = chunk(0x1239,pack('7I',0,1,1,1,0,0,0)+node+mesh+material+animation)
    header = b'ASSIMP.binary-dump.'.ljust(44,b'\0')+pack('4I2H',1,0,0,0,0,0)+bytes(448)
    return header+scene


def pmx_morph_fixture(cycle=False):
    pack = lambda fmt,*values: struct.pack('<'+fmt,*values)
    string = lambda text: pack('i',len(text.encode()))+text.encode()
    data = b'PMX '+pack('f',2.0)+bytes([8,1,0,1,1,1,1,1,1])
    data += string('PmxFixture')+string('PmxFixture')+string('self-authored')+string('')+pack('i',3)
    for i,p in enumerate(((0,0,0),(1,0,0),(0,1,0))):
        data += pack('8f',*p,0,0,-1,0,0)
        data += (bytes([0,0]) if i==0 else bytes([1,0,1])+pack('f',.25)) + pack('f',1)
    data += pack('i',3)+bytes([0,1,2])+pack('ii',0,1)
    data += string('Material')+string('Material')+pack('11f',1,1,1,1,0,0,0,0,0,0,0)
    data += bytes([0])+pack('5f',0,0,0,1,1)+bytes([255,255,0,1,0])+string('')+pack('i',3)
    data += pack('i',2)
    for name,parent,y in (('Root',255,0),('Tip',0,2)):
        data += string(name)+string(name)+pack('3f',0,y,0)+bytes([parent])+pack('iH3f',0,0,0,1,0)
    data += pack('i',2)
    data += string('Smile')+string('Smile')+bytes([3,1])+pack('i',1)+bytes([1])+pack('3f',0,0,-.5)
    data += string('HalfSmile')+string('HalfSmile')+bytes([3,0])+pack('i',1)+bytes([1 if cycle else 0])+pack('f',.5)
    return data+pack('4i',0,0,0,0)


def skin_instances_fixture(nonuniform=False):
    from scene_fixtures import skinned_scene_bytes
    doc=json.loads(skinned_scene_bytes());binary=bytearray(base64.b64decode(doc['buffers'][0]['uri'].split(',')[1]))
    def add(values,width):
        offset=len(binary);binary.extend(struct.pack('<'+'f'*len(values),*values))
        doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(values)*4})
        doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,'componentType':5126,'count':len(values)//width,'type':{3:'VEC3',4:'VEC4'}[width]})
        return len(doc['accessors'])-1
    translate=add([0,0,0,10,0,0],3)
    doc['nodes'][0]['children']=[1,3]
    doc['nodes'][1]['extensions']={'EXT_mesh_gpu_instancing':{'attributes':{'TRANSLATION':translate}}}
    if nonuniform:
        doc['nodes'][1]['extensions']['EXT_mesh_gpu_instancing']['attributes']['SCALE']=add([1,1,1,1,2,1],3)
    # Move the shared joint from 5 to 9, while the mesh node stays at x=100.
    doc['animations'][0]['channels'][0]['target']['node']=3
    values=doc['accessors'][doc['animations'][0]['samplers'][0]['output']]['bufferView'];offset=doc['bufferViews'][values]['byteOffset']
    struct.pack_into('<6f',binary,offset,5,0,0,9,0,0)
    doc['extensionsUsed']=doc['extensionsRequired']=['EXT_mesh_gpu_instancing']
    doc['buffers'][0]={'byteLength':len(binary),'uri':'data:application/octet-stream;base64,'+base64.b64encode(binary).decode()}
    return json.dumps(doc)


def collada_curve_fixture(mode):
    def source(name,kind,values,count,stride,params):
        array=f'{name}-array'
        return f'<source id="{name}"><{kind}_array id="{array}" count="{len(values.split())}">{values}</{kind}_array><technique_common><accessor source="#{array}" count="{count}" stride="{stride}">{params}</accessor></technique_common></source>'
    sources=source('time','float','0 1',2,1,'<param name="TIME" type="float"/>')
    sources+=source('value','float','2 6',2,1,'<param name="X" type="float"/>')
    sources+=source('mode','Name',f'{mode} {mode}',2,1,'<param name="INTERPOLATION" type="Name"/>')
    tangent='<param name="X" type="float"/><param name="Y" type="float"/>'
    sources+=source('intan','float','0 2 0.6666666667 6',2,2,tangent)
    sources+=source('outtan','float','0.3333333333 6 1 6',2,2,tangent)
    return f'''<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
<asset><created>2026-10-09T00:00:00Z</created><modified>2026-10-09T00:00:00Z</modified><up_axis>Z_UP</up_axis></asset>
<library_geometries><geometry id="Triangle"><mesh>
<source id="positions"><float_array id="positions-array" count="9">0 0 0 1 0 0 0 1 0</float_array><technique_common><accessor source="#positions-array" count="3" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
<vertices id="vertices"><input semantic="POSITION" source="#positions"/></vertices><triangles count="1"><input semantic="VERTEX" source="#vertices" offset="0"/><p>0 1 2</p></triangles>
</mesh></geometry></library_geometries>
<library_animations><animation id="Move" name="Move">{sources}
<sampler id="sampler"><input semantic="INPUT" source="#time"/><input semantic="OUTPUT" source="#value"/><input semantic="INTERPOLATION" source="#mode"/><input semantic="IN_TANGENT" source="#intan"/><input semantic="OUT_TANGENT" source="#outtan"/></sampler>
<channel source="#sampler" target="Moving/location.X"/>
</animation></library_animations>
<library_visual_scenes><visual_scene id="Scene"><node id="Moving" name="Moving"><translate sid="location">2 0 0</translate><instance_geometry url="#Triangle"/></node></visual_scene></library_visual_scenes>
<scene><instance_visual_scene url="#Scene"/></scene></COLLADA>
'''


class SceneIntegrationCases:
    def scene_positions(self,name):
        data=(self.root/f'models/{name}.vvd').read_bytes();count=struct.unpack_from('<i',data,16)[0];start=struct.unpack_from('<i',data,56)[0]
        return [struct.unpack_from('<3f',data,start+i*48+16) for i in range(count)]

    def test_fbx_true_bind_matrices_and_two_named_takes(self):
        self.write('bind.fbx',fbx_bind_fixture())
        self.scene_qc('$modelname bind\n$bonecullmethod none\n$body m bind.fbx InNode Mesh\n$animationcullmethod none\n$animation walk bind.fbx Pick Walk SampleRate 2\n$animation run bind.fbx Pick Run SampleRate 2\n$sequence WalkSeq walk\n$sequence RunSeq run\n')
        data,bones=self.csgo_bone_table('bind')
        self.assertAlmostEqual(struct.unpack_from('<f',data,bones['Root'][1]+32)[0],2,places=4)
        self.assertAlmostEqual(struct.unpack_from('<f',data,bones['Tip'][1]+32)[0],5,places=4)
        self.assertEqual(sorted(round(p[0],3) for p in self.scene_positions('bind')),[0,0,1])
        for clip,expected in [('walk',[10,12,14]),('run',[20,21,22])]:
            samples=self.scene_bone_animation('bind',clip,'Root')
            self.assertEqual(len(samples),len(expected))
            for sample,value in zip(samples,expected):self.assertAlmostEqual(sample[0],value,delta=.005)

    def test_fbx_conflicting_geometry_bind_is_diagnostic(self):
        self.write('conflict.fbx',fbx_bind_fixture(conflict=True))
        output=self.scene_qc('$modelname bad\n$body m conflict.fbx\n',success=False)
        self.assertIn('conflicting FBX geometry bind',output)

    def test_fbx_native_file_rates_and_explicit_sample_rate(self):
        for fps in (24,30,60):
            self.write(f'rate{fps}.fbx',fbx_bind_fixture(fps=fps))
            self.scene_qc(f'$modelname rate\n$body m rate{fps}.fbx\n$animationcullmethod none\n$animation move rate{fps}.fbx Pick Walk\n$sequence idle move\n')
            self.assertEqual(len(self.scene_bone_animation('rate','move','Root')),fps+1)
        self.scene_qc('$modelname rate\n$body m rate60.fbx\n$animationcullmethod none\n$animation move rate60.fbx Pick Run SampleRate 4\n$sequence idle move\n')
        self.assertEqual(len(self.scene_bone_animation('rate','move','Root')),5)

    def test_fbx_neko_backend_and_assimp_axis_policy(self):
        self.write('hierarchy.fbx',(Path(__file__).parent/'fixtures/hierarchy.fbx').read_text())
        sets=[]
        for axis in ('z','y'):
            self.scene_qc(f'$modelname policy\n$fbxcompatibility neko\n$UpAxis {axis} assimp\n$body m hierarchy.fbx InNode Mesh\n')
            sets.append(sorted(tuple(round(x,3) for x in p) for p in self.scene_positions('policy')))
        # Assimp first changes this Z-up FBX into its own Y-up scene.
        self.assertEqual(sets[0],[(12,4,-4),(12,4,-3),(14,4,-3)])
        self.assertEqual(sets[1],[(12,3,4),(12,4,4),(14,3,4)])
        for fps in (24,60):
            self.write(f'policy{fps}.fbx',fbx_bind_fixture(fps=fps))
            self.scene_qc(f'$modelname policy\n$fbxcompatibility neko\n$UpAxis z assimp\n$body m policy{fps}.fbx\n$animationcullmethod none\n$animation move policy{fps}.fbx Pick Walk\n$sequence idle move\n')
            self.assertEqual(len(self.scene_bone_animation('policy','move','Root')),31)

    def test_assimp_animation_pre_and_post_contract(self):
        expected={0:[9,9,2,3,4,9,9],1:[2,2,2,3,4,4,4],2:[0,1,2,3,4,5,6],3:[2,3,2,3,4,3,2]}
        for behaviour,positions in expected.items():
            (self.root/'boundary.assbin').write_bytes(assbin_boundary_fixture(behaviour))
            self.scene_qc('$modelname boundary\n$UpAxis z assimp\n$body m boundary.assbin\n$animationcullmethod none\n$animation move boundary.assbin Pick Move SampleRate 2\n$sequence idle move\n')
            samples=self.scene_bone_animation('boundary','move','Boundary')
            self.assertEqual(len(samples),len(positions))
            for sample,value in zip(samples,positions):self.assertAlmostEqual(sample[0],value,delta=.005)

    def test_collada_authored_step_linear_and_bezier_sampling(self):
        expected={'STEP':[2,2,2,2,6],'LINEAR':[2,3,4,5,6],'BEZIER':[2,4.3125,5.5,5.9375,6]}
        for mode,positions in expected.items():
            self.write('curve.dae',collada_curve_fixture(mode))
            self.scene_qc('$modelname curve\n$body m curve.dae\n$animationcullmethod none\n$animation move curve.dae Pick Move SampleRate 4\n$sequence idle move\n')
            samples=self.scene_bone_animation('curve','move','Moving');self.assertEqual(len(samples),len(positions))
            for sample,value in zip(samples,positions):self.assertAlmostEqual(sample[0],value,delta=.005)
        self.write('curve.dae',collada_curve_fixture('HERMITE'))
        output=self.scene_qc('$modelname invalid\n$body m curve.dae\n',success=False)
        self.assertIn('author-side animation baking',output)

    def test_pmx_skin_and_named_vertex_and_group_morph(self):
        (self.root/'fixture.pmx').write_bytes(pmx_morph_fixture())
        self.scene_qc('$modelname pmx\n$bonecullmethod none\n$body m fixture.pmx {\nflex Smile\nflex HalfSmile\nflexcontroller test range 0 1 strength\n%Smile = strength\n%HalfSmile = strength\n}\n')
        data,bones=self.csgo_bone_table('pmx');self.assertIn('Root',bones);self.assertIn('Tip',bones)
        count,table=struct.unpack_from('<2i',data,260)
        names=[]
        for i in range(count):
            at=table+i*4;start=at+struct.unpack_from('<i',data,at)[0];names.append(data[start:data.index(b'\0',start)].decode())
        self.assertIn('Smile',names);self.assertIn('HalfSmile',names)
        _,flex=self.first_mesh_flex('pmx');self.assertEqual(len(flex),1)
        self.assertEqual(len(self.scene_positions('pmx')),3)
        vvd=(self.root/'models/pmx.vvd').read_bytes();start=struct.unpack_from('<i',vvd,56)[0]
        self.assertIn(2,[vvd[start+i*48+15] for i in range(3)])

    def test_pmx_cyclic_group_morph_is_rejected(self):
        (self.root/'cycle.pmx').write_bytes(pmx_morph_fixture(cycle=True))
        output=self.scene_qc('$modelname cycle\n$body m cycle.pmx\n',success=False)
        self.assertIn('cyclic PMX group morph',output)

    def test_skinned_gpu_instances_preserve_geometry_morph_and_animation(self):
        self.write('instances.gltf',skin_instances_fixture())
        for backend in ('','$NoFastGltf\n'):
            self.scene_qc('$modelname instances\n'+backend+'$UpAxis z gltf\n$body m instances.gltf InNode MeshA {\nflex Smile\nflexcontroller test strength\n%Smile = strength\n}\n$animationcullmethod none\n$animation move instances.gltf Pick Move SampleRate 2\n$sequence idle move\n')
            self.assertEqual(sorted(round(p[0],3) for p in self.scene_positions('instances')),[-1,0,1,9,10,11])
            data,bones=self.csgo_bone_table('instances')
            for i,offset in ((0,0),(1,10)):
                name=f'MeshA_instance_{i}_Joint';self.assertIn(name,bones)
                samples=self.scene_bone_animation('instances','move',name)
                self.assertEqual(len(samples),3)
                for sample,value in zip(samples,[5+offset,7+offset,9+offset]):self.assertAlmostEqual(sample[0],value,delta=.005)
            _,flex=self.first_mesh_flex('instances');self.assertEqual(len(flex),6)

    def test_skinned_instance_nonuniform_scale_is_explicit(self):
        self.write('instances.gltf',skin_instances_fixture(nonuniform=True))
        output=self.scene_qc('$modelname instances\n$body m instances.gltf\n',success=False)
        self.assertIn('positive uniform scale',output)

    def test_meshopt_octahedral_quaternion_and_color_filters(self):
        self.write('filters.gltf',(Path(__file__).parent/'fixtures/meshopt-filters.gltf').read_text())
        self.scene_qc('$modelname filters\n$UpAxis z gltf\n$body m filters.gltf\n')
        data=(self.root/'models/filters.vvd').read_bytes();count=struct.unpack_from('<i',data,16)[0];start=struct.unpack_from('<i',data,56)[0]
        self.assertEqual(count,6)
        rows=[]
        for i in range(count):
            p=struct.unpack_from('<3f',data,start+i*48+16);n=struct.unpack_from('<3f',data,start+i*48+28);uv=struct.unpack_from('<2f',data,start+i*48+40)
            rows.append((tuple(round(x,3) for x in p),tuple(round(x,3) for x in n),tuple(round(x,3) for x in uv)))
        self.assertIn(((1,0,0),(1,0,0),(0,0)),rows)
        self.assertIn(((3,0,0),(0,1,0),(.502,.502)),rows)
        self.assertIn(((2,1,0),(0,0,-1),(1,1)),rows)
        self.assertIn(((13,0,0),(-1,0,0),(0,0)),rows)
        self.assertIn(((11,0,0),(0,-1,0),(.502,.502)),rows)
        self.assertIn(((12,-1,0),(0,0,-1),(1,1)),rows)

    def test_m3d_ascii_geometry_import(self):
        self.write('triangle.a3d','3dmodel 1\nTriangle\nCC0\nNewPageMergeMDL tests\nself-authored fixture\n\nVertex\n0 0 0 1\n1 0 0 1\n0 1 0 1\n\nMesh\n0 1 2\n\nEnd\n')
        self.scene_qc('$modelname m3d\n$UpAxis z assimp\n$body m triangle.a3d\n')
        self.assertEqual(sorted(tuple(round(v,4) for v in p) for p in self.scene_positions('m3d')),[(0,0,0),(0,1,0),(1,0,0)])

    def test_usda_mesh_and_hierarchy_transform(self):
        self.write('triangle.usda','''#usda 1.0
(
    upAxis = "Z"
)
def Xform "Group" {
    double3 xformOp:translate = (2, 3, 4)
    uniform token[] xformOpOrder = ["xformOp:translate"]
    def Mesh "Triangle" {
        int[] faceVertexCounts = [3]
        int[] faceVertexIndices = [0, 1, 2]
        point3f[] points = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        uniform token subdivisionScheme = "none"
    }
}
''')
        self.scene_qc('$modelname usd\n$UpAxis z assimp\n$body m triangle.usda\n')
        self.assertEqual(sorted(tuple(round(v,4) for v in p) for p in self.scene_positions('usd')),[(2,3,4),(2,4,4),(3,3,4)])
        authored=(self.root/'triangle.usda').read_text()
        self.write('triangle.usda',authored+authored[authored.index('def Xform'):].replace('"Group"','"Second"').replace('"Triangle"','"SecondTriangle"').replace('(2, 3, 4)','(12, 3, 4)'))
        self.scene_qc('$modelname usd_roots\n$UpAxis z assimp\n$body m triangle.usda\n')
        self.assertEqual(sorted(tuple(round(v,4) for v in p) for p in self.scene_positions('usd_roots')),[(2,3,4),(2,4,4),(3,3,4),(12,3,4),(12,4,4),(13,3,4)])
        self.write('triangle.usda','#usda 1.0\n')
        failed=self.scene_qc('$modelname usd_empty\n$body m triangle.usda\n',success=False)
        self.assertNotIn('FAILED: crashed',failed)

    def test_separate_vrml_converter_and_compile_bridge(self):
        import __main__,subprocess,sys
        compiler=Path(__main__.COMPILER)
        converter=compiler.with_name('NewPageVRMLtoX3D'+compiler.suffix)
        script=Path(__file__).resolve().parents[1]/'tools/vrml_import.py'
        self.write('triangle.wrl','''#VRML V2.0 utf8
Transform {
  translation 2 3 4
  children [ Shape { geometry IndexedFaceSet {
    coord Coordinate { point [ 0 0 0, 1 0 0, 0 1 0 ] }
    coordIndex [ 0 1 2 -1 ]
  } } ]
}
''')
        command=[sys.executable,str(script),str(self.root/'triangle.wrl'),'--output',str(self.root/'converted.x3d'),
                 '--converter',str(converter),'--compiler',str(compiler),'--game',str(self.root),'--modelname','vrml','--upaxis','z']
        result=subprocess.run(command,capture_output=True,text=True,errors='replace')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(sorted(tuple(round(v,4) for v in p) for p in self.scene_positions('vrml')),[(2,3,4),(2,4,4),(3,3,4)])
        previous=(self.root/'converted.x3d').read_bytes()
        self.write('invalid.wrl','#VRML V2.0 utf8\nShape { geometry IndexedFaceSet {\n')
        failed=subprocess.run([str(converter),str(self.root/'invalid.wrl'),str(self.root/'converted.x3d')],capture_output=True,text=True)
        self.assertNotEqual(failed.returncode,0);self.assertEqual((self.root/'converted.x3d').read_bytes(),previous)
        unicode_source=self.root/'输入 场景.wrl';unicode_output=self.root/'输出 场景.x3d'
        unicode_source.write_bytes((self.root/'triangle.wrl').read_bytes())
        converted=subprocess.run([str(converter),str(unicode_source),str(unicode_output)],capture_output=True)
        self.assertEqual(converted.returncode,0,repr(converted.stdout+converted.stderr))
        self.assertEqual(unicode_output.read_bytes(),previous)
        same=subprocess.run([str(converter),str(unicode_source),str(unicode_source)],capture_output=True)
        self.assertNotEqual(same.returncode,0)
        self.assertEqual(unicode_source.read_bytes(),(self.root/'triangle.wrl').read_bytes())
        self.assertEqual(list(self.root.glob('.npmdl-vrml-*')),[])
