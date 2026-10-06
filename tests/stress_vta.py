"""Opt-in dense VTA stress test: python tests/stress_vta.py COMPILER [--work DIR]."""
import argparse,json,struct,subprocess,time,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('compiler');p.add_argument('--work',required=True);p.add_argument('--vertices',type=int,default=30000);p.add_argument('--frames',type=int,default=80);a=p.parse_args()
r=Path(a.work).resolve();r.mkdir(parents=True,exist_ok=True)
assert a.vertices>=3 and a.vertices%3==0 and a.frames>=2
points=[]
for i in range(a.vertices//3):
 x=(i%100)*2;y=(i//100)*2
 points += [(x,y,0),(x+1,y,0),(x,y+1,0)]
with (r/'mesh.smd').open('w',encoding='utf-8') as f:
 f.write('version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\ntriangles\n')
 for i,(x,y,z) in enumerate(points):
  if i%3==0:f.write('material\n')
  f.write(f'0 {x} {y} {z} 0 0 1 {i%3==1:d} {i%3==2:d}\n')
 f.write('end\n')
with (r/'dense.vta').open('w',encoding='utf-8') as f:
 f.write('version 1\nvertexanimation\n')
 for frame in range(a.frames):
  f.write(f'time {frame}\n')
  f.writelines(f'{i} {x:.8f} {y:.8f} {frame*.001:.8f} 0.00000000 0.00000000 1.00000000\n' for i,(x,y,z) in enumerate(points))
 f.write('end\n')
size=(r/'dense.vta').stat().st_size;assert size>128*1024*1024, size
(r/'stress.qc').write_text(f'$modelname stress\n$model face mesh.smd {{\nflexfile dense.vta {{\nflex shape frame {a.frames-1}\n}}\nflexcontroller test strength\n%shape = strength\n}}\n$sequence idle mesh.smd\n')
peak=0
if os.name == 'nt':
 import ctypes
 from ctypes import wintypes
 class Counters(ctypes.Structure):
  _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ['peakWorking','working','peakPaged','paged','peakNonPaged','nonPaged','pagefile','peakPagefile']]
 query=ctypes.WinDLL('psapi').GetProcessMemoryInfo
 query.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD];query.restype=wintypes.BOOL
 def sample(process):
  counters=Counters();counters.cb=ctypes.sizeof(counters)
  return counters.peakWorking if query(int(process._handle),ctypes.byref(counters),counters.cb) else 0
else:
 def sample(process):return 0
started=time.perf_counter()
with (r/'compile.log').open('wb') as log:
 process=subprocess.Popen([str(Path(a.compiler).resolve()),str(r/'stress.qc'),'-game',str(r),'-perfmetrics'],stdout=log,stderr=subprocess.STDOUT)
 while process.poll() is None:
  peak=max(peak,sample(process))
  if time.perf_counter()-started>300:process.kill();process.wait();raise TimeoutError('VTA compiler timed out')
  time.sleep(.05)
 if process.returncode:raise subprocess.CalledProcessError(process.returncode,process.args)
elapsed=time.perf_counter()-started
if os.name != 'nt':
 import resource
 peak=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024
d=(r/'models/stress.mdl').read_bytes();bp=struct.unpack_from('<i',d,236)[0];model=bp+struct.unpack_from('<i',d,bp+12)[0];mesh=model+struct.unpack_from('<i',d,model+76)[0];assert struct.unpack_from('<i',d,mesh+16)[0]>0
key=mesh+struct.unpack_from('<i',d,mesh+20)[0];assert struct.unpack_from('<i',d,key+20)[0]==a.vertices
vanim=key+struct.unpack_from('<i',d,key+24)[0]
assert abs(struct.unpack_from('<e',d,vanim+8)[0]-(a.frames-1)*.001)<.0003
report={'vta_bytes':size,'vertices':a.vertices,'frames':a.frames,'seconds':round(elapsed,3),'peak_working_set_bytes':peak,'mdl_bytes':len(d),'result':'passed'}
(r/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
