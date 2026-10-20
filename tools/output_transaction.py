"""Stage authoring-helper outputs and roll back ordinary publication failures.

The native compiler receives a private -OutDir. Only this publication step may
replace the user's model, its companions, generated sources and runtime JSON.
This is not a power-loss or forced-process-termination recovery protocol.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile


def key(path):
    return os.path.normcase(str(Path(path).resolve()))


def different_paths(inputs, outputs):
    for source in inputs:
        for output in outputs:
            if key(source) == key(output) or (Path(source).exists() and Path(output).exists()
                                              and os.path.samefile(source, output)):
                raise ValueError('input and generated output paths must differ: ' + str(output))


def fingerprint(path):
    if path.is_symlink():
        raise ValueError('refusing a symbolic-link output: ' + str(path))
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError('output is not a regular file: ' + str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.digest()


def model_checksum(path, suffix):
    if not path.is_file():
        return None
    with path.open('rb') as stream:
        data = stream.read(20)
    if suffix == '.mdl' and len(data) >= 12 and data[:4] == b'IDST' and struct.unpack_from('<I', data, 4)[0] in (48, 49):
        return struct.unpack_from('<I', data, 8)[0]
    if suffix == '.vvd' and len(data) >= 12 and data[:4] == b'IDSV':
        return struct.unpack_from('<I', data, 8)[0]
    if suffix in ('.vtx', '.dx90.vtx', '.dx80.vtx', '.sw.vtx') and len(data) >= 20 and struct.unpack_from('<I', data)[0] == 7:
        return struct.unpack_from('<I', data, 16)[0]
    if suffix == '.phy' and len(data) >= 16 and struct.unpack_from('<II', data) == (16, 0) and struct.unpack_from('<I', data, 8)[0] > 0:
        return struct.unpack_from('<I', data, 12)[0]
    return None


class Publication:
    def __init__(self, inputs=()):
        self.temporary = tempfile.TemporaryDirectory(prefix='newpage-helper-')
        self.work = Path(self.temporary.name)
        self.entries = {}
        self.locks = []
        self.retained = False
        self.inputs = tuple(inputs)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        for stream in reversed(self.locks):
            stream.close()
        if not self.retained:
            self.temporary.cleanup()
        else:
            # Preserve evidence if a competing writer prevents rollback.
            self.temporary._finalizer.detach()

    def reserve(self, destination):
        destination = Path(destination).absolute()
        different_paths(self.inputs, [destination])
        identity = key(destination)
        if identity in self.entries:
            return self.entries[identity]
        lockpath = Path(tempfile.gettempdir()) / ('newpage-helper-lock-' +
                   hashlib.sha256(identity.encode('utf-8')).hexdigest() + '.lock')
        stream = lockpath.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                if stream.seek(0, 2) == 0:
                    stream.write(b'\0'); stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            stream.close()
            raise ValueError('another helper is writing this output: ' + str(destination)) from None
        self.locks.append(stream)
        entry = dict(destination=destination, before=fingerprint(destination), source=None, remove=False)
        self.entries[identity] = entry
        return entry

    def add(self, source, destination):
        entry = self.reserve(destination)
        entry['source'] = Path(source)

    def compile(self, compiler, qc, game, model):
        game = Path(game).resolve()
        destination = game / model
        # Reserve the complete standard output family before starting a compiler.
        base = str(destination.with_suffix(''))
        suffixes = ('.mdl', '.vvd', '.vtx', '.dx90.vtx', '.dx80.vtx', '.sw.vtx', '.ani', '.phy', '.vertexanim.json')
        for suffix in suffixes:
            self.reserve(Path(base + suffix))
        old_checksum = model_checksum(destination, '.mdl')
        compiled = self.work / 'compiled'
        result = subprocess.run([str(Path(compiler).resolve()), str(qc), '-game', str(game),
                                 '-OutDir', str(compiled)])
        if result.returncode:
            return result.returncode
        if not (compiled / model).is_file():
            raise ValueError('compiler succeeded without the expected model: ' + model)
        for source in sorted((compiled / 'models').rglob('*')):
            if source.is_file():
                self.add(source, game / source.relative_to(compiled))
        for suffix in suffixes[1:]:
            entry = self.reserve(Path(base + suffix))
            if entry['before'] is not None and entry['source'] is None:
                if old_checksum is not None and model_checksum(entry['destination'], suffix) == old_checksum:
                    entry['remove'] = True
                else:
                    print('warning: retaining obsolete companion with unverified ownership: ' + str(entry['destination']), file=sys.stderr)
        return 0

    def commit(self):
        entries = [entry for entry in self.entries.values() if entry['source'] is not None or entry['remove']]
        backups, replacements, published = [], [], []
        created = []
        try:
            # Check every destination before changing any of them.
            for entry in entries:
                if fingerprint(entry['destination']) != entry['before']:
                    raise ValueError('output changed during generation: ' + str(entry['destination']))
                if not entry['remove'] and not entry['source'].is_file():
                    raise ValueError('missing staged output: ' + str(entry['source']))
            for entry in entries:
                target = entry['destination']
                if entry['remove']:
                    replacements.append((entry, None))
                    continue
                missing = []
                parent = target.parent
                while not parent.exists():
                    missing.append(parent); parent = parent.parent
                for directory in reversed(missing):
                    directory.mkdir(); created.append(directory)
                descriptor, temp = tempfile.mkstemp(prefix='.newpage-helper-new-', dir=target.parent)
                os.close(descriptor); temp = Path(temp)
                replacements.append((entry, temp))
                shutil.copyfile(entry['source'], temp)
                with temp.open('r+b') as stream:
                    os.fsync(stream.fileno())
            # Move all old files out of the way first. A locked JSON therefore
            # fails before any new model is visible, regardless of file order.
            for entry, _ in replacements:
                target = entry['destination']
                if fingerprint(target) != entry['before']:
                    raise ValueError('output changed before publication: ' + str(target))
                if entry['before'] is not None:
                    descriptor, backup = tempfile.mkstemp(prefix='.newpage-helper-old-', dir=target.parent)
                    os.close(descriptor); backup = Path(backup)
                    try:
                        os.replace(target, backup)
                    except BaseException:
                        backup.unlink(); raise
                    backups.append((entry, backup))
            for entry, temp in replacements:
                if entry['remove']:
                    continue
                if entry['destination'].exists():
                    raise ValueError('output appeared during publication: ' + str(entry['destination']))
                os.replace(temp, entry['destination'])
                published.append(entry)
        except BaseException as failure:
            try:
                for entry in reversed(published):
                    if fingerprint(entry['destination']) != fingerprint(entry['source']):
                        raise ValueError('published output changed before rollback: ' + str(entry['destination']))
                    entry['destination'].unlink()
                for entry, backup in reversed(backups):
                    if entry['destination'].exists():
                        raise ValueError('output appeared before rollback: ' + str(entry['destination']))
                    os.replace(backup, entry['destination'])
            except BaseException as rollback:
                self.retained = True
                recovery = self.work / 'recovery.json'
                try:
                    recovery.write_text(json.dumps([
                        dict(destination=str(entry['destination']), backup=str(backup),
                             staged=str(entry['source']) if entry['source'] else None)
                        for entry, backup in backups if backup.exists()
                    ], indent=2) + '\n', encoding='utf-8')
                except OSError:
                    pass  # Original backups and staging still remain recoverable.
                raise OSError(f'{failure}; rollback needs attention: {rollback}; staging and recovery mapping retained at {self.work}') from failure
            raise
        else:
            for _, backup in backups:
                try:
                    backup.unlink()
                except OSError as error:
                    # Publication has committed. Cleanup must not falsely report
                    # a failed transaction after all outputs were replaced.
                    print(f'warning: outputs committed; old backup retained at {backup}: {error}', file=sys.stderr)
        finally:
            for _, temp in replacements:
                if temp is not None and temp.exists():
                    try:
                        temp.unlink()
                    except OSError as error:
                        print(f'warning: staged output cleanup failed at {temp}: {error}', file=sys.stderr)
            for directory in reversed(created):
                try:
                    directory.rmdir()
                except OSError:
                    pass
