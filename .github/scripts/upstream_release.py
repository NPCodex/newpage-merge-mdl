#!/usr/bin/env python3
"""Fetch upstream versions, apply maintained source patches, stage tested releases.

Closed-source downloads are reference inputs only and are never redistributed.
All URLs come from configured official GitHub repositories, not release-body text.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        host = parsed.hostname or ''
        if parsed.scheme != 'https' or not (host in {'api.github.com', 'github.com', 'codeload.github.com'}
                                           or host.endswith('.githubusercontent.com')):
            raise ValueError('Unexpected GitHub download redirect')
        redirected = super().redirect_request(request, fp, code, message, headers, newurl)
        if redirected and host != urllib.parse.urlparse(request.full_url).hostname:
            redirected.remove_header('Authorization')
        return redirected


def fetch(url, accept=None):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in {
        'api.github.com', 'github.com', 'codeload.github.com'
    }:
        raise ValueError('Unexpected upstream URL host')
    headers = {'User-Agent': 'NewPageMergeMDL-upstream-sync'}
    if parsed.hostname == 'api.github.com':
        headers['Accept'] = accept or 'application/vnd.github+json'
        if os.environ.get('GH_TOKEN'):
            headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    opener = urllib.request.build_opener(GitHubRedirect())
    with opener.open(urllib.request.Request(url, headers=headers), timeout=120) as response:
        return response.read()


def api(path):
    return json.loads(fetch('https://api.github.com/' + path))


def latest_commit(repo):
    # No branch guess: /commits defaults to the repository's default branch.
    return api(f'repos/{repo}/commits?per_page=1')[0]['sha']


def select_tools(release, names):
    assets = []
    for name in names:
        matches = [a for a in release['assets'] if a['name'] == name]
        if len(matches) != 1:
            raise ValueError(f'Expected exactly one Tools++ asset: {name}')
        asset = matches[0]
        assets.append({k: asset[k] for k in ('id', 'name', 'size', 'updated_at', 'browser_download_url')})
    return assets


def fingerprint(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def published_manifest(repo):
    if not repo:
        return None
    releases = api(f'repos/{repo}/releases?per_page=100')
    # API list order can differ from publication order when tags share an older target.
    for release in sorted(releases, key=lambda item: item.get('published_at') or '', reverse=True):
        if release['draft'] or not (release['tag_name'].startswith('newpage-auto-') or
                                  re.fullmatch(r'v\d+\.\d+(?:\.\d+)?(?:-auto-[\w-]+)?', release['tag_name'])):
            continue
        for asset in release['assets']:
            if asset['name'] == 'upstream-manifest.json':
                # The API endpoint supports GITHUB_TOKEN for private repositories.
                manifest = json.loads(fetch(asset['url'], accept='application/octet-stream'))
                manifest.setdefault('release_tag', release['tag_name'])
                return manifest
    return None


def run(*args, cwd=None):
    subprocess.run(list(map(str, args)), cwd=cwd, check=True)


def emit(**values):
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output, 'a', encoding='utf-8') as stream:
            for key, value in values.items():
                stream.write(f'{key}={str(value).lower() if isinstance(value, bool) else value}\n')
    print(json.dumps(values))


def create_source(root, pulse_repo, revision, base, patch):
    root = Path(root).resolve()
    if root.exists():
        raise ValueError('Candidate directory must be new; refusing to overwrite it')
    run('git', 'clone', '--filter=blob:none', '--no-checkout',
        f'https://github.com/{pulse_repo}.git', root)
    # Fetch both exact revisions. Do not substitute a moving branch or release tag.
    run('git', 'fetch', 'origin', revision, base, cwd=root)
    # Materialize the base blobs before applying an abbreviated-id patch.
    # Partial clones cannot lazy-fetch unknown abbreviated object ids.
    run('git', 'checkout', '--detach', base, cwd=root)
    run('git', 'checkout', '--detach', revision, cwd=root)
    run('git', 'apply', '--3way', '--index', '--whitespace=nowarn', Path(patch).resolve(), cwd=root)
    # Preserve upstream vendored source/license formatting. Whitespace checks
    # still gate maintained compiler code; apply --3way --index rejects conflicts.
    run('git', 'diff', '--check', '--cached', '--', '.',
        ':(exclude)libs/assimp/**', ':(exclude)libs/cgltf/cgltf.h', cwd=root)


def release_version(base, previous, content_fingerprint):
    """Allocate a patch release, preserving the identity of forced retries."""
    def parts(value):
        if not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', value):
            raise ValueError('Invalid project version: ' + value)
        return tuple(map(int, (value + '.0' if value.count('.') == 1 else value).split('.')))
    floor = parts(base)
    if previous and previous.get('fingerprint') == content_fingerprint:
        version = previous.get('project_version', base)
        parts(version)
        return version, previous.get('release_tag', 'v' + version)
    if previous and previous.get('project_version'):
        old = parts(previous['project_version'])
        floor = max(floor, (old[0], old[1], old[2] + 1))
    version = '.'.join(map(str, floor))
    return version, 'v' + version


def stamp_version(candidate, base, version):
    cmake = candidate / 'CMakeLists.txt'
    text = cmake.read_text(encoding='utf-8')
    text, count = re.subn(r'(project\(NewPageMergeMDL VERSION )\S+', lambda m: m[1] + version, text)
    if count != 1:
        raise ValueError('Expected one compiler project version')
    cmake.write_text(text, encoding='utf-8')
    for name in ('README.md', 'README.en.md', 'AUTOMATION.md'):
        path = candidate / name
        path.write_text(path.read_text(encoding='utf-8').replace('v' + base, 'v' + version), encoding='utf-8')
    config_path = candidate / 'automation/upstreams.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    config['project_version'] = version
    config_path.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')


def prepare(args):
    config = json.loads((ROOT / 'automation/upstreams.json').read_text())
    overlay = ROOT / 'automation/compatibility.patch'
    controller = os.environ.get('GITHUB_SHA') or subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    state = {
        'schema': 1,
        'project_version': config.get('project_version', '1.2.0'),
        'controller_sha': controller,
        'overlay_sha256': sha256(overlay),
        'configuration_sha256': sha256(ROOT / 'automation/upstreams.json'),
        'pulsemodel': {'repo': config['pulsemodel'], 'sha': latest_commit(config['pulsemodel'])},
        'integration': {
            'pulsemodel': 'source patch overlay',
            'studiomdl_ce': 'reference download; new functionality not automatically ported',
            'studiomdl_plusplus': 'reference download; new functionality not automatically ported'
        }
    }
    state['fingerprint'] = fingerprint(state)
    previous = published_manifest(os.environ.get('GITHUB_REPOSITORY'))
    base_version = state['project_version']
    state['project_version'], tag = release_version(base_version, previous, state['fingerprint'])
    state['version_base'] = base_version
    state['release_tag'] = tag
    if previous and previous.get('fingerprint') == state['fingerprint'] and not args.force:
        emit(changed=False, tag=tag)
        return
    # Closed-source versions are provenance only. They cannot independently
    # trigger a rebuild; the user supplies their functional updates manually.
    state['studiomdl_ce'] = {'repo': config['studiomdl_ce'], 'sha': latest_commit(config['studiomdl_ce'])}
    state['studiomdl_plusplus'] = {
        'repo': config['tools_repository'], 'tag': config['tools_tag'],
        'assets': select_tools(api(f"repos/{config['tools_repository']}/releases/tags/{config['tools_tag']}"),
                              config['tools_assets'])
    }
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    references = work / 'references'
    references.mkdir()
    for asset in state['studiomdl_plusplus']['assets']:
        path = references / asset['name']
        path.write_bytes(fetch(asset['browser_download_url']))
        if path.stat().st_size != asset['size']:
            raise ValueError('Tools++ asset size mismatch')
        asset['download_sha256'] = sha256(path)
    ce = state['studiomdl_ce']
    ce_path = references / 'StudioMDL-CE.zip'
    ce_path.write_bytes(fetch(f"https://codeload.github.com/{ce['repo']}/zip/{ce['sha']}"))
    ce['download_sha256'] = sha256(ce_path)
    if not zipfile.is_zipfile(ce_path):
        raise ValueError('StudioMDL-CE download is not a valid ZIP')
    candidate = work / 'candidate'
    create_source(candidate, config['pulsemodel'], state['pulsemodel']['sha'], config['pulse_base'], overlay)
    # Ship the controller's automation, tests and user documentation, never upstream workflows.
    for name in ('.github', 'automation', 'tests'):
        target = candidate / name
        if target.exists():
            if candidate.resolve() not in target.resolve().parents:
                raise ValueError('Controller target escapes candidate')
            shutil.rmtree(target)
        shutil.copytree(ROOT / name, candidate / name, dirs_exist_ok=True)
    for name in ('README.md', 'README.en.md', 'UPSTREAM_README.md', 'COMPATIBILITY.md', 'BINARY_ANALYSIS.md', 'AUTOMATION.md', 'RESEARCH.md', '.gitignore'):
        shutil.copy2(ROOT / name, candidate / name)
    stamp_version(candidate, base_version, state['project_version'])
    run(sys.executable, candidate / '.github/scripts/refresh_overlay.py', '--base-repository', candidate)
    state['build_overlay_sha256'] = sha256(candidate / 'automation/compatibility.patch')
    state['generated_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (work / 'upstream-manifest.json').write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    notes = (
        f"# NewPageMergeMDL v{state['project_version']} automatic build\n\n"
        f"PulseModel source: `{state['pulsemodel']['sha']}`\n\n"
        f"StudioMDL-CE reference: `{ce['sha']}`\n\n"
        'Tools++ reference assets: ' + ', '.join(a['name'] for a in state['studiomdl_plusplus']['assets']) + '\n\n'
        'PulseModel was integrated using the maintained compatibility overlay. '
        'StudioMDL-CE and StudioMDL++ were downloaded for version tracking only; '
        'their new closed-source functionality is not automatically integrated. '
        'Their binaries are not included in this release.\n\n'
        'Includes independently implemented NekoMDL compatibility based on the supplied Chinese v2.3.0 changelog: '
        'scene import, Neko model/driver syntax, jiggle options and QC extensions. '
        'Neko binaries are not redistributed; reference updates are reviewed manually. '
        'See both READMEs and COMPATIBILITY.md for remaining differences.\n\n'
        'Includes NvTriStrip legacy ordering, LOD replacement validation, '
        'DMX finite-number checks, safe oversized animation encoding and long PHY strings. '
        'Global legacy clamping and 512 final bones remain unsupported; '
        'see RESEARCH.md for measured performance and validation scope.\n\n'
        'Both platform builds and compatibility tests must pass before publication. '
        'The attached source archive is the actual merged build input; '
        'GitHub-generated source archives correspond to the controller commit.\n'
    )
    (work / 'release-notes.md').write_text(notes, encoding='utf-8')
    emit(changed=True, tag=tag)


def source_archive(args):
    source, destination = Path(args.source), Path(args.output)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob('*')):
            relative = path.relative_to(source)
            if path.is_file() and not any(p in {'.git', '__pycache__', 'build', 'out', 'dist'} for p in relative.parts):
                archive.write(path, Path('NewPageMergeMDL') / relative)


def package(args):
    dist, output = Path(args.dist), Path(args.output)
    extension = '.exe' if args.platform == 'win64' else ''
    for name in ('NewPageMergeMDL', 'NewPageMergeMDL-Decompiler'):
        if not (dist / (name + extension)).is_file():
            raise ValueError('Missing required executable: ' + name)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dist.rglob('*')):
            if path.is_file():
                archive.write(path, Path('NewPageMergeMDL') / path.relative_to(dist))
        for name in ('LICENSE', 'README.md', 'README.en.md', 'COMPATIBILITY.md', 'BINARY_ANALYSIS.md', 'AUTOMATION.md', 'RESEARCH.md'):
            archive.write(Path(args.source) / name, Path('NewPageMergeMDL') / name)
        archive.write(args.manifest, 'NewPageMergeMDL/upstream-manifest.json')
        # Preserve bundled third-party license notices.
        for path in sorted((Path(args.source) / 'libs').rglob('*')):
            nv_notice = path.parent.name == 'nvtristrip' and path.name in {'README.txt', 'SOURCE.md'}
            if path.is_file() and ('license' in path.name.lower() or 'copying' in path.name.lower() or nv_notice):
                archive.write(path, Path('NewPageMergeMDL') / path.relative_to(args.source))


def checksums(args):
    folder = Path(args.folder)
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.name != 'SHA256SUMS.txt')
    (folder / 'SHA256SUMS.txt').write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in files), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare'); p.add_argument('--work', required=True); p.add_argument('--force', action='store_true')
    p = commands.add_parser('source-archive'); p.add_argument('--source', required=True); p.add_argument('--output', required=True)
    p = commands.add_parser('package'); p.add_argument('--source', required=True); p.add_argument('--dist', required=True)
    p.add_argument('--platform', choices=['win64', 'linux64'], required=True); p.add_argument('--output', required=True)
    p.add_argument('--manifest', required=True)
    p = commands.add_parser('checksums'); p.add_argument('--folder', required=True)
    args = parser.parse_args()
    {'prepare': prepare, 'source-archive': source_archive, 'package': package, 'checksums': checksums}[args.command](args)
