#!/usr/bin/env python3
"""Stage redistributable Windows helpers from a pinned, verified own release.

CI needs only the already linked C4D executable, never the Cineware SDK. Both
the release archive and each selected executable must match their pinned hashes.
No files are staged until every configured executable has passed verification.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('windows_extras_download',
                                            ROOT / '.github/scripts/upstream_release.py')
downloads = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloads)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Expected a pinned SHA256 digest')
    return value


def validate_config(config):
    if config.get('schema') != 1:
        raise ValueError('Unsupported Windows extras manifest schema')
    source = config['source']
    if not re.fullmatch(
            r'https://github\.com/NPCodex/newpage-merge-mdl/releases/download/'
            r'[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\.zip', source['url']):
        raise ValueError('Windows extras must come from a pinned project release ZIP')
    if not re.fullmatch(
            r'https://api\.github\.com/repos/NPCodex/newpage-merge-mdl/releases/assets/[0-9]+',
            source['api_url']):
        raise ValueError('Windows extras require a pinned project asset API URL')
    _hash(source['sha256'])
    files = config['files']
    if not files:
        raise ValueError('Expected at least one Windows helper')
    names, members = set(), set()
    for entry in files:
        name, member = entry['name'], entry['member']
        if not re.fullmatch(r'[A-Za-z0-9._-]+\.exe', name):
            raise ValueError('Windows helper output must be a flat executable filename')
        path = PurePosixPath(member)
        if (not path.parts or path.is_absolute() or '..' in path.parts or '\\' in member
                or ':' in member or member != path.as_posix()
                or path.parts[0] != 'NewPageMergeMDL'):
            raise ValueError('Unsafe Windows helper archive member')
        if name.casefold() in names or member in members:
            raise ValueError('Duplicate Windows helper output or member')
        names.add(name.casefold())
        members.add(member)
        _hash(entry['sha256'])


def stage(config_path, dist, fetch=None):
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    validate_config(config)
    data = (fetch or downloads.fetch)(config['source']['api_url'], accept='application/octet-stream')
    if _digest(data) != config['source']['sha256']:
        raise ValueError('Windows extras archive SHA256 mismatch')
    staged = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        for entry in config['files']:
            if names.count(entry['member']) != 1:
                raise ValueError('Missing or ambiguous Windows helper: ' + entry['member'])
            binary = archive.read(entry['member'])
            if _digest(binary) != entry['sha256']:
                raise ValueError('Windows helper SHA256 mismatch: ' + entry['name'])
            if not binary.startswith(b'MZ'):
                raise ValueError('Windows helper is not a PE executable: ' + entry['name'])
            staged[entry['name']] = binary
    # Include executable provenance in the final package alongside build provenance.
    staged['windows-extras-manifest.json'] = (json.dumps(config, indent=2) + '\n').encode('utf-8')
    dist = Path(dist)
    dist.mkdir(parents=True, exist_ok=True)
    for name, contents in staged.items():
        with tempfile.NamedTemporaryFile(dir=dist, prefix='.windows-extra-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
        try:
            os.replace(temporary, dist / name)
        finally:
            temporary.unlink(missing_ok=True)
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'automation/windows-extras.json')
    parser.add_argument('--dist', type=Path, required=True)
    args = parser.parse_args()
    config = stage(args.config, args.dist)
    print('Verified and staged: ' + ', '.join(entry['name'] for entry in config['files']))


if __name__ == '__main__':
    main()
