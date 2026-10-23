#!/usr/bin/env python3
"""Build the same exact source twice at different paths and compare every byte.

This is one-toolchain reproducibility evidence. It does not claim equality across
different compiler versions, operating systems, or SDK-generated helpers.
"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/scripts'))
from compare_builds import compare
import package_symbols
import upstream_release


def unpack_source(archive, destination):
    with zipfile.ZipFile(archive) as source:
        names = source.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate source archive members')
        for name in names:
            path = PurePosixPath(name)
            if (not name.startswith('NewPageMergeMDL/') or '..' in path.parts
                    or '\\' in name or ':' in name):
                raise ValueError('Unsafe source archive member: ' + name)
        source.extractall(destination)
    return destination / 'NewPageMergeMDL'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-archive', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--platform', choices=('win64', 'linux64'), required=True)
    parser.add_argument('--cmake', default='cmake')
    parser.add_argument('--parallel', type=int, default=2)
    parser.add_argument('--ipo', choices=('ON', 'OFF'), default='ON')
    parser.add_argument('--extras-dist', type=Path,
                        help='Already SHA-verified Windows helper staging directory')
    args = parser.parse_args()
    if 'SOURCE_DATE_EPOCH' not in os.environ:
        parser.error('SOURCE_DATE_EPOCH must identify the exact input revision')
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    archive = args.source_archive.resolve()
    original_manifest = args.manifest.read_bytes()
    result = {'schema': 1, 'scope': 'Two clean builds, one toolchain, distinct source/build paths',
              'source_archive_sha256': upstream_release.sha256(archive), 'platform': args.platform,
              'configuration': 'MinSizeRel', 'requested_ipo': args.ipo,
              'source_date_epoch': os.environ['SOURCE_DATE_EPOCH'], 'success': False}
    try:
        for label in ('first', 'second'):
            folder = work / label
            source = unpack_source(archive, folder)
            build, dist = folder / 'build', folder / 'dist'
            command = [args.cmake, '-S', str(source), '-B', str(build),
                       '-DCMAKE_BUILD_TYPE=MinSizeRel', '-DCMAKE_INTERPROCEDURAL_OPTIMIZATION=' + args.ipo,
                       '-DNEWPAGE_REPRODUCIBLE=ON', '-DNEWPAGE_SEPARATE_SYMBOLS=ON',
                       '-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded',
                       '-DPULSE_BUILD_MESHTOOL=ON', '-DPULSE_BUILD_L4D_ANIMSWAP=ON',
                       '-DPULSE_BUILD_VMD2VALVEBIPED=ON', '-DPULSE_BUILD_AG2PROPORTIONS=ON',
                       '-DCMAKE_RUNTIME_OUTPUT_DIRECTORY=' + str(dist),
                       '-DCMAKE_RUNTIME_OUTPUT_DIRECTORY_MINSIZEREL=' + str(dist)]
            for step, invocation in (('configure', command), ('build', [args.cmake, '--build', str(build),
                                     '--config', 'MinSizeRel', '--parallel', str(args.parallel)])):
                print(label + ': ' + step, flush=True)
                with (folder / (step + '.log')).open('w', encoding='utf-8') as log:
                    subprocess.run(invocation, stdout=log, stderr=subprocess.STDOUT, check=True)
            if args.platform == 'win64':
                if not args.extras_dist:
                    raise ValueError('Windows package comparison needs verified --extras-dist')
                # Include identical pinned inputs in both packages without building
                # or claiming reproducibility for the proprietary SDK helper.
                config = json.loads((source / 'automation/windows-extras.json').read_text())
                for entry in config['files']:
                    helper = args.extras_dist / entry['name']
                    if upstream_release.sha256(helper) != entry['sha256']:
                        raise ValueError('Unverified Windows helper: ' + entry['name'])
                    shutil.copyfile(helper, dist / entry['name'])
                metadata = args.extras_dist / 'windows-extras-manifest.json'
                if json.loads(metadata.read_text()) != config:
                    raise ValueError('Windows helper metadata differs from source pin')
                shutil.copyfile(metadata, dist / metadata.name)
            manifest = folder / 'manifest.json'
            manifest.write_bytes(original_manifest)
            upstream_release.record_build(argparse.Namespace(manifest=manifest, cache=build / 'CMakeCache.txt',
                                                              configuration='MinSizeRel'))
            runtime, symbols = folder / 'runtime.zip', folder / 'symbols.zip'
            upstream_release.package(argparse.Namespace(source=source, dist=dist, platform=args.platform,
                                                        manifest=manifest, source_archive=archive, output=runtime))
            package_symbols.package(dist, runtime, args.platform, symbols)
        result['executables'] = compare(work / 'first/dist', work / 'second/dist')
        result['runtime_packages'] = compare(work / 'first/runtime.zip', work / 'second/runtime.zip')
        result['symbol_packages'] = compare(work / 'first/symbols.zip', work / 'second/symbols.zip')
        result['required_equal'] = ['executables', 'runtime_packages']
        if args.platform == 'linux64':
            result['required_equal'].append('symbol_packages')
        elif not result['symbol_packages']['equal']:
            # Keep every difference in the report. MSVC maps compilation source
            # paths, but its linker still writes absolute object/CVTRES working
            # paths into PDB streams. Rewriting those streams risks invalidating
            # source-line information. Native identity and source provenance were
            # verified independently for both archives by package_symbols above.
            result['symbol_reproducibility_limit'] = (
                'Windows PDBs retain absolute linker object/CVTRES paths. Matching '
                'GUID/age and source provenance are required; symbol ZIP byte '
                'equality is reported but not claimed or required on Windows.')
        result['success'] = all(result[key]['equal'] for key in result['required_equal'])
        print(json.dumps(result, indent=2))
        return 0 if result['success'] else 1
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result['error'] = str(error)
        raise
    finally:
        (work / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())
