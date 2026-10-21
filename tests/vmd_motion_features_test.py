"""VMD IK/FK transitions, projection diagnostics and numeric failure preservation.

Usage: python tests/vmd_motion_features_test.py path/to/vmd2valvebiped[.exe]
All fixtures are authored in temporary directories; no game assets are required.
"""
from pathlib import Path
import math
import re
import struct
import subprocess
import sys
import tempfile
import unittest

from subtools_integrity_test import target_mdl

TOOL = Path(sys.argv.pop(1)).resolve()


def motion(switches=None, projection=0, fk_angle=0.6, lights=False):
    keys = []
    for name, pos, rot in (
        ("下半身", (0, 0, 0), (0, 0, 0, 1)),
        ("左足ＩＫ", (3, 0, 0), (0, 0, 0, 1)),
        ("左足", (0, 0, 0), (0, 0, math.sin(fk_angle / 2), math.cos(fk_angle / 2))),
    ):
        for frame in (0, 4):
            keys.append(name.encode("shift_jis").ljust(15, b"\0") +
                        struct.pack("<I7f", frame, *pos, *rot) + bytes(64))
    data = b"Vocaloid Motion Data 0002".ljust(30, b"\0") + b"fixture".ljust(20, b"\0")
    data += struct.pack("<I", len(keys)) + b"".join(keys) + struct.pack("<II", 0, 1)
    data += struct.pack("<If6f", 0, -30, 0, 10, 0, 0, 0, 0) + bytes(24)
    data += struct.pack("<IB", 45, projection)
    if switches is not None:
        data += struct.pack("<I", int(lights))
        if lights:
            data += struct.pack("<I6f", 0, 1, 1, 1, 0, -1, 0)
        data += struct.pack("<I", int(lights))
        if lights:
            data += struct.pack("<IBf", 0, 1, 100)
        data += struct.pack("<I", len(switches))
        for frame, states in switches:
            data += struct.pack("<IBI", frame, 1, len(states))
            for name, enabled in states:
                data += name.encode("shift_jis").ljust(20, b"\0") + bytes([enabled])
    return data


def pmx(knee_x=0.9):
    def text(value):
        encoded = value.encode("utf-8")
        return struct.pack("<i", len(encoded)) + encoded
    bones = [("下半身", (0, 11.8, 0)), ("上半身", (0, 12, 0)), ("頭", (0, 16.8, 0))]
    for side, x in (("左", 0.9), ("右", -0.9)):
        bones += [(side + "足", (x, 10.9, 0.1)),
                  (side + "ひざ", (knee_x if side == "左" else x, 6, -0.1)),
                  (side + "足首", (x, 1.1, 0.4)), (side + "足ＩＫ", (x, 1.1, 0.4))]
    data = b"PMX " + struct.pack("<fB", 2.0, 8) + bytes([1, 0, 1, 1, 1, 1, 1, 1])
    data += text("fixture") + text("") + text("") + text("")
    data += struct.pack("<5i", 0, 0, 0, 0, len(bones))
    for name, position in bones:
        data += text(name) + text("") + struct.pack("<3fbiH3f", *position, -1, 0, 0, 0, 0, 0)
    return data + struct.pack("<4i", 0, 0, 0, 0)


def tail_motion(body_end=0, camera_end=30, morph_end=None):
    data = b"Vocaloid Motion Data 0002".ljust(30, b"\0") + b"tail".ljust(20, b"\0")
    bone_frames = [] if body_end is None else sorted({0, body_end})
    data += struct.pack('<I', len(bone_frames))
    for frame in bone_frames:
        data += ('下半身'.encode('shift_jis').ljust(15, b'\0') +
                 struct.pack('<I7f', frame, 0, 0, 0, 0, 0, 0, 1) + bytes(64))
    morph_frames = [] if morph_end is None else sorted({0, morph_end})
    data += struct.pack('<I', len(morph_frames))
    for frame in morph_frames:
        data += b'test'.ljust(15, b'\0') + struct.pack('<If', frame, frame / max(1, morph_end))
    camera_frames = [] if camera_end is None else sorted({0, camera_end})
    data += struct.pack('<I', len(camera_frames))
    for frame in camera_frames:
        data += struct.pack('<If6f', frame, -30, frame, 10, 0, 0, 0, 0) + bytes(24)
        data += struct.pack('<IB', 45, 0)
    return data


def channels(path):
    objects = {}
    for kind, body in re.findall(r'^"([^"]+)"\s*\n\{(.*?)^\}', path.read_text(), re.S | re.M):
        ident = re.search(r'"id"\s+"elementid"\s+"([^"]+)"', body)
        if ident:
            objects[ident[1]] = kind, body
    result = {}
    for kind, body in objects.values():
        if kind != "DmeChannel":
            continue
        name = re.search(r'"name"\s+"string"\s+"([^"]+)"', body)[1]
        log = re.search(r'"log"\s+"element"\s+"([^"]+)"', body)[1]
        layer = re.search(r'"layers"\s+"element_array"\s*\[\s*"element"\s+"([^"]+)"', objects[log][1])[1]
        values = re.search(r'"values"\s+"(?:vector3|quaternion|float)_array"\s*\[([^]]*)\]', objects[layer][1])[1]
        result[name] = [tuple(map(float, value.split())) for value in re.findall(r'"([^"]+)"', values)]
    return result


class MotionFeatures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="newpage-vmd-features-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "target.mdl"
        target_mdl(self.target)

    def convert(self, name, data, extra=(), error=None):
        folder = self.root / name
        folder.mkdir()
        source = folder / "motion.vmd"
        source.write_bytes(data)
        expected = [folder / "motion.dmx", folder / "motion_camera.smd", folder / "motion_camera.dmx"]
        if error:
            for path in expected:
                path.write_bytes(b"preserve-existing-output")
        proc = subprocess.run([str(TOOL), "-mdl", str(self.target), "-vmd", str(source),
                               "-dmxencoding", "keyvalues2", "-camerafov", "dmx", *map(str, extra)],
                              capture_output=True, timeout=30)
        text = (proc.stdout + proc.stderr).decode("utf-8", "replace")
        if error:
            self.assertNotEqual(proc.returncode, 0, text)
            self.assertIn(error, text)
            for path in expected:
                self.assertEqual(path.read_bytes(), b"preserve-existing-output")
            return None
        self.assertEqual(proc.returncode, 0, text)
        for path in expected:
            self.assertTrue(path.is_file(), text)
            self.assertIsNone(re.search(r'(?i)(?<![a-z])(?:nan|[+-]?inf)(?![a-z])', path.read_text()))
        return channels(expected[0])

    def sample(self, clip, bone, frame):
        values = clip["ValveBiped.Bip01_" + bone + "_o"]
        return values[min(frame, len(values) - 1)]

    def test_ik_switches_apply_on_exact_frames_and_keep_other_leg(self):
        enabled = self.convert("enabled", motion([(0, [("左足ＩＫ", 1)])]))
        disabled = self.convert("disabled", motion([(0, [("左足ＩＫ", 0)])]))
        legacy = self.convert("legacy", motion())
        switched = self.convert("switch", motion([(1, [("左足ＩＫ", 0)]),
                                                   (3, [("左足ＩＫ", 1)])], lights=True))
        self.assertEqual(enabled, legacy)
        self.assertNotEqual(self.sample(enabled, "L_Thigh", 0), self.sample(disabled, "L_Thigh", 0))
        for frame in range(5):
            reference = disabled if frame in (1, 2) else enabled
            for bone in ("L_Thigh", "L_Calf", "L_Foot"):
                for actual, expected in zip(self.sample(switched, bone, frame), self.sample(reference, bone, frame)):
                    self.assertAlmostEqual(actual, expected, places=6)
            self.assertEqual(self.sample(switched, "R_Thigh", frame), self.sample(enabled, "R_Thigh", frame))

    def test_disabled_ik_retains_authored_fk_rotations(self):
        off = [(0, [("左足ＩＫ", 0)])]
        moved = self.convert("fk-moved", motion(off))
        bind = self.convert("fk-bind", motion(off, fk_angle=0))
        self.assertNotEqual(self.sample(moved, "L_Thigh", 0), self.sample(bind, "L_Thigh", 0))
        self.assertAlmostEqual(abs(self.sample(moved, "L_Thigh", 0)[3]), math.cos(0.3), places=5)

    def test_sparse_unsorted_duplicate_switches_hold_last_value(self):
        off = self.convert("off", motion([(0, [("左足ＩＫ", 0)])]))
        mixed = self.convert("mixed", motion([(3, [("左足ＩＫ", 1)]),
                                               (0, [("左足ＩＫ", 0)]),
                                               (2, [("右足ＩＫ", 1)]),
                                               (3, [("左足ＩＫ", 0)])]))
        self.assertEqual(off, mixed)

    def test_orthographic_and_bad_projection_preserve_outputs(self):
        for flag, error in ((1, "orthographic camera at frame 0"), (2, "invalid perspective flag")):
            with self.subTest(flag=flag):
                self.convert("projection" + str(flag), motion(projection=flag), error=error)

    def test_bad_or_truncated_ik_records_preserve_outputs(self):
        self.convert("bad-ik", motion([(0, [("左足ＩＫ", 2)])]), error="invalid IK enable flag")
        data = motion([(0, [("左足ＩＫ", 1)])])
        for missing in (1, 10, 25):
            with self.subTest(missing=missing):
                self.convert("short" + str(missing), data[:-missing], error="truncated")

    def test_pmx_invalid_positions_are_rejected_with_context(self):
        good = self.root / "good.pmx"
        good.write_bytes(pmx())
        self.convert("good-pmx", motion(), ["-pmx", good])
        for name, value in (("nan", math.nan), ("inf", math.inf), ("negative-inf", -math.inf),
                            ("extreme", 3e38)):
            with self.subTest(name=name):
                path = self.root / (name + ".pmx")
                path.write_bytes(pmx(value))
                self.convert(name, motion(), ["-pmx", path], error="rest position")

    def test_nonfinite_bind_and_overflowing_scale_preserve_outputs(self):
        valid = self.target.read_bytes()
        for name, value, expected in (("bind-nan", math.nan, "non-finite bind transform"),
                                      ("scale-overflow", 1e30, "motion scale")):
            with self.subTest(name=name):
                model = bytearray(valid)
                # Bone 3 is L_Calf; poseToBone translation z is matrix element 11.
                struct.pack_into("<f", model, 408 + 3 * 216 + 96 + 44, value)
                self.target.write_bytes(model)
                self.convert(name, motion(), error=expected)

    def add_face_controller(self):
        data = bytearray(self.target.read_bytes())
        struct.pack_into('<2i', data, 268, 1, len(data))
        data += struct.pack('<3i2f', 20, 28, -1, 0, 1) + b'default\0test\0'
        struct.pack_into('<i', data, 76, len(data))
        self.target.write_bytes(data)
        facemap = self.root / 'facemap.txt'
        facemap.write_text('test test=1\n')
        return facemap

    def test_camera_and_morph_tail_extend_common_interval(self):
        facemap = self.add_face_controller()
        clip = self.convert('tails', tail_motion(camera_end=20, morph_end=30),
                            ['-dmxmodel', '22', '-facemap', facemap])
        self.assertEqual(len(clip['test']), 31)
        self.assertAlmostEqual(clip['test'][-1][0], 1)
        camera = (self.root / 'tails/motion_camera.smd').read_text()
        self.assertEqual(len(re.findall(r'^time ', camera, re.M)), 31)
        frames = re.findall(r'^time \d+\n([^\n]+)', camera, re.M)
        self.assertNotEqual(frames[0], frames[20])
        self.assertEqual(frames[20], frames[30])

    def test_explicit_interval_keeps_crop_and_last_value_hold(self):
        facemap = self.add_face_controller()
        clip = self.convert('crop', tail_motion(camera_end=30, morph_end=30),
                            ['-start', '10', '-end', '20', '-dmxmodel', '22', '-facemap', facemap])
        self.assertEqual(len(clip['test']), 11)
        self.assertAlmostEqual(clip['test'][0][0], 1 / 3, places=5)
        self.assertAlmostEqual(clip['test'][-1][0], 2 / 3, places=5)

    def test_sidecars_participate_in_interval_and_override_before_sampling(self):
        facemap = self.add_face_controller()
        folder = self.root / 'sidecars'
        folder.mkdir()
        (folder / 'motion.vmd').write_bytes(tail_motion(camera_end=90, morph_end=90))
        (folder / 'motion_face.vmd').write_bytes(tail_motion(None, None, 30))
        (folder / 'motion_camera.vmd').write_bytes(tail_motion(None, 20, None))
        proc = subprocess.run([str(TOOL), '-mdl', str(self.target), '-vmd', str(folder / 'motion.vmd'),
                               '-facemap', str(facemap), '-dmxmodel', '22', '-dmxencoding', 'keyvalues2'],
                              capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(len(channels(folder / 'motion.dmx')['test']), 31)
        camera = (folder / 'motion_camera.smd').read_text()
        self.assertEqual(len(re.findall(r'^time ', camera, re.M)), 31)

    def standalone(self, mode, source, output, extra=(), success=True):
        proc = subprocess.run([str(TOOL), '-mode', mode, '-vmd', str(source), '-o', str(output),
                               '-dmxencoding', 'keyvalues2', *map(str, extra)],
                              capture_output=True, timeout=30)
        text = (proc.stdout + proc.stderr).decode('utf-8', 'replace')
        self.assertEqual(proc.returncode == 0, success, text)
        return text

    def test_camera_only_requires_no_model_and_preserves_fov_and_interval(self):
        source = self.root / 'camera.vmd'
        source.write_bytes(tail_motion(None, 30, None))
        output = self.root / 'camera.dmx'
        self.standalone('camera', source, output, ['-camera-scale', '2', '-start', '5', '-end', '15'])
        tracks = channels(output)
        self.assertEqual(len(tracks['position']), 11)
        self.assertAlmostEqual(tracks['position'][-1][0] - tracks['position'][0][0], 20, places=5)
        self.assertEqual(tracks['fov'], [(45.0,)])
        self.assertEqual(len(re.findall(r'^time ', output.with_suffix('.smd').read_text(), re.M)), 11)

    def test_face_only_has_no_skeleton_channels_or_ik_requirement(self):
        facemap = self.add_face_controller()
        model = bytearray(self.target.read_bytes())
        struct.pack_into('<2i', model, 284, 0, 0)  # no leg chains
        self.target.write_bytes(model)
        source = self.root / 'face.vmd'
        source.write_bytes(tail_motion(None, None, 30))
        output = self.root / 'face.dmx'
        self.standalone('face', source, output, ['-mdl', self.target, '-facemap', facemap])
        tracks = channels(output)
        self.assertEqual(set(tracks), {'test'})
        self.assertEqual(len(tracks['test']), 31)
        self.assertAlmostEqual(tracks['test'][-1][0], 1)

    def test_standalone_rejects_input_aliases_and_unmapped_face_preserves_output(self):
        source = self.root / 'camera.vmd'
        source.write_bytes(tail_motion(None, 30, None))
        alias = self.root / 'alias.dmx'
        import os
        os.link(source, alias)
        original = source.read_bytes()
        self.assertIn('aliases an input', self.standalone('camera', source, alias, success=False))
        self.assertEqual(source.read_bytes(), original)
        facemap = self.add_face_controller()
        source.write_bytes(tail_motion(None, None, 30))
        facemap.write_text('different test=1\n')
        output = self.root / 'face.dmx'
        output.write_bytes(b'previous face')
        self.assertIn('no facial tracks map', self.standalone('face', source, output,
                      ['-mdl', self.target, '-facemap', facemap], success=False))
        self.assertEqual(output.read_bytes(), b'previous face')

    def test_standalone_batch_failure_preserves_every_output(self):
        first, second = self.root / 'one.vmd', self.root / 'two.vmd'
        first.write_bytes(tail_motion(None, 30, None))
        second.write_bytes(b'bad VMD')
        targets = [first.with_suffix('.dmx'), first.with_suffix('.smd')]
        for target in targets:
            target.write_bytes(b'previous')
        result = subprocess.run([str(TOOL), '-mode', 'camera', '-vmd', str(first), '-vmd', str(second)],
                                capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        for target in targets:
            self.assertEqual(target.read_bytes(), b'previous')

    def custom_rig(self, leg_mode='ik', options=''):
        roles = ['Pelvis', 'Head1', 'L_Thigh', 'L_Calf', 'L_Foot', 'R_Thigh', 'R_Calf', 'R_Foot']
        names = ['hips', 'head', 'left upper leg', 'left knee', 'left ankle',
                 'right upper leg', 'right knee', 'right ankle']
        data = bytearray(self.target.read_bytes())
        table = struct.unpack_from('<i', data, 160)[0]
        for i, name in enumerate(names):
            at = table + i * 216
            struct.pack_into('<i', data, at, len(data) - at)
            data += name.encode() + b'\0'
        # The mapping's explicit anatomical chains do not need embedded MDL IK.
        struct.pack_into('<2i', data, 284, 0, 0)
        struct.pack_into('<i', data, 76, len(data))
        self.target.write_bytes(data)
        profile = self.root / 'humanoid.map'
        profile.write_text('vmd_humanoid_mapping 1\nleg_mode ' + leg_mode + '\n' +
                           ''.join(f'role {role} "{name}"\n' for role, name in zip(roles, names)) + options)
        return profile, dict(zip(roles, names))

    def test_custom_named_humanoid_explicit_ik_chain_matches_standard_rig(self):
        reference = self.convert('standard', motion())
        profile, names = self.custom_rig()
        custom = self.convert('custom', motion(), ['-mapping', profile])
        for role, name in names.items():
            for kind in ('_p', '_o'):
                self.assertEqual(custom[name + kind], reference['ValveBiped.Bip01_' + role + kind])

    def test_custom_fk_only_ignores_ik_switches_and_keeps_fk(self):
        reference = self.convert('standard-fk', motion([(0, [('左足ＩＫ', 0), ('右足ＩＫ', 0)])]))
        profile, names = self.custom_rig('fk')
        custom = self.convert('custom-fk', motion(), ['-mapping', profile])
        for role, name in names.items():
            self.assertEqual(custom[name + '_o'], reference['ValveBiped.Bip01_' + role + '_o'])

    def test_custom_motion_scale_and_basis_have_measurable_root_effect(self):
        data = bytearray(tail_motion(30, 0))
        struct.pack_into('<f', data, 54 + 111 + 19, 2)  # second lower-body key's X
        profile, names = self.custom_rig('fk')
        original = profile.read_text()
        first = self.convert('scale-one', data, ['-mapping', profile])
        profile.write_text(original + 'motion_scale 2\nbasis 0 1 0 0 0 1\n')
        second = self.convert('scale-two', data, ['-mapping', profile])
        a = first[names['Pelvis'] + '_p']; b = second[names['Pelvis'] + '_p']
        dx = a[-1][0] - a[0][0]
        dy = b[-1][1] - b[0][1]
        self.assertGreater(abs(dx), 1)
        self.assertAlmostEqual(dy, 2 * dx, places=4)
        self.assertAlmostEqual(b[-1][0], b[0][0], places=5)

    def test_mapping_errors_reject_before_replacing_old_outputs(self):
        profile, _ = self.custom_rig('fk')
        original = profile.read_text()
        for name, text, error in [
            ('version', original.replace('mapping 1', 'mapping 2'), 'expected vmd_humanoid_mapping 1'),
            ('duplicate', original + 'role Pelvis "hips"\n', 'duplicate role'),
            ('unknown', original + 'typo 1\n', 'unknown mapping directive'),
            ('basis', original + 'basis 1 0 0 1 0 0\n', 'orthogonal unit vectors'),
            ('scale', original + 'motion_scale nan\n', 'complete finite number'),
            ('missing', original.replace('"hips"', '"missing"'), 'target bone not found'),
            ('alias', original.replace('"head"', '"hips"'), 'share target bone')]:
            with self.subTest(name=name):
                profile.write_text(text)
                self.convert('bad-map-' + name, motion(), ['-mapping', profile], error=error)

    def test_opt_in_key_reduction_meets_independent_error_samples_and_keeps_ik_edges(self):
        from dmx_keys import channels as keyed_channels, sample, error
        data=b'Vocaloid Motion Data 0002'.ljust(30,b'\0')+b'reduction'.ljust(20,b'\0')
        data+=struct.pack('<I',31)
        for frame in range(31):
            angle=frame*0.015
            data+='下半身'.encode('shift_jis').ljust(15,b'\0')
            data+=struct.pack('<I7f',frame,frame*.3+math.sin(frame*.4)*.03,0,0,
                              0,math.sin(angle/2),0,math.cos(angle/2))+bytes(64)
        data+=tail_motion(None,0,None)[54:]
        # FK for most frames, with an explicit IK boundary to preserve at frame 15.
        data+=struct.pack('<3I',0,0,2)
        for frame in (0,15):
            data+=struct.pack('<IBI',frame,1,2)
            for name in ('左足ＩＫ','右足ＩＫ'):
                data+=name.encode('shift_jis').ljust(20,b'\0')+bytes([int(frame==15)])
        self.convert('full-keys',data)
        self.convert('reduced-keys',data,['-reducepos','0.02','-reduceangle','0.05'])
        full=keyed_channels(self.root/'full-keys/motion.dmx')
        reduced=keyed_channels(self.root/'reduced-keys/motion.dmx')
        self.assertLess(sum(len(c[1]) for c in reduced.values()),sum(len(c[1]) for c in full.values()))
        for name,channel in full.items():
            kind,times,values=channel
            limit=.05 if kind=='quaternion' else .02
            probes=set(times)
            for a,b in zip(times,times[1:]):
                probes.update(a+(b-a)*part/8 for part in range(1,8))
            for time in probes:
                self.assertLessEqual(error(sample(channel,time),sample(reduced[name],time),kind=='quaternion'),limit+2e-4,name)
            # Even constant tracks retain the explicit transition's adjacent keys in opt-in mode.
            for boundary in (.5,.4667):
                self.assertLess(min(abs(t-boundary) for t in reduced[name][1]),1e-6)


if __name__ == "__main__":
    unittest.main()
