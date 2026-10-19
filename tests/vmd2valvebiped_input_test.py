#!/usr/bin/env python3
"""Reject invalid VMD and face-map numeric data without replacing outputs."""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from subtools_integrity_test import target_mdl


def make_vmd(path, *, position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0, 1.0),
             bone_interpolation=None, morph_weight=None, camera=None):
    data = bytearray(b"Vocaloid Motion Data 0002".ljust(30, b"\0") + b"input-test".ljust(20, b"\0"))
    data.extend(struct.pack("<I", 1))
    data.extend("下半身".encode("shift_jis").ljust(15, b"\0"))
    data.extend(struct.pack("<I7f", 0, *position, *rotation))
    interpolation = bytearray(64)
    if bone_interpolation is not None:
        interpolation[bone_interpolation[0]] = bone_interpolation[1]
    data.extend(interpolation)
    if morph_weight is None:
        data.extend(struct.pack("<I", 0))
    else:
        data.extend(struct.pack("<I", 1))
        data.extend(b"mouth".ljust(15, b"\0"))
        data.extend(struct.pack("<If", 0, morph_weight))
    if camera is None:
        data.extend(struct.pack("<I", 0))
    else:
        distance, at, rotation, fov, bad_interpolation = camera
        data.extend(struct.pack("<I", 1))
        data.extend(struct.pack("<If6f", 0, distance, *at, *rotation))
        interpolation = bytearray(24)
        if bad_interpolation is not None:
            interpolation[bad_interpolation[0]] = bad_interpolation[1]
        data.extend(interpolation)
        data.extend(struct.pack("<IB", fov, 0))
    path.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", required=True, type=Path)
    args = parser.parse_args()
    binary = args.bin_dir.resolve()
    if (binary / "subtools").is_dir():
        binary /= "subtools"
    executable = binary / ("vmd2valvebiped.exe" if os.name == "nt" else "vmd2valvebiped")
    sentinel = b"existing animation must survive invalid input"
    cases = []

    with tempfile.TemporaryDirectory(prefix="vmd-input-validation-") as directory:
        root = Path(directory)
        mdl, vmd, output = root / "target.mdl", root / "motion.vmd", root / "motion.dmx"
        target_mdl(mdl)

        def run_invalid(name, *, expected, motion_args=None, face_map=None):
            if face_map is None:
                make_vmd(vmd, **(motion_args or {}))
            else:
                vmd.write_bytes(b"unused because face map is rejected first")
            output.write_bytes(sentinel)
            arguments = ["-mdl", mdl, "-vmd", vmd, "-o", output]
            if face_map is not None:
                face_path = root / "face.map"
                face_path.write_text(face_map, encoding="utf-8")
                arguments += ["-facemap", face_path]
            result = subprocess.run([str(executable), *map(str, arguments)], cwd=root,
                                    capture_output=True, timeout=30)
            diagnostic = (result.stdout + result.stderr).decode("utf-8", "replace")
            assert result.returncode != 0, (name, diagnostic)
            assert expected in diagnostic, (name, expected, diagnostic)
            assert output.read_bytes() == sentinel, (name, "existing output changed")
            cases.append(name)

        for name, kwargs, expected in (
            ("bone_nan_position", {"position": (float("nan"), 0, 0)}, "bone key #1"),
            ("bone_infinite_quaternion", {"rotation": (0, 0, float("inf"), 1)}, "quaternion"),
            ("bone_zero_quaternion", {"rotation": (0, 0, 0, 0)}, "quaternion"),
            ("bone_position_overflow_range", {"position": (1.0e8, 0, 0)}, "position"),
            ("bone_interpolation_out_of_range", {"bone_interpolation": (3, 255)}, "interpolation"),
            ("morph_nan_weight", {"morph_weight": float("nan")}, "morph key #1"),
            ("morph_infinite_weight", {"morph_weight": float("inf")}, "morph key #1"),
            ("morph_extreme_weight", {"morph_weight": 1.0e7}, "out-of-range weight"),
            ("camera_nan_distance", {"camera": (float("nan"), (0, 0, 0), (0, 0, 0), 45, None)},
             "camera key #1"),
            ("camera_infinite_position", {"camera": (1, (0, float("inf"), 0), (0, 0, 0), 45, None)},
             "distance/position"),
            ("camera_extreme_rotation", {"camera": (1, (0, 0, 0), (1.0e5, 0, 0), 45, None)},
             "rotation"),
            ("camera_invalid_fov", {"camera": (1, (0, 0, 0), (0, 0, 0), 181, None)}, "field of view"),
            ("camera_interpolation_out_of_range",
             {"camera": (1, (0, 0, 0), (0, 0, 0), 45, (9, 128))}, "interpolation"),
        ):
            run_invalid(name, motion_args=kwargs, expected=expected)

        for name, weight in (("nan", "nan"), ("infinity", "inf"),
                             ("overflow", "1e1000"), ("extreme", "1000001"),
                             ("suffix", "1.5x")):
            run_invalid("face_map_" + name, face_map=f"# comment\nmouth jaw={weight}\n",
                        expected='face.map" line 2')

    print(f"vmd2valvebiped input validation: {len(cases)} malformed-input cases passed")


if __name__ == "__main__":
    main()
