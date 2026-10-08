"""QC-context flex expansion and material-derived teeth metadata."""
from pathlib import Path
import struct


def variable_flex_fixture(expression='$amount$'):
    text=(Path(__file__).parent/'fixtures/ce-facial.dmx').read_text()
    uid=lambda n:f'a100bebc-a100-bebc-00be-{n:012x}'
    text=text.replace('"targets" "element_array"\n\t[\n\t\t"element" "'+uid(9)+'"',
                      '"targets" "element_array"\n\t[\n\t\t"element" "'+uid(9)+'",\n\t\t"element" "'+uid(20)+'"')
    text+=f'\n"DmeFlexRules" {{ "id" "elementid" "{uid(20)}" "name" "string" "rules" "deltaStates" "element_array" [ "element" "{uid(21)}" ] }}\n'
    text+=f'"DmeFlexRuleExpression" {{ "id" "elementid" "{uid(21)}" "name" "string" "smile" "expr" "string" "{expression}" }}\n'
    return text


class CsgoClosureCases:
    def flex_constants(self,name='face'):
        return [struct.unpack('<f',struct.pack('<i',value))[0]
                for desc,ops in self.ce_data(name)[3] if desc=='smile'
                for opcode,value in ops if opcode==1]

    def test_dmx_flex_variables_capture_import_context(self):
        self.write('face.dmx',variable_flex_fixture('$amount$ * 2'))
        self.scene_qc('$modelname face\n$definevariable amount .25\n$model m face.dmx\n$redefinevariable amount .75\n')
        self.assertIn(.25,self.flex_constants());self.assertNotIn(.75,self.flex_constants())
        self.assertTrue(self.ce_data()[1])

    def test_dmx_flex_variables_manual_import_reuses_immutable_document(self):
        self.write('face.dmx',variable_flex_fixture())
        self.scene_qc('$modelname face\n$definevariable amount .25\n$model m face.dmx { NoAutoDMXRules }\n'
                      '$datamodelflexes face.dmx flexrule\n$redefinevariable amount .75\n$datamodelflexes face.dmx flexrule\n')
        self.assertIn(.25,self.flex_constants());self.assertIn(.75,self.flex_constants())
        self.assertIn('$amount$',(self.root/'face.dmx').read_text())

    def test_dmx_flex_unknown_variable_fails_preserving_model(self):
        self.write('face.dmx',variable_flex_fixture())
        self.scene_qc('$modelname face\n$definevariable amount .25\n$model m face.dmx\n')
        old=self.mdl('face')
        output=self.scene_qc('$modelname face\n$model m face.dmx\n',success=False)
        self.assertIn('unknown variable "$amount$"',output)
        self.assertEqual(self.mdl('face'),old)

    def test_dmx_flex_cli_variable_override_and_include(self):
        self.write('face.dmx',variable_flex_fixture('$amount$ + $offset$'))
        self.write('values.qci','$definevariable amount .25\n$definevariable offset .125\n')
        self.scene_qc('$modelname face\n$include values.qci\n$model m face.dmx\n','-defvar','amount','.75')
        self.assertIn(.75,self.flex_constants());self.assertIn(.125,self.flex_constants())

    def material_metadata(self,name):
        data=self.mdl(name);count,start=struct.unpack_from('<2i',data,204);out={}
        for i in range(count):
            p=start+64*i;s=p+struct.unpack_from('<i',data,p)[0]
            out[data[s:data.index(b'\0',s)].decode()]=struct.unpack_from('<2i',data,p+4)
        return out

    def vtx_mesh_flags(self,name,ext='dx90'):
        data=(self.root/f'models/{name}.{ext}.vtx').read_bytes()
        body=struct.unpack_from('<i',data,32)[0];model=body+struct.unpack_from('<i',data,body+4)[0]
        count,offset=struct.unpack_from('<2i',data,model);flags=[]
        for i in range(count):
            lod=model+offset+i*12;meshes,offset2=struct.unpack_from('<2i',data,lod)
            flags.extend(data[lod+offset2+j*9+8] for j in range(meshes))
        return flags

    def test_mouthshader_skin_family_sets_teeth_at_all_lods(self):
        self.write('materials/teeth.vmt','VertexLitGeneric { "$clientShader" "mOuThShAdEr" }')
        self.run_qc('$modelname teeth\n$cdmaterials ""\n$texturegroup skins { { material } { teeth } }\n$lod 12 { }\n')
        self.assertEqual(self.material_metadata('teeth')['teeth'],(1,1))
        self.assertEqual(self.material_metadata('teeth')['material'],(0,0))
        for ext in ('dx80','dx90'):self.assertEqual(self.vtx_mesh_flags('teeth',ext),[1,1])

    def test_mouthshader_rename_patch_include_and_other_shader(self):
        self.write('materials/base.vmt','VertexLitGeneric { "$clientShader" "OtherShader" }')
        self.write('materials/face/renamed.vmt','Patch { include "materials/base.vmt" replace { "$clientShader" "MouthShader" } }')
        self.scene_qc('$modelname teeth\n$cdmaterials face\n$body m mesh.smd RenameMat material renamed\n')
        self.assertEqual(self.material_metadata('teeth')['renamed'],(1,1))
        self.assertEqual(self.vtx_mesh_flags('teeth'),[1])
        self.write('materials/face/renamed.vmt','VertexLitGeneric { "$clientShader" "OtherShader" }')
        self.scene_qc('$modelname teeth\n$cdmaterials face\n$body m mesh.smd RenameMat material renamed\n')
        self.assertEqual(self.material_metadata('teeth')['renamed'],(0,1))
        self.assertEqual(self.vtx_mesh_flags('teeth'),[0])

    def test_mouthshader_mount_resolution_and_cyclic_patch_diagnostic(self):
        mounted=self.root/'mounted';mounted.mkdir()
        self.write('gameinfo.txt','GameInfo { FileSystem { SteamAppId 730 SearchPaths { Game "|gameinfo_path|mounted" } } }')
        self.write('mounted/materials/material.vmt','VertexLitGeneric { "$clientShader" "MouthShader" }')
        self.run_qc('$modelname teeth\n$cdmaterials ""\n')
        self.assertEqual(self.material_metadata('teeth')['material'],(1,1))
        self.write('mounted/materials/material.vmt','Patch { include "material" }')
        output=self.run_qc('$modelname teeth\n$cdmaterials ""\n')
        self.assertIn('cyclic',output);self.assertEqual(self.material_metadata('teeth')['material'],(0,0))
