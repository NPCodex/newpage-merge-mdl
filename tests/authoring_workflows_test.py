"""Native geometry adapters and local material dependency collection."""
import argparse
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

parser=argparse.ArgumentParser()
parser.add_argument('--bin-dir',required=True,type=Path)
parser.add_argument('--tools-dir',type=Path)
args,rest=parser.parse_known_args();sys.argv=[sys.argv[0],*rest]
BIN=args.bin_dir.resolve();TOOLS=(args.tools_dir or BIN/'tools').resolve()
sys.path.insert(0,str(TOOLS))
import mesh_workflow
import material_collect
MESHTOOL=BIN/'subtools'/('meshtool.exe' if os.name=='nt' else 'meshtool')
CUBE='''v -1 -1 -1
v 1 -1 -1
v 1 1 -1
v -1 1 -1
v -1 -1 1
v 1 -1 1
v 1 1 1
v -1 1 1
f 1 4 3 2
f 5 6 7 8
f 1 2 6 5
f 2 3 7 6
f 3 4 8 7
f 4 1 5 8
'''


class AuthoringWorkflows(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='authoring-workflows-')
        self.root=Path(self.temporary.name)
    def tearDown(self):self.temporary.cleanup()
    def test_obj_simplify_preserves_uv_normals_groups_and_native_summary(self):
        source=self.root/'input.obj'
        source.write_text('v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nvt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nvn 0 0 1\ng face\nusemtl body\nf 1/1/1 2/2/1 3/3/1 4/4/1\n')
        output=self.root/'simplified.obj'
        self.assertEqual(mesh_workflow.main(['simplify',str(source),'--output',str(output),'--meshtool',str(MESHTOOL),'--ratio','1']),0)
        mesh=mesh_workflow.read_mesh(output)
        self.assertEqual(len(mesh['runs'][0]['indices']),6)
        self.assertEqual(mesh['runs'][0]['material'],'body')
        self.assertTrue(all(uv is not None and normal==[0,0,1] for uv,normal in mesh['attributes']))
        report=json.loads(output.with_suffix('.mesh.json').read_text())
        self.assertEqual(report['input_triangles'],2);self.assertEqual(report['output_triangles'],2)
        self.assertEqual(report['meshoptimizer_normalized_errors'],[0])
    def test_glb_node_transform_and_geometry_match_static_obj(self):
        positions=[(0,0,0),(1,0,0),(0,1,0)];blob=b''.join(struct.pack('<3f',*p) for p in positions)
        doc=dict(asset={'version':'2.0'},buffers=[{'byteLength':len(blob)}],
                 bufferViews=[dict(buffer=0,byteOffset=0,byteLength=len(blob))],
                 accessors=[dict(bufferView=0,componentType=5126,count=3,type='VEC3')],
                 meshes=[dict(primitives=[dict(attributes={'POSITION':0})])],
                 nodes=[dict(mesh=0,translation=[10,20,30])],scenes=[dict(nodes=[0])],scene=0)
        text=json.dumps(doc).encode();text+=b' '*(-len(text)%4)
        source=self.root/'input.glb'
        source.write_bytes(struct.pack('<III',0x46546C67,2,12+8+len(text)+8+len(blob))+struct.pack('<II',len(text),0x4E4F534A)+text+struct.pack('<II',len(blob),0x004E4942)+blob)
        output=self.root/'scene.obj'
        self.assertEqual(mesh_workflow.main(['simplify',str(source),'--output',str(output),'--meshtool',str(MESHTOOL),'--ratio','1']),0)
        self.assertEqual(mesh_workflow.read_mesh(output)['vertices'],[[10.,20.,30.],[11.,20.,30.],[10.,21.,30.]])
    def test_convex_decomposition_exports_faces_containing_each_hull(self):
        source=self.root/'cube.obj';source.write_text(CUBE);output=self.root/'hulls.obj'
        self.assertEqual(mesh_workflow.main(['decompose',str(source),'--output',str(output),'--meshtool',str(MESHTOOL),'--resolution','10000','--max-hulls','4']),0)
        mesh=mesh_workflow.read_mesh(output);self.assertTrue(mesh['runs'])
        for run in mesh['runs']:
            points=[mesh['vertices'][i] for i in set(run['indices'])]
            self.assertGreaterEqual(len(run['indices']),12)
            for at in range(0,len(run['indices']),3):
                a,b,c=[mesh['vertices'][i] for i in run['indices'][at:at+3]]
                normal=mesh_workflow.cross(mesh_workflow.sub(b,a),mesh_workflow.sub(c,a))
                self.assertTrue(all(mesh_workflow.dot(normal,mesh_workflow.sub(p,a))<=1e-5 for p in points))
    def test_bad_geometry_and_alias_leave_previous_results(self):
        source=self.root/'bad.obj';source.write_text('v nan 0 0\nf 1 1 1\n');output=self.root/'old.obj';output.write_text('old')
        self.assertEqual(mesh_workflow.main(['simplify',str(source),'--output',str(output),'--meshtool',str(MESHTOOL)]),2)
        self.assertEqual(output.read_text(),'old')
        source.write_text(CUBE)
        self.assertEqual(mesh_workflow.main(['simplify',str(source),'--output',str(source),'--meshtool',str(MESHTOOL)]),2)
        self.assertEqual(source.read_text(),CUBE)
    def materials(self):
        high=self.root/'high/materials';low=self.root/'low/materials'
        (high/'characters').mkdir(parents=True);(high/'shared').mkdir();(low/'textures').mkdir(parents=True);(low/'characters').mkdir()
        (high/'characters/Face.vmt').write_text('Patch { include "materials/shared/Base.vmt" replace { "$basetexture" "Textures/Skin" } }')
        (high/'shared/Base.vmt').write_text('VertexLitGeneric { "$bumpmap" "textures/normal" "$envmap" "env_cubemap" }')
        (low/'characters/face.vmt').write_text('VertexLitGeneric { "$basetexture" "missing/low_priority" }')
        (low/'textures/skin.vtf').write_bytes(b'VTF\0skin')
        (low/'textures/normal.vtf').write_bytes(b'VTF\0normal')
        return high,low
    def test_material_priority_patch_casefold_and_isolated_resolution(self):
        high,low=self.materials();output=self.root/'collected'
        self.assertEqual(material_collect.main(['--root',str(high),'--root',str(low),'--material','CHARACTERS/FACE','--output',str(output)]),0)
        report=json.loads((output/'materials-manifest.json').read_text())
        self.assertTrue(report['complete']);self.assertEqual(len(report['files']),4)
        face=next(f for f in report['files'] if f['name']=='characters/face.vmt')
        self.assertEqual(face['priority'],0);self.assertEqual(len(face['shadowed_sources']),1)
        isolated=material_collect.collect([output],[['characters/face.vmt']])
        self.assertTrue(isolated['complete']);self.assertEqual(len(isolated['files']),4)
        self.assertEqual((output/'materials/textures/skin.vtf').read_bytes(),b'VTF\0skin')
    def test_missing_and_cyclic_materials_publish_report_without_partial_files(self):
        high,low=self.materials();output=self.root/'collected';(output/'materials/characters').mkdir(parents=True)
        previous=output/'materials/characters/face.vmt';previous.write_text('previous material')
        (low/'textures/skin.vtf').unlink()
        self.assertEqual(material_collect.main(['--root',str(high),'--root',str(low),'--material','characters/face','--output',str(output)]),2)
        self.assertEqual(previous.read_text(),'previous material')
        report=json.loads((output/'materials-manifest.json').read_text());self.assertFalse(report['published']);self.assertEqual(report['missing'][0]['name'],'Textures/Skin.vtf')
        (high/'shared/Base.vmt').write_text('Patch { include "characters/face" }')
        report=material_collect.collect([high,low],[['characters/face.vmt']])
        self.assertTrue(any('cyclic VMT include' in error for error in report['errors']))
    def test_material_path_escape_and_source_alias_are_rejected(self):
        high,low=self.materials()
        with self.assertRaises(ValueError):material_collect.resource_name('../outside','.vmt')
        before=(high/'characters/Face.vmt').read_bytes()
        self.assertEqual(material_collect.main(['--root',str(high),'--root',str(low),'--material','characters/face','--output',str(high.parent)]),2)
        self.assertEqual((high/'characters/Face.vmt').read_bytes(),before)
    def test_mdl_material_directory_names_are_read_with_bounds_checks(self):
        data=bytearray(1024);data[:4]=b'IDST';struct.pack_into('<I',data,4,49);struct.pack_into('<I',data,76,len(data))
        struct.pack_into('<4I',data,204,1,512,1,580);struct.pack_into('<i',data,512,88);struct.pack_into('<I',data,580,620)
        data[600:605]=b'Face\0';data[620:632]=b'characters/\0';source=self.root/'test.mdl';source.write_bytes(data)
        self.assertEqual(material_collect.mdl_materials(source),[['characters/Face.vmt']])
        struct.pack_into('<I',data,208,1020);source.write_bytes(data)
        with self.assertRaises(ValueError):material_collect.mdl_materials(source)


if __name__=='__main__':unittest.main()
