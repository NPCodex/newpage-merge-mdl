"""Generate isolated, self-authored Rotation/IK game fixtures (no installation)."""
import argparse
import json
from pathlib import Path
from dmx_dependency_cases import Document


def marker(rows,bone,center,radius,material):
    x,y,z=center
    points=[(x+radius,y,z),(x-radius,y,z),(x,y+radius,z),(x,y,z+radius)]
    for triangle in [(0,2,3),(2,1,3),(1,0,3),(0,1,2)]:
        for order in [triangle,tuple(reversed(triangle))]:
            rows.append(material)
            for index in order:
                p=points[index];rows.append(f'{bone} '+' '.join(map(str,p))+' 0 0 1 0 0')


def bar(rows,bone,start,end,width,material):
    # Rigid bind-space prism along X, with visible top and side faces.
    x,y,z=start;xx,yy,zz=end
    points=[(x,y-width,z-width),(x,y+width,z-width),(x,y+width,z+width),(x,y-width,z+width),
            (xx,yy-width,zz-width),(xx,yy+width,zz-width),(xx,yy+width,zz+width),(xx,yy-width,zz+width)]
    for face in [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]:
        for a,b,c in [(face[0],face[1],face[2]),(face[0],face[2],face[3])]:
            rows.append(material)
            for i in [a,b,c]:rows.append(f'{bone} '+' '.join(map(str,points[i]))+' 0 0 1 0 0')


def fixture(kind):
    rotation=kind=='rotation'
    names=['root','rot'] if rotation else ['root','upper','middle','end','target','pole']
    parents=[-1,0] if rotation else [-1,0,1,2,0,0]
    positions=[(0,0,0),(0,0,32)] if rotation else [(0,0,0),(0,0,36),(24,0,0),(24,0,0),(32,16,36),(0,0,70)]
    d=Document();d.element(1,'DmElement',kind,f'"skeleton" {d.ref(2)} "animationList" {d.ref(200)} '+d.elements('constraints',[100]))
    d.element(2,'DmeModel','model',d.elements('children',[10])+d.elements('jointList',range(10,10+len(names))))
    for i,name in enumerate(names):
        d.element(10+i,'DmeJoint',name,f'"transform" {d.ref(30+i)} '+d.elements('children',[10+j for j,p in enumerate(parents) if p==i]))
        d.element(30+i,'DmeTransform',name,'"position" "vector3" "'+' '.join(map(str,positions[i]))+'" "orientation" "quaternion" "0 0 0 1"')
    if rotation:
        d.element(100,'DmeRigRotationConstraintOperator','rotation',f'"slave" {d.ref(101)} '+d.array('axies','vector3',['0 0 1'])+d.array('rotations','float',[0]))
        d.element(101,'DmeConstraintSlave','slave',f'"target" {d.ref(11)} "orientation" "quaternion" "0 0 0 1"')
    else:
        d.element(100,'DmeRigIKConstraintOperator','ik',f'"startJoint" {d.ref(101)} "midJoint" {d.ref(102)} "endJoint" {d.ref(103)} "pvTarget" {d.ref(15)} '+d.elements('targets',[104])+' "startOffset" "quaternion" "0 0 0 1" "midOffset" "quaternion" "0 0 0 1"')
        for i,bone in enumerate([11,12,13]):d.element(101+i,'DmeConstraintSlave','joint',f'"target" {d.ref(bone)} "orientation" "quaternion" "0 0 0 1"')
        d.element(104,'DmeConstraintTarget','target',f'"target" {d.ref(14)} "targetWeight" "float" "1"')
    d.element(200,'DmeAnimationList','animations',d.elements('animations',[201]))
    d.element(201,'DmeChannelsClip','motion',f'"frameRate" "int" "30" "timeFrame" {d.ref(202)} '+d.elements('channels',[203]))
    d.element(202,'DmeTimeFrame','time','"start" "time" "0" "duration" "time" "4" "scale" "float" "1"')
    d.element(203,'DmeChannel','control',f'"toElement" {d.ref(100 if rotation else 34)} "toAttribute" "string" "'+('rotations' if rotation else 'position')+f'" "toIndex" "int" "0" "log" {d.ref(204)}')
    logkind='Float' if rotation else 'Vector3'
    d.element(204,'Dme'+logkind+'Log','log',d.elements('layers',[205]))
    values=[0,90,0,-90,0] if rotation else ['32 16 36','16 32 42','32 -16 36','40 0 32','32 16 36']
    d.element(205,'Dme'+logkind+'LogLayer','layer',d.array('times','int',[0,10000,20000,30000,40000])+d.array('values',logkind.lower(),values))
    rows=['version 1','nodes']+[f'{i} "{name}" {parents[i]}' for i,name in enumerate(names)]+['end','skeleton','time 0']
    rows += [f'{i} '+' '.join(map(str,p))+' 0 0 0' for i,p in enumerate(positions)]
    rows += ['end','triangles']
    marker(rows,0,(0,0,5),5,'base')
    if rotation:
        bar(rows,1,(0,0,32),(28,0,32),2,'cyan');marker(rows,1,(28,0,32),5,'cyan')
    else:
        bar(rows,1,(0,0,36),(24,0,36),2,'cyan');bar(rows,2,(24,0,36),(48,0,36),2,'yellow')
        marker(rows,1,(0,0,36),3,'base');marker(rows,2,(24,0,36),3,'yellow');marker(rows,3,(48,0,36),3,'cyan');marker(rows,4,(32,16,36),5,'target')
    rows+=['end']
    name='np_v1222_'+kind
    qc=f'$modelname "np_validation/{name}.mdl"\n$body markers "{name}.smd"\n$datamodeljoints "{name}.dmx" proceduralbones\n$cdmaterials "np_validation/v1222_rig/"\n$sequence motion "{name}.dmx" fps 30 loop\n$bbox -80 -80 -10 80 80 100\n'
    return name,'\n'.join(rows)+'\n',d.text(),qc


def generate(directory):
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    materials=directory/'materials'/'np_validation'/'v1222_rig';materials.mkdir(parents=True,exist_ok=True)
    for name,color in [('base','0.8 0.8 0.8'),('cyan','0.1 0.9 1'),('yellow','1 0.8 0.1'),('target','1 0.1 0.5')]:
        (materials/(name+'.vmt')).write_text('"VertexLitGeneric"\n{\n "$basetexture" "vgui/white_additive"\n "$color2" "['+color+']"\n "$selfillum" "1"\n}\n')
    entries=[]
    for kind in ['rotation','ik']:
        name,smd,dmx,qc=fixture(kind)
        for ext,body in [('smd',smd),('dmx',dmx),('qc',qc)]: (directory/(name+'.'+ext)).write_text(body)
        entries.append({'kind':kind,'qc':str(directory/(name+'.qc')),'model':'models/np_validation/'+name+'.mdl','sequence':'motion','duration_seconds':4,'fps':30,'key_values':[0,90,0,-90,0] if kind=='rotation' else [[32,16,36],[16,32,42],[32,-16,36],[40,0,32],[32,16,36]]})
    manifest={'self_authored':True,'models':entries,'materials':str(materials),'compiler_output_directory':str(directory/'compiled'),'expected_visual':'Rotation cyan pointer swings +90/-90 degrees; IK cyan/yellow bars follow moving pink target through the two-joint chain.'}
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');args=parser.parse_args()
    print(json.dumps(generate(args.directory),indent=2))
