"""Isolated production-model performance report, with reproducible checksums."""
import argparse,hashlib,json,statistics,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('compiler');p.add_argument('--qc',action='append',required=True);p.add_argument('--runs',type=int,default=3);p.add_argument('--report',required=True)
a=p.parse_args()
if a.runs<1: p.error('--runs must be positive')
report={'schema':1,'compiler':str(Path(a.compiler).resolve()),'cases':[]}
for qc in a.qc:
 samples=[];checksums=None
 with tempfile.TemporaryDirectory(prefix='newpage-benchmark-') as folder:
  root=Path(folder)
  for i in range(a.runs):
   output=root/str(i);output.mkdir();metrics=output/'perf.json'
   # stdin prelude is applied after the user's script, forcing isolated output.
   text=Path(qc).read_text(encoding='utf-8-sig')+'\n$OutDir "'+output.as_posix()+'"\n'
   args=[report['compiler'],str(Path(qc).resolve()),'-stdin','-game',str(output),'-perfjson',str(metrics)]
   start=time.monotonic();result=subprocess.run(args,input=text,text=True,capture_output=True,errors='replace')
   if result.returncode:raise RuntimeError(f'{qc}: {result.stdout[-3000:]} {result.stderr[-1000:]}')
   values=json.loads(metrics.read_text());values['wall_seconds']=time.monotonic()-start;samples.append(values)
   hashes={str(f.relative_to(output/'models')):hashlib.sha256(f.read_bytes()).hexdigest() for f in (output/'models').rglob('*') if f.is_file()}
   if checksums is not None and checksums!=hashes:raise RuntimeError('non-deterministic outputs: '+qc)
   checksums=hashes
 report['cases'].append({'qc':str(Path(qc).resolve()),'samples':samples,'median_total_ms':statistics.median(v['total_ms'] for v in samples),'median_peak_bytes':statistics.median(v['peak_working_set_bytes'] for v in samples),'output_sha256':checksums})
Path(a.report).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
