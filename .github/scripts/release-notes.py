#!/usr/bin/env python3
"""Merge the section blocks out of every commit since the last release.

Commit bodies can use "<section>:" headers followed by "- " bullets. Compiler,
subtool and release changes are retained; ordinary commits use their subject.
"Bump version" bullets collapse to the newest one.
"""

import re
import sys

BULLET = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")
BUMP = re.compile(r"bump\s+version", re.I)
CI_MARKER = re.compile(r'\[(?:skip ci|ci skip|no ci|skip actions|actions skip)\]', re.I)

# lowercase header -> display name; unknown body sections are not release notes.
SECTIONS = {name: name for name in (
    "mdlcompiler", "mdldecompiler", "subtools", "platform", "release", "documentation",
)}

def render(log, seen_commits=()):
    sections = {}
    bumps = {}
    seen = set(seen_commits)

    def add(key, text):
        text = CI_MARKER.sub('', text).strip()
        if not text:
            return
        entry = sections.setdefault(key, [])
        if text not in entry:
            entry.append(text)

    # Commits arrive oldest-first, each preceded by a NUL.
    for commit in log.split("\0"):
        if '\x1f' in commit:
            sha, commit = commit.split('\x1f', 1)
            sha = sha.strip()
            if sha in seen:
                continue
            seen.add(sha)
        lines = commit.strip("\n").split("\n")
        if not any(line.strip() for line in lines):
            continue
        section = None
        recognized = False
        for line in lines[1:]:
            if not line.strip():
                continue
            match = BULLET.match(line)
            if match:
                if section is None:
                    continue
                recognized = True
                if BUMP.search(match.group(1)):
                    bumps[section] = CI_MARKER.sub('', match.group(1)).strip()
                else:
                    add(section, match.group(1))
            else:
                section = SECTIONS.get(line.strip().rstrip(":").lower())
        if not recognized:
            add('changes', lines[0].strip())

    for section, text in bumps.items():
        add(section, text)
    out = []
    for name, items in sections.items():
        if name != 'changes':
            out.append(f"**{name}:**")
        out.extend(f"- {item}" for item in items)
        out.append("")
    return "\n".join(out).strip() or "No changes."


if __name__ == '__main__':
    if len(sys.argv) < 2:
        log = sys.stdin.read()
    else:
        with open(sys.argv[1], encoding='utf-8') as stream:
            log = stream.read()
    print(render(log))
