# NewPageMergeMDL v1.2.18

English | [简体中文](README.md)

**Project version: v1.2.18.** The compiler, decompiler and bundled tools share this
version.

A Source model toolchain based on [PulseModel](https://github.com/ToppiOfficial/PulseModel),
with independently implemented StudioMDL-CE / StudioMDL++ / NekoMDL compatibility extensions.
NekoMDL integration follows its supplied Chinese v2.3.0 changelog.
The compiler is `NewPageMergeMDL.exe`; the decompiler is
`NewPageMergeMDL-Decompiler.exe`. Windows x64 and Linux builds are verified by
GitHub Actions. See [AUTOMATION.md](AUTOMATION.md) for automatic upstream integration
and GitHub Release configuration.

The objective is one PulseModel-based compiler integrating CE, NekoMDL, StudioMDL 2013 and StudioMDL++ model compilation features. See the [five-compiler feature checklist](FEATURE_MATRIX.md) for source-by-source status and priorities.

## v1.2.18: CSGO LOD skinning and CONTENT mounts

For CSGO legacy (gameinfo SteamAppId 730), lower LODs inherit skin weights from the nearest root-model vertex; ties use UV, normal and source index. `$skinnedLODs` preserves authored lower-LOD weights. Other games retain their defaults. Spatial lookup precedes the existing LOD bone remapping. Two-stage root/higher-LOD tolerance matching checks position, UVs, normals, weights and tangents. Small UV-boundary fixtures match the installed stock CSGO StudioMDL; this is not whole-file parity for arbitrary models.

`$contentrootrelative` supports CONTENT `*` / `?` patterns, VPKs and archive chunks. Loose directory files precede archives; GAME lookup precedes CONTENT, which remains opt-in. All 187 compatibility and six mount tests pass; Plum and Yvette compile and pass structural checks. No new in-game validation was performed. Cloth, full SubD and complete bone-collapse parity remain open.

Supply the correct `-game` directory for CSGO/MCV, even with a separate OutDir; `-vtxformat` alone only selects VTX layout. CSGO/MCV targets now use a 256-byte extended header with a zero FE pointer slot before bodygroup presets. Other targets retain their layout. Installed stock models confirm this span. Each game's preset fixture survives 15 seconds under its HLMV/debugger without access violations; temporary game files were removed. This fixes the serialization prerequisite, not the full cloth pipeline.

## v1.2.17: startup description correction

Compiler and decompiler startup messages now use `Source model toolchain` instead of a fixed MDL version label. Model output formats are unchanged.

## v1.2.16: CSGO / MCV loading crash fix

When `-game` supplies a gameinfo.txt with SteamAppId 730 (CSGO legacy) or 1012110 (MCV), the compiler automatically selects extended VTX headers: 33-byte strip groups and 35-byte strips. The former 25/27-byte default is misinterpreted by these loaders and can crash HLMV or the game even though the MDL version is 49. Other targets keep their defaults. Explicit QC `$vtxformat` / pulseqc `vtx_archetype` override detection; CLI `-vtxformat` has highest priority. Forcing legacy layout for these targets emits a warning.

One compiler supports both targets. Use the actual `.../csgo` or `.../vietnam` directory with `-game`; `-vtxformat 1` only selects VTX layout. Since v1.2.18 the MDL extended header also follows the detected game, so supply `-game` even when setting a separate OutDir. Deploy the complete MDL/VVD/DX90 VTX/PHY set. Mixing a new MDL with an old VTX can still crash. Preserve the CSGO player/custom_player model path: an ordinary test-model directory selects the old player-animation behavior. The original QC needs no extra stock-player animation include.

All 182 compatibility and 20 automation tests pass. Yvette body/three arms QCs and MCV body/arms/legs QCs compile and load in their respective installed HLMV tools; all seven outputs survive 15-second debugger checks without access violations. Actual character rendering and Yvette included-animation playback were separately observed. MCV tests cover players, first-person arms, bots, ragdolls and map reload on mcv_camp/mcv_bridge. CSGO tests on de_dust2/ar_baggage cover player/bot replacement, 11 skins × 18 body combinations in bounded native-entity batches, normal player death and map reload. See the [v1.2.16 report](tests/reports/v1.2.16-validation.json) for CSGO runtime evidence. Plum retains legacy output and passes structural validation with 126 bones / 572,277 vertices. These are bounded model/scenario checks, not universal game compatibility.

## v1.2.15: CSGO QC compatibility (31 entries; cloth remains unfinished)

Implements 31 of the previously missing 33 command entries: bone controllers/runtime flags, prefix/substr renaming, bind-axis and center adjustments, bounding-box policies, collision precision, appended sources, attachment replacement, CONTENT lookup, internal/physics naming, and virtual VTA generation from OBJ frames. Output changes are serialized into MDL/VVD/PHY. Virtual VTA supports flexfile, native `$vta` and VCA without intermediate files and rejects changed frame topology.

This is not 31 new algorithms. `$externaltextures` warns and ignores as in the reference; `$gamma` has no texture-processing use in this Source pipeline; `$skinnedLODs` corresponds to the existing native per-LOD skin preservation policy. `$insertbone` reparents without inserting a bone, matching the enabled reference code. `$subd` emits the subdivision-surface header flag; the complete quad/SubD importer has not been ported.

`$cloth` and `$clothplanecollision` remain **unimplemented and rejected**. They require finite-element nodes, constraints, control-bone backsolving and the CSGO extended-header data, rather than a jigglebone or keyvalues substitute. All 19 new targeted cases, 181 compatibility tests and 20 automation tests pass. Plum (126 bones, 572,277 vertices) and Yvette compile and pass serialized-output checks. No CSGO in-game validation is claimed. See [COMPATIBILITY.md](COMPATIBILITY.md) and the [validation record](tests/reports/v1.2.15-validation.json).

## v1.2.14: CSGO QC triangle-order compatibility

Adds `$preservetriangleorder` with actual cache/overdraw and NvTriStrip sorting bypass, using reference depth-first edge traversal. It takes precedence over `$UseLegacyStripify`, retaining bone palettes, flex groups and the selected VTX format. Global source-face order across materials/groups is not guaranteed. A self-authored 32-face grid matches CE order; regression covers command case, DX80/DX90, both VTX layouts, LODs and legacy combinations. The original Yvette QC compiles (144 bones, 65,902 vertices), and Plum still compiles. All 162 compatibility and 20 automation tests pass; CSGO in-game behavior has not been tested.

## v1.2.13: Insurgency 2 / Military Conflict: Vietnam QC fixes

Restores legacy single/double-backslash macro continuations alongside `$endmacro`. Attachments, hitboxes and hitgroups accept final `$renamebone` aliases before bone retention; case-only bone renames are allowed, while collisions with a different bone remain errors. Both supplied original QC/QCI sets compile without input changes and pass MDL/VVD/VTX structure validation. All 161 compatibility and 20 automation tests pass. In-game behavior in these two games has not been tested in this batch.

## v1.2.12: CE LOD option recovered through binary analysis

Static analysis of the CE x64 LOD parser and three self-authored reference compiles confirm `replacemodel source replacement reverse`. The case-insensitive option belongs on the same command line and reverses replacement LOD winding. Imported normals and shared sources remain unchanged. DX80/DX90 regression checks cover reversed and later ordinary LODs. All 158 compatibility and 20 automation tests pass.

The changelog's `replacemesh` remains unresolved: neither supplied x86 nor x64 binary contains that token, and the inspected x64 parser exposes replacemodel/replacematerial/removemesh. This recovered reverse option is not treated as proof of that changelog entry.

## v1.2.11: glTF animation interpolation on the Assimp path

Fixes lost STEP markers and CUBICSPLINE tangents with `$NoFastGltf`. Assimp still imports geometry and skins; animation is sampled from original glTF accessors without building a second geometry copy. Eighteen translation checks cover LINEAR, STEP and CUBICSPLINE on both backends across glTF/GLB/VRM. Quaternion animation, unnamed nodes/clips and scale/morph-weight baking are also checked. All 157 compatibility and 20 automation tests pass. Other Assimp formats are not universally verified.

## v1.2.10: Neko procedural parent compatibility

`$NekoDriverBone` now accumulates pose-animation ancestor transforms and resolves world poses against the final model's bind parents. Animated ancestors and differing pose/model hierarchies are retained. Sampling sources no longer define the model skeleton, including when the command precedes `$body`. Six self-authored Neko 2.3.0 reference cases cover separate parents, parent animation, hierarchy changes, scale, renamed parents and multiple helpers; twelve command-order regression cases pass. Native `$driverbone` sampling semantics remain unchanged. All 154 compatibility and 20 automation tests pass.

## v1.2.9: Neko morph mapping and output preservation

With `$dmxcompatibility neko`, `$RenameMorph` maps exact imported FBX/glTF names once: missing names are ignored, the latest definition wins, mappings do not chain, and QC declarations remain unchanged. Named flex blocks retain declared keys. Native global renaming is preserved; ambiguous target names are rejected.

Output files are staged with checked writes, flushes and closes, then backed up and replaced. Handled failures roll back the set. Directory conflicts and Windows VTX sharing locks preserve prior bytes in tests. Power loss and forced termination recovery are not guaranteed. All 153 compatibility and 20 automation tests pass.

## v1.2.8: five-compiler integration focus

Restores warning-only acceptance of older Neko `$prefer_fbx` and `$forcecapsules` directives, matching Neko 2.3.0 without changing import or generating capsules. `-usenvtristrip` selects the existing legacy backend. CE `$DontDestroy` / `-DontDestroy` accepts the default output-preservation policy. All 150 compatibility tests pass. The two StudioMDL 2013 archives count as one compiler with different dependencies.

## v1.2.7: reference flex policies and production validation

Adds `$dmxcompatibility native|ce|neko`, preserving native defaults while matching distinct reference rule/controller policies in 14 cases per compiler. Claudia is tested with its actual materials, facial changes, an isolated generated decimated LOD and ragdoll physics in GMod. Both original Hair QCs still compile. Repeated joint weights and macro error provenance are fixed; output preflight and serialized-table checks are expanded. `-perfjson` includes individual processing stages. There are 146 compatibility and 20 automation tests. See [IMPROVEMENTS.md](IMPROVEMENTS.md).

## v1.2.6: compatibility, ragdolls and package verification

Adds explicit copy weightlists, fixes procedural collision geometry causing unstable ragdolls, improves include diagnostics and long-scene sampling. Complete Hair player/NPC models were tested in GMod. There are 138 compatibility and 20 automation tests. See [IMPROVEMENTS.md](IMPROVEMENTS.md) for all seven areas and unresolved differences.

## v1.2.5: Hair QC compilation fix

Correct overly strict bodygroup validation; add final-product and preset-integer regressions. The current suite has 128 compatibility tests.

## v1.2.4: seven improvements

- Ordered SearchPaths, AppID/Steam library discovery, directories and VPK v1/v2 with preload/split archives; `-steamdir` overrides Steam discovery.
- Direct Draco decoding with attribute IDs, normals, UVs and uncompressed morphs; corrupt streams fail explicitly.
- `BakeSceneAnimation <clip> SceneSampleRate <fps>` samples scale, skinning and morph weights into vertex flex frames. Emits `.vertexanim.json`, ships GMod Lua playback and includes sampled render bounds.
- Per-bone `$collisionjoints` VHACD decomposition preserves mass, hierarchy and constraints.
- Six CE/Neko differential fixtures check hierarchy, transforms, IK/LOD, jiggle, DMX, controllers and eyelid bindings. Fixed an orphan VTA eyelid descriptor; existing corrective/driver/normal regressions remain covered.
- Actual GMod Alyx loading, faces/eyelids and forced LOD, plus authored vertex-animation and two-body physics/ground-contact tests. White material override isolates geometry; authored shaders are not comprehensively certified.
- `-perfjson` phase timings/peak working set and isolated repeated production benchmarks with deterministic output checksums.

**146 compatibility tests and 20 automation tests.** Usage and bounded results: [VALIDATION.md](VALIDATION.md).

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

- The compiler, decompiler and utilities share the NewPageMergeMDL project naming and current project version; compiler startup messages and redirected logs are plain text, without a colored banner.
- Automatic PulseModel integration through a maintained patch, followed by Windows/Linux builds, tests and GitHub Release publication. Conflicts or failed checks stop publication. New closed-source CE/++/Neko features require manual analysis.
- 146 compatibility tests and 20 automation tests inspect actual outputs. The supplied complete `survivor_teenangst.qc` compiles with mixed DMX/GLB bodies, and the user's Alyx QC remains compilable. User models and reference compiler binaries are not redistributed.

## v1.2.3: fewer incomplete features

- Model-scoped `RenameMat` now supports many-to-one material names. Mesh ranges, triangles, morph vertex indices and face tags are regrouped without affecting other body choices. Tests cover six vertices, two LODs and flex output.
- The fast glTF path decodes meshopt ATTRIBUTES, TRIANGLES and INDICES streams and applies NONE/OCTAHEDRAL/QUATERNION/EXPONENTIAL/COLOR filters. EXPONENTIAL attributes and both index modes have output tests for geometry, UV, flex and decompiled animation; other filters are not individually certified. Encoding quantization remains observable. Invalid ranges and corrupt streams fail before output.
- Static unskinned `EXT_mesh_gpu_instancing` expands shared meshes under per-instance translation, rotation and scale, retaining inherited transforms, morph targets and InNode subtree selection. Rotation, mirrored scale and invalid quaternions have tests. Expanded scenes retain the source node/bone budget.

The unsupported material-merge row is removed and the glTF compression/instance limitation is narrowed. Draco, AppID mounting, animated scale/weights, complex-rig parity and engine validation remain open. There are 127 compatibility and 20 automation tests.

## v1.2.2: six improvements

- **Bodygroups:** 64-bit combination arithmetic accepts up to 2^31 combinations (body values 0..2147483647). Tests accept 31 binary groups and reject 32 before output. Fixed single-choice parts no longer add meaningless preset-mask digits.
- **Skin groups:** check materials × families × 2 bytes before allocating the table, including configured MDL/file budgets. Tests cover 1001 skins and preservation of prior outputs on rejection.
- **Global clamping:** `$UseLegacyClampMethod` splits across materials. `$MaxVerts limit [clamp]` controls the trigger and piece cap (at most 65536). LODs, flexes and eyeball mesh references move with vertices. Added `_clamped` bodyparts share the original base and choices, with blank alternatives for absent pieces. Conservative triangle reservation operates on the unified output dictionary, rather than reproducing all historical CE source-stage behavior.
- **Animation:** retain bones and parents used only by `localhierarchy`; reject self-parenting. Explicit `$alwayscollapse` retains its existing precedence.
- **DMX:** validate corner counts and index bounds before normal collapsing and flex indexing, covering positions, normals, UVs, balance and speed. Finite-number validation also covers blendweights, balance and speed.
- **Collision:** accumulate volume-weighted mass in double precision to avoid NaN with large biases; reject nonpositive biases and unrepresentable volumes. Single-body `$collisionmodel` gains `$decomposeconcave` using bundled VHACD for closed, connected concave meshes with a positive `$maxconvexpieces`. Ordinary `$concave` retains island splitting; v1.2.4 also supports ragdoll decomposition.

**v1.2.5 fix:** correct an overly strict check that blocked the complete Hair QC. Both original player and NPC QCs compile, with 126 / 124 bones and 572277 vertices, without changing the user models. Validate stored bodygroup bases and preset values while retaining diagnostics.

## v1.2.1 additions and fixes

- `$UseLegacyStripify` / `-nvtristrip` select the bundled NvTriStrip backend; meshoptimizer remains the default. Tests cover DX80/DX90, both VTX layouts, LODs and skin remapping across hardware bone palettes. The legacy algorithm removes duplicate and index-degenerate faces.
- LOD bone replacement resolves chains and rejects cycles or conflicting targets. Added combined output checks for IK chains, procedural drivers, renamed bones and unused-bone collapse.
- DMX loading rejects NaN/Inf in geometry, weights and animation numbers. Corrective COMBO/DOMINATE rules have numeric evaluation tests; comprehensive complex-rig parity remains unverified.
- Large translations and oversized RLE animation records use frame encoding, with float32 positions when half precision would overflow. Tests cover 255-frame repeat boundaries and section seams. Compressed IK/local-hierarchy offsets above 32767 bytes fail before replacing output files.
- Long PHY surface properties, root-bone names and merge names are no longer truncated by 512-byte temporary buffers.
- Animation range scanning visits contiguous poses. A 128-bone, 1800-frame benchmark improves its three-run median from 118.1 to 109.5 ms, with identical SHA256 values for four output files. This measures the compression stage of one fixture.

See `libs/nvtristrip/SOURCE.md` for dependency provenance and [RESEARCH.md](RESEARCH.md) for the six investigations and remaining work.

## v1.2.0 validation and optimizations

- SMD/VTA loading reads lines directly instead of retaining redundant whole-file buffers. Invalid bone parents, non-finite coordinates and invalid weights fail explicitly; more than 16 source weights no longer cause an out-of-bounds read.
- Sparse mesh partition maps and ownership tracking reduce a 9000-vertex, 3-vertex-cap benchmark from 300.7 ms to 15.8 ms, with four byte-identical output files. This measures an extreme partition case, not a universal speedup.
- A 181,271,943-byte (172.88 MiB) VTA with 2.4 million real vertex records compiles successfully. Peak working set falls from 880 MB to 376 MB with byte-identical output. Run `tests/stress_vta.py` to reproduce.
- Tests cover 130 output materials, collapse of 512 source bones, 256 output bones and animation of bone 255. The 256-bone case uses frame animation encoding. **512 final output bones remain unsupported**: standard MDL/VVD byte-sized bone indices require rejection above 256 before writing.
- Added multi-bone DMX morph, split flex/LOD and collision rename/parent regressions. The supplied extreme model compiles with 126 bones and 572277 VVD vertices. Subsequent v1.2.6/v1.2.7 checks cover GMod geometry and physics; material validation still lacks assets.
- Automatic releases increment patch versions and recognize existing versioned tags. See [RESEARCH.md](RESEARCH.md) for investigation results and remaining work.

## Unfinished features and known issues

This list reflects v1.2.18 implementation and existing validation records. “Unverified” identifies a coverage gap, not an unimplemented feature.

| Area | Current status and remaining work |
| --- | --- |
| CSGO cloth and SubD | `$cloth` / `$clothplanecollision` are unimplemented; `$subd` provides the global header flag only. Complete quad/SubD import and cloth in-game verification remain unfinished. |
| Integration gaps | CE replacemesh semantics remain unconfirmed. Separate/animated Neko parents and differing pose hierarchies are fixed and compared with reference output. Additional formats and rig combinations beyond tested cases still need coverage; power-loss/forced termination recovery remains incomplete. See FEATURE_MATRIX.md. |
| Extra extension: skinned instances and mesh swaps | These are not prerequisites for five-compiler integration. Skinned `EXT_mesh_gpu_instancing` and animated mesh swaps remain unsupported. Static unskinned instances are supported. |
| Extra extension: VRM runtime behavior | These are not prerequisites for five-compiler integration. Complete spring-bone and proprietary expression-mapping runtime semantics remain unimplemented. Existing VRM import and default morph-weight regressions do not establish complete VRM compatibility. |
| Import format and interpolation coverage | Lost STEP/CUBICSPLINE semantics on the glTF fallback are fixed and tested. Other Assimp formats, complex FBX/VRM hierarchies and interpolation in other formats still need coverage. |
| Complex rig and collision coverage | IK, jiggle, drivers, correctives, eyelids, combined facial rigs and per-bone VHACD have regressions. Arbitrary complex hierarchies, hard edges, authored normals, controller remapping and complex collisions still need model-specific checks. Single-bone weighting remains experimental. |
| Cross-game and reference coverage | Specific GMod, CSGO legacy and MCV samples are tested. Other models, games and shaders need independent checks; not all reference compiler syntax edge cases, diagnostic text or performance scenarios are covered. |

v1.2.8 production validation uses Plum. Its original Hair QC and serialized output checks pass. Supplied materials load in GMod without missing entries; 28 captures cover bodygroups, skins and facial changes, and all 18 ragdoll bodies settle stably. The initial capture was retested with material warm-up. Future production validation uses Plum rather than Claudia. See the [v1.2.8 validation record](tests/reports/v1.2.8-validation.json).

Removed from the issue list: Draco/meshopt decoding, sampled scale/morph-weight baking, NvTriStrip and cross-material partitioning, large-translation animation bounds fixes, phase timings and output integrity checks. Explicit CE/Neko facial profiles pass 28 reference comparisons. `copy animation weightlist`, `match pos/rot`, conditionals and `reverse` pass seven StudioMDL++ pose/FPS cases. See [IMPROVEMENTS.md](IMPROVEMENTS.md) and the [v1.2.7 validation record](tests/reports/v1.2.7-validation.json) for coverage.

## Compatibility choices and usage requirements

These are integration requirements or intentional implementation differences, rather than unresolved bugs.

- Animation baking is capped at 4096 frames and 16 million source vertex samples. Accuracy depends on sampling; game playback requires controller integration. UTC synchronization through `gmtime` also requires mod support.
- The default `native` facial behavior retains PulseModel semantics. Use `$dmxcompatibility ce|neko` for reference facial policies. `$CEBoneRules` is opt-in.
- `$MaxVerts` controls per-material output mesh splitting, with a real ceiling of 65536. `$FileBufferSize` caps each output file's bytes. Dynamic buffers and a unified LOD vertex dictionary do not reproduce reference source pre-splitting or fixed preallocation.
- `NoAutoDMXRules` suppresses automatic rules per source; use `NoAutoDMXRulesLegacy` to clear earlier automatic controllers and rules. `addcontrollerbyflex` honors min/max rather than reproducing the reference binary's range parsing defect.
- Whole-file byte equality with the reference CE/++ outputs is not promised. Existing `copy pos/rot` is a project extension.
- PulseModel source is integrated automatically; conflicts or failing checks stop publication. CE/++ updates supplied by the user require manual analysis and implementation. VBSP, VVIS, VRAD and BSPZIP map tools are outside this project's scope.

See [COMPATIBILITY.md](COMPATIBILITY.md) for syntax and differences, and [BINARY_ANALYSIS.md](BINARY_ANALYSIS.md) for binary investigation evidence.

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

There are 181 compatibility tests using temporary SMD/QC and synthetic DMX fixtures,
and 20 automation tests. Tests inspect MDL/VVD data and decompile animations to
check positions, rotations and conditions. The user-provided Alyx QC compiled
successfully with 113 bones and 27,571 VVD vertices; this does not cover in-game
loading or rendering.

## Credits and license

Original project: Toppi. The original [MIT LICENSE](LICENSE) and third-party
notices are preserved. [UPSTREAM_README.md](UPSTREAM_README.md) keeps upstream
information, including old program names and download links, for reference.
StudioMDL-CE / Tools++ closed-source executables and recovered source are not
included in this project.
