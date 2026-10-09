#!/usr/bin/env python3
"""Compile a finite sequence of mesh topologies as standard Source bodygroups."""
import argparse
import bisect
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile


def number(value, label, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int,float)):
        raise ValueError(label+' must be a finite number')
    try:
        value=float(value)
    except OverflowError:
        raise ValueError(label+' must be a finite number') from None
    if not math.isfinite(value):
        raise ValueError(label+' must be a finite number')
    if positive and value<=0:
        raise ValueError(label+' must be positive')
    return value


def identifier(value, label):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+',value):
        raise ValueError(label+' must contain only letters, digits, underscore, dot or hyphen')
    return value


def quoted(value):
    value=str(value).replace('\\','/')
    if any(c in value for c in ('"','\n','\r','\0')):
        raise ValueError('QC paths cannot contain quotes, newlines or NUL')
    return '"'+value+'"'


def prepare(spec, source_dir):
    if not isinstance(spec,dict):
        raise ValueError('manifest must be a JSON object')
    unknown=set(spec)-{'modelname','group','states','fps','times','sequence','duration','loop'}
    if unknown:
        raise ValueError('unknown manifest fields: '+', '.join(sorted(unknown)))
    name=spec.get('modelname')
    if not isinstance(name,str) or '\\' in name or not re.fullmatch(r'[A-Za-z0-9_./-]+',name):
        raise ValueError('modelname must be a relative model path using forward slashes')
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or name.endswith('/'):
        raise ValueError('modelname must stay within models/')
    if path.parts and path.parts[0]=='models':
        path=PurePosixPath(*path.parts[1:])
    if not path.name or path.name in ('.','..'):
        raise ValueError('modelname needs a filename')
    if path.suffix and path.suffix.lower()!='.mdl':
        raise ValueError('modelname must have .mdl extension or no extension')
    path=path.with_suffix('.mdl')
    group=identifier(spec.get('group','mesh_state'),'group')
    states=spec.get('states')
    if not isinstance(states,list) or not states or len(states)>2147483647:
        raise ValueError('states must be a nonempty array within the bodygroup count format')
    names=set();rows=[];metadata=[];has_source=False
    for i,state in enumerate(states):
        if not isinstance(state,dict) or set(state)-{'name','source','blank'}:
            raise ValueError(f'states[{i}] must contain name and source, or name and blank=true')
        state_name=identifier(state.get('name'),f'states[{i}].name')
        if state_name in names:
            raise ValueError('state names must be unique')
        names.add(state_name)
        if 'blank' in state and state['blank'] is not True:
            raise ValueError(f'states[{i}].blank must be true when present')
        blank=state.get('blank',False)
        if blank == ('source' in state):
            raise ValueError(f'states[{i}] needs exactly one of source or blank=true')
        if blank:
            rows.append('    blank')
        else:
            source=state['source']
            if not isinstance(source,str) or not source:
                raise ValueError(f'states[{i}].source must be a nonempty filename')
            source=(source_dir/source).resolve()
            if not source.is_file():
                raise ValueError(f'mesh source does not exist: {source}')
            rows.append('    studio '+quoted(source))
            has_source=True
        metadata.append(dict(name=state_name,bodygroup_value=i,blank=blank))
    if not has_source:
        raise ValueError('at least one state must have a mesh source')
    sequence=spec.get('sequence',list(range(len(states))))
    if not isinstance(sequence,list) or not sequence:
        raise ValueError('sequence must be a nonempty array of zero-based state indices')
    if any(isinstance(i,bool) or not isinstance(i,int) or not 0<=i<len(states) for i in sequence):
        raise ValueError('sequence contains an invalid state index')
    if ('fps' in spec)==('times' in spec):
        raise ValueError('provide exactly one of fps or times')
    if 'fps' in spec:
        fps=number(spec['fps'],'fps',True)
        times=[i/fps for i in range(len(sequence))]
        default_duration=len(sequence)/fps
    else:
        if not isinstance(spec['times'],list) or len(spec['times'])!=len(sequence):
            raise ValueError('times must match sequence length')
        times=[number(t,'time') for t in spec['times']]
        if times[0]!=0 or any(a>=b for a,b in zip(times,times[1:])):
            raise ValueError('times must start at zero and increase strictly')
        default_duration=times[-1]+(times[-1]-times[-2] if len(times)>1 else 1)
    duration=number(spec.get('duration',default_duration),'duration',True)
    if duration<=times[-1]:
        raise ValueError('duration must be after the last sample time')
    loop=spec.get('loop',True)
    if not isinstance(loop,bool):
        raise ValueError('loop must be a JSON boolean')
    qc='$modelname '+quoted(path.as_posix())+'\n$bodygroup '+quoted(group)+'\n{\n'+'\n'.join(rows)+'\n}\n'
    clip=dict(schema=1,type='newpage_mesh_states',model='models/'+path.as_posix(),group=group,
              states=metadata,sequence=sequence,times=times,duration=duration,loop=loop)
    return qc,clip


def sample(clip,seconds):
    """Same left-closed step sampling used by the GMod client helper."""
    seconds=max(0,number(seconds,'seconds'))
    if clip['loop']:
        seconds%=clip['duration']
    else:
        seconds=min(seconds,clip['duration'])
    return clip['sequence'][bisect.bisect_right(clip['times'],seconds)-1]


def write_atomic(path,content):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='\n',dir=path.parent,delete=False) as f:
            temporary=Path(f.name);f.write(content)
        os.replace(temporary,path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('--out',type=Path,help='QC and staging directory (default: manifest directory/meshstates-build)')
    parser.add_argument('--compiler',type=Path,help='optional NewPageMergeMDL executable')
    parser.add_argument('--game',type=Path,help='game directory; required with --compiler')
    args=parser.parse_args(argv)
    try:
        if bool(args.compiler)!=bool(args.game):
            raise ValueError('--compiler and --game must be supplied together')
        manifest=args.manifest.resolve()
        qc,clip=prepare(json.loads(manifest.read_text(encoding='utf-8-sig')),manifest.parent)
        out=(args.out or manifest.parent/'meshstates-build').resolve()
        qc_path=out/(manifest.stem+'.qc')
        write_atomic(qc_path,qc)
        target=(args.game.resolve() if args.game else out)/PurePosixPath(clip['model']).with_suffix('.meshstates.json')
        if args.compiler:
            result=subprocess.run([str(args.compiler.resolve()),str(qc_path),'-game',str(args.game.resolve())])
            if result.returncode:
                return result.returncode
            model=args.game.resolve()/PurePosixPath(clip['model'])
            if not model.is_file():
                raise ValueError('compiler succeeded without the expected model: '+str(model))
        write_atomic(target,json.dumps(clip,ensure_ascii=False,indent=2)+'\n')
        print('QC: '+str(qc_path));print('Playback metadata: '+str(target))
        return 0
    except (ValueError,OSError,json.JSONDecodeError) as error:
        print('mesh_states: '+str(error),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
