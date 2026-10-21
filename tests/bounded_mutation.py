#!/usr/bin/env python3
"""Reproducible, budgeted format mutation with retained/minimized failures.

This is a bounded regression experiment, not coverage-guided fuzzing or proof
that arbitrary model files are safe. All corpus assets are authored locally.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import zlib

from subtools_integrity_test import target_mdl, vmd

SANITIZER = re.compile(r'(?:ERROR: (?:AddressSanitizer|LeakSanitizer)|(?:AddressSanitizer:DEADLYSIGNAL)|runtime error:|SUMMARY: .*Sanitizer|UndefinedBehaviorSanitizer)')
SMD_HEADER = 'version 1\nnodes\n0 "root" -1\n1 "child" 0\nend\nskeleton\n'
SMD_POSE = 'time 0\n0 0 0 0 0 0 0\n1 0 0 0 0 0 0\nend\n'


def digest(data): return hashlib.sha256(data).hexdigest()


def memory_bytes(pid):
    if sys.platform.startswith('linux'):
        try:
            text = Path('/proc')/str(pid)/'status'
            match = re.search(r'^VmRSS:\s+(\d+)\s+kB', text.read_text(), re.M)
            return int(match[1])*1024 if match else 0
        except (OSError, ValueError): return 0
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in
                        ('peak_working', 'working', 'peak_paged', 'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
        if not handle: return 0
        try:
            counters = Counters(); counters.cb = ctypes.sizeof(counters)
            query = ctypes.WinDLL('psapi').GetProcessMemoryInfo
            query.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
            return counters.working if query(handle, ctypes.byref(counters), counters.cb) else 0
        finally: kernel.CloseHandle(handle)
    return 0


def run(command, root, timeout, memory_mb=512, log_limit=4*1024*1024):
    log = root/'process.log'; started = time.monotonic(); peak = 0; violation = None
    with log.open('wb') as stream:
        process = subprocess.Popen(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=os.name != 'nt')
        try:
            while process.poll() is None:
                peak = max(peak, memory_bytes(process.pid))
                if time.monotonic()-started > timeout: violation = 'timeout'
                elif peak > memory_mb*1024*1024: violation = 'memory-budget'
                elif log.stat().st_size > log_limit: violation = 'log-budget'
                if violation:
                    if os.name != 'nt': os.killpg(process.pid, signal.SIGKILL)
                    else: process.kill()
                    break
                time.sleep(.02)
            code = process.wait(timeout=10)
        finally:
            if process.poll() is None: process.kill(); process.wait(timeout=10)
    if violation is None and log.stat().st_size > log_limit:
        violation = 'log-budget'  # Also catch a fast writer that exited between polls.
    with log.open('rb') as stream:
        text = stream.read(log_limit).decode('utf-8', 'replace')
    matched = next((line.strip() for line in text.splitlines() if SANITIZER.search(line)), None)
    status = violation or ('sanitizer' if matched else 'accepted' if code == 0 else 'rejected' if code in (1,2) else 'crash')
    signature = re.sub(r'0x[0-9a-fA-F]+', '<address>', matched or '')
    signature = re.sub(r'==\d+==', '==PID==', signature)
    return dict(status=status, exit_code=code, seconds=time.monotonic()-started, peak_rss_bytes=peak,
                signature=[status, code if status == 'crash' else None, signature], log=text)


def require_ok(result, label):
    if result['status'] != 'accepted': raise RuntimeError(label+': '+result['status']+'\n'+result['log'])


def generate_corpus(root, compiler, decompiler, vmdtool, timeout):
    source = root/'source'; source.mkdir()
    (source/'gameinfo.txt').write_text('GameInfo { FileSystem { SteamAppId 4000 SearchPaths { Game "|gameinfo_path|." } } }')
    mesh = SMD_HEADER+SMD_POSE+'triangles\n'
    points = ((0,0,0),(1,0,0),(0,1,0),(0,0,1))
    for face in ((0,1,2),(0,3,1),(0,2,3),(1,3,2)):
        mesh += 'material\n'+''.join('0 '+' '.join(map(str, points[i]))+' 0 0 1 0 0 2 0 0.5 1 0.5\n' for i in face)
    mesh += 'end\n'
    (source/'mesh.smd').write_text(mesh)
    (source/'anim.smd').write_text(SMD_HEADER+''.join(f'time {i}\n0 {i} 0 0 0 0 0\n1 0 {i} 0 0 0 0\n' for i in range(4))+'end\n')
    (source/'model.qc').write_text('$modelname fixture\n$bonealwayssetup child\n$body body mesh.smd\n$sequence idle anim.smd\n$attachment mount root 0 0 0\n$hbox 0 child -1 -1 -1 1 1 1\n')
    require_ok(run([str(compiler), str(source/'model.qc'), '-game', str(source), '-OutDir', str(root/'compiled')], root, timeout, 2048), 'seed compile')
    model = root/'compiled/models/fixture.mdl'
    require_ok(run([str(decompiler), str(model), '-outdir', str(root/'decompiled'), '-dmxencoding', 'keyvalues2'], root, timeout, 2048), 'seed decompile')
    common = {str(p.relative_to(root/'compiled/models')):p.read_bytes() for p in (root/'compiled/models').iterdir() if p.is_file()}
    common['gameinfo.txt'] = (source/'gameinfo.txt').read_bytes()
    cases = []
    def add(name, files, target, command):
        folder = root/name; folder.mkdir()
        for relative, data in files.items():
            dest = folder/relative; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
        cases.append(dict(name=name, folder=folder, target=target, command=command))
    for name, target in (('mdl','fixture.mdl'),('vvd','fixture.vvd'),('vtx','fixture.dx90.vtx'),('mdl-animation','fixture.mdl')):
        add(name, common, target, [str(decompiler), '{root}/fixture.mdl', '-outdir', '{root}/output'])
    dmx_files = {str(p.relative_to(root/'decompiled')):p.read_bytes() for p in (root/'decompiled').rglob('*') if p.is_file() and p.suffix in ('.dmx','.qc','.smd','.qci','.vrd','.bones')}
    dmx_files['gameinfo.txt'] = common['gameinfo.txt']
    mesh_dmx = next(path for path in dmx_files if path.endswith('.dmx') and b'DmeMesh' in dmx_files[path])
    qc = next(path for path in dmx_files if path.endswith('.qc'))
    add('dmx', dmx_files, mesh_dmx, [str(compiler), '{root}/'+qc, '-game', '{root}', '-OutDir', '{root}/output'])
    smd_files = {p.name:p.read_bytes() for p in source.iterdir() if p.is_file()}
    add('smd-animation', smd_files, 'anim.smd', [str(compiler), '{root}/model.qc', '-game', '{root}', '-OutDir', '{root}/output'])
    payload = mesh.encode(); preload = payload[:32]; remainder = payload[32:]
    tree = b'smd\0 \0archived\0'+struct.pack('<IHHIIH', zlib.crc32(payload), len(preload), 0x7fff, 0, len(remainder), 0xffff)+preload+b'\0\0\0'
    archive = struct.pack('<III4I', 0x55aa1234, 2, len(tree), len(remainder), 0, 0, 0)+tree+remainder
    add('vpk', {'sources_dir.vpk':archive, 'gameinfo.txt':b'GameInfo { FileSystem { SteamAppId 730 SearchPaths { CONTENT "|gameinfo_path|sources.vpk" } } }',
                'model.qc':b'$modelname packed\n$contentrootrelative\n$body body archived.smd\n'}, 'sources_dir.vpk',
        [str(compiler), '{root}/model.qc', '-game', '{root}', '-OutDir', '{root}/output'])
    if vmdtool:
        target_mdl(root/'target.mdl'); vmd(root/'motion.vmd', last_frame=4)
        add('vmd-animation', {'target.mdl':(root/'target.mdl').read_bytes(), 'motion.vmd':(root/'motion.vmd').read_bytes()}, 'motion.vmd',
            [str(vmdtool), '-mdl', '{root}/target.mdl', '-vmd', '{root}/motion.vmd', '-camerafov', 'dmx'])
    return cases


def mutate(original, rng, index, name):
    data = bytearray(original); operation = index % 6
    if not data: return b'\xff', 'nonempty'
    if operation == 0:
        size = rng.randrange(len(data)); return bytes(data[:size]), 'truncate:'+str(size)
    if operation == 1:
        at = rng.randrange(len(data)); data[at] ^= 1 << rng.randrange(8); return bytes(data), 'bitflip:'+str(at)
    if operation == 2 and len(data) >= 4:
        at = rng.randrange(len(data)-3)
        if name == 'mdl-animation' and len(data) > 188:
            count, table = struct.unpack_from('<2i', data, 180)
            if count > 0 and 0 <= table <= len(data)-100: at = table+rng.choice((4,8,12,16,52,56,60,64,68,72,80,84,88))
        number = rng.choice((0,1,0xffffffff,0x7fffffff,0x80000000,0x7fc00000,0x7f800000))
        struct.pack_into('<I', data, at, number); return bytes(data), f'word:{at}:{number}'
    if operation == 3:
        at = rng.randrange(len(data)); size = rng.randint(1,min(64,len(data)-at)); del data[at:at+size]
        return bytes(data), f'delete:{at}:{size}'
    if operation == 4 and name in ('dmx','smd-animation'):
        matches = list(re.finditer(rb'(?<![\w.])-?\d+(?:\.\d+)?', data))
        if matches:
            match = rng.choice(matches); replacement = rng.choice((b'nan', b'inf', b'-2147483648', b'2147483647', b'1e39', b'OOPS'))
            return bytes(data[:match.start()]+replacement+data[match.end():]), 'numeric-token'
    at = rng.randrange(len(data)+1); payload = bytes(rng.randrange(256) for _ in range(rng.randint(1,32)))
    data[at:at] = payload; return bytes(data), 'insert:'+str(at)


def execute_case(case, payload, runs, timeout, memory_mb):
    with tempfile.TemporaryDirectory(prefix=case['name']+'-', dir=runs) as temporary:
        root = Path(temporary).resolve()
        for source in case['folder'].rglob('*'):
            if source.is_file():
                dest = root/source.relative_to(case['folder']); dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, dest)
        (root/case['target']).write_bytes(payload)
        command = [value.replace('{root}', str(root)) for value in case['command']]
        return run(command, root, timeout, memory_mb)


def minimize(case, original, expected, runs, timeout, memory_mb, deadline, attempts):
    best = original; tested = 0; granularity = 2
    while len(best) > 1 and tested < attempts and time.monotonic() < deadline:
        width = max(1, len(best)//granularity); changed = False
        for start in range(0, len(best), width):
            if tested >= attempts or time.monotonic() >= deadline: break
            candidate = best[:start]+best[start+width:]
            result = execute_case(case, candidate, runs, min(timeout,max(.1,deadline-time.monotonic())), memory_mb); tested += 1
            if result['signature'] == expected:
                best = candidate; changed = True; break
        if not changed:
            if granularity >= len(best): break
            granularity = min(len(best), granularity*2)
    return best, tested


def preserve(output, case, original, reduced, result, operation, index, attempts):
    finding = output/'findings'/f'{index:05d}-{case["name"]}'; finding.mkdir(parents=True)
    shutil.copytree(case['folder'], finding/'repro')
    (finding/'repro'/case['target']).write_bytes(reduced)
    (finding/'original-input.bin').write_bytes(original)
    (finding/'process.log').write_text(result['log'], encoding='utf-8')
    record = {k:v for k,v in result.items() if k != 'log'}
    record.update(family=case['name'], mutation=operation, sample=index, target=case['target'],
                  original_sha256=digest(original), minimized_sha256=digest(reduced), original_size=len(original),
                  minimized_size=len(reduced), reduction_attempts=attempts, command=case['command'])
    (finding/'finding.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    (finding/'reproduce.py').write_text('import json, subprocess\nfrom pathlib import Path\np=Path(__file__).resolve().parent\nr=json.loads((p/"finding.json").read_text())\nraise SystemExit(subprocess.run([a.replace("{root}",str(p/"repro")) for a in r["command"]],cwd=p/"repro").returncode)\n')
    return str(finding.relative_to(output))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path); parser.add_argument('--decompiler', required=True, type=Path)
    parser.add_argument('--vmd-tool', type=Path); parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--samples', type=int, default=240); parser.add_argument('--seconds', type=float, default=180)
    parser.add_argument('--case-timeout', type=float, default=5); parser.add_argument('--memory-mb', type=int, default=512)
    parser.add_argument('--seed', type=int, default=1238); parser.add_argument('--minimize-attempts', type=int, default=32)
    parser.add_argument('--max-findings', type=int, default=8)
    args = parser.parse_args(argv)
    if not (1 <= args.samples <= 100000 and 1 <= args.seconds <= 3600 and .1 <= args.case_timeout <= 120
            and 64 <= args.memory_mb <= 8192 and 0 <= args.minimize_attempts <= 256 and 1 <= args.max_findings <= 100):
        parser.error('sample/time/memory/reduction budget is outside supported bounds')
    if os.name == 'nt':
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(3)
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    corpus = output/'corpus'; corpus.mkdir(); runs = output/'runs'; runs.mkdir()
    report = dict(schema=1, started_at=datetime.now(timezone.utc).isoformat(), seed=args.seed, budgets=vars(args).copy(),
                  controls=[], samples=[], findings=[], scope='Authored bounded mutations; normal parse rejection is not a crash; no exhaustive safety claim.')
    report['budgets'] = {k:str(v) if isinstance(v, Path) else v for k,v in report['budgets'].items()}
    try:
        compiler=args.compiler.resolve(); decompiler=args.decompiler.resolve(); vmdtool=args.vmd_tool.resolve() if args.vmd_tool else None
        report['executables'] = {str(p):digest(p.read_bytes()) for p in (compiler,decompiler,vmdtool) if p}
        cases = generate_corpus(corpus, compiler, decompiler, vmdtool, max(args.case_timeout, 30))
        for case in cases:
            payload = (case['folder']/case['target']).read_bytes()
            result = execute_case(case, payload, runs, max(args.case_timeout, 30), args.memory_mb)
            report['controls'].append(dict(family=case['name'], **{k:v for k,v in result.items() if k != 'log'}))
            require_ok(result, 'valid '+case['name']+' control')
        rng=random.Random(args.seed); started=time.monotonic(); deadline=started+args.seconds; signatures=set()
        for index in range(args.samples):
            if time.monotonic() >= deadline or len(report['findings']) >= args.max_findings: break
            case=cases[index%len(cases)]; original=(case['folder']/case['target']).read_bytes()
            payload, operation=mutate(original,rng,index//len(cases),case['name'])
            result=execute_case(case,payload,runs,min(args.case_timeout,max(.1,deadline-time.monotonic())),args.memory_mb)
            report['samples'].append(dict(index=index,family=case['name'],mutation=operation,sha256=digest(payload),
                                          **{k:v for k,v in result.items() if k != 'log'}))
            if result['status'] not in ('accepted','rejected'):
                signature=(case['name'],json.dumps(result['signature']))
                if signature not in signatures:
                    signatures.add(signature)
                    reduced, attempts=minimize(case,payload,result['signature'],runs,args.case_timeout,args.memory_mb,deadline,args.minimize_attempts)
                    report['findings'].append(preserve(output,case,payload,reduced,result,operation,index,attempts))
            if (index+1)%32 == 0: print(f'{index+1} samples, {len(report["findings"])} distinct findings',flush=True)
        report['mutation_seconds']=time.monotonic()-started
        report['counts']={status:sum(item['status']==status for item in report['samples']) for status in ('accepted','rejected','sanitizer','crash','timeout','memory-budget','log-budget')}
        report['success']=not report['findings']
        print(json.dumps(dict(samples=len(report['samples']),counts=report['counts'],findings=report['findings']),indent=2))
        return 0 if report['success'] else 1
    except (OSError, ValueError, RuntimeError, StopIteration, subprocess.SubprocessError) as error:
        report['success']=False;report['setup_error']=str(error);print(str(error),file=sys.stderr);return 2
    finally:
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__': raise SystemExit(main())
