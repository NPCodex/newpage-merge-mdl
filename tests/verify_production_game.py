"""Validate production-model engine reports without hiding missing materials."""
import argparse
import json
import math
from pathlib import Path
from PIL import Image, ImageChops

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('folder');p.add_argument('--output',required=True)
p.add_argument('--max-drift',type=float,default=200)
p.add_argument('--require-materials',action='store_true')
p.add_argument('--require-lod-reduction',action='store_true')
p.add_argument('--require-face-change',action='store_true')
a=p.parse_args();root=Path(a.folder)
client=json.loads((root/'client.json').read_text());server=json.loads((root/'server.json').read_text())
if client['errors'] or server['errors']:raise RuntimeError('Engine reported errors: '+str(client['errors']+server['errors']))
if a.require_materials and any(c['missing'] for c in client['materials']):raise RuntimeError('Missing model materials')
render_differences=[]
for model in {c['model'] for c in client['cases']}:
    cases={c['name']:c for c in client['cases'] if c['model']==model}
    if a.require_lod_reduction:
        if not 0<cases['lod1']['triangles']<cases['neutral']['triangles']:raise RuntimeError('LOD geometry did not reduce: '+model)
    if a.require_face_change:
        def changed(left,right):
            delta=ImageChops.difference(Image.open(root/cases[left]['image']).convert('RGB'),Image.open(root/cases[right]['image']).convert('RGB'))
            return sum(max(rgb)>0 for rgb in getattr(delta,'get_flattened_data',delta.getdata)())
        noise=changed('face_neutral','face_repeat');expression=changed('face_neutral','face_expression')
        if expression<=4*noise+100:raise RuntimeError('Face change indistinguishable from rendering noise: '+model)
        render_differences.append({'model':model,'noise_pixels':noise,'expression_pixels':expression})
for case in client['cases']:
    image=Image.open(root/case['image']).convert('RGB')
    if sum(pixel!=(24,36,56) for pixel in getattr(image,'get_flattened_data',image.getdata)())<100:raise RuntimeError('No visible model geometry: '+case['image'])
    if 'choice' in case and case['selected']!=case['choice']:raise RuntimeError('Bodygroup selection mismatch')
for case in server['cases']:
    if not case['count'] or len(case['bodies'])!=case['count']:raise RuntimeError('Missing physics bodies')
    for body in case['bodies']:
        if not all(math.isfinite(body[k]) for k in ('x','y','z','mass','volume','speed','drift')):raise RuntimeError('Non-finite physics')
        if body['mass']<=0 or body['volume']<=0 or body['speed']>100 or body['drift']>a.max_drift:raise RuntimeError('Unstable physics')
summary={'schema':1,'engine':'GarrysMod x64','render_cases':len(client['cases']),
         'face_differences':render_differences,'lod_reduction_required':a.require_lod_reduction,
         'geometry_and_selection_verified':True,'full_material_rendering_verified':not any(c['missing'] for c in client['materials']),
         'material_probes':client['materials'],'physics':[{'model':c['model'],'bodies':c['count'],'max_horizontal_drift':max(b['drift'] for b in c['bodies']),'max_final_speed':max(b['speed'] for b in c['bodies'])} for c in server['cases']]}
Path(a.output).write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
