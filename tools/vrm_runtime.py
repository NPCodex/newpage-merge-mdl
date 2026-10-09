#!/usr/bin/env python3
"""Prepare VRM 0.x/1.0 expressions and spring metadata for the GMod runtime."""
import argparse
import base64
import copy
import json
import math
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import sys
from mesh_states import number, quoted, write_atomic


def vector(value, label, default=None):
    if value is None: value=default
    if isinstance(value,dict): value=[value.get(k,0) for k in ('x','y','z')]
    if not isinstance(value,list) or len(value)!=3: raise ValueError(label+' must be a 3-vector')
    return [number(v,label) for v in value]


def index(value, sequence, label):
    if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<len(sequence):
        raise ValueError('invalid '+label+' index')
    return value


def load_document(path):
    raw=path.read_bytes()
    if raw[:4]!=b'glTF': return json.loads(raw.decode('utf-8-sig'))
    if len(raw)<20: raise ValueError('truncated GLB')
    _,version,size=struct.unpack_from('<III',raw)
    if version!=2 or size!=len(raw): raise ValueError('invalid GLB version/length')
    cursor=12;doc=None;binary=None
    while cursor<len(raw):
        if cursor+8>len(raw): raise ValueError('truncated GLB chunk')
        length,kind=struct.unpack_from('<II',raw,cursor);cursor+=8
        if length%4 or cursor+length>len(raw): raise ValueError('invalid GLB chunk length')
        chunk=raw[cursor:cursor+length];cursor+=length
        if kind==0x4e4f534a:
            if doc is not None: raise ValueError('duplicate GLB JSON')
            doc=json.loads(chunk.decode('utf-8').rstrip('\0 '))
        elif kind==0x004e4942:
            if binary is not None: raise ValueError('duplicate GLB binary')
            binary=chunk
    if doc is None: raise ValueError('missing GLB JSON')
    if binary is not None:
        buffers=doc.get('buffers',[])
        if not buffers or 'uri' in buffers[0] or buffers[0]['byteLength']>len(binary):
            raise ValueError('invalid GLB buffer')
        buffers[0]['uri']='data:application/octet-stream;base64,'+base64.b64encode(binary).decode()
    return doc


def multiply(a,b):
    return [[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def point(m,v): return [sum(m[i][k]*v[k] for k in range(3))+m[i][3] for i in range(3)]


def transforms(nodes):
    parents={}
    for i,n in enumerate(nodes):
        for child in n.get('children',[]):
            index(child,nodes,'child')
            if child in parents: raise ValueError('VRM node has multiple parents')
            parents[child]=i
    worlds={};active=set()
    def world(i):
        if i in worlds:return worlds[i]
        if i in active:raise ValueError('VRM node hierarchy cycle')
        active.add(i);node=nodes[i]
        if 'matrix' in node:
            values=node['matrix']
            if len(values)!=16: raise ValueError('invalid node matrix')
            m=[[number(values[j*4+k],'matrix') for j in range(4)] for k in range(4)]
        else:
            x,y,z,w=node.get('rotation',[0,0,0,1])
            q=[number(v,'rotation') for v in (x,y,z,w)];length=math.sqrt(sum(v*v for v in q))
            if length<1e-10: raise ValueError('zero node quaternion')
            x,y,z,w=[v/length for v in q]
            m=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w),0],
               [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w),0],
               [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y),0],[0,0,0,1]]
            scale=vector(node.get('scale'),'scale',[1,1,1]);translation=vector(node.get('translation'),'translation',[0,0,0])
            for row in range(3):
                for col in range(3):m[row][col]*=scale[col]
                m[row][3]=translation[row]
        if i in parents:m=multiply(world(parents[i]),m)
        active.remove(i);worlds[i]=m;return m
    for i in range(len(nodes)):world(i)
    return worlds,parents


def prepare(document, source_dir, modelname, scale=39.3700787402):
    scale=number(scale,'scale',True)
    if not re.fullmatch(r'[A-Za-z0-9_./-]+',modelname):raise ValueError('invalid modelname')
    path=PurePosixPath(modelname)
    if path.is_absolute() or '..' in path.parts or path.suffix.lower() not in ('','.mdl') or not path.name:
        raise ValueError('modelname must be a relative .mdl path')
    if path.parts[0]=='models':path=PurePosixPath(*path.parts[1:])
    path=path.with_suffix('.mdl')
    doc=copy.deepcopy(document);extensions=doc.get('extensions',{})
    v1=extensions.get('VRMC_vrm');v0=extensions.get('VRM')
    if not v1 and not v0:raise ValueError('document has neither VRM 0.x nor VRMC_vrm 1.0 metadata')
    if v1 and v0:raise ValueError('ambiguous VRM 0.x and 1.0 metadata')
    nodes=doc.get('nodes',[]);meshes=list(doc.get('meshes',[]));worlds,parents=transforms(nodes)
    warnings=[];keep=set();original_names=[n.get('name','') for n in nodes]
    for i,node in enumerate(nodes):node['name']='vrm_node_'+str(i)
    # Stable per-node morph names preserve VRM 1's node-specific bindings even
    # when several nodes instantiate one glTF mesh.
    aliases={};node_mesh={};mesh_nodes={}
    for i,node in enumerate(nodes):
        if 'mesh' not in node:continue
        source=index(node['mesh'],meshes,'mesh');mesh_nodes.setdefault(source,[]).append(i)
        mesh=copy.deepcopy(meshes[source]);slot=len(doc['meshes']);doc['meshes'].append(mesh)
        node['mesh']=slot;node_mesh[i]=mesh
        counts={len(p.get('targets',[])) for p in mesh.get('primitives',[])}
        if len(counts)>1:raise ValueError('inconsistent primitive morph counts')
        names=['vrm_n'+str(i)+'_m'+str(j) for j in range(next(iter(counts),0))]
        mesh.setdefault('extras',{})['targetNames']=names
        for j,name in enumerate(names):aliases[i,j]=name
    def node_name(i):
        index(i,nodes,'node');keep.add(i);return nodes[i]['name']
    def binding(node,morph,weight):
        index(node,nodes,'morph node')
        if isinstance(morph,bool) or not isinstance(morph,int):raise ValueError('invalid expression morph index')
        if (node,morph) not in aliases:raise ValueError('invalid expression morph index')
        weight=number(weight,'morph weight')
        if not 0<=weight<=1:raise ValueError('morph weight must be within [0,1]')
        return dict(controller='ctrl_'+aliases[node,morph],weight=weight)
    expressions={}
    entries=[]
    if v1:
        for group in ('preset','custom'):
            for name,expression in v1.get('expressions',{}).get(group,{}).items():entries.append((name,expression))
    else:
        for expression in v0.get('blendShapeMaster',{}).get('blendShapeGroups',[]):
            name=expression.get('presetName')
            if not name or name=='unknown':name=expression.get('name')
            entries.append((name,expression))
    for name,e in entries:
        if not isinstance(name,str) or not name or name in expressions:raise ValueError('empty/duplicate expression name')
        binary=e.get('isBinary',False)
        if not isinstance(binary,bool):raise ValueError('isBinary must be boolean')
        row=dict(binary=binary,binds=[],material_binds=[],overrides={})
        if v1:
            for bind in e.get('morphTargetBinds',[]):row['binds'].append(binding(bind['node'],bind['index'],bind['weight']))
            for key in ('overrideBlink','overrideLookAt','overrideMouth'):
                value=e.get(key,'none')
                if value not in ('none','block','blend'):raise ValueError('invalid expression override')
                row['overrides'][key]=value
            for bind in e.get('materialColorBinds',[]):
                material=index(bind['material'],doc.get('materials',[]),'material')
                row['material_binds'].append(dict(kind='color',material=material,property=bind['type'],target=bind['targetValue']))
            for bind in e.get('textureTransformBinds',[]):
                material=index(bind['material'],doc.get('materials',[]),'material')
                row['material_binds'].append(dict(kind='texture',material=material,scale=bind['scale'],offset=bind['offset']))
        else:
            for bind in e.get('binds',[]):
                mesh=index(bind['mesh'],meshes,'expression mesh')
                for node in mesh_nodes.get(mesh,[]):row['binds'].append(binding(node,bind['index'],number(bind['weight'],'weight')/100))
            for bind in e.get('materialValues',[]):
                matches=[i for i,m in enumerate(doc.get('materials',[])) if m.get('name')==bind['materialName']]
                if len(matches)!=1:raise ValueError('ambiguous expression material name')
                row['material_binds'].append(dict(kind='legacy',material=matches[0],property=bind['propertyName'],target=bind['targetValue']))
        expressions[name]=row
    # Standard glTF animation weight tracks otherwise conflict with named QC
    # expression controls. Only discard these explicit tracks, retaining bone animation.
    for animation in doc.get('animations',[]):
        channels=animation.get('channels',[])
        if any(c.get('target',{}).get('path')=='weights' for c in channels):
            warnings.append('glTF animated morph-weight tracks replaced by VRM expression controls')
            animation['channels']=[c for c in channels if c.get('target',{}).get('path')!='weights']
    def metric(i):
        m=worlds[i];lengths=[math.sqrt(sum(m[r][c]**2 for r in range(3))) for c in range(3)]
        if min(lengths)<1e-8 or max(lengths)-min(lengths)>1e-5*max(lengths):
            raise ValueError('spring/collider nodes require uniform nonzero world scale; bake scale in the authoring tool')
        for a in range(3):
            for b in range(a):
                if abs(sum(m[r][a]*m[r][b] for r in range(3)))>1e-5*lengths[a]*lengths[b]:
                    raise ValueError('spring/collider shear must be baked')
        determinant=(m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1])
                     -m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0])
                     +m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0]))
        if determinant<0:raise ValueError('spring/collider reflected transforms must be baked')
        return lengths[0]*scale
    colliders=[];groups=[];springs=[]
    spring_ext=extensions.get('VRMC_springBone',{}) if v1 else v0.get('secondaryAnimation',{})
    def collider(node,shape):
        name=node_name(node);factor=metric(node)
        kind='sphere' if 'sphere' in shape else 'capsule' if 'capsule' in shape else ''
        if not kind:raise ValueError('unsupported spring collider shape')
        definition=shape[kind];offset=vector(definition.get('offset'),'collider offset',[0,0,0])
        radius=number(definition.get('radius',0),'collider radius')
        if radius<0:raise ValueError('negative collider radius')
        row=dict(bone=name,shape=kind,offset=[v*factor for v in offset],radius=radius*factor)
        if kind=='capsule':row['tail']=[v*factor for v in vector(definition['tail'],'collider tail')]
        colliders.append(row);return len(colliders)-1
    if v1:
        for c in spring_ext.get('colliders',[]):collider(c['node'],c['shape'])
        for group in spring_ext.get('colliderGroups',[]):
            groups.append([index(i,colliders,'collider') for i in group.get('colliders',[])])
        raw_springs=spring_ext.get('springs',[])
    else:
        for group in spring_ext.get('colliderGroups',[]):
            groups.append([collider(group['node'],{'sphere':c}) for c in group.get('colliders',[])])
        raw_springs=[]
        for old in spring_ext.get('boneGroups',[]):
            joints=[];seen=set()
            def walk(i):
                index(i,nodes,'spring node')
                if i in seen:return
                seen.add(i);joints.append(dict(node=i,stiffness=old.get('stiffiness',1),
                    gravityPower=old.get('gravityPower',0),gravityDir=old.get('gravityDir',[0,-1,0]),
                    dragForce=old.get('dragForce',.4),hitRadius=old.get('hitRadius',0)))
                for child in nodes[i].get('children',[]):walk(child)
            for root in old.get('bones',[]):walk(root)
            raw_springs.append(dict(name=old.get('comment',''),center=old.get('center',-1),
                                    joints=joints,colliderGroups=old.get('colliderGroups',[])))
    owned=set()
    for raw in raw_springs:
        row=dict(name=raw.get('name',''),joints=[],colliders=[])
        if raw.get('center',-1)!=-1:row['center']=node_name(raw['center'])
        for group in raw.get('colliderGroups',[]):row['colliders'].extend(groups[index(group,groups,'collider group')])
        row['colliders']=sorted(set(row['colliders']))
        source_joints=raw.get('joints',[])
        if v1:
            # VRM 1 is an explicit chain of head/tail pairs. The last entry
            # only supplies a tail position, and a pair may skip scene nodes.
            chain=[index(j['node'],nodes,'spring node') for j in source_joints]
            if not chain:raise ValueError('VRM 1 spring requires at least one joint')
            occupied=set(chain)
            if len(occupied)!=len(chain):raise ValueError('spring node belongs to multiple springs')
            for head,tail_node in zip(chain,chain[1:]):
                ancestor=parents.get(tail_node)
                while ancestor is not None and ancestor!=head:
                    occupied.add(ancestor);ancestor=parents.get(ancestor)
                if ancestor!=head:raise ValueError('spring joint must descend from the preceding joint')
            if owned.intersection(occupied):raise ValueError('spring node belongs to multiple springs')
            owned.update(occupied)
            if 'center' in row:
                ancestor=chain[0]
                while ancestor is not None and ancestor!=raw['center']:ancestor=parents.get(ancestor)
                if ancestor is None:raise ValueError('spring center must be the first joint or an ancestor')
        for joint_index,j in enumerate(source_joints):
            i=index(j['node'],nodes,'spring node')
            if v1 and joint_index==len(source_joints)-1:continue
            if not v1:
                if i in owned:raise ValueError('spring node belongs to multiple springs')
                owned.add(i)
            name=node_name(i);factor=metric(i)
            children=nodes[i].get('children',[])
            tail_node=chain[joint_index+1] if v1 else children[0] if children else None
            tail=None
            if tail_node is not None:
                m=worlds[i];p=[worlds[tail_node][r][3]-m[r][3] for r in range(3)]
                tail=[sum(m[r][c]*p[r] for r in range(3))/(factor/scale)**2 for c in range(3)]
            if tail is None or sum(v*v for v in tail)<1e-12:
                if v1:raise ValueError('spring head and tail must have different positions')
                tail=[0,.07,0]
            stiffness=number(j.get('stiffness',1),'stiffness');gravity=number(j.get('gravityPower',0),'gravity power')
            drag=number(j.get('dragForce',.5 if v1 else .4),'drag');radius=number(j.get('hitRadius',0),'hit radius')
            if min(stiffness,gravity,radius)<0 or not 0<=drag<=1:raise ValueError('invalid spring parameters')
            direction=vector(j.get('gravityDir'),'gravity direction',[0,-1,0]);x,y,z=direction
            row['joints'].append(dict(bone=name,tail=[v*factor for v in tail],stiffness=stiffness,
                gravity=gravity*scale,gravity_dir=[x,-z,y],drag=drag,radius=radius*factor))
        if row['joints']:springs.append(row)
    for collection in ('buffers','images'):
        for item in doc.get(collection,[]):
            uri=item.get('uri','')
            if uri and not uri.startswith('data:'):
                if re.match(r'^[A-Za-z]+://',uri):raise ValueError('external network assets must be downloaded before conversion')
                item['uri']=(source_dir/uri).resolve().as_posix()
    for extension in ('VRM','VRMC_vrm','VRMC_springBone'):
        doc.get('extensions',{}).pop(extension,None)
        for field in ('extensionsRequired','extensionsUsed'):
            doc[field]=[v for v in doc.get(field,[]) if v!=extension]
    materials=[]
    for i,m in enumerate(doc.get('materials',[])):
        original=m.get('name','material_'+str(i));name='vrm_material_'+str(i);m['name']=name
        materials.append(dict(name=name,original_name=original,
            base_color=m.get('pbrMetallicRoughness',{}).get('baseColorFactor',[1,1,1,1])))
    metadata=dict(schema=1,type='newpage_vrm',version='1.0' if v1 else '0.x',model='models/'+path.as_posix(),
        scale=scale,expressions=expressions,springs=springs,colliders=colliders,materials=materials,
        nodes=[dict(name=n['name'],original_name=original_names[i]) for i,n in enumerate(nodes)],warnings=sorted(set(warnings)))
    # -90 cancels the QC compiler's built-in +90 yaw. glTF importer converts Y up to Z up.
    qc=['$modelname '+quoted(path.as_posix()),'$transformmodel angles 0 0 -90 scale '+str(scale)]
    for i in sorted(keep):qc.append('$bonemerge '+quoted(nodes[i]['name']))
    qc.extend(['$model avatar "avatar.gltf" {'])
    used=sorted({b['controller'][5:] for e in expressions.values() for b in e['binds']})
    for alias in used:qc.extend(['flex '+alias,'flexcontroller vrm range 0 1 ctrl_'+alias,'%'+alias+' = ctrl_'+alias])
    qc.append('}')
    return doc,metadata,'\n'.join(qc)+'\n'


def bake_expressions(metadata,clip,fps):
    fps=number(fps,'clip fps',True)
    if fps>240:raise ValueError('clip fps must be <=240')
    if not isinstance(clip,list) or not clip:raise ValueError('expression clip must be a nonempty keyframe array')
    previous=-1
    for key in clip:
        t=number(key['time'],'clip time')
        if t<0 or t<=previous:raise ValueError('clip key times must be nonnegative and increase')
        previous=t
        for name,value in key.get('weights',{}).items():
            if name not in metadata['expressions']:raise ValueError('unknown expression '+name)
            if not 0<=number(value,'expression weight')<=1:raise ValueError('expression weights must be within [0,1]')
    if clip[0]['time']!=0:raise ValueError('expression clip must start at zero')
    count=math.ceil(previous*fps)+1
    if count>100000:raise ValueError('expression clip exceeds 100000 samples')
    samples=[];cursor=0
    for frame in range(count):
        t=min(frame/fps,previous)
        while cursor+1<len(clip) and clip[cursor+1]['time']<=t:cursor+=1
        a=clip[cursor];b=clip[min(cursor+1,len(clip)-1)]
        u=(t-a['time'])/(b['time']-a['time']) if a is not b else 0
        samples.append({name:(a.get('weights',{}).get(name,0)*(1-u)+b.get('weights',{}).get(name,0)*u)
                        for name in metadata['expressions']})
    return dict(fps=fps,duration=previous,samples=samples)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--modelname',default='vrm/avatar');parser.add_argument('--scale',type=float,default=39.3700787402)
    parser.add_argument('--compiler',type=Path);parser.add_argument('--game',type=Path)
    parser.add_argument('--expression-clip',type=Path);parser.add_argument('--fps',type=float,default=60)
    args=parser.parse_args(argv)
    try:
        if bool(args.compiler)!=bool(args.game):raise ValueError('--compiler and --game must be supplied together')
        doc,metadata,qc=prepare(load_document(args.source),args.source.resolve().parent,args.modelname,args.scale)
        if args.expression_clip:metadata['clip']=bake_expressions(metadata,json.loads(args.expression_clip.read_text()),args.fps)
        out=args.out.resolve();write_atomic(out/'avatar.gltf',json.dumps(doc,ensure_ascii=False))
        write_atomic(out/'avatar.qc',qc)
        if args.compiler:
            result=subprocess.run([str(args.compiler.resolve()),str(out/'avatar.qc'),'-game',str(args.game.resolve())])
            if result.returncode:return result.returncode
            if not (args.game.resolve()/metadata['model']).is_file():raise ValueError('expected compiled model is missing')
        target=(args.game.resolve() if args.game else out)/PurePosixPath(metadata['model']).with_suffix('.vrm.json')
        write_atomic(target,json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
        for warning in metadata['warnings']:print('warning: '+warning)
        print('QC: '+str(out/'avatar.qc'));print('VRM runtime metadata: '+str(target));return 0
    except (OSError,ValueError,KeyError,TypeError) as e:
        print('vrm_runtime: '+str(e),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
