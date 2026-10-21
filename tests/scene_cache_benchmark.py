"""Measure multi-rate scene reuse with a self-authored external-buffer glTF."""
import argparse, hashlib, json, platform, statistics, struct, subprocess, time
from pathlib import Path


def fixture(folder, side=180):
    folder.mkdir(parents=True, exist_ok=True)
    binary=bytearray(); views=[]; accessors=[]
    def accessor(values,width,component=5126):
        offset=len(binary)
        binary.extend(struct.pack('<'+('f' if component==5126 else 'I')*len(values),*values))
        views.append(dict(buffer=0,byteOffset=offset,byteLength=len(binary)-offset))
        accessors.append(dict(bufferView=len(views)-1,componentType=component,count=len(values)//width,type={1:'SCALAR',2:'VEC2',3:'VEC3'}[width]))
        return len(accessors)-1
    points=[(x/side,y/side,0) for y in range(side+1) for x in range(side+1)]
    pos=accessor([v for p in points for v in p],3)
    accessors[pos].update(min=[0,0,0],max=[1,1,0])
    normal=accessor([0,0,1]*len(points),3)
    uv=accessor([v for x,y,z in points for v in (x,y)],2)
    indices=[]
    for y in range(side):
        for x in range(side):
            a=y*(side+1)+x;indices.extend([a,a+1,a+side+1,a+1,a+side+2,a+side+1])
    index=accessor(indices,1,5125)
    morphs=[{'POSITION':accessor([v for x,y,z in points for v in (0,0,.01*(i+1)*x*y)],3)} for i in range(4)]
    times=accessor([0,2],1);accessors[times].update(min=[0],max=[2])
    move=accessor([0,0,0,1,0,0],3)
    doc={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0]}],
         'nodes':[{'name':'Root','children':[1]},{'name':'Mesh','mesh':0}],
         'meshes':[{'name':'Grid','primitives':[{'attributes':{'POSITION':pos,'NORMAL':normal,'TEXCOORD_0':uv},'indices':index,'targets':morphs}]}],
         'animations':[{'name':'Move','samplers':[{'input':times,'output':move,'interpolation':'LINEAR'}], 'channels':[{'sampler':0,'target':{'node':1,'path':'translation'}}]}],
         'buffers':[{'byteLength':len(binary),'uri':'scene.bin'}],'bufferViews':views,'accessors':accessors}
    (folder/'scene.bin').write_bytes(binary)
    (folder/'scene.gltf').write_text(json.dumps(doc,separators=(',',':')),encoding='utf-8')
    return {'vertices':len(points),'triangles':len(indices)//3,'morphs':len(morphs),'rates':[15,24,30,60,120],
            'input_sha256':{p.name:sha(p) for p in (folder/'scene.bin',folder/'scene.gltf')}}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(compiler, folder, runs):
    identity=fixture(folder/'input');samples=[];outputs={}
    for repetition in range(runs+1):
        # Reverse order on alternate repetitions to avoid a fixed warm-cache bias.
        for backend,budget in ([('native',0),('native',256),('assimp',0),('assimp',256)][::1 if repetition%2==0 else -1]):
            name=f'{backend}-{budget}-{repetition}';work=folder/name;work.mkdir()
            qc=folder/'input'/'scene.qc'
            text='$modelname benchmark/multirate\n$animationcullmethod none\n'
            text+=f'$SceneCacheMiB {budget}\n'+('$NoFastGltf\n' if backend=='assimp' else '')
            text+='$body body scene.gltf InNode Mesh\n'
            for fps in identity['rates']:
                text+=f'$animation a{fps} scene.gltf Pick Move SampleRate {fps}\n$sequence s{fps} a{fps}\n'
            qc.write_text(text,encoding='utf-8')
            args=[str(compiler),str(qc),'-game',str(work),'-OutDir',str(work),'-perfjson',str(work/'perf.json')]
            start=time.monotonic()
            proc=subprocess.run(args,capture_output=True,timeout=120)
            (work/'compile.log').write_bytes(proc.stdout+proc.stderr)
            if proc.returncode:raise RuntimeError((name,proc.returncode,(proc.stdout+proc.stderr)[-3000:]))
            perf=json.loads((work/'perf.json').read_text())
            hashes={p.relative_to(work/'models').as_posix():sha(p) for p in (work/'models').rglob('*') if p.is_file() and not any(s.startswith('.') for s in p.relative_to(work/'models').parts)}
            if backend in outputs and hashes!=outputs[backend]:raise AssertionError('different model bytes across cache configurations: '+name)
            outputs[backend]=hashes
            samples.append(dict(backend=backend,budget_mib=budget,repetition=repetition,warmup=repetition==0,command=args,wall_seconds=time.monotonic()-start,metrics=perf))
            print(name,perf['scene_cache'],flush=True)
    summaries=[]
    for backend in ('native','assimp'):
        for budget in (0,256):
            measured=[s['metrics'] for s in samples if not s['warmup'] and s['backend']==backend and s['budget_mib']==budget]
            summaries.append(dict(backend=backend,budget_mib=budget,median_total_ms=statistics.median(s['total_ms'] for s in measured),
                                 median_peak_working_set_bytes=statistics.median(s['peak_working_set_bytes'] for s in measured),
                                 median_import_ms=1000*statistics.median(s['scene_cache']['import_seconds'] for s in measured),
                                 cache=measured[0]['scene_cache']))
    return dict(schema=1,compiler=str(compiler),compiler_sha256=sha(compiler),machine=dict(system=platform.platform(),processor=platform.processor(),node=platform.node()),
                fixture=identity,runs=runs,warmup=1,summaries=summaries,samples=samples,output_sha256=outputs,
                limits='Self-authored grid; process peak working set differs from estimated retained aiScene bytes. Filesystem cache is not flushed. Concurrent system load can affect timings.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('compiler',type=Path);p.add_argument('output',type=Path);p.add_argument('--runs',type=int,default=5)
    a=p.parse_args()
    if a.runs<3:p.error('at least three measured runs required')
    a.output.mkdir(parents=True,exist_ok=False)
    report=run(a.compiler.resolve(),a.output,a.runs)
    (a.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report['summaries'],indent=2))
