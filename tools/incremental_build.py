#!/usr/bin/env python3
"""Conservative dependency-aware model batches with structured per-job results."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time

from output_transaction import Publication, different_paths, key


SCHEMA = 1
RESERVED = {'-game', '-outdir', '-dependencyjson', '-diagnosticsjson', '-perfjson',
            '-stdin', '-verify', '-batch', '-recursive', '-r'}


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''): digest.update(data)
    return digest.hexdigest()


def file_identity(path, fnv=False):
    path = Path(path).resolve()
    if not path.is_file(): raise ValueError('dependency/output is not a file: ' + str(path))
    before = path.stat(); digest = hashlib.sha256(); native = 0xcbf29ce484222325
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(data)
            if fnv:
                for value in data: native = ((native ^ value) * 0x100000001b3) & 0xffffffffffffffff
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('file changed while hashing: ' + str(path))
    result = dict(path=str(path), sha256=digest.hexdigest(), size=after.st_size)
    if fnv: result['fnv1a64'] = format(native, '016x')
    return result


def inside(path, parent):
    try: Path(path).relative_to(parent); return True
    except ValueError: return False


def directory_identity(roots, excluded):
    """Hash entry names/types/links, not every unrelated source's contents."""
    rows = []; symlinks = []
    def skip(path): return any(inside(path, item) for item in excluded)
    def walk(folder, root):
        for item in sorted(folder.iterdir(), key=lambda p: p.name):
            if skip(item): continue
            info = item.lstat(); relative = item.relative_to(root).as_posix()
            if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
                target = str(item.resolve()); rows.append([str(root), relative, 'link', target])
                symlinks.append(str(item)); continue
            if stat.S_ISDIR(info.st_mode):
                rows.append([str(root), relative, 'directory']); walk(item, root)
            elif stat.S_ISREG(info.st_mode): rows.append([str(root), relative, 'file'])
            else: rows.append([str(root), relative, 'special'])
    for root in roots:
        if not root.is_dir(): raise ValueError('watch root is not a directory: ' + str(root))
        rows.append([str(root), '', 'root']); walk(root, root)
    return dict(sha256=digest_json(rows), symlinks=symlinks)


def toolchain_identity(compiler, extra):
    paths = {compiler, Path(__file__).resolve(), Path(__file__).with_name('output_transaction.py').resolve()}
    # Portable package executables and libraries; explicit additions support
    # custom compiler/helper layouts outside the package directory.
    for folder in (compiler.parent, compiler.parent/'subtools', compiler.parent/'tools'):
        if not folder.is_dir(): continue
        for path in folder.iterdir():
            if path.is_file() and (path.suffix.lower() in ('.exe', '.dll', '.so', '.dylib', '.py')
                                   or '.so.' in path.name or (os.name != 'nt' and os.access(path, os.X_OK))):
                paths.add(path.resolve())
    for name in ('meshtool', 'meshtool.exe'):
        path = shutil.which(name)
        if path: paths.add(Path(path).resolve())
    paths.update(extra)
    return [file_identity(p) for p in sorted(paths)]


def load_plan(path, compiler, cache, report):
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or data.get('schema') != SCHEMA or not isinstance(data.get('jobs'), list) or not data['jobs']:
        raise ValueError('plan requires schema: 1 and a nonempty jobs array')
    base = path.parent; jobs = []; names = set()
    def resolve(value):
        if not isinstance(value, str) or not value or '\0' in value: raise ValueError('expected a nonempty path string')
        value = Path(value); return (base/value).resolve() if not value.is_absolute() else value.resolve()
    for raw in data['jobs']:
        if not isinstance(raw, dict): raise ValueError('each job must be an object')
        name = raw.get('id')
        if not isinstance(name, str) or not name or name in names: raise ValueError('job IDs must be nonempty and unique')
        names.add(name)
        args = raw.get('args', [])
        if not isinstance(args, list) or not all(isinstance(a, str) and '\0' not in a for a in args): raise ValueError('args must be an array of strings')
        if any(a.lower().split('=', 1)[0] in RESERVED for a in args):
            raise ValueError('job args contain wrapper-owned output/report/batch options: ' + name)
        roots = raw.get('watch_roots', [])
        extras = raw.get('toolchain_files', [])
        if not isinstance(roots, list) or not isinstance(extras, list): raise ValueError('watch_roots/toolchain_files must be arrays')
        if type(raw.get('complete_search_roots', False)) is not bool: raise ValueError('complete_search_roots must be boolean')
        job = dict(id=name, qc=resolve(raw['qc']), game=resolve(raw['game']), output=resolve(raw['output']),
                   cwd=resolve(raw.get('cwd', '.')), args=args, watch_roots=sorted(set(resolve(p) for p in roots)),
                   toolchain_files=[resolve(p) for p in extras], complete_search_roots=raw.get('complete_search_roots', False))
        if not job['qc'].is_file() or not job['game'].is_dir() or not job['cwd'].is_dir():
            raise ValueError('QC, game directory and cwd must exist for ' + name)
        jobs.append(job)
    for i, job in enumerate(jobs):
        if any(inside(other['output'], job['output']) or inside(job['output'], other['output']) for other in jobs[:i]):
            raise ValueError('each job requires a distinct, non-overlapping output directory')
        if any(inside(source, job['output']) for source in [path, compiler, *(j['qc'] for j in jobs)]):
            raise ValueError('output directory contains an input or compiler: ' + str(job['output']))
        if inside(cache, job['output']) or inside(job['output'], cache) or inside(report, job['output']):
            raise ValueError('cache/report must be separate from model output directories')
    different_paths([path, compiler, *(j['qc'] for j in jobs)], [report])
    if inside(path, cache) or any(inside(j['qc'], cache) for j in jobs): raise ValueError('cache directory contains source inputs')
    if not inside(report, cache): raise ValueError('batch report must be inside the dedicated cache directory')
    if report.is_file():
        try: old_report = json.loads(report.read_text(encoding='utf-8'))
        except ValueError: raise ValueError('existing report is not a batch report; refusing to replace it') from None
        if not isinstance(old_report, dict) or old_report.get('schema') != SCHEMA or not isinstance(old_report.get('jobs'), list) or not isinstance(old_report.get('counts'), dict):
            raise ValueError('existing report is not a batch report; refusing to replace it')
    return jobs


def cache_match(previous, identity, tree):
    if previous.get('schema') != SCHEMA or not previous.get('cacheable'): return 'no reusable successful cache'
    if previous.get('identity') != identity: return 'compiler, settings, environment or plan changed'
    if previous.get('directory_identity') != tree: return 'search-directory entries changed'
    for kind in ('dependencies', 'outputs'):
        if not previous.get(kind): return 'cache has no ' + kind
        for record in previous[kind]:
            try:
                current = file_identity(record['path'])
                if current['sha256'] != record['sha256'] or current['size'] != record['size']: return kind + ' changed: ' + record['path']
            except (OSError, ValueError, KeyError): return kind + ' missing or invalid'
    return None


def native_diagnostics(stdout):
    records = []
    for line in stdout.splitlines():
        if line.startswith('@diagnostic '):
            try:
                item = json.loads(line[len('@diagnostic '):])
                if item.get('schema') == 1: records.append(item)
            except (ValueError, AttributeError): pass
    return records


def build_job(job, compiler, excluded, previous, work, timeout, force):
    started = time.monotonic()
    tree = directory_identity(job['watch_roots'], excluded)
    tools = toolchain_identity(compiler, job['toolchain_files'])
    identity = digest_json(dict(job={k: [str(x) for x in v] if isinstance(v, list) else str(v) if isinstance(v, Path) else v for k,v in job.items()},
                                tools=tools, environment=digest_json(dict(os.environ)), wrapper_schema=SCHEMA))
    reason = 'forced rebuild' if force else cache_match(previous, identity, tree)
    if reason is None:
        return dict(id=job['id'], status='skipped', success=True, cacheable=True, duration_seconds=time.monotonic()-started,
                    reason='dependencies, outputs and search paths unchanged', diagnostics=previous.get('diagnostics', []), stderr_tail=''), previous
    dependency_report = work/'dependencies.json'
    command = [str(compiler), str(job['qc']), '-game', str(job['game']), '-OutDir', str(job['output']),
               *job['args'], '-dependencyjson', str(dependency_report), '-diagnosticsjson']
    result = subprocess.run(command, cwd=job['cwd'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    diagnostics = native_diagnostics(result.stdout)
    row = dict(id=job['id'], status='built' if result.returncode == 0 else 'failed', success=result.returncode == 0,
               exit_code=result.returncode, reason=reason, diagnostics=diagnostics, stderr_tail=result.stderr[-16384:],
               stdout_tail='\n'.join(line for line in result.stdout.splitlines() if not line.startswith('@diagnostic '))[-16384:])
    state = dict(schema=SCHEMA, cacheable=False, identity=identity, dependencies=[], outputs=[], diagnostics=diagnostics)
    restrictions = []
    if result.returncode == 0:
        if not dependency_report.is_file(): raise ValueError('compiler succeeded without a dependency report')
        native = json.loads(dependency_report.read_text(encoding='utf-8'))
        if native.get('schema') != 1 or native.get('success') is not True: raise ValueError('invalid compiler dependency report')
        if not job['complete_search_roots']: restrictions.append('complete_search_roots is not explicitly true; search coverage is unproven')
        if not native.get('cacheable'): restrictions.append('native compiler marked this input uncacheable')
        if not job['watch_roots']: restrictions.append('no watch_roots declared')
        if tree['symlinks']: restrictions.append('watched roots contain symbolic links/junctions; search coverage is unproven')
        for dependency in native.get('dependencies', []):
            path = Path(dependency['path']).resolve()
            if not any(inside(path, root) for root in job['watch_roots']) or any(inside(path, root) for root in excluded):
                restrictions.append('dependency outside watched input roots: ' + str(path))
            try:
                record = file_identity(path, fnv=True)
                if record.pop('fnv1a64') != dependency['fnv1a64'].lower(): restrictions.append('dependency changed during compilation: ' + str(path))
                state['dependencies'].append(record)
            except (OSError, ValueError) as error: restrictions.append(str(error))
        for output in native.get('outputs', []):
            path = Path(output['path']).resolve()
            if not inside(path, job['output']): raise ValueError('compiler output escaped declared output directory: ' + str(path))
            state['outputs'].append(file_identity(path))
        if not state['dependencies'] or not state['outputs']: restrictions.append('compiler reported no actual dependencies or outputs')
        if directory_identity(job['watch_roots'], excluded) != tree: restrictions.append('search-directory entries changed during compilation')
        if toolchain_identity(compiler, job['toolchain_files']) != tools: restrictions.append('compiler/helper identity changed during compilation')
        state.update(cacheable=not restrictions, directory_identity=tree)
    row.update(cacheable=state['cacheable'], uncacheable_reasons=restrictions, duration_seconds=time.monotonic()-started)
    return row, state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--cache-dir', type=Path); parser.add_argument('--report', type=Path)
    parser.add_argument('--timeout', type=float, default=1800); parser.add_argument('--force', action='store_true')
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0: raise ValueError('timeout must be positive')
        plan = args.plan.resolve(); compiler = args.compiler.resolve()
        cache = (args.cache_dir or plan.parent/'.newpage-batch').resolve()
        report = (args.report or cache/'batch-report.json').resolve()
        if not compiler.is_file(): raise ValueError('compiler does not exist')
        jobs = load_plan(plan, compiler, cache, report)
        excluded = [cache, report, *(j['output'] for j in jobs)]
        rows = []; inputs = [plan, compiler, *(j['qc'] for j in jobs)]
        with Publication(inputs) as publication:
            publication.reserve(cache/'batch.lock')
            publication.reserve(report)
            # Create the owned output directories before measuring names. Their
            # creation must not cause an otherwise stable first build to miss.
            for job in jobs: job['output'].mkdir(parents=True, exist_ok=True)
            cache.mkdir(parents=True, exist_ok=True)
            for job in jobs:
                name = hashlib.sha256(job['id'].encode()).hexdigest()+'.json'; destination = cache/name
                different_paths([report], [destination]); publication.reserve(destination)
                previous = {}
                if destination.is_file():
                    try: previous = json.loads(destination.read_text(encoding='utf-8'))
                    except ValueError: pass
                    if not isinstance(previous, dict): previous = {}
                work = publication.work/hashlib.sha256(job['id'].encode()).hexdigest(); work.mkdir()
                try:
                    row, state = build_job(job, compiler, excluded, previous, work, args.timeout, args.force)
                except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
                    row = dict(id=job['id'], status='failed', success=False, cacheable=False, stderr_tail=str(error),
                               diagnostics=[dict(schema=1, success=False, diagnostics=[dict(code='NPB1001', severity='error', stage='batch',
                                                  source=str(job['qc']), line=None, message=str(error))])])
                    state = dict(schema=SCHEMA, cacheable=False)
                inputs.extend(Path(entry['path']) for entry in state.get('dependencies', []))
                inputs.extend(Path(entry['path']) for entry in state.get('outputs', []))
                rows.append(row)
                staged = work/'cache.json'; staged.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
                publication.add(staged, destination)
                print(job['id']+': '+row['status']+(' (uncacheable)' if not row['cacheable'] else ''))
            # Reports/cache must never alias a dependency discovered by native
            # compilation, even when it was not apparent in the plan.
            publication.inputs = tuple(inputs)
            different_paths(inputs, [entry['destination'] for entry in publication.entries.values()])
            summary = dict(schema=SCHEMA, checked_at=datetime.now(timezone.utc).isoformat(), plan=str(plan),
                           success=all(row['success'] for row in rows), jobs=rows,
                           counts={status:sum(row['status']==status for row in rows) for status in ('built','skipped','failed')})
            staged = publication.work/'batch-report.json'; staged.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            publication.add(staged, report); publication.commit()
        return 0 if summary['success'] else 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('incremental_build: '+str(error), file=sys.stderr); return 2


if __name__ == '__main__': raise SystemExit(main())
