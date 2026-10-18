"""Malformed SMD rejection and obsolete companion retirement using real binaries."""
from pathlib import Path
import hashlib
import struct
import subprocess
import sys
import tempfile
import unittest

COMPILER = str(Path(sys.argv.pop(1)).resolve())
HEADER = 'version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\ntriangles\nmaterial\n'
VERTEX = '0 0 0 0 0 0 1 .25 .75'
MESH = HEADER + VERTEX + '\n0 1 0 0 0 0 1 1 0\n0 0 1 0 0 0 1 0 1\nend\n'


class CompilerIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.mesh = self.root/'mesh.smd'
        self.mesh.write_text(MESH)

    def tearDown(self):
        self.temp.cleanup()

    def compile(self, extra='', args=(), success=True):
        qc = self.root/'test.qc'
        qc.write_text('$modelname fixture\n$body m mesh.smd\n'+extra)
        p = subprocess.run([COMPILER, str(qc), '-game', str(self.root), *args],
                           capture_output=True, text=True, errors='replace')
        self.assertEqual(p.returncode == 0, success, p.stdout+p.stderr)
        return p.stdout+p.stderr

    def outputs(self):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (self.root/'models').rglob('*') if p.is_file()
                and '.npmdl' not in str(p)}

    def test_invalid_vertex_fields_preserve_previous_output(self):
        self.compile(); before = self.outputs()
        invalid = [
            (VERTEX.replace('.75','OOPS'),'UV V'),
            (VERTEX.rsplit(' ',1)[0],'UV V'),
            (VERTEX.replace('.25','0.25oops'),'UV U'),
            (VERTEX.replace('.25','1e1000'),'UV U'),
            (VERTEX.replace('.75','nan'),'UV V'),
            ('2147483648'+VERTEX[1:],'bone index'),
            ('0x0'+VERTEX[1:],'bone index'),
            (VERTEX+' OOPS','weight count'),
            (VERTEX+' 1 0','influence weight'),
            (VERTEX+' 1 0 -1','bone influence'),
            (VERTEX+' 1 999999999999999999 1','influence bone index'),
            (VERTEX+' 1 0 1garbage','influence weight'),
            (VERTEX+' 0 trailing','trailing data'),
            (VERTEX+' -1','weight count'),
        ]
        for line, field in invalid:
            with self.subTest(line=line):
                self.mesh.write_text(MESH.replace(VERTEX,line))
                log=self.compile(success=False)
                self.assertIn('mesh.smd:11:',log)
                self.assertIn(field,log)
                self.assertEqual(before,self.outputs())

    def test_valid_plain_weighted_and_comment_vertices(self):
        reference=None
        for suffix in ('',' 0',' 1 0 1',' // comment',' 1 0 1 // comment'):
            with self.subTest(suffix=suffix):
                self.mesh.write_text(MESH.replace(VERTEX,VERTEX+suffix))
                self.compile()
                data=(self.root/'models/fixture.vvd').read_bytes()
                # MDL checksums include source text; compare actual vertex data.
                start=struct.unpack_from('<i',data,56)[0]
                if reference is None: reference=data[start:]
                else: self.assertEqual(reference,data[start:])

    def test_version3_extra_uv_pairs_are_consumed_and_validated(self):
        self.mesh.write_text(MESH.replace('version 1','version 3').replace(VERTEX,VERTEX+' 0 2 .1 .2 .3 .4'))
        self.compile(); before=self.outputs()
        for suffix in (' 0 -1',' 0 1 .1',' 0 1 .1 OOPS',' 0 1 .1 .2 trailing',' 0 9'):
            with self.subTest(suffix=suffix):
                self.mesh.write_text(MESH.replace('version 1','version 3').replace(VERTEX,VERTEX+suffix))
                self.assertIn('mesh.smd:11:',self.compile(success=False))
                self.assertEqual(before,self.outputs())

    def test_finite_float_underflow_remains_accepted(self):
        for value in ('1e-40','1e-1000'):
            with self.subTest(value=value):
                self.mesh.write_text(MESH.replace('.25',value))
                self.compile()

    def tetra(self):
        faces = [((0,0,0),(0,1,0),(1,0,0)),((0,0,0),(1,0,0),(0,0,1)),
                 ((0,0,0),(0,0,1),(0,1,0)),((1,0,0),(0,1,0),(0,0,1))]
        self.mesh.write_text(HEADER.rsplit('material\n',1)[0]+''.join(
            'material\n'+''.join(f'0 {x} {y} {z} 0 0 1 0 0\n' for x,y,z in face)
            for face in faces)+'end\n')

    def test_removed_collision_and_dx80_retire_matching_previous_companions(self):
        self.tetra();self.compile('$collisionmodel mesh.smd { $mass 10 }\n')
        output=self.root/'models'
        self.assertTrue((output/'fixture.phy').exists())
        self.assertTrue((output/'fixture.dx80.vtx').exists())
        self.compile(args=('-nodx80',))
        self.assertFalse((output/'fixture.phy').exists())
        self.assertFalse((output/'fixture.dx80.vtx').exists())
        self.assertTrue((output/'fixture.dx90.vtx').exists())
        self.assertEqual(struct.unpack_from('<I',(output/'fixture.mdl').read_bytes(),8)[0],
                         struct.unpack_from('<I',(output/'fixture.vvd').read_bytes(),8)[0])

    def test_unattributable_and_custom_companions_are_retained(self):
        self.tetra();self.compile('$collisionmodel mesh.smd { $mass 10 }\n')
        output=self.root/'models'
        phy=output/'fixture.phy'; data=bytearray(phy.read_bytes()); data[12]^=1;phy.write_bytes(data)
        custom=output/'shared.phy';custom.write_bytes(data)
        sidecar=output/'fixture.vertexanim.json';sidecar.write_text('{"user":"metadata"}')
        log=self.compile(args=('-nodx80',))
        self.assertIn('unverified ownership',log)
        self.assertEqual(phy.read_bytes(),bytes(data));self.assertEqual(custom.read_bytes(),bytes(data))
        self.assertEqual(sidecar.read_text(),'{"user":"metadata"}')


if __name__ == '__main__':
    unittest.main()
