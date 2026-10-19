"""Distinct targets with same-named clips must survive one L4D -all batch."""
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest

COMPILER = Path(sys.argv.pop(1)).resolve()
TOOL = Path(sys.argv.pop(1)).resolve()
HEADER = 'version 1\nnodes\n0 "root" -1\nend\nskeleton\n'


class RetargetNames(unittest.TestCase):
    def run_tool(self, *arguments):
        result = subprocess.run(list(map(str, arguments)), capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).decode('utf-8', 'replace'))

    def make_model(self, root, name, distance, final_sequence, fps=30):
        source = root / name
        source.mkdir()
        (source/'mesh.smd').write_text(HEADER+'time 0\n0 0 0 0 0 0 0\nend\ntriangles\nmaterial\n0 0 0 0 0 0 1 0 0\n0 1 0 0 0 0 1 1 0\n0 0 1 0 0 0 1 0 1\nend\n')
        (source/'anim.smd').write_text(HEADER+''.join(f'time {i}\n0 {i*distance} 0 0 0 0 0\n' for i in range(4))+'end\n')
        qc = source/'model.qc'
        qc.write_text(f'$modelname {name}\n$definebone root "" 0 0 0 0 0 0 0 0 0 0 0 0\n$body m mesh.smd\n$sequence idle anim.smd\n$sequence walk anim.smd\n$sequence {final_sequence} anim.smd fps {fps}\n')
        self.run_tool(COMPILER, '-game', source, qc)
        return (source/'models'/f'{name}.mdl').read_bytes()

    def clip(self, qci, light):
        text = qci.read_text(encoding='utf-8')
        paths = re.findall(r'"(anims/[^"\n]+\.dmx)"', text)
        matches = [p for p in paths if 'c1m1_intro' in p and ('_light' in p) == light]
        self.assertEqual(len(matches), 1, text)
        path = qci.parent/matches[0]
        self.assertTrue(path.is_file(), path)
        return matches[0], path.read_bytes()

    def test_all_keeps_body_and_light_clips_for_each_target(self):
        with tempfile.TemporaryDirectory(prefix='np-l4d-names-') as directory:
            root = Path(directory)
            rig = self.make_model(root, 'rig', 1, 'run')
            first = self.make_model(root, 'first', 2, 'c1m1_intro')
            second = self.make_model(root, 'second', 7, 'c1m1_intro')
            vanilla = root/'vanilla'
            vanilla.mkdir()
            for code in ('teenangst','producer','namvet','biker','manager','coach','gambler','mechanic'):
                (vanilla/f'survivor_{code}.mdl').write_bytes(rig)
            for code, data in (('producer', first), ('gambler', second)):
                # Identical sequence names refer to genuinely different motion.
                include = 'anim_'+code+'.mdl'
                (vanilla/include).write_bytes(data)
                model = bytearray(data)
                struct.pack_into('<2i', model, 336, 1, len(model))
                model.extend(struct.pack('<2i', 0, 8)+include.encode()+b'\0')
                struct.pack_into('<i', model, 76, len(model))
                (vanilla/f'survivor_{code}.mdl').write_bytes(model)
                (vanilla/f'survivor_{code}_light.mdl').write_bytes(data)
            references = {}
            for target in ('rochelle', 'nick'):
                output = root/target/'swap.qci'
                self.run_tool(TOOL, '-vanilla', vanilla, '-rig', 'zoey', '-replace', target,
                              '-retarget', '-keepintro', '-o', output)
                for light in (False, True):
                    qci = output.with_stem(output.stem+'_Light') if light else output
                    references[target, light] = self.clip(qci, light)
            # Sensitivity: each pair's standalone result has different motion.
            for light in (False, True):
                self.assertNotEqual(references['rochelle',light][1], references['nick',light][1])
            batch = root/'batch'
            self.run_tool(TOOL, '-vanilla', vanilla, '-all', '-retarget', '-keepintro', '-outdir', batch)
            for light in (False, True):
                paths = []
                for target in ('rochelle', 'nick'):
                    qci = batch/('Anims_RigToZoey_Replace'+target.capitalize()+('_Light' if light else '')+'.qci')
                    path, data = self.clip(qci, light)
                    paths.append(path)
                    self.assertEqual(data, references[target,light][1], f'{target} overwritten in -all (light={light})')
                self.assertEqual(len(set(paths)), 2, 'Different target models share a generated clip path')

    def test_fractional_source_fps_matches_retarget_qc_and_dmx(self):
        for fps in (23.976, 29.97, 23.7):
            with self.subTest(fps=fps), tempfile.TemporaryDirectory(prefix='np-l4d-fps-') as directory:
                root = Path(directory)
                rig = self.make_model(root, 'rig', 1, 'run')
                donor = self.make_model(root, 'donor', 2, 'c1m1_intro', fps=fps)
                vanilla = root/'vanilla'
                vanilla.mkdir()
                for code in ('teenangst', 'producer', 'namvet', 'biker', 'manager', 'coach', 'gambler', 'mechanic'):
                    (vanilla/f'survivor_{code}.mdl').write_bytes(rig)
                include = 'anim_producer.mdl'
                (vanilla/include).write_bytes(donor)
                target = bytearray(donor)
                struct.pack_into('<2i', target, 336, 1, len(target))
                target.extend(struct.pack('<2i', 0, 8)+include.encode()+b'\0')
                struct.pack_into('<i', target, 76, len(target))
                (vanilla/'survivor_producer.mdl').write_bytes(target)

                qci = root/'swap.qci'
                self.run_tool(TOOL, '-vanilla', vanilla, '-rig', 'zoey', '-replace', 'rochelle',
                              '-retarget', '-keepintro', '-dmxencoding', 'keyvalues2', '-o', qci)
                qc_text = qci.read_text(encoding='utf-8')
                qc_rate = re.search(r'\bfps\s+([0-9.]+)', qc_text)
                self.assertIsNotNone(qc_rate, qc_text)
                self.assertAlmostEqual(float(qc_rate.group(1)), fps, places=3)
                dmx_paths = re.findall(r'"(anims/[^"\n]*c1m1_intro[^"\n]*\.dmx)"', qc_text)
                self.assertTrue(dmx_paths, qc_text)
                dmx_text = (qci.parent/dmx_paths[0]).read_text(encoding='utf-8')
                rate = re.search(r'"frameRate"\s+"float"\s+"([^"]+)"', dmx_text)
                self.assertIsNotNone(rate, dmx_text[:1000])
                self.assertAlmostEqual(float(rate.group(1)), fps, places=3)
                duration = re.search(r'"duration"\s+"time"\s+"([^"]+)"', dmx_text)
                self.assertIsNotNone(duration, dmx_text[:1000])
                self.assertAlmostEqual(float(duration.group(1)), 3 / fps, delta=0.00005)


if __name__ == '__main__':
    unittest.main()
