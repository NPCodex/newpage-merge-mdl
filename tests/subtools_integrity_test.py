#!/usr/bin/env python3
"""Exercise subtool failure boundaries with authored, disposable binary fixtures.

Usage: python tests/subtools_integrity_test.py --bin-dir build-local/bin
The directory may contain subtools/ or the three helper executables directly.
"""
import argparse
import ctypes
import json
import os
import re
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


def vmd(path, camera=True, last_frame=30):
    data = bytearray(b"Vocaloid Motion Data 0002".ljust(30, b"\0") + b"integrity".ljust(20, b"\0"))
    data.extend(struct.pack("<I", 2))
    for frame in (0, last_frame):
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


def decompose_request(jobs):
    data = bytearray(struct.pack("<III", 0x44435750, 2, len(jobs)))
    for vertices, triangles, concavity, max_hulls, decimate, resolution in jobs:
        data.extend(struct.pack("<I", len(vertices) // 3))
        if vertices:
            data.extend(struct.pack("<" + "f" * len(vertices), *vertices))
        data.extend(struct.pack("<I", len(triangles) // 3))
        if triangles:
            data.extend(struct.pack("<" + "i" * len(triangles), *triangles))
        data.extend(struct.pack("<fIfI", concavity, max_hulls, decimate, resolution))
    return bytes(data)


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
            "bad_magic": b"BAD!" + simplify_request()[4:],
            "bad_version": simplify_request()[:4] + struct.pack("<I", 99) + simplify_request()[8:],
            "big_endian_header": struct.pack(">IIII", 0x4D535750, 1, 0, 0),
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
            "vertex_limit": struct.pack("<III", 0x4D535750, 1, 4 * 1024 * 1024 + 1),
            "run_limit": struct.pack("<IIII", 0x4D535750, 1, 0, 1024 * 1024 + 1),
            "index_limit": struct.pack("<IIIIIII", 0x4D535750, 1, 0, 1,
                                        16 * 1024 * 1024 + 2, 0, 0),
        }
        for name, data in invalid.items():
            request.write_bytes(data)
            response.write_bytes(b"previous response must survive")
            run("mesh_" + name, "meshtool", ["simplify", request, response], 1, [response], "simplify:")
        request.write_bytes(simplify_request(indices=(), target=0, positions=()))
        run("mesh_empty_run", "meshtool", ["simplify", request, response])
        assert struct.unpack("<III f", response.read_bytes()) == (0x4D535750, 1, 0, 0)

        # Decomposition preserves the distinction between a valid empty job
        # and malformed or unusable geometry, and never replaces an old answer
        # unless every job has been processed successfully.
        decompose_response = root / "decompose.response"
        sentinel = b"previous decompose response must survive"
        empty_job = ((), (), 0.1, 4, 1.0, 10000)
        request.write_bytes(decompose_request([empty_job]))
        run("mesh_decompose_empty_job", "meshtool", ["decompose", request, decompose_response])
        assert struct.unpack("<III", decompose_response.read_bytes()) == (0x44435750, 1, 0)

        tetra_vertices = (0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1)
        tetra_faces = (0, 2, 1, 0, 1, 3, 1, 2, 3, 2, 0, 3)
        request.write_bytes(decompose_request([
            (tetra_vertices, tetra_faces, 0.1, 4, 1.0, 10000),
        ]))
        run("mesh_decompose_tetrahedron", "meshtool", ["decompose", request, decompose_response])
        decoded = decompose_response.read_bytes()
        magic, jobs, hulls = struct.unpack_from("<III", decoded)
        assert (magic, jobs) == (0x44435750, 1) and hulls >= 1, decoded
        offset = 12
        for _ in range(hulls):
            points, = struct.unpack_from("<I", decoded, offset)
            assert points >= 4, decoded
            offset += 4 + points * 3 * 4
        assert offset == len(decoded), decoded

        bad_decompose_jobs = {
            "index_out_of_range": (tetra_vertices, (0, 1, 9), 0.1, 4, 1.0, 10000),
            "negative_index": (tetra_vertices, (0, 1, -1), 0.1, 4, 1.0, 10000),
            "nan_position": ((0, 0, 0, 1, 0, 0, 0, 1, 0, float("nan"), 0, 1),
                             tetra_faces, 0.1, 4, 1.0, 10000),
            "nan_concavity": (tetra_vertices, tetra_faces, float("nan"), 4, 1.0, 10000),
            "infinite_decimate": (tetra_vertices, tetra_faces, 0.1, 4, float("inf"), 10000),
            "partial_empty_mesh": ((0, 0, 0), (), 0.1, 4, 1.0, 10000),
            # Valid indices and counts, but a single degenerate triangle cannot
            # seed VHACD's 3D decomposition.
            "vhacd_degenerate_mesh": (
                tetra_vertices, (0, 0, 0), 0.1, 4, 1.0, 10000),
        }
        malformed_decompose = {
            "bad_magic": b"BAD!" + decompose_request([empty_job])[4:],
            "bad_version": struct.pack("<III", 0x44435750, 99, 0),
            "big_endian_header": struct.pack(">III", 0x44435750, 2, 0),
            "job_limit": struct.pack("<III", 0x44435750, 2, 256 * 1024 + 1),
            "vertex_limit": struct.pack("<IIII", 0x44435750, 2, 1, 4 * 1024 * 1024 + 1),
            "triangle_limit": struct.pack("<IIIII", 0x44435750, 2, 1, 0, 8 * 1024 * 1024 + 1),
            "truncated_job": decompose_request([empty_job])[:-1],
            "trailing_data": decompose_request([empty_job]) + b"garbage",
        }
        for name, data in malformed_decompose.items():
            request.write_bytes(data)
            decompose_response.write_bytes(sentinel)
            run("mesh_decompose_" + name, "meshtool", ["decompose", request, decompose_response],
                1, [decompose_response], "decompose:")
        # Oversized sparse requests must fail before attempting a multi-GiB
        # allocation. Mark the Windows file sparse before extending it.
        with request.open("wb") as sparse:
            if os.name == "nt":
                import msvcrt
                handle = msvcrt.get_osfhandle(sparse.fileno())
                returned = ctypes.c_ulong()
                assert ctypes.windll.kernel32.DeviceIoControl(
                    ctypes.c_void_p(handle), 0x900C4, None, 0, None, 0,
                    ctypes.byref(returned), None), "cannot create sparse request fixture"
            sparse.truncate((1 << 32) + 16)
        for operation in ("simplify", "decompose"):
            decompose_response.write_bytes(sentinel)
            run("mesh_" + operation + "_file_size_limit", "meshtool",
                [operation, request, decompose_response], 1, [decompose_response], "size limit")
        for name, job in bad_decompose_jobs.items():
            request.write_bytes(decompose_request([job]))
            decompose_response.write_bytes(sentinel)
            run("mesh_decompose_" + name, "meshtool", ["decompose", request, decompose_response],
                1, [decompose_response], "decompose:")
        assert "VHACD" in next(result["stderr"] for result in results
                               if result["name"] == "mesh_decompose_vhacd_degenerate_mesh")

        # A failed second job must not publish the successfully decomposed first one.
        request.write_bytes(decompose_request([
            (tetra_vertices, tetra_faces, 0.1, 4, 1.0, 10000),
            bad_decompose_jobs["vhacd_degenerate_mesh"],
        ]))
        decompose_response.write_bytes(sentinel)
        run("mesh_decompose_late_job_failure", "meshtool", ["decompose", request, decompose_response],
            1, [decompose_response], "VHACD")

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

        # Clips over the frame budget retain their full MMD duration. Their
        # fractional sampling rate must be represented consistently in DMX,
        # generated sequence QC, and the camera companion timeline.
        long_motion = root / "long_motion.vmd"
        long_span = 6328  # requires 23.6994 fps to use the full 5000-frame budget
        vmd(long_motion, camera=True, last_frame=long_span)
        long_base = ["-mdl", target, "-camerafov", "dmx", "-dmxencoding", "keyvalues2",
                     "-vmd", long_motion]
        run("vmd_fractional_budget_rate", "vmd2valvebiped", long_base)
        long_output = results[-1]["stdout"] + results[-1]["stderr"]
        fps_match = re.search(r'\$sequence "long_motion" "long_motion\.dmx" fps ([0-9.]+)', long_output)
        assert fps_match, long_output
        fps = float(fps_match.group(1))
        assert abs(fps - 30 * 4999 / long_span) < 1e-5, (fps, long_output)
        assert "5000 frames" in long_output, long_output
        for output in (root / "long_motion.dmx", root / "long_motion_camera.dmx"):
            text = output.read_text(encoding="utf-8")
            rate = re.search(r'"frameRate"\s+"float"\s+"([^"]+)"', text)
            duration = re.search(r'"duration"\s+"time"\s+"([^"]+)"', text)
            assert rate and abs(float(rate.group(1)) - fps) < 1e-5, (output, text[:500])
            assert duration and abs(float(duration.group(1)) - long_span / 30) < 0.001, (output, duration)
    report = {"passed": len(results), "cases": results}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"subtools integrity: {len(results)} cases passed")


if __name__ == "__main__":
    main()
