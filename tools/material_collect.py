#!/usr/bin/env python3
"""Collect local Source VMT/VTF dependencies in explicit root-priority order."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import sys

from output_transaction import Publication, different_paths


TEXTURE_KEYS = {
    '$basetexture', '$bumpmap', '$normalmap', '$detail', '$envmap', '$envmapmask',
    '$phongexponenttexture', '$selfillummask', '$blendmodulatetexture', '$dudvmap',
    '$lightwarptexture', '$refracttinttexture', '$flowmap', '$noisetexture',
    '$gradienttexture', '$phongwarptexture', '$flashlighttexture', '$wrinkle',
    '$stretch', '$compress', '$flow_noise_texture', '$flow_bounds_texture',
    '$iris', '$ambientoccltexture', '$corneatexture',
}


def resource_name(value, extension):
    value=value.replace('\\','/').strip()
    if value.lower().startswith('materials/'):value=value[10:]
    path=PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or ':' in value or '\0' in value:
        raise ValueError('material dependency must stay under materials/: '+value)
    if path.suffix.lower()!=extension:path=PurePosixPath(str(path)+extension)
    return path.as_posix()


def tokens(text):
    result=[];at=0
    while at<len(text):
        if text[at].isspace():at+=1;continue
        if text.startswith('//',at):
            end=text.find('\n',at);at=len(text) if end<0 else end;continue
        if text.startswith('/*',at):
            end=text.find('*/',at+2)
            if end<0:raise ValueError('unterminated VMT block comment')
            at=end+2;continue
        if text[at] in '{}':result.append(text[at]);at+=1;continue
        if text[at]=='"':
            at+=1;value=[]
            while at<len(text) and text[at]!='"':
                if text[at]=='\\' and at+1<len(text) and text[at+1] in ('"','\\'):
                    at+=1
                value.append(text[at]);at+=1
            if at==len(text):raise ValueError('unterminated VMT string')
            at+=1;result.append(''.join(value));continue
        begin=at
        while at<len(text) and not text[at].isspace() and text[at] not in '{}':at+=1
        result.append(text[begin:at])
    return result


def parse_vmt(text):
    source=tokens(text);at=0
    def block(nested=False):
        nonlocal at
        rows=[]
        while at<len(source):
            key=source[at];at+=1
            if key=='}':
                if not nested:raise ValueError('unexpected VMT closing brace')
                return rows
            if key=='{' or at>=len(source):raise ValueError('invalid VMT key/value')
            value=source[at];at+=1
            if value=='{':value=block(True)
            elif value=='}':raise ValueError('missing VMT value')
            rows.append((key,value))
            # Collect all conditional branches: the destination may be used
            # with a different DX/platform choice than the collection host.
            if at<len(source) and source[at].startswith('[') and source[at].endswith(']'):at+=1
        if nested:raise ValueError('missing VMT closing brace')
        return rows
    rows=block()
    if len(rows)!=1 or not isinstance(rows[0][1],list):raise ValueError('VMT needs one shader block')
    return rows[0]


def mdl_materials(path):
    data=path.read_bytes()
    if len(data)<220 or data[:4]!=b'IDST' or struct.unpack_from('<I',data,4)[0] not in (48,49):
        raise ValueError('material collection supports Source MDL versions 48 and 49')
    length=struct.unpack_from('<I',data,76)[0]
    if length!=len(data):raise ValueError('MDL header length does not match file')
    count,offset,dir_count,dir_offset=struct.unpack_from('<4I',data,204)
    if count>65536 or dir_count>65536 or offset+count*64>len(data) or dir_offset+dir_count*4>len(data):
        raise ValueError('invalid MDL material directory table')
    def string(at):
        if not 0<=at<len(data):raise ValueError('MDL material string is out of bounds')
        end=data.find(b'\0',at,min(len(data),at+65536))
        if end<0:raise ValueError('unterminated MDL material string')
        return data[at:end].decode('utf-8')
    directories=[string(struct.unpack_from('<I',data,dir_offset+i*4)[0]) for i in range(dir_count)] or ['']
    result=[]
    for i in range(count):
        base=offset+i*64;name=string(base+struct.unpack_from('<i',data,base)[0])
        result.append([resource_name(directory.rstrip('/')+'/'+name if directory else name,'.vmt') for directory in directories])
    return result


def index_roots(roots):
    result=[]
    for root in roots:
        root=root.resolve();folder=root/'materials' if (root/'materials').is_dir() else root
        if not folder.is_dir():raise ValueError('material root is not a directory: '+str(folder))
        files={}
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or path.suffix.lower() not in ('.vmt','.vtf'):continue
            relative=path.relative_to(folder).as_posix();identity=relative.casefold()
            if identity in files:raise ValueError('ambiguous case-insensitive material paths in one root: '+str(files[identity])+' and '+str(path))
            files[identity]=path.resolve()
        result.append((folder,files))
    return result


def collect(roots, requests, texture_keys=()):
    indexed=index_roots(roots);selected={};missing=[];errors=[];builtins=[];active=[];visited=set()
    keys=TEXTURE_KEYS|set(key.lower() for key in texture_keys)
    def resolve(name):
        matches=[(priority,folder,files[name.casefold()]) for priority,(folder,files) in enumerate(indexed) if name.casefold() in files]
        return matches
    def record(name,kind,parent):
        matches=resolve(name)
        if not matches:
            missing.append(dict(kind=kind,name=name,requested_by=parent));return None
        priority,folder,path=matches[0]
        identity=name.casefold()
        if identity not in selected:
            selected[identity]=dict(name=identity,kind=kind,source=str(path),root=str(folder),priority=priority,
                                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                    shadowed_sources=[str(p) for _,_,p in matches[1:]])
        return path
    def visit(name,parent):
        identity=name.casefold()
        if identity in active:
            errors.append('cyclic VMT include: '+' -> '.join(active+[identity]));return
        path=record(name,'vmt',parent)
        if path is None or identity in visited:return
        active.append(identity)
        try:
            shader,rows=parse_vmt(path.read_text(encoding='utf-8-sig'))
            def walk(values):
                for key,value in values:
                    if isinstance(value,list):walk(value);continue
                    lower=key.lower()
                    if lower=='include' and shader.lower()=='patch':
                        visit(resource_name(value,'.vmt'),name)
                    elif lower in keys or re.sub(r'\d+$','',lower) in keys:
                        if not value:continue
                        if value.lower()=='env_cubemap' or value.lower().startswith('_rt_'):
                            builtins.append(dict(name=value,requested_by=name,key=key));continue
                        record(resource_name(value,'.vtf'),'vtf',name)
            walk(rows)
        except (OSError,ValueError) as error:errors.append(str(path)+': '+str(error))
        finally:active.pop();visited.add(identity)
    for alternatives in requests:
        choice=next((name for name in alternatives if resolve(name)),alternatives[0])
        visit(choice,'requested model/material')
    return dict(schema=1,complete=not missing and not errors,root_priority=[str(folder) for folder,_ in indexed],
                files=list(selected.values()),missing=missing,errors=errors,runtime_resources=builtins,
                texture_keys=sorted(keys))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',action='append',required=True,type=Path,help='game/materials root, highest priority first')
    parser.add_argument('--material',action='append',default=[],help='material path relative to materials/')
    parser.add_argument('--mdl',action='append',default=[],type=Path)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--report',type=Path)
    parser.add_argument('--texture-key',action='append',default=[],help='additional texture-valued shader key')
    parser.add_argument('--allow-missing',action='store_true',help='publish found files even if some dependencies are missing')
    args=parser.parse_args(argv)
    try:
        if not args.material and not args.mdl:raise ValueError('specify --material or --mdl')
        requests=[[resource_name(name,'.vmt')] for name in args.material]
        for model in args.mdl:requests.extend(mdl_materials(model))
        report=collect(args.root,requests,args.texture_key)
        output=args.output.resolve();report_path=(args.report or output/'materials-manifest.json').resolve()
        material_output=output/'materials'
        for source_root in report['root_priority']:
            source_root=Path(source_root).resolve()
            if material_output.is_relative_to(source_root) or source_root.is_relative_to(material_output):
                raise ValueError('material output must be isolated from source material roots: '+str(material_output))
        inputs=[Path(item['source']) for item in report['files']]+[p.resolve() for p in args.mdl]
        publish=not report['errors'] and (not report['missing'] or args.allow_missing)
        report['published']=publish
        with Publication(inputs) as transaction:
            transaction.reserve(report_path)
            if publish:
                for item in report['files']:
                    source=Path(item['source']);destination=output/'materials'/item['name']
                    different_paths(inputs,[destination])
                    different_paths([report_path],[destination])
                    if hashlib.sha256(source.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('material changed while collecting: '+str(source))
                    staged=transaction.work/str(len(transaction.entries));staged.write_bytes(source.read_bytes())
                    if hashlib.sha256(staged.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('material changed while copying: '+str(source))
                    transaction.add(staged,destination)
            staged_report=transaction.work/'report.json';staged_report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            transaction.add(staged_report,report_path);transaction.commit()
        print(f"Materials: {len(report['files'])} files, {len(report['missing'])} missing; " + ('published' if publish else 'report only; existing materials preserved'))
        for error in report['errors']:print('error: '+error,file=sys.stderr)
        for item in report['missing']:print('missing: '+item['name']+' (from '+item['requested_by']+')',file=sys.stderr)
        return 0 if report['complete'] else 2
    except (OSError,ValueError,KeyError,IndexError,struct.error) as error:
        print('material_collect: '+str(error),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
