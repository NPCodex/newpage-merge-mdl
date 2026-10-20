#!/usr/bin/env python3
"""Real-process termination/recovery checks for the VMD/L4D batch transaction.

The production transaction header is built into subtool_transaction_probe with
pause hooks enabled only there. Children are forcibly terminated; destructors and
exception rollback do not run. Uses isolated generated fixtures, never user data.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time


def main():
    probe = Path(sys.argv[1]).resolve()
    passed = []
    with tempfile.TemporaryDirectory(prefix='newpage-subtool-crash-') as temporary:
        root = Path(temporary)

        def fixture(name, existing=True):
            work = root / name
            work.mkdir()
            if existing:
                (work / 'a').write_bytes(b'old a')
                (work / 'b').write_bytes(b'old b')
            (work / 'old.ani').write_bytes(b'old companion')
            return work

        def snapshot(work):
            result = {}
            for name in ('a', 'b', 'old.ani'):
                path = work / name
                result[name] = path.read_bytes() if path.is_file() else ('directory' if path.exists() else None)
            return result

        def expected(existing=True, committed=False):
            return dict(a=b'new a' if committed else (b'old a' if existing else None),
                        b=b'new b' if committed else (b'old b' if existing else None),
                        **{'old.ani': None if committed else b'old companion'})

        def markers(work):
            return sorted(work.glob('*.newpage-subtool-journal'))

        def manifest(work):
            pointer = shlex.split(markers(work)[-1].read_text(encoding='utf-8'))
            return Path(pointer[1]) / 'journal'

        def target(work):
            return str(markers(work)[-1])[:-len('.newpage-subtool-journal')]

        def child(work, point, index=0, recover=False, lock_target=None):
            ready = work / 'ready'
            ready.unlink(missing_ok=True)
            env = os.environ.copy()
            env.update(NEWPAGE_SUBTOOL_PAUSE_POINT=point, NEWPAGE_SUBTOOL_PAUSE_INDEX=str(index),
                       NEWPAGE_SUBTOOL_READY=str(ready))
            command = [str(probe), '--durable-recover', target(work)] if recover else [str(probe), '--durable-write', str(work)]
            if lock_target is not None:
                command = [str(probe), '--durable-lock', str(lock_target)]
            process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 20
            while not ready.exists():
                if process.poll() is not None:
                    raise AssertionError((point, index, process.communicate()))
                if time.monotonic() > deadline:
                    process.kill()
                    raise AssertionError(('child did not reach pause', point, index, process.communicate()))
                time.sleep(0.01)
            return process

        def kill(process):
            process.kill()
            process.communicate(timeout=10)
            assert process.returncode != 0

        def recover(work, success=True, destination=None):
            command = [str(probe), '--durable-recover', str(destination or target(work))]
            result = subprocess.run(command, capture_output=True, timeout=15)
            assert (result.returncode == 0) == success, (command, result.returncode, result.stdout, result.stderr)
            return result

        def clean(work, old_root):
            assert not markers(work), ('markers left behind', work)
            assert not list(work.glob('.newpage-subtool-publish-*')), ('slots left behind', work)
            assert not old_root.exists(), ('root left behind', old_root)

        # A crash can occur between any two renames, including removal of an old
        # companion. Either one common commit decision survives or all old files
        # are restored, regardless of the marker used to enter recovery.
        points = [('stage', 0), ('stage', 1), ('prepared', 0), ('prepared', 2), ('journal', 0),
                  ('backed_up', 0), ('backed_up', 1), ('backed_up', 2),
                  ('published', 0), ('published', 1), ('published', 2),
                  ('before_commit', 0), ('committed', 0), ('cleanup_previous', 0),
                  ('cleanup_replacement', 0), ('cleanup_owner', 0), ('cleanup_slot', 0),
                  ('cleanup_marker', 0), ('cleanup_marker', 1)]
        for existing in (False, True):
            for point, index in points:
                work = fixture(f'{point}-{index}-{existing}', existing)
                process = child(work, point, index)
                old_root = manifest(work).parent
                kill(process)
                recover(work)
                assert snapshot(work) == expected(existing, point == 'committed' or point.startswith('cleanup_')), (work, snapshot(work))
                clean(work, old_root)
                passed.append(work.name)

        # Recovery itself is restartable after restoration of each individual
        # file, after preflight, and partway through marker cleanup.
        for existing in (False, True):
            for point, index in [('recovery_preflight', 0), ('recovered', 0), ('recovered', 1),
                                 ('recovered', 2), ('cleanup_previous', 0), ('cleanup_replacement', 0),
                                 ('cleanup_owner', 0), ('cleanup_slot', 0), ('cleanup_marker', 0)]:
                work = fixture(f'recovery-{point}-{index}-{existing}', existing)
                process = child(work, 'published', 2)
                old_root = manifest(work).parent
                kill(process)
                process = child(work, point, index, recover=True)
                kill(process)
                recover(work)
                assert snapshot(work) == expected(existing), (work, snapshot(work))
                clean(work, old_root)
                passed.append(work.name)

        work = fixture('cross-process-lock-中文')
        process = child(work, 'stage', 0)
        before = snapshot(work)
        error = recover(work, success=False, destination=work/'a')
        assert b'locked' in error.stderr.lower() and snapshot(work) == before
        kill(process)
        recover(work)
        assert snapshot(work) == before
        passed.append(work.name)

        work = fixture('cross-process-recovery-batch-lock')
        process = child(work, 'published', 1)
        journal = manifest(work); kill(process)
        process = child(work, 'locked', lock_target=work/'b')
        before = snapshot(work)
        result = recover(work, success=False, destination=work/'a')
        assert b'locked' in result.stderr.lower() and snapshot(work) == before
        kill(process)
        recover(work)
        assert snapshot(work) == expected()
        clean(work, journal.parent)
        passed.append(work.name)

        # A conflict in the last target must be caught before an earlier target
        # is restored, and all recovery material must remain available.
        for kind in ('destination', 'destination-directory', 'backup', 'backup-directory', 'replacement',
                     'owner', 'missing-backup', 'missing-marker'):
            work = fixture('external-' + kind)
            process = child(work, 'published', 0)
            journal = manifest(work)
            lines = journal.read_text(encoding='utf-8').splitlines()
            entry_a, entry_b = shlex.split(lines[1]), shlex.split(lines[2])
            slot_a, slot_b = Path(entry_a[2]), Path(entry_b[2])
            kill(process)
            changed = None
            if kind == 'destination':
                changed = work / 'b'
            elif kind == 'backup':
                changed = slot_a / 'previous'
            elif kind == 'replacement':
                changed = slot_b / 'replacement'
            elif kind == 'owner':
                changed = slot_b / 'owner'
            if changed:
                saved = changed.read_bytes()
                changed.write_bytes(b'external replacement')
            elif kind.endswith('-directory'):
                changed = (work/'b') if kind == 'destination-directory' else (slot_a/'previous')
                saved = changed.read_bytes()
                changed.unlink(); changed.mkdir(); (changed/'foreign').write_bytes(b'foreign')
            elif kind == 'missing-backup':
                changed = slot_a/'previous'; saved = changed.read_bytes(); changed.unlink()
            else:
                changed = work/'b.newpage-subtool-journal'; saved = changed.read_bytes(); changed.unlink()
            before = snapshot(work)
            recover(work, success=False, destination=work/'a')
            assert snapshot(work) == before and journal.exists(), (work, snapshot(work), before)
            if changed.is_dir(): shutil.rmtree(changed)
            changed.write_bytes(saved)
            recover(work)
            assert snapshot(work) == expected()
            clean(work, journal.parent)
            passed.append(work.name)

        def encode(tokens):
            return ' '.join(json.dumps(token, ensure_ascii=False) if isinstance(token, str) else str(token) for token in tokens)

        def rewrite(journal, header, entries, checksum=True):
            body = '\n'.join([encode(header), *map(encode, entries)]) + '\n'
            value = 14695981039346656037
            for byte in body.encode('utf-8'):
                value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
            journal.write_text(body + f'CHECKSUM {value:x}\n' if checksum else body + 'CHECKSUM bad\n', encoding='utf-8', newline='')

        # Recompute the checksum in structural attacks so validation of actual
        # paths/state is tested independently from accidental corruption.
        for kind in ('checksum', 'phase', 'duplicate', 'slot', 'staged', 'fingerprint', 'target', 'trailing'):
            work = fixture('malformed-' + kind)
            process = child(work, 'published', 1)
            journal = manifest(work); original = journal.read_bytes(); kill(process)
            rows = [shlex.split(line) for line in original.decode().splitlines()[:-1]]
            header, entries = rows[0], rows[1:]
            if kind == 'phase': header[2] = '9'
            elif kind == 'duplicate': entries[1] = entries[0].copy()
            elif kind == 'slot': entries[1][2] = str(root/'foreign-slot')
            elif kind == 'staged': entries[1][1] = str(root/'outside-stage')
            elif kind == 'fingerprint': entries[1][3] = '0'
            elif kind == 'target': entries[1][0] = str(root/'unowned-target')
            rewrite(journal, header, entries, checksum=kind != 'checksum')
            if kind == 'trailing': journal.write_bytes(journal.read_bytes()+b'junk')
            before = snapshot(work)
            recover(work, success=False)
            assert snapshot(work) == before and journal.exists()
            journal.write_bytes(original)
            recover(work)
            assert snapshot(work) == expected()
            clean(work, journal.parent)
            passed.append(work.name)

        # A directory junction is Windows' normal no-admin link facility. On
        # POSIX the same test uses a directory symlink.
        def link_directory(link, destination):
            if os.name == 'nt':
                result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(destination)], capture_output=True)
                assert result.returncode == 0, result.stderr
            else:
                link.symlink_to(destination, target_is_directory=True)

        def unlink_directory(link):
            if os.name == 'nt': link.rmdir()
            else: link.unlink()

        for kind in ('root', 'slot'):
            work = fixture('linked-' + kind)
            process = child(work, 'published', 1)
            journal = manifest(work)
            slot = Path(shlex.split(journal.read_text(encoding='utf-8').splitlines()[2])[2])
            kill(process)
            linked = journal.parent if kind == 'root' else slot
            holding = linked.with_name(linked.name + '-held')
            linked.rename(holding); link_directory(linked, holding)
            before = snapshot(work)
            recover(work, success=False)
            assert snapshot(work) == before and (holding/'journal' if kind == 'root' else holding/'previous').exists()
            unlink_directory(linked); holding.rename(linked)
            recover(work)
            assert snapshot(work) == expected()
            clean(work, journal.parent)
            passed.append(work.name)

        # A non-cooperating edit during generation belongs to the external
        # writer. No output was moved in phase 0/1, so cleanup preserves it.
        work = fixture('external-during-generation')
        process = child(work, 'prepared', 2)
        journal = manifest(work); kill(process)
        (work/'b').write_bytes(b'external new b')
        before = snapshot(work)
        recover(work)
        assert snapshot(work) == before
        clean(work, journal.parent)
        passed.append(work.name)

    print(f'{len(passed)} durable subtool process checks passed')
    for name in passed:
        print('PASS', name)


if __name__ == '__main__':
    main()
