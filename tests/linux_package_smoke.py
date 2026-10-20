#!/usr/bin/env python3
"""Check the runnable metadata of a Linux release archive.

This is deliberately independent from the full package verifier: it checks
the ZIP central-directory mode bits before extraction, then starts every
native tool from a clean temporary directory.  It catches archives that are
valid ELF files but lose execute permission or the Linux loader entry.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import zipfile


ROOT = "NewPageMergeMDL/"
TOOLS = (
    "NewPageMergeMDL",
    "NewPageMergeMDL-Decompiler",
    "NewPageVRMLtoX3D",
    "subtools/ag2proportions",
    "subtools/l4d_animswap",
    "subtools/meshtool",
    "subtools/vmd2valvebiped",
)
USAGE = {
    "NewPageMergeMDL": (1, "usage: NewPageMergeMDL"),
    "NewPageMergeMDL-Decompiler": (1, "usage: NewPageMergeMDL-Decompiler"),
    "NewPageVRMLtoX3D": (0, "Usage: NewPageVRMLtoX3D"),
    "subtools/ag2proportions": (1, "CS2 AnimGraph2 proportion wrapper"),
    "subtools/l4d_animswap": (2, "l4d_animswap -vanilla"),
    "subtools/meshtool": (1, "simplify <request_file> <response_file>"),
    "subtools/vmd2valvebiped": (1, "vmd2valvebiped -vmd"),
}


def check_elf(name, data):
    if len(data) < 20 or data[:4] != b"\x7fELF":
        raise ValueError(f"{name} is not an ELF executable")
    # EI_CLASS=2 (64-bit), EI_DATA=1 (little endian), e_machine=62 (x86-64).
    if data[4] != 2 or data[5] != 1 or int.from_bytes(data[18:20], "little") != 62:
        raise ValueError(f"{name} is not a little-endian x86-64 ELF")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    if os.name != "posix":
        raise ValueError("Linux smoke checks must execute on a Linux host")
    expected = {ROOT + name for name in TOOLS}
    with zipfile.ZipFile(args.archive) as archive:
        infos = {info.filename: info for info in archive.infolist()}
        missing = expected - infos.keys()
        if missing:
            raise ValueError("Linux archive is missing: " + ", ".join(sorted(missing)))
        for member in sorted(expected):
            info = infos[member]
            mode = (info.external_attr >> 16) & 0o777
            if not mode & 0o111:
                raise ValueError(f"{member} has no executable permission in ZIP (mode {mode:o})")
            check_elf(member, archive.read(member))
        version = json.loads(archive.read(ROOT + "upstream-manifest.json"))["project_version"]
        with tempfile.TemporaryDirectory(prefix="newpage-linux-smoke-") as folder:
            root = Path(folder) / "NewPageMergeMDL"
            archive.extractall(folder)
            for name in TOOLS:
                binary = root / name
                if not os.access(binary, os.X_OK):
                    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
                headers = subprocess.run(["readelf", "-l", str(binary)], capture_output=True,
                                         text=True, timeout=20, check=True).stdout
                loader = re.search(r"Requesting program interpreter: ([^\]]+)", headers)
                if loader and not Path(loader[1]).is_file():
                    raise ValueError(f"{name} requires unavailable loader {loader[1]}")
                dynamic = subprocess.run(["readelf", "-d", str(binary)], capture_output=True,
                                         text=True, timeout=20, check=True).stdout
                needed = re.findall(r"\(NEEDED\).*\[([^\]]+)\]", dynamic)
                if needed:
                    deps = subprocess.run(["ldd", str(binary)], capture_output=True,
                                          text=True, timeout=20)
                    if deps.returncode or "not found" in deps.stdout + deps.stderr:
                        raise ValueError(f"{name} has unresolved dependencies: {deps.stdout}{deps.stderr}")
                print(f"{name}: loader={loader[1] if loader else 'static'}, needed={needed}")
                result = subprocess.run([str(binary)], cwd=folder, capture_output=True,
                                        text=True, errors="replace", timeout=20)
                status, marker = USAGE[name]
                output = result.stdout + result.stderr
                if result.returncode != status or marker not in output:
                    raise ValueError(f"{name} failed usage probe ({result.returncode}): {output}")
                if name not in ("NewPageVRMLtoX3D", "subtools/meshtool") and version not in output:
                    raise ValueError(f"{name} usage banner has the wrong release version")
            ag2 = root / "subtools/ag2proportions"
            for flag, marker in (("--help", "Usage:"), ("--version", f"ag2proportions {version}")):
                result = subprocess.run([str(ag2), flag], cwd=folder, capture_output=True,
                                        text=True, errors="replace", timeout=20, check=True)
                if marker not in result.stdout:
                    raise ValueError(f"ag2proportions {flag} output is incomplete")
    print(f"Linux package smoke check passed: {len(TOOLS)} ELF tools, dependencies, permissions and CLI probes")


if __name__ == "__main__":
    main()
