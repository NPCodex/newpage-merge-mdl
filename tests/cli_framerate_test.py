"""CLI rejection/output preservation and fractional DMX animation round trips."""
from pathlib import Path
import math
import re
import struct
import subprocess
import sys
import tempfile
import unittest

COMPILER = Path(sys.argv.pop(1)).resolve()
DECOMPILER = Path(sys.argv.pop(1)).resolve()
HEADER = 'version 1\nnodes\n0 "root" -1\nend\nskeleton\n'


class Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='np-cli-fps-')
        self.root = Path(self.tmp.name)
        (self.root / 'gameinfo.txt').write_text('GameInfo { FileSystem { SteamAppId 220 SearchPaths { Game "|gameinfo_path|." } } }')
        (self.root / 'mesh.smd').write_text(HEADER + 'time 0\n0 0 0 0 0 0 0\nend\ntriangles\nmaterial\n0 0 0 0 0 0 1 0 0\n0 1 0 0 0 0 1 1 0\n0 0 1 0 0 0 1 0 1\nend\n')
        (self.root / 'motion.smd').write_text(HEADER + ''.join(
            f'time {i}\n0 {math.sin(i * .21) * 3:.9f} 0 0 0 0 {math.sin(i * .13) * .3:.9f}\n'
            for i in range(47)) + 'end\n')
        self.qc = self.root / 'model.qc'
        self.qc.write_text('$modelname model\n$definebone root "" 0 0 0 0 0 0 0 0 0 0 0 0\n$body m mesh.smd\n$sequence motion motion.smd fps 23.7\n')

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args, success=True):
        p = subprocess.run(list(map(str, args)), capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=60)
        self.assertEqual(p.returncode == 0, success, p.stdout + p.stderr)
        return p.stdout + p.stderr

    def compile(self, *args, success=True):
        return self.run_tool(COMPILER, self.qc, '-game', self.root, *args, success=success)

    def outputs(self):
        return {p.name: p.read_bytes() for p in (self.root / 'models').glob('model.*')}

    def test_cli_rejects_complete_bad_numbers_without_replacing_output(self):
        self.compile()
        old = self.outputs()
        cases = [('-vtxformat', x) for x in ('banana', '1garbage', '1.0', '+-0', '2', '999999999999999999999', '')]
        cases += [('-minlod', x) for x in ('1suffix', '-1', '1e1', ' 1', '2147483648')]
        cases += [('-maxbones', x) for x in ('1suffix', '257', '1.5')]
        cases += [(option, x) for option in ('-EyeballScale', '-OutputBufferSize', '-MDLOutputBufferSize', '-ANIOutputBufferSize')
                  for x in ('1suffix', '+-1', 'nan', 'inf', '0', '1e40')]
        for args in cases:
            with self.subTest(args=args):
                self.assertIn('bad option', self.compile(*args, success=False))
                self.assertEqual(self.outputs(), old)
        self.compile('-VTXFORMAT', '1', '-minlod', '+0', '-EyeballScale', '1e0')

    def test_uppercase_named_d_options_are_not_macro_definitions(self):
        for option in ('-DEFINEBONES', '-DUMPDEPENDENCIES', '-DUMPMATERIALS', '-DUMPPROCEDURAL'):
            with self.subTest(option=option):
                self.compile(option)
        self.compile('-DEFVAR', 'unused', 'value', '-Dsample', 'another')

    def test_required_cli_values_are_not_swallowed(self):
        self.compile()
        old = self.outputs()
        for option in ('-game', '-steamdir', '-perfjson', '-vtxformat', '-modelname', '-outdir',
                       '-includesearchdir', '-filesearchdir', '-tempcontent', '-defvar', '-Dsample',
                       '-IncludePrefix', '-IncludeAnimPrefix', '-maxbones', '-minlod'):
            for suffix in ([], ['-nodx80']):
                with self.subTest(option=option, suffix=suffix):
                    self.assertIn('bad option', self.compile(option, *suffix, success=False))
                    self.assertEqual(self.outputs(), old)

    def test_defaults_receive_the_same_numeric_validation(self):
        self.compile()
        old = self.outputs()
        (self.root / 'gameinfo.txt').write_text('GameInfo { Tools { studiomdl "-vtxformat 1garbage" } FileSystem { SteamAppId 220 SearchPaths { Game "|gameinfo_path|." } } }')
        self.assertIn('bad option', self.compile(success=False))
        self.assertEqual(self.outputs(), old)
        self.compile('-nodefaultargs')

    def test_decompiler_numeric_and_missing_arguments_preserve_tree(self):
        self.compile()
        destination = self.root / 'decoded'
        destination.mkdir()
        marker = destination / 'keep.txt'
        marker.write_bytes(b'previous user file')
        mdl = self.root / 'models/model.mdl'
        for option, value in [('-forceversion', '49junk'), ('-forceversion', '999999999999'), ('-dmxmodel', '15junk')]:
            self.assertIn('command line', self.run_tool(DECOMPILER, mdl, '-outdir', destination, option, value, success=False))
        for option in ('-outdir', '-forceversion', '-dmxmodel', '-dmxencoding'):
            for suffix in ([], ['-noanimation']):
                self.assertIn('command line', self.run_tool(DECOMPILER, mdl, '-outdir', destination, option, *suffix, success=False))
        self.assertEqual(list(destination.iterdir()), [marker])
        self.assertEqual(marker.read_bytes(), b'previous user file')

    def poses(self, mdl, directory):
        self.run_tool(DECOMPILER, mdl, '-outdir', directory, '-smdanimation')
        smd = next(directory.rglob('motion.smd')).read_text()
        skeleton = smd.split('skeleton\n', 1)[1].split('end', 1)[0]
        return [[float(v) for v in line.split()[1:]] for line in skeleton.splitlines() if line.startswith('0 ')]

    def test_fractional_fps_time_axis_and_roundtrip_all_dmx_formats(self):
        for rate in (23.7, 29.97, 60000 / 1001, 30):
            self.qc.write_text(re.sub(r'fps [^\n]+', f'fps {rate:.9f}', self.qc.read_text()))
            self.compile()
            mdl = self.root / 'models/model.mdl'
            original = self.poses(mdl, self.root / f'original-{rate}')
            for model in (1, 15, 18, 22):
                for encoding in ('keyvalues2', 'binary'):
                    with self.subTest(rate=rate, model=model, encoding=encoding):
                        destination = self.root / f'dmx-{rate}-{model}-{encoding}'
                        self.run_tool(DECOMPILER, mdl, '-outdir', destination, '-dmxmodel', model, '-dmxencoding', encoding)
                        animation = next(destination.rglob('motion.dmx'))
                        if encoding == 'keyvalues2':
                            text = animation.read_text()
                            match = re.search(r'"frameRate"\s+"(?:float|int)"\s+"([^"]+)"', text)
                            self.assertIsNotNone(match, text[:200])
                            self.assertAlmostEqual(float(match[1]), rate, delta=1e-5)
                            duration = re.search(r'"duration(?:Time)?"\s+"(?:time|int)"\s+"([^"]+)"', text)
                            self.assertIsNotNone(duration)
                            actual = float(duration[1]) / (10000 if model == 1 else 1)
                            self.assertAlmostEqual(actual, 46 / rate, delta=.00006)
                        scripts = list(destination.rglob('*.qc')) + list(destination.rglob('*.pulseqc'))
                        self.assertEqual(len(scripts), 1)
                        roundtrip = self.root / f'roundtrip-{rate}-{model}-{encoding}'
                        self.run_tool(COMPILER, scripts[0], '-game', self.root, '-OutDir', roundtrip)
                        rebuilt = next(roundtrip.rglob('model.mdl'))
                        data = rebuilt.read_bytes()
                        count, offset = struct.unpack_from('<2i', data, 180)
                        self.assertEqual(count, 1)
                        self.assertAlmostEqual(struct.unpack_from('<f', data, offset + 8)[0], rate, delta=1e-5)
                        frames = self.poses(rebuilt, roundtrip / 'decoded')
                        self.assertEqual(len(frames), len(original))
                        self.assertLess(max(abs(x-y) for a,b in zip(frames, original) for x,y in zip(a,b)), .002)


if __name__ == '__main__':
    unittest.main()
