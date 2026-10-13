#!/usr/bin/env python3
"""Publish verified packages as stable releases without moving Latest backward."""
import argparse
import json
import re
import subprocess

_MISSING = object()


def release_version(tag):
    match = re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)(?:-r(\d+))?', tag)
    if not match:
        raise ValueError('Unsupported project release tag: ' + str(tag))
    return tuple(int(part or 0) for part in match.groups())


def read_api(endpoint, missing_ok=False):
    result = subprocess.run(['gh', 'api', '--include', endpoint],
                            capture_output=True, text=True, check=False)
    header, separator, body = result.stdout.replace('\r\n', '\n').partition('\n\n')
    match = re.match(r'HTTP/\S+ (\d{3})(?:\s|$)', header)
    status = int(match[1]) if match else None
    # Only an actual HTTP 404 means absence. Authentication, transport and
    # server failures must never grant permission to replace Latest.
    if missing_ok and status == 404 and separator and result.returncode != 0:
        return _MISSING
    if result.returncode != 0 or status != 200 or not separator:
        raise RuntimeError(f'GitHub release query failed: {endpoint} '
                           f'(HTTP {status}, gh exit {result.returncode})')
    return json.loads(body)


def read_release(repository, suffix, missing_ok=False):
    endpoint = f'repos/{repository}/releases/{suffix}'
    value = read_api(endpoint, missing_ok=missing_ok)
    if value is _MISSING:
        return None
    if not isinstance(value, dict) or not isinstance(value.get('tag_name'), str):
        raise ValueError('Invalid GitHub release response: ' + endpoint)
    return value


def find_release(repository, tag, missing_ok=False):
    release = read_release(repository, 'tags/' + tag, missing_ok=True)
    if release is not None:
        if release['tag_name'] != tag:
            raise ValueError('GitHub returned a different release tag')
        return release
    # GitHub can return 404 for a draft via /tags even to an authenticated
    # publisher. Its release list includes drafts, and /<id> can read them.
    page = 1
    while True:
        endpoint = f'repos/{repository}/releases?per_page=100&page={page}'
        releases = read_api(endpoint)
        if not isinstance(releases, list):
            raise ValueError('Invalid GitHub release list: ' + endpoint)
        for item in releases:
            if not isinstance(item, dict) or not isinstance(item.get('tag_name'), str):
                raise ValueError('Invalid GitHub release list entry: ' + endpoint)
            if item['tag_name'] != tag:
                continue
            identifier = item.get('id')
            if type(identifier) is not int or identifier <= 0:
                raise ValueError('Invalid GitHub release ID for ' + tag)
            release = read_release(repository, str(identifier))
            if (release['tag_name'] != tag or type(release.get('id')) is not int
                    or release['id'] != identifier):
                raise ValueError('GitHub returned a different release tag or ID')
            return release
        if len(releases) < 100:
            if missing_ok:
                return None
            raise ValueError('GitHub release does not exist: ' + tag)
        page += 1


def create_draft(repository, tag, target, notes):
    release_version(tag)
    existing = find_release(repository, tag, missing_ok=True)
    if existing is not None:
        return
    # A retry leaves an existing release's draft/stable state untouched.
    subprocess.run(['gh', 'release', 'create', tag, '--repo', repository,
                    '--target', target, '--title', 'NewPageMergeMDL ' + tag,
                    '--notes-file', str(notes), '--draft'], check=True)


def publish(repository, tag, notes):
    version = release_version(tag)
    find_release(repository, tag)
    latest = read_release(repository, 'latest', missing_ok=True)
    promote = latest is None or version >= release_version(latest['tag_name'])
    # Never rely on GitHub's publication-time heuristic: an old forced retry
    # remains stable while a higher project version keeps the Latest badge.
    subprocess.run(['gh', 'release', 'edit', tag, '--repo', repository,
                    '--draft=false', '--prerelease=false',
                    '--latest=' + str(promote).lower(),
                    '--notes-file', str(notes)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('draft', 'publish'))
    parser.add_argument('--repo', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--notes-file', required=True)
    parser.add_argument('--target', help='Required when creating a draft')
    args = parser.parse_args()
    if args.operation == 'draft':
        if not args.target:
            parser.error('--target is required for draft')
        create_draft(args.repo, args.tag, args.target, args.notes_file)
    else:
        publish(args.repo, args.tag, args.notes_file)


if __name__ == '__main__':
    main()
