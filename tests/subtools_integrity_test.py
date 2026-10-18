#!/usr/bin/env python3
"""Exercise subtool failure boundaries with authored, disposable binary fixtures.

Usage: python tests/subtools_integrity_test.py --bin-dir build-local/bin
The directory may contain subtools/ or the three helper executables directly.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile


def integer(data, offset, *values):
    struct.pack_into("<" + "i" * len(values), data, offset, *values)


def header():
    data = bytearray(408)
    integer(data, 0, 0x54534449, 49)
    return data


def survivor(path, include=None):
    data = header()
    integer(data, 188, 3, 408)
    data.extend(bytes(3 * 212))
    for i, name in enumerate(("idle", "walk", "run")):
        at = 408 + i * 212
        integer(data, at + 4, len(data) - at)
        data.extend(name.encode() + b"\0")
    if include:
        integer(data, 336, 1, len(data))
        data.extend(struct.pack("<ii", 0, 8) + include.encode() + b"\0")
    integer(data, 76, len(data))
    path.write_bytes(data)


def target_mdl(path):
    data = header()
    bones = [
        ("Pelvis", -1, (0, 0, 40)), ("Head1", 0, (0, 0, 65)),
        ("L_Thigh", 0, (5, 0, 38)), ("L_Calf", 2, (5, 1, 21)),
        ("L_Foot", 3, (5, 0, 3)), ("R_Thigh", 0, (-5, 0, 38)),
        ("R_Calf", 5, (-5, 1, 21)), ("R_Foot", 6, (-5, 0, 3)),
    ]
    integer(data, 156, len(bones), 408)
    data.extend(bytes(216 * len(bones)))
    for i, (name, parent, world) in enumerate(bones):
        at = 408 + i * 216
        integer(data, at, len(data) - at, parent)
        data.extend(("ValveBiped.Bip01_" + name).encode() + b"\0")
        origin = bones[parent][2] if parent >= 0 else (0, 0, 0)
        struct.pack_into("<3f", data, at + 32, *[world[j] - origin[j] for j in range(3)])
        struct.pack_into("<4f", data, at + 44, 0, 0, 0, 1)
        struct.pack_into("<12f", data, at + 96, 1, 0, 0, -world[0],
                         0, 1, 0, -world[1], 0, 0, 1, -world[2])
    integer(data, 284, 2, len(data))
    chains = len(data)
    data.extend(bytes(32))
    for i, links in enumerate(((2, 3, 4), (5, 6, 7))):
        at = chains + i * 16
        integer(data, at, 0, 0, 3, len(data) - at)
        for bone in links:
            data.extend(struct.pack("<i6f", bone, 0, 1, 0, 0, 0, 0))
    integer(data, 76, len(data))
    path.write_bytes(data)


def vmd(path, camera=True):
    data = bytearray(b"Vocaloid Motion Data 0002".ljust(30, b"\0") + b"integrity".ljust(20, b"\0"))
    data.extend(struct.pack("<I", 2))
    for frame in (0, 30):
        data.extend("下半身".encode("shift_jis").ljust(15, b"\0") +
                    struct.pack("<I7f", frame, 0, 0, 0, 0, 0, 0, 1) + bytes(64))
    data.extend(struct.pack("<II", 0, int(camera)))
    if camera:
        data.extend(struct.pack("<If6f", 0, -30, 0, 10, 0, 0, 0, 0) + bytes(24) + struct.pack("<IB", 45, 0))
    path.write_bytes(data)


def simplify_request(indices=(0, 1, 2), target=3, positions=(0, 0, 0, 1, 0, 0, 0, 1, 0), runs=None):
    data = struct.pack("<III", 0x4D535750, 1, len(positions) // 3)
    data += struct.pack("<" + "f" * len(positions), *positions)
    runs = [(indices, target, 0)] if runs is None else runs
    data += struct.pack("<I", len(runs))
    for indices, target, flags in runs:
        data += struct.pack("<III", len(indices), target, flags)
        data += struct.pack("<" + "I" * len(indices), *indices)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    binary = args.bin_dir.resolve()
    if (binary / "subtools").is_dir():
        binary /= "subtools"
    suffix = ".exe" if os.name == "nt" else ""
    if os.name == "nt":
        ctypes.windll.kernel32.SetErrorMode(3)
    results = []
    with tempfile.TemporaryDirectory(prefix="subtools-integrity-") as temporary:
        root = Path(temporary)

        def run(name, tool, arguments, code=0, protected=(), message=None):
            before = {path: path.read_bytes() for path in protected}
            process = subprocess.run([str(binary / (tool + suffix)), *map(str, arguments)],
                                     cwd=root, capture_output=True, timeout=30)
            stdout = process.stdout.decode("utf-8", "replace")
            stderr = process.stderr.decode("utf-8", "replace")
            result = {"name": name, "returncode": process.returncode, "stdout": stdout, "stderr": stderr}
            results.append(result)
            assert process.returncode == code, result
            for path, original in before.items():
                assert path.read_bytes() == original, (name, "existing output changed", path)
            if message:
                assert message.lower() in (stdout + stderr).lower(), result

        # Valid topology still returns a parseable triangle, including both runs.
        request, response = root / "mesh.request", root / "mesh.response"
        request.write_bytes(simplify_request(runs=[((0, 1, 2), 3, 0), ((0, 2, 1), 3, 1)]))
        run("mesh_valid_two_runs", "meshtool", ["simplify", request, response])
        result = response.read_bytes()
        assert struct.unpack_from("<II", result) == (0x4D535750, 2)
        offset = 8
        for _ in range(2):
            count, error = struct.unpack_from("<If", result, offset)
            assert count == 3 and error == 0, result
            offset += 8
            assert set(struct.unpack_from("<3I", result, offset)) == {0, 1, 2}
            offset += 12
        assert offset == len(result)
        invalid = {
            "index_out_of_range": simplify_request((0, 1, 0x7FFFFFFF)),
            "non_triangular": simplify_request((0, 1, 2, 0)),
            "target_out_of_range": simplify_request(target=4),
            "nan_position": simplify_request(positions=(float("nan"), 0, 0, 1, 0, 0, 0, 1, 0)),
            "infinite_position": simplify_request(positions=(0, 0, 0, 1, float("inf"), 0, 0, 1, 0)),
            "no_vertices": simplify_request(positions=()),
            "truncated_positions": simplify_request()[:20],
            "truncated_run_header": simplify_request()[:56],
            "truncated_indices": simplify_request()[:-1],
            "bad_second_run": simplify_request(runs=[((0, 1, 2), 3, 0), ((0, 1, 9), 0, 0)]),
            "unsupported_flags": simplify_request(runs=[((0, 1, 2), 3, 2)]),
            "trailing_data": simplify_request() + b"garbage",
        }
        for name, data in invalid.items():
            request.write_bytes(data)
            response.write_bytes(b"previous response must survive")
            run("mesh_" + name, "meshtool", ["simplify", request, response], 1, [response], "simplify:")
        request.write_bytes(simplify_request(indices=(), target=0, positions=()))
        run("mesh_empty_run", "meshtool", ["simplify", request, response])
        assert struct.unpack("<III f", response.read_bytes()) == (0x4D535750, 1, 0, 0)

        # One requested female pair must work without the six male survivor MDLs.
        vanilla = root / "vanilla"
        vanilla.mkdir()
        zoey, rochelle = vanilla / "survivor_teenangst.mdl", vanilla / "survivor_producer.mdl"
        survivor(zoey, "shared.mdl")
        survivor(rochelle, "shared.mdl")
        survivor(vanilla / "shared.mdl")
        qci = root / "swap.qci"
        l4d = ["-vanilla", vanilla, "-rig", "zoey", "-replace", "rochelle", "-o", qci]
        run("l4d_valid_pair_only", "l4d_animswap", l4d)
        assert "$includemodel" in qci.read_text()
        (vanilla / "survivor_coach.mdl").write_bytes(b"unrelated corrupt survivor")
        run("l4d_unrelated_corrupt_ignored", "l4d_animswap", l4d)
        shared = vanilla / "shared.mdl"
        good_shared = shared.read_bytes()
        shared.unlink()
        run("l4d_missing_include", "l4d_animswap", l4d, 1, [qci], "no QCI written")
        malformed = bytearray(good_shared)
        integer(malformed, 188, 99999, 408)
        shared.write_bytes(malformed)
        run("l4d_truncated_sequence_table", "l4d_animswap", l4d, 1, [qci], "no QCI written")
        malformed = bytearray(good_shared)
        malformed[-1] = ord("x")
        shared.write_bytes(malformed)
        run("l4d_unterminated_sequence_name", "l4d_animswap", l4d, 1, [qci], "no QCI written")
        survivor(shared, "survivor_teenangst.mdl")
        run("l4d_include_cycle", "l4d_animswap", l4d, 1, [qci], "cyclic")
        shared.write_bytes(good_shared)
        run("l4d_missing_explicit_donor", "l4d_animswap", l4d + ["-via", "nick"], 1, [qci])
        for code in ("namvet", "biker", "manager", "coach", "gambler", "mechanic"):
            survivor(vanilla / ("survivor_" + code + ".mdl"))
        survivor(vanilla / "survivor_mechanic.mdl", "missing.mdl")
        all_dir = root / "all_qci"
        all_dir.mkdir()
        run("l4d_all_preflight_before_any_write", "l4d_animswap",
            ["-vanilla", vanilla, "-all", "-outdir", all_dir], 1, message="no QCI written")
        assert not list(all_dir.iterdir())
        run("l4d_existing_selftest", "l4d_animswap", ["-selftest"])

        # Motion outputs are parsed as body and camera DMX, then used as sentinels.
        target = root / "target.mdl"
        target_mdl(target)
        dance, dance_camera = root / "dance.vmd", root / "dance_camera.vmd"
        vmd(dance)
        vmd(dance_camera)
        base = ["-mdl", target, "-camerafov", "dmx", "-dmxencoding", "keyvalues2"]
        run("vmd_single_body_camera", "vmd2valvebiped", base + ["-vmd", dance_camera])
        body = root / "dance_camera.dmx"
        camera = root / "dance_camera_camera.dmx"
        smd = root / "dance_camera_camera.smd"
        assert b"format model 15" in body.read_bytes()[:100]
        assert b"format pulsecamera 1" in camera.read_bytes()[:100]
        run("vmd_body_camera_collision", "vmd2valvebiped",
            base + ["-vmd", dance_camera, "-vmd", dance], 1, [body, camera, smd], "collision")
        assert not (root / "dance.dmx").exists()
        run("vmd_body_camera_collision_reverse", "vmd2valvebiped",
            base + ["-vmd", dance, "-vmd", dance_camera], 1, [body, camera, smd], "collision")
        alias_dir = root / "alias"
        alias_dir.mkdir()
        run("vmd_dot_segment_alias", "vmd2valvebiped",
            base + ["-vmd", dance_camera, "-vmd", alias_dir / ".." / dance_camera.name],
            1, [body, camera, smd], "collision")
        if os.name == "nt":
            run("vmd_windows_case_alias", "vmd2valvebiped",
                base + ["-vmd", dance_camera, "-vmd", root / "DANCE_CAMERA.VMD"],
                1, [body, camera, smd], "collision")
            unicode_motion = root / "Élan.vmd"
            vmd(unicode_motion, False)
            unicode_body = root / "Élan.dmx"
            unicode_body.write_bytes(b"old Unicode path output")
            run("vmd_windows_unicode_case_alias", "vmd2valvebiped",
                base + ["-vmd", unicode_motion, "-vmd", root / "élan.vmd"],
                1, [unicode_body], "collision")
        # Both compile input sequences and data copies must be reserved, without
        # invoking the main compiler or needing a game for these rejected jobs.
        source, game = root / "source", root / "game"
        source.mkdir()
        preserved_qc = source / "motion.qc"
        preserved_qc.write_bytes(b"old QC")
        compile_args = ["-compile", "motion.mdl", "-srcdir", source, "-game", game]
        run("vmd_compile_sequence_collision", "vmd2valvebiped",
            base + ["-vmd", dance_camera, "-vmd", dance] + compile_args,
            1, [preserved_qc], "collision")
        assert set(source.iterdir()) == {preserved_qc}
        face_dir = game / "datamodel" / "flex_anims"
        face_dir.mkdir(parents=True)
        face = face_dir / "dance.dmx"
        face.write_bytes(b"previous face animation")
        run("vmd_body_face_path_collision", "vmd2valvebiped",
            base + ["-vmd", dance, "-compile", "motion.mdl", "-srcdir", face_dir, "-game", game],
            1, [face], "collision")
        linked = root / "linked.vmd"
        vmd(linked, False)
        linked_body = root / "linked.dmx"
        os.link(body, linked_body)
        run("vmd_existing_hardlink_alias", "vmd2valvebiped",
            base + ["-vmd", dance_camera, "-vmd", linked], 1, [body, linked_body], "collision")
        linked_body.unlink()
        broken = root / "broken.vmd"
        broken.write_bytes(b"truncated VMD")
        run("vmd_later_invalid_input_preflight", "vmd2valvebiped",
            base + ["-vmd", dance_camera, "-vmd", broken], 1, [body, camera, smd])
        safe = root / "safe.vmd"
        vmd(safe, False)
        run("vmd_nonconflicting_batch", "vmd2valvebiped",
            base + ["-vmd", dance_camera, "-vmd", safe])
        assert b"format model 15" in (root / "safe.dmx").read_bytes()[:100]
    report = {"passed": len(results), "cases": results}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"subtools integrity: {len(results)} cases passed")


if __name__ == "__main__":
    main()
