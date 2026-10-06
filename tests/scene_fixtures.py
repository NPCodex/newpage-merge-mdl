"""Small self-authored scene fixtures; no user or third-party models."""
import base64
import json
import struct


def scene_bytes(kind='gltf', interpolation='LINEAR', normals=True, uv=False):
    binary=bytearray(); views=[]; accessors=[]
    def accessor(values,width,minimum=None,maximum=None):
        offset=len(binary); binary.extend(struct.pack('<'+'f'*len(values),*values))
        views.append({'buffer':0,'byteOffset':offset,'byteLength':len(values)*4})
        result={'bufferView':len(views)-1,'componentType':5126,'count':len(values)//width,
                'type':{1:'SCALAR',2:'VEC2',3:'VEC3'}[width]}
        if minimum is not None: result['min']=minimum
        if maximum is not None: result['max']=maximum
        accessors.append(result); return len(accessors)-1
    pos=accessor([-1,0,0,1,0,0,0,1,0],3,[-1,0,0],[1,1,0])
    norm=accessor([0,0,1]*3,3)
    delta=accessor([0,0,.25]*3,3)
    ndelta=accessor([.2,0,-.1]*3,3)
    times=accessor([0,1],1,[0],[1])
    values=[2,0,0,6,0,0]
    if interpolation=='CUBICSPLINE': values=[0,0,0,2,0,0,8,0,0,0,0,0,6,0,0,0,0,0]
    output=accessor(values,3)
    attrs={'POSITION':pos}
    if normals: attrs['NORMAL']=norm
    if uv: attrs['TEXCOORD_0']=accessor([.1,.2,.7,.3,.4,.9],2)
    shape={'POSITION':delta}
    if normals: shape['NORMAL']=ndelta
    doc={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0]}],
         'nodes':[{'name':'Group','children':[1,2]},
                  {'name':'MeshA','mesh':0,'translation':[2,0,0]},
                  {'name':'MeshB','mesh':0,'translation':[10,0,0]}],
         'materials':[{'name':'Original'}],
         'meshes':[{'name':'Triangle','extras':{'targetNames':['Smile']},
                    'primitives':[{'attributes':attrs,'material':0,'targets':[shape]}]}],
         'animations':[{'name':'Move','samplers':[{'input':times,'output':output,'interpolation':interpolation}],
                        'channels':[{'sampler':0,'target':{'node':1,'path':'translation'}}]}],
         'buffers':[{'byteLength':len(binary)}], 'bufferViews':views,'accessors':accessors}
    if kind=='gltf':
        doc['buffers'][0]['uri']='data:application/octet-stream;base64,'+base64.b64encode(binary).decode()
        return json.dumps(doc).encode()
    text=json.dumps(doc).encode(); text+=b' '*((-len(text))%4); binary+=b'\0'*((-len(binary))%4)
    payload=struct.pack('<II',len(text),0x4E4F534A)+text+struct.pack('<II',len(binary),0x004E4942)+binary
    return struct.pack('<III',0x46546C67,2,12+len(payload))+payload


def skinned_scene_bytes():
    doc=json.loads(scene_bytes())
    binary=bytearray(base64.b64decode(doc['buffers'][0]['uri'].split(',')[1]))
    def add(payload,component,count,kind):
        binary.extend(b'\0'*((-len(binary))%4)); offset=len(binary); binary.extend(payload)
        doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(payload)})
        doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,'componentType':component,'count':count,'type':kind})
        return len(doc['accessors'])-1
    joints=add(bytes([0]*12),5121,3,'VEC4')
    weights=add(struct.pack('<12f',*([1,0,0,0]*3)),5126,3,'VEC4')
    inverse=add(struct.pack('<16f',1,0,0,0,0,1,0,0,0,0,1,0,-5,0,0,1),5126,1,'MAT4')
    doc['nodes'].append({'name':'Joint','translation':[5,0,0]})
    doc['nodes'][0]['children'].append(3)
    doc['nodes'][1]['skin']=0; doc['nodes'][1]['translation']=[100,0,0]
    doc['skins']=[{'joints':[3],'inverseBindMatrices':inverse}]
    attrs=doc['meshes'][0]['primitives'][0]['attributes']; attrs['JOINTS_0']=joints; attrs['WEIGHTS_0']=weights
    doc['buffers'][0]={'byteLength':len(binary),'uri':'data:application/octet-stream;base64,'+base64.b64encode(binary).decode()}
    return json.dumps(doc).encode()
