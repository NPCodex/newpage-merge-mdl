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

COMPILER = str(Path(sys.argv.pop(1)).resolve())


class Compatibility(unittest.TestCase):
    def scene_qc(self,text,*args,success=True):
        qc=self.write('scene.qc',text)
        result=subprocess.run([COMPILER,str(qc),'-game',str(self.root),*args],capture_output=True,text=True,errors='replace')
        self.assertEqual(result.returncode==0,success,result.stdout+result.stderr)
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
        for a,b in zip(plain,raw):
            for x,y in zip(a,b): self.assertAlmostEqual(x,y,places=3)
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

    def test_ce_unimplemented_legacy_algorithms_fail_explicitly(self):
        for option in ['UseLegacyClampMethod','UseLegacyStripify']:
            output=self.run_qc('$modelname legacy\n$'+option+'\n',success=False)
            self.assertIn('legacy CE algorithm is not implemented',output)
            self.assertFalse((self.root/'models/legacy.mdl').exists())


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


if __name__ == "__main__":
    unittest.main()
