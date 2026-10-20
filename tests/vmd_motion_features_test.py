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
        values = re.search(r'"values"\s+"(?:vector3|quaternion)_array"\s*\[([^]]*)\]', objects[layer][1])[1]
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


if __name__ == "__main__":
    unittest.main()
