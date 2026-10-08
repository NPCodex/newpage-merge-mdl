"""AxisInterp decompile/recompile checks against the actual binary pose table."""
from pathlib import Path
import re
import struct
import subprocess

from procedural_cases import axis_fixture, dot


def axis_records(data):
    count,start=struct.unpack_from('<2i',data,156)
    bones=[start+i*216 for i in range(count)]
    names=[]
    for bone in bones:
        at=bone+struct.unpack_from('<i',data,bone)[0]
        names.append(data[at:data.index(b'\0',at)].decode())
    records={}
    for i,bone in enumerate(bones):
        kind,offset=struct.unpack_from('<2i',data,bone+164)
        if kind!=1:continue
        at=bone+offset;control,axis=struct.unpack_from('<2i',data,at)
        records[names[i]]=(names[control],axis,
                          [struct.unpack_from('<3f',data,at+8+j*12) for j in range(6)],
                          [struct.unpack_from('<4f',data,at+80+j*16) for j in range(6)])
    return records


class AxisExportCases:
    def export_axis(self,*flags,label='default',success=True):
        import __main__
        compiler=Path(__main__.COMPILER)
        decoder=compiler.with_name('NewPageMergeMDL-Decompiler'+compiler.suffix)
        out=self.root/('axis-export-'+label)
        result=subprocess.run([str(decoder),str(self.root/'models/axis.mdl'),'-outdir',str(out),*flags],
                              capture_output=True,text=True,errors='replace')
        self.assertEqual(result.returncode==0,success,result.stdout+result.stderr)
        if not success:return result.stdout+result.stderr
        qc=next(out.rglob('*.pulseqc' if '-pulseqc' in flags else '*.qc'))
        self.assertIn('$proceduralbones "axis_axis.bones"',qc.read_text())
        return qc,qc.with_name('axis_axis.bones')

    def axis_export_roundtrip(self,*flags,label='default'):
        import __main__
        before=axis_records(self.mdl('axis'));self.assertTrue(before)
        qc,bones=self.export_axis(*flags,label=label)
        self.assertTrue(bones.is_file())
        text=bones.read_text();self.assertIn('type compiled',text)
        self.assertTrue(text.startswith('proceduralbones\n'))
        self.assertEqual(text.count('\naxis '),6*len(before))
        qc.write_text(re.sub(r'^\$modelname .*$', '$modelname axis_roundtrip',qc.read_text(),flags=re.M))
        result=subprocess.run([__main__.COMPILER,str(qc),'-game',str(self.root)],capture_output=True,text=True,errors='replace')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        after=axis_records(self.mdl('axis_roundtrip'));self.assertEqual(before.keys(),after.keys())
        for name,(control,axis,positions,rotations) in before.items():
            actual=after[name];self.assertEqual(actual[:2],(control,axis))
            for p,q in zip(positions,actual[2]):
                for a,b in zip(p,q):self.assertAlmostEqual(a,b,delta=2e-5)
            for p,q in zip(rotations,actual[3]):self.assertAlmostEqual(abs(dot(p,q)),1,delta=2e-6)
        return qc,bones

    def test_axis_export_roundtrip_stock_pulseqc_and_joints(self):
        self.axis_compile(qc='$scale 2\n')
        for flags,label in [((),'stock'),(('-pulseqc',),'pulse'),(('-datamodeljoints',),'joints')]:
            with self.subTest(label=label):self.axis_export_roundtrip(*flags,label=label)

    def test_axis_export_preserves_root_control_slots_without_double_rotation(self):
        text=axis_fixture().replace('"driver" "root" 1','"root" "" 3')
        self.axis_compile(text=text)
        _,bones=self.axis_export_roundtrip(label='root-control')
        # Stock's quoted scanset rejects empty names, even the ignored parent.
        self.assertIn('bone "helper" "root" "root" "-" 3',bones.read_text())

    def test_axis_export_preserves_names_with_dots_and_spaces(self):
        self.axis_compile(qc='$renamebone driver "rig.driver"\n$renamebone helper "rig helper"\n')
        _,bones=self.axis_export_roundtrip(label='names')
        self.assertIn('bone "rig helper" "root" "rig.driver" "root" 1',bones.read_text())

    def test_axis_export_nomesh_keeps_reference_without_writing_bones(self):
        self.axis_compile()
        _,bones=self.export_axis('-nomesh',label='nomesh')
        self.assertFalse(bones.exists())

    def test_axis_export_rejects_corrupt_records_before_replacing_outputs(self):
        self.axis_compile();original,bones=self.csgo_bone_table('axis')
        owner=bones['helper'][1];at=owner+struct.unpack_from('<i',original,owner+168)[0]
        qc,path=self.export_axis(label='preserved');before_qc=qc.read_bytes();before_bones=path.read_bytes()
        cases=[(owner+168,'i',0,'outside model bounds'),(owner+168,'i',2147483647,'outside model bounds'),
               (owner+168,'i',len(original)-owner-80,'outside model bounds'),
               (at,'i',99,'control bone index'),(at+4,'i',3,'selected axis'),
               (owner+4,'i',-1,'parent bone index'),(at+8,'f',float('nan'),'non-finite pose'),
               (at+80,'f',3,'quaternion is not normalized')]
        for offset,kind,value,message in cases:
            with self.subTest(message=message):
                bad=bytearray(original);struct.pack_into('<'+kind,bad,offset,value)
                (self.root/'models/axis.mdl').write_bytes(bad)
                self.assertIn(message,self.export_axis(label='preserved',success=False))
                self.assertEqual(before_qc,qc.read_bytes());self.assertEqual(before_bones,path.read_bytes())
        (self.root/'models/axis.mdl').write_bytes(original)
