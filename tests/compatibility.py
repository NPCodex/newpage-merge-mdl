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


    def ce_fixture(self):
        self.write('face.vta', 'version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\n'
                   'time 1\n0 0 0 0 0 0 0\ntime 2\n0 0 0 0 0 0 0\nend\nvertexanimation\n'
                   'time 0\n0 0 0 0 0 0 1\n1 1 0 0 0 0 1\n2 0 1 0 0 0 1\n'
                   'time 1\n0 0 0 .25 0 0 1\n1 1 0 .5 0 0 1\n'
                   'time 2\n0 0 0 .5 0 0 1\n1 1 0 1 0 0 1\nend\n')
        return 'flexfile face.vta {\ndefaultflex frame 0\nflex smile frame 1\n}\nflexcontroller test range 0 1 strength\n%smile = strength\n'

    def ce_data(self, name='face'):
        data=self.mdl(name)
        integer=lambda o:struct.unpack_from('<i',data,o)[0]
        string=lambda o:data[o:data.index(b'\0',o)].decode()
        desc=[string(integer(264)+i*4+integer(integer(264)+i*4)) for i in range(integer(260))]
        controllers=[]
        for i in range(integer(268)):
            p=integer(272)+i*20
            controllers.append((string(p+integer(p+4)),string(p+integer(p)),*struct.unpack_from('<2f',data,p+12)))
        keys=[]; eyes=[]; models=[]
        for b in range(integer(232)):
            bp=integer(236)+b*16
            for m in range(integer(bp+4)):
                model=bp+integer(bp+12)+m*148;models.append(model)
                for e in range(integer(model+100)):
                    p=model+integer(model+104)+e*172
                    eyes.append((string(p+integer(p)),struct.unpack_from('<3f',data,p+8),struct.unpack_from('<f',data,p+24)[0],struct.unpack_from('<f',data,p+60)[0]))
                for j in range(integer(model+72)):
                    mesh=model+integer(model+76)+j*116
                    for i in range(integer(mesh+16)):
                        p=mesh+integer(mesh+20)+i*60;v=p+integer(p+24);size=18 if data[p+32] else 16
                        keys.append(dict(name=desc[integer(p)],pair=integer(p+28),
                                    vertices=[(struct.unpack_from('<H',data,v+k*size)[0],data[v+k*size+2],
                                        struct.unpack_from('<6e',data,v+k*size+4),
                                        struct.unpack_from('<h',data,v+k*size+16)[0] if size==18 else None)
                                        for k in range(integer(p+20))]))
        rules=[]
        for i in range(integer(276)):
            p=integer(280)+i*12;op=p+integer(p+8)
            rules.append((desc[integer(p)], [struct.unpack_from('<ii',data,op+j*8) for j in range(integer(p+4))]))
        return controllers,keys,eyes,rules,models

    def ce_compile(self, global_options='', options=None, *args):
        block=self.ce_fixture() if options is None else options
        self.run_qc('$modelname face\n'+global_options+'\n$model face mesh.smd {\n'+block+'\n}\n',*args)
        return self.ce_data()

    def test_ce_controller_override_and_duplicate_tables(self):
        block=self.ce_fixture().replace('flexcontroller test range 0 1 strength',
                    'flexcontroller old range 0 1 strength\nflexcontroller new range -1 2 strength')
        for flag,expected in [('', [('strength','old',0,1)]),
                   ('$OverrideFlexControllers',[('strength','new',-1,2)]),
                   ('$AllowDuplicationFlexControllers',[('strength','old',0,1),('strength','new',-1,2)])]:
            with self.subTest(flag=flag): self.assertEqual(self.ce_compile(flag,block)[0],expected)
        self.assertEqual(self.ce_compile('',block,'-OvErRiDeFlExCoNtRoLlErS')[0],[('strength','new',-1,2)])

    def test_ce_inverse_geometry_rule_and_controller_range(self):
        controllers,keys,_,rules,_=self.ce_compile('$AddInvStudioFlexes')
        self.assertEqual(controllers,[('strength','test',-1,1)])
        original=next(k for k in keys if k['name']=='smile');inverse=next(k for k in keys if k['name']=='smile_Inv')
        for a,b in zip(original['vertices'],inverse['vertices']):
            for x,y in zip(a[2],b[2]):self.assertAlmostEqual(x,-y,places=4)
        rule=next(ops for name,ops in rules if name=='smile_Inv')
        self.assertEqual(rule[-2:],[(1,-1082130432),(6,0)])

    def test_ce_inverse_toggle_and_stereo_names(self):
        block=self.ce_fixture().replace('flex smile frame 1','InvertControllers\nflexpair smile 1 frame 1\nInvertControllers\nflex other frame 2')
        block=block.replace('%smile = strength','%smileL = strength\n%smileR = strength\n%other = strength')
        keys=self.ce_compile('',block)[1]
        self.assertEqual({k['name'] for k in keys},{'smileL','smile_InvL','other'})
        self.assertTrue(next(k for k in keys if k['name']=='smile_InvL')['pair'])

    def test_ce_fscale_overrides_tenfold_flex_strength(self):
        baseline=self.ce_compile()[1][0]['vertices']
        for flags,suffix,factor in [('$DefaqScale','',10),('$DefaqScale',' fscale 2',2),('',' fscale -1',-1)]:
            block=self.ce_fixture().replace('flex smile frame 1','flex smile frame 1'+suffix)
            result=self.ce_compile(flags,block)[1][0]['vertices']
            for a,b in zip(baseline,result):self.assertAlmostEqual(a[2][2]*factor,b[2][2],places=3)

    def test_ce_zero_decay_sets_all_vertex_speeds(self):
        baseline=self.ce_compile()[1][0]['vertices']
        self.assertLess(min(v[1] for v in baseline),255)
        result=self.ce_compile('$ZeroFlexDecay')[1][0]['vertices']
        self.assertEqual({v[1] for v in result},{255})

    def test_ce_auto_controller_range_and_toggle(self):
        self.ce_fixture()
        block='flexfile face.vta {\naddcontrollerbyflex generated -1 2\nflex smile frame 1\naddcontrollerbyflex\nflex other frame 2\n}\n%smile = smile\n'
        controllers,keys,_,_,_=self.ce_compile('',block)
        self.assertEqual(controllers,[('smile','generated',-1,2)])
        self.assertEqual([k['name'] for k in keys],['smile'])

    def test_ce_default_pose_bakes_mesh_and_rebases_flexes(self):
        block=self.ce_fixture().replace('defaultflex frame 0','defaultflex frame 1').replace('flex smile frame 1','flex smile frame 2')
        for flag,height in [('',.25),('$IgnoreDefaultFlexKey',.5)]:
            keys=self.ce_compile(flag,block)[1]
            self.assertEqual('default' in [k['name'] for k in keys],bool(flag))
            smile=next(k for k in keys if k['name']=='smile')
            self.assertAlmostEqual(smile['vertices'][0][2][2],height,places=3)
            vvd=(self.root/'models/face.vvd').read_bytes();p=struct.unpack_from('<i',vvd,56)[0]
            self.assertAlmostEqual(struct.unpack_from('<f',vvd,p+24)[0],0 if flag else .25)

    def test_ce_eye_scaling_and_independent_iris(self):
        block='eyeball eye root 1 2 3 material 2 0 iris .5\n'
        for flags,origin,radius,iris in [('$scale 2\n$EyeballScale 3',(3,6,9),1,2/3),
                        ('$scale 2\n$IgnoreEyeballScaling',(1,2,3),1,2),
                        ('$scale 2\n$EyeballScale 3\n$IgnoreEyeballIrisScale',(3,6,9),1,2)]:
            eye=self.ce_compile(flags,block)[2][0]
            self.assertEqual(eye[1],origin);self.assertEqual(eye[2],radius);self.assertAlmostEqual(eye[3],iris,places=5)

    def test_ce_bodygroup_face_blocks_and_material_edits_stay_scoped(self):
        block=self.ce_fixture()
        self.run_qc('$modelname face\n$bodygroup heads {\nstudio mesh.smd {\n'
                    'eyeball eye_a root 1 2 3 material 2 0 iris .5\n'+block+'}\n'
                    'studio mesh.smd {\neyeball eye_b root 4 5 6 material 2 0 iris .5\n}\nblank\n}\n')
        eyes=self.ce_data()[2]
        self.assertEqual([e[1] for e in eyes],[(1,2,3),(4,5,6)])
        self.assertEqual(len(self.ce_data()[4]),4) # includes run_qc's additional body
        self.run_qc('$modelname renamed\n$bodygroup heads {\nstudio mesh.smd renamemat material variant\n'
                    'studio mesh.smd renamematbyprefix other_\n}\n')
        d=self.mdl('renamed');self.assertIn(b'variant\0',d);self.assertIn(b'other_material\0',d);self.assertIn(b'material\0',d)

    def test_ce_outdir_and_cli_prefixes(self):
        self.write('inc/pre_part.qci','$modelname output\n')
        self.run_qc('$include inc/part.qci\n$includemodel anim.mdl\n','-InClUdEpReFiX','inc/part.qci','pre_',
                    '-IncludeAnimPrefix','pre_','-OutDir','custom')
        d=(self.root/'custom/models/output.mdl').read_bytes();self.assertIn(b'models/pre_anim.mdl\0',d)
        self.run_qc('$modelname output\n$OutDir other\n')
        self.assertTrue((self.root/'other/models/output.mdl').exists())

    def test_ce_buffer_limit_failure_does_not_overwrite_old_outputs(self):
        self.run_qc('$modelname safe\n');old=self.mdl('safe')
        self.run_qc('$modelname safe\n$MDLOutputBufferSize .0001\n',success=False)
        self.assertEqual(self.mdl('safe'),old)
        self.run_qc('$modelname safe\n$OutputBufferSize -1\n',success=False)
        self.assertEqual(self.mdl('safe'),old)

    def ce_dmx(self, global_options='', suboptions=''):
        self.write('face.dmx',(Path(__file__).parent/'fixtures/ce-facial.dmx').read_text())
        self.run_qc('$modelname dmx\n'+global_options+'\n$model face face.dmx '+suboptions+'\n')
        return self.ce_data('dmx')

    def test_ce_dmx_smooth_normals_include_stationary_vertices(self):
        baseline=self.ce_dmx()[1][0]['vertices'];self.assertEqual(len(baseline),1)
        computed=self.ce_dmx('$ComputeDeltaNormals')[1][0]['vertices'];self.assertEqual(len(computed),3)
        for va in computed:
            for actual,expected in zip(va[2][3:],(.235595703125,.235595703125,-.05718994140625)):
                self.assertAlmostEqual(actual,expected,delta=.0003)
        for sub in ['IgnoreComputeDeltaNormals','IgnoreComputeNormalsAndWrinkles']:
            self.assertEqual(len(self.ce_dmx('$ComputeNormalsAndWrinkles',sub)[1][0]['vertices']),1)

    def test_ce_dmx_wrinkle_generation_and_local_disable(self):
        base=self.ce_dmx()[1][0]['vertices'];self.assertEqual(base[0][3],8192)
        self.assertEqual(self.ce_dmx('$ComputeWrinkles')[1][0]['vertices'][0][3],8192)
        disabled=self.ce_dmx('$ComputeWrinkles','IgnoreComputeWrinkles')[1][0]['vertices']
        self.assertIsNone(disabled[0][3])

    def test_ce_dmx_defaq_scale_can_be_disabled_independently(self):
        baseline=self.ce_dmx()[1][0]['vertices'][0][2][2]
        self.assertAlmostEqual(self.ce_dmx('$DefaqScale')[1][0]['vertices'][0][2][2],baseline*10)
        self.assertAlmostEqual(self.ce_dmx('$DefaqScale\n$IgnoreDMXDefaq')[1][0]['vertices'][0][2][2],baseline)

    def test_ce_invalid_eye_scale_and_flex_scale_fail(self):
        self.run_qc('$modelname invalid\n$EyeballScale 0\n',success=False)
        self.run_qc('$modelname invalid\n$EyeballScale nan\n',success=False)
        block=self.ce_fixture().replace('flex smile frame 1','flex smile frame 1 fscale nan')
        self.run_qc('$modelname invalid\n$model face mesh.smd {\n'+block+'}\n',success=False)


    def test_ce_repeated_global_flags_toggle_off(self):
        self.assertEqual(self.ce_compile('$ZeroFlexDecay\n$ZeroFlexDecay')[1],self.ce_compile()[1])
        self.assertEqual([k['name'] for k in self.ce_compile('$AddInvStudioFlexes\n$AddInvStudioFlexes')[1]],['smile'])

    def test_ce_fscale_scales_normal_deltas_too(self):
        block=self.ce_fixture()
        p=self.root/'face.vta';p.write_text(p.read_text().replace('0 0 0 .25 0 0 1','0 0 0 .25 .2 0 .98'))
        baseline=self.ce_compile('',block)[1][0]['vertices'][0][2]
        scaled=self.ce_compile('',block.replace('flex smile frame 1','flex smile frame 1 fscale 2'))[1][0]['vertices'][0][2]
        self.assertNotEqual(baseline[3],0)
        for a,b in zip(baseline,scaled):self.assertAlmostEqual(a*2,b,delta=.0005)

    def test_ce_dmx_remapping_rotates_deltas_to_authored_bind_pose(self):
        definition='$definebone root "" 0 0 0 0 0 90 0 0 0 0 0 0\n'
        before=self.ce_dmx(definition)[1][0]['vertices'][0][2][:3]
        after=self.ce_dmx(definition+'$RemapFlexToGlobal')[1][0]['vertices'][0][2][:3]
        self.assertEqual(before,(0,0,.25))
        for a,b in zip(after,(0,-.25,0)):self.assertAlmostEqual(a,b,places=4)

    def test_ce_force_collapse_overrides_keep_and_defined_bone(self):
        qc='$modelname bone_rules\n$bonecullmethod none\n$definebone unused_child root 0 0 1 0 0 0 0 0 0 0 0 0\n$donotcollapse unused_child\n$alwayscollapse unused_child\n'
        self.run_qc(qc);self.assertEqual(struct.unpack_from('<i',self.mdl('bone_rules'),156)[0],2)
        self.run_qc('$CEBoneRules\n'+qc);self.assertEqual(struct.unpack_from('<i',self.mdl('bone_rules'),156)[0],1)

    def test_ce_bind_to_one_bone_changes_serialized_weights(self):
        p=self.root/'mesh.smd';p.write_text(p.read_text().replace('0 0 0 1 0 0 0','0 0 0 0 0 0 0').replace('0 0 1 0 1\n','0 0 1 0 1\n'))
        lines=p.read_text().splitlines();start=lines.index('triangles')
        for i in range(start+2,len(lines)-1):lines[i]+=' 2 0 .7 1 .3'
        p.write_text('\n'.join(lines)+'\n')
        counts=[]
        for sub in ['', 'BindToOneBone']:
            self.run_qc('$modelname weights\n$bonecullmethod none\n$model face mesh.smd '+sub+'\n')
            d=(self.root/'models/weights.vvd').read_bytes();offset=struct.unpack_from('<i',d,56)[0]
            counts.append(d[offset+15])
            if sub:self.assertEqual(struct.unpack_from('<f',d,offset)[0],1)
        self.assertEqual(counts,[2,1])

    def test_ce_procedural_pushd_switch_selects_source_directory(self):
        self.write('procedural.vrd','<aimconstraint> unused_child root root\n')
        self.write('sub/procedural.vrd','<helper> malformed\n')
        text='$modelname procedural\n$pushd sub\n$proceduralbones procedural.vrd\n$popd\n'
        self.run_qc(text)
        output=self.run_qc('$PUSHDProcedural 1\n'+text,success=False)
        self.assertIn('<helper> expects',output)

    def test_ce_unimplemented_legacy_algorithms_fail_explicitly(self):
        for option in ['UseLegacyClampMethod','UseLegacyStripify']:
            output=self.run_qc('$modelname legacy\n$'+option+'\n',success=False)
            self.assertIn('legacy CE algorithm is not implemented',output)
            self.assertFalse((self.root/'models/legacy.mdl').exists())


    def test_ce_hbox_ignore_child_keeps_mesh_bounds(self):
        p=self.root/'mesh.smd';s=p.read_text().replace('1 0 0 1 0 0 0','1 100 0 0 0 0 0').replace('0 1 0 0 0 0 1 1 0','0 3 3 0 0 0 1 1 0').replace('0 0 1 0 0 0 1 0 1','0 0 0 3 0 0 1 0 1');p.write_text(s)
        bounds=[]
        for flags in ['', '$HBoxIgnoreChild\n']:
            self.run_qc('$modelname hitboxes\n$bonecullmethod none\n'+flags)
            d=self.mdl('hitboxes');hset=struct.unpack_from('<i',d,176)[0]
            self.assertGreater(struct.unpack_from('<i',d,hset+4)[0],0)
            box=hset+struct.unpack_from('<i',d,hset+8)[0]
            bounds.append(max(abs(v) for v in struct.unpack_from('<6f',d,box+8)))
        self.assertEqual(bounds,[100,3])

    def test_ce_legacy_no_auto_dmx_rules_removes_previous_controllers(self):
        self.write('face.dmx',(Path(__file__).parent/'fixtures/ce-facial.dmx').read_text())
        for option,count in [('NoAutoDMXRules',1),('NoAutoDMXRulesLegacy',0)]:
            self.run_qc('$modelname no_auto\n$model first face.dmx\n$model second face.dmx {\n'+option+'\n}\n')
            d=self.mdl('no_auto');self.assertEqual(struct.unpack_from('<i',d,268)[0],count)
            if count==0:self.assertEqual(struct.unpack_from('<i',d,276)[0],0)


if __name__ == "__main__":
    unittest.main()
