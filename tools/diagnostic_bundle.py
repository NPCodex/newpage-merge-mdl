"""Create a local, redacted diagnostic ZIP containing metadata and selected text logs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile
from output_transaction import Publication, different_paths


def redact(text):
    # Known token forms and common key/value log formats. No environment dump.
    text = re.sub(r'(?i)\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b', '<redacted-token>', text)
    text = re.sub(r'(?im)((?:authorization|password|passwd|token|api[_-]?key|secret)\s*[=:]\s*)([^\r\n]+)', r'\1<redacted>', text)
    text = re.sub(r'(?i)https?://[^\s/@]+:[^\s/@]+@', 'https://<redacted>@', text)
    # Absolute paths can disclose user and project names. Keep no directory names.
    text = re.sub(r'(?i)[A-Z]:[\\/][^\r\n\t"<>|]*', '<local-path>', text)
    text = re.sub(r'(?<![\w:/])/(?:home|Users|mnt|media|tmp|var|opt|workspace|workspaces)/[^\s"<>|]*', '<local-path>', text)
    user = os.environ.get('USERNAME') or os.environ.get('USER')
    if user and len(user) >= 3:
        text = re.sub(r'(?<!\w)' + re.escape(user) + r'(?!\w)', '<user>', text, flags=re.I)
    return text


def build(output, manifest, logs, compiler=None):
    inputs = [manifest, *logs] + ([compiler] if compiler else [])
    different_paths(inputs, [output])
    metadata = json.loads(manifest.read_text(encoding='utf-8-sig'))
    if not isinstance(metadata, dict):
        raise ValueError('Build manifest must be a JSON object')
    # Copy only identity fields, not arbitrary embedded application/user data.
    selected = {k: metadata[k] for k in ('project_version', 'controller_sha', 'fingerprint', 'release_tag', 'build') if k in metadata}
    if compiler:
        selected['executable_sha256'] = hashlib.sha256(compiler.read_bytes()).hexdigest()
    selected['schema'] = 1
    selected['contents'] = 'Build identity and explicit text logs only; no models, textures, settings or environment dump.'
    with Publication(inputs=inputs) as publication:
        publication.reserve(output)
        staged = publication.work / 'diagnostics.zip'
        with zipfile.ZipFile(staged, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('build.json', redact(json.dumps(selected, indent=2)))
            for index, path in enumerate(logs, 1):
                if path.suffix.lower() not in ('.txt', '.log'):
                    raise ValueError('Only explicitly selected .txt/.log files may be included')
                if path.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError('Log exceeds the 2 MiB per-file limit')
                text = path.read_text(encoding='utf-8-sig')
                if '\0' in text:
                    raise ValueError('Binary content is not a diagnostic text log')
                archive.writestr(f'logs/{index}.log', redact(text))
        publication.add(staged, output)
        publication.commit()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--log', type=Path, action='append', default=[])
    p.add_argument('--compiler', type=Path, help='Hash this executable; never include its bytes')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    build(a.output, a.manifest, a.log, a.compiler)
    print('Saved local diagnostics:', a.output)


if __name__ == '__main__':
    main()
