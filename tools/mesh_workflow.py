#!/usr/bin/env python3
"""Simplify static OBJ/GLB geometry or export convex decomposition as OBJ."""
import argparse
import base64
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
from urllib.parse import unquote

from output_transaction import Publication, different_paths
from vrm_runtime import load_document, transforms, point


MAX_BYTES = 512 * 1024 * 1024


def finite(values):
    result = [float(v) for v in values]
    if not all(math.isfinite(v) and abs(v) <= 3.402823466e38 for v in result):
        raise ValueError('geometry must contain finite binary32 values')
    return result


def sub(a, b): return [a[i]-b[i] for i in range(3)]
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def cross(a, b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def triangulate(indices, vertices):
    if len(indices) < 3: raise ValueError('OBJ face needs at least three vertices')
    if len(indices) == 3: return list(indices)
    points = [vertices[i] for i in indices]
    normal = [0., 0., 0.]
    for a, b in zip(points, points[1:]+points[:1]):
        normal = [normal[i]+cross(a, b)[i] for i in range(3)]
    axis = max(range(3), key=lambda i: abs(normal[i]))
    if abs(normal[axis]) < 1e-12: raise ValueError('degenerate OBJ polygon')
    axes = [i for i in range(3) if i != axis]
    p = [[v[i] for i in axes] for v in points]
    turn = lambda a, b, c: (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])
    orientation = 1 if sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(p, p[1:]+p[:1])) > 0 else -1
    left, result = list(range(len(indices))), []
    while len(left) > 3:
        found = False
        for at, b in enumerate(left):
            a, c = left[at-1], left[(at+1)%len(left)]
            if orientation*turn(p[a], p[b], p[c]) <= 1e-12: continue
            if any(all(orientation*turn(p[x], p[y], p[k]) >= -1e-12 for x, y in ((a,b),(b,c),(c,a)))
                   for k in left if k not in (a,b,c)): continue
            result.extend((indices[a],indices[b],indices[c])); del left[at]; found=True; break
        if not found: raise ValueError('OBJ polygon is self-intersecting or degenerate; triangulate it in the authoring tool')
    result.extend(indices[i] for i in left)
    return result


def read_obj(path):
    positions, normals, uvs, vertices, attributes, runs, mapping = [], [], [], [], [], [], {}
    group, material, libraries = 'mesh', '', []
    def resolve(value, values):
        index = int(value); index = index-1 if index > 0 else len(values)+index
        if not 0 <= index < len(values): raise ValueError('OBJ vertex/attribute index is out of range')
        return index
    for line_number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        tokens = line.split('#', 1)[0].split()
        if not tokens: continue
        try:
            kind, values = tokens[0], tokens[1:]
            if kind == 'v':
                if len(values) != 3: raise ValueError('OBJ positions must have exactly three components')
                positions.append(finite(values))
            elif kind == 'vn':
                if len(values) != 3: raise ValueError('OBJ normals need three components')
                normals.append(finite(values))
            elif kind == 'vt':
                if len(values) != 2: raise ValueError('OBJ texture coordinates need two components')
                uvs.append(finite(values))
            elif kind in ('o', 'g'): group = '_'.join(values) or 'mesh'
            elif kind == 'usemtl': material = ' '.join(values)
            elif kind == 'mtllib': libraries.extend(values)
            elif kind == 'f':
                face = []
                for value in values:
                    corner = value.split('/')
                    if len(corner) > 3: raise ValueError('invalid OBJ face corner')
                    vi = resolve(corner[0], positions)
                    ti = resolve(corner[1], uvs) if len(corner)>1 and corner[1] else None
                    ni = resolve(corner[2], normals) if len(corner)>2 and corner[2] else None
                    identity = (vi, ti, ni)
                    if identity not in mapping:
                        mapping[identity] = len(vertices); vertices.append(positions[vi])
                        attributes.append((uvs[ti] if ti is not None else None, normals[ni] if ni is not None else None))
                    face.append(mapping[identity])
                if not runs or (runs[-1]['name'],runs[-1]['material']) != (group, material):
                    runs.append(dict(name=group,material=material,indices=[]))
                runs[-1]['indices'].extend(triangulate(face, vertices))
            elif kind in ('l','p','curv','surf'):
                raise ValueError('only polygon geometry is supported; convert curves/points to triangles')
        except (ValueError, IndexError) as error:
            raise ValueError(f'{path}:{line_number}: {error}') from error
    return dict(vertices=vertices, attributes=attributes, runs=runs,
                warnings=['OBJ material libraries/textures are not copied; material names are retained'] if libraries else [])


def read_glb(path):
    doc = load_document(path)
    if doc.get('animations') or doc.get('skins'): raise ValueError('mesh workflow needs a static GLB; bake skin/animation first')
    buffers=[]
    for buffer in doc.get('buffers',[]):
        uri=buffer.get('uri','')
        if not uri.startswith('data:') or ';base64,' not in uri:
            raise ValueError('GLB external buffers must be embedded before mesh processing')
        buffers.append(base64.b64decode(uri.split(',',1)[1],validate=True))
    def accessor(index):
        if type(index) is not int or not 0<=index<len(doc.get('accessors',[])): raise ValueError('invalid GLB accessor')
        a=doc['accessors'][index]
        if 'sparse' in a: raise ValueError('sparse GLB accessors must be expanded before mesh processing')
        view=doc['bufferViews'][a['bufferView']]; data=buffers[view['buffer']]
        widths={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}
        formats={5120:('b',1),5121:('B',1),5122:('h',2),5123:('H',2),5125:('I',4),5126:('f',4)}
        width=widths[a['type']];code,size=formats[a['componentType']]
        offset=view.get('byteOffset',0)+a.get('byteOffset',0); stride=view.get('byteStride',width*size)
        count=a['count']
        if type(count) is not int or count<0 or count>16_777_216 or stride<width*size or offset<0:
            raise ValueError('invalid GLB accessor size/stride')
        end=offset+(count-1)*stride+width*size if count else offset
        if end>len(data) or end>view.get('byteOffset',0)+view['byteLength']:raise ValueError('truncated GLB accessor')
        result=[]
        for i in range(count):
            values=struct.unpack_from('<'+code*width,data,offset+i*stride)
            if a.get('normalized') and code!='f':
                limit=(1<<(size*8-(1 if code.islower() else 0)))-1
                values=[max(-1,v/limit) for v in values]
            result.append(finite(values))
        return result
    nodes=doc.get('nodes',[]); worlds,parents=transforms(nodes)
    roots=doc.get('scenes',[{}])[doc.get('scene',0)].get('nodes',[i for i in range(len(nodes)) if i not in parents])
    selected=[]
    def walk(i):
        if type(i) is not int or not 0<=i<len(nodes):raise ValueError('invalid GLB scene node')
        if i in selected:raise ValueError('duplicate GLB scene node')
        selected.append(i)
        for child in nodes[i].get('children',[]):walk(child)
    for i in roots:walk(i)
    vertices, attributes, runs = [], [], []
    for node_id in selected:
        node=nodes[node_id]
        if 'mesh' not in node:continue
        matrix=worlds[node_id]
        a,b,c=([matrix[r][col] for r in range(3)] for col in range(3))
        determinant=dot(a,cross(b,c))
        if abs(determinant)<1e-12:raise ValueError('singular GLB transform')
        normal_columns=[cross(b,c),cross(c,a),cross(a,b)]
        for primitive in doc['meshes'][node['mesh']].get('primitives',[]):
            if primitive.get('mode',4)!=4 or primitive.get('targets'):raise ValueError('GLB needs static triangle primitives without morph targets')
            attrs=primitive['attributes']; positions=accessor(attrs['POSITION'])
            if any(len(p)!=3 for p in positions):raise ValueError('GLB POSITION must be VEC3')
            normals=accessor(attrs['NORMAL']) if 'NORMAL' in attrs else [None]*len(positions)
            uv=accessor(attrs['TEXCOORD_0']) if 'TEXCOORD_0' in attrs else [None]*len(positions)
            if len(normals)!=len(positions) or len(uv)!=len(positions):raise ValueError('GLB attribute counts differ')
            base=len(vertices)
            for p,n,t in zip(positions,normals,uv):
                vertices.append(finite(point(matrix,p)))
                if n is not None:
                    if len(n)!=3:raise ValueError('GLB NORMAL must be VEC3')
                    n=[sum(normal_columns[k][r]*n[k] for k in range(3))/determinant for r in range(3)]
                    length=math.sqrt(dot(n,n));n=[x/length for x in n] if length else [0,0,0]
                if t is not None and len(t)!=2:raise ValueError('GLB TEXCOORD_0 must be VEC2')
                attributes.append((t,n))
            raw=accessor(primitive['indices']) if 'indices' in primitive else [[i] for i in range(len(positions))]
            indices=[]
            for value in raw:
                if len(value)!=1 or value[0]!=int(value[0]) or not 0<=value[0]<len(positions):raise ValueError('invalid GLB triangle index')
                indices.append(base+int(value[0]))
            if len(indices)%3:raise ValueError('GLB triangle indices must be divisible by three')
            if determinant<0:
                for i in range(0,len(indices),3):indices[i+1],indices[i+2]=indices[i+2],indices[i+1]
            material=doc.get('materials',[])[primitive['material']].get('name','material_'+str(primitive['material'])) if 'material' in primitive else ''
            runs.append(dict(name=node.get('name','node_'+str(node_id)),material=material,indices=indices))
    return dict(vertices=vertices,attributes=attributes,runs=runs,
                warnings=['OBJ preserves geometry, normals, UV0 and material names; GLB textures/shaders are not converted'])


def read_mesh(path):
    if path.stat().st_size>MAX_BYTES:raise ValueError('mesh input exceeds 512 MiB')
    if path.suffix.lower()=='.obj':mesh=read_obj(path)
    elif path.suffix.lower()=='.glb':mesh=read_glb(path)
    else:raise ValueError('input must be OBJ or GLB')
    if not mesh['vertices'] or not any(r['indices'] for r in mesh['runs']):raise ValueError('input has no triangles')
    if len(mesh['vertices'])>4_194_304:raise ValueError('vertex pool exceeds meshtool limit')
    return mesh


class Reader:
    def __init__(self,data):self.data=data;self.at=0
    def unpack(self,format):
        size=struct.calcsize('<'+format)
        if size>len(self.data)-self.at:raise ValueError('truncated meshtool response')
        values=struct.unpack_from('<'+format,self.data,self.at);self.at+=size;return values
    def count(self,limit):
        value=self.unpack('I')[0]
        if value>limit:raise ValueError('meshtool response exceeds geometry budget')
        return value
    def finish(self):
        if self.at!=len(self.data):raise ValueError('trailing bytes in meshtool response')


def convex_faces(points):
    """Incremental oriented hull; verify containment before publishing faces."""
    if len(points)<4:raise ValueError('convex result has fewer than four points')
    extent=max(max(p[i] for p in points)-min(p[i] for p in points) for i in range(3))
    epsilon=max(1e-10,extent*1e-7)
    a=min(range(len(points)),key=lambda i:points[i][0])
    b=max(range(len(points)),key=lambda i:dot(sub(points[i],points[a]),sub(points[i],points[a])))
    c=max(range(len(points)),key=lambda i:dot(cross(sub(points[b],points[a]),sub(points[i],points[a])),cross(sub(points[b],points[a]),sub(points[i],points[a]))))
    plane=cross(sub(points[b],points[a]),sub(points[c],points[a]))
    d=max(range(len(points)),key=lambda i:abs(dot(plane,sub(points[i],points[a]))))
    if abs(dot(plane,sub(points[d],points[a])))<=epsilon*math.sqrt(dot(plane,plane)):
        raise ValueError('convex result is coplanar/degenerate')
    center=[sum(points[i][k] for i in (a,b,c,d))/4 for k in range(3)]
    def orient(face):
        x,y,z=face;n=cross(sub(points[y],points[x]),sub(points[z],points[x]))
        return (x,z,y) if dot(n,sub(center,points[x]))>0 else face
    def distance(face,p):
        x,y,z=face;n=cross(sub(points[y],points[x]),sub(points[z],points[x]));length=math.sqrt(dot(n,n))
        return dot(n,sub(p,points[x]))/length if length else 0
    faces=[orient(f) for f in ((a,b,c),(a,b,d),(a,c,d),(b,c,d))]
    for i,p in enumerate(points):
        if i in (a,b,c,d):continue
        visible=[f for f in faces if distance(f,p)>epsilon]
        if not visible:continue
        edges={}
        for x,y,z in visible:
            for edge in ((x,y),(y,z),(z,x)):
                identity=tuple(sorted(edge));edges[identity]=None if identity in edges else edge
        faces=[f for f in faces if f not in visible]
        faces.extend(orient((edge[0],edge[1],i)) for edge in edges.values() if edge is not None)
    if any(distance(face,p)>epsilon*4 for face in faces for p in points):raise ValueError('convex face reconstruction failed containment check')
    return [i for face in faces for i in face]


def obj_text(mesh):
    lines=['# NewPageMergeMDL mesh workflow; geometry export']
    used=sorted({i for run in mesh['runs'] for i in run['indices']}); ids={i:j+1 for j,i in enumerate(used)}
    uv_ids,normal_ids={},{}
    for i in used:lines.append('v '+' '.join(format(v,'.9g') for v in mesh['vertices'][i]))
    for i in used:
        uv,normal=mesh['attributes'][i]
        if uv is not None:uv_ids[i]=len(uv_ids)+1;lines.append('vt '+' '.join(format(v,'.9g') for v in uv))
    for i in used:
        normal=mesh['attributes'][i][1]
        if normal is not None:normal_ids[i]=len(normal_ids)+1;lines.append('vn '+' '.join(format(v,'.9g') for v in normal))
    for run in mesh['runs']:
        clean=lambda s:str(s).replace('\n','_').replace('\r','_').replace('#','_')
        lines.append('g '+clean(run['name']))
        if run['material']:lines.append('usemtl '+clean(run['material']))
        for at in range(0,len(run['indices']),3):
            corners=[]
            for i in run['indices'][at:at+3]:
                value=str(ids[i])
                if i in uv_ids or i in normal_ids:value+='/'+(str(uv_ids[i]) if i in uv_ids else '')
                if i in normal_ids:value+='/'+str(normal_ids[i])
                corners.append(value)
            lines.append('f '+' '.join(corners))
    return '\n'.join(lines)+'\n'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('simplify','decompose'));parser.add_argument('source',type=Path)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--summary',type=Path)
    parser.add_argument('--meshtool',type=Path,default=Path(__file__).resolve().parents[1]/'subtools'/('meshtool.exe' if os.name=='nt' else 'meshtool'))
    parser.add_argument('--ratio',type=float,default=.5);parser.add_argument('--unlock-borders',action='store_true')
    parser.add_argument('--max-hulls',type=int,default=16);parser.add_argument('--concavity',type=float,default=.0025)
    parser.add_argument('--resolution',type=int,default=100000);parser.add_argument('--timeout',type=float,default=300)
    args=parser.parse_args(argv)
    try:
        if args.output.suffix.lower()!='.obj':raise ValueError('output must have .obj extension')
        if not math.isfinite(args.ratio) or not 0<args.ratio<=1:raise ValueError('ratio must be within (0,1]')
        if not math.isfinite(args.concavity) or not 0<=args.concavity<=1:raise ValueError('concavity must be within [0,1]')
        if not 1<=args.max_hulls<=1024 or not 10000<=args.resolution<=16000000:raise ValueError('hull/resolution setting is outside supported budget')
        if not math.isfinite(args.timeout) or args.timeout<=0:raise ValueError('timeout must be positive')
        source=args.source.resolve();output=args.output.resolve();summary=(args.summary or output.with_suffix('.mesh.json')).resolve()
        different_paths([source],[output,summary]);different_paths([output],[summary])
        mesh=read_mesh(source);vertices=mesh['vertices'];triangles=sum(len(r['indices'])//3 for r in mesh['runs'])
        with Publication([source]) as publication:
            publication.reserve(output);publication.reserve(summary)
            request=publication.work/'request.bin';response=publication.work/'response.bin'
            with request.open('wb') as stream:
                if args.operation=='simplify':
                    stream.write(struct.pack('<III',0x4D535750,1,len(vertices)))
                    for p in vertices:stream.write(struct.pack('<3f',*p))
                    stream.write(struct.pack('<I',len(mesh['runs'])))
                    for run in mesh['runs']:
                        count=len(run['indices']);target=max(3,int(count/3*args.ratio)*3) if count else 0
                        stream.write(struct.pack('<III',count,target,0 if args.unlock_borders else 1))
                        for i in run['indices']:stream.write(struct.pack('<I',i))
                else:
                    stream.write(struct.pack('<IIII',0x44435750,2,1,len(vertices)))
                    for p in vertices:stream.write(struct.pack('<3f',*p))
                    stream.write(struct.pack('<I',triangles))
                    for run in mesh['runs']:
                        for i in run['indices']:stream.write(struct.pack('<i',i))
                    stream.write(struct.pack('<fIfI',args.concavity,args.max_hulls,1.,args.resolution))
            if request.stat().st_size>MAX_BYTES:raise ValueError('mesh request exceeds 512 MiB')
            result=subprocess.run([str(args.meshtool.resolve()),args.operation,str(request),str(response)],capture_output=True,text=True,errors='replace',timeout=args.timeout)
            if result.returncode:raise ValueError('meshtool failed: '+(result.stderr or result.stdout).strip())
            if response.stat().st_size>MAX_BYTES:raise ValueError('meshtool response exceeds 512 MiB')
            reader=Reader(response.read_bytes());magic,count=reader.unpack('II');errors=[]
            if args.operation=='simplify':
                if magic!=0x4D535750 or count!=len(mesh['runs']):raise ValueError('unexpected simplify response')
                for run in mesh['runs']:
                    kept=reader.count(len(run['indices']));error=reader.unpack('f')[0]
                    if kept%3 or not math.isfinite(error) or error<0:raise ValueError('invalid simplify result')
                    indices=list(reader.unpack('I'*kept))
                    if any(i>=len(vertices) for i in indices):raise ValueError('simplify returned an invalid vertex')
                    run['indices']=indices;errors.append(error)
            else:
                if magic!=0x44435750 or count!=1:raise ValueError('unexpected decomposition response')
                hulls=reader.count(1024);mesh=dict(vertices=[],attributes=[],runs=[],warnings=[])
                if not hulls:raise ValueError('decomposition returned no convex hulls')
                for hull in range(hulls):
                    count=reader.count(65536);points=[finite(reader.unpack('3f')) for _ in range(count)]
                    faces=convex_faces(points);base=len(mesh['vertices'])
                    mesh['vertices'].extend(points);mesh['attributes'].extend([(None,None)]*len(points))
                    mesh['runs'].append(dict(name='hull_'+str(hull),material='',indices=[base+i for i in faces]))
            reader.finish()
            report=dict(schema=1,operation=args.operation,source=str(source),input_vertices=len(vertices),input_triangles=triangles,
                        output_vertices=len({i for r in mesh['runs'] for i in r['indices']}),output_triangles=sum(len(r['indices'])//3 for r in mesh['runs']),
                        groups=len(mesh['runs']),meshoptimizer_normalized_errors=errors,warnings=mesh['warnings'])
            geometry=publication.work/'result.obj';geometry.write_text(obj_text(mesh),encoding='utf-8')
            metadata=publication.work/'summary.json';metadata.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
            publication.add(geometry,output);publication.add(metadata,summary);publication.commit()
        print(f"{args.operation}: {triangles} -> {report['output_triangles']} triangles; {report['groups']} groups")
        for warning in report['warnings']:print('warning: '+warning)
        return 0
    except (OSError,ValueError,KeyError,IndexError,TypeError,struct.error,subprocess.TimeoutExpired) as error:
        print('mesh_workflow: '+str(error),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
