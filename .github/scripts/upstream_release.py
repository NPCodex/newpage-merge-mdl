#!/usr/bin/env python3
"""Fetch upstream versions, apply maintained source patches, stage tested releases.

Closed-source downloads are reference inputs only and are never redistributed.
All URLs come from configured official GitHub repositories, not release-body text.
"""
import argparse
import datetime
import time
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def build_record_time():
    epoch = os.environ.get('SOURCE_DATE_EPOCH')
    return (datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc) if epoch is not None
            else datetime.datetime.now(datetime.timezone.utc)).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def source_text_sha256(data):
    """Only source identity ignores CRLF; asset/inventory hashes remain raw."""
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def checked_source_text_hash(data, declared, label):
    canonical = data.replace(b'\r\n', b'\n')
    equivalents = {hashlib.sha256(value).hexdigest() for value in
                   (data, canonical, canonical.replace(b'\n', b'\r\n'))}
    if declared not in equivalents:
        raise ValueError('Source snapshot does not match declared ' + label)
    return source_text_sha256(data)


RELEASE_INPUT_ROOTS = ('libs', 'mdlcompiler', 'mdldecompiler', 'subtools', 'cmake',
                       'tools', 'integration', 'assets/branding', '.github/images')
RELEASE_INPUT_FILES = ('CMakeLists.txt', 'CMakePresets.json', 'utf8.manifest', 'LICENSE',
                       'automation/upstreams.json', 'automation/windows-extras.json',
                       'automation/linux-runtime.json')
RELEASE_TEXT_SUFFIXES = {'.c', '.cc', '.cpp', '.cxx', '.h', '.hh', '.hpp', '.hxx', '.inc', '.inl', '.ipp',
                         '.cmake', '.txt', '.json', '.py', '.lua', '.rc', '.manifest', '.xml', '.def',
                         '.in', '.m', '.mm', '.natvis', '.props', '.targets', '.sln', '.vcxproj',
                         '.sh', '.bat', '.ps1', '.md', '.rst', '.license', '.cs', '.csproj', '.build', '.s', '.kv3'}


def is_release_input(name):
    path = PurePosixPath(name)
    if any(part in {'.git', '__pycache__', 'build', 'out', 'dist'} for part in path.parts):
        return False
    if path.suffix.lower() in {'.pyc', '.pyo'}:
        return False
    if name not in RELEASE_INPUT_FILES and not any(name.startswith(root + '/') for root in RELEASE_INPUT_ROOTS):
        return False
    # Documentation and acceptance evidence can follow a release without
    # changing its tools. License notices remain distribution inputs.
    notice = any(word in path.name.lower() for word in ('license', 'copying', 'notice'))
    if not notice and (path.suffix.lower() in {'.md', '.rst'} or path.name.lower().startswith('readme')
                       or any(part in {'test', 'tests'} for part in path.parts)):
        return False
    return True


def release_inputs_fingerprint(files, pulsemodel):
    identity = []
    for name, data in files:
        if is_release_input(name):
            # Normalize known source text across checkouts. Unknown/binary
            # resources retain exact bytes even when they contain no NUL.
            path = PurePosixPath(name)
            text = (path.suffix.lower() in RELEASE_TEXT_SUFFIXES or
                    path.name.lower() in {'makefile', 'license', 'copying', 'notice'})
            canonical = data.replace(b'\r\n', b'\n') if text and b'\0' not in data[:8000] else data
            identity.append((name, hashlib.sha256(canonical).hexdigest()))
    return fingerprint({'schema': 1, 'pulsemodel': pulsemodel, 'files': sorted(identity)})


def checkout_release_inputs(source, pulsemodel):
    source = Path(source)
    if (source / '.git').exists():
        # Maintained packages use git archive; ignored SDK/build leftovers are
        # not inputs to those packages. Still read working bytes for tracked edits.
        tracked = subprocess.check_output(['git', 'ls-files', '-z', '--',
                                          *RELEASE_INPUT_ROOTS, *RELEASE_INPUT_FILES], cwd=source)
        paths = set(tracked.decode('utf-8').rstrip('\0').split('\0')) - {''}
    else:
        paths = set(RELEASE_INPUT_FILES)
        for root in RELEASE_INPUT_ROOTS:
            paths.update(path.relative_to(source).as_posix() for path in (source / root).rglob('*') if path.is_file())
    return release_inputs_fingerprint(((name, (source / name).read_bytes()) for name in sorted(paths)
                                       if is_release_input(name) and (source / name).is_file()), pulsemodel)


def same_release_inputs(previous, provenance_fingerprint, release_inputs_sha256=None):
    if not previous:
        return False
    if release_inputs_sha256 is not None and previous.get('release_inputs_sha256') is not None:
        return previous['release_inputs_sha256'] == release_inputs_sha256
    # Unverifiable legacy snapshots retain the old conservative comparison.
    return previous.get('fingerprint') == provenance_fingerprint


def verified_package_manifest(package, manifest):
    """Migrate historical text hashes only when the embedded source proves it.

    Maintained source is unstamped and can verify both controller input hashes.
    A merged snapshot has a refreshed overlay and stamped configuration: only
    its build_overlay hash is directly verifiable. Its original controller
    overlay/config declarations must continue to agree exactly across platforms.
    """
    source_name = 'NewPageMergeMDL/sources/NewPageMergeMDL-source.zip'
    if source_name not in package.namelist():
        legacy = dict(manifest)
        legacy.pop('release_inputs_sha256', None)
        return legacy  # Legacy packages retain strict manifest equality.
    result = dict(manifest)
    controller = manifest.get('controller_sha', '')
    if not isinstance(controller, str) or not re.fullmatch(r'[0-9a-f]{40}', controller):
        raise ValueError('Invalid source snapshot controller commit')
    text_paths = {'automation/compatibility.patch', 'automation/upstreams.json'}
    with zipfile.ZipFile(io.BytesIO(package.read(source_name))) as source:
        if source.comment and source.comment != controller.encode('ascii'):
            raise ValueError('Source archive comment does not match controller commit')
        files, identity = {}, []
        for info in source.infolist():
            path = PurePosixPath(info.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in info.filename or ':' in info.filename
                    or not path.parts or path.parts[0] != 'NewPageMergeMDL'):
                raise ValueError('Unsafe source archive member: ' + info.filename)
            if info.is_dir():
                continue
            relative = path.relative_to('NewPageMergeMDL').as_posix()
            if relative in files:
                raise ValueError('Duplicate source archive member: ' + relative)
            data = source.read(info)
            files[relative] = data
            # All other source and binary files are compared byte-for-byte.
            value = data.replace(b'\r\n', b'\n') if relative in text_paths else data
            identity.append((relative, hashlib.sha256(value).hexdigest()))
        result['_verified_source_tree_sha256'] = fingerprint(sorted(identity))
        required_files = ('CMakeLists.txt', 'automation/compatibility.patch', 'automation/upstreams.json')
        if any(path not in files for path in required_files):
            raise ValueError('Source snapshot is missing required identity files')
        payload_keys = ('schema', 'controller_sha', 'overlay_sha256', 'configuration_sha256', 'pulsemodel', 'integration')
        if any(key not in manifest for key in (*payload_keys, 'project_version', 'fingerprint')):
            raise ValueError('Source manifest is missing required identity fields')
        payload = {key: manifest[key] for key in payload_keys}
        payload['project_version'] = manifest.get('version_base', manifest['project_version'])
        if manifest['fingerprint'] != fingerprint(payload):
            raise ValueError('Declared source fingerprint does not match its identity fields')
        version = re.search(rb'project\(NewPageMergeMDL VERSION ([0-9.]+)', files['CMakeLists.txt'])
        if not version or version[1].decode('ascii') != manifest['project_version']:
            raise ValueError('Source snapshot CMake version does not match manifest')
        if manifest.get('source_kind') == 'maintained checkout':
            for field, path in (('overlay_sha256', 'automation/compatibility.patch'),
                                ('configuration_sha256', 'automation/upstreams.json')):
                payload[field] = result[field] = checked_source_text_hash(files[path], manifest[field], field)
            config = json.loads(files['automation/upstreams.json'])
            if (config.get('pulsemodel') != manifest['pulsemodel']['repo'] or
                    config.get('pulse_base') != manifest['pulsemodel']['sha'] or
                    config.get('project_version', '1.2.0') != payload['project_version']):
                raise ValueError('Source snapshot configuration does not match maintained manifest')
            result['fingerprint'] = fingerprint(payload)
            content = release_inputs_fingerprint(files.items(), result['pulsemodel'])
            if manifest.get('release_inputs_sha256', content) != content:
                raise ValueError('Source snapshot does not match declared release inputs')
            result['release_inputs_sha256'] = content
        elif 'release_inputs_sha256' in manifest:
            # Automatic packages retain their original controller input hash.
            # Their merged snapshot already has newer upstream code and stamped
            # versions; recomputing from it would cause perpetual new releases.
            content = manifest['release_inputs_sha256']
            if not isinstance(content, str) or not re.fullmatch(r'[0-9a-f]{64}', content):
                raise ValueError('Invalid controller release input hash')
        if manifest.get('build_overlay_sha256') is not None:
            result['build_overlay_sha256'] = checked_source_text_hash(
                files['automation/compatibility.patch'], manifest['build_overlay_sha256'], 'build_overlay_sha256')
    return result


def package_source_identity(manifest):
    fields = ('controller_sha', 'fingerprint', 'project_version', 'pulsemodel',
              'overlay_sha256', 'configuration_sha256', 'build_overlay_sha256', 'source_kind',
              '_verified_source_tree_sha256', 'release_inputs_sha256')
    return json.dumps({key: manifest.get(key) for key in fields}, sort_keys=True)


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
                                  re.fullmatch(r'v\d+\.\d+(?:\.\d+)?(?:-auto-[\w-]+|-r\d+)?', release['tag_name'])):
            continue
        # Installed packages take precedence over obsolete standalone manifests.
        # Read both platforms: different source identities cannot safely drive
        # automatic version selection from an arbitrary platform's snapshot.
        packages = sorted((a for a in release['assets']
                           if re.search(r'-(?:linux64|win64)\.zip$', a['name'], re.I)),
                          key=lambda a: ('linux64' not in a['name'].lower(), a['name']))
        current = {platform: [a for a in packages if a['name'] == 'newpage-merge-mdl-' + platform + '.zip']
                   for platform in ('linux64', 'win64')}
        packages = [a for a in packages if not current['linux64' if 'linux64' in a['name'].lower() else 'win64']
                    or a in current['linux64' if 'linux64' in a['name'].lower() else 'win64']]
        manifests = []
        for asset in packages:
            data = fetch(asset['url'], accept='application/octet-stream')
            if asset.get('digest') and asset['digest'] != 'sha256:' + hashlib.sha256(data).hexdigest():
                raise ValueError('Published package digest mismatch: ' + asset['name'])
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if 'NewPageMergeMDL/upstream-manifest.json' not in archive.namelist():
                    continue
                manifest = json.loads(archive.read('NewPageMergeMDL/upstream-manifest.json'))
                manifest = verified_package_manifest(archive, manifest)
                manifest['build_tag'] = manifest.get('release_tag')
                manifest['release_tag'] = release['tag_name']
                manifests.append(manifest)
        if manifests:
            identities = {package_source_identity(m) for m in manifests}
            if len(identities) != 1:
                raise ValueError('Published platform packages have different source identities: ' + release['tag_name'])
            return manifests[0]
        for asset in release['assets']:
            if asset['name'] == 'upstream-manifest.json':
                # Legacy releases without embedded provenance remain readable.
                manifest = json.loads(fetch(asset['url'], accept='application/octet-stream'))
                manifest.pop('release_inputs_sha256', None)
                manifest['build_tag'] = manifest.get('release_tag')
                manifest['release_tag'] = release['tag_name']
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
        ':(exclude)libs/assimp/**', ':(exclude)libs/tinyusdz/**',
        ':(exclude)libs/cgltf/cgltf.h', cwd=root)


def release_version(base, previous, content_fingerprint, release_inputs_sha256=None):
    """Allocate a patch release, preserving the identity of forced retries."""
    def parts(value):
        if not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', value):
            raise ValueError('Invalid project version: ' + value)
        return tuple(map(int, (value + '.0' if value.count('.') == 1 else value).split('.')))
    floor = parts(base)
    if same_release_inputs(previous, content_fingerprint, release_inputs_sha256):
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


def release_changes(state, previous, repository):
    """Record only the revisions introduced since the preceding package.

    PulseModel is a default-branch source revision, not an upstream stable or
    preview release. CE/Tools++ are reference metadata and never feature notes.
    """
    previous = previous or {}
    sources = (
        ('NewPage', repository, previous.get('controller_sha'), state['controller_sha']),
        ('PulseModel 默认分支源码', state['pulsemodel']['repo'],
         previous.get('pulsemodel', {}).get('sha'), state['pulsemodel']['sha']),
    )
    changes = []
    for label, repo, before, after in sources:
        if before == after:
            continue
        change = dict(label=label, repository=repo, before=before, after=after)
        changes.append(change)
        if not repo or not before:
            change['status'] = 'baseline-unavailable'
            continue
        change['url'] = f'https://github.com/{repo}/compare/{before}...{after}'
        try:
            comparison = api(f'repos/{repo}/compare/{before}...{after}?per_page=100')
            change['status'] = comparison['status']
            change['total_commits'] = comparison['total_commits']
            change['subjects'] = [commit['commit']['message'].splitlines()[0]
                                  for commit in comparison['commits']]
        except (urllib.error.URLError, TimeoutError, KeyError, TypeError, ValueError):
            # A release-note lookup is not evidence of an empty source diff.
            change['status'] = 'comparison-unavailable'
    return changes


def concise_release_notes(changes):
    """Human-facing deltas only; full revisions and references stay in manifest."""
    def plain(value):
        # Commit subjects are display data. Prevent Markdown/HTML formatting.
        value = ' '.join(str(value).split())[:180]
        return re.sub(r'([\\`*_{}\[\]<>])', r'\\\1', value)

    lines = []
    for change in changes:
        label = change['label']
        if change['status'] == 'baseline-unavailable':
            lines.append(f'- {label}：首次记录构建来源，无法确认相对上一发行包的变更。')
            continue
        link = f"[提交差异]({change['url']})"
        if change['status'] == 'comparison-unavailable':
            lines.append(f'- {label}：源码版本已变化，具体变更暂未核实（{link}）。')
            continue
        subjects = change.get('subjects', [])
        for subject in subjects[:5]:
            lines.append(f'- {label}：{plain(subject)}')
        if change['status'] != 'ahead':
            lines.append(f'- {label}：源码历史已变化（{link}）。')
        elif len(subjects) > 5 or change.get('total_commits', 0) > len(subjects):
            lines.append(f'- {label}：共 {change["total_commits"]} 项提交，完整内容见{link}。')
        elif subjects:
            lines.append(f'\n{label}：{link}')
    if not lines:
        return '按现有源码重新构建；没有新增源码提交。\n'
    return '\n'.join(lines).strip() + '\n'


def append_release_notes(previous, current, tag, source_sha=None):
    """Preserve earlier change entries while replacing obsolete ZIP digests."""
    previous = previous.replace('\r\n', '\n')
    previous = re.sub(
        r'(?im)^[ \t]*(?:#{1,6}[ \t]+)?ZIP SHA-?256:[ \t]*\n\s*```(?:text)?[ \t]*\n'
        r'(?:[a-f0-9]{64}[ \t]+[^\n]+\n)+```[ \t]*(?:\n|$)', '', previous).strip()
    if previous:
        # A replacement tag deliberately stays fixed. Retrying publication must
        # not append its entire commit range or duplicate an earlier bullet.
        previous_bullets = {line.strip() for line in previous.splitlines() if line.lstrip().startswith(('- ', '* '))}
        blocks = []
        for block in current.strip().split('\n\n'):
            lines = block.splitlines()
            lines = [line for line in lines if line.strip() not in previous_bullets]
            if lines and not (len(lines) == 1 and lines[0].startswith('**') and lines[0].endswith('**')):
                blocks.append('\n'.join(lines))
        current = '\n\n'.join(blocks)
        marker = '<!-- newpage-source:' + source_sha + ' -->' if source_sha else None
        if marker and marker in previous:
            # Keep the previously reviewed prose; only refresh the digests.
            checksum = re.search(r'(?ims)^ZIP SHA-?256:.*$', current)
            return previous + ('\n\n' + checksum[0] if checksum else '')
        if not current:
            return previous
        if marker:
            current += '\n\n' + marker
        visible = re.sub(r'<!--.*?-->', '', current, flags=re.S)
        visible = re.sub(r'(?ims)^ZIP SHA-?256:.*$', '', visible).strip()
        heading = '\n\n## ' + tag + ' 后续更新' if visible else ''
        return previous + heading + '\n\n' + current.lstrip()
    if source_sha:
        return current.rstrip() + '\n\n<!-- newpage-source:' + source_sha + ' -->\n'
    return current


def source_state(config, controller, pulse_revision, source):
    """Canonical rebuild identity shared by maintained and upstream packages."""
    source = Path(source)
    state = {
        'schema': 1,
        'project_version': config.get('project_version', '1.2.0'),
        'controller_sha': controller,
        'overlay_sha256': source_text_sha256((source / 'automation/compatibility.patch').read_bytes()),
        'configuration_sha256': source_text_sha256((source / 'automation/upstreams.json').read_bytes()),
        'pulsemodel': {'repo': config['pulsemodel'], 'sha': pulse_revision},
        'integration': {
            'pulsemodel': 'source patch overlay',
            'studiomdl_ce': 'reference download; new functionality not automatically ported',
            'studiomdl_plusplus': 'reference download; new functionality not automatically ported'
        }
    }
    state['fingerprint'] = fingerprint(state)
    state['release_inputs_sha256'] = checkout_release_inputs(source, state['pulsemodel'])
    return state


def maintained_manifest(args):
    source = Path(args.source).resolve()
    config = json.loads((source / 'automation/upstreams.json').read_text(encoding='utf-8'))
    controller = os.environ.get('GITHUB_SHA') or subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    version = re.search(r'project\(NewPageMergeMDL VERSION ([0-9.]+)',
                        (source / 'CMakeLists.txt').read_text(encoding='utf-8'))[1]
    state = source_state(config, controller, config['pulse_base'], source)
    state.update(version_base=state['project_version'], project_version=version,
                 release_tag=args.tag, source_kind='maintained checkout',
                 generated_utc=build_record_time())
    Path(args.output).write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')


def prepare(args):
    config = json.loads((ROOT / 'automation/upstreams.json').read_text())
    overlay = ROOT / 'automation/compatibility.patch'
    controller = os.environ.get('GITHUB_SHA') or subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    state = source_state(config, controller, latest_commit(config['pulsemodel']), ROOT)
    previous = published_manifest(os.environ.get('GITHUB_REPOSITORY'))
    base_version = state['project_version']
    state['project_version'], tag = release_version(base_version, previous, state['fingerprint'],
                                                  state['release_inputs_sha256'])
    state['version_base'] = base_version
    state['release_tag'] = tag
    if same_release_inputs(previous, state['fingerprint'], state['release_inputs_sha256']) and not args.force:
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
    for name in ('.github', 'automation', 'tests', 'integration', 'tools', 'assets/branding'):
        target = candidate / name
        if target.exists():
            if candidate.resolve() not in target.resolve().parents:
                raise ValueError('Controller target escapes candidate')
            shutil.rmtree(target)
        shutil.copytree(ROOT / name, candidate / name, dirs_exist_ok=True)
    for name in ('README.md', 'README.en.md', 'INSTALL.md', 'UPSTREAM_README.md', 'COMPATIBILITY.md', 'BINARY_ANALYSIS.md', 'AUTOMATION.md', 'RESEARCH.md', 'VALIDATION.md', 'IMPROVEMENTS.md', 'FEATURE_MATRIX.md', 'AGENTS.md', '.gitignore'):
        shutil.copy2(ROOT / name, candidate / name)
    stamp_version(candidate, base_version, state['project_version'])
    for name in ('CSGO_PORTING_SCOPE.md', 'CSGO_CLOTH_AUTHORING.md', 'CSGO_DMX_INPUTS.md',
                 'FIVE_COMPILER_COMPLETION.md', 'MESH_STATE_WORKFLOW.md', 'VRM_RUNTIME.md', 'O5_FORMAT_IMPORTS.md',
                 'AUTHORING_WORKFLOWS.md', 'DECOMPILER_EXPORTS.md', 'SCENE_IMPORT.md', 'GAME_PLATFORM_MATRIX.md'):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, candidate / name)
    run(sys.executable, candidate / '.github/scripts/refresh_overlay.py', '--base-repository', candidate)
    state['build_overlay_sha256'] = source_text_sha256((candidate / 'automation/compatibility.patch').read_bytes())
    state['generated_utc'] = build_record_time()
    state['release_changes'] = release_changes(state, previous, os.environ.get('GITHUB_REPOSITORY'))
    (work / 'upstream-manifest.json').write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    notes = concise_release_notes(state['release_changes'])
    (work / 'release-notes.md').write_text(notes, encoding='utf-8')
    emit(changed=True, tag=tag)


class ReproducibleZipFile(zipfile.ZipFile):
    """Stable entry metadata; exact file bytes and explicit ELF modes are retained."""
    def writestr(self, zinfo_or_arcname, data, compress_type=None, compresslevel=None):
        info = zinfo_or_arcname if isinstance(zinfo_or_arcname, zipfile.ZipInfo) else zipfile.ZipInfo(zinfo_or_arcname)
        epoch = max(315532800, int(os.environ.get('SOURCE_DATE_EPOCH', '315532800')))
        info.date_time = time.gmtime(epoch)[:6]
        info.create_system = 3
        info.external_attr = (0o40755 if info.is_dir() else 0o100644) << 16
        info.compress_type = self.compression if compress_type is None else compress_type
        level = getattr(self, 'compresslevel', getattr(self, '_compresslevel', 9))
        return super().writestr(info, data, compress_type, level if compresslevel is None else compresslevel)

    def write(self, filename, arcname=None, compress_type=None, compresslevel=None):
        path = Path(filename)
        name = str(arcname if arcname is not None else filename).replace('\\', '/')
        self.writestr(name, path.read_bytes(), compress_type, compresslevel)


def source_archive(args):
    source, destination = Path(args.source), Path(args.output)
    with ReproducibleZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob('*')):
            relative = path.relative_to(source)
            if path.is_file() and not any(p in {'.git', '__pycache__', 'build', 'out', 'dist'} for p in relative.parts):
                archive.write(path, (Path('NewPageMergeMDL') / relative).as_posix())


def record_build(args):
    """Record the configuration actually selected, including IPO fallback."""
    cache = {}
    for line in Path(args.cache).read_text(encoding='utf-8').splitlines():
        match = re.match(r'([^#/:][^:]*):[^=]+=(.*)$', line)
        if match:
            cache[match[1]] = match[2]
    compiler = cache.get('NEWPAGE_BUILD_CXX_COMPILER') or cache.get('CMAKE_CXX_COMPILER')
    if not compiler or 'CMAKE_INTERPROCEDURAL_OPTIMIZATION' not in cache:
        raise ValueError('Build cache must identify its compiler and explicit IPO setting')
    manifest = Path(args.manifest)
    state = json.loads(manifest.read_text(encoding='utf-8'))
    state['build'] = {
        'configuration': args.configuration,
        'c_compiler': cache.get('NEWPAGE_BUILD_C_COMPILER') or cache.get('CMAKE_C_COMPILER'),
        'cxx_compiler': compiler,
        'compiler_id': cache.get('NEWPAGE_BUILD_CXX_COMPILER_ID'),
        'compiler_version': cache.get('NEWPAGE_BUILD_CXX_COMPILER_VERSION'),
        'interprocedural_optimization': cache['CMAKE_INTERPROCEDURAL_OPTIMIZATION'].upper() in ('ON', 'TRUE', '1', 'YES'),
        'reproducible': cache.get('NEWPAGE_REPRODUCIBLE', 'OFF').upper() in ('ON', 'TRUE', '1', 'YES'),
        'separate_symbols': cache.get('NEWPAGE_SEPARATE_SYMBOLS', 'OFF').upper() in ('ON', 'TRUE', '1', 'YES'),
        'source_date_epoch': os.environ.get('SOURCE_DATE_EPOCH'),
    }
    manifest.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')


def write_inventory(archive):
    """Hash every payload entry; the inventory deliberately excludes itself."""
    entries = archive.infolist()
    if len({entry.filename for entry in entries}) != len(entries):
        raise ValueError('Duplicate package entries')
    lines = []
    for entry in sorted(entries, key=lambda item: item.filename):
        if entry.is_dir():
            continue
        digest = hashlib.sha256()
        with archive.open(entry) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        lines.append(digest.hexdigest() + '  ' + entry.filename.removeprefix('NewPageMergeMDL/') + '\n')
    archive.writestr('NewPageMergeMDL/SHA256SUMS.txt', ''.join(lines))


def package(args):
    dist, output = Path(args.dist), Path(args.output)
    # Linux subtools are extensionless files, so their source directories cannot
    # also exist in the runtime package. Keep guides beside those executables.
    guide_paths = {
        'subtools/ag2proportions/README.md': 'subtools/ag2proportions.md',
        'subtools/vmd2valvebiped/README.md': 'subtools/vmd2valvebiped.md',
        'subtools/l4d_animswap/RETARGET.md': 'subtools/l4d_animswap-retarget.md',
    }

    def write_source(archive, relative):
        relative = Path(relative).as_posix()
        path = Path(args.source) / relative
        target = guide_paths.get(relative, relative)
        if path.suffix == '.md':
            content = path.read_text(encoding='utf-8')
            for original, packaged in guide_paths.items():
                content = content.replace(original, packaged)
            if target != relative:
                content = content.replace('](../../', '](../')
            archive.writestr('NewPageMergeMDL/' + target, content)
        else:
            archive.write(path, 'NewPageMergeMDL/' + target)

    extension = '.exe' if args.platform == 'win64' else ''
    required = ['NewPageMergeMDL', 'NewPageMergeMDL-Decompiler', 'NewPageVRMLtoX3D']
    if args.platform == 'win64':
        required.append('NewPageMergeMDL-C4D')
    required.extend('subtools/' + name for name in ('ag2proportions', 'l4d_animswap', 'meshtool', 'vmd2valvebiped'))
    for name in required:
        if not (dist / (name + extension)).is_file():
            raise ValueError('Missing required executable: ' + name)
    for name in ('subtools/licenses/zstd.txt', 'subtools/licenses/ValveResourceFormat.txt'):
        notice = dist / name
        if not notice.is_file() or notice.stat().st_size == 0:
            raise ValueError('Missing or empty required ag2proportions license: ' + name)
    with ReproducibleZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(dist.rglob('*')):
            if path.is_file() and path.suffix.lower() not in ('.pdb', '.debug', '.ilk'):
                name = (Path('NewPageMergeMDL') / path.relative_to(dist)).as_posix()
                archive.write(path, name)
                if args.platform == 'linux64':
                    with path.open('rb') as stream:
                        is_elf = stream.read(4) == b'\x7fELF'
                    if is_elf:
                        # Repacking a Linux release on Windows must retain
                        # runnable Unix permissions in its central directory.
                        info = archive.getinfo(name)
                        info.create_system = 3
                        info.external_attr = 0o100755 << 16
        for name in ('LICENSE', 'README.md', 'README.en.md', 'INSTALL.md', 'COMPATIBILITY.md', 'BINARY_ANALYSIS.md', 'AUTOMATION.md', 'RESEARCH.md', 'VALIDATION.md', 'IMPROVEMENTS.md', 'FEATURE_MATRIX.md'):
            write_source(archive, name)
        archive.write(Path(args.source) / 'subtools/meshtool/PROTOCOL.md',
                      'NewPageMergeMDL/subtools/meshtool-protocol.md')
        for name in ('subtools/ag2proportions/README.md', 'subtools/vmd2valvebiped/README.md',
                     'subtools/l4d_animswap/RETARGET.md'):
            path = Path(args.source) / name
            if path.is_file():
                write_source(archive, name)
        archive.write(args.manifest, 'NewPageMergeMDL/upstream-manifest.json')
        # Keep README previews usable after extraction and retain the editable
        # brand source. Do not bundle workflow files with the runtime tools.
        for name in ('.github/images/newpage-compiler.png', '.github/images/newpage-decompiler.png',
                     'assets/branding/NewPage-logo.png', 'assets/branding/generate_icons.py',
                     'assets/branding/README.md'):
            path = Path(args.source) / name
            if path.is_file():
                archive.write(path, 'NewPageMergeMDL/' + name)
        if getattr(args, 'source_archive', None):
            archive.write(args.source_archive, 'NewPageMergeMDL/sources/NewPageMergeMDL-source.zip')
        for name in ('CSGO_PORTING_SCOPE.md', 'CSGO_CLOTH_AUTHORING.md', 'CSGO_DMX_INPUTS.md',
                     'FIVE_COMPILER_COMPLETION.md', 'MESH_STATE_WORKFLOW.md', 'VRM_RUNTIME.md', 'O5_FORMAT_IMPORTS.md',
                     'AUTHORING_WORKFLOWS.md', 'DECOMPILER_EXPORTS.md', 'SCENE_IMPORT.md', 'GAME_PLATFORM_MATRIX.md'):
            if (Path(args.source) / name).is_file():
                write_source(archive, name)
        for path in sorted((Path(args.source) / 'tests/reports').glob('*')):
            if path.is_file() and path.suffix in ('.json', '.md'):
                write_source(archive, 'tests/reports/' + path.name)
        for path in sorted((Path(args.source) / 'integration').rglob('*')):
            if path.is_file():
                archive.write(path, (Path('NewPageMergeMDL') / path.relative_to(args.source)).as_posix())

        # tinyusdz is statically compiled into Assimp: its source and developer
        # images are not runtime dependencies. Keep its complete binary notices,
        # including the licenses otherwise embedded only inside source headers.
        # The full source remains in Git and in automatic builds' source archive.
        for name in ('LICENSE', 'LICENSE-APACHE-2.0', 'SOURCE.md', 'THIRD_PARTY_NOTICES.md'):
            path = Path(args.source) / 'libs/tinyusdz' / name
            archive.write(path, 'NewPageMergeMDL/libs/tinyusdz/' + name)
        # The standalone GPL VRML converter's corresponding source and build
        # files, including its pugixml dependency, must stay in the binary ZIP.
        for folder in ('tools', 'libs/assimp/contrib/pugixml'):
            for path in sorted((Path(args.source) / folder).rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                    archive.write(path, (Path('NewPageMergeMDL') / path.relative_to(args.source)).as_posix())
        # Preserve bundled third-party license notices.
        for path in sorted((Path(args.source) / 'libs').rglob('*')):
            nv_notice = path.parent.name in {'nvtristrip', 'meshoptimizer'} and path.name in {'README.txt', 'SOURCE.md'}
            if path.is_file() and 'pugixml' not in path.parts and 'tinyusdz' not in path.parts and ('license' in path.name.lower() or 'copying' in path.name.lower() or nv_notice):
                archive.write(path, (Path('NewPageMergeMDL') / path.relative_to(args.source)).as_posix())
    # Reopen after writing: Windows ZipInfo.from_file retains a backslash
    # orig_filename until the central directory is read back from disk.
    with ReproducibleZipFile(output, 'a', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        write_inventory(archive)


def checksums(args):
    folder = Path(args.folder)
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.name != 'SHA256SUMS.txt')
    (folder / 'SHA256SUMS.txt').write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in files), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare'); p.add_argument('--work', required=True); p.add_argument('--force', action='store_true')
    p = commands.add_parser('source-archive'); p.add_argument('--source', required=True); p.add_argument('--output', required=True)
    p = commands.add_parser('maintained-manifest')
    p.add_argument('--source', default='.'); p.add_argument('--output', required=True)
    p.add_argument('--tag', required=True)
    p = commands.add_parser('record-build')
    p.add_argument('--manifest', required=True); p.add_argument('--cache', required=True)
    p.add_argument('--configuration', required=True)
    p = commands.add_parser('package'); p.add_argument('--source', required=True); p.add_argument('--dist', required=True)
    p.add_argument('--platform', choices=['win64', 'linux64'], required=True); p.add_argument('--output', required=True)
    p.add_argument('--manifest', required=True)
    p.add_argument('--source-archive', help='Exact merged build input for automatic upstream releases')
    p = commands.add_parser('checksums'); p.add_argument('--folder', required=True)
    args = parser.parse_args()
    {'prepare': prepare, 'source-archive': source_archive, 'maintained-manifest': maintained_manifest, 'record-build': record_build,
     'package': package, 'checksums': checksums}[args.command](args)
