"""Measure isolated model compiles and compare a same-machine baseline."""
import argparse
import datetime
import hashlib
import json
import math
import platform
import statistics
import subprocess
import tempfile
import time
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_configuration(cache_path, configuration):
    """Read comparable, path-independent toolchain/settings from a real build."""
    cache = {}
    for line in cache_path.read_text(encoding='utf-8').splitlines():
        if not line or line.startswith(('#', '//')) or '=' not in line:
            continue
        key, value = line.split('=', 1)
        cache[key.split(':', 1)[0]] = value
    keys = ['CMAKE_GENERATOR', 'CMAKE_GENERATOR_PLATFORM', 'CMAKE_GENERATOR_TOOLSET',
            'CMAKE_MSVC_RUNTIME_LIBRARY', 'CMAKE_INTERPROCEDURAL_OPTIMIZATION',
            'NEWPAGE_COMPACT_RELEASE', 'NEWPAGE_REPRODUCIBLE', 'NEWPAGE_SEPARATE_SYMBOLS',
            'NEWPAGE_SANITIZERS', 'ASSIMP_BUILD_ALL_IMPORTERS_BY_DEFAULT',
            'NEWPAGE_BUILD_CXX_COMPILER_ID', 'NEWPAGE_BUILD_CXX_COMPILER_VERSION']
    for language in ['C', 'CXX', 'EXE_LINKER', 'STATIC_LINKER']:
        keys.extend([f'CMAKE_{language}_FLAGS', f'CMAKE_{language}_FLAGS_{configuration.upper()}'])
    values = {key: cache.get(key, '') for key in keys}
    # OFF can have a different cache type across CMake versions; the type is not
    # part of its effective value. Paths differ in two isolated source builds.
    values['configuration'] = configuration
    for language in ['C', 'CXX']:
        compiler = cache.get(f'NEWPAGE_BUILD_{language}_COMPILER',
                             cache.get(f'CMAKE_{language}_COMPILER'))
        if not compiler or not Path(compiler).is_file():
            raise ValueError(f'Cannot verify {language} compiler identity in {cache_path}')
        values[f'{language}_compiler_sha256'] = sha(compiler)
    return values


def fixture_identity(qc):
    """Benchmarks must use self-contained fixture directories, without outputs."""
    return {path.relative_to(qc.parent).as_posix(): sha(path)
            for path in sorted(qc.parent.rglob('*')) if path.is_file()}


def measure(compiler, qc, runs, warmup, plain=False):
    samples, checksums = [], None
    inputs = fixture_identity(qc)
    with tempfile.TemporaryDirectory(prefix='newpage-benchmark-') as folder:
        root = Path(folder)
        # Keep the first process separate from both warmup and measured samples.
        # Starting a new process does not flush Windows/Linux file caches.
        for i in range(1 + runs + warmup):
            output = root / str(i)
            output.mkdir()
            metrics = output / 'perf.json'
            text = qc.read_text(encoding='utf-8-sig') + '\n$OutDir "' + output.as_posix() + '"\n'
            args = [str(compiler), str(qc), '-stdin', '-game', str(output)]
            if not plain:
                args += ['-perfjson', str(metrics)]
            start = time.perf_counter()
            result = subprocess.run(args, input=text, text=True, capture_output=True, errors='replace', timeout=600)
            wall_seconds = time.perf_counter() - start
            if result.returncode:
                raise RuntimeError(f'{qc}: {result.stdout[-3000:]} {result.stderr[-1000:]}')
            values = {'schema': None} if plain else json.loads(metrics.read_text())
            values.update(wall_seconds=wall_seconds, sample=i,
                          phase='first_process' if i == 0 else 'warmup' if i <= warmup else 'measured')
            samples.append(values)
            hashes = {str(f.relative_to(output / 'models')): sha(f)
                      for f in (output / 'models').rglob('*') if f.is_file()
                      and not any(part.startswith('.') for part in f.relative_to(output / 'models').parts)}
            if not hashes:
                raise RuntimeError('Compiler produced no model files: ' + str(qc))
            if checksums is not None and checksums != hashes:
                raise RuntimeError('non-deterministic model outputs: ' + str(qc))
            checksums = hashes
    if inputs != fixture_identity(qc):
        raise RuntimeError('Input files changed during measurement: ' + str(qc))
    schemas = {sample['schema'] for sample in samples}
    if len(schemas) != 1:
        raise ValueError('Compiler metrics schema changed between samples')
    timed = samples[1 + warmup:]
    stages = {}
    for sample in timed:
        for stage in sample.get('stages', []):
            stages.setdefault(stage['tag'] + '/' + stage['name'], []).append(stage['ms'])
    return dict(qc=str(qc), qc_sha256=sha(qc), input_sha256=inputs, metrics_schema=schemas.pop(), samples=samples,
                first_process_ms=samples[0].get('total_ms'),
                first_process_wall_ms=samples[0]['wall_seconds'] * 1000,
                median_wall_ms=statistics.median(s['wall_seconds'] * 1000 for s in timed),
                median_total_ms=statistics.median(s['total_ms'] for s in timed) if not plain else None,
                median_peak_bytes=statistics.median(s['peak_working_set_bytes'] for s in timed) if not plain else None,
                main_stage_median_ms={key: statistics.median(s[key] for s in timed)
                                      for key in ['load_ms', 'compile_ms', 'write_ms']} if not plain else {},
                stage_median_ms={k: statistics.median(v) for k, v in stages.items()},
                output_sha256=checksums)


def compare(report, baseline, time_limit, memory_limit):
    if report.get('schema') != baseline.get('schema'):
        raise ValueError('Benchmark report schemas differ; regenerate the baseline with this harness')
    if report['machine'] != baseline['machine']:
        raise ValueError('Performance comparisons require the same machine identity')
    if not report.get('build_configuration') or not baseline.get('build_configuration'):
        raise ValueError('Performance comparisons require verified build configuration on both sides')
    if report['build_configuration'] != baseline['build_configuration']:
        raise ValueError('Performance comparisons require identical build configuration and toolchain')
    if report['instrumentation'] != baseline['instrumentation']:
        raise ValueError('Performance comparisons require identical instrumentation modes')
    if any(report[key] != baseline[key] for key in ['runs', 'warmup', 'first_process_runs']):
        raise ValueError('Performance comparisons require identical sampling protocols')
    old = {Path(c['qc']).name: c for c in baseline['cases']}
    names = [Path(c['qc']).name for c in report['cases']]
    if len(old) != len(baseline['cases']) or len(set(names)) != len(names) or set(old) != set(names):
        raise ValueError('Baseline case set differs or includes duplicate case names')
    failures = []
    for case in report['cases']:
        name = Path(case['qc']).name
        if name not in old or case['qc_sha256'] != old[name]['qc_sha256']:
            raise ValueError('Baseline fixture identity differs: ' + name)
        if not case.get('input_sha256') or case['input_sha256'] != old[name].get('input_sha256'):
            raise ValueError('Baseline input dependencies differ: ' + name)
        if case['metrics_schema'] != old[name]['metrics_schema']:
            raise ValueError('Compiler metric schemas differ; compare only explicitly compatible fields: ' + name)
        for field, threshold in [('median_wall_ms', time_limit), ('median_total_ms', time_limit),
                                 ('median_peak_bytes', memory_limit)]:
            reference = old[name][field]
            if (reference is None) != (case[field] is None):
                raise ValueError('Metric availability differs: ' + field)
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
    p.add_argument('--build-cache', type=Path, help='CMakeCache.txt from the measured compiler build')
    p.add_argument('--configuration', help='Actual build configuration, e.g. MinSizeRel')
    p.add_argument('--source-revision', help='Full Git revision used to build the measured compiler')
    p.add_argument('--plain', action='store_true',
                   help='Measure ordinary CLI wall time without optional report generation; no native stages or peak metric')
    p.add_argument('--max-time-regression', type=float, default=.20)
    p.add_argument('--max-memory-regression', type=float, default=.15)
    a = p.parse_args()
    limits = [a.max_time_regression, a.max_memory_regression]
    if a.runs < 3 or a.warmup < 0 or any(not math.isfinite(value) or value < 0 for value in limits):
        p.error('Use at least 3 measured runs, nonnegative warmup and regression fractions')
    if bool(a.build_cache) != bool(a.configuration):
        p.error('--build-cache and --configuration must be supplied together')
    if a.baseline and not a.build_cache:
        p.error('--baseline requires --build-cache and --configuration')
    compiler = a.compiler.resolve()
    report = dict(schema=3, compiler=str(compiler), compiler_sha256=sha(compiler),
                  measured_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  source_revision=a.source_revision,
                  build_cache_sha256=sha(a.build_cache) if a.build_cache else None,
                  build_configuration=build_configuration(a.build_cache, a.configuration) if a.build_cache else None,
                  machine=dict(system=platform.platform(), processor=platform.processor(), node=platform.node()),
                  runs=a.runs, warmup=a.warmup, first_process_runs=1,
                  instrumentation='none' if a.plain else 'perfjson',
                  clock='perf_counter subprocess wall time; compiler steady-clock stages; first process is not guaranteed disk-cold',
                  thresholds=dict(time_fraction=a.max_time_regression, memory_fraction=a.max_memory_regression,
                                  time_metrics=['median_wall_ms', 'median_total_ms']),
                  input_contract='Each QC parent directory must contain its complete input dependency tree and no outputs',
                  cases=[measure(compiler, q.resolve(), a.runs, a.warmup, a.plain) for q in a.qc])
    report['regressions'] = compare(report, json.loads(a.baseline.read_text()),
                                   a.max_time_regression, a.max_memory_regression) if a.baseline else []
    a.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for case in report['cases']:
        native = (f", compiler {case['median_total_ms']:.1f} ms, {case['median_peak_bytes'] / 1048576:.1f} MiB"
                  if case['median_total_ms'] is not None else '')
        print(f"{Path(case['qc']).name}: process {case['median_wall_ms']:.1f} ms{native}")
    if report['regressions']:
        raise SystemExit('Performance regression thresholds exceeded; inspect ' + str(a.report))


if __name__ == '__main__':
    main()
