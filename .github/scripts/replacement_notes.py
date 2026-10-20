"""Build replacement notes from the source commit inside the previous package."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile
from upstream_release import api, fetch, append_release_notes


def manifest_for_release(release):
    direct = [a for a in release['assets'] if a['name'] == 'upstream-manifest.json']
    if len(direct) == 1:
        return json.loads(fetch(direct[0]['url'], accept='application/octet-stream'))
    packages = sorted((a for a in release['assets'] if re.fullmatch(r'newpage-merge-mdl-(?:v[\w.-]+-)?(?:win64|linux64)\.zip', a['name'])),
                      key=lambda a: (a['size'], a['name']))
    if not packages:
        raise ValueError('Previous release has no package manifest; cannot establish the incremental source range')
    data = fetch(packages[0]['url'], accept='application/octet-stream')
    digest = packages[0].get('digest')
    if digest and digest != 'sha256:' + hashlib.sha256(data).hexdigest():
        raise ValueError('Previous release package digest mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return json.loads(archive.read('NewPageMergeMDL/upstream-manifest.json'))


def incremental_notes(release, manifest, head, checksums, git=subprocess.check_output):
    base = manifest.get('controller_sha', '')
    if not re.fullmatch(r'[0-9a-f]{40}', base) or not re.fullmatch(r'[0-9a-f]{40}', head):
        raise ValueError('Invalid release source commit')
    git(['git', 'merge-base', '--is-ancestor', base, head])
    previous = release.get('body') or ''
    recorded = re.findall(r'<!-- newpage-source:([0-9a-f]{40}) -->', previous)
    if recorded:
        # If uploading finished but editing the body failed, the package may
        # already be newer than the last recorded notes. Resume that range.
        base = recorded[-1]
        git(['git', 'merge-base', '--is-ancestor', base, head])
    seen = re.findall(r'<!-- newpage-commit:([0-9a-f]{40}) -->', previous)
    log = git(['git', 'log', '--reverse', '--pretty=format:%x00%H%x1f%B', base + '..' + head]).decode('utf-8')
    spec = importlib.util.spec_from_file_location('notes_renderer', Path(__file__).with_name('release-notes.py'))
    renderer = importlib.util.module_from_spec(spec); spec.loader.exec_module(renderer)
    prose = renderer.render(log, seen)
    if prose == 'No changes.':
        prose = ''
    commits = [sha for sha in re.findall(r'\x00([0-9a-f]{40})\x1f', log) if sha not in seen]
    if commits:
        prose += '\n\n' + '\n'.join('<!-- newpage-commit:' + sha + ' -->' for sha in dict.fromkeys(commits))
    current = prose.strip() + '\n\nZIP SHA256:\n```text\n' + checksums + '\n```\n'
    return append_release_notes(previous, current.strip(), release['tag_name'], head)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('packages', type=Path, nargs='+')
    args = parser.parse_args()
    if not re.fullmatch(r'v\d+\.\d+\.\d+', args.tag):
        raise ValueError('Expected a stable replacement tag')
    release = api(f'repos/{args.repo}/releases/tags/{args.tag}')
    manifest = manifest_for_release(release)
    checksums = '\n'.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name for p in sorted(args.packages))
    body = incremental_notes(release, manifest, args.head, checksums)
    args.output.write_text(body.rstrip() + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
