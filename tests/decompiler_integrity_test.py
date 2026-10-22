"""Isolated decompiler integrity regressions.

Usage: python tests/decompiler_integrity_test.py <compiler> <decompiler>
Only synthetic models and temporary output directories are used.
"""
from pathlib import Path
import struct
import os
import subprocess
import sys
import tempfile
import unittest

COMPILER = str(Path(sys.argv.pop(1)).resolve())
DECOMPILER = str(Path(sys.argv.pop(1)).resolve())


def bone_names(path):
    data = path.read_bytes()
    count, offset = struct.unpack_from('<2i', data, 156)
    names = []
    for i in range(count):
        bone = offset + i * 216
        start = bone + struct.unpack_from('<i', data, bone)[0]
        names.append(data[start:data.index(b'\0', start)].decode('utf-8'))
    return names


class DecompilerIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='npmdl-decompiler-')
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_tool(self, exe, args, success=True):
        proc = subprocess.run([exe, *map(str, args)], capture_output=True, timeout=90)
        output = (proc.stdout + proc.stderr).decode('utf-8', 'replace')
        if success:
            self.assertEqual(proc.returncode, 0, output)
        else:
            self.assertNotEqual(proc.returncode, 0, output)
        return output

    def fixture(self, folder='source', names=('bone_1', '\u8155'), mesh=True):
        root = self.root / folder
        root.mkdir(parents=True, exist_ok=True)
        (root / 'gameinfo.txt').write_text('"GameInfo" { "FileSystem" { "SteamAppId" "4000" } }')
        text = 'version 1\nnodes\n'
        text += ''.join(f'{i} "{n}" {i - 1}\n' for i, n in enumerate(names))
        text += 'end\nskeleton\ntime 0\n'
        text += ''.join(f'{i} 0 0 {i} 0 0 0\n' for i in range(len(names)))
        text += 'end\ntriangles\n'
        for i in range(len(names)):
            text += f'mat\n{i} 0 0 {i} 0 0 1 0 0\n{i} 1 0 {i} 0 0 1 1 0\n{i} 0 1 {i} 0 0 1 0 1\n'
        text += 'end\n'
        (root / 'mesh.smd').write_text(text, encoding='utf-8')
        qc = '$modelname shared\n' + ('$body body mesh.smd\n' if mesh else '')
        qc += '$sequence idle mesh.smd\n'
        (root / 'model.qc').write_text(qc, encoding='utf-8')
        self.run_tool(COMPILER, ['-nodefaultargs', '-game', root, root / 'model.qc'])
        return root / 'models/shared.mdl'

    def decompile(self, source, output='output', extra=(), success=True):
        destination = self.root / output
        log = self.run_tool(DECOMPILER, [source, '-outdir', destination,
                            '-dmxencoding', 'keyvalues2', '-smdanimation', *extra], success)
        return destination, log

    def output_dir(self, destination):
        return next(destination.glob('decompiled */shared'))

    def snapshot(self, directory):
        # Persistent lock identities intentionally survive successful/failed
        # transactions. They are metadata, not decompiled user outputs.
        return {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob('*')
                if p.is_file() and not (p.parent.name == '.newpage-output-locks' and p.suffix == '.lock')}

    def assert_no_staging(self, directory):
        self.assertEqual(list(directory.rglob('.newpage-decompile-*')), [])
        for journals in directory.rglob('.newpage-output-transactions'):
            # Stable empty identity directories may remain; journals, staged
            # work and recovery backups must all have been removed.
            self.assertEqual([p for p in journals.rglob('*') if not p.is_dir() or p.parent != journals], [])

    def roundtrip(self, destination, names):
        generated = self.output_dir(destination)
        qc = generated / 'shared.qc'
        smd = generated / 'anims/idle.smd'
        nodes = smd.read_text(encoding='utf-8').split('nodes\n', 1)[1].split('\nend', 1)[0]
        for name in names:
            self.assertIn(f'"{name}"', nodes)
            self.assertIn(f'"{name}"', qc.read_text(encoding='utf-8'))
        game = self.root / 'roundtrip'
        game.mkdir(exist_ok=True)
        (game / 'gameinfo.txt').write_text('"GameInfo" { "FileSystem" { "SteamAppId" "4000" } }')
        self.run_tool(COMPILER, ['-nodefaultargs', '-game', game, qc])
        self.assertEqual(bone_names(game / 'models/shared.mdl'), names)

    def test_unicode_bones_survive_smd_dmx_qc_roundtrip(self):
        source = self.fixture()
        destination, _ = self.decompile(source)
        self.roundtrip(destination, ['bone_1', '\u8155'])

    def test_fallback_reserves_later_valid_names_and_casefolds_duplicates(self):
        source = self.fixture(names=('invalid', 'bone_0', 'bone_0_2', 'second'))
        data = bytearray(source.read_bytes())
        _, base = struct.unpack_from('<2i', data, 156)
        for i, replacement in ((0, b'\xff'), (3, b'BONE_0')):
            bone = base + i * 216
            start = bone + struct.unpack_from('<i', data, bone)[0]
            end = data.index(b'\0', start)
            self.assertLessEqual(len(replacement), end - start)
            data[start:end] = replacement.ljust(end - start, b'\0')
        source.write_bytes(data)
        destination, log = self.decompile(source)
        self.assertIn('renamed unsafe or duplicate bone', log)
        self.roundtrip(destination, ['bone_0_3', 'bone_0', 'bone_0_2', 'bone_3'])
        before = self.snapshot(destination)
        self.decompile(source)
        self.assertEqual(self.snapshot(destination), before)

    def test_batch_same_basename_rejected_before_any_write(self):
        one = self.fixture('one')
        two = self.fixture('two')
        destination, _ = self.decompile(one)
        before = self.snapshot(destination)
        log = self.run_tool(DECOMPILER, [one, two, '-outdir', destination], success=False)
        self.assertIn('output collision', log)
        self.assertEqual(self.snapshot(destination), before)
        self.assert_no_staging(destination)

    @unittest.skipUnless(os.name == 'nt', 'Windows filenames compare Unicode case-insensitively')
    def test_batch_unicode_case_collision_is_rejected_before_extraction(self):
        one = self.fixture('one')
        two = self.fixture('two')
        inputs = []
        # Cyrillic case pairs are representable in the Windows Chinese ACP too.
        for source, name in ((one, 'Жmodel'), (two, 'жmodel')):
            for path in list(source.parent.glob('shared.*')):
                path.rename(path.with_name(path.name.replace('shared.', name + '.', 1)))
            inputs.append(source.with_name(name + '.mdl'))
        destination = self.root / 'output'
        log = self.run_tool(DECOMPILER, [*inputs, '-outdir', destination], success=False)
        self.assertIn('output collision', log)
        self.assertNotIn('Decompiling:', log)
        self.assertFalse(destination.exists())

    def test_batch_unique_basenames_succeeds(self):
        one = self.fixture('one')
        two = self.fixture('two')
        for path in list(two.parent.glob('shared.*')):
            path.rename(path.with_name(path.name.replace('shared.', 'other.', 1)))
        destination = self.root / 'output'
        self.run_tool(DECOMPILER, [one, two.with_name('other.mdl'), '-outdir', destination])
        self.assertEqual(len(list(destination.rglob('*.qc'))), 2)

    def test_missing_required_sidecars_fail_and_preserve_existing_output(self):
        source = self.fixture()
        destination, _ = self.decompile(source)
        generated = self.output_dir(destination)
        (generated / 'user-notes.txt').write_text('keep this file')
        before = self.snapshot(destination)
        for extension, expected in (('.vvd', 'no usable'), ('.dx90.vtx', 'VTX sidecar')):
            with self.subTest(extension=extension):
                targets = ([source.with_suffix(extension)] if extension == '.vvd'
                           else list(source.parent.glob('shared*.vtx')))
                saved = {p: p.read_bytes() for p in targets}
                for path in targets:
                    path.unlink()
                _, log = self.decompile(source, success=False)
                self.assertIn(expected, log)
                self.assertEqual(self.snapshot(destination), before)
                self.assert_no_staging(destination)
                for path, content in saved.items():
                    path.write_bytes(content)

    def test_nomesh_explicitly_allows_missing_sidecars(self):
        source = self.fixture()
        for path in source.parent.glob('shared.*'):
            if path != source:
                path.unlink()
        destination, _ = self.decompile(source, extra=('-nomesh',))
        self.assertTrue((self.output_dir(destination) / 'shared.qc').is_file())
        self.assertEqual(list(destination.rglob('meshes/*.dmx')), [])

    def test_animation_only_model_needs_no_mesh_sidecars(self):
        source = self.fixture(mesh=False)
        for path in source.parent.glob('shared.*'):
            if path != source:
                path.unlink()
        destination, _ = self.decompile(source)
        self.assertTrue((self.output_dir(destination) / 'anims/idle.smd').is_file())

    def test_invalid_sequence_grid_counts_and_ranges_preserve_existing_output(self):
        source = self.fixture()
        original = source.read_bytes()
        count, sequence = struct.unpack_from('<2i', original, 188)
        self.assertEqual(count, 1)
        destination, _ = self.decompile(source)
        before = self.snapshot(destination)
        cases = ((0, 1, None), (-1, 1, None), (12550144, 12550144, None),
                 (81792, 14417920, None), (2147483647, 1, None),
                 (1, 1, 0), (1, 1, len(original)))
        for width, height, offset in cases:
            with self.subTest(width=width, height=height, offset=offset):
                data = bytearray(original)
                struct.pack_into('<2i', data, sequence + 68, width, height)
                if offset is not None:
                    struct.pack_into('<i', data, sequence + 60, offset)
                source.write_bytes(data)
                _, log = self.decompile(source, success=False)
                self.assertIn('invalid sequence blend grid', log)
                self.assertEqual(self.snapshot(destination), before)
                self.assert_no_staging(destination)

    def test_invalid_animation_frame_counts_fail_even_without_animation_export(self):
        source = self.fixture()
        original = source.read_bytes()
        count, animation = struct.unpack_from('<2i', original, 180)
        self.assertEqual(count, 1)
        destination, _ = self.decompile(source)
        before = self.snapshot(destination)
        for frames in (-2147483648, -1, 0):
            for extra in ((), ('-noanimation',)):
                with self.subTest(frames=frames, extra=extra):
                    data = bytearray(original)
                    struct.pack_into('<i', data, animation + 16, frames)
                    source.write_bytes(data)
                    _, log = self.decompile(source, extra=extra, success=False)
                    self.assertIn('invalid animation frame count', log)
                    self.assertEqual(self.snapshot(destination), before)
                    self.assert_no_staging(destination)

    def test_declared_animations_and_sequences_allow_absent_local_frames_and_grid(self):
        source = self.fixture()
        data = bytearray(source.read_bytes())
        _, animation = struct.unpack_from('<2i', data, 180)
        _, sequence = struct.unpack_from('<2i', data, 188)
        for record in (animation, sequence):
            flags, = struct.unpack_from('<i', data, record + 12)
            struct.pack_into('<i', data, record + 12, flags | 0x0800)
        struct.pack_into('<i', data, animation + 16, 0)
        struct.pack_into('<i', data, sequence + 60, 0)
        struct.pack_into('<2i', data, sequence + 68, 0, 0)
        source.write_bytes(data)
        destination, _ = self.decompile(source)
        script = (self.output_dir(destination) / 'shared.qc').read_text(encoding='utf-8')
        self.assertIn('$declareanimation', script)
        self.assertIn('$declaresequence', script)

    def test_invalid_sidecar_fails_without_publishing_partial_output(self):
        source = self.fixture()
        for extension in ('.vvd', '.dx90.vtx'):
            with self.subTest(extension=extension):
                path = source.with_suffix(extension)
                saved = path.read_bytes()
                path.write_bytes(b'truncated')
                destination, _ = self.decompile(source, success=False)
                self.assertEqual(self.snapshot(destination), {})
                self.assert_no_staging(destination)
                path.write_bytes(saved)

    def test_mesh_output_failure_preserves_qc_and_existing_extras(self):
        source = self.fixture()
        destination, _ = self.decompile(source)
        generated = self.output_dir(destination)
        mesh = next((generated / 'meshes').glob('*.dmx'))
        mesh.unlink()
        mesh.mkdir()
        (mesh / 'blocker.txt').write_text('existing directory must stay')
        (generated / 'user-notes.txt').write_text('keep this file')
        before = self.snapshot(destination)
        _, log = self.decompile(source, success=False)
        self.assertIn('cannot finish writing', log)
        self.assertEqual(self.snapshot(destination), before)
        self.assert_no_staging(destination)

    def test_animation_output_failure_is_not_success(self):
        source = self.fixture()
        destination, _ = self.decompile(source)
        anim = self.output_dir(destination) / 'anims/idle.smd'
        anim.unlink()
        anim.mkdir()
        before = self.snapshot(destination)
        _, log = self.decompile(source, success=False)
        self.assertIn('cannot write', log)
        self.assertEqual(self.snapshot(destination), before)

    def test_missing_animation_sidecar_fails_but_noanimation_skips_it(self):
        source = self.fixture()
        folder = source.parent.parent
        animation = 'version 1\nnodes\n0 "bone_1" -1\n1 "腕" 0\nend\nskeleton\n'
        for i in range(10):
            animation += f'time {i}\n0 0 0 0 0 0 0\n1 0 0 {i + 1} 0 0 0\n'
        (folder / 'anim.smd').write_text(animation + 'end\n', encoding='utf-8')
        (folder / 'model.qc').write_text('$modelname shared\n$animblocksize 1\n$body body mesh.smd\n'
                                       '$sequence idle anim.smd\n', encoding='utf-8')
        self.run_tool(COMPILER, ['-nodefaultargs', '-game', folder, folder / 'model.qc'])
        self.assertTrue(source.with_suffix('.ani').is_file())
        destination, _ = self.decompile(source)
        before = self.snapshot(destination)
        source.with_suffix('.ani').unlink()
        _, log = self.decompile(source, success=False)
        self.assertIn('cannot decode animation', log)
        self.assertEqual(self.snapshot(destination), before)
        skipped, _ = self.decompile(source, output='skip-animation', extra=('-noanimation',))
        self.assertEqual(list(skipped.rglob('*.smd')), [])
        self.assert_no_staging(destination)

    def test_successful_replacement_preserves_user_added_files(self):
        source = self.fixture()
        destination, _ = self.decompile(source)
        generated = self.output_dir(destination)
        note = generated / 'user-notes.txt'
        note.write_text('keep this file')
        self.decompile(source)
        self.assertEqual(note.read_text(), 'keep this file')
        self.assert_no_staging(destination)


if __name__ == '__main__':
    unittest.main()
