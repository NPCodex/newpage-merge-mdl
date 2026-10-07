"""Verify and exercise the actual packaged binaries before publishing.

Usage: python tests/verify_package.py package.zip --manifest manifest.json
"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile


def verify(archive, expected, destination):
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        if len(set(names)) != len(names):
            raise ValueError('Duplicate archive entries')
        for name in names:
            path = PurePosixPath(name.replace('\\', '/'))
            if path.is_absolute() or '..' in path.parts or ':' in name or not path.parts or path.parts[0] != 'NewPageMergeMDL':
                raise ValueError('Unsafe archive member: ' + name)
        manifest = json.loads(package.read('NewPageMergeMDL/upstream-manifest.json'))
        if manifest != expected:
            raise ValueError('Packaged source provenance does not match preparation manifest')
        for name in ('README.md', 'README.en.md', 'VALIDATION.md', 'IMPROVEMENTS.md', 'integration/gmod/newpage_vertexanim.lua'):
            package.getinfo('NewPageMergeMDL/' + name)
        suffix = '.exe' if os.name == 'nt' else ''
        for tool in ('NewPageMergeMDL', 'NewPageMergeMDL-Decompiler'):
            binary = package.read('NewPageMergeMDL/' + tool + suffix)
            if not binary.startswith(b'MZ' if os.name == 'nt' else b'\x7fELF'):
                raise ValueError('Invalid native executable: ' + tool)
        package.extractall(destination)
    root = Path(destination) / 'NewPageMergeMDL'
    if os.name != 'nt':
        for binary in root.iterdir():
            if binary.is_file() and binary.read_bytes()[:4] == b'\x7fELF':
                binary.chmod(0o755)
    return root / ('NewPageMergeMDL' + suffix)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--manifest', required=True)
    args = parser.parse_args()
    expected = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='newpage-package-') as folder:
        compiler = verify(args.archive, expected, folder)
        banner = subprocess.run([str(compiler), '-version'], capture_output=True, text=True, errors='replace')
        if 'v' + expected['project_version'] not in banner.stdout:
            raise ValueError('Executable version does not match packaged source version')
        subprocess.run([sys.executable, str(Path(__file__).with_name('compatibility.py')), str(compiler)], check=True)
    print('Packaged binaries, version, provenance, runtime files and compatibility suite verified.')


if __name__ == '__main__':
    main()
