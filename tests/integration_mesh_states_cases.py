"""Finite topology conversion and deterministic playback boundaries."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys

_tool_path=Path(__file__).resolve().parents[1]/'tools/mesh_states.py'
sys.path.insert(0,str(_tool_path.parent))
_spec=importlib.util.spec_from_file_location('newpage_mesh_states',_tool_path)
mesh_states=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mesh_states)


class IntegrationMeshStatesCases:
    def mesh_state_spec(self):
        original=(self.root/'mesh.smd').read_text()
        head,triangles=original.split('triangles\n')
        triangle=triangles.removesuffix('end\n')
        other=triangle.replace('0 0 0 0 0 0 1','0 2 0 0 0 0 1').replace('0 1 0 0 0 0 1','0 3 0 0 0 0 1').replace('0 0 1 0 0 0 1','0 2 1 0 0 0 1')
        self.write('double.smd',head+'triangles\n'+triangle+other+'end\n')
        return dict(modelname='models/integration/states.mdl',group='mesh_state',
                    states=[dict(name='single',source='mesh.smd'),dict(name='double',source='double.smd'),dict(name='blank',blank=True)],
                    sequence=[0,1,2,1],fps=2,loop=True)

    def test_integration_mesh_states_compiles_topologies_blank_and_sidecar(self):
        spec=self.mesh_state_spec()
        manifest=self.write('states.json',json.dumps(spec))
        compiler=sys.modules[self.scene_qc.__module__].COMPILER
        args=[sys.executable,str(_tool_path),str(manifest),'--out',str(self.root/'generated'),
              '--compiler',compiler,'--game',str(self.root/'game')]
        result=subprocess.run(args,capture_output=True,text=True,errors='replace')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        mdl=self.root/'game/models/integration/states.mdl'
        from validate_outputs import validate
        validate(mdl)
        data=mdl.read_bytes();body=struct.unpack_from('<i',data,236)[0]
        self.assertEqual(struct.unpack_from('<i',data,body+4)[0],3)
        model=body+struct.unpack_from('<i',data,body+12)[0]
        self.assertEqual([struct.unpack_from('<i',data,model+i*148+80)[0] for i in range(3)],[3,6,0])
        sidecar=mdl.with_suffix('.meshstates.json');clip=json.loads(sidecar.read_text())
        self.assertEqual(clip['model'],'models/integration/states.mdl')
        self.assertEqual(clip['sequence'],[0,1,2,1])
        self.assertTrue(clip['states'][2]['blank'])
        original=sidecar.read_bytes()
        self.write('double.smd','invalid mesh')
        result=subprocess.run(args,capture_output=True,text=True,errors='replace')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(sidecar.read_bytes(),original)
        self.assertEqual(mdl.read_bytes(),data)

    def test_integration_mesh_states_explicit_times_loop_and_terminal_boundaries(self):
        spec=self.mesh_state_spec()
        _,clip=mesh_states.prepare(spec,self.root)
        for time,wanted in [(-1,0),(0,0),(.499,0),(.5,1),(1,2),(1.5,1),(1.999,1),(2,0),(4.5,1)]:
            self.assertEqual(mesh_states.sample(clip,time),wanted)
        spec.pop('fps');spec.update(times=[0,.125,.5,1],duration=1.5,loop=False)
        _,clip=mesh_states.prepare(spec,self.root)
        for time,wanted in [(.1249,0),(.125,1),(.5,2),(1,1),(1.5,1),(20,1)]:
            self.assertEqual(mesh_states.sample(clip,time),wanted)

    def test_integration_mesh_states_rejects_ambiguous_or_unsafe_inputs(self):
        base=self.mesh_state_spec()
        bad=[dict(fps=0),dict(fps=float('inf')),dict(fps=10**1000),dict(times=[0,1,2,3]),dict(sequence=[0,3]),
             dict(sequence=[False]),dict(duration=1),dict(loop='true'),dict(modelname='../escape.mdl'),
             dict(modelname='/absolute.mdl'),dict(group='name\n$include injected'),dict(unknown=1),
             dict(states=[dict(name='bad',source='mesh.smd',blank=True)]),dict(states=[dict(name='blank',blank=True)])]
        for change in bad:
            with self.subTest(change=change):
                spec=copy.deepcopy(base);spec.update(change)
                with self.assertRaises(ValueError):mesh_states.prepare(spec,self.root)
        for times in ([.1,.2,.3,.4],[0,.2,.2,.3],[0,float('nan'),1,2],[0,1]):
            spec=copy.deepcopy(base);spec.pop('fps');spec['times']=times
            with self.assertRaises(ValueError):mesh_states.prepare(spec,self.root)
