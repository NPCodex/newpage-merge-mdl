"""Measure isolated model compiles and compare a same-machine baseline."""
import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import tempfile
import time
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def measure(compiler, qc, runs, warmup):
    samples, checksums = [], None
    with tempfile.TemporaryDirectory(prefix='newpage-benchmark-') as folder:
        root = Path(folder)
        for i in range(runs + warmup):
            output = root / str(i)
            output.mkdir()
            metrics = output / 'perf.json'
            text = qc.read_text(encoding='utf-8-sig') + '\n$OutDir "' + output.as_posix() + '"\n'
            args = [str(compiler), str(qc), '-stdin', '-game', str(output), '-perfjson', str(metrics)]
            start = time.monotonic()
            result = subprocess.run(args, input=text, text=True, capture_output=True, errors='replace', timeout=600)
            if result.returncode:
                raise RuntimeError(f'{qc}: {result.stdout[-3000:]} {result.stderr[-1000:]}')
            values = json.loads(metrics.read_text())
            values.update(wall_seconds=time.monotonic() - start, sample=i, warmup=i < warmup)
            samples.append(values)
            hashes = {str(f.relative_to(output / 'models')): sha(f)
                      for f in (output / 'models').rglob('*') if f.is_file()
                      and not any(part.startswith('.') for part in f.relative_to(output / 'models').parts)}
            if checksums is not None and checksums != hashes:
                raise RuntimeError('non-deterministic model outputs: ' + str(qc))
            checksums = hashes
    timed = samples[warmup:]
    stages = {}
    for sample in timed:
        for stage in sample['stages']:
            stages.setdefault(stage['tag'] + '/' + stage['name'], []).append(stage['ms'])
    return dict(qc=str(qc), qc_sha256=sha(qc), samples=samples,
                first_process_ms=samples[0]['total_ms'],
                median_total_ms=statistics.median(s['total_ms'] for s in timed),
                median_peak_bytes=statistics.median(s['peak_working_set_bytes'] for s in timed),
                stage_median_ms={k: statistics.median(v) for k, v in stages.items()},
                output_sha256=checksums)


def compare(report, baseline, time_limit, memory_limit):
    if report['machine'] != baseline['machine']:
        raise ValueError('Performance comparisons require the same machine identity')
    old = {Path(c['qc']).name: c for c in baseline['cases']}
    failures = []
    for case in report['cases']:
        name = Path(case['qc']).name
        if name not in old or case['qc_sha256'] != old[name]['qc_sha256']:
            raise ValueError('Baseline fixture identity differs: ' + name)
        for field, threshold in [('median_total_ms', time_limit), ('median_peak_bytes', memory_limit)]:
            reference = old[name][field]
            if reference and case[field] > reference * (1 + threshold):
                failures.append(dict(case=name, metric=field, previous=reference,
                                     current=case[field], allowed_fraction=threshold))
    return failures


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('compiler', type=Path)
    p.add_argument('--qc', type=Path, action='append', required=True)
    p.add_argument('--runs', type=int, default=5)
    p.add_argument('--warmup', type=int, default=1)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--baseline', type=Path)
    p.add_argument('--max-time-regression', type=float, default=.20)
    p.add_argument('--max-memory-regression', type=float, default=.15)
    a = p.parse_args()
    if a.runs < 3 or a.warmup < 0 or min(a.max_time_regression, a.max_memory_regression) < 0:
        p.error('Use at least 3 measured runs, nonnegative warmup and regression fractions')
    compiler = a.compiler.resolve()
    report = dict(schema=2, compiler=str(compiler), compiler_sha256=sha(compiler),
                  machine=dict(system=platform.platform(), processor=platform.processor(), node=platform.node()),
                  runs=a.runs, warmup=a.warmup, clock='steady wall time; first process is not guaranteed disk-cold',
                  cases=[measure(compiler, q.resolve(), a.runs, a.warmup) for q in a.qc])
    report['regressions'] = compare(report, json.loads(a.baseline.read_text()),
                                   a.max_time_regression, a.max_memory_regression) if a.baseline else []
    a.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for case in report['cases']:
        print(f"{Path(case['qc']).name}: {case['median_total_ms']:.1f} ms, {case['median_peak_bytes'] / 1048576:.1f} MiB")
    if report['regressions']:
        raise SystemExit('Performance regression thresholds exceeded; inspect ' + str(a.report))


if __name__ == '__main__':
    main()
