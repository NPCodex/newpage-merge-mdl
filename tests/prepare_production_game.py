"""Compile user production models into explicitly isolated game paths.

Installs a named temporary autorun; remove it after testing. User QC/assets
remain unchanged, and are not packaged or pushed to GitHub.
"""
import argparse
import json
from pathlib import Path
import subprocess

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('compiler');p.add_argument('--qc',action='append',required=True)
p.add_argument('--game',required=True);p.add_argument('--work',required=True)
a=p.parse_args();game=Path(a.game).resolve();work=Path(a.work).resolve();work.mkdir(parents=True,exist_ok=True)
models=[]
for i,qc in enumerate(a.qc):
    qc=Path(qc).resolve();name='hair_player' if i==0 else 'hair_npc'
    text=qc.read_text(encoding='utf-8-sig')+'\n$modelname newpage_production_validation/'+name+'.mdl\n$OutDir "'+game.as_posix()+'"\n'
    result=subprocess.run([str(Path(a.compiler).resolve()),str(qc),'-stdin','-game',str(game)],input=text,text=True,capture_output=True,errors='replace')
    (work/(name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode:raise RuntimeError('production compile failed: '+str(qc))
    models.append('models/newpage_production_validation/'+name+'.mdl')
lua=game/'lua/newpage_production_validation';lua.mkdir(parents=True,exist_ok=True)
(lua/'config.lua').write_text('return {models={'+','.join(json.dumps(m) for m in models)+'}}')
for source,target in [('production_game_client.lua','client.lua'),('production_game_server.lua','server.lua')]:
    (lua/target).write_bytes(Path(__file__).with_name(source).read_bytes())
auto=game/'lua/autorun/server/newpage_production_validation.lua'
hook='hook.Add("InitPostEntity","newpage_production_validation",function() include("newpage_production_validation/server.lua") end)'
if auto.exists() and auto.read_text().strip()!=hook:raise RuntimeError('refusing to overwrite unrelated autorun')
auto.parent.mkdir(parents=True,exist_ok=True);auto.write_text(hook)
print('Production models and temporary validation autorun prepared.')
