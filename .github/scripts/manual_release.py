"""Allocate revision drafts using both tags and releases, and safely resume them."""
import argparse
import json
import re
import subprocess
from pathlib import Path
from publish_release import find_release, read_api


def choose_revision(version, head, tags, releases):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or not re.fullmatch(r'[0-9a-f]{40}', head):
        raise ValueError('Expected semantic version and full source commit SHA')
    pattern = re.compile(r'v' + re.escape(version) + r'-r([1-9]\d*)')
    occupied, resumable = set(), []
    for tag in tags:
        match = pattern.fullmatch(tag)
        if match:
            occupied.add(int(match[1]))
    for release in releases:
        match = pattern.fullmatch(release['tag_name'])
        if not match:
            continue
        revision = int(match[1])
        occupied.add(revision)
        if (release.get('draft') is True and release.get('target_commitish') == head
                and (release['tag_name'] not in tags or tags[release['tag_name']] == head)):
            resumable.append(revision)
    revision = max(resumable) if resumable else max(occupied, default=0) + 1
    return f'v{version}-r{revision}'


def releases(repository):
    result, page = [], 1
    while True:
        items = read_api(f'repos/{repository}/releases?per_page=100&page={page}')
        if not isinstance(items, list):
            raise ValueError('Expected a release list including drafts')
        result.extend(items)
        if len(items) < 100:
            return result
        page += 1


def ensure_draft(repository, tag, head, notes):
    existing = find_release(repository, tag, missing_ok=True)
    if existing is None:
        subprocess.run(['gh', 'release', 'create', tag, '--repo', repository,
                        '--target', head, '--title', 'NewPageMergeMDL ' + tag,
                        '--notes-file', str(notes), '--draft'], check=True)
    # Re-read after creation or retry. A foreign/published release is never
    # overwritten, including if another actor won the allocation race.
    current = find_release(repository, tag)
    if current.get('draft') is not True or current.get('target_commitish') != head:
        raise ValueError('Revision is no longer a draft for this exact source; retry allocation')
    return current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('choose', 'upload'))
    parser.add_argument('--repo', required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--version')
    parser.add_argument('--tag')
    parser.add_argument('--notes')
    parser.add_argument('--symbols', nargs=2, default=[],
                        metavar=('WINDOWS_SYMBOLS', 'LINUX_SYMBOLS'))
    parser.add_argument('assets', nargs='*')
    args = parser.parse_intermixed_args()
    if args.operation == 'choose':
        tags = {}
        for tag in subprocess.check_output(['git', 'tag', '--list'], text=True).splitlines():
            tags[tag] = subprocess.check_output(['git', 'rev-list', '-n', '1', tag], text=True).strip()
        print(choose_revision(args.version, args.head, tags, releases(args.repo)))
    else:
        if not args.tag or not args.notes or len(args.assets) != 2:
            parser.error('upload requires --tag, --notes and both platform ZIPs')
        args.assets.extend(args.symbols)
        if len({Path(asset).name for asset in args.assets}) != len(args.assets):
            parser.error('Asset filenames must be distinct')
        for asset in args.assets:
            if not Path(asset).is_file():
                parser.error('Missing asset: ' + asset)
        ensure_draft(args.repo, args.tag, args.head, args.notes)
        subprocess.run(['gh', 'release', 'upload', args.tag, '--repo', args.repo,
                        '--clobber', *args.assets], check=True)
        current = find_release(args.repo, args.tag)
        import hashlib
        for name in args.assets:
            digest = 'sha256:' + hashlib.sha256(Path(name).read_bytes()).hexdigest()
            matches = [a for a in current['assets'] if a['name'] == Path(name).name]
            if len(matches) != 1 or matches[0].get('digest') != digest:
                raise ValueError('Uploaded asset identity mismatch: ' + name)
        subprocess.run(['gh', 'release', 'edit', args.tag, '--repo', args.repo,
                        '--notes-file', args.notes], check=True)


if __name__ == '__main__':
    main()
