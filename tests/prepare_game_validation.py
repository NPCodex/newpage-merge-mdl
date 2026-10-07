"""Install explicitly named, self-authored fixtures for an engine smoke test.
Run the Lua server file explicitly in a local gm_flatgrass listen server.
Does not change game configuration or launch Steam/update games.
"""
import argparse,json,subprocess,sys
from pathlib import Path
from scene_fixtures import scene_bytes
p=argparse.ArgumentParser();p.add_argument('compiler');p.add_argument('--game',required=True);p.add_argument('--work',required=True);p.add_argument('--face-qc',required=True)
p.add_argument('--autorun',action='store_true',help='Install the explicitly named test InitPostEntity hook; remove after testing')
a=p.parse_args();game=Path(a.game);root=Path(a.work).resolve();root.mkdir(parents=True,exist_ok=True)
compiler=str(Path(a.compiler).resolve())
def compile(qc,text):
 result=subprocess.run([compiler,str(qc),'-stdin','-game',str(game)],input=text,text=True,capture_output=True,errors='replace')
 (root/(qc.stem+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
 if result.returncode:raise RuntimeError('compile failed: '+str(qc))
face=Path(a.face_qc).resolve()
compile(face,face.read_text(encoding='utf-8-sig')+'\n$modelname newpage_validation_v124/face.mdl\n$OutDir "'+game.as_posix()+'"\n$lod 20 { }\n')
scene=json.loads(scene_bytes());scene['materials'][0]['name']='models/debug/debugwhite';scene['nodes'][0]['children']=[1]
(root/'scene.gltf').write_text(json.dumps(scene));qc=root/'baked.qc'
(root/'idle.smd').write_text('version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\n')
text='$modelname newpage_validation_v124/baked.mdl\n$body m scene.gltf BakeSceneAnimation Move SceneSampleRate 2\n$sequence idle idle.smd\n';qc.write_text(text);compile(qc,text)
outline=[(0,0),(2,0),(2,1),(1,1),(1,2),(0,2)]
vertices=[(x,y,z) for z in (0,1) for x,y in outline];cap=[(0,1,3),(1,2,3),(0,3,5),(3,4,5)]
faces=[tuple(reversed(f)) for f in cap]+[tuple(v+6 for v in f) for f in cap]
for i in range(6):j=(i+1)%6;faces.extend([(i,j,j+6),(i,j+6,i+6)])
mesh='version 1\nnodes\n0 "root" -1\n1 "child" 0\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\n1 5 0 0 0 0 0\nend\ntriangles\n'
for bone in (0,1):
 for face in faces:mesh+='models/debug/debugwhite\n'+''.join(f'{bone} {vertices[v][0]+5*bone} {vertices[v][1]} {vertices[v][2]} 0 0 1 0 0\n' for v in face)
(root/'ragdoll.smd').write_text(mesh+'end\n');qc=root/'ragdoll.qc'
low=mesh.split('triangles\n')[0]+'triangles\n';tetra=[(0,0,0),(2,0,0),(0,2,0),(0,0,1)]
for bone in (0,1):
 for face in [(0,2,1),(0,1,3),(0,3,2),(1,2,3)]:low+='models/debug/debugwhite\n'+''.join(f'{bone} {tetra[v][0]+5*bone} {tetra[v][1]} {tetra[v][2]} 0 0 1 0 0\n' for v in face)
(root/'low.smd').write_text(low+'end\n')
text='$modelname newpage_validation_v124/ragdoll.mdl\n$bonecullmethod none\n$body m ragdoll.smd\n$sequence idle ragdoll.smd\n$lod 20 { replacemodel ragdoll.smd low.smd }\n$collisionjoints ragdoll.smd { $mass 10 $rootbone root $maxconvexpieces 4 $decomposeconcave }\n';qc.write_text(text);compile(qc,text)
lua=game/'lua/newpage_validation_v124';lua.mkdir(parents=True,exist_ok=True)
for name in ('game_validation_client.lua','game_validation_server.lua'):(lua/name).write_bytes((Path(__file__).parent/name).read_bytes())
(lua/'newpage_vertexanim.lua').write_bytes((Path(__file__).parent.parent/'integration/gmod/newpage_vertexanim.lua').read_bytes())
if a.autorun:
 auto=game/'lua/autorun/server/newpage_validation_v124.lua'
 text='hook.Add("InitPostEntity", "newpage_validation_v124_start", function() include("newpage_validation_v124/game_validation_server.lua") end)'
 if auto.exists() and auto.read_text(encoding='utf-8-sig').strip()!=text:raise RuntimeError('refusing to replace an unrelated autorun file')
 auto.parent.mkdir(parents=True,exist_ok=True);auto.write_text(text,encoding='utf-8')
print('Prepared isolated models and Lua under newpage_validation_v124')
