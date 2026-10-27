"""Direct StudioMDL++ output roots, CE compatibility and publication safety.

Usage: python tests/studiomdlpp_output_test.py <NewPageMergeMDL>
Fixtures are self-authored and all outputs stay in a temporary directory.
"""
from pathlib import Path
import json
import struct
import subprocess
import sys
import tempfile
import unittest

from integration_workflow_cases import journal_text

COMPILER = Path(sys.argv.pop(1)).resolve()
HEADER = 'version 1\nnodes\n0 "root" -1\nend\nskeleton\n'
MESH = HEADER + ('time 0\n0 0 0 0 0 0 0\nend\ntriangles\nmaterial\n'
                 '0 0 0 0 0 0 1 0 0\n0 1 0 0 0 0 1 1 0\n'
                 '0 0 1 0 0 0 1 0 1\nend\n')
GAMEINFO = 'GameInfo { game fixture FileSystem { SteamAppId 220 SearchPaths { Game "|gameinfo_path|." } } }'
BASE = '$modelname nested/probe.mdl\n$body body mesh.smd\n'
FAMILY = ('.mdl', '.vvd', '.dx80.vtx', '.dx90.vtx')


def sequences(path):
    data = path.read_bytes()
    count, offset = struct.unpack_from('<2i', data, 188)
    result = []
    for i in range(count):
        seq = offset + i * 212
        name = seq + struct.unpack_from('<i', data, seq + 4)[0]
        result.append(data[name:data.index(b'\0', name)].decode())
    return result


class DirectOutput(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='np-direct-output-')
        self.root = Path(self.temp.name)
        self.source, self.cwd, self.game = (self.root / p for p in ('QC directory', 'working directory', 'game'))
        for path in (self.source, self.cwd, self.game):
            path.mkdir()
        (self.source / 'mesh.smd').write_text(MESH)
        (self.game / 'gameinfo.txt').write_text(GAMEINFO)
        self.qc = self.source / 'probe.qc'

    def tearDown(self):
        self.temp.cleanup()

    def compile(self, *args, extra='', sequence_text='$sequence idle mesh.smd\n', game=True, success=True):
        self.qc.write_text(BASE + sequence_text + extra, encoding='utf-8')
        argv = [str(COMPILER), '-nodefaultargs', str(self.qc)]
        if game:
            argv += ['-game', str(self.game)]
        result = subprocess.run(argv + list(map(str, args)), cwd=self.cwd,
                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def family(self, output):
        return {suffix: (output / ('nested/probe' + suffix)).read_bytes() for suffix in FAMILY}

    def assert_no_other_outputs(self, output):
        paths = sorted(p.resolve() for p in self.root.rglob('*.mdl'))
        self.assertEqual(paths, [(output / 'nested/probe.mdl').resolve()])

    def test_relative_direct_root_uses_cwd_and_absolute_models_is_not_doubled(self):
        self.compile('-OuTdIrMoDeLs', 'relative output')
        self.assert_no_other_outputs(self.cwd / 'relative output')
        first = self.family(self.cwd / 'relative output')
        absolute = self.root / 'absolute output' / 'models'
        self.compile('-OutDirModels', absolute)
        self.assertEqual(self.family(absolute), first)
        self.assertFalse((absolute / 'models').exists())
        self.assertFalse((self.source / 'relative output').exists())

    def test_direct_root_overrides_game_cli_ce_and_qc_ce_regardless_of_order(self):
        direct = self.root / 'selected output'
        for args in (('-OutDir', 'ce-cli', '-OutDirModels', direct),
                     ('-OutDirModels', direct, '-OutDir', 'ce-cli'),
                     ('-OutDirModels', direct, '-game', self.game)):
            with self.subTest(args=args):
                self.compile(*args, extra='$OutDir ce-qc\n')
                self.assert_no_other_outputs(direct)
        self.assertFalse((self.source / 'ce-cli').exists())
        self.assertFalse((self.source / 'ce-qc').exists())
        self.assertFalse((self.game / 'models').exists())

    def test_ce_and_default_output_keep_existing_semantics(self):
        self.compile('-OutDir', 'ce-cli')
        self.family(self.source / 'ce-cli/models')
        self.compile(extra='$OutDir ce-qc\n')
        self.family(self.source / 'ce-qc/models')
        self.compile()
        self.family(self.game / 'models')
        self.compile(game=False)
        self.family(self.source / 'models')

    def test_direct_output_can_compile_without_game_and_directory_can_end_in_qc(self):
        # Known-option argument scanning must not mistake this directory for a QC.
        direct = self.cwd / 'output.qc'
        self.compile('-OutDirModels', 'output.qc', game=False)
        self.family(direct)
        self.assert_no_other_outputs(direct)

    def test_missing_direct_path_rejected_without_replacing_existing_output(self):
        direct = self.root / 'selected'
        self.compile('-OutDirModels', direct)
        old = self.family(direct)
        for values in ((), ('',), ('-nodx80',)):
            with self.subTest(values=values):
                log = self.compile('-OutDirModels', direct, '-OutDirModels', *values, success=False)
                self.assertIn('bad option', log)
                self.assertEqual(self.family(direct), old)

    def test_recompile_reads_sequence_order_from_direct_root(self):
        first = '$sequence first mesh.smd\n$sequence second mesh.smd\n'
        reversed_ = '$sequence second mesh.smd\n$sequence first mesh.smd\n'
        direct = self.root / 'direct'
        self.compile('-OutDirModels', direct, '-noremap', sequence_text=first)
        # A competing model in the default game output must not supply the order.
        self.compile('-noremap', sequence_text=reversed_)
        self.compile('-OutDirModels', direct, sequence_text=reversed_)
        self.assertEqual(sequences(direct / 'nested/probe.mdl'), ['first', 'second'])
        self.assertEqual(sequences(self.game / 'models/nested/probe.mdl'), ['second', 'first'])

    def test_reports_list_and_protect_the_actual_direct_outputs(self):
        direct = self.root / 'direct'
        report = self.root / 'dependencies.json'
        self.compile('-OutDirModels', direct, '-dependencyjson', report)
        result = json.loads(report.read_text())
        self.assertTrue(result['success'])
        self.assertEqual({Path(x['path']).resolve() for x in result['outputs']},
                         {(direct / ('nested/probe' + suffix)).resolve() for suffix in FAMILY})
        old = self.family(direct)
        for option in ('-perfjson', '-dependencyjson'):
            with self.subTest(option=option):
                self.compile('-OutDirModels', direct, option, direct / 'nested/probe.mdl', success=False)
                self.assertEqual(self.family(direct), old)

    def test_recovery_uses_direct_root_before_sequence_remap(self):
        direct = self.root / 'direct'
        first = '$sequence first mesh.smd\n$sequence second mesh.smd\n'
        reversed_ = '$sequence second mesh.smd\n$sequence first mesh.smd\n'
        self.compile('-OutDirModels', direct, sequence_text=first)
        entries = []
        for i, path in enumerate(sorted((direct / 'nested').glob('probe.*'))):
            old, new = path.read_bytes(), b'interrupted replacement ' + path.suffix.encode()
            entries.append((path.relative_to(direct).as_posix(), old, new))
            path.rename(str(path) + f'.npmdl-123456789-{i}.backup')
            path.write_bytes(new)
        (direct / 'nested/probe.mdl.npmdl-journal').write_text(journal_text(entries))
        log = self.compile('-OutDirModels', direct, sequence_text=reversed_)
        self.assertIn('Recovered interrupted output transaction', log)
        self.assertEqual(sequences(direct / 'nested/probe.mdl'), ['first', 'second'])
        self.assertFalse(list(direct.rglob('*.npmdl-*')))

    def test_failed_compile_keeps_direct_model_family(self):
        direct = self.root / 'direct'
        self.compile('-OutDirModels', direct)
        old = self.family(direct)
        self.compile('-OutDirModels', direct, '-MDLOutputBufferSize', '.0001', success=False)
        self.assertEqual(self.family(direct), old)

    def test_animation_and_physics_sidecars_share_direct_root(self):
        tetra = HEADER + 'time 0\n0 0 0 0 0 0 0\nend\ntriangles\n'
        for face in (((0, 0, 0), (0, 1, 0), (1, 0, 0)),
                     ((0, 0, 0), (1, 0, 0), (0, 0, 1)),
                     ((0, 0, 0), (0, 0, 1), (0, 1, 0)),
                     ((1, 0, 0), (0, 1, 0), (0, 0, 1))):
            tetra += 'material\n' + ''.join(f'0 {x} {y} {z} 0 0 1 0 0\n' for x, y, z in face)
        (self.source / 'tetra.smd').write_text(tetra + 'end\n')
        (self.source / 'anim.smd').write_text(HEADER + ''.join(
            f'time {i}\n0 {i * .31} 0 0 0 0 {i * .017}\n' for i in range(30)) + 'end\n')
        direct = self.root / 'direct'
        report = self.root / 'dependencies.json'
        self.compile('-OutDirModels', direct, '-dependencyjson', report,
                     sequence_text='$sequence idle anim.smd\n',
                     extra='$animblocksize 1\n$internalname alternate/inner.mdl\n'
                           '$phyname alternate/collision\n$collisionmodel tetra.smd { $mass 10 }\n')
        self.family(direct)
        self.assertTrue((direct / 'alternate/inner.ani').is_file())
        self.assertTrue((direct / 'alternate/collision.phy').is_file())
        recorded = {Path(x['path']).resolve() for x in json.loads(report.read_text())['outputs']}
        self.assertIn((direct / 'alternate/inner.ani').resolve(), recorded)
        self.assertIn((direct / 'alternate/collision.phy').resolve(), recorded)
        self.assertFalse((direct / 'models').exists())
        self.assertFalse((self.game / 'models').exists())


if __name__ == '__main__':
    unittest.main()
