# NewPageMergeMDL v1.1

English | [简体中文](README.md)

**Project version: v1.1.** The compiler, decompiler and bundled tools share this
version. The output model format remains MDL v49.

A Source model toolchain based on [PulseModel](https://github.com/ToppiOfficial/PulseModel),
with independently implemented StudioMDL-CE / StudioMDL++ compatibility extensions.
The compiler is `NewPageMergeMDL.exe`; the decompiler is
`NewPageMergeMDL-Decompiler.exe`. Windows x64 and Linux builds are verified by
GitHub Actions. See [AUTOMATION.md](AUTOMATION.md) for automatic upstream integration
and GitHub Release configuration.

## Features

- PulseModel SMD / DMX / FBX compilation, model decompilation and utility tools.
- `$setvariable`, include/model prefixes, `$PUSHDInclude` and bone prefix collapse.
- `-cullanims`, `-MostlyOpaque` and duplicate variable warnings.
- Independently specified animation `copy`, `match pos/rot` and nested conditions.
- Repeated VTA `flex` / `flexpair` names preserve separate frame deltas and ramps.
- `$sequence gmtime`, existing sequence order preservation and `-noremap`.
- CE controller overrides/duplicates, inverse flexes, `fscale`, zero decay and default pose baking.
- Eye scaling, DMX smooth normals/wrinkles and flex remapping to compiled bind space.
- Bodygroup face blocks, per-reference material renames, single-bone weights,
  optional CE bone collapse rules and output size limits.
- Colored terminal banner; redirected logs remain plain text.

## Unfinished features and known issues

| Area | Current status and limitations |
| --- | --- |
| CE legacy mesh algorithms | `$UseLegacyStripify` (NvTriStrip) and `$UseLegacyClampMethod` (global vertex clamping) are unimplemented and fail explicitly. |
| `gameinfo.txt` AppID mounting | Unimplemented; AppID-based discovery of other games' resources is unavailable. |
| Full syntax/output parity | Animation copy, channel matching and conditions use this project's documented semantics. Complete StudioMDL++ parity is unverified. Output is v49 rather than the reference compilers' v48; whole-file byte equality is not expected. |
| Complex face/DMX rigs | Basic normals, wrinkles, inverse flexes and eyelid rules are tested. Complex corrective rigs, hard edges, authored normals, controller remaps and in-game eyelids need more verification. |
| Material renaming | Many-to-one material renames fail; merging material mesh ranges is unsupported. |
| `NoAutoDMXRules` | Retains PulseModel's per-source suppression, differing from CE's observed suppression of prior auto rules in multi-model scripts. `NoAutoDMXRulesLegacy` clears previous automatic rigs/controllers. |
| `addcontrollerbyflex` | Honors documented min/max instead of reproducing CE's range parser bug that writes both values into min. |
| Bones, collision and large models | `$CEBoneRules` is opt-in; single-bone weighting is experimental. Complex procedural/IK/LOD rigs, collision physics and extreme models lack comprehensive parity/stress tests. Format field widths still constrain engine compatibility. |
| Diagnostics and performance | Bounding-box/cmdlist diagnostic parity is incomplete. No systematic performance comparison against the reference compilers has been performed. |
| Engine loading and UTC animation | Successful compilation does not certify in-game behavior. `gmtime` requires support in the target mod. |
| Automatic updates | PulseModel source is integrated automatically; patch conflicts or failing checks stop publication. CE/++ versions are tracked as references; new closed-source features require manual analysis and implementation. |
| Other Tools++ tools | VBSP, VVIS, VRAD and BSPZIP are map tools outside this model compiler's scope. |

See [COMPATIBILITY.md](COMPATIBILITY.md) for syntax and intentional differences,
and [BINARY_ANALYSIS.md](BINARY_ANALYSIS.md) for binary investigation evidence.
Complete compatibility with StudioMDL-CE / StudioMDL++ is not claimed.

## Build from source

Windows: use a Visual Studio 2022 x64 developer terminal with CMake 3.22+ and Ninja.

```powershell
cmake --preset x64-release
cmake --build --preset x64-release
```

Output: `out/build/x64-release/NewPageMergeMDL/`.

Linux: install CMake and a C/C++ compiler, then run:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
```

Dependencies are vendored in `libs/`; no additional package manager is required.

## Usage

```powershell
NewPageMergeMDL.exe model.qc -game "C:/Games/MyMod" -vtxformat 1
NewPageMergeMDL-Decompiler.exe model.mdl -smdanimation
```

`.qc` and `.pulseqc` inputs remain supported. Internal `pulse` namespaces are
preserved for source compatibility.

## Validation

```powershell
python tests/compatibility.py out/build/x64-release/NewPageMergeMDL/NewPageMergeMDL.exe
python -m unittest discover -s tests -p test_automation.py
```

There are 56 compatibility tests using temporary SMD/QC and synthetic DMX fixtures,
and 12 automation tests. Tests inspect MDL/VVD data and decompile animations to
check positions, rotations and conditions. The user-provided Alyx QC compiled
successfully with 113 bones and 27,571 VVD vertices; this does not cover in-game
loading or rendering.

## Credits and license

Original project: Toppi. The original [MIT LICENSE](LICENSE) and third-party
notices are preserved. [UPSTREAM_README.md](UPSTREAM_README.md) keeps upstream
information, including old program names and download links, for reference.
StudioMDL-CE / Tools++ closed-source executables and recovered source are not
included in this project.
