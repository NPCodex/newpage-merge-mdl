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
from upstream_release import api, fetch, append_release_notes, verified_package_manifest, package_source_identity


def recorded_source(release):
    recorded = re.findall(r'<!-- newpage-source:([0-9a-f]{40}) -->', release.get('body') or '')
    return recorded[-1] if recorded else None


def manifest_for_release(release):
    packages = []
    for platform in ('win64', 'linux64'):
        candidates = [a for a in release['assets'] if re.fullmatch(
            r'newpage-merge-mdl-(?:v[\w.-]+-)?' + platform + r'\.zip', a['name'])]
        # Same-tag replacement uses unversioned names. Old versioned archives
        # can still be present, but are no longer the active platform package.
        current = [a for a in candidates if a['name'] == 'newpage-merge-mdl-' + platform + '.zip']
        selected = current or candidates
        if len(selected) > 1:
            raise ValueError('Ambiguous previous platform package: ' + platform)
        packages.extend(selected)
    if packages:
        manifests = []
        for asset in packages:
            data = fetch(asset['url'], accept='application/octet-stream')
            digest = asset.get('digest')
            if digest and digest != 'sha256:' + hashlib.sha256(data).hexdigest():
                raise ValueError('Previous release package digest mismatch: ' + asset['name'])
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                manifest = json.loads(archive.read('NewPageMergeMDL/upstream-manifest.json'))
                manifest = verified_package_manifest(archive, manifest)
            sha = manifest.get('controller_sha', '')
            if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}', sha):
                raise ValueError('Invalid release source commit: ' + asset['name'])
            manifests.append(manifest)
        sources = sorted({m['controller_sha'] for m in manifests})
        for source in sources:
            identities = {package_source_identity(m) for m in manifests if m['controller_sha'] == source}
            if len(identities) > 1:
                raise ValueError('Platform package source identities differ at the same controller commit')
        if len(sources) > 1 and not recorded_source(release):
            raise ValueError('Platform package sources differ and no release checkpoint exists')
        return dict(manifests[0], controller_sha=recorded_source(release) or sources[0],
                    package_controller_shas=sources)
    direct = [a for a in release['assets'] if a['name'] == 'upstream-manifest.json']
    if len(direct) == 1:
        data = fetch(direct[0]['url'], accept='application/octet-stream')
        digest = direct[0].get('digest')
        if digest and digest != 'sha256:' + hashlib.sha256(data).hexdigest():
            raise ValueError('Previous release manifest digest mismatch')
        return json.loads(data)
    raise ValueError('Previous release has no package manifest; cannot establish the incremental source range')


def source_base(release, manifest, head, git=subprocess.check_output):
    base = manifest.get('controller_sha', '')
    sources = manifest.get('package_controller_shas', [base])
    if not isinstance(sources, list) or not sources or any(
            not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}', sha)
            for sha in [base, head, *sources]):
        raise ValueError('Invalid release source commit')
    for source in sources:
        git(['git', 'merge-base', '--is-ancestor', source, head])
    recorded = recorded_source(release)
    if recorded:
        # All packages must be at or after this notes checkpoint. A partial
        # upload can have two source SHAs; neither silently becomes the base.
        for source in sources:
            git(['git', 'merge-base', '--is-ancestor', recorded, source])
        base = recorded
    return base


def checkpoint_body(release, manifest, head, git=subprocess.check_output):
    base = source_base(release, manifest, head, git)
    previous = release.get('body') or ''
    if recorded_source(release) == base:
        return previous
    return previous + ('\n\n' if previous else '') + '<!-- newpage-source:' + base + ' -->\n'


def incremental_notes(release, manifest, head, checksums, git=subprocess.check_output):
    base = source_base(release, manifest, head, git)
    previous = release.get('body') or ''
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
    parser.add_argument('--checkpoint', type=Path, required=True,
                        help='Old body plus source checkpoint; publish this before replacing any asset')
    parser.add_argument('packages', type=Path, nargs='+')
    args = parser.parse_args()
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-r\d+)?', args.tag):
        raise ValueError('Expected a stable replacement tag')
    release = api(f'repos/{args.repo}/releases/tags/{args.tag}')
    manifest = manifest_for_release(release)
    checksums = '\n'.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name for p in sorted(args.packages))
    body = incremental_notes(release, manifest, args.head, checksums)
    checkpoint = checkpoint_body(release, manifest, args.head)
    args.output.write_text(body.rstrip() + '\n', encoding='utf-8')
    args.checkpoint.write_text(checkpoint, encoding='utf-8')


if __name__ == '__main__':
    main()
