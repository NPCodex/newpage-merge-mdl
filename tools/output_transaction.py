"""Stage authoring-helper outputs with persistent publication recovery.

The native compiler receives a private -OutDir. Only this publication step may
replace the user's model, its companions, generated sources and runtime JSON.
Adjacent journals and backups allow the next invocation to recover interrupted
publication. Conflicting external edits are retained for manual inspection.
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
import uuid


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


def _digest(path):
    value = fingerprint(path)
    return value.hex() if value is not None else None


def _sync_parent(path):
    # Windows does not expose a portable directory fsync through Python.
    # File content is flushed on both platforms; this is not a blanket
    # guarantee against hardware, filesystem or power-loss failures.
    if os.name != 'nt':
        descriptor = os.open(str(Path(path).parent), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _atomic_json(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix='.newpage-helper-journal-write-', dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_parent(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(path):
    fingerprint(path)  # Reject symlinks and non-files before reading metadata.
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('oversized helper recovery journal: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def _marker(destination):
    return destination.with_name(destination.name + '.newpage-helper-journal')


def _cleanup_journal(path, journal):
    # Keep all discovery pointers if any backup cannot yet be cleaned. A later
    # invocation can finish committed cleanup without rolling back new outputs.
    for entry in journal['entries']:
        for field, expected in (('backup', entry['before']), ('temporary', entry['after'])):
            item = Path(entry[field]) if entry[field] else None
            if item is not None and item.exists():
                if _digest(item) != expected:
                    raise ValueError('recovery file changed: ' + str(item))
                item.unlink(); _sync_parent(item)
    for entry in journal['entries']:
        marker = _marker(Path(entry['destination']))
        if marker.exists():
            pointer = _read_json(marker)
            if pointer != dict(schema=1, token=journal['token'], journal=str(path)):
                raise ValueError('helper recovery pointer changed: ' + str(marker))
            marker.unlink(); _sync_parent(marker)
    if path.exists():
        path.unlink(); _sync_parent(path)


def _restore_journal(path, journal):
    # Check the complete set before restoring any file. Recovery is idempotent:
    # a second interruption may leave some old files already restored.
    for entry in journal['entries']:
        target = Path(entry['destination'])
        current = _digest(target)
        backup = Path(entry['backup']) if entry['backup'] else None
        saved = _digest(backup) if backup is not None else None
        before, after = entry['before'], entry['after']
        if journal['committed']:
            if current != after:
                raise ValueError('committed output changed before cleanup: ' + str(target))
        elif saved is not None:
            if saved != before or current not in (None, before, after):
                raise ValueError('output or backup changed before recovery: ' + str(target))
        elif current != before:
            if before is not None or current != after:
                raise ValueError('output changed before recovery: ' + str(target))
        temporary = Path(entry['temporary']) if entry['temporary'] else None
        if temporary is not None and temporary.exists() and _digest(temporary) != after:
            raise ValueError('staged output changed before recovery: ' + str(temporary))
    if not journal['committed']:
        for entry in reversed(journal['entries']):
            target = Path(entry['destination'])
            backup = Path(entry['backup']) if entry['backup'] else None
            current = _digest(target)
            saved = _digest(backup) if backup is not None else None
            if saved is not None:
                if saved != entry['before'] or current not in (None, entry['before'], entry['after']):
                    raise ValueError('output or backup changed during recovery: ' + str(target))
            elif current != entry['before'] and (entry['before'] is not None or current != entry['after']):
                raise ValueError('output changed during recovery: ' + str(target))
            if backup is not None and backup.exists():
                if target.exists():
                    target.unlink(); _sync_parent(target)
                if target.exists() or target.is_symlink():
                    raise ValueError('output appeared during recovery: ' + str(target))
                os.replace(backup, target); _sync_parent(target)
            elif entry['before'] is None and target.exists():
                target.unlink(); _sync_parent(target)
    _cleanup_journal(path, journal)


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
        self.locked = set()
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

    def _acquire(self, destination):
        identity = key(destination)
        if identity in self.locked:
            return
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
        self.locked.add(identity)

    def _recover(self, destination):
        marker = _marker(destination)
        if not marker.exists() and not marker.is_symlink():
            return
        pointer = _read_json(marker)
        if not isinstance(pointer, dict) or pointer.get('schema') != 1 or not isinstance(pointer.get('journal'), str):
            raise ValueError('invalid helper recovery pointer: ' + str(marker))
        path = Path(pointer['journal'])
        journal = _read_json(path)
        token = pointer.get('token')
        if (not isinstance(token, str) or len(token) != 32 or any(c not in '0123456789abcdef' for c in token)
                or path.name != '.newpage-helper-transaction-' + token + '.json'
                or not path.is_absolute() or not isinstance(journal, dict)
                or journal.get('schema') != 1 or journal.get('token') != token
                or type(journal.get('committed')) is not bool
                or not isinstance(journal.get('entries'), list) or not journal['entries']):
            raise ValueError('invalid helper recovery journal: ' + str(path))
        destinations = []
        for index, entry in enumerate(journal['entries']):
            if (not isinstance(entry, dict) or not isinstance(entry.get('destination'), str)
                    or not {'destination', 'before', 'after', 'backup', 'temporary'} <= entry.keys()):
                raise ValueError('invalid helper recovery entry: ' + str(path))
            target = Path(entry['destination'])
            if not target.is_absolute() or target.is_symlink() or target != target.resolve():
                raise ValueError('invalid helper recovery destination: ' + str(target))
            for field in ('before', 'after'):
                value = entry.get(field)
                if value is not None and (not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value)):
                    raise ValueError('invalid helper recovery fingerprint: ' + str(path))
            for field, prefix in (('backup', '.newpage-helper-old-'), ('temporary', '.newpage-helper-new-')):
                value = entry.get(field)
                expected = str(target.parent / (prefix + token + '-' + str(index)))
                if value is not None and value != expected:
                    raise ValueError('invalid helper recovery file path: ' + str(path))
            if ((entry['before'] is None) != (entry.get('backup') is None)
                    or (entry['after'] is None) != (entry.get('temporary') is None)):
                raise ValueError('incomplete helper recovery entry: ' + str(path))
            destinations.append(target)
        if (key(destination) not in {key(p) for p in destinations}
                or len({key(p) for p in destinations}) != len(destinations)
                or path.parent != destinations[0].parent):
            raise ValueError('helper recovery journal belongs to different outputs: ' + str(path))
        different_paths(self.inputs, destinations)
        for target in sorted(destinations, key=key):
            self._acquire(target)
        try:
            _restore_journal(path, journal)
        except (OSError, ValueError) as error:
            raise OSError(f'helper recovery needs attention: {error}; journal retained at {path}') from error
        # A recovered group can include an output already reserved by this
        # invocation. Refresh its baseline before any new generation commits.
        for target in destinations:
            if key(target) in self.entries:
                self.entries[key(target)]['before'] = fingerprint(target)

    def reserve(self, destination):
        destination = Path(destination).absolute()
        different_paths(self.inputs, [destination])
        if destination.is_symlink():
            raise ValueError('refusing a symbolic-link output: ' + str(destination))
        destination = destination.resolve()
        identity = key(destination)
        if identity in self.entries:
            return self.entries[identity]
        self._acquire(destination)
        self._recover(destination)
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
        if not entries:
            return
        token = uuid.uuid4().hex
        path = entries[0]['destination'].parent / ('.newpage-helper-transaction-' + token + '.json')
        journal = dict(schema=1, token=token, committed=False, entries=[])
        created, staged = [], []
        journal_started = False
        try:
            # Check every destination before changing any of them.
            for entry in entries:
                if fingerprint(entry['destination']) != entry['before']:
                    raise ValueError('output changed during generation: ' + str(entry['destination']))
                if not entry['remove'] and not entry['source'].is_file():
                    raise ValueError('missing staged output: ' + str(entry['source']))
                different_paths(self.inputs, [_marker(entry['destination'])])
                if _marker(entry['destination']).exists() or _marker(entry['destination']).is_symlink():
                    raise ValueError('unexpected helper recovery pointer: ' + str(_marker(entry['destination'])))
            for index, entry in enumerate(entries):
                target = entry['destination']
                missing = []
                parent = target.parent
                while not parent.exists():
                    missing.append(parent); parent = parent.parent
                for directory in reversed(missing):
                    directory.mkdir(); created.append(directory)
                temp = None
                if not entry['remove']:
                    temp = target.parent / ('.newpage-helper-new-' + token + '-' + str(index))
                    with temp.open('xb') as output:
                        staged.append(temp)
                        with entry['source'].open('rb') as source:
                            shutil.copyfileobj(source, output)
                        output.flush(); os.fsync(output.fileno())
                backup = target.parent / ('.newpage-helper-old-' + token + '-' + str(index)) if entry['before'] is not None else None
                if backup is not None and (backup.exists() or backup.is_symlink()):
                    raise ValueError('unexpected helper backup: ' + str(backup))
                journal['entries'].append(dict(destination=str(target),
                    before=entry['before'].hex() if entry['before'] is not None else None,
                    after=_digest(temp) if temp is not None else None,
                    temporary=str(temp) if temp is not None else None,
                    backup=str(backup) if backup is not None else None))
            # Record the full recovery set before the first destructive rename.
            # Every target points to this record, so restarting any member of
            # the batch can recover all companions under their original locks.
            _atomic_json(path, journal)
            journal_started = True
            for record in journal['entries']:
                _atomic_json(_marker(Path(record['destination'])), dict(schema=1, token=token, journal=str(path)))
            # Move all old files out of the way first. A locked JSON therefore
            # fails before any new model is visible, regardless of file order.
            for record in journal['entries']:
                target = Path(record['destination'])
                if _digest(target) != record['before']:
                    raise ValueError('output changed before publication: ' + str(target))
                if record['backup'] is not None:
                    os.replace(target, record['backup']); _sync_parent(target)
            for record in journal['entries']:
                if record['temporary'] is None:
                    continue
                target = Path(record['destination'])
                if target.exists() or target.is_symlink():
                    raise ValueError('output appeared during publication: ' + str(target))
                os.replace(record['temporary'], target); _sync_parent(target)
            committed = dict(journal, committed=True)
            _atomic_json(path, committed)
            journal = committed
        except BaseException as failure:
            # An fsync failure can occur after the committed marker rename.
            # The on-disk marker is authoritative: never roll back outputs
            # after readers/recovery may already have observed this decision.
            if journal_started and not journal['committed']:
                try:
                    saved_journal = _read_json(path)
                    if saved_journal == dict(journal, committed=True):
                        journal = saved_journal
                except (OSError, ValueError):
                    pass
            if journal['committed']:
                print(f'warning: outputs committed; durability/cleanup needs attention at {path}: {failure}', file=sys.stderr)
                return
            try:
                if journal_started:
                    _restore_journal(path, journal)
            except BaseException as rollback:
                self.retained = True
                recovery = self.work / 'recovery.json'
                try:
                    recovery.write_text(json.dumps([
                        dict(destination=record['destination'], backup=record['backup'],
                             staged=str(entry['source']) if entry['source'] else None)
                        for entry, record in zip(entries, journal['entries']) if record['backup'] and Path(record['backup']).exists()
                    ], indent=2) + '\n', encoding='utf-8')
                except OSError:
                    pass  # Original backups and staging still remain recoverable.
                raise OSError(f'{failure}; rollback needs attention: {rollback}; journal {path}; staging and recovery mapping retained at {self.work}') from failure
            raise
        else:
            try:
                _cleanup_journal(path, journal)
            except (OSError, ValueError) as error:
                # The committed marker is durable before cleanup begins. A
                # failed cleanup must not turn a successful publication into a
                # failure or restore the old version on the next invocation.
                print(f'warning: outputs committed; cleanup journal retained at {path}: {error}', file=sys.stderr)
        finally:
            if not journal_started:
              for temp in staged:
                if temp.exists():
                    try:
                        temp.unlink()
                    except OSError as error:
                        print(f'warning: staged output cleanup failed at {temp}: {error}', file=sys.stderr)
            for directory in reversed(created):
                try:
                    directory.rmdir()
                except OSError:
                    pass
