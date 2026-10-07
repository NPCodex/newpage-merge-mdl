"""Check engine reports and actual rendered pixels; does not launch/control a game."""
import argparse,json,math
from pathlib import Path
from PIL import Image,ImageChops
p=argparse.ArgumentParser();p.add_argument('reports');p.add_argument('--output',required=True);a=p.parse_args();root=Path(a.reports)
server=json.loads((root/'server.json').read_text());client=json.loads((root/'client.json').read_text())
assert not server['errors'] and not client['errors'],(server['errors'],client['errors'])
assert server['physics_count']==2
assert abs(sum(body['mass'] for body in server['initial'])-10)<1e-4
assert all(2.9<body['volume']<3.2 for body in server['initial'])
assert all(math.isfinite(v) for body in server['final'] for v in body.values())
assert all(server['ground_z']-.5<body['z']<server['ground_z']+5 for body in server['final'])
def pixels(name):return Image.open(root/(name+'.png')).convert('RGB')
differences={}
for x,y in [('face_neutral','face_expression'),('face_expression','face_lod1'),('ragdoll_lod0','ragdoll_lod1'),('bake_start','bake_middle'),('bake_middle','bake_end')]:
 delta=ImageChops.difference(pixels(x),pixels(y));count=sum(max(rgb)>0 for rgb in delta.getdata())
 assert count>0,(x,y,'identical rendered pixels')
 differences[x+' -> '+y]=count
noise=sum(max(rgb)>0 for rgb in ImageChops.difference(pixels('face_neutral'),pixels('face_neutral_repeat')).getdata())
assert differences['face_neutral -> face_expression']>noise*4+100,('face change indistinguishable from rendering noise',noise)
assert differences['ragdoll_lod0 -> ragdoll_lod1']>1000,'LOD did not replace visible geometry'
for name in ('bake_start','bake_middle','bake_end'):
 assert sum(max(rgb)-min(rgb)<5 and min(rgb)>120 for rgb in pixels(name).getdata())>100,name+' did not render visible geometry'
centers=[]
for name in ('bake_start','bake_middle','bake_end'):
 im=pixels(name);points=[x for y in range(im.height) for x in range(im.width) if min(im.getpixel((x,y)))>120]
 centers.append((min(points)+max(points))*.5)
assert centers[1]-centers[0]>100 and centers[2]-centers[1]>100,('insufficient vertex animation displacement',centers)
assert abs((centers[1]-centers[0])-(centers[2]-centers[1]))<5,('nonlinear midpoint',centers)
report={'schema':1,'engine':'GarrysMod x64','map':'gm_flatgrass','geometry_material_override':'models/debug/debugwhite','server':server,'client':client,'changed_pixels':differences}
report['baked_screen_center_x']=centers
report['neutral_repeat_changed_pixels']=noise
Path(a.output).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
