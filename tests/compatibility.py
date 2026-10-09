"""Black-box regression tests. Usage: python tests/compatibility.py <mdlcompiler>.

Tests inspect emitted MDL headers instead of merely checking command registration.
All fixtures and outputs are isolated in a temporary directory.
"""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from scene_fixtures import scene_bytes,skinned_scene_bytes
from extended_cases import ExtendedCases
from physics_mass_cases import PhysicsMassCases
from physics_extra_cases import PhysicsExtraCases
from cloth_cases import ClothCases
from subd_cases import SubdCases
from dmx_dependency_cases import DmxDependencyCases
from procedural_cases import ProceduralCases
from axis_export_cases import AxisExportCases
from csgo_closure_cases import CsgoClosureCases
from cloth_advanced_cases import ClothAdvancedCases
from cloth_scope_cases import ClothScopeCases
from dmx_scope_cases import DmxScopeCases
from procedural_scope_cases import ProceduralScopeCases
from cloth_projection_cases import ClothProjectionCases
from integration_capacity_cases import IntegrationCapacityCases
from integration_rig_cases import IntegrationRigCases
from scene_integration_cases import SceneIntegrationCases
from integration_mesh_states_cases import IntegrationMeshStatesCases
from integration_workflow_cases import IntegrationWorkflowCases
from integration_policy_cases import IntegrationPolicyCases
from integration_vrm_cases import IntegrationVrmCases
from validate_outputs import validate

COMPILER = str(Path(sys.argv.pop(1)).resolve())


class Compatibility(ExtendedCases,PhysicsMassCases,PhysicsExtraCases,ClothCases,SubdCases,DmxDependencyCases,ProceduralCases,AxisExportCases,CsgoClosureCases,ClothAdvancedCases,ClothScopeCases,DmxScopeCases,ProceduralScopeCases,ClothProjectionCases,IntegrationCapacityCases,IntegrationRigCases,SceneIntegrationCases,IntegrationMeshStatesCases,IntegrationWorkflowCases,IntegrationPolicyCases,IntegrationVrmCases,unittest.TestCase):
    def test_merged_materials_keep_geometry_flexes_and_lods(self):
        import json,copy
        doc=json.loads(scene_bytes());doc['materials'].append({'name':'Second'})
        doc['meshes'].append(copy.deepcopy(doc['meshes'][0]));doc['meshes'][1]['primitives'][0]['material']=1
        doc['nodes'][2]['mesh']=1
        self.write('scene.gltf',json.dumps(doc))
        self.scene_qc('$modelname merged\n$body m scene.gltf RenameMat Original Shared RenameMat Second Shared {\nflex Smile\nflexcontroller test strength\n%Smile = strength\n}\n$lod 10 { }\n')
        d,flex=self.first_mesh_flex('merged');self.assertEqual(len(flex),6)
        self.assertEqual(struct.unpack_from('<i',d,204)[0],1)
        body=struct.unpack_from('<i',d,236)[0];model=body+struct.unpack_from('<i',d,body+12)[0]
        self.assertEqual(struct.unpack_from('<i',d,model+72)[0],1)
        self.assertEqual(struct.unpack_from('<i',d,model+80)[0],6)
        self.assertEqual(sorted(struct.unpack_from('<H',d,v)[0] for v in flex),list(range(6)))
        vvd=(self.root/'models/merged.vvd').read_bytes();start=struct.unpack_from('<i',vvd,56)[0]
        points=[struct.unpack_from('<3f',vvd,start+i*48+16) for i in range(6)]
        self.assertAlmostEqual(min(p[0] for p in points),1);self.assertAlmostEqual(max(p[0] for p in points),11)
        for ext in ('dx80','dx90'):
            vtx=(self.root/f'models/merged.{ext}.vtx').read_bytes();bp=struct.unpack_from('<i',vtx,32)[0]
            model=bp+struct.unpack_from('<i',vtx,bp+4)[0];lods,off=struct.unpack_from('<2i',vtx,model)
            self.assertEqual(lods,2)
            for i in range(lods):self.assertEqual(struct.unpack_from('<i',vtx,model+off+i*12)[0],1)

    def test_material_merge_is_scoped_to_one_body_choice(self):
        self.scene_fixture()
        self.scene_qc('$modelname scoped\n$bodygroup heads {\nstudio scene.gltf RenameMat Original Shared\nstudio scene.gltf\n}\n')
        d=self.mdl('scoped');self.assertEqual(struct.unpack_from('<i',d,204)[0],2)
        self.assertIn(b'Shared\0',d);self.assertIn(b'Original\0',d)

    def test_meshopt_compression_matches_plain_geometry_and_flex(self):
        fixture=Path(__file__).parent/'fixtures'
        baseline=None
        for kind in ('plain','triangles','indices'):
            self.write('scene.gltf',(fixture/f'meshopt-{kind}.gltf').read_text())
            self.scene_qc('$modelname packed\n$body m scene.gltf { flex Smile\nflexcontroller test strength\n%Smile = strength\n}\n$sequence idle scene.gltf\n')
            d,flex=self.first_mesh_flex('packed')
            vvd=(self.root/'models/packed.vvd').read_bytes();count=struct.unpack_from('<i',vvd,16)[0]
            start=struct.unpack_from('<i',vvd,56)[0]
            result=([struct.unpack_from('<12f',vvd,start+i*48) for i in range(count)],[d[v:v+16] for v in flex],self.animation_poses('packed','idle'))
            if baseline is None:baseline=result
            else:
                self.assertEqual(len(result[0]),len(baseline[0]));self.assertEqual(result[1:],baseline[1:])
                # EXPONENTIAL preprocessing intentionally quantizes floats.
                for a,b in zip(result[0],baseline[0]):
                    for x,y in zip(a,b):self.assertAlmostEqual(x,y,places=6)

    def test_corrupt_meshopt_stream_keeps_existing_output(self):
        import json,base64
        fixture=Path(__file__).parent/'fixtures'
        doc=json.loads((fixture/'meshopt-triangles.gltf').read_text())
        self.write('scene.gltf',json.dumps(doc));self.scene_qc('$modelname packed\n$body m scene.gltf\n');old=self.mdl('packed')
        data=bytearray(base64.b64decode(doc['buffers'][1]['uri'].split(',')[1]));data[0]=0
        doc['buffers'][1]['uri']='data:application/octet-stream;base64,'+base64.b64encode(data).decode()
        self.write('scene.gltf',json.dumps(doc))
        self.assertIn('invalid meshopt compressed stream',self.scene_qc('$modelname packed\n$body m scene.gltf\n',success=False))
        self.assertEqual(self.mdl('packed'),old)

    def instance_fixture(self,rotation=None,scale=None):
        import json,base64
        doc=json.loads(scene_bytes());doc['animations']=[];doc['nodes'][0]['children']=[1]
        payload=bytearray(base64.b64decode(doc['buffers'][0]['uri'].split(',')[1]))
        def attribute(values,width):
            offset=len(payload);payload.extend(struct.pack('<'+'f'*len(values),*values))
            doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(values)*4})
            doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,'componentType':5126,'count':2,'type':'VEC4' if width==4 else 'VEC3'})
            return len(doc['accessors'])-1
        attrs={'TRANSLATION':attribute([0,0,0,10,0,0],3)}
        if rotation is not None:attrs['ROTATION']=attribute(rotation,4)
        if scale is not None:attrs['SCALE']=attribute(scale,3)
        doc['nodes'][1]['extensions']={'EXT_mesh_gpu_instancing':{'attributes':attrs}}
        doc['extensionsUsed']=['EXT_mesh_gpu_instancing'];doc['extensionsRequired']=doc['extensionsUsed']
        doc['buffers'][0]={'byteLength':len(payload),'uri':'data:application/octet-stream;base64,'+base64.b64encode(payload).decode()}
        self.write('scene.gltf',json.dumps(doc))

    def test_static_gpu_instances_expand_transforms_and_morphs(self):
        self.instance_fixture(scale=[1,1,1,2,1,1])
        self.scene_qc('$modelname instanced\n$body m scene.gltf InNode MeshA { flex Smile\nflexcontroller test strength\n%Smile = strength\n}\n')
        d,flex=self.first_mesh_flex('instanced');self.assertEqual(len(flex),6)
        vvd=(self.root/'models/instanced.vvd').read_bytes();self.assertEqual(struct.unpack_from('<i',vvd,16)[0],6)
        start=struct.unpack_from('<i',vvd,56)[0]
        points=sorted(round(struct.unpack_from('<f',vvd,start+i*48+16)[0],4) for i in range(6))
        self.assertEqual(points,[1,2,3,10,12,14])

    def test_invalid_instance_rotation_is_rejected(self):
        self.instance_fixture(rotation=[0,0,0,0,0,0,0,1])
        result=self.scene_qc('$modelname invalid\n$body m scene.gltf\n',success=False)
        self.assertIn('zero glTF instance rotation',result);self.assertFalse((self.root/'models/invalid.mdl').exists())

    def test_static_instances_preserve_rotation_and_mirrored_winding(self):
        import math
        h=math.sqrt(.5)
        self.instance_fixture(rotation=[0,0,h,h,0,0,0,1],scale=[1,1,1,-1,1,1])
        self.scene_qc('$modelname rotated\n$UpAxis z gltf\n$body m scene.gltf InNode MeshA\n')
        vvd=(self.root/'models/rotated.vvd').read_bytes();start=struct.unpack_from('<i',vvd,56)[0]
        points=sorted(tuple(round(x,4) for x in struct.unpack_from('<3f',vvd,start+i*48+16)) for i in range(6))
        self.assertEqual(points,[(1,0,0),(2,-1,0),(2,1,0),(11,0,0),(12,1,0),(13,0,0)])

    def test_meshopt_range_errors_are_reported_before_output(self):
        import json
        fixture=Path(__file__).parent/'fixtures'
        for field,value in [('byteStride',0),('byteOffset',999999)]:
            doc=json.loads((fixture/'meshopt-triangles.gltf').read_text())
            doc['bufferViews'][0]['extensions']['EXT_meshopt_compression'][field]=value
            self.write('scene.gltf',json.dumps(doc))
            self.scene_qc('$modelname bad\n$body m scene.gltf\n',success=False)
            self.assertFalse((self.root/'models/bad.mdl').exists())

    def scene_qc(self,text,*args,success=True):
        qc=self.write('scene.qc',text)
        result=subprocess.run([COMPILER,str(qc),'-game',str(self.root),*args],capture_output=True,text=True,errors='replace')
        self.assertEqual(result.returncode==0,success,result.stdout+result.stderr)
        if success:
            for mdl in (self.root/'models').rglob('*.mdl'):validate(mdl)
        return result.stdout+result.stderr

    def scene_fixture(self,kind='gltf',**options):
        path=self.root/('scene.'+kind); path.write_bytes(scene_bytes(kind,**options)); return path

    def first_mesh_flex(self,name):
        data=self.mdl(name); body=struct.unpack_from('<i',data,236)[0]
        model=body+struct.unpack_from('<i',data,body+12)[0]
        mesh=model+struct.unpack_from('<i',data,model+76)[0]
        count,index=struct.unpack_from('<2i',data,mesh+16)
        self.assertGreater(count,0); key=mesh+index
        vertices,vanim=struct.unpack_from('<2i',data,key+20)
        return data,[key+vanim+i*16 for i in range(vertices)]

    def test_neko_fast_and_assimp_gltf_node_selection_and_missing_uv_normals(self):
        self.scene_fixture(normals=False)
        for backend in ('','$NoFastGltf\n'):
            self.scene_qc('$modelname scene\n'+backend+'$body mesh "scene.gltf" InNode MeshA\n$sequence idle scene.gltf\n')
            vvd=(self.root/'models/scene.vvd').read_bytes()
            count=struct.unpack_from('<i',vvd,16)[0]; start=struct.unpack_from('<i',vvd,56)[0]
            self.assertEqual(count,3)
            positions=[struct.unpack_from('<3f',vvd,start+i*48+16) for i in range(count)]
            # Bind-space geometry bakes the scene transform and Y-to-Z conversion.
            self.assertAlmostEqual(max(p[0] for p in positions),3,places=4)
            self.assertAlmostEqual(max(p[2] for p in positions),1,places=4)
        output=self.scene_qc('$modelname invalid\n$body mesh scene.gltf InNode missing\n',success=False)
        self.assertIn('InNode not found',output)

    def test_neko_gltf_uv_matches_reference_on_both_backends(self):
        self.scene_fixture(uv=True)
        for backend in ('', '$NoFastGltf\n'):
            self.scene_qc('$modelname scene\n'+backend+'$body mesh scene.gltf InNode MeshA\n')
            data=(self.root/'models/scene.vvd').read_bytes()
            count=struct.unpack_from('<i',data,16)[0]; start=struct.unpack_from('<i',data,56)[0]
            actual=sorted(tuple(round(x,4) for x in struct.unpack_from('<2f',data,start+i*48+40)) for i in range(count))
            self.assertEqual(actual,[(.1,.2),(.4,.9),(.7,.3)])

    def test_neko_glb_vrm_and_scoped_up_axis(self):
        for kind in ('glb','vrm'):
            self.scene_fixture(kind)
            self.scene_qc(f'$modelname {kind}\n$UpAxis z gltf\n$body mesh scene.{kind} InNode MeshA\n')
            self.assertTrue(self.mdl(kind).startswith(b'IDST'))

    def test_neko_sample_rate_pick_and_cubic_animation(self):
        self.scene_fixture(interpolation='CUBICSPLINE')
        self.scene_qc('$modelname sampled\n$animationcullmethod none\n$FPS 4\n'
                      '$body mesh scene.gltf InNode MeshA\n'
                      '$animation movement scene.gltf Pick Move SampleRate 8\n$sequence idle movement\n')
        data=self.mdl('sampled'); count,offset=struct.unpack_from('<2i',data,180)
        self.assertEqual(count,1)
        self.assertEqual(struct.unpack_from('<i',data,offset+16)[0],9)
        self.assertAlmostEqual(struct.unpack_from('<f',data,offset+8)[0],4)
        output=self.scene_qc('$modelname bad\n$body m scene.gltf\n$animation a scene.gltf SampleRate 0\n',success=False)
        self.assertIn('SampleRate',output)

    def test_neko_multi_studio_model_flexes_and_discard_delta_normals(self):
        self.scene_fixture()
        qc='$modelname face\n$NekoModel face {\nstudio scene.gltf InNode MeshA\nstudio scene.gltf InNode MeshB\nflex Smile\nflexcontroller test strength\n%Smile = strength\n}\n'
        self.scene_qc(qc)
        data,vertices=self.first_mesh_flex('face'); self.assertEqual(len(vertices),3)
        self.assertTrue(any(any(struct.unpack_from('<3e',data,v+10)) for v in vertices))
        body=struct.unpack_from('<i',data,236)[0]; self.assertEqual(struct.unpack_from('<i',data,body+4)[0],2)
        self.scene_qc('$DiscardVertexAnimationNormals\n'+qc)
        data,vertices=self.first_mesh_flex('face')
        self.assertTrue(all(struct.unpack_from('<3e',data,v+10)==(0,0,0) for v in vertices))

    def test_neko_pre_rename_material_and_obj_import(self):
        self.write('triangle.obj','mtllib triangle.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl Original\nf 1 2 3\n')
        self.write('triangle.mtl','newmtl Original\nKd 1 1 1\n')
        self.scene_qc('$modelname obj\n$PreRenameMaterial Original Renamed\n$UpAxis z assimp\n$body m triangle.obj\n')
        data=self.mdl('obj'); count,index=struct.unpack_from('<2i',data,204)
        self.assertEqual(count,1); name=index+struct.unpack_from('<i',data,index)[0]
        self.assertEqual(data[name:data.index(b'\0',name)],b'Renamed')

    def test_neko_line_conditions_cli_define_and_optional_include(self):
        output=self.run_qc('$modelname vars\n$DefineVariable x 0\n$if x == 1\n$unknown_loser\n'
                           '$elif x == 0\n$ifdef absent\n$unknown_nested\n$eldef name\n$Msg $name$\n$endif\n'
                           '$else\n$unknown_else\n$endif\n$UndefineVariable x\n'
                           '$Include missing.qci iffileexists\n$QCAssert boneexists root mesh.smd\n', '-Dname','selected')
        self.assertIn('selected',output); self.assertIn('[Success]',output)
        self.assertIn('missing $endif',self.run_qc('$if 1\n$Msg bad\n',success=False))

    def test_neko_jiggle_realign_and_reverse_matches_reference_values(self):
        self.write('jiggle.smd','version 1\nnodes\n0 "root" -1\n1 "jiggle" 0\nend\nskeleton\ntime 0\n'
                   '0 0 0 0 0 0 0\n1 0 0 1 .2 .3 .4\nend\ntriangles\nmat\n'
                   '1 0 0 1 0 0 1 0 0\n1 1 0 1 0 0 1 1 0\n1 0 1 1 0 0 1 0 1\nend\n')
        self.scene_qc('$modelname jiggle\n$body m jiggle.smd\n$JiggleBoneRealign 10 20 30\n'
                      '$ReverseJiggleBoneRotation pitch yaw\n$jigglebone jiggle { is_flexible { '
                      'pitch_constraint -10 30 yaw_constraint -20 40 } }\n')
        data=self.mdl('jiggle'); bones,index=struct.unpack_from('<2i',data,156)
        bone=index+(bones-1)*216
        for actual,expected in zip(struct.unpack_from('<3f',data,bone+60),(.53632557,.49104747,1.04254591)):
            self.assertAlmostEqual(actual,expected,places=5)
        proc=bone+struct.unpack_from('<i',data,bone+168)[0]
        values=struct.unpack_from('<8f',data,proc+40)
        for actual,expected in zip((values[0],values[1],values[4],values[5]),(-.69813168,.34906584,-.52359879,.17453292)):
            self.assertAlmostEqual(actual,expected,places=5)

    def test_neko_budget_validation(self):
        self.assertIn('MaxBones',self.run_qc('$MaxBones 257\n',success=False))
        self.assertIn('MaxVerts',self.run_qc('$MaxVerts 2\n',success=False))
        self.assertIn('MaxVertexClamp',self.run_qc('$MaxVerts 10 11\n',success=False))
        self.assertIn('buffer size',self.run_qc('$FileBufferSize 0\n',success=False))

    def test_neko_stereo_balance_matches_reference(self):
        import json
        path=self.scene_fixture(); doc=json.loads(path.read_text()); doc['nodes'][1]['translation']=[0,0,0]
        path.write_text(json.dumps(doc))
        self.scene_qc('$modelname stereo\n$NekoModel face {\nstudio scene.gltf InNode MeshA\n'
                      'flexpair Smile\nflexcontroller test L R\n%SmileL = L\n%SmileR = R\n}\n')
        data,vertices=self.first_mesh_flex('stereo')
        self.assertEqual(sorted(data[v+3] for v in vertices),[0,127,255])

    def test_neko_file_budget_validates_all_files_before_overwrite(self):
        self.run_qc('$modelname limited\n')
        original=self.mdl('limited')
        output=self.run_qc('$modelname limited\n$FileBufferSize .0001\n',success=False)
        self.assertIn('FileBufferSize output limit exceeded',output)
        self.assertEqual(self.mdl('limited'),original)

    def test_neko_driver_bone_samples_all_helpers(self):
        self.write('pose.smd','version 1\nnodes\n0 "root" -1\n1 "unused_child" 0\nend\nskeleton\n'
                   'time 0\n0 0 0 0 0 0 0\n1 0 0 1 0 0 0\ntime 1\n0 0 0 0 0 0 .5\n1 .25 0 1 0 .25 0\nend\n')
        self.run_qc('$modelname driver\n$NekoDriverBone root {\npose pose.smd\ntrigger 90 0\ntrigger 90 1\nunused_child\n}\n')
        data=self.mdl('driver'); count,index=struct.unpack_from('<2i',data,156)
        procedural=[index+b*216 for b in range(count) if struct.unpack_from('<i',data,index+b*216+164)[0]==2]
        self.assertEqual(len(procedural),1)
        proc=procedural[0]+struct.unpack_from('<i',data,procedural[0]+168)[0]
        self.assertEqual(struct.unpack_from('<i',data,proc+4)[0],2)

    def test_neko_append_scale_multiplies_existing_scale(self):
        self.animation_fixture()
        self.run_qc('$modelname scaled\n$animationcullmethod none\n$animation base moving.smd\n'
                    '$animation bigger moving.smd scale 2 AppendScale 1.5\n$sequence idle bigger\n')
        original=self.animation_poses('scaled','base'); scaled=self.animation_poses('scaled','bigger')
        for a,b in zip(original,scaled):
            # RLE/half-position compression quantizes each clip independently.
            for i in range(3): self.assertAlmostEqual(b[i],3*a[i],delta=.02)

    def test_neko_no_bone_realign_is_scoped_to_one_animation(self):
        self.animation_fixture()
        self.run_qc('$modelname plain\n$animation raw moving.smd\n$sequence idle raw\n')
        plain=self.animation_poses('plain','raw')
        self.run_qc('$modelname realigned\n$animationcullmethod none\n'
                    '$definebone root "" 0 0 0 30 0 0 0 0 0 20 10 5\n'
                    '$animation aligned moving.smd\n$animation raw moving.smd NoBoneRealign\n$sequence idle raw\n')
        raw=self.animation_poses('realigned','raw'); aligned=self.animation_poses('realigned','aligned')
        # Retained animated bones can use the animation's first pose as the
        # bind pose. The explicit definebone has a different bind pose, so
        # their RLE residuals quantize independently; compare within both
        # emitted scale steps instead of an arbitrary decimal-place cutoff.
        steps=[]
        for name in ('plain','realigned'):
            data=self.mdl(name);bone=struct.unpack_from('<i',data,160)[0]
            steps.append(struct.unpack_from('<6f',data,bone+72))
        for a,b in zip(plain,raw):
            for axis,(x,y) in enumerate(zip(a,b)):
                self.assertAlmostEqual(x,y,delta=abs(steps[0][axis])+abs(steps[1][axis])+2e-6)
        self.assertNotEqual(raw,aligned)

    def test_split_mesh_preserves_flexes_and_reduced_lod(self):
        import json
        self.scene_fixture()
        doc=json.loads((self.root/'scene.gltf').read_bytes())
        doc['nodes']=doc['nodes'][:2];doc['nodes'][0]['children']=[1]
        self.write('lod.gltf',json.dumps(doc))
        self.scene_qc('$modelname lod\n$MaxVerts 3\n$NekoModel face {\nstudio scene.gltf\n'
                      'flex Smile\nflexcontroller test strength\n%Smile = strength\n}\n'
                      '$lod 10 { replacemodel scene.gltf lod.gltf }\n')
        data=(self.root/'models/lod.vvd').read_bytes()
        self.assertEqual(struct.unpack_from('<i',data,12)[0],2)
        self.assertEqual(struct.unpack_from('<2i',data,16),(6,3))
        keys=self.ce_data('lod')[1]
        self.assertEqual(sum(len(key['vertices']) for key in keys),6)
        for key in keys:
            for va in key['vertices']:self.assertAlmostEqual(va[2][1],-.25,delta=.002)

    def test_neko_small_mesh_limit_splits_without_dropping_geometry(self):
        self.scene_fixture()
        self.scene_qc('$modelname split\n$MaxVerts 3\n$body m scene.gltf\n')
        data=self.mdl('split'); body=struct.unpack_from('<i',data,236)[0]
        model=body+struct.unpack_from('<i',data,body+12)[0]
        self.assertEqual(struct.unpack_from('<i',data,model+72)[0],2)
        vvd=(self.root/'models/split.vvd').read_bytes()
        self.assertEqual(struct.unpack_from('<i',vvd,16)[0],6)

    def test_neko_gltf_skin_uses_inverse_bind_without_mesh_node_transform(self):
        (self.root/'skin.gltf').write_bytes(skinned_scene_bytes())
        for backend in ('','$NoFastGltf\n'):
            self.scene_qc('$modelname skin\n$CEBoneRules\n'+backend+'$body m skin.gltf InNode MeshA\n')
            vvd=(self.root/'models/skin.vvd').read_bytes(); start=struct.unpack_from('<i',vvd,56)[0]
            xs=[struct.unpack_from('<f',vvd,start+i*48+16)[0] for i in range(3)]
            self.assertEqual(sorted(round(x,4) for x in xs),[-1,0,1])
            data=self.mdl('skin'); count,index=struct.unpack_from('<2i',data,156); joints=[]
            for b in range(count):
                bone=index+b*216; name=bone+struct.unpack_from('<i',data,bone)[0]
                if data[name:data.index(b'\0',name)]==b'Joint': joints.append(struct.unpack_from('<3f',data,bone+32))
            self.assertEqual(joints,[(5,0,0)])

    def test_neko_animated_scale_fails_instead_of_silently_losing_deformation(self):
        import base64,json
        path=self.scene_fixture(); doc=json.loads(path.read_text())
        doc['animations'][0]['channels'][0]['target']['path']='scale'
        accessor=doc['accessors'][doc['animations'][0]['samplers'][0]['output']]
        offset=doc['bufferViews'][accessor['bufferView']]['byteOffset']
        blob=bytearray(base64.b64decode(doc['buffers'][0]['uri'].split(',')[1]))
        struct.pack_into('<6f',blob,offset,1,1,1,2,2,2)
        doc['buffers'][0]['uri']='data:application/octet-stream;base64,'+base64.b64encode(blob).decode()
        path.write_text(json.dumps(doc))
        output=self.scene_qc('$modelname bad_scale\n$body m scene.gltf\n',success=False)
        self.assertIn('animated scene scaling must be baked',output)

    def test_branding_and_clean_captured_output(self):
        output = self.run_qc('$modelname branding\n', '-verify')
        self.assertIn('NewPageMergeMDL | Model Compiler', output)
        self.assertIn('[ SOURCE MODEL FORGE ]', output)
        self.assertNotIn('\x1b[', output)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.write("mesh.smd", 'version 1\nnodes\n0 "root" -1\n1 "unused_child" 0\nend\n'
                   'skeleton\ntime 0\n0 0 0 0 0 0 0\n1 0 0 1 0 0 0\nend\n'
                   'triangles\nmaterial\n0 0 0 0 0 0 1 0 0\n'
                   '0 1 0 0 0 0 1 1 0\n0 0 1 0 0 0 1 0 1\nend\n')

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_qc(self, text, *args, success=True):
        qc = self.write("test.qc", text + '\n$body mesh "mesh.smd"\n')
        result = subprocess.run([COMPILER, str(qc), "-game", str(self.root), *args],
                                capture_output=True, text=True, errors="replace")
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def mdl(self, name):
        return (self.root / "models" / (name + ".mdl")).read_bytes()

    def sequences(self, name):
        data = self.mdl(name)
        count, index = struct.unpack_from('<2i', data, 188)
        result = []
        for i in range(count):
            offset = index + i * 212
            label = offset + struct.unpack_from('<i', data, offset + 4)[0]
            name = data[label:data.index(b'\0', label)].decode()
            result.append((name, struct.unpack_from('<i', data, offset + 12)[0], offset))
        return result

    def test_animation_bounds_outside_coordinate_range_remain_ordered(self):
        for x in (20000, -20000):
            self.write('outside.smd', 'version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 '+str(x)+' 0 0 0 0 0\nend\n')
            output=self.run_qc('$modelname bounds\n$animationcullmethod none\n$sequence idle outside.smd\n')
            self.assertIn('exceeds coordinate range',output)
            data=self.mdl('bounds'); offset=self.sequences('bounds')[0][2]
            low=struct.unpack_from('<3f',data,offset+32); high=struct.unpack_from('<3f',data,offset+44)
            for a,b in zip(low,high): self.assertLessEqual(a,b)
            limit=16384 if x>0 else -16384
            self.assertAlmostEqual(low[1],limit)
            self.assertAlmostEqual(high[1],limit)

    def test_smd_invalid_parent_is_diagnostic_not_crash(self):
        for parent in (-2, 999, 0):
            text=(self.root/'mesh.smd').read_text().replace('0 "root" -1',f'0 "root" {parent}')
            self.write('bad.smd',text)
            output=self.scene_qc('$modelname invalid\n$body m bad.smd\n',success=False)
            self.assertIn('parent',output)
            self.assertFalse((self.root/'models/invalid.mdl').exists())

    def test_qc_nonfinite_numbers_preserve_previous_output(self):
        self.run_qc('$modelname finite\n')
        previous=self.mdl('finite')
        for value in ('nan','inf','-inf'):
            self.run_qc('$modelname finite\n$scale '+value+'\n',success=False)
            self.assertEqual(previous,self.mdl('finite'))

    def test_smd_stream_reader_preserves_bom_and_crlf(self):
        original=(self.root/'mesh.smd').read_text()
        (self.root/'mesh.smd').write_bytes(b'\xef\xbb\xbf'+original.replace('\n','\r\n').encode())
        self.run_qc('$modelname bom\n$sequence idle mesh.smd\n')
        self.assertTrue(self.mdl('bom').startswith(b'IDST'))

    def test_512_source_bones_collapse_and_extended_output_fails_explicitly(self):
        nodes='\n'.join(['0 "root" -1']+[f'{i} "bone{i}" 0' for i in range(1,512)])
        poses='\n'.join(f'{i} 0 0 0 0 0 0' for i in range(512))
        triangles=(self.root/'mesh.smd').read_text().split('triangles\n')[1]
        self.write('manybones.smd','version 1\nnodes\n'+nodes+'\nend\nskeleton\ntime 0\n'+poses+'\nend\ntriangles\n'+triangles)
        self.scene_qc('$modelname manybones\n$body m manybones.smd\n$sequence idle manybones.smd\n')
        self.assertLessEqual(struct.unpack_from('<i',self.mdl('manybones'),156)[0],256)
        before=self.mdl('manybones')
        output=self.scene_qc('$modelname manybones\n$ModelBudget bones 512\n$bonecullmethod none\n$body m manybones.smd\n',success=False)
        self.assertIn('byte-index tables',output)
        self.assertEqual(before,self.mdl('manybones'))

    def test_256_bone_animation_uses_frame_encoding_for_highest_index(self):
        nodes='\n'.join(['0 "root" -1']+[f'{i} "bone{i}" 0' for i in range(1,256)])
        poses='\n'.join(f'{i} 0 0 0 0 0 0' for i in range(256))
        triangles=(self.root/'mesh.smd').read_text().split('triangles\n')[1]
        self.write('full.smd','version 1\nnodes\n'+nodes+'\nend\nskeleton\ntime 0\n'+poses+'\ntime 1\n255 1 0 0 0 0 0\nend\ntriangles\n'+triangles)
        self.scene_qc('$modelname full\n$MaxBones 256\n$bonecullmethod none\n$body m full.smd\n$sequence idle full.smd\n')
        data=self.mdl('full');self.assertEqual(struct.unpack_from('<i',data,156)[0],256)
        index=struct.unpack_from('<i',data,184)[0]
        self.assertTrue(struct.unpack_from('<i',data,index+12)[0] & 0x40)
        self.animation_poses('full','idle')
        files=list((self.root/'decompiled').rglob('idle.smd'))
        poses=[list(map(float,line.split()[1:])) for line in files[0].read_text().splitlines() if line.startswith('255 ') and '"' not in line]
        self.assertEqual(len(poses),2)
        self.assertGreater(sum(abs(a-b) for a,b in zip(*poses)),.5)

    def test_smd_invalid_weights_fail_before_output(self):
        base=(self.root/'mesh.smd').read_text()
        for suffix in (' 17 '+'0 1 '*17, ' 1 999 1', ' 1 0 nan', ' 1 0 -1'):
            self.write('bad.smd',base.replace('0 0 0 0 0 0 1 0 0\n','0 0 0 0 0 0 1 0 0'+suffix+'\n'))
            output=self.scene_qc('$modelname invalid\n$body m bad.smd\n',success=False)
            self.assertTrue('weight count' in output or 'influence' in output)

    def test_more_than_128_materials_serialize_without_truncation(self):
        text=(self.root/'mesh.smd').read_text();head,triangle=text.split('triangles\n')
        triangles=triangle.removesuffix('end\n')
        self.write('materials.smd',head+'triangles\n'+''.join(triangles.replace('material\n',f'material{i}\n') for i in range(130))+'end\n')
        self.scene_qc('$modelname materials\n$body m materials.smd\n')
        self.assertEqual(struct.unpack_from('<i',self.mdl('materials'),204)[0],130)

    def test_gmtime_exact_flags_and_decompile_round_trip(self):
        self.run_qc('$modelname utc\n$sequence idle mesh.smd gmtime loop\n')
        self.assertEqual(self.sequences('utc')[0][1] & 0x100101, 0x100101)
        compiler = Path(COMPILER)
        decompiler = compiler.with_name('NewPageMergeMDL-Decompiler' + compiler.suffix)
        result = subprocess.run([str(decompiler), str(self.root / 'models/utc.mdl'), '-pulseqc',
                                 '-outdir', str(self.root / 'utc-decompiled')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        qc = next((self.root / 'utc-decompiled').rglob('*.pulseqc'))
        self.assertIn('gmtime', qc.read_text())
        result = subprocess.run([COMPILER, str(qc), '-game', str(self.root / 'roundtrip')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = (self.root / 'roundtrip/models/utc.mdl').read_bytes()
        index = struct.unpack_from('<i', data, 192)[0]
        self.assertEqual(struct.unpack_from('<i', data, index + 12)[0] & 0x100101, 0x100101)

    def test_default_sequence_remap_and_noremap_opt_out(self):
        self.run_qc('$modelname ordering\n$sequence Idle mesh.smd\n$sequence walk mesh.smd\n')
        reversed_qc = '$modelname ordering\n$sequence walk mesh.smd\n$sequence idle mesh.smd\n'
        self.run_qc(reversed_qc)
        self.assertEqual([s[0] for s in self.sequences('ordering')], ['idle', 'walk'])
        self.run_qc(reversed_qc, '-noremap')
        self.assertEqual([s[0] for s in self.sequences('ordering')], ['walk', 'idle'])

    def test_sequence_remap_removes_missing_names_and_appends_new_names(self):
        self.run_qc('$modelname ordering\n$sequence idle mesh.smd\n$sequence walk mesh.smd\n$sequence fire mesh.smd\n')
        self.run_qc('$modelname ordering\n$sequence run mesh.smd\n$sequence walk mesh.smd\n')
        self.assertEqual([s[0] for s in self.sequences('ordering')], ['walk', 'run'])

    def test_sequence_remap_updates_autolayer_indices_and_accepts_v48_header(self):
        self.run_qc('$modelname layered\n$sequence layer mesh.smd\n'
                    '$sequence base mesh.smd { addlayer layer }\n')
        path = self.root / 'models/layered.mdl'
        data = bytearray(path.read_bytes())
        struct.pack_into('<i', data, 4, 48)
        path.write_bytes(data)
        qc = '$modelname layered\n$sequence base mesh.smd { addlayer layer }\n$sequence layer mesh.smd\n'
        self.run_qc(qc)
        sequences = self.sequences('layered')
        self.assertEqual([s[0] for s in sequences], ['layer', 'base'])
        data = self.mdl('layered')
        count, index = struct.unpack_from('<2i', data, sequences[1][2] + 148)
        self.assertEqual(count, 1)
        self.assertEqual(struct.unpack_from('<h', data, sequences[1][2] + index)[0], 0)
        self.run_qc(qc, '-noremap')
        sequences = self.sequences('layered')
        self.assertEqual([s[0] for s in sequences], ['base', 'layer'])
        data = self.mdl('layered')
        index = struct.unpack_from('<i', data, sequences[0][2] + 152)[0]
        self.assertEqual(struct.unpack_from('<h', data, sequences[0][2] + index)[0], 1)

    def test_invalid_existing_model_offsets_do_not_crash_or_control_output(self):
        self.run_qc('$modelname ordering\n$sequence idle mesh.smd\n')
        path = self.root / 'models/ordering.mdl'
        data = bytearray(path.read_bytes())
        struct.pack_into('<i', data, 192, 0x7fffffff)
        path.write_bytes(data)
        output = self.run_qc('$modelname ordering\n$sequence walk mesh.smd\n$sequence idle mesh.smd\n')
        self.assertIn('Cannot preserve sequence order', output)
        self.assertEqual([s[0] for s in self.sequences('ordering')], ['walk', 'idle'])

    def vta_keys(self, options, stereo=False):
        self.write('face.vta', 'version 1\nnodes\n0 "root" -1\nend\n'
                   'skeleton\ntime 0\n0 0 0 0 0 0 0\ntime 1\n0 0 0 0 0 0 0\n'
                   'time 2\n0 0 0 0 0 0 0\nend\nvertexanimation\n'
                   'time 0\n0 0 0 0 0 0 1\n1 1 0 0 0 0 1\n2 0 1 0 0 0 1\n'
                   'time 1\n0 0 0 0.25 0 0 1\n1 1 0 0.4 0 0 1\n'
                   'time 2\n0 0 0 0.5 0 0 1\n1 1 0 0.8 0 0 1\nend\n')
        rules = '%sharedL = strength\n%sharedR = strength' if stereo else '%shared = strength'
        self.run_qc('$modelname face\n$model face "mesh.smd" {\n'
                    'flexfile "face.vta" {\n' + options + '\n}\n'
                    'flexcontroller test range 0 1 strength\n' + rules + '\n}\n')
        data = self.mdl('face')
        body = struct.unpack_from('<i', data, 236)[0]
        model = body + struct.unpack_from('<i', data, body + 12)[0]
        mesh = model + struct.unpack_from('<i', data, model + 76)[0]
        count, index = struct.unpack_from('<2i', data, mesh + 16)
        keys = []
        for i in range(count):
            offset = mesh + index + i * 60
            desc = struct.unpack_from('<i', data, offset)[0]
            targets = struct.unpack_from('<4f', data, offset + 4)
            vertices, vanim = struct.unpack_from('<2i', data, offset + 20)
            pair = struct.unpack_from('<i', data, offset + 28)[0]
            heights = [struct.unpack_from('<e', data, offset + vanim + j * 16 + 8)[0]
                       for j in range(vertices)]
            sides = [data[offset + vanim + j * 16 + 3] for j in range(vertices)]
            keys.append((desc, pair, targets, heights, sides))
        return keys

    def test_repeated_vta_name_preserves_distinct_frame_deltas_and_equal_position_order(self):
        keys = self.vta_keys('flex "shared" frame 1\nflex "shared" frame 2')
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0][0], keys[1][0])
        self.assertEqual(keys[0][2], (0, 1, 1, 1))
        self.assertEqual(keys[1][2], (1, 1, 10, 11))
        self.assertAlmostEqual(max(keys[1][3]), 2 * max(keys[0][3]), places=3)

    def test_repeated_stereo_vta_name_preserves_pair_balance_and_progressive_positions(self):
        keys = self.vta_keys('flexpair "shared" 1 frame 1 position 0.5\n'
                             'flexpair "shared" 1 frame 2 position 1', stereo=True)
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0][:2], keys[1][:2])
        self.assertNotEqual(keys[0][0], keys[0][1])
        self.assertEqual(keys[0][2], (0, 0.5, 0.5, 1))
        self.assertEqual(keys[1][2], (0.5, 1, 10, 11))
        self.assertEqual(keys[0][4], keys[1][4])
        self.assertGreater(len(set(keys[0][4])), 1)
        self.assertAlmostEqual(max(keys[1][3]), 2 * max(keys[0][3]), places=3)

    def test_repeated_vta_positions_keep_ce_declaration_order(self):
        keys = self.vta_keys('flex "shared" frame 2 position 1\n'
                             'flex "shared" frame 1 position 0.5')
        self.assertEqual(keys[0][2], (0, 1, 1, 0.5))
        self.assertEqual(keys[1][2], (1, 0.5, 10, 11))
        self.assertAlmostEqual(max(keys[0][3]), 2 * max(keys[1][3]), places=3)

    def test_variable_assignment_and_replacement(self):
        self.run_qc('$setvariable name first\n$setvariable name replaced\n$modelname "$name$.mdl"\n')
        self.assertEqual(self.mdl("replaced")[:4], b"IDST")

    def test_launch_variable_stays_pinned(self):
        self.run_qc('$setvariable name ignored\n$modelname "$name$.mdl"\n',
                    "-defvar", "name", "pinned")
        self.mdl("pinned")

    def test_duplicate_define_warns_and_preserves_first_value(self):
        text = self.run_qc('$definevariable name first\n$definevariable name second\n'
                           '$modelname "$name$.mdl"\n')
        self.assertIn("WARNING:", text)
        self.mdl("first")

    def test_prefixed_include_in_subdirectory(self):
        self.write("inc/pre_child.qci", '$setvariable name included\n')
        self.run_qc('$IncludePrefix "inc/child.qci" "pre_"\n'
                    '$include "inc/child.qci"\n$modelname "$name$.mdl"\n')
        self.mdl("included")

    def test_pushd_include_and_nested_include(self):
        self.write("other/child.qci", '$include "nested.qci"\n')
        self.write("other/nested.qci", '$setvariable name nested\n')
        self.write("child.qci", '$setvariable name wrong\n')
        self.run_qc('$PUSHDInclude 1\n$pushd "other"\n$include "child.qci"\n'
                    '$popd\n$modelname "$name$.mdl"\n')
        self.mdl("nested")

    def test_include_animation_prefix(self):
        self.run_qc('$modelname include_test\n$IncludeAnimPrefix "pre_"\n'
                    '$includemodel "folder/anim.mdl"\n')
        data = self.mdl("include_test")
        self.assertIn(b"models/folder/pre_anim.mdl\x00", data)
        self.assertEqual(struct.unpack_from("<i", data, 336)[0], 1)

    def test_mostlyopaque_launch_overrides_qc(self):
        self.run_qc('$modelname opaque\n$opaque\n', "-MostlyOpaque")
        flags = struct.unpack_from("<i", self.mdl("opaque"), 152)[0]
        self.assertTrue(flags & 8)
        self.assertFalse(flags & 4)

    def test_invalid_pushd_value(self):
        text = self.run_qc('$modelname bad\n$PUSHDInclude 2\n', success=False)
        self.assertIn("expected 0 or 1", text)

    def test_empty_collapse_prefix_is_rejected(self):
        text = self.run_qc('$modelname bad\n$AlwaysCollapseByPrefix ""\n', success=False)
        self.assertIn("empty prefix", text)

    def test_missing_launch_prefix_is_rejected(self):
        text = self.run_qc('$modelname bad\n', "-AlwaysCollapseByPrefix", success=False)
        self.assertIn("needs a non-empty prefix", text)

    def test_collapse_prefix_changes_output_skeleton(self):
        qc = '$modelname bones\n$bonecullmethod none\n'
        self.run_qc(qc)
        before = struct.unpack_from("<i", self.mdl("bones"), 156)[0]
        self.run_qc(qc, "-AlwaysCollapseByPrefix", "UNUSED_")
        after = struct.unpack_from("<i", self.mdl("bones"), 156)[0]
        self.assertEqual(before, 2)
        self.assertEqual(after, 1)
        self.run_qc(qc + '$AlwaysCollapseByPrefix unused_\n')
        self.assertEqual(struct.unpack_from("<i", self.mdl("bones"), 156)[0], after)

    def test_animation_culling_launch_override_and_nocull(self):
        qc = ('$modelname anims\n$animationcullmethod none\n'
              '$animation used "mesh.smd" fps 30\n'
              '$animation unused "mesh.smd" fps 12\n$sequence idle used\n')
        self.run_qc(qc)
        self.assertEqual(struct.unpack_from("<i", self.mdl("anims"), 180)[0], 2)
        self.run_qc(qc, "-cullanims")
        self.assertEqual(struct.unpack_from("<i", self.mdl("anims"), 180)[0], 1)
        self.run_qc(qc.replace('fps 12', 'fps 12 nocull'), "-cullanims")
        self.assertEqual(struct.unpack_from("<i", self.mdl("anims"), 180)[0], 2)

    def test_macro_defaults_and_variable_fallback(self):
        self.run_qc('$definevariable dir macro\n$definemacro emit name=default\n'
                    '$modelname "$dir$/$name$.mdl"\n$endmacro\n$emit\n')
        self.mdl("macro/default")

    def test_circular_prefixed_include_is_rejected(self):
        self.write("pre_loop.qci", '$include "loop.qci"\n')
        text = self.run_qc('$modelname bad\n$IncludePrefix loop.qci pre_\n'
                           '$include loop.qci\n', success=False)
        self.assertIn("circular include", text)

    def animation_fixture(self):
        self.write("moving.smd", 'version 1\nnodes\n0 "root" -1\nend\n'
                   'skeleton\ntime 0\n0 10 0 0 0 0 0.5\n'
                   'time 1\n0 20 0 0 0 0 1.0\nend\n')

    def animation_poses(self, model, name):
        compiler_path = Path(COMPILER)
        decompiler = str(compiler_path.with_name("NewPageMergeMDL-Decompiler" + compiler_path.suffix))
        result = subprocess.run([decompiler, str(self.root / 'models' / (model+'.mdl')),
                                 '-smdanimation', '-outdir', str(self.root / 'decompiled')],
                                capture_output=True, text=True, errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        files = [p for p in (self.root / 'decompiled').rglob(name+'.smd')
                 if any(parent.name==model for parent in p.parents)]
        self.assertEqual(len(files), 1, str(list((self.root / 'decompiled').rglob('*.smd'))))
        frames = []
        in_skeleton = False
        for line in files[0].read_text().splitlines():
            if line.strip() == 'skeleton': in_skeleton = True
            elif line.strip() == 'end': in_skeleton = False
            elif in_skeleton:
                values = line.split()
                if len(values) == 7 and values[0] == '0':
                    frames.append(tuple(float(v) for v in values[1:]))
        return frames

    def test_animation_conditions_select_only_one_branch(self):
        self.animation_fixture()
        self.run_qc('$modelname conditions\n$setvariable mode 2\n'
                    '$animation clip "moving.smd" {\n'
                    'if mode == 1 { unknown_unselected_option }\n'
                    'else if mode == 2 { if 1 { numframes 4 } }\n'
                    'else { unknown_unselected_option }\n}\n$sequence idle clip\n')
        self.assertEqual(len(self.animation_poses('conditions', 'clip')), 4)

    def test_animation_copy_copies_motion_and_holds_last_frame(self):
        self.animation_fixture()
        self.run_qc('$modelname copying\n$animationcullmethod none\n'
                    '$animation source "moving.smd"\n'
                    '$animation dest "mesh.smd" { numframes 4 copy source }\n'
                    '$sequence idle dest\n')
        src = self.animation_poses('copying', 'source')
        dst = self.animation_poses('copying', 'dest')
        self.assertEqual(len(dst), 4)
        for actual, expected in zip(dst, [src[0], src[1], src[1], src[1]]):
            for a, b in zip(actual, expected): self.assertAlmostEqual(a, b, places=3)

    def test_copy_self_reference_rejected(self):
        text = self.run_qc('$modelname bad\n$animation clip "mesh.smd" copy clip\n'
                           '$sequence idle clip\n', success=False)
        self.assertIn('requires an earlier animation', text)

    def test_animation_match_position_preserves_rotation(self):
        self.animation_fixture()
        self.run_qc('$modelname matching\n$animationcullmethod none\n'
                    '$animation source "moving.smd"\n'
                    '$animation dest "mesh.smd" match source pos\n'
                    '$sequence idle dest\n')
        src = self.animation_poses('matching', 'source')[0]
        dst = self.animation_poses('matching', 'dest')[0]
        # The two clips may choose different MDL quantization scales.
        for a, b in zip(src[:3], dst[:3]): self.assertAlmostEqual(a, b, delta=0.01)
        self.assertGreater(abs(src[5]-dst[5]), 0.1)

    def test_match_rotation_and_default_agree(self):
        self.animation_fixture()
        self.run_qc('$modelname rotations\n$animationcullmethod none\n'
                    '$animation source "moving.smd"\n'
                    '$animation explicit "mesh.smd" match source rot\n'
                    '$animation implicit "mesh.smd" match source\n'
                    '$sequence idle explicit\n')
        explicit = self.animation_poses('rotations', 'explicit')[0]
        implicit = self.animation_poses('rotations', 'implicit')[0]
        source = self.animation_poses('rotations', 'source')[0]
        for a, b in zip(explicit, implicit): self.assertAlmostEqual(a, b, delta=0.01)
        for a, b in zip(explicit[3:], source[3:]): self.assertAlmostEqual(a, b, delta=0.01)
        self.assertGreater(abs(explicit[0]-source[0]), 1.0)

    def test_copy_position_does_not_copy_rotation(self):
        self.animation_fixture()
        self.run_qc('$modelname channels\n$animationcullmethod none\n'
                    '$animation source "moving.smd"\n'
                    '$animation dest "mesh.smd" copy source pos\n$sequence idle dest\n')
        src = self.animation_poses('channels', 'source')[0]
        dst = self.animation_poses('channels', 'dest')[0]
        for a, b in zip(src[:3], dst[:3]): self.assertAlmostEqual(a, b, delta=0.01)
        self.assertGreater(abs(src[5]-dst[5]), 0.1)

    def test_animation_condition_missing_brace_is_error(self):
        text = self.run_qc('$modelname bad\n$animation clip "mesh.smd" { if 1 fps 12 }\n'
                           '$sequence idle clip\n', success=False)
        self.assertIn('missing', text)

    def test_animation_else_without_if_is_error(self):
        text = self.run_qc('$modelname bad\n$animation clip "mesh.smd" { else { fps 12 } }\n'
                           '$sequence idle clip\n', success=False)
        self.assertIn('else without', text)


    def ce_fixture(self):
        self.write('face.vta', 'version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\n'
                   'time 1\n0 0 0 0 0 0 0\ntime 2\n0 0 0 0 0 0 0\nend\nvertexanimation\n'
                   'time 0\n0 0 0 0 0 0 1\n1 1 0 0 0 0 1\n2 0 1 0 0 0 1\n'
                   'time 1\n0 0 0 .25 0 0 1\n1 1 0 .5 0 0 1\n'
                   'time 2\n0 0 0 .5 0 0 1\n1 1 0 1 0 0 1\nend\n')
        return 'flexfile face.vta {\ndefaultflex frame 0\nflex smile frame 1\n}\nflexcontroller test range 0 1 strength\n%smile = strength\n'

    def ce_data(self, name='face'):
        data=self.mdl(name)
        integer=lambda o:struct.unpack_from('<i',data,o)[0]
        string=lambda o:data[o:data.index(b'\0',o)].decode()
        desc=[string(integer(264)+i*4+integer(integer(264)+i*4)) for i in range(integer(260))]
        controllers=[]
        for i in range(integer(268)):
            p=integer(272)+i*20
            controllers.append((string(p+integer(p+4)),string(p+integer(p)),*struct.unpack_from('<2f',data,p+12)))
        keys=[]; eyes=[]; models=[]
        for b in range(integer(232)):
            bp=integer(236)+b*16
            for m in range(integer(bp+4)):
                model=bp+integer(bp+12)+m*148;models.append(model)
                for e in range(integer(model+100)):
                    p=model+integer(model+104)+e*172
                    eyes.append((string(p+integer(p)),struct.unpack_from('<3f',data,p+8),struct.unpack_from('<f',data,p+24)[0],struct.unpack_from('<f',data,p+60)[0]))
                for j in range(integer(model+72)):
                    mesh=model+integer(model+76)+j*116
                    for i in range(integer(mesh+16)):
                        p=mesh+integer(mesh+20)+i*60;v=p+integer(p+24);size=18 if data[p+32] else 16
                        keys.append(dict(name=desc[integer(p)],pair=integer(p+28),
                                    vertices=[(struct.unpack_from('<H',data,v+k*size)[0],data[v+k*size+2],
                                        struct.unpack_from('<6e',data,v+k*size+4),
                                        struct.unpack_from('<h',data,v+k*size+16)[0] if size==18 else None)
                                        for k in range(integer(p+20))]))
        rules=[]
        for i in range(integer(276)):
            p=integer(280)+i*12;op=p+integer(p+8)
            rules.append((desc[integer(p)], [struct.unpack_from('<ii',data,op+j*8) for j in range(integer(p+4))]))
        return controllers,keys,eyes,rules,models

    def ce_compile(self, global_options='', options=None, *args):
        block=self.ce_fixture() if options is None else options
        self.run_qc('$modelname face\n'+global_options+'\n$model face mesh.smd {\n'+block+'\n}\n',*args)
        return self.ce_data()

    def test_ce_controller_override_and_duplicate_tables(self):
        block=self.ce_fixture().replace('flexcontroller test range 0 1 strength',
                    'flexcontroller old range 0 1 strength\nflexcontroller new range -1 2 strength')
        for flag,expected in [('', [('strength','old',0,1)]),
                   ('$OverrideFlexControllers',[('strength','new',-1,2)]),
                   ('$AllowDuplicationFlexControllers',[('strength','old',0,1),('strength','new',-1,2)])]:
            with self.subTest(flag=flag): self.assertEqual(self.ce_compile(flag,block)[0],expected)
        self.assertEqual(self.ce_compile('',block,'-OvErRiDeFlExCoNtRoLlErS')[0],[('strength','new',-1,2)])

    def test_ce_inverse_geometry_rule_and_controller_range(self):
        controllers,keys,_,rules,_=self.ce_compile('$AddInvStudioFlexes')
        self.assertEqual(controllers,[('strength','test',-1,1)])
        original=next(k for k in keys if k['name']=='smile');inverse=next(k for k in keys if k['name']=='smile_Inv')
        for a,b in zip(original['vertices'],inverse['vertices']):
            for x,y in zip(a[2],b[2]):self.assertAlmostEqual(x,-y,places=4)
        rule=next(ops for name,ops in rules if name=='smile_Inv')
        self.assertEqual(rule[-2:],[(1,-1082130432),(6,0)])

    def test_ce_inverse_toggle_and_stereo_names(self):
        block=self.ce_fixture().replace('flex smile frame 1','InvertControllers\nflexpair smile 1 frame 1\nInvertControllers\nflex other frame 2')
        block=block.replace('%smile = strength','%smileL = strength\n%smileR = strength\n%other = strength')
        keys=self.ce_compile('',block)[1]
        self.assertEqual({k['name'] for k in keys},{'smileL','smile_InvL','other'})
        self.assertTrue(next(k for k in keys if k['name']=='smile_InvL')['pair'])

    def test_ce_fscale_overrides_tenfold_flex_strength(self):
        baseline=self.ce_compile()[1][0]['vertices']
        for flags,suffix,factor in [('$DefaqScale','',10),('$DefaqScale',' fscale 2',2),('',' fscale -1',-1)]:
            block=self.ce_fixture().replace('flex smile frame 1','flex smile frame 1'+suffix)
            result=self.ce_compile(flags,block)[1][0]['vertices']
            for a,b in zip(baseline,result):self.assertAlmostEqual(a[2][2]*factor,b[2][2],places=3)

    def test_ce_zero_decay_sets_all_vertex_speeds(self):
        baseline=self.ce_compile()[1][0]['vertices']
        self.assertLess(min(v[1] for v in baseline),255)
        result=self.ce_compile('$ZeroFlexDecay')[1][0]['vertices']
        self.assertEqual({v[1] for v in result},{255})

    def test_ce_auto_controller_range_and_toggle(self):
        self.ce_fixture()
        block='flexfile face.vta {\naddcontrollerbyflex generated -1 2\nflex smile frame 1\naddcontrollerbyflex\nflex other frame 2\n}\n%smile = smile\n'
        controllers,keys,_,_,_=self.ce_compile('',block)
        self.assertEqual(controllers,[('smile','generated',-1,2)])
        self.assertEqual([k['name'] for k in keys],['smile'])

    def test_ce_default_pose_bakes_mesh_and_rebases_flexes(self):
        block=self.ce_fixture().replace('defaultflex frame 0','defaultflex frame 1').replace('flex smile frame 1','flex smile frame 2')
        for flag,height in [('',.25),('$IgnoreDefaultFlexKey',.5)]:
            keys=self.ce_compile(flag,block)[1]
            self.assertEqual('default' in [k['name'] for k in keys],bool(flag))
            smile=next(k for k in keys if k['name']=='smile')
            self.assertAlmostEqual(smile['vertices'][0][2][2],height,places=3)
            vvd=(self.root/'models/face.vvd').read_bytes();p=struct.unpack_from('<i',vvd,56)[0]
            self.assertAlmostEqual(struct.unpack_from('<f',vvd,p+24)[0],0 if flag else .25)

    def test_ce_eye_scaling_and_independent_iris(self):
        block='eyeball eye root 1 2 3 material 2 0 iris .5\n'
        for flags,origin,radius,iris in [('$scale 2\n$EyeballScale 3',(3,6,9),1,2/3),
                        ('$scale 2\n$IgnoreEyeballScaling',(1,2,3),1,2),
                        ('$scale 2\n$EyeballScale 3\n$IgnoreEyeballIrisScale',(3,6,9),1,2)]:
            eye=self.ce_compile(flags,block)[2][0]
            self.assertEqual(eye[1],origin);self.assertEqual(eye[2],radius);self.assertAlmostEqual(eye[3],iris,places=5)

    def test_ce_bodygroup_face_blocks_and_material_edits_stay_scoped(self):
        block=self.ce_fixture()
        self.run_qc('$modelname face\n$bodygroup heads {\nstudio mesh.smd {\n'
                    'eyeball eye_a root 1 2 3 material 2 0 iris .5\n'+block+'}\n'
                    'studio mesh.smd {\neyeball eye_b root 4 5 6 material 2 0 iris .5\n}\nblank\n}\n')
        eyes=self.ce_data()[2]
        self.assertEqual([e[1] for e in eyes],[(1,2,3),(4,5,6)])
        self.assertEqual(len(self.ce_data()[4]),4) # includes run_qc's additional body
        self.run_qc('$modelname renamed\n$bodygroup heads {\nstudio mesh.smd renamemat material variant\n'
                    'studio mesh.smd renamematbyprefix other_\n}\n')
        d=self.mdl('renamed');self.assertIn(b'variant\0',d);self.assertIn(b'other_material\0',d);self.assertIn(b'material\0',d)

    def test_ce_outdir_and_cli_prefixes(self):
        self.write('inc/pre_part.qci','$modelname output\n')
        self.run_qc('$include inc/part.qci\n$includemodel anim.mdl\n','-InClUdEpReFiX','inc/part.qci','pre_',
                    '-IncludeAnimPrefix','pre_','-OutDir','custom')
        d=(self.root/'custom/models/output.mdl').read_bytes();self.assertIn(b'models/pre_anim.mdl\0',d)
        self.run_qc('$modelname output\n$OutDir other\n')
        self.assertTrue((self.root/'other/models/output.mdl').exists())

    def test_ce_buffer_limit_failure_does_not_overwrite_old_outputs(self):
        self.run_qc('$modelname safe\n');old=self.mdl('safe')
        self.run_qc('$modelname safe\n$MDLOutputBufferSize .0001\n',success=False)
        self.assertEqual(self.mdl('safe'),old)
        self.run_qc('$modelname safe\n$OutputBufferSize -1\n',success=False)
        self.assertEqual(self.mdl('safe'),old)

    def ce_dmx(self, global_options='', suboptions=''):
        self.write('face.dmx',(Path(__file__).parent/'fixtures/ce-facial.dmx').read_text())
        self.run_qc('$modelname dmx\n'+global_options+'\n$model face face.dmx '+suboptions+'\n')
        return self.ce_data('dmx')

    def test_ce_dmx_remap_translation_preserves_morph_deltas(self):
        baseline=self.ce_dmx()[1]
        shifted=self.ce_dmx('$RemapFlexToGlobal\n$definebone root "" 10 20 30 0 0 0 0 0 0 0 0 0')[1]
        self.assertEqual(len(baseline),len(shifted))
        for original,remapped in zip(baseline,shifted):
            self.assertEqual(original['vertices'],remapped['vertices'])

    def test_collision_bone_rename_updates_phy_hierarchy(self):
        points=[(0,0,0),(1,0,0),(0,1,0),(0,0,1)]
        faces=[(0,2,1),(0,1,3),(0,3,2),(1,2,3)]
        text='version 1\nnodes\n0 "root" -1\n1 "child" 0\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\n1 3 0 0 0 0 0\nend\ntriangles\n'
        for bone in (0,1):
            for face in faces:
                text+='material\n'
                for index in face:
                    x,y,z=points[index];text+=f'{bone} {x+3*bone} {y} {z} 0 0 1 0 0\n'
        self.write('tetra.smd',text+'end\n')
        self.scene_qc('$modelname physics\n$bonecullmethod none\n$body m tetra.smd\n'
                      '$collisionjoints tetra.smd { $mass 10 $rootbone root }\n'
                      '$renamebone root renamed_root\n$renamebone child renamed_child\n')
        data=(self.root/'models/physics.phy').read_bytes()
        self.assertIn(b'renamed_root',data);self.assertIn(b'renamed_child',data)
        self.assertIn(b'parent',data);self.assertIn(b'ragdollconstraint',data)
        self.assertNotIn(b'"name" "root"',data);self.assertNotIn(b'"name" "child"',data)

    def test_ce_dmx_two_bone_remap_preserves_weighted_position_deltas(self):
        import re
        fixture=(Path(__file__).parent/'fixtures/ce-facial.dmx').read_text()
        results=[]
        for weight in (1,0,.5):
            text=fixture.replace('"jointCount" "int" "1"','"jointCount" "int" "2"')
            values='\n'.join(f'"{v}"' for v in [weight,1-weight]*3)
            text=re.sub(r'("jointWeights" "float_array"\s*\[).*?(\])',lambda m:m[1]+values+m[2],text,flags=re.S)
            text=re.sub(r'("jointIndices" "int_array"\s*\[).*?(\])',lambda m:m[1]+'"0", "1", "0", "1", "0", "1"'+m[2],text,flags=re.S)
            self.write('blend.dmx',text)
            self.run_qc('$modelname blend\n$bonecullmethod none\n$RemapFlexToGlobal\n'
                        '$definebone root "" 0 0 0 90 0 0 0 0 0 0 0 0\n'
                        '$definebone mesh "" 0 0 0 0 0 0 0 0 0 0 0 0\n$model face blend.dmx\n')
            results.append(self.ce_data('blend')[1][0]['vertices'][0][2][:3])
        for a,b,mixed in zip(*results): self.assertAlmostEqual(mixed,.5*(a+b),delta=.002)

    def test_ce_dmx_smooth_normals_include_stationary_vertices(self):
        baseline=self.ce_dmx()[1][0]['vertices'];self.assertEqual(len(baseline),1)
        computed=self.ce_dmx('$ComputeDeltaNormals')[1][0]['vertices'];self.assertEqual(len(computed),3)
        for va in computed:
            for actual,expected in zip(va[2][3:],(.235595703125,.235595703125,-.05718994140625)):
                self.assertAlmostEqual(actual,expected,delta=.0003)
        for sub in ['IgnoreComputeDeltaNormals','IgnoreComputeNormalsAndWrinkles']:
            self.assertEqual(len(self.ce_dmx('$ComputeNormalsAndWrinkles',sub)[1][0]['vertices']),1)

    def test_ce_dmx_wrinkle_generation_and_local_disable(self):
        base=self.ce_dmx()[1][0]['vertices'];self.assertEqual(base[0][3],8192)
        self.assertEqual(self.ce_dmx('$ComputeWrinkles')[1][0]['vertices'][0][3],8192)
        disabled=self.ce_dmx('$ComputeWrinkles','IgnoreComputeWrinkles')[1][0]['vertices']
        self.assertIsNone(disabled[0][3])

    def test_ce_dmx_defaq_scale_can_be_disabled_independently(self):
        baseline=self.ce_dmx()[1][0]['vertices'][0][2][2]
        self.assertAlmostEqual(self.ce_dmx('$DefaqScale')[1][0]['vertices'][0][2][2],baseline*10)
        self.assertAlmostEqual(self.ce_dmx('$DefaqScale\n$IgnoreDMXDefaq')[1][0]['vertices'][0][2][2],baseline)

    def test_ce_invalid_eye_scale_and_flex_scale_fail(self):
        self.run_qc('$modelname invalid\n$EyeballScale 0\n',success=False)
        self.run_qc('$modelname invalid\n$EyeballScale nan\n',success=False)
        block=self.ce_fixture().replace('flex smile frame 1','flex smile frame 1 fscale nan')
        self.run_qc('$modelname invalid\n$model face mesh.smd {\n'+block+'}\n',success=False)


    def test_ce_repeated_global_flags_toggle_off(self):
        self.assertEqual(self.ce_compile('$ZeroFlexDecay\n$ZeroFlexDecay')[1],self.ce_compile()[1])
        self.assertEqual([k['name'] for k in self.ce_compile('$AddInvStudioFlexes\n$AddInvStudioFlexes')[1]],['smile'])

    def test_ce_fscale_scales_normal_deltas_too(self):
        block=self.ce_fixture()
        p=self.root/'face.vta';p.write_text(p.read_text().replace('0 0 0 .25 0 0 1','0 0 0 .25 .2 0 .98'))
        baseline=self.ce_compile('',block)[1][0]['vertices'][0][2]
        scaled=self.ce_compile('',block.replace('flex smile frame 1','flex smile frame 1 fscale 2'))[1][0]['vertices'][0][2]
        self.assertNotEqual(baseline[3],0)
        for a,b in zip(baseline,scaled):self.assertAlmostEqual(a*2,b,delta=.0005)

    def test_ce_dmx_remapping_rotates_deltas_to_authored_bind_pose(self):
        definition='$definebone root "" 0 0 0 0 0 90 0 0 0 0 0 0\n'
        before=self.ce_dmx(definition)[1][0]['vertices'][0][2][:3]
        after=self.ce_dmx(definition+'$RemapFlexToGlobal')[1][0]['vertices'][0][2][:3]
        self.assertEqual(before,(0,0,.25))
        for a,b in zip(after,(0,-.25,0)):self.assertAlmostEqual(a,b,places=4)

    def test_ce_force_collapse_overrides_keep_and_defined_bone(self):
        qc='$modelname bone_rules\n$bonecullmethod none\n$definebone unused_child root 0 0 1 0 0 0 0 0 0 0 0 0\n$donotcollapse unused_child\n$alwayscollapse unused_child\n'
        self.run_qc(qc);self.assertEqual(struct.unpack_from('<i',self.mdl('bone_rules'),156)[0],2)
        self.run_qc('$CEBoneRules\n'+qc);self.assertEqual(struct.unpack_from('<i',self.mdl('bone_rules'),156)[0],1)

    def test_ce_bind_to_one_bone_changes_serialized_weights(self):
        p=self.root/'mesh.smd';p.write_text(p.read_text().replace('0 0 0 1 0 0 0','0 0 0 0 0 0 0').replace('0 0 1 0 1\n','0 0 1 0 1\n'))
        lines=p.read_text().splitlines();start=lines.index('triangles')
        for i in range(start+2,len(lines)-1):lines[i]+=' 2 0 .7 1 .3'
        p.write_text('\n'.join(lines)+'\n')
        counts=[]
        for sub in ['', 'BindToOneBone']:
            self.run_qc('$modelname weights\n$bonecullmethod none\n$model face mesh.smd '+sub+'\n')
            d=(self.root/'models/weights.vvd').read_bytes();offset=struct.unpack_from('<i',d,56)[0]
            counts.append(d[offset+15])
            if sub:self.assertEqual(struct.unpack_from('<f',d,offset)[0],1)
        self.assertEqual(counts,[2,1])

    def test_ce_procedural_pushd_switch_selects_source_directory(self):
        self.write('procedural.vrd','<aimconstraint> unused_child root root\n')
        self.write('sub/procedural.vrd','<helper> malformed\n')
        text='$modelname procedural\n$pushd sub\n$proceduralbones procedural.vrd\n$popd\n'
        self.run_qc(text)
        output=self.run_qc('$PUSHDProcedural 1\n'+text,success=False)
        self.assertIn('<helper> expects',output)

    def test_ce_legacy_clamp_accepts_small_models(self):
        self.run_qc('$modelname legacy\n$UseLegacyClampMethod\n')
        self.assertEqual(struct.unpack_from('<i',self.mdl('legacy'),232)[0],1)

    def test_ce_hbox_ignore_child_keeps_mesh_bounds(self):
        p=self.root/'mesh.smd';s=p.read_text().replace('1 0 0 1 0 0 0','1 100 0 0 0 0 0').replace('0 1 0 0 0 0 1 1 0','0 3 3 0 0 0 1 1 0').replace('0 0 1 0 0 0 1 0 1','0 0 0 3 0 0 1 0 1');p.write_text(s)
        bounds=[]
        for flags in ['', '$HBoxIgnoreChild\n']:
            self.run_qc('$modelname hitboxes\n$bonecullmethod none\n'+flags)
            d=self.mdl('hitboxes');hset=struct.unpack_from('<i',d,176)[0]
            self.assertGreater(struct.unpack_from('<i',d,hset+4)[0],0)
            box=hset+struct.unpack_from('<i',d,hset+8)[0]
            bounds.append(max(abs(v) for v in struct.unpack_from('<6f',d,box+8)))
        self.assertEqual(bounds,[100,3])

    def test_ce_legacy_no_auto_dmx_rules_removes_previous_controllers(self):
        self.write('face.dmx',(Path(__file__).parent/'fixtures/ce-facial.dmx').read_text())
        for option,count in [('NoAutoDMXRules',1),('NoAutoDMXRulesLegacy',0)]:
            self.run_qc('$modelname no_auto\n$model first face.dmx\n$model second face.dmx {\n'+option+'\n}\n')
            d=self.mdl('no_auto');self.assertEqual(struct.unpack_from('<i',d,268)[0],count)
            if count==0:self.assertEqual(struct.unpack_from('<i',d,276)[0],0)


    def test_ce_ignore_eyelid_preserves_flex_rules_without_eye_binding(self):
        self.ce_fixture()
        block=('eyeball eye root 0 0 0 material 2 0 iris .5\n'
               'eyelid upper face.vta lowerer 1 -.2 neutral 0 0 raiser 2 .2 split 0 eyeball eye\n'
               'flexcontroller eyelid range -1 1 lid\n%upper = lid\n')
        results=[]; bindings=[]
        for flags in ['', '$IgnoreEyelid']:
            data=self.ce_compile(flags,block);results.append(data[:2]+(data[3],))
            d=self.mdl('face');model=data[4][0];eye=model+struct.unpack_from('<i',d,model+104)[0]
            index=struct.unpack_from('<i',d,eye+116)[0];entry=struct.unpack_from('<i',d,264)[0]+index*4
            start=entry+struct.unpack_from('<i',d,entry)[0];bindings.append(d[start:d.index(b'\0',start)].decode())
        self.assertEqual(results[0],results[1])
        self.assertEqual(bindings,['upper','dummy_eyelid'])



    def vtx_triangles(self, name, extension='dx90', full=False, lod=0):
        from collections import Counter
        data=(self.root/f'models/{name}.{extension}.vtx').read_bytes()
        body=struct.unpack_from('<i',data,32)[0]
        model=body+struct.unpack_from('<i',data,body+4)[0]
        level=model+struct.unpack_from('<i',data,model+4)[0]+lod*12
        meshes,offset=struct.unpack_from('<2i',data,level)
        triangles=Counter()
        for mi in range(meshes):
            mesh=level+offset+mi*9
            groups,goff=struct.unpack_from('<2i',data,mesh)
            for gi in range(groups):
                group=mesh+goff+gi*(33 if full else 25)
                nv,vo,ni,io,ns,so=struct.unpack_from('<6i',data,group)
                vertices=[struct.unpack_from('<H',data,group+vo+v*9+4)[0] for v in range(nv)]
                for si in range(ns):
                    strip=group+so+si*(35 if full else 27)
                    count,base=struct.unpack_from('<2i',data,strip)
                    self.assertEqual(data[strip+18]&1,1)
                    ids=struct.unpack_from('<'+'H'*count,data,group+io+base*2)
                    self.assertTrue(all(i<nv for i in ids))
                    for start in range(0,len(ids),3):
                        tri=tuple(vertices[i] for i in ids[start:start+3])
                        triangles[(mi,min(tri,tri[1:]+tri[:1],tri[2:]+tri[:2]))]+=1
        return triangles

    def test_nvtristrip_qc_and_cli_preserve_triangles_and_lods(self):
        self.scene_fixture()
        for full in (False,True):
            qc=f'$modelname strips\n$vtxformat {int(full)}\n$body m scene.gltf\n$lod 10 {{ }}\n'
            self.scene_qc(qc)
            before={(ext,lod):self.vtx_triangles('strips',ext,full,lod) for ext in (('dx90',) if full else ('dx80','dx90')) for lod in (0,1)}
            for flag,args in (('$UseLegacyStripify\n',()),('',('-nvtristrip',))):
                self.scene_qc(flag+qc,*args)
                after={(ext,lod):self.vtx_triangles('strips',ext,full,lod) for ext in (('dx90',) if full else ('dx80','dx90')) for lod in (0,1)}
                self.assertEqual(before,after)

    def test_smd_fallback_bone_is_validated(self):
        original=(self.root/'mesh.smd').read_text()
        for bone in ('-1','999'):
            self.write('bad.smd',original.replace('0 0 0 0 0 0 1 0 0',bone+' 0 0 0 0 0 1 0 0'))
            output=self.scene_qc('$modelname bad\n$body m bad.smd\n',success=False)
            self.assertIn('bogus bone index',output)
            self.assertFalse((self.root/'models/bad.mdl').exists())

    def test_lod_bone_replacement_cycles_and_conflicts_fail(self):
        for options,error in [('replacebone root child\nreplacebone child root','cyclic LOD'),
                              ('replacebone child root\nreplacebone child child','conflicting LOD')]:
            output=self.run_qc('$modelname bad\n$bonecullmethod none\n$lod 10 {\n'+options+'\n}\n',success=False)
            self.assertIn(error,output)
            self.assertFalse((self.root/'models/bad.mdl').exists())
        self.run_qc('$modelname identity\n$lod 10 { replacebone root root }\n')
        self.mdl('identity')

    def test_large_constant_animation_uses_finite_full_precision_position(self):
        source=(self.root/'mesh.smd').read_text()
        prefix=source.split('triangles\n')[0].removesuffix('end\n')
        self.write('far.smd',prefix+'time 1\n0 100000 0 0 0 0 0\nend\n')
        self.run_qc('$modelname far\n$sequence moved far.smd { frame 1 1 }\n')
        data=self.mdl('far');anim=struct.unpack_from('<i',data,184)[0]
        self.assertTrue(struct.unpack_from('<i',data,anim+12)[0]&0x40)
        poses=self.animation_poses('far','moved')
        self.assertTrue(all(__import__('math').isfinite(v) for pose in poses for v in pose))
        self.assertAlmostEqual(sum(v*v for v in poses[0][:3])**.5,100000,delta=2)

    def test_long_animation_avoids_signed_rle_offsets(self):
        import math
        poses=''.join(f'time {i}\n0 {math.sin(i*.13)*10} {math.cos(i*.17)*10} {math.sin(i*.23)*10} {math.sin(i*.11)*.2} {math.cos(i*.19)*.2} {math.sin(i*.29)*.2}\n' for i in range(3500))
        self.write('long.smd','version 1\nnodes\n0 "root" -1\nend\nskeleton\n'+poses+'end\n')
        self.run_qc('$modelname long\n$sectionframes 10000 10000\n$sequence move long.smd\n')
        data=self.mdl('long');anim=struct.unpack_from('<i',data,184)[0]
        self.assertTrue(struct.unpack_from('<i',data,anim+12)[0]&0x40)
        actual=self.animation_poses('long','move');self.assertEqual(len(actual),3500)
        for i in (0,255,256,3499):
            self.assertTrue(all(math.isfinite(v) for v in actual[i]))
            self.assertAlmostEqual(actual[i][2],math.sin(i*.23)*10,delta=.02)

    def test_dmx_nonfinite_geometry_and_morphs_fail_before_output(self):
        import re
        fixture=(Path(__file__).parent/'fixtures/ce-facial.dmx').read_text()
        for key in ('positions','normals','jointWeights'):
            pattern=r'("'+key+r'"\s+"[^"]+"\s*\[\s*")([^"]+)'
            bad=re.sub(pattern,lambda m:m[1]+'nan'+((' '+m[2].split(' ',1)[1]) if ' ' in m[2] else ''),fixture,count=1)
            self.assertNotEqual(bad,fixture);self.write('bad.dmx',bad)
            output=self.scene_qc('$modelname bad\n$model m bad.dmx { }\n',success=False)
            self.assertIn('non-finite DMX attribute',output)
            self.assertFalse((self.root/'models/bad.mdl').exists())

    def test_collision_long_names_and_surface_properties_are_not_truncated(self):
        name='bone_'+('a'*600);surface='surface_'+('b'*600)
        self.write('tetra.smd','version 1\nnodes\n0 "'+name+'" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\ntriangles\n'+''.join('material\n'+''.join(f'0 {x} {y} {z} 0 0 1 0 0\n' for x,y,z in face) for face in [((0,0,0),(0,1,0),(1,0,0)),((0,0,0),(1,0,0),(0,0,1)),((0,0,0),(0,0,1),(0,1,0)),((1,0,0),(0,1,0),(0,0,1))])+'end\n')
        self.scene_qc('$modelname physics\n$surfaceprop "'+surface+'"\n$body m tetra.smd\n$collisionmodel tetra.smd { $mass 10 }\n')
        data=(self.root/'models/physics.phy').read_bytes()
        self.assertIn(('"surfaceprop" "'+surface+'"\n').encode(),data)
        self.assertIn(('"rootname" "'+name+'"\n').encode(),data)


    def test_rle_repeat_runs_and_animation_section_seams(self):
        for sections,frames in ((False,262),(True,122)):
            samples=[1 if i<256 else 2 for i in range(frames)] if not sections else [i*.125 for i in range(frames)]
            poses=''.join(f'time {i}\n0 {value} 0 0 0 0 0\n' for i,value in enumerate(samples))
            self.write('runs.smd','version 1\nnodes\n0 "root" -1\nend\nskeleton\n'+poses+'end\n')
            self.run_qc('$modelname runs\n'+('$sectionframes 30 30\n' if sections else '$sectionframes 1000 1000\n')+'$sequence move runs.smd\n')
            actual=self.animation_poses('runs','move');self.assertEqual(len(actual),frames)
            for i in ((0,29,30,31,59,60,61,121) if sections else (0,254,255,256,261)):
                self.assertAlmostEqual(sum(x*x for x in actual[i][:3])**.5,samples[i],delta=.015)

    def test_ik_chain_and_procedural_helper_survive_bone_collapse_and_rename(self):
        nodes='0 "hip" -1\n1 "knee" 0\n2 "foot" 1\n3 "unused" 0\n4 "helper" 0\n'
        bind='0 0 0 0 0 0 0\n1 1 0 0 0 0 0\n2 1 .1 0 0 0 0\n3 0 0 0 0 0 0\n4 0 0 1 0 0 0\n'
        mesh='version 1\nnodes\n'+nodes+'end\nskeleton\ntime 0\n'+bind+'end\ntriangles\nmaterial\n2 0 0 0 0 0 1 0 0\n2 1 0 0 0 0 1 1 0\n2 0 1 0 0 0 1 0 1\nend\n'
        self.write('chain.smd',mesh)
        self.write('driver.smd','version 1\nnodes\n'+nodes+'end\nskeleton\ntime 0\n'+bind+'time 1\n'+bind.replace('4 0 0 1 0 0 0','4 .25 0 1 0 .2 0')+'end\n')
        self.scene_qc('$modelname chain\n$body m chain.smd\n$ikchain leg foot knee 0 1 0\n$ikautoplaylock leg 1 .5\n$NekoDriverBone hip {\npose driver.smd\ntrigger 90 0\ntrigger 90 1\nhelper\n}\n$renamebone hip renamed_hip\n$sequence idle chain.smd\n')
        data=self.mdl('chain');count,bones=struct.unpack_from('<2i',data,156)
        names=[]
        for i in range(count):
            p=bones+i*216;start=p+struct.unpack_from('<i',data,p)[0];names.append(data[start:data.index(b'\0',start)].decode())
        self.assertEqual(set(names),{'renamed_hip','knee','foot','helper'})
        chains,index=struct.unpack_from('<2i',data,284);self.assertEqual(chains,1)
        links,offset=struct.unpack_from('<2i',data,index+8);self.assertEqual(links,3)
        self.assertEqual([names[struct.unpack_from('<i',data,index+offset+i*28)[0]] for i in range(3)],['renamed_hip','knee','foot'])
        helper=bones+names.index('helper')*216
        self.assertEqual(struct.unpack_from('<i',data,helper+164)[0],2)
        self.assertEqual(struct.unpack_from('<i',data,helper+160)[0]&4,4)
        locks,offset=struct.unpack_from('<2i',data,320);self.assertEqual(locks,1)
        chain,pos,rot=struct.unpack_from('<iff',data,offset)
        self.assertEqual(chain,0);self.assertAlmostEqual(pos,1);self.assertAlmostEqual(rot,.5)

    def test_dmx_corrective_and_dominator_rules_evaluate_numerically(self):
        import math
        self.write('face.dmx',(Path(__file__).parent/'fixtures/ce-facial.dmx').read_text())
        self.scene_qc('$modelname face\n$model m face.dmx { NoAutoDMXRules }\n$flexcontroller test range 0 1 A B D\n$flexcorrective smile A B\n$flexdominate smile D\n')
        controllers,keys,_,rules,_=self.ce_data()
        self.assertTrue(any(k['name']=='smile' and k['vertices'] for k in keys))
        operations=next(ops for name,ops in rules if name=='smile')
        for values in ({'A':.4,'B':.5,'D':.2},{'A':1,'B':1,'D':1},{'A':0,'B':1,'D':0}):
            stack=[]
            for op,value in operations:
                if op==2:stack.append(values[controllers[value][0]])
                elif op in (18,19):
                    product=math.prod(stack[-value:]);del stack[-value:]
                    if op==18:stack.append(product)
                    else:stack[-1]*=1-product
                else:self.fail(f'unexpected flex opcode {op}')
            self.assertEqual(len(stack),1)
            self.assertAlmostEqual(stack[0],values['A']*values['B']*(1-values['D']),places=6)

    def test_nvtristrip_skin_palettes_match_vvd_across_lod_replacements(self):
        nodes='\n'.join(['0 "root" -1']+[f'{i} "b{i}" 0' for i in range(1,70)])
        poses='\n'.join(f'{i} 0 0 0 0 0 0' for i in range(70))
        triangles=''
        for face in range(30):
            triangles+='material\n'
            for corner,(dx,dy) in enumerate(((0,0),(1,0),(0,1))):
                bone=1+(face*3+corner)%69;triangles+=f'{bone} {face*2+dx} {dy} 0 0 0 1 {dx} {dy} 2 0 .4 {bone} .6\n'
        self.write('skin.smd','version 1\nnodes\n'+nodes+'\nend\nskeleton\ntime 0\n'+poses+'\nend\ntriangles\n'+triangles+'end\n')
        for mode in ('','$UseLegacyStripify\n'):
            self.scene_qc('$modelname skin\n$bonecullmethod none\n'+mode+'$body m skin.smd\n$lod 10 { replacebone b65 root }\n')
            mdl=self.mdl('skin');bp=struct.unpack_from('<i',mdl,236)[0];model=bp+struct.unpack_from('<i',mdl,bp+12)[0]
            model_vertex=struct.unpack_from('<i',mdl,model+84)[0];mesh=model+struct.unpack_from('<i',mdl,model+76)[0];mesh_vertex=struct.unpack_from('<i',mdl,mesh+12)[0]
            vvd=(self.root/'models/skin.vvd').read_bytes();start=struct.unpack_from('<i',vvd,56)[0];fixups,fixup_start=struct.unpack_from('<2i',vvd,48)
            if fixups:
                spans=[struct.unpack_from('<3i',vvd,fixup_start+i*12) for i in range(fixups)]
                vvd=b''.join(vvd[start+source*48:start+(source+count)*48] for lod,source,count in spans if lod>=0)
            else:vvd=vvd[start:]
            vstart=model_vertex+mesh_vertex*48
            for extension in ('dx80','dx90'):
                data=(self.root/f'models/skin.{extension}.vtx').read_bytes();body=struct.unpack_from('<i',data,32)[0];vm=body+struct.unpack_from('<i',data,body+4)[0]
                lo=vm+struct.unpack_from('<i',data,vm+4)[0]
                for lod in (0,1):
                    level=lo+lod*12;mesh=level+struct.unpack_from('<i',data,level+4)[0]
                    ng,go=struct.unpack_from('<2i',data,mesh)
                    for g in range(ng):
                        group=mesh+go+g*25;nv,vo,ni,io,ns,so=struct.unpack_from('<6i',data,group)
                        if not data[group+24]&2:continue
                        if extension=='dx90' and lod==0:self.assertGreater(ns,1)
                        for s in range(ns):
                            strip=group+so+s*27;count,offset=struct.unpack_from('<2i',data,strip);nc,co=struct.unpack_from('<2i',data,strip+19)
                            palette=dict(struct.unpack_from('<ii',data,strip+co+c*8) for c in range(nc))
                            self.assertLessEqual(len(palette),16 if extension=='dx80' else 53)
                            indices=struct.unpack_from('<'+'H'*count,data,group+io+offset*2)
                            for i in indices:
                                vertex=group+vo+i*9;original=struct.unpack_from('<H',data,vertex+4)[0]
                                for slot in range(data[vertex+3]):
                                    weight=data[vertex+slot];hardware=data[vertex+6+slot]
                                    self.assertEqual(palette[hardware],vvd[vstart+original*48+12+weight])


    def test_ik_error_offset_overflow_preserves_existing_output(self):
        import math
        nodes='0 "hip" -1\n1 "knee" 0\n2 "foot" 1\n'
        bind='0 0 0 0 0 0 0\n1 1 0 0 0 0 0\n2 1 .1 0 0 0 0\n'
        self.write('chain.smd','version 1\nnodes\n'+nodes+'end\nskeleton\ntime 0\n'+bind+'end\ntriangles\nmaterial\n2 0 0 0 0 0 1 0 0\n2 1 0 0 0 0 1 1 0\n2 0 1 0 0 0 1 0 1\nend\n')
        self.scene_qc('$modelname longik\n$body m chain.smd\n')
        previous={p.name:p.read_bytes() for p in (self.root/'models').glob('longik.*')}
        text='version 1\nnodes\n'+nodes+'end\nskeleton\n'
        for i in range(4500):
            text+=f'time {i}\n0 0 0 0 0 0 0\n1 {1+math.sin(i*.13)*.2} {math.cos(i*.17)*.2} {math.sin(i*.23)*.2} {math.sin(i*.11)*.3} {math.cos(i*.19)*.3} {math.sin(i*.29)*.3}\n2 {1+math.cos(i*.14)*.2} {math.sin(i*.18)*.2} {math.cos(i*.24)*.2} {math.cos(i*.12)*.3} {math.sin(i*.2)*.3} {math.cos(i*.3)*.3}\n'
        self.write('move.smd',text+'end\n')
        output=self.scene_qc('$modelname longik\n$body m chain.smd\n$ikchain leg foot\n$sequence move move.smd { ikrule leg touch hip usesource }\n',success=False)
        self.assertIn('32767',output);self.assertIn('write error',output)
        self.assertEqual({p.name:p.read_bytes() for p in (self.root/'models').glob('longik.*')},previous)

    def test_bodygroup_combination_capacity_is_checked(self):
        groups=lambda n: ''.join(f'$bodygroup choice{i} {{ blank\nblank\n}}\n' for i in range(n))
        self.run_qc('$modelname combinations\n'+groups(31))
        d=self.mdl('combinations');count,index=struct.unpack_from('<2i',d,232)
        self.assertEqual(count,32)
        self.assertEqual(struct.unpack_from('<i',d,index+30*16+8)[0],1<<30)
        old=d
        text=self.run_qc('$modelname combinations\n'+groups(32),success=False)
        self.assertIn('bodygroup combination count exceeds',text)
        self.assertEqual(self.mdl('combinations'),old)
        text=self.run_qc('$modelname combinations\n$bodygroup empty { }\n',success=False)
        self.assertIn('expects at least one choice',text)
        self.assertEqual(self.mdl('combinations'),old)

    def test_final_bodygroup_product_does_not_reject_valid_bases(self):
        groups=''.join(f'$bodygroup choice{i} {{ blank\nblank\n}}\n' for i in range(30))
        text=self.run_qc('$modelname widechoices\n'+groups+'$bodygroup last { blank\nblank\nblank\n}\n')
        self.assertIn('preserving valid MDL bases',text)
        d=self.mdl('widechoices');count,index=struct.unpack_from('<2i',d,232)
        self.assertEqual(struct.unpack_from('<i',d,index+30*16+8)[0],1<<30)
        old=d
        text=self.run_qc('$modelname widechoices\n'+groups+'$bodygroup last { blank\nblank\nblank\n}\n$modelgrouppreset invalid { last 2 }\n',success=False)
        self.assertIn('preset selection exceeds',text)
        self.assertEqual(self.mdl('widechoices'),old)

    def test_skin_table_budget_precedes_output_replacement(self):
        self.run_qc('$modelname skins\n$texturegroup family {\n'+'{ material }\n'*1001+'}\n')
        old=self.mdl('skins');self.assertEqual(struct.unpack_from('<i',old,224)[0],1001)
        rows='{ material }\n'+''.join('{ material'+str(i)+' }\n' for i in range(20))
        text=self.run_qc('$modelname skins\n$MDLOutputBufferSize .0002\n$texturegroup family {\n'+rows+'}\n',success=False)
        self.assertIn('skin table exceeds output capacity',text)
        self.assertEqual(self.mdl('skins'),old)

    def test_global_clamp_preserves_materials_lods_flexes_and_choices(self):
        import json
        doc=json.loads(scene_bytes());doc['materials'].append({'name':'second'})
        import copy
        doc['meshes'].append(copy.deepcopy(doc['meshes'][0]));doc['meshes'][1]['primitives'][0]['material']=1;doc['nodes'][2]['mesh']=1
        self.write('scene.gltf',json.dumps(doc))
        self.scene_qc('$modelname clamped\n$UseLegacyClampMethod\n$MaxVerts 4\n$bodygroup heads {\nstudio scene.gltf { flex Smile\nflexcontroller test strength\n%Smile = strength\n}\nblank\n}\n$lod 10 { }\n')
        d=self.mdl('clamped');count,index=struct.unpack_from('<2i',d,232)
        self.assertEqual(count,2);all_mats=[];all_flex=[]
        for bp in (index,index+16):
            choices,base,offset=struct.unpack_from('<3i',d,bp+4);self.assertEqual((choices,base),(2,1))
            model=bp+offset;num_meshes,meshes,vertices=struct.unpack_from('<3i',d,model+72)
            self.assertEqual(vertices,3);self.assertEqual(num_meshes,1)
            self.assertEqual(struct.unpack_from('<i',d,model+148+80)[0],0) # blank alternative
            mesh=model+meshes;all_mats.append(struct.unpack_from('<i',d,mesh)[0])
            nf,of=struct.unpack_from('<2i',d,mesh+16)
            self.assertEqual(nf,1)
            key=mesh+of;nv,ov=struct.unpack_from('<2i',d,key+20);self.assertEqual(nv,3)
            for v in range(nv):
                entry=key+ov+v*16;self.assertLess(struct.unpack_from('<H',d,entry)[0],3)
                all_flex.append(struct.unpack_from('<3e',d,entry+4))
        self.assertEqual(set(all_mats),{0,1});self.assertEqual(len(all_flex),6)
        for ext in ('dx80','dx90'):
            vtx=(self.root/f'models/clamped.{ext}.vtx').read_bytes();parts,po=struct.unpack_from('<2i',vtx,28)
            self.assertEqual(parts,2)
            for bp in (po,po+8):
                nm,mo=struct.unpack_from('<2i',vtx,bp);self.assertEqual(nm,2)
                model=bp+mo;lods,lo=struct.unpack_from('<2i',vtx,model);self.assertEqual(lods,2)
                for lod in range(lods):
                    lr=model+lo+lod*12;meshes,moff=struct.unpack_from('<2i',vtx,lr);self.assertEqual(meshes,1)
                    mesh=lr+moff;ng,go=struct.unpack_from('<2i',vtx,mesh);self.assertEqual(ng,1)
                    self.assertEqual(struct.unpack_from('<i',vtx,mesh+go+8)[0],3)

    def test_localhierarchy_keeps_unweighted_parent_and_rejects_self(self):
        source=(self.root/'mesh.smd').read_text().replace('1 \"unused_child\" 0\nend', '1 \"unused_child\" 0\n2 \"helper\" 0\nend').replace('1 0 0 1 0 0 0\nend', '1 0 0 1 0 0 0\n2 5 0 0 0 0 0\nend')
        self.write('mesh.smd',source)
        self.run_qc('$modelname hierarchy\n$sequence move mesh.smd { localhierarchy unused_child helper }\n')
        d=self.mdl('hierarchy');self.assertEqual(struct.unpack_from('<i',d,156)[0],3)
        anim=struct.unpack_from('<i',d,184)[0];n,offset=struct.unpack_from('<2i',d,anim+72)
        self.assertEqual(n,1);self.assertEqual(struct.unpack_from('<2i',d,anim+offset),(1,2))
        result=self.run_qc('$modelname hierarchy\n$sequence move mesh.smd { localhierarchy root root }\n',success=False)
        self.assertIn('cannot parent a bone to itself',result);self.assertEqual(self.mdl('hierarchy'),d)

    def test_dmx_corner_stream_lengths_and_indices_are_validated(self):
        import re
        fixture=(Path(__file__).parent/'fixtures/ce-facial.dmx').read_text()
        for name,values,message in [('normalsIndices','"0", "1"','corner count mismatch'),('positionsIndices','"0", "1", "99"','index out of range'),('normalsIndices','"-1", "1", "2"','index out of range')]:
            bad=re.sub(r'("'+name+r'"\s+"int_array"\s*\[)[^\]]*',lambda m:m[1]+values,fixture,count=1)
            self.write('bad.dmx',bad)
            result=self.scene_qc('$modelname bad\n$body m bad.dmx\n',success=False)
            self.assertIn(message,result);self.assertFalse((self.root/'models/bad.mdl').exists())
        primary='"position$0" "vector3_array" [ "0 0 0", "1 0 0", "0 1 0" ]\n"position$0Indices" "int_array" [ "0", "1", "2" ]\n'
        both=re.sub(r'("positions"\s+"vector3_array"\s*\[)[^\]]*',lambda m:m[1]+'"0 0 0"',fixture,count=1)
        start=both.index('"DmeVertexData"')
        both=both[:start]+both[start:].replace('"name" "string" "bind"','"name" "string" "bind"\n'+primary,1)
        self.write('aliases.dmx',both)
        self.scene_qc('$modelname aliases\n$body m aliases.dmx\n')
        self.assertEqual(struct.unpack_from('<i',(self.root/'models/aliases.vvd').read_bytes(),16)[0],3)
        bad=fixture.replace('"name" "string" "bind"','"name" "string" "bind"\n"balance" "float_array" [ "nan" ]',1)
        self.write('bad.dmx',bad);self.assertIn('non-finite DMX',self.scene_qc('$modelname bad\n$body m bad.dmx\n',success=False))

    def test_collision_large_mass_bias_stays_finite_and_negative_fails(self):
        import re,math
        points=[(0,0,0),(10,0,0),(0,10,0),(0,0,10)];faces=[(0,2,1),(0,1,3),(0,3,2),(1,2,3)]
        mesh='version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\ntriangles\n'
        for face in faces:
            mesh+='material\n'+''.join(f'0 {points[v][0]} {points[v][1]} {points[v][2]} 0 0 1 0 0\n' for v in face)
        self.write('tetra.smd',mesh+'end\n')
        qc='$modelname physics\n$body m tetra.smd\n$collisionmodel tetra.smd { $mass 10 $jointmassbias root %s }\n'
        self.scene_qc(qc%'1e38')
        data=(self.root/'models/physics.phy').read_bytes();mass=float(re.search(rb'"mass" "([^"]+)"',data)[1]);self.assertTrue(math.isfinite(mass));self.assertAlmostEqual(mass,10,places=3)
        text=self.scene_qc(qc%'-1',success=False);self.assertIn('mass bias must be positive',text)
        self.assertEqual((self.root/'models/physics.phy').read_bytes(),data)

    def test_opt_in_concave_collision_decomposes_connected_geometry(self):
        import re
        outline=[(0,0),(2,0),(2,1),(1,1),(1,2),(0,2)]
        vertices=[(x,y,z) for z in (0,1) for x,y in outline]
        cap=[(0,1,3),(1,2,3),(0,3,5),(3,4,5)]
        faces=[tuple(reversed(f)) for f in cap]+[tuple(v+6 for v in f) for f in cap]
        for a in range(6):
            b=(a+1)%6;faces.extend([(a,b,b+6),(a,b+6,a+6)])
        mesh='version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\ntriangles\n'
        for face in faces:
            mesh+='material\n'+''.join(f'0 {vertices[v][0]} {vertices[v][1]} {vertices[v][2]} 0 0 1 0 0\n' for v in face)
        self.write('concave.smd',mesh+'end\n')
        qc='$modelname concave\n$body m concave.smd\n$collisionmodel concave.smd { $mass 10 $maxconvexpieces 4 %s }\n'
        self.scene_qc(qc%'$concave');data=(self.root/'models/concave.phy').read_bytes()
        before=float(re.search(rb'"volume" "([^"]+)"',data)[1])
        output=self.scene_qc(qc%'$decomposeconcave');data=(self.root/'models/concave.phy').read_bytes()
        after=float(re.search(rb'"volume" "([^"]+)"',data)[1]);pieces=int(re.search(r'Decomposed collision .*: (\d+) convex pieces',output)[1])
        self.assertGreater(pieces,1);self.assertLessEqual(pieces,4)
        self.assertLess(after,before-.05);self.assertGreater(after,2.5)

if __name__ == "__main__":
    unittest.main()
