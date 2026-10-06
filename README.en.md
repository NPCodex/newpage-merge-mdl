# NewPageMergeMDL v1.2.0

English | [简体中文](README.md)

**Project version: v1.2.0.** The compiler, decompiler and bundled tools share this
version. The output model format remains MDL v49.

A Source model toolchain based on [PulseModel](https://github.com/ToppiOfficial/PulseModel),
with independently implemented StudioMDL-CE / StudioMDL++ / NekoMDL compatibility extensions.
NekoMDL integration follows its supplied Chinese v2.3.0 changelog.
The compiler is `NewPageMergeMDL.exe`; the decompiler is
`NewPageMergeMDL-Decompiler.exe`. Windows x64 and Linux builds are verified by
GitHub Actions. See [AUTOMATION.md](AUTOMATION.md) for automatic upstream integration
and GitHub Release configuration.

## Inherited PulseModel features

SMD / DMX / FBX compilation, model decompilation and utility tools are retained. Fast SMD loading, meshoptimizer, dynamic output buffers, mesh splitting, `-nodx80`, animation `reverse`, macro defaults / `$endmacro`, `nocull`, mesh-selected `$bbox` and unused-material removal already exist upstream and are not additions by this project.

## Additions compared with original PulseModel

This comparison uses merge baseline `52cf296a953fd6c2d072e34cfde5eb8eccc95564`. The following features and compatibility fixes are implemented independently; they do not certify full parity with the closed-source reference compilers. See [COMPATIBILITY.md](COMPATIBILITY.md) for arguments and behavioral differences.

### QC, animation and StudioMDL++ compatibility

| Feature | Supported additions |
| --- | --- |
| Variables and diagnostics | `$setvariable` replaces variables; duplicate `$definevariable` warns and preserves the first definition. |
| Include resolution | `$IncludePrefix` / `-IncludePrefix`, `$IncludeAnimPrefix` / `-IncludeAnimPrefix`; `$PUSHDInclude` enables lookup in the current pushd directory. |
| Animation extensions | `copy reference [pos] [rot]`, `match reference [pos] [rot]`, and nested animation `if / else if / else`, with this project's documented semantics. |
| Animation culling / rendering | `-cullanims` forces unreferenced-animation culling while honoring `nocull`; `-MostlyOpaque` overrides QC render settings. |
| Sequence ordering / UTC flag | Preserves order from existing v48/v49 models by default; `-noremap` selects QC order. `$sequence gmtime` survives decompilation; UTC synchronization needs mod support. |
| VTA compatibility fix | Repeated `flex` / `flexpair` names preserve independent frame deltas and weight ramps. |

### StudioMDL-CE face, bone and output extensions

| Feature | Supported additions |
| --- | --- |
| Flex controllers | `$OverrideFlexControllers`, `$AllowDuplicationFlexControllers`, model-block `addcontrollerbyflex`. |
| Inverse flexes / delta scaling | `$AddInvStudioFlexes` / `InvertControllers`; `$DefaqScale`, `$IgnoreDMXDefaq`, per-key `fscale`. |
| Decay / default flex | `$ZeroFlexDecay`; default-flex baking and `$IgnoreDefaultFlexKey`; `NoAutoDMXRulesLegacy` clears previous automatic rules/controllers. |
| Eyes / eyelids | `$EyeballScale`, `$IgnoreEyeballScaling`, `$IgnoreEyeballIrisScale`, `$IgnoreEyelid`; eye binding remains scoped to each model. |
| DMX normals / wrinkles | `$ComputeDeltaNormals`, `$ComputeWrinkles`, `$ComputeNormalsAndWrinkles` and model-level overrides; `$RemapFlexToGlobal` maps flexes into compiled bind space. |
| Per-model options | `$body` / `$bodygroup studio` face blocks; private `RenameMat` / `RenameMatByPrefix`; `BindToOneBone` / `$CollisionBindToOneBone`. |
| Bones / bounds | Opt-in `$CEBoneRules`; `$AllowCollapseVertexBone`; `$AlwaysCollapseByPrefix` and its launch equivalent; `$HBoxIgnoreChild`. |
| Paths / output limits | `$PUSHDProcedural`; `$OutDir` / `-OutDir`; `$OutputBufferSize`, `$MDLOutputBufferSize`, `$ANIOutputBufferSize` check sizes before writing. |

CE compatibility switches are opt-in; some boolean switches toggle when repeated. Single-bone weighting is experimental, and arbitrary complex rigs are not certified equivalent to CE.

### NekoMDL import and scripting extensions

Implementation follows the supplied **Chinese v2.3.0 changelog**.

| Feature | Supported additions |
| --- | --- |
| More formats | Fast cgltf import of glTF / GLB / VRM; Assimp import of OBJ, DAE, PMX and other supported formats; `$NoFastGltf` selects Assimp for glTF. The existing ufbx FBX importer remains. |
| Scenes / morphs | Node transforms, static scale, skins, named morph targets; missing UVs/morph normals are accepted, and missing base normals are generated. |
| Node / animation selection | `InNode` selects a node and descendants; `Pick` selects an animation; `SampleRate` controls sampling; `$FPS` sets subsequent default playback/sampling rates; `$UpAxis y/z gltf/assimp` independently sets import axes. |
| Faces / driver bones | `$NekoModel` supports multiple studios, shared flexes/rules and scoped eyes/lids; named `flex` / `flexpair` bind source morphs; `$NekoDriverBone`. |
| Jiggle / animation transforms | `$JiggleBoneRealign`, `$ReverseJiggleBoneRotation`; animation `NoBoneRealign`, `AppendScale`. |
| Materials / morph normals | `$PreRenameMaterial`; `$DiscardVertexAnimationNormals` removes delta normals while retaining base normals and position deltas. |
| Resource budgets | `$MaxVerts limit [clamp]` splits per-material output meshes; `$MaxBones` / `-maxbones`; `$FileBufferSize` caps each serialized output. Algorithm/default differences are documented below. |
| Scripts | Line `$if/$ifdef/$elif/$eldef/$else/$endif`; `$UndefineVariable`, `$Msg`, `-Dname value`; `$Include file iffileexists`; `$QCAssert` with an omitted expected boolean. |
| Post-compilation actions | `-checksequenceorder`; `-reloadhlmv` notifies Windows HLMV; `-playbeep` signals success/failure. |

### Project tooling and maintenance

- Compiler, decompiler and utilities share the project naming and **v1.2.0** version; colored startup banner, plain redirected logs.
- Automatic PulseModel integration through a maintained patch, followed by Windows/Linux builds, tests and GitHub Release publication. Conflicts or failed checks stop publication. New closed-source CE/++/Neko features require manual analysis.
- 85 compatibility tests and 16 automation tests inspect actual outputs. The supplied complete `survivor_teenangst.qc` compiles with mixed DMX/GLB bodies, and the user's Alyx QC remains compilable. User models and reference compiler binaries are not redistributed.

## v1.2.0 validation and optimizations

- SMD/VTA loading reads lines directly instead of retaining redundant whole-file buffers. Invalid bone parents, non-finite coordinates and invalid weights fail explicitly; more than 16 source weights no longer cause an out-of-bounds read.
- Sparse mesh partition maps and ownership tracking reduce a 9000-vertex, 3-vertex-cap benchmark from 300.7 ms to 15.8 ms, with four byte-identical output files. This measures an extreme partition case, not a universal speedup.
- A 181,271,943-byte (172.88 MiB) VTA with 2.4 million real vertex records compiles successfully. Peak working set falls from 880 MB to 376 MB with byte-identical output. Run `tests/stress_vta.py` to reproduce.
- Tests cover 130 output materials, collapse of 512 source bones, 256 output bones and animation of bone 255. The 256-bone case uses frame animation encoding. **512 final output bones remain unsupported**: standard MDL/VVD byte-sized bone indices require rejection above 256 before writing.
- Added multi-bone DMX morph, split flex/LOD and collision rename/parent regressions. The supplied extreme model compiles with 126 bones and 572277 VVD vertices; in-game loading remains unverified.
- Automatic releases increment patch versions and recognize existing versioned tags. See [RESEARCH.md](RESEARCH.md) for investigation results and remaining work.

## Unfinished features and known issues

| Area | Current status and limitations |
| --- | --- |
| Neko import parity | Uses cgltf and Assimp 6.0.4. Basic transforms, skins, named morphs, node filters and animation sampling are tested. Every Assimp format, complex FBX/VRM rigs and in-game behavior have not been certified. |
| glTF animation/compression | The fast importer supports LINEAR, STEP and CUBICSPLINE translation/rotation; static scale is baked into geometry. Animated scale, morph weights and mesh swaps fail explicitly and need baking or QC flex controllers. Draco, meshopt compression and GPU instancing need expanded source files. Assimp fallback interpolation may differ for STEP/CUBICSPLINE; prefer the fast path. |
| Neko algorithms/defaults | `$MaxVerts` splits per-material output meshes, with a real 65536 index ceiling, rather than reproducing source pre-splitting/clamping. `$FileBufferSize` caps serialized output sizes without fixed preallocation. Existing dynamic buffers, bone collapse and sequence ordering defaults remain. Use `$CEBoneRules` to retain weighted bones. |
| Neko faces/drivers | Basic stereo balance and jiggle rotation/constraints are checked against binary output. Multi-studio faces and drivers have output tests; complex procedural/driver/IK hierarchy parity is unverified. |
| Legacy mesh algorithms | CE `$UseLegacyStripify` / `$UseLegacyClampMethod` and Neko `-nvtristrip` remain unimplemented and fail explicitly. |
| `gameinfo.txt` AppID mounting | Unimplemented; AppID-based discovery of other games' resources is unavailable. |
| Full syntax/output parity | Animation copy, channel matching and conditions use this project's documented semantics. Complete StudioMDL++ parity is unverified. Output is v49 rather than the reference compilers' v48; whole-file byte equality is not expected. |
| Complex face/DMX rigs | Basic normals, wrinkles, inverse flexes and eyelid rules are tested. Complex corrective rigs, hard edges, authored normals, controller remaps and in-game eyelids need more verification. |
| Material renaming | Many-to-one material renames fail; merging material mesh ranges is unsupported. |
| `NoAutoDMXRules` | Retains PulseModel's per-source suppression, differing from CE's observed suppression of prior auto rules in multi-model scripts. `NoAutoDMXRulesLegacy` clears previous automatic rigs/controllers. |
| `addcontrollerbyflex` | Honors documented min/max instead of reproducing CE's range parser bug that writes both values into min. |
| Bones, collision and large models | `$CEBoneRules` is opt-in; single-bone weighting is experimental. Complex procedural/IK/LOD rigs, collision physics and extreme models lack comprehensive parity/stress tests. Format field widths still constrain engine compatibility. |
| Animation bounds fix | Removes the 9999-unit accumulation sentinel that truncated large translations; clamps both endpoints to the coordinate interval. Positive/negative animations beyond 16384 units are tested. |
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
and 16 automation tests. Tests inspect MDL/VVD data and decompile animations to
check positions, rotations and conditions. The user-provided Alyx QC compiled
successfully with 113 bones and 27,571 VVD vertices; this does not cover in-game
loading or rendering.

## Credits and license

Original project: Toppi. The original [MIT LICENSE](LICENSE) and third-party
notices are preserved. [UPSTREAM_README.md](UPSTREAM_README.md) keeps upstream
information, including old program names and download links, for reference.
StudioMDL-CE / Tools++ closed-source executables and recovered source are not
included in this project.
