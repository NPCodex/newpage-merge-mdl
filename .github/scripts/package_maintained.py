"""Shared strict package and verification path for maintained CI builds."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=Path('.'))
    p.add_argument('--dist', type=Path, required=True)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--configuration', required=True)
    p.add_argument('--platform', choices=('win64', 'linux64'), required=True)
    p.add_argument('--tag', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--symbols-output', type=Path,
                   help='Independent symbols ZIP; requires NEWPAGE_SEPARATE_SYMBOLS=ON')
    p.add_argument('--manifest', type=Path, default=Path('upstream-manifest.json'))
    p.add_argument('--subtool-probe', type=Path, required=True)
    a = p.parse_args()
    source = a.source.resolve()
    os.environ.setdefault('SOURCE_DATE_EPOCH', subprocess.check_output(
        ['git', '-C', str(source), 'show', '-s', '--format=%ct', 'HEAD'], text=True).strip())
    script = source / '.github/scripts/upstream_release.py'

    def run(*args):
        subprocess.run(list(map(str, args)), check=True)

    with tempfile.TemporaryDirectory(prefix='newpage-source-') as directory:
        archive = Path(directory) / 'NewPageMergeMDL-source.zip'
        run('git', '-C', source, '-c', 'core.autocrlf=false', '-c', 'core.eol=lf',
            'archive', '--format=zip', '--prefix=NewPageMergeMDL/', '--output=' + str(archive), 'HEAD')
        run(sys.executable, script, 'maintained-manifest', '--source', source,
            '--output', a.manifest, '--tag', a.tag)
        run(sys.executable, script, 'record-build', '--manifest', a.manifest,
            '--cache', a.cache, '--configuration', a.configuration)
        run(sys.executable, script, 'package', '--source', source, '--dist', a.dist,
            '--platform', a.platform, '--manifest', a.manifest, '--source-archive', archive,
            '--output', a.output)
    run(sys.executable, source / 'tests/verify_package.py', a.output,
        '--manifest', a.manifest, '--subtool-probe', a.subtool_probe)
    if a.platform == 'linux64':
        run(sys.executable, source / 'tests/linux_package_smoke.py', a.output, '--require-baseline')
    if a.symbols_output:
        run(sys.executable, source / '.github/scripts/package_symbols.py', 'package',
            '--dist', a.dist, '--runtime', a.output, '--platform', a.platform,
            '--output', a.symbols_output)


if __name__ == '__main__':
    main()
