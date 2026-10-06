"""Black-box regression tests. Usage: python tests/compatibility.py <mdlcompiler>.

Tests inspect emitted MDL headers instead of merely checking command registration.
All fixtures and outputs are isolated in a temporary directory.
"""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

COMPILER = str(Path(sys.argv.pop(1)).resolve())


class Compatibility(unittest.TestCase):
    def test_branding_and_clean_captured_output(self):
        output = self.run_qc('$modelname branding\n', '-verify')
        self.assertIn('NewPageMergeMDL | Model Compiler', output)
        self.assertIn('[ SOURCE MODEL FORGE ]', output)
        self.assertNotIn('\x1b[', output)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.write("mesh.smd", 'version 1\nnodes\n0 "root" -1\n1 "unused_child" 0\nend\n'
                   'skeleton\ntime 0\n0 0 0 0 0 0 0\n1 0 0 1 0 0 0\nend\n'
                   'triangles\nmaterial\n0 0 0 0 0 0 1 0 0\n'
                   '0 1 0 0 0 0 1 1 0\n0 0 1 0 0 0 1 0 1\nend\n')

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_qc(self, text, *args, success=True):
        qc = self.write("test.qc", text + '\n$body mesh "mesh.smd"\n')
        result = subprocess.run([COMPILER, str(qc), "-game", str(self.root), *args],
                                capture_output=True, text=True, errors="replace")
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def mdl(self, name):
        return (self.root / "models" / (name + ".mdl")).read_bytes()

    def sequences(self, name):
        data = self.mdl(name)
        count, index = struct.unpack_from('<2i', data, 188)
        result = []
        for i in range(count):
            offset = index + i * 212
            label = offset + struct.unpack_from('<i', data, offset + 4)[0]
            name = data[label:data.index(b'\0', label)].decode()
            result.append((name, struct.unpack_from('<i', data, offset + 12)[0], offset))
        return result

    def test_gmtime_exact_flags_and_decompile_round_trip(self):
        self.run_qc('$modelname utc\n$sequence idle mesh.smd gmtime loop\n')
        self.assertEqual(self.sequences('utc')[0][1] & 0x100101, 0x100101)
        compiler = Path(COMPILER)
        decompiler = compiler.with_name('NewPageMergeMDL-Decompiler' + compiler.suffix)
        result = subprocess.run([str(decompiler), str(self.root / 'models/utc.mdl'), '-pulseqc',
                                 '-outdir', str(self.root / 'utc-decompiled')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        qc = next((self.root / 'utc-decompiled').rglob('*.pulseqc'))
        self.assertIn('gmtime', qc.read_text())
        result = subprocess.run([COMPILER, str(qc), '-game', str(self.root / 'roundtrip')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = (self.root / 'roundtrip/models/utc.mdl').read_bytes()
        index = struct.unpack_from('<i', data, 192)[0]
        self.assertEqual(struct.unpack_from('<i', data, index + 12)[0] & 0x100101, 0x100101)

    def test_default_sequence_remap_and_noremap_opt_out(self):
        self.run_qc('$modelname ordering\n$sequence Idle mesh.smd\n$sequence walk mesh.smd\n')
        reversed_qc = '$modelname ordering\n$sequence walk mesh.smd\n$sequence idle mesh.smd\n'
        self.run_qc(reversed_qc)
        self.assertEqual([s[0] for s in self.sequences('ordering')], ['idle', 'walk'])
        self.run_qc(reversed_qc, '-noremap')
        self.assertEqual([s[0] for s in self.sequences('ordering')], ['walk', 'idle'])

    def test_sequence_remap_removes_missing_names_and_appends_new_names(self):
        self.run_qc('$modelname ordering\n$sequence idle mesh.smd\n$sequence walk mesh.smd\n$sequence fire mesh.smd\n')
        self.run_qc('$modelname ordering\n$sequence run mesh.smd\n$sequence walk mesh.smd\n')
        self.assertEqual([s[0] for s in self.sequences('ordering')], ['walk', 'run'])

    def test_sequence_remap_updates_autolayer_indices_and_accepts_v48_header(self):
        self.run_qc('$modelname layered\n$sequence layer mesh.smd\n'
                    '$sequence base mesh.smd { addlayer layer }\n')
        path = self.root / 'models/layered.mdl'
        data = bytearray(path.read_bytes())
        struct.pack_into('<i', data, 4, 48)
        path.write_bytes(data)
        qc = '$modelname layered\n$sequence base mesh.smd { addlayer layer }\n$sequence layer mesh.smd\n'
        self.run_qc(qc)
        sequences = self.sequences('layered')
        self.assertEqual([s[0] for s in sequences], ['layer', 'base'])
        data = self.mdl('layered')
        count, index = struct.unpack_from('<2i', data, sequences[1][2] + 148)
        self.assertEqual(count, 1)
        self.assertEqual(struct.unpack_from('<h', data, sequences[1][2] + index)[0], 0)
        self.run_qc(qc, '-noremap')
        sequences = self.sequences('layered')
        self.assertEqual([s[0] for s in sequences], ['base', 'layer'])
        data = self.mdl('layered')
        index = struct.unpack_from('<i', data, sequences[0][2] + 152)[0]
        self.assertEqual(struct.unpack_from('<h', data, sequences[0][2] + index)[0], 1)

    def test_invalid_existing_model_offsets_do_not_crash_or_control_output(self):
        self.run_qc('$modelname ordering\n$sequence idle mesh.smd\n')
        path = self.root / 'models/ordering.mdl'
        data = bytearray(path.read_bytes())
        struct.pack_into('<i', data, 192, 0x7fffffff)
        path.write_bytes(data)
        output = self.run_qc('$modelname ordering\n$sequence walk mesh.smd\n$sequence idle mesh.smd\n')
        self.assertIn('Cannot preserve sequence order', output)
        self.assertEqual([s[0] for s in self.sequences('ordering')], ['walk', 'idle'])

    def vta_keys(self, options, stereo=False):
        self.write('face.vta', 'version 1\nnodes\n0 "root" -1\nend\n'
                   'skeleton\ntime 0\n0 0 0 0 0 0 0\ntime 1\n0 0 0 0 0 0 0\n'
                   'time 2\n0 0 0 0 0 0 0\nend\nvertexanimation\n'
                   'time 0\n0 0 0 0 0 0 1\n1 1 0 0 0 0 1\n2 0 1 0 0 0 1\n'
                   'time 1\n0 0 0 0.25 0 0 1\n1 1 0 0.4 0 0 1\n'
                   'time 2\n0 0 0 0.5 0 0 1\n1 1 0 0.8 0 0 1\nend\n')
        rules = '%sharedL = strength\n%sharedR = strength' if stereo else '%shared = strength'
        self.run_qc('$modelname face\n$model face "mesh.smd" {\n'
                    'flexfile "face.vta" {\n' + options + '\n}\n'
                    'flexcontroller test range 0 1 strength\n' + rules + '\n}\n')
        data = self.mdl('face')
        body = struct.unpack_from('<i', data, 236)[0]
        model = body + struct.unpack_from('<i', data, body + 12)[0]
        mesh = model + struct.unpack_from('<i', data, model + 76)[0]
        count, index = struct.unpack_from('<2i', data, mesh + 16)
        keys = []
        for i in range(count):
            offset = mesh + index + i * 60
            desc = struct.unpack_from('<i', data, offset)[0]
            targets = struct.unpack_from('<4f', data, offset + 4)
            vertices, vanim = struct.unpack_from('<2i', data, offset + 20)
            pair = struct.unpack_from('<i', data, offset + 28)[0]
            heights = [struct.unpack_from('<e', data, offset + vanim + j * 16 + 8)[0]
                       for j in range(vertices)]
            sides = [data[offset + vanim + j * 16 + 3] for j in range(vertices)]
            keys.append((desc, pair, targets, heights, sides))
        return keys

    def test_repeated_vta_name_preserves_distinct_frame_deltas_and_equal_position_order(self):
        keys = self.vta_keys('flex "shared" frame 1\nflex "shared" frame 2')
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0][0], keys[1][0])
        self.assertEqual(keys[0][2], (0, 1, 1, 1))
        self.assertEqual(keys[1][2], (1, 1, 10, 11))
        self.assertAlmostEqual(max(keys[1][3]), 2 * max(keys[0][3]), places=3)

    def test_repeated_stereo_vta_name_preserves_pair_balance_and_progressive_positions(self):
        keys = self.vta_keys('flexpair "shared" 1 frame 1 position 0.5\n'
                             'flexpair "shared" 1 frame 2 position 1', stereo=True)
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0][:2], keys[1][:2])
        self.assertNotEqual(keys[0][0], keys[0][1])
        self.assertEqual(keys[0][2], (0, 0.5, 0.5, 1))
        self.assertEqual(keys[1][2], (0.5, 1, 10, 11))
        self.assertEqual(keys[0][4], keys[1][4])
        self.assertGreater(len(set(keys[0][4])), 1)
        self.assertAlmostEqual(max(keys[1][3]), 2 * max(keys[0][3]), places=3)

    def test_repeated_vta_positions_keep_ce_declaration_order(self):
        keys = self.vta_keys('flex "shared" frame 2 position 1\n'
                             'flex "shared" frame 1 position 0.5')
        self.assertEqual(keys[0][2], (0, 1, 1, 0.5))
        self.assertEqual(keys[1][2], (1, 0.5, 10, 11))
        self.assertAlmostEqual(max(keys[0][3]), 2 * max(keys[1][3]), places=3)

    def test_variable_assignment_and_replacement(self):
        self.run_qc('$setvariable name first\n$setvariable name replaced\n$modelname "$name$.mdl"\n')
        self.assertEqual(self.mdl("replaced")[:4], b"IDST")

    def test_launch_variable_stays_pinned(self):
        self.run_qc('$setvariable name ignored\n$modelname "$name$.mdl"\n',
                    "-defvar", "name", "pinned")
        self.mdl("pinned")

    def test_duplicate_define_warns_and_preserves_first_value(self):
        text = self.run_qc('$definevariable name first\n$definevariable name second\n'
                           '$modelname "$name$.mdl"\n')
        self.assertIn("WARNING:", text)
        self.mdl("first")

    def test_prefixed_include_in_subdirectory(self):
        self.write("inc/pre_child.qci", '$setvariable name included\n')
        self.run_qc('$IncludePrefix "inc/child.qci" "pre_"\n'
                    '$include "inc/child.qci"\n$modelname "$name$.mdl"\n')
        self.mdl("included")

    def test_pushd_include_and_nested_include(self):
        self.write("other/child.qci", '$include "nested.qci"\n')
        self.write("other/nested.qci", '$setvariable name nested\n')
        self.write("child.qci", '$setvariable name wrong\n')
        self.run_qc('$PUSHDInclude 1\n$pushd "other"\n$include "child.qci"\n'
                    '$popd\n$modelname "$name$.mdl"\n')
        self.mdl("nested")

    def test_include_animation_prefix(self):
        self.run_qc('$modelname include_test\n$IncludeAnimPrefix "pre_"\n'
                    '$includemodel "folder/anim.mdl"\n')
        data = self.mdl("include_test")
        self.assertIn(b"models/folder/pre_anim.mdl\x00", data)
        self.assertEqual(struct.unpack_from("<i", data, 336)[0], 1)

    def test_mostlyopaque_launch_overrides_qc(self):
        self.run_qc('$modelname opaque\n$opaque\n', "-MostlyOpaque")
        flags = struct.unpack_from("<i", self.mdl("opaque"), 152)[0]
        self.assertTrue(flags & 8)
        self.assertFalse(flags & 4)

    def test_invalid_pushd_value(self):
        text = self.run_qc('$modelname bad\n$PUSHDInclude 2\n', success=False)
        self.assertIn("expected 0 or 1", text)

    def test_empty_collapse_prefix_is_rejected(self):
        text = self.run_qc('$modelname bad\n$AlwaysCollapseByPrefix ""\n', success=False)
        self.assertIn("empty prefix", text)

    def test_missing_launch_prefix_is_rejected(self):
        text = self.run_qc('$modelname bad\n', "-AlwaysCollapseByPrefix", success=False)
        self.assertIn("needs a non-empty prefix", text)

    def test_collapse_prefix_changes_output_skeleton(self):
        qc = '$modelname bones\n$bonecullmethod none\n'
        self.run_qc(qc)
        before = struct.unpack_from("<i", self.mdl("bones"), 156)[0]
        self.run_qc(qc, "-AlwaysCollapseByPrefix", "UNUSED_")
        after = struct.unpack_from("<i", self.mdl("bones"), 156)[0]
        self.assertEqual(before, 2)
        self.assertEqual(after, 1)
        self.run_qc(qc + '$AlwaysCollapseByPrefix unused_\n')
        self.assertEqual(struct.unpack_from("<i", self.mdl("bones"), 156)[0], after)

    def test_animation_culling_launch_override_and_nocull(self):
        qc = ('$modelname anims\n$animationcullmethod none\n'
              '$animation used "mesh.smd" fps 30\n'
              '$animation unused "mesh.smd" fps 12\n$sequence idle used\n')
        self.run_qc(qc)
        self.assertEqual(struct.unpack_from("<i", self.mdl("anims"), 180)[0], 2)
        self.run_qc(qc, "-cullanims")
        self.assertEqual(struct.unpack_from("<i", self.mdl("anims"), 180)[0], 1)
        self.run_qc(qc.replace('fps 12', 'fps 12 nocull'), "-cullanims")
        self.assertEqual(struct.unpack_from("<i", self.mdl("anims"), 180)[0], 2)

    def test_macro_defaults_and_variable_fallback(self):
        self.run_qc('$definevariable dir macro\n$definemacro emit name=default\n'
                    '$modelname "$dir$/$name$.mdl"\n$endmacro\n$emit\n')
        self.mdl("macro/default")

    def test_circular_prefixed_include_is_rejected(self):
        self.write("pre_loop.qci", '$include "loop.qci"\n')
        text = self.run_qc('$modelname bad\n$IncludePrefix loop.qci pre_\n'
                           '$include loop.qci\n', success=False)
        self.assertIn("circular include", text)

    def animation_fixture(self):
        self.write("moving.smd", 'version 1\nnodes\n0 "root" -1\nend\n'
                   'skeleton\ntime 0\n0 10 0 0 0 0 0.5\n'
                   'time 1\n0 20 0 0 0 0 1.0\nend\n')

    def animation_poses(self, model, name):
        compiler_path = Path(COMPILER)
        decompiler = str(compiler_path.with_name("NewPageMergeMDL-Decompiler" + compiler_path.suffix))
        result = subprocess.run([decompiler, str(self.root / 'models' / (model+'.mdl')),
                                 '-smdanimation', '-outdir', str(self.root / 'decompiled')],
                                capture_output=True, text=True, errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        files = list((self.root / 'decompiled').rglob(name+'.smd'))
        self.assertEqual(len(files), 1, str(list((self.root / 'decompiled').rglob('*.smd'))))
        frames = []
        in_skeleton = False
        for line in files[0].read_text().splitlines():
            if line.strip() == 'skeleton': in_skeleton = True
            elif line.strip() == 'end': in_skeleton = False
            elif in_skeleton:
                values = line.split()
                if len(values) == 7 and values[0] == '0':
                    frames.append(tuple(float(v) for v in values[1:]))
        return frames

    def test_animation_conditions_select_only_one_branch(self):
        self.animation_fixture()
        self.run_qc('$modelname conditions\n$setvariable mode 2\n'
                    '$animation clip "moving.smd" {\n'
                    'if mode == 1 { unknown_unselected_option }\n'
                    'else if mode == 2 { if 1 { numframes 4 } }\n'
                    'else { unknown_unselected_option }\n}\n$sequence idle clip\n')
        self.assertEqual(len(self.animation_poses('conditions', 'clip')), 4)

    def test_animation_copy_copies_motion_and_holds_last_frame(self):
        self.animation_fixture()
        self.run_qc('$modelname copying\n$animationcullmethod none\n'
                    '$animation source "moving.smd"\n'
                    '$animation dest "mesh.smd" { numframes 4 copy source }\n'
                    '$sequence idle dest\n')
        src = self.animation_poses('copying', 'source')
        dst = self.animation_poses('copying', 'dest')
        self.assertEqual(len(dst), 4)
        for actual, expected in zip(dst, [src[0], src[1], src[1], src[1]]):
            for a, b in zip(actual, expected): self.assertAlmostEqual(a, b, places=3)

    def test_copy_self_reference_rejected(self):
        text = self.run_qc('$modelname bad\n$animation clip "mesh.smd" copy clip\n'
                           '$sequence idle clip\n', success=False)
        self.assertIn('requires an earlier animation', text)

    def test_animation_match_position_preserves_rotation(self):
        self.animation_fixture()
        self.run_qc('$modelname matching\n$animationcullmethod none\n'
                    '$animation source "moving.smd"\n'
                    '$animation dest "mesh.smd" match source pos\n'
                    '$sequence idle dest\n')
        src = self.animation_poses('matching', 'source')[0]
        dst = self.animation_poses('matching', 'dest')[0]
        # The two clips may choose different MDL quantization scales.
        for a, b in zip(src[:3], dst[:3]): self.assertAlmostEqual(a, b, delta=0.01)
        self.assertGreater(abs(src[5]-dst[5]), 0.1)

    def test_match_rotation_and_default_agree(self):
        self.animation_fixture()
        self.run_qc('$modelname rotations\n$animationcullmethod none\n'
                    '$animation source "moving.smd"\n'
                    '$animation explicit "mesh.smd" match source rot\n'
                    '$animation implicit "mesh.smd" match source\n'
                    '$sequence idle explicit\n')
        explicit = self.animation_poses('rotations', 'explicit')[0]
        implicit = self.animation_poses('rotations', 'implicit')[0]
        source = self.animation_poses('rotations', 'source')[0]
        for a, b in zip(explicit, implicit): self.assertAlmostEqual(a, b, delta=0.01)
        for a, b in zip(explicit[3:], source[3:]): self.assertAlmostEqual(a, b, delta=0.01)
        self.assertGreater(abs(explicit[0]-source[0]), 1.0)

    def test_copy_position_does_not_copy_rotation(self):
        self.animation_fixture()
        self.run_qc('$modelname channels\n$animationcullmethod none\n'
                    '$animation source "moving.smd"\n'
                    '$animation dest "mesh.smd" copy source pos\n$sequence idle dest\n')
        src = self.animation_poses('channels', 'source')[0]
        dst = self.animation_poses('channels', 'dest')[0]
        for a, b in zip(src[:3], dst[:3]): self.assertAlmostEqual(a, b, delta=0.01)
        self.assertGreater(abs(src[5]-dst[5]), 0.1)

    def test_animation_condition_missing_brace_is_error(self):
        text = self.run_qc('$modelname bad\n$animation clip "mesh.smd" { if 1 fps 12 }\n'
                           '$sequence idle clip\n', success=False)
        self.assertIn('missing', text)

    def test_animation_else_without_if_is_error(self):
        text = self.run_qc('$modelname bad\n$animation clip "mesh.smd" { else { fps 12 } }\n'
                           '$sequence idle clip\n', success=False)
        self.assertIn('else without', text)


if __name__ == "__main__":
    unittest.main()
