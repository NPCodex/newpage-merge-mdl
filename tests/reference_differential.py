"""Run self-authored bone/procedural/face fixtures against a reference compiler.
Reference binaries are provided locally by the user and never redistributed.
"""
import argparse,json,struct,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('compiler');p.add_argument('--reference',required=True);p.add_argument('--work',required=True)
a=p.parse_args();root=Path(a.work).resolve();root.mkdir(parents=True,exist_ok=True)
nodes='0 "root" -1\n1 "upper" 0\n2 "hand" 1\n3 "helper" 0\n'
pose='0 0 0 0 0 0 0\n1 0 0 2 0 0 0\n2 0 0 2 0 0 0\n3 0 2 0 .2 .3 .4\n'
mesh='version 1\nnodes\n'+nodes+'end\nskeleton\ntime 0\n'+pose+'end\ntriangles\n'
for bone in range(4):mesh+='material\n'+''.join(f'{bone} {x} {y} {bone+z} 0 0 1 0 0\n' for x,y,z in ((0,0,0),(1,0,0),(0,1,0)))
(root/'mesh.smd').write_text(mesh+'end\n')
definitions=''.join('$definebone '+name+' '+parent+' '+values+' 0 0 0 0 0 0\n' for name,parent,values in [('root','""','0 0 0 0 0 0'),('upper','root','0 0 2 0 0 0'),('hand','upper','0 0 2 0 0 0'),('helper','root','0 2 0 11.459156 17.188734 22.918312')])
cases={
 'bones':'$attachment grip hand 0 0 0\n',
 'jiggle':'$jigglebone helper { is_flexible { length 10 tip_mass 1 pitch_stiffness 100 yaw_stiffness 100 pitch_constraint -10 30 yaw_constraint -20 40 } }\n',
 'ik_lod':'$ikchain arm hand\n$lod 10 { replacebone hand upper }\n',
 'face':'$model face mesh.smd { flexfile face.vta {\nflex Smile frame 1\n}\nflexcontroller test range 0 1 strength\n%Smile = strength\n}\n',
 'eyelid':'$model face mesh.smd {\neyeball eye root 0 0 0 material 2 0 iris .5\neyelid upper face.vta lowerer 1 -.2 neutral 0 0 raiser 2 .2 split 0 eyeball eye\nflexcontroller eyelid range -1 1 lid\n%upper = lid\n}\n',
 'dmx':'$model face face.dmx\n',
 'dmx_explicit':'$model face face.dmx {\n%smile = smile\n}\n',
 'dmx_multi':'$model face_a face.dmx\n$model face_b face.dmx\n',
 'rig_combined':'$attachment grip hand 1 2 3\n$ikchain arm hand\n$lod 10 { replacebone hand upper }\n$jigglebone helper { is_flexible { length 10 tip_mass 1 pitch_stiffness 100 yaw_stiffness 100 pitch_constraint -10 30 yaw_constraint -20 40 } }\n',
 'face_stereo':'$model face mesh.smd { flexfile face.vta {\nflexpair Smile .5 frame 1\n}\nflexcontroller test range 0 1 left right\n%SmileL = left\n%SmileR = right\n}\n'
}
(root/'face.dmx').write_bytes((Path(__file__).parent/'fixtures/ce-facial.dmx').read_bytes())
vta='version 1\nnodes\n'+nodes+'end\nskeleton\ntime 0\n'+pose+'time 1\n'+pose+'time 2\n'+pose+'end\nvertexanimation\ntime 0\n'
for bone in range(4):
 for j,(x,y,z) in enumerate(((0,0,0),(1,0,0),(0,1,0))):vta+=f'{bone*3+j} {x} {y} {bone+z} 0 0 1\n'
vta+='time 1\n'
for bone in range(4):
 for j,(x,y,z) in enumerate(((0,0,0),(1,0,0),(0,1,0))):vta+=f'{bone*3+j} {x} {y} {bone+z+.25} 0 0 1\n'
vta+='time 2\n'
for bone in range(4):
 for j,(x,y,z) in enumerate(((0,0,0),(1,0,0),(0,1,0))):vta+=f'{bone*3+j} {x} {y} {bone+z+.5} 0 0 1\n'
(root/'face.vta').write_text(vta+'end\n')
def summary(path):
 d=path.read_bytes();result={};n,off=struct.unpack_from('<2i',d,156);bones=[]
 integer=lambda off:struct.unpack_from('<i',d,off)[0]
 string=lambda off:d[off:d.index(b'\0',off)].decode()
 for i in range(n):
  b=off+i*216;name=b+struct.unpack_from('<i',d,b)[0];name=d[name:d.index(b'\0',name)].decode()
  bones.append({'name':name,'parent':struct.unpack_from('<i',d,b+4)[0],'position':struct.unpack_from('<3f',d,b+32),'rotation':struct.unpack_from('<3f',d,b+60),'procedural':struct.unpack_from('<i',d,b+164)[0]})
 result['bones']=bones;result['ikchains']=struct.unpack_from('<i',d,284)[0]
 result['flexdescs']=struct.unpack_from('<i',d,260)[0];result['flexcontrollers']=struct.unpack_from('<i',d,268)[0]
 result['descriptors']=[string(integer(264)+i*4+integer(integer(264)+i*4)) for i in range(integer(260))]
 result['controllers']=[]
 for i in range(integer(268)):
  c=integer(272)+i*20;result['controllers'].append([string(c+integer(c+4)),*struct.unpack_from('<2f',d,c+12)])
 result['rules']=[]
 for i in range(integer(276)):
  rule=integer(280)+i*12;target,count,relative=struct.unpack_from('<3i',d,rule);ops=[]
  for k in range(count):
   op,value=struct.unpack_from('<2i',d,rule+relative+k*8)
   if op==1:value=struct.unpack_from('<f',d,rule+relative+k*8+4)[0]
   elif op==2:value=result['controllers'][value][0]
   elif op==12:value=result['descriptors'][value]
   ops.append([op,value])
  result['rules'].append([result['descriptors'][target],ops])
 result['eyes']=[]
 for b in range(integer(232)):
  bp=integer(236)+b*16
  for j in range(integer(bp+4)):
   model=bp+integer(bp+12)+j*148
   for k in range(integer(model+100)):
    eye=model+integer(model+104)+k*172
    result['eyes'].append([string(eye+integer(eye)),integer(eye+4),*struct.unpack_from('<3f',d,eye+8),struct.unpack_from('<f',d,eye+24)[0],struct.unpack_from('<f',d,eye+60)[0],*[result['descriptors'][integer(eye+64+t*4)] for t in range(6)],*struct.unpack_from('<6f',d,eye+88)])
 return result
def close(x,y):
 if isinstance(x,(tuple,list)) and isinstance(y,(tuple,list)):return len(x)==len(y) and all(close(a,b) for a,b in zip(x,y))
 if isinstance(x,(int,float)) and isinstance(y,(int,float)):return abs(x-y)<2e-4
 return x==y
report={'schema':1,'reference':str(Path(a.reference).resolve()),'cases':[]}
for name,options in cases.items():
 qc=root/(name+'.qc');qc.write_text('$modelname '+name+'\n'+('' if name in ('face','eyelid','dmx','dmx_explicit','dmx_multi','face_stereo') else '$body body mesh.smd\n')+options+definitions+'$sequence idle mesh.smd\n')
 outputs={}
 for label,compiler in [('project',a.compiler),('reference',a.reference)]:
  game=root/label;game.mkdir(exist_ok=True);(game/'gameinfo.txt').write_text('GameInfo { game fixture FileSystem { SteamAppId 220 SearchPaths { game "|gameinfo_path|." } } }')
  result=subprocess.run([str(Path(compiler).resolve()),'-game',str(game),str(qc)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
  (root/(name+'-'+label+'.log')).write_bytes(result.stdout)
  mdl=game/'models'/f'{name}.mdl'
  if result.returncode or not mdl.exists():raise RuntimeError(name+' '+label+' failed; see isolated logs')
  outputs[label]=summary(mdl)
 expected=outputs['reference'];actual=outputs['project'];differences=[]
 if [b['name'] for b in expected['bones']]!=[b['name'] for b in actual['bones']]:differences.append('bone ordering/names')
 else:
  for x,y in zip(expected['bones'],actual['bones']):
   if x['parent']!=y['parent'] or x['procedural']!=y['procedural']:differences.append(x['name']+' hierarchy/procedural')
   if any(abs(u-v)>2e-4 for field in ('position','rotation') for u,v in zip(x[field],y[field])):differences.append(x['name']+' bind transform')
 for field in ('ikchains','flexdescs','flexcontrollers'):
  if expected[field]!=actual[field]:differences.append(field)
 for field in ('descriptors','controllers','eyes','rules'):
  left,right=expected[field],actual[field]
  if field=='descriptors':left,right=sorted(left),sorted(right) # names/bindings are semantic; table order is not
  if not close(left,right):differences.append(field)
 report['cases'].append({'name':name,'outputs':outputs,'differences':differences})
(root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if any(c['differences'] for c in report['cases']):raise SystemExit(1)
