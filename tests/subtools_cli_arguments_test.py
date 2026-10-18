#!/usr/bin/env python3
"""Check strict CLI token parsing and output preservation for standalone subtools."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", required=True, type=Path)
    args = parser.parse_args()
    binary = args.bin_dir.resolve()
    if (binary / "subtools").is_dir():
        binary /= "subtools"
    suffix = ".exe" if os.name == "nt" else ""
    cases = []
    sentinel = b"existing output must survive invalid arguments"

    with tempfile.TemporaryDirectory(prefix="subtools-cli-arguments-") as folder:
        root = Path(folder)
        vmd_output = root / "existing-vmd-output.dmx"
        def run(name, tool, args, protected):
            before = {path: path.read_bytes() for path in protected}
            result = subprocess.run([str(binary / (tool + suffix)), *map(str, args)],
                                    cwd=root, capture_output=True, timeout=20)
            assert result.returncode != 0, (name, result.stdout, result.stderr)
            for path, data in before.items():
                assert path.read_bytes() == data, (name, "output changed", path)
            cases.append(name)

        vmd_base = ["-mdl", root / "missing-model.mdl", "-vmd", root / "missing-motion.vmd",
                    "-o", vmd_output]
        vmd_bad_values = {
            "armangle_suffix": ("-armangle", "35deg"),
            "armangle_nan": ("-armangle", "nan"),
            "armangle_inf": ("-armangle", "inf"),
            "armangle_overflow": ("-armangle", "1e1000"),
            "armangle_out_of_range": ("-armangle", "181"),
            "eyerange_suffix": ("-eyerange", "30x"),
            "eyerange_zero": ("-eyerange", "0"),
            "eyerange_overflow": ("-eyerange", "999999999999999999999"),
            "start_suffix": ("-start", "1frame"),
            "start_overflow": ("-start", "999999999999999999999"),
            "start_negative": ("-start", "-1"),
            "end_suffix": ("-end", "2.5"),
            "walkframe_suffix": ("-walkframe", "2frames"),
            "walkframe_negative": ("-walkframe", "-1"),
            "walkframe_overflow": ("-walkframe", "999999999999999999999"),
            "walktolerance_suffix": ("-walktolerance", "4units"),
            "walktolerance_zero": ("-walktolerance", "0"),
            "walktolerance_nan": ("-walktolerance", "nan"),
            "dmxmodel_suffix": ("-dmxmodel", "15junk"),
            "dmxmodel_overflow": ("-dmxmodel", "999999999999999999999"),
            "dmxmodel_unsupported": ("-dmxmodel", "2"),
        }
        for name, (option, value) in vmd_bad_values.items():
            vmd_output.write_bytes(sentinel)
            run("vmd_" + name, "vmd2valvebiped", [*vmd_base, option, value], [vmd_output])

        for name, option in (("vmd_missing_vmd", "-vmd"), ("vmd_missing_mdl", "-mdl"),
                             ("vmd_missing_pmx", "-pmx"), ("vmd_missing_output", "-o"),
                             ("vmd_missing_compile", "-compile"), ("vmd_missing_srcdir", "-srcdir"),
                             ("vmd_missing_game", "-game"), ("vmd_missing_armangle", "-armangle"),
                             ("vmd_missing_eyerange", "-eyerange"), ("vmd_missing_start", "-start"),
                             ("vmd_missing_end", "-end"), ("vmd_missing_walkframe", "-walkframe"),
                             ("vmd_missing_walktolerance", "-walktolerance"),
                             ("vmd_missing_dmxencoding", "-dmxencoding"),
                             ("vmd_missing_dmxmodel", "-dmxmodel"), ("vmd_missing_facemap", "-facemap"),
                             ("vmd_missing_faceset", "-faceset"), ("vmd_missing_camerafov", "-camerafov")):
            vmd_output.write_bytes(sentinel)
            extra = [option]
            if name.endswith("dmxencoding"):
                extra.append("-sound")
            run(name, "vmd2valvebiped", [*vmd_base, *extra], [vmd_output])

        l4d_output = root / "existing-l4d-output.qci"
        l4d_base = ["-vanilla", root / "missing-vanilla", "-rig", "bill", "-replace", "nick",
                    "-o", l4d_output]
        l4d_bad_args = {
            "skip_suffix": ["-skip", "2slots"],
            "skip_overflow": ["-skip", "999999999999999999999"],
            "skip_negative": ["-skip", "-1"],
            "dmxmodel_suffix": ["-dmxmodel", "15junk"],
            "dmxmodel_overflow": ["-dmxmodel", "999999999999999999999"],
            "via_empty": ["-via", ""],
            "via_empty_item": ["-via", "nick,,ellis"],
            "via_trailing_comma": ["-via", "nick,"],
            "via_unknown_survivor": ["-via", "nick,unknown"],
            "unknown_option": ["-bogus"],
            "unknown_rig": ["-rig", "unknown"],
            "unknown_replace": ["-replace", "unknown"],
        }
        for name, extra in l4d_bad_args.items():
            l4d_output.write_bytes(sentinel)
            run("l4d_" + name, "l4d_animswap", [*l4d_base, *extra], [l4d_output])
        for name, option in (("vanilla", "-vanilla"), ("rig", "-rig"), ("replace", "-replace"),
                             ("skip", "-skip"), ("dmxmodel", "-dmxmodel"), ("dmxencoding", "-dmxencoding"),
                             ("out", "-o"), ("outdir", "-outdir"), ("via", "-via"), ("ref", "-ref")):
            l4d_output.write_bytes(sentinel)
            run("l4d_missing_" + name, "l4d_animswap",
                [*l4d_base, option], [l4d_output])
        # Valid numeric tokens must reach input loading rather than fail argument parsing.
        l4d_output.write_bytes(sentinel)
        result = subprocess.run(
            [str(binary / ("l4d_animswap" + suffix)), *map(str, l4d_base),
             "-skip", "2", "-dmxmodel", "22"],
            cwd=root, capture_output=True, timeout=20)
        assert result.returncode != 0
        assert b"requires a complete integer" not in result.stderr, (result.stdout, result.stderr)
        assert l4d_output.read_bytes() == sentinel
        cases.append("l4d_valid_numeric_tokens")
        # Well-formed integer and scientific-notation float tokens pass parsing;
        # loading then fails only because the paths are deliberately absent.
        vmd_output.write_bytes(sentinel)
        result = subprocess.run(
            [str(binary / ("vmd2valvebiped" + suffix)), *map(str, vmd_base),
             "-armangle", "3.5e1", "-eyerange", "3e1", "-start", "0", "-end", "1",
             "-walkframe", "0", "-walktolerance", "1e-1", "-dmxmodel", "22"],
            cwd=root, capture_output=True, timeout=20)
        assert result.returncode != 0
        assert b"requires a " not in result.stderr, (result.stdout, result.stderr)
        assert vmd_output.read_bytes() == sentinel
        cases.append("vmd_valid_numeric_tokens")

    print(f"subtools CLI arguments: {len(cases)} invalid-input cases passed")


if __name__ == "__main__":
    main()
