"""Bounded face, bone-rule and historical-fix integration acceptance cases."""
from pathlib import Path
import base64
import copy
import json
import re
import struct
from scene_fixtures import scene_bytes


class IntegrationRigCases:
    def test_integration_bbox_diagnostic_locates_bone_frame_and_source(self):
        nodes='0 "root" -1\n1 "far" 0\n'
        pose='0 0 0 0 0 0 0\n1 0 0 0 0 0 0\n'
        self.write('far.smd','version 1\nnodes\n'+nodes+'end\nskeleton\ntime 0\n'+pose+
                   'time 1\n'+pose.replace('1 0 0 0','1 20000 0 0')+'end\n')
        mesh=(self.root/'mesh.smd').read_text().replace('unused_child','far').replace('1 0 0 1','1 0 0 0')
        self.write('base.smd',mesh)
        qc='$modelname bounds\n$body m base.smd\n$hbox 0 far -1 -1 -1 1 1 1\n$sequence bad far.smd\n'
        output=self.scene_qc(qc)
        self.assertIn('animation "@bad" bounding box',output)
        self.assertIn('bone "far", frame 1 (zero-based)',output)
        self.assertIn('bone render bounds',output)
        self.assertIn('$skipboneinbbox',output)
        self.assertNotIn('first out-of-range',self.scene_qc(qc+'$bboxonlyverts\n'))
        self.write('far.smd',(self.root/'far.smd').read_text().replace('1 20000 0 0','1 0 0 0').replace('time 1\n0 0 0 0','time 1\n0 20000 0 0'))
        output=self.scene_qc(qc+'$bboxonlyverts\n')
        self.assertIn('skinned vertex (dominant influence): bone "root", frame 1',output)
        self.assertNotIn('$skipboneinbbox',output)

    def test_integration_bbox_exact_boundary_does_not_warn(self):
        output=self.scene_qc('$modelname boundary\n$body m mesh.smd\n$bboxonlyverts\n'
                             '$clampworldspace -1 -1 -1 1 1 1\n$sequence idle mesh.smd\n')
        self.assertNotIn('exceeds coordinate range',output)

    def test_integration_ce_face_remap_corrective_inverse_normals_wrinkle_eyelid(self):
        text=(Path(__file__).parent/'fixtures/ce-facial.dmx').read_text()
        text=text.replace('"jointCount" "int" "1"','"jointCount" "int" "2"')
        for field,kind,values in [('jointWeights','float','".5", ".5", ".5", ".5", ".5", ".5"'),
                                 ('jointIndices','int','"0", "1", "0", "1", "0", "1"'),
                                 ('normals','vector3','"0 0 1", ".6 0 .8", "0 .6 .8", "0 0 -1", "-.6 0 -.8", "0 -.6 -.8"'),
                                 ('positionsIndices','int','"0", "1", "2", "0", "1", "2"'),
                                 ('normalsIndices','int','"0", "1", "2", "3", "4", "5"'),
                                 ('textureCoordinatesIndices','int','"0", "1", "2", "0", "1", "2"'),
                                 ('faces','int','"0", "1", "2", "-1", "3", "5", "4", "-1"')]:
            text=re.sub(r'("'+field+'" "'+kind+r'_array"\s*\[).*?(\])',lambda m:m[1]+values+m[2],text,count=1,flags=re.S)
        text=text.replace('"0 0 0"\n\t]\n\t"normalsIndices"','".1 .2 -.1"\n\t]\n\t"normalsIndices"')
        self.write('complex.dmx',text)
        self.ce_fixture()
        mouth=('eyeball eye root 0 0 0 material 2 0 iris .5\n'
               'flexfile face.vta { flex blink frame 1 }\n'
               'flexcontroller test range 0 1 blinkctl\n%blink = blinkctl\n'
               'eyelid upper face.vta lowerer 1 -.2 neutral 0 0 raiser 2 .2 split 0 eyeball eye\n'
               'flexcontroller eyelid range -1 1 lid\n%upper = lid\n')
        qc=('$modelname combined\n$bonecullmethod none\n$RemapFlexToGlobal\n$ComputeWrinkles\n'
            '$definebone root "" 0 0 0 90 0 0 0 0 0 0 0 0\n'
            '$definebone mesh "" 0 0 0 0 0 0 0 0 0 0 0 0\n'
            '$model face complex.dmx { NoAutoDMXRules }\n'
            '$flexcontroller test range 0 1 A B\n$flexcorrective smile A B\n'
            '$AddInvStudioFlexes\n$model mouth mesh.smd {\n'+mouth+'}\n')
        self.scene_qc(qc)
        controllers,keys,eyes,rules,models=self.ce_data('combined')
        self.assertEqual(len(models),2)
        self.assertEqual(len(eyes),1)
        smile=next(k for k in keys if k['name']=='smile')
        # The shared moved position has separate front/back normal corners.
        self.assertEqual(len(smile['vertices']),2)
        self.assertEqual(struct.unpack_from('<i',self.mdl('combined'),models[0]+80)[0],6)
        # Equal influences average a 90-degree X-rotated and unchanged delta.
        delta=smile['vertices'][0][2]
        self.assertAlmostEqual(sum(v*v for v in delta[:3]),.03125,delta=.0002)
        self.assertIsNotNone(smile['vertices'][0][3])
        self.assertTrue(any(abs(v)>.01 for vertex in smile['vertices'] for v in vertex[2][3:]))
        normal=next(k for k in keys if k['name']=='blink')
        inverse=next(k for k in keys if k['name']=='blink_Inv')
        for a,b in zip(normal['vertices'],inverse['vertices']):
            for x,y in zip(a[2],b[2]):self.assertAlmostEqual(x,-y,delta=.001)
        ops=next(ops for name,ops in rules if name=='smile')
        self.assertEqual(ops[-1],(18,2))
        self.assertEqual({controllers[v][0] for op,v in ops if op==2},{'A','B'})
        self.assertTrue(any(k['name'].startswith('upper') for k in keys))

    def test_integration_neko_two_studios_face_rename_split_lod(self):
        doc=json.loads(scene_bytes())
        binary=bytearray(base64.b64decode(doc['buffers'][0]['uri'].split(',')[1]))
        source=doc['meshes'][0]['primitives'][0]['targets'][0]
        shapes=[source]
        for amount in (-.25,0):
            offset=len(binary);binary.extend(struct.pack('<9f',*([0,0,amount]*3)))
            doc['bufferViews'].append(dict(buffer=0,byteOffset=offset,byteLength=36))
            doc['accessors'].append(dict(bufferView=len(doc['bufferViews'])-1,componentType=5126,count=3,type='VEC3'))
            shapes.append(dict(POSITION=len(doc['accessors'])-1))
        doc['meshes'][0]['primitives'][0]['targets']=shapes
        doc['meshes'][0]['extras']['targetNames']=['Smile','Lower','Neutral']
        doc['buffers'][0]=dict(byteLength=len(binary),uri='data:application/octet-stream;base64,'+base64.b64encode(binary).decode())
        self.write('full.gltf',json.dumps(doc))
        self.write('variant.gltf',json.dumps(doc))
        low=copy.deepcopy(doc);low['nodes']=low['nodes'][:2];low['nodes'][0]['children']=[1]
        self.write('low.gltf',json.dumps(low))
        qc=('$modelname neko_mix\n$dmxcompatibility neko\n$MaxVerts 3\n$RenameMorph Smile Raise\n'
            '$prerenamematerial Original face_mat\n$definebone Group "" 0 0 0 0 0 0 0 0 0 0 0 0\n'
            '$NekoModel face {\n')
        for i in range(2):
            qc+='studio '+('full.gltf' if i==0 else 'variant.gltf')+'\n'+f'eyeball right{i} Group -1 0 0 face_mat 2 0 iris .5\n'+f'eyeball left{i} Group 1 0 0 face_mat 2 0 iris .5\n'+f'eyelid upper Lower -1 Neutral 0 Raise 1 right{i} left{i}\n'
        qc+=('flex Raise\nflexpair Lower\nflexcontroller test range 0 1 strength\n'
             '%Raise = strength\n%LowerL = strength\n%LowerR = strength\n'
             'flexcontroller eyelid range -1 1 lid\n%upper_left = lid\n%upper_right = lid\n}\n'
             '$lod 10 { replacemodel full.gltf low.gltf\nreplacemodel variant.gltf low.gltf\n}\n')
        self.scene_qc(qc)
        controllers,keys,eyes,rules,models=self.ce_data('neko_mix')
        self.assertEqual(len(models),2)
        self.assertEqual(len(eyes),4)
        self.assertEqual(sum(name=='strength' for name,*_ in controllers),1)
        self.assertIn(b'face_mat\0',self.mdl('neko_mix'))
        self.assertNotIn(b'Original\0',self.mdl('neko_mix'))
        self.assertTrue(any(k['name']=='Raise' for k in keys))
        self.assertTrue(any(k['name']=='LowerL' and k['pair'] for k in keys))
        for model in models:
            self.assertEqual(struct.unpack_from('<i',self.mdl('neko_mix'),model+72)[0],2)
        vvd=(self.root/'models/neko_mix.vvd').read_bytes()
        self.assertEqual(struct.unpack_from('<2i',vvd,16),(12,6))

    def test_integration_bone_retention_categories_and_lod_vertex(self):
        names=['root','vertex','lod_vertex','hitbox','defined','animated','procedural','ik_upper','ik_middle','ik_end','attachment','bonemerge','unused']
        parents=[-1,0,0,0,0,0,0,0,7,8,0,0,0]
        nodes=''.join(f'{i} "{name}" {parents[i]}\n' for i,name in enumerate(names))
        pose=''.join(f'{i} {1 if i in (8,9) else 0} {0.1 if i==9 else 0} 0 0 0 0\n' for i in range(len(names)))
        head='version 1\nnodes\n'+nodes+'end\nskeleton\ntime 0\n'+pose+'end\n'
        triangle=lambda bone:f'triangles\nmaterial\n{bone} 0 0 0 0 0 1 0 0\n{bone} 1 0 0 0 0 1 1 0\n{bone} 0 1 0 0 0 1 0 1\nend\n'
        self.write('keep.smd',head+triangle(1));self.write('low.smd',head+triangle(2))
        self.write('move.smd','version 1\nnodes\n'+nodes+'end\nskeleton\ntime 0\n'+pose+'time 1\n'+pose.replace('5 0 0 0','5 0 1 0')+'end\n')
        self.scene_qc('$modelname retention\n$CEBoneRules\n$body m keep.smd\n$lod 20 { replacemodel keep.smd low.smd }\n'
                      '$hbox 0 hitbox -1 -1 -1 1 1 1\n$definebone root "" 0 0 0 0 0 0 0 0 0 0 0 0\n'
                      '$definebone defined root 0 0 0 0 0 0 0 0 0 0 0 0\n'
                      '$jigglebone procedural { is_flexible { length 2 tip_mass 1 } }\n'
                      '$ikchain leg ik_end\n$attachment socket attachment 0 0 0\n$bonemerge bonemerge\n$sequence move move.smd\n')
        _,bones=self.csgo_bone_table('retention')
        self.assertEqual(set(bones),set(names)-{'unused'})

    def test_integration_alwayscollapse_overrides_vertex_animation_defined_keep(self):
        text=(self.root/'mesh.smd').read_text().replace('unused_child','forced')
        text=text.replace('triangles\nmaterial\n0 ','triangles\nmaterial\n1 ')
        self.write('forced.smd',text)
        animation=text.split('triangles')[0].removesuffix('end\n')+'time 1\n0 0 0 0 0 0 0\n1 5 0 1 0 0 0\nend\n'
        self.write('forced_anim.smd',animation)
        self.scene_qc('$modelname forced\n$CEBoneRules\n$bonecullmethod none\n$body m forced.smd\n'
                      '$definebone forced root 0 0 1 0 0 0 0 0 0 0 0 0\n$donotcollapse forced\n$alwayscollapse forced\n'
                      '$sequence move forced_anim.smd\n')
        _,bones=self.csgo_bone_table('forced');self.assertEqual(set(bones),{'root'})

    def test_integration_staticprop_blank_bodygroup_keeps_choices(self):
        self.scene_qc('$modelname blank_static\n$staticprop\n$bodygroup choice { studio mesh.smd\nblank\n}\n')
        data=self.mdl('blank_static');body=struct.unpack_from('<i',data,236)[0]
        self.assertEqual(struct.unpack_from('<i',data,body+4)[0],2)
        model=body+struct.unpack_from('<i',data,body+12)[0]
        self.assertEqual(struct.unpack_from('<i',data,model+80)[0],3)
        self.assertEqual(struct.unpack_from('<i',data,model+148+80)[0],0)

    def test_integration_procedural_error_names_helper_then_driver(self):
        self.write('names.vrd','<helper> unused_child root root missing_driver\n')
        output=self.scene_qc('$modelname bad_proc\n$body m mesh.smd\n$proceduralbones names.vrd\n',success=False)
        self.assertIn('animconstraint "unused_child": missing driver bone "missing_driver"',output)

    def test_integration_invalid_animation_diagnostic_and_output_preservation(self):
        self.scene_qc('$modelname bad_anim\n$body m mesh.smd\n$sequence idle mesh.smd\n')
        before=self.mdl('bad_anim')
        self.write('empty.smd','version 1\nnodes\n0 "root" -1\nend\nskeleton\nend\n')
        output=self.scene_qc('$modelname bad_anim\n$body m mesh.smd\n$animation broken empty.smd\n$sequence idle broken\n',success=False)
        self.assertIn('empty.smd',output);self.assertIn('skeleton block has no frames',output)
        self.assertEqual(self.mdl('bad_anim'),before)
