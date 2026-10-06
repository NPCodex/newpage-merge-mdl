#!/usr/bin/env python3
"""Regenerate the maintained overlay without touching the current Git history."""
import json
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PATHS = ['libs', 'mdlcompiler', 'mdldecompiler', 'subtools', 'CMakeLists.txt', 'CMakePresets.json', 'utf8.manifest']


def run(*args, cwd=None, capture=False):
    return subprocess.run(list(map(str, args)), cwd=cwd, check=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if the stored overlay is stale')
    parser.add_argument('--base-repository', help='Optional local mirror for offline verification')
    args = parser.parse_args()
    config = json.loads((ROOT / 'automation/upstreams.json').read_text())
    with tempfile.TemporaryDirectory() as directory:
        repo = Path(directory) / 'base'
        run('git', 'clone', '--filter=blob:none', '--no-checkout',
            args.base_repository or f"https://github.com/{config['pulsemodel']}.git", repo)
        run('git', 'config', 'core.autocrlf', 'input', cwd=repo)
        run('git', 'checkout', '--detach', config['pulse_base'], cwd=repo)
        for name in PATHS:
            source, target = ROOT / name, repo / name
            if not source.exists():
                raise ValueError('Required overlay input missing: ' + name)
            if source.is_dir():
                # Delete only our temporary clone's selected source directory.
                if repo.resolve() not in target.resolve().parents:
                    raise ValueError('Target escapes temporary clone')
                shutil.rmtree(target)
                shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            else:
                shutil.copy2(source, target)
        run('git', 'add', '--', *PATHS, cwd=repo)
        patch = run('git', 'diff', '--cached', '--binary', '--', *PATHS, cwd=repo, capture=True)
        if not patch:
            raise ValueError('Empty overlay; refusing to overwrite maintained patch')
        destination = ROOT / 'automation/compatibility.patch'
        if args.check:
            # A Windows checkout can convert this text patch to CRLF.
            if not destination.exists() or destination.read_bytes().replace(b'\r\n', b'\n') != patch:
                raise ValueError('Stale compatibility.patch: run refresh_overlay.py and commit the result')
            print('Compatibility overlay matches maintained source.')
        else:
            destination.write_bytes(patch)
            print('Updated compatibility.patch; review and commit it with the source changes.')


if __name__ == '__main__':
    main()
