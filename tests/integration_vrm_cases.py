import copy
import json
from pathlib import Path
import struct
import subprocess
import sys
from scene_fixtures import skinned_scene_bytes

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import vrm_runtime


class IntegrationVrmCases:
    def vrm_fixture(self,version=1):
        doc=json.loads(skinned_scene_bytes());doc['animations']=[]
        doc['nodes'][3]['children']=[4]
        doc['nodes'].append(dict(name='HairTip',translation=[0,1,0]))
        if version==1:
            doc['extensions']={'VRMC_vrm':{'specVersion':'1.0','expressions':{'preset':{
                'happy':{'morphTargetBinds':[dict(node=1,index=0,weight=.8)],'overrideBlink':'blend'},
                'blink':{'morphTargetBinds':[dict(node=2,index=0,weight=1)],'isBinary':True}}}},
                'VRMC_springBone':{'colliders':[dict(node=0,shape={'capsule':dict(offset=[0,0,0],tail=[0,1,0],radius=.1)})],
                    'colliderGroups':[dict(colliders=[0])],
                    'springs':[dict(center=0,joints=[dict(node=3,stiffness=1,gravityPower=.2,gravityDir=[0,-1,0],dragForce=.3,hitRadius=.05),dict(node=4)],colliderGroups=[0])]}}
        else:
            doc['extensions']={'VRM':{'specVersion':'0.0','blendShapeMaster':{'blendShapeGroups':[
                dict(name='Happy',presetName='joy',isBinary=False,binds=[dict(mesh=0,index=0,weight=75)])]},
                'secondaryAnimation':{'boneGroups':[dict(bones=[3],center=0,stiffiness=2,gravityPower=.2)],
                    'colliderGroups':[dict(node=0,colliders=[dict(offset=dict(x=1,y=0,z=0),radius=.2)])]}}}
        return doc

    def test_vrm0_and_vrm1_expression_spring_compile_and_baked_clip(self):
        compiler=sys.modules[self.scene_qc.__module__].COMPILER
        for version in (0,1):
            with self.subTest(version=version):
                doc=self.vrm_fixture(version);source=self.write('input.gltf',json.dumps(doc))
                expression='happy' if version else 'joy'
                clip=self.write('clip.json',json.dumps([dict(time=0,weights={expression:0}),dict(time=1,weights={expression:1})]))
                out=self.root/('vrm'+str(version));game=self.root/'game'
                result=subprocess.run([sys.executable,vrm_runtime.__file__,str(source),'--out',str(out),
                    '--compiler',compiler,'--game',str(game),'--scale','1','--modelname','integration/avatar'+str(version),
                    '--expression-clip',str(clip),'--fps','2'],capture_output=True,text=True,errors='replace')
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                model=game/f'models/integration/avatar{version}.mdl'
                from validate_outputs import validate
                validate(model);data=model.read_bytes()
                meta=json.loads(model.with_suffix('.vrm.json').read_text())
                self.assertEqual(meta['version'],'1.0' if version else '0.x')
                self.assertEqual(len(meta['clip']['samples']),3)
                self.assertEqual(meta['clip']['samples'][1][expression],.5)
                self.assertEqual(meta['springs'][0]['joints'][0]['tail'],[0,1,0])
                self.assertEqual(meta['springs'][0]['joints'][0]['gravity_dir'],[0,0,-1])
                self.assertIn(b'vrm_node_3\0',data)
                for e in meta['expressions'].values():
                    for binding in e['binds']:self.assertIn(binding['controller'].encode()+b'\0',data)
                # Version 1 targets one instance; VRM 0 binds both instances of a mesh.
                self.assertEqual(len(meta['expressions'][expression]['binds']),1 if version else 2)
                if version:self.assertEqual(meta['colliders'][0]['shape'],'capsule')

    def test_vrm_validation_rejects_invalid_metadata_before_output(self):
        doc=self.vrm_fixture()
        for mutate in (
            lambda d:d['extensions']['VRMC_vrm']['expressions']['preset']['happy']['morphTargetBinds'][0].update(index=99),
            lambda d:d['extensions']['VRMC_springBone']['springs'][0]['joints'][0].update(dragForce=2),
            lambda d:d['nodes'][3].update(scale=[1,2,1]),
            lambda d:d['nodes'][3].update(scale=[-1,1,1]),
            lambda d:d['nodes'][4].update(children=[3]),
            lambda d:d['extensions']['VRMC_springBone']['colliders'][0]['shape']['capsule'].update(radius=-1),
        ):
            invalid=copy.deepcopy(doc);mutate(invalid)
            with self.assertRaises(ValueError):vrm_runtime.prepare(invalid,self.root,'valid')
        with self.assertRaises(ValueError):vrm_runtime.prepare(doc,self.root,'../invalid')

    def test_vrm_glb_input_and_per_node_morph_names_are_preserved(self):
        doc=self.vrm_fixture();data=json.dumps(doc).encode();data+=b' '*(-len(data)%4)
        source=self.root/'input.vrm';source.write_bytes(struct.pack('<5I',0x46546c67,2,len(data)+20,len(data),0x4e4f534a)+data)
        loaded=vrm_runtime.load_document(source)
        normalized,meta,qc=vrm_runtime.prepare(loaded,self.root,'test',1)
        names=[normalized['meshes'][normalized['nodes'][i]['mesh']]['extras']['targetNames'][0] for i in (1,2)]
        self.assertEqual(names,['vrm_n1_m0','vrm_n2_m0'])
        self.assertNotIn('VRMC_vrm',normalized['extensions'])
        self.assertEqual(meta['nodes'][3]['original_name'],'Joint')
        self.assertIn('$transformmodel angles 0 0 -90 scale 1',qc)

    def test_vrm1_explicit_spring_pairs_skip_nodes_and_leave_terminal_unrotated(self):
        doc=self.vrm_fixture()
        # The first scene child is a different branch; the declared tail is
        # below a skipped node, so neither children[0] nor a direct-child
        # translation reproduces its authored position.
        doc['nodes'][3]['children']=[5,4]
        doc['nodes'][4].update(children=[6])
        doc['nodes'].extend([dict(name='OtherBranch',translation=[9,0,0]),
                             dict(name='DeclaredTail',translation=[0,2,0])])
        spring=doc['extensions']['VRMC_springBone']['springs'][0]
        spring['joints']=[dict(node=3),dict(node=6,stiffness=999)]
        _,meta,_=vrm_runtime.prepare(doc,self.root,'test',1)
        joints=meta['springs'][0]['joints']
        self.assertEqual(len(joints),1)
        self.assertEqual(joints[0]['bone'],'vrm_node_3')
        self.assertEqual(joints[0]['tail'],[0,3,0])
        self.assertEqual(joints[0]['drag'],.5)
        spring['joints']=[dict(node=3)]
        self.assertEqual(vrm_runtime.prepare(doc,self.root,'test',1)[1]['springs'],[])
        spring['joints']=[dict(node=3),dict(node=2)]
        with self.assertRaisesRegex(ValueError,'descend'):
            vrm_runtime.prepare(doc,self.root,'test',1)
        # A second chain cannot claim a node skipped by the first chain.
        spring['joints']=[dict(node=3),dict(node=6)]
        doc['extensions']['VRMC_springBone']['springs'].append(dict(joints=[dict(node=4)]))
        with self.assertRaisesRegex(ValueError,'multiple springs'):
            vrm_runtime.prepare(doc,self.root,'test',1)
