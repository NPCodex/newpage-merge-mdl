# NewPageMergeMDL compatibility

This fork uses PulseModel commit `52cf296a953fd6c2d072e34cfde5eb8eccc95564`
as its base. It does not include StudioMDL-CE or Tools++ binaries or claim
complete behavioral parity. Implementations use public documentation and the
StudioMDL++ changelog supplied by the user on 2026-10-06, plus analysis and
isolated differential tests of the user-supplied executable; see BINARY_ANALYSIS.md.

References:
- https://github.com/ToppiOfficial/PulseModel
- https://github.com/DeadZoneLuna/StudioMDL-CE/blob/main/how-to-use-new-commands.md
- https://ficool2.github.io/HammerPlusPlus-Website/tools.html
- https://discord.com/channels/1448719578589827144/1448781234980388864
  (not read directly; the user supplied its changelog)

## Implemented and tested

| Feature | Behavior |
| --- | --- |
| `$setvariable name value` | Defines or replaces a variable; launch `-defvar` remains pinned. |
| Duplicate `$definevariable` | Warns and preserves the first definition. |
| `$IncludePrefix target prefix` | Prefixes the filename of a matching include path, preserving its directory. Matching is case insensitive; nested includes and cycle checks remain active. |
| `$IncludeAnimPrefix prefix` | Prefixes filenames of subsequent `$includemodel` paths. Empty prefix clears the setting. |
| `$PUSHDInclude 0\|1` | When enabled, searches the active `$pushd` directory first, retaining existing fallback directories. Defaults to 0. |
| `$AlwaysCollapseByPrefix prefix` | Case insensitive prefix matching uses the existing force-collapse pipeline. Rejects empty prefixes. |
| `-AlwaysCollapseByPrefix prefix` | Repeatable launch equivalent of the QC command. |
| `-MostlyOpaque` / `-mostlyopaque` | Overrides QC render-pass settings with translucent two-pass rendering. |
| `-cullanims` | Overrides `$animationcullmethod` with aggressive culling; `nocull` survives. |
| Animation `copy reference [pos] [rot]` | Self-authored weighted local-pose copy. Keeps destination length and FPS; holds the source's final frame when shorter. References must be earlier, non-declared animations. Defaults to both channels. |
| Animation `match reference [pos] [rot]` | Adds the first-frame local translation difference and/or applies the first-frame rotation correction across the clip. Default remains rotation only. |
| Animation `if / else if / else` | Self-authored compile-time braced conditions using the existing variable/comparison evaluator. Only the chosen body is parsed. Nested conditions work. |

| Sequence `gmtime` | Emits REALTIME plus the UTC extension bit (0x100100); decompiler preserves it. Requires target mod support. |
| Existing sequence order / `-noremap` | Reads existing v48/v49 local sequence names, matches case insensitively, preserves surviving sequence order and appends new names. Updates autolayer indices. Invalid old models warn and fall back to QC order. `-noremap` bypasses reading. |

PulseModel's default `$donotcollapse` priority is preserved. `$CEBoneRules` opts
into unconditional `$alwayscollapse` and protects vertex bones unless
`$AllowCollapseVertexBone` is enabled. Launch `-IncludePrefix` and
`-IncludeAnimPrefix` are supported.

## Existing PulseModel functionality (source inspection)

- Meshoptimizer, fast SMD loading, dynamic output buffers and mesh splitting.
  Performance relative to other compilers has not been benchmarked.
- `-nodx80`, animation/sequence `reverse`, optional activity weight (-1), numeric
  `$contents`, optional attachment origin, extensionless collision/LOD sources.
- Macro defaults, `$endmacro`, duplicate-macro errors, global-variable fallback.
  Defaults and fallback also pass the regression suite.
- Animation culling with `nocull`, warnings for missing weightlist bones,
  selected-render-mesh `$bbox`, unused render-material removal, no `.sw.vtx`.
- Weight threshold 0.0001; relaxed source-bone, mesh and attachment limits.
  File field widths still limit materials/animations to 32767, mesh-relative
  vertex indices to 65536 and LODs to 8. Compiler acceptance does not imply
  engine support. This is not a claim of unlimited engine compatibility.
- Bone rename, procedural, collision and blank-bodygroup paths need dedicated
  fixtures before claiming parity with the changelog's crash fixes.

## Remaining differences

| Area | Remaining work / needed specification |
| --- | --- |
| Tools++ syntax parity | The self-authored animation extensions have documented semantics and passing tests, but their syntax and output are not certified identical to StudioMDL++. |
| `gameinfo.txt` appid mounting | Search-path rules and installed-game fixtures. |
| Bone collapse rules | `$CEBoneRules` is opt-in; full skeletal/procedural/LOD parity still needs larger fixtures. |
| Bounding-box warnings / cmdlist checks | Diagnostic parity and extreme-input fixtures; dynamic vectors already avoid fixed-array overflow. |
| CE face/flex extensions | Implemented below; arbitrary corrective rigs, custom normals, eyelid setup and engine rendering are not certified identical. |
| CE legacy mesh algorithms | `$UseLegacyStripify` / `-nvtristrip` select NvTriStrip triangle-list ordering (16-entry cache, no meshoptimizer overdraw pass). `$UseLegacyClampMethod` now enables cross-material clamping on the unified LOD dictionary, with synchronized bodygroup alternatives; default output uses meshoptimizer and per-material splitting. |
| Other Tools++ tools | VBSP/VVIS/VRAD/BSPZIP are map tools, outside this model compiler port. |

## Build and validation

Windows x64 Release builds succeeded with portable LLVM-MinGW 20260922 and
CMake 4.4.4. No system-wide toolchain was installed. Original MSVC presets remain.

```powershell
cmake --preset x64-release
cmake --build --preset x64-release
python tests/compatibility.py out/build/x64-release/NewPageMergeMDL/NewPageMergeMDL.exe
```

The 112 black-box tests generate temporary SMD/QC fixtures and inspect emitted
MDL flags, bone/animation counts, include-model strings and diagnostics.
Animation tests decompile emitted models back to SMD and compare frame poses,
including channel isolation, final-frame holding and nested branch selection.
Synthetic DMX tests cover smooth normals, wrinkle switches and changed bind-pose
remapping. Engine loading, large-model stress tests and general whole-file binary
parity with closed-source compilers remain unverified. There are also 16 automation
unit tests. The user-provided Alyx QC was recompiled successfully (113 bones,
27571 VVD vertices) with outputs isolated from the game directory.

## Self-authored animation syntax

```qc
$setvariable mode 2
$animation reference "reference.smd"
$animation result "result.smd" {
    if mode == 1 {
        match reference pos rot
    } else if mode == 2 {
        copy reference pos
    } else {
        reverse
    }
}
$sequence idle result
```

Operands may be numeric, quoted strings, bare variable names or `$name$`
expansions. Supported operators are `==`, `!=`, `<`, `<=`, `>`, `>=`, `&&`
and `||`, with spaces around operators. Conditions are evaluated at compile
time, not per animation frame. Every branch condition is validated; options in
unselected bodies are not parsed. This permits platform/variant-specific
options without loading unused sources or applying unused animation commands.

`copy` samples by frame index, not seconds, and respects rotation weights and
position weights independently. `match` applies the correction only to bones
enabled by the relevant weight channel. Channel selectors follow the reference
name and can be combined. Existing bare `match reference` keeps its old behavior.

## Repeated VTA flex names

Multiple QC `flex` or `flexpair` declarations may share a name while reading
different VTA frames. Each key retains its own frame's vertex deltas; keys share
the flex descriptor (or stereo descriptor pair). Ramp endpoints follow adjacent
same-name declarations in source order, including equal and descending positions.
This behavior was checked against StudioMDL-CE 0.3.0 output and is covered by
binary-output regression tests. DMX named-morph lookup remains unchanged.


## StudioMDL-CE extensions (2026-10-06)

These independently authored changes use CE 0.3.0 binary observations and its
public command guide. CE switches are opt-in. Global boolean options below toggle
when repeated; command names are case insensitive. Their `-Name` launch forms run
before QC commands. `$PUSHDProcedural` is a QC command only.

| Commands / options | Implemented behavior |
| --- | --- |
| `$OverrideFlexControllers` | Reuses an existing controller index and replaces its type and range. |
| `$AllowDuplicationFlexControllers` | Retains distinct controller table entries with the same name. |
| `$AddInvStudioFlexes`, model-block `InvertControllers` | Adds `_Inv` morphs, negative vertex deltas and negative flex rules, including stereo descriptors. Referenced ordinary controllers use range -1..1. Complex DMX controller remaps need further parity testing. |
| `addcontrollerbyflex [type min max]` | Toggles automatic controller creation for subsequent flexes; type/range are required when enabling. Honors the documented range. |
| `$ZeroFlexDecay` | Sets VTA/DMX vertex animation speeds to 255. |
| `$DefaqScale`, `$IgnoreDMXDefaq`, flex `fscale value` | Multiplies flex position and normal deltas by 10; DMX can opt out. Per-VTA-key `fscale` overrides the global multiplier and supports negative values. |
| `$IgnoreDefaultFlexKey` | Opts out of baking a nonzero `defaultflex` into the mesh. Otherwise default deltas become the basis and other flexes are rebased. Frame 0 uses the original mesh. |
| `$EyeballScale positive`, `$IgnoreEyeballScaling`, `$IgnoreEyeballIrisScale` | Controls eye origin scale and independent iris scaling. CE eye switches preserve the authored eye radius. Without these switches existing PulseModel radius scaling remains. Eyeballs authored inside a model/bodygroup block stay scoped to that mesh. |
| `$IgnoreEyelid` | Skips automatic eyelid-to-eye binding while keeping flex descriptors, keys and manual rules. Full engine eyelid behavior remains unverified. |
| `$ComputeDeltaNormals`, `$ComputeWrinkles`, `$ComputeNormalsAndWrinkles` | Computes smooth base/morph normals and wrinkles from DMX combo wrinkle scales. Normal changes include stationary vertices. |
| Per-model `ComputeDeltaNormals`, `ComputeWrinkles`, `ComputeNormalsAndWrinkles` and `Ignore...` forms | Overrides global computation for that source. Disabling wrinkle computation preserves authored wrinkle fields. |
| `$RemapFlexToGlobal` | Re-skins DMX posed vertices/normals to compiled bind space, then subtracts the transformed base. A root bind rotation test matches CE's (0,-0.25,0) result. |
| `NoAutoDMXRulesLegacy` | Clears previous automatic rigs and controller declarations. Deltas stay loaded; unreferenced flexes can still be culled. Existing `NoAutoDMXRules` keeps PulseModel's per-source suppression semantics. CE instead suppresses previous auto rules in the observed two-model case; this difference is intentional to preserve existing scripts. |
| `BindToOneBone`, `$CollisionBindToOneBone` | Uses each vertex's first imported influence at weight 1. The collision option applies to collision source loads; the per-model option changes the private render source. |
| `RenameMat old new`, `RenameMatByPrefix prefix` | Renames materials only on the private source for that body choice. Many-to-one material merges fail explicitly to avoid overlapping mesh ranges. |
| `$body` / `$bodygroup studio` face blocks | Accepts model face/flex blocks and per-reference options; each studio entry loads a private source. |
| `$CEBoneRules`, `$AllowCollapseVertexBone` | Explicit CE/++ retention mode protects weighted bones by default; force collapse wins over keep/definebone. AllowCollapseVertexBone selects aggressive culling and permits vertex-bone collapse, retaining animation/IK/attachment/procedural dependencies. |
| `$HBoxIgnoreChild` | Omits child origins from autogenerated hitbox bounds. |
| `$PUSHDProcedural 0\|1` | Defaults to QC-directory VRD lookup; 1 enables the active source pushd directory. |
| `$OutDir path`, `-OutDir path` | Relative paths resolve against the root QC directory. Output goes under `path/models`; explicit OutDir takes precedence over -game. Without either option, the root QC directory is used. |
| `$OutputBufferSize MB`, `$MDLOutputBufferSize MB`, `$ANIOutputBufferSize MB` | Enforces the requested serialized byte limits before overwriting output files. Dynamic buffers remain unlimited by default, rather than CE's fixed 64 MB allocation. Values must represent at least 1 byte and at most 4096 MB. |

The CE binary's `addcontrollerbyflex` range parser was observed writing both min
and max into the min slot (max remains 1). This implementation honors the command
guide's min/max semantics instead of reproducing that bug. Non-stereo balance
bytes and v48/v49 model headers also differ. These differences do not constitute
whole-file equivalence. See [BINARY_ANALYSIS.md](BINARY_ANALYSIS.md).

## NekoMDL v2.3.0 compatibility

The supplied **Chinese** ChangeLog.txt is the feature checklist. The executable
is a behavioral reference, not bundled or called by this compiler.

| Entry | Implemented behavior |
| --- | --- |
| glTF / GLB / VRM | cgltf fast parser, scene transforms, skins, named morph targets, optional UVs/morph normals; missing base normals are generated. Assimp 6.0.4 imports additional supported scene formats. Existing ufbx FBX import remains. |
| `$NoFastGltf` | Uses Assimp instead of cgltf for subsequent glTF references. Parsed scene geometry is shared between private InNode loads. |
| `studio file InNode name` | Selects meshes on that scene node and descendants; a missing node is an error. Supported by body/model/bodygroup and NekoModel; available for FBX too. |
| `$FPS N`, `Pick name`, `SampleRate N` | FPS sets subsequent default animation playback and scene sampling. Pick aliases blockname. SampleRate changes import sampling, independently of playback FPS. Default clip is the first non-BindPose animation. Rates must be finite, positive and at most 1000. FBX keeps its original scene rate unless FPS/SampleRate explicitly overrides it. |
| `$UpAxis y\|z gltf`, `$UpAxis y\|z assimp` | Independent scene import axes, default Y-up. A bare UpAxis retains existing model-wide behavior. ufbx FBX retains its native coordinate conversion. |
| `$NekoModel name { ... }` | One bodygroup with private studio choices. Each studio's eyes/lids stay scoped; shared named flex/flexpair declarations apply to all choices and controllers/rules are registered once. Use separate lines for studio and face declarations. Neko eyelid syntax takes three morph/target pairs followed by right and left eye names. |
| Named `flex`, `flexpair` | Uses the source morph name. Stereo glTF/FBX morphs receive smooth balance over the default one-unit X band. Missing morph data creates an empty descriptor with a warning, matching the reference's permissive declarations. Existing SMD/VTA frame syntax remains unchanged. |
| `$NekoDriverBone driver { pose file; trigger angle frame; helpers... }` | Samples every helper from the pose animation and emits quaternion procedural triggers. Trigger/helper declarations use separate lines. |
| `$JiggleBoneRealign p y r` | Applies a local XYZ rotation in degrees to jiggle bone bind axes, compensating geometry/animations through srcRealign. |
| `$ReverseJiggleBoneRotation [pitch] [yaw]` | Reverses each selected constraint range to [-max,-min], independently of declaration order. |
| `NoBoneRealign`, `AppendScale N` | Opts one animation out of source realignment; multiplies its existing scale. |
| `$PreRenameMaterial old new` | Renames material lookup inputs for subsequent source loads, before global material registration. Existing per-model RenameMat stays private. |
| `$DiscardVertexAnimationNormals` | Zeros imported morph/VTA normal deltas, preserving base mesh normals and position deltas. |
| `$MaxVerts limit [clamp]` | Splits per-material output meshes without dropping triangles; limit/clamp must be at least 3, clamp cannot exceed limit, and effective mesh cap is at most 65536. This differs from Neko source pre-splitting. |
| `$MaxBones N`, `-maxbones N` | Changes final post-collapse budget; 1..256 because VVD bone indices are bytes. Existing default remains 255. |
| `$FileBufferSize MB` | Caps every serialized MDL/VVD/VTX/PHY/ANI file before overwriting any output. Buffers remain dynamically sized; no fixed 8 MB default. |
| `$UndefineVariable`, `$Msg`, `-Dname value` | Removes an unlocked variable, prints text, or pins a command-line variable. Pinned variables survive undefine/redefine attempts. |
| Line `$if/$ifdef/$elif/$eldef/$else/$endif` | Normalizes line blocks to the existing conditional evaluator; nesting and skipped invalid branches are supported. Existing braced syntax remains available. |
| `$Include file iffileexists`, `$QCAssert ...` | Optional include alias; a QCAssert without explicit true/false defaults to true. |
| `-checksequenceorder` | Enables existing-model ordering; already the project's default. `-noremap` selects QC order. |
| `-playbeep`, `-reloadhlmv` | Completion/error tone; Windows HLMV notification using mx_class / WM_COMMAND 1017, sent only after successful file output. |

Static node scale is baked into geometry. Animated scene scale cannot be encoded
as MDL bone TRS and fails explicitly; bake it into vertex animation first.

Unimplemented or unverified: complete historical source-clamp
algorithm parity, all scene formats/complex rigs, animated morph weights/mesh
swaps, Draco-compressed glTF, skinned instancing, and engine integration. Assimp fallback can
lose glTF STEP/CUBICSPLINE interpolation semantics. No claim of whole-file or
performance equality is made. PulseModel updates retain these maintained source
changes through the overlay; Neko reference updates are reviewed manually.

## CS:GO reference investigation

The user-specified `perilouswithadollarsign/cstrike15_src` repository contains a
historical StudioMDL implementation. This investigation inspected its
`studiomdl.cpp`, `simplify.cpp`, `optimize.cpp`, `tristrip.cpp` and `studiomdl.h`.
Historical core compiler reference files remain outside the release archives. The NvTriStrip dependency is bundled in `libs/nvtristrip`; see its `SOURCE.md` and original README for provenance.

- The historical source splits whole source models across material boundaries;
  its accounting conservatively reserves a face's vertices before deduplication.
  Current per-material output splitting is a different algorithm. This does not
  establish that CE's `$UseLegacyClampMethod` is identical to this version.
- The complete reference tree contains `utils/nvtristriplib`. The bundled portable backend now implements legacy triangle-list ordering. It removes duplicate and index-degenerate faces. Configuration is initialized once before concurrent mesh tasks use it; the default backend remains meshoptimizer.
- Cmdlist overflow guards protect fixed arrays in that source. This project's
  dynamic vectors do not need the same numeric cap; imposing it would reject
  otherwise valid scripts rather than improve safety.
- Bounds comparison exposed this project's 9999-unit accumulation sentinel.
  A regression reproduces truncated sequence bounds for a root translated
  outside the coordinate interval. The fix accumulates using full float range
  and clamps both endpoints, with positive and negative output tests. It is
  intentionally more robust than reproducing historical clipping defects.

No performance improvement is claimed from this bounds correctness fix.

## v1.2.0 safety and stress validation

SMD nodes require a valid parent defined before the child. Coordinates and weights must be finite; influences are nonnegative and limited to the loader's 16 input slots. Invalid inputs fail before output. A 256-bone model uses frame animation encoding to avoid the RLE bone-255 terminator collision. Standard MDL/VVD tables cannot encode more than 256 final bones; the writer rejects this even when a larger `$ModelBudget` is requested. 512 source bones can be collapsed to fit the output budget.

A real 172.88 MiB VTA and 130 output materials pass serialization tests. See [RESEARCH.md](RESEARCH.md) for measured partition/loading improvements, the supplied extreme model and reference-program startup limitations.

## v1.2.1 investigation results

LOD replacement chains are flattened; identity mappings are accepted, cycles and conflicting targets fail. Output tests verify bone-palette remapping over DX80/DX90 palette boundaries and LOD replacement, alongside retained IK links and procedural controls.

DMX positions, normals, texture coordinates, weights, orientation and animation values/times must be finite. A corrective rule test evaluates COMBO and DOMINATE numerically and checks the emitted flex geometry. This does not certify arbitrary production rigs or engine rendering.

Oversized RLE records and constant translations outside the half-float range switch the complete animation to frame encoding. Frame position channels use float32 when needed. Compressed IK/local-hierarchy channel offsets must fit the signed 16-bit field: oversized inputs fail before any output replacement. RLE 255-frame runs and section seams are tested by decompiling poses.

PHY string serialization no longer uses fixed 512-byte buffers for keyed strings or joint-merge names. A 600-character surface property and root-bone name survive output. Simulation behavior remains unverified. See RESEARCH.md for benchmark scope and unresolved global clamp, full rig and 512-final-bone work.

## v1.2.2 capacity, clamp and collision behavior

Body combination capacity is 2^31, with signed nonnegative body values; integer multiplication and preset handling are checked. The compiler rejects an excessive authored combination space instead of wrapping. Skin family count is capped at 8388608, but the actual table must also fit signed 32-bit offsets and configured MDL/file budgets.

`$UseLegacyClampMethod` performs conservative cross-material splitting after LOD unification. `$MaxVerts limit [clamp]` selects the trigger and chunk cap. Added bodyparts share the original base and alternatives, with blank pieces where needed; these helper groups are visible in viewers and cannot be selected independently. Vertices, flex deltas and eyeball mesh indices are remapped. Default thresholds remain project defaults; historical CE/source preprocessing and in-game parity are not certified.

`localhierarchy` references retain their unweighted bones and new parents under ordinary culling/collapse; self-parenting fails. DMX corner streams require matching lengths and valid indices before normal and flex processing. Empty optional streams retain existing fallback behavior.

`$collisionmodel file { $decomposeconcave $maxconvexpieces 4 }` opts into VHACD decomposition of closed connected meshes. It uses a 100000-voxel budget, 0.01 volume-error tolerance, depth 10 and the requested positive piece cap. It does not affect ordinary `$concave`, and rejects ragdoll use. Collision mass uses double intermediate arithmetic; nonpositive mass bias or non-finite volume fails. Geometry decomposition is approximate and game physics remains unverified.

The supplied extreme QC now fails at Shoes: 2774532096 body combinations exceed capacity. Its source files are unchanged. Isolated Hair1 geometry passes global clamping, and complete Alyx/Neko examples pass. See RESEARCH.md for tests and remaining work.

## v1.2.3 material merging and glTF extensions

Model-scoped `RenameMat` can merge several material IDs into one name. Vertex and face ranges are regrouped in ascending material order; morph indices and face tags follow the remapping. Vertices are retained rather than welded, preserving normal/UV seams. Other body choices remain private. This does not change top-level `$renamematerial` or `$renametextures` table-renaming semantics.

The fast glTF/GLB/VRM path decodes meshopt compressed buffer views using the bundled meshoptimizer v1.1 codecs. Supported modes: ATTRIBUTES, TRIANGLES, INDICES; filters: NONE, OCTAHEDRAL, QUATERNION, EXPONENTIAL, COLOR. EXPONENTIAL and both index modes have dedicated fixture comparisons; other filters use the dependency decoder but lack dedicated output fixtures. Quantization filters need not reproduce the original floats bit-for-bit. Buffer range, decoded size and stream failures are checked before output.

`EXT_mesh_gpu_instancing` expands unskinned meshes into generated child nodes sharing imported mesh data. Node/ancestor transforms compose with instance translation/rotation/scale. Morph deltas remain attached to each instance. `InNode` includes generated children. Singular scales, zero/non-finite quaternions and malformed accessor types fail explicitly. Generated names avoid collisions; the expanded scene is still subject to the source bone/node limit. Draco, animated scale/morph weights, skinned instances and game validation remain unresolved.
