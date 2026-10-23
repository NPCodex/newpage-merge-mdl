"""Compare actual runtime bytes or every member of two independently built ZIPs."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(path):
    path = Path(path)
    if path.is_file():
        with zipfile.ZipFile(path) as archive:
            names = [i.filename for i in archive.infolist() if not i.is_dir()]
            if len(names) != len(set(names)):
                raise ValueError('Duplicate ZIP members')
            return {name: digest(archive.read(name)) for name in sorted(names)}
    result = {}
    for file in sorted(path.rglob('*')):
        if not file.is_file():
            continue
        if file.suffix.lower() in ('.debug', '.pdb'):
            continue  # Compared separately, including all bytes, in symbols.zip.
        with file.open('rb') as stream:
            magic = stream.read(4)
        if file.suffix.lower() == '.exe' or magic == b'\x7fELF':
            result[file.relative_to(path).as_posix()] = digest(file.read_bytes())
    if not result:
        raise ValueError('No executable artifacts in ' + str(path))
    return result


def compare(left, right):
    a, b = inventory(left), inventory(right)
    result = dict(schema=1, equal=a == b, entries=len(a),
                  missing=sorted(a.keys() - b.keys()), extra=sorted(b.keys() - a.keys()),
                  changed={name: {'left': a[name], 'right': b[name]} for name in sorted(a.keys() & b.keys()) if a[name] != b[name]})
    if Path(left).is_file() and Path(right).is_file():
        result['archive_bytes_equal'] = digest(Path(left).read_bytes()) == digest(Path(right).read_bytes())
        result['equal'] &= result['archive_bytes_equal']
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('left', type=Path)
    p.add_argument('right', type=Path)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    result = compare(a.left, a.right)
    a.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['equal'] else 1)
