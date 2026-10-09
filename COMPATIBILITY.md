# NewPageMergeMDL compatibility

**Before every production compile, set `-game` to the target game/mod directory containing its correct `gameinfo.txt`.** Pass the directory, not the file, Steam root or `bin` directory. This is especially important for CSGO and MCV: AppID and mounts affect target layout, resources and defaults. Do not substitute another game's file. `-OutDir` controls output only and does not replace target selection. Keep existing assets and test isolated output in the intended game before replacing them. See the opening notes in [README.md](README.md) / [README.en.md](README.en.md) for format, material and runtime requirements.

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

Current version: **v1.2.25**. All **A1–A7 and B1–B4** packages in the [fixed CSGO scope](CSGO_PORTING_SCOPE.md) are complete. Current authoring references are the [cloth guide](CSGO_CLOTH_AUTHORING.md) and [DMX input guide](CSGO_DMX_INPUTS.md). Source-by-source status is in [FEATURE_MATRIX.md](FEATURE_MATRIX.md). Older version sections retain historical implementation and validation states; their superseded restrictions are not current TODOs. The fixed scope is closed, without an additional CSGO porting backlog.

Installation uses one complete ZIP per platform; see [INSTALL.md](INSTALL.md). Both archives include the compiler, decompiler, subtools, separate VRML converter with its corresponding source, scripts, Lua consumers, documentation, licenses, `upstream-manifest.json` and `SHA256SUMS.txt`. Reports remain in `tests/reports/`. Windows also includes the C4D helper. Automatic upstream releases embed their exact merged project source at `sources/NewPageMergeMDL-source.zip`; manual releases use the repository source at the release tag. This packaging change retains compiler version v1.2.25 and all existing format/runtime boundaries. Extract the full archive into a new directory on update. Python preparation scripts require separately installed Python 3; ordinary compilation does not.

## v1.2.25: procedural parents and shared skin tables

VRD short names and fully qualified names use the same bone lookup during parent collapse and final constraint mapping. Helper poses and driver triggers are transformed into the surviving parent's space, including successive collapses. Lookup identity prevents an unrelated namespaced bone with the same suffix from transforming the constraint. Strict QC driver names and errors for missing parents remain in effect.

For a shared `$texturegroup`, a column whose base material is absent from the model now warns and is skipped. All skin-family rows remain; used base materials retain their substitutions. CE retains unused skin-only textures in its serialized table; this compiler continues to prune them, so table sizes need not match CE. Material-merge conflicts and malformed row lengths remain errors.

## v1.2.24: compact release binaries

Release/MinSizeRel builds use function/data sections and linker garbage collection (MSVC uses /Gy, /Gw and /OPT:REF). GNU/Clang release tools omit development symbols; runtime unwind metadata and Windows resources remain present. No importer, target game, compiler option or runtime extension is removed. Debug/RelWithDebInfo builds are unchanged; `NEWPAGE_COMPACT_RELEASE=OFF` restores the previous build policy. Local size and model-output measurements are in VALIDATION.md; Windows MSVC/Linux results require their own CI verification.

## v1.2.23: five-compiler integration

The fixed R1–R6 / E1–E3 / V1–V7 / S1–S6 / O1–O5 scope and explicit H exclusions are tracked in [FIVE_COMPILER_COMPLETION.md](FIVE_COMPILER_COMPLETION.md). Older restrictions below are historical where superseded.

`$qccompatibility neko` allows bare RHS strings, makes an undefined LHS comparison false (including `!=`), and skips later `elif` evaluation after a winner. Scientific notation is not newly promoted to decimal comparison. Native strict conditions remain the default. `$boneweightpolicy ce` culls normalized imported weights below .001 and renormalizes; native/neko keep .0001. Policies capture their source context and participate in cache identity.

`$fbxcompatibility neko` selects Assimp, a default 30 Hz sample rate, and its UpAxis setting; native uses ufbx/file FPS. True FBX cluster bind matrices are independent of sampled rest/animation transforms. Assimp pre/post behaviors and authored key interpolation are consumed; Collada STEP/LINEAR/BEZIER is evaluated before Assimp can discard the curve. Unsupported tangent representations require explicit author-side baking.

Game defaults are read once from `Tools/studiomdl` and `cfg/commandline.cfg` keyed by the case-insensitive QC filename stem. Priority is gameinfo < cfg < explicit CLI; `-nodefaultargs` disables injection. Output transactions recover their durable journal before sequence remapping on the next compile. Changed files and damaged journals are retained for review; hardware failure cannot be made unconditionally lossless.

On Windows, output recovery identifies the root directory by filesystem identity before checking each relative component. Short names such as `RUNNER~1` and case aliases share recovery journals and locks; symlinks/junctions below the root still fail. Vertex-key hashes mix their high bits into low bits to avoid pathological MSVC bucket collisions on integer-grid geometry; vertex equality and first-occurrence output ordering are unchanged.

The former model-wide flex thresholds are removed: each final split mesh still obeys the uint16 index boundary. The 511451-moving-vertex case preserves all deltas/geometry; this is a file-writing validation, not a guarantee about every game's runtime budget. Early bone usage now includes lower LOD skin, explicit hitboxes and surviving animation.

Runtime extensions require their supplied consumers: [mesh states](MESH_STATE_WORKFLOW.md), [VRM](VRM_RUNTIME.md). Positive uniform skinned instance transforms expand into actual independent geometry/bones; arbitrary nonuniform/sheared skeletal instance animation requires prior baking. Extra import formats and dependency/license boundaries are documented in [O5_FORMAT_IMPORTS.md](O5_FORMAT_IMPORTS.md). `-importformats` lists actual enabled importers rather than a universal format-equivalence claim.

The complete Windows x64 package includes the separately linked C4D helper, including in automated releases. CI reuses a licensed, tested product binary with a fixed source and hash; it does not acquire the Cineware SDK. Linux accepts GLB files converted beforehand on Windows. C4D acceptance covers editable polygons, hierarchy, material names/basic diffuse colors, UVs and normals. Generated caches, skin/animation and shader baking are outside that importer. The main Windows executable embeds its UTF-8 manifest in MinGW builds as well as MSVC; VPK index keys remain raw bytes so legacy Latin-1 archive names do not break unrelated resource lookup.

## v1.2.22 historical record: fixed scope complete

The following 11 packages are implemented in actual input, compilation and output paths. “Complete” refers to their fixed scope and stated validation, rather than universal model or runtime equivalence.

| Package | Delivered behavior |
| --- | --- |
| A1 | Cloth/plane proxy documents honor their own Y/Z `upAxis`. `prerotate pitch yaw roll` rotates final FE initial positions/orientations in degrees after constraints are built; it does not rebuild local constraints. |
| A2 | `flex_borders`, mixed fixed/dynamic fitting, multiweight fixed points and configurable influence/cloud thresholds. Defaults are `flex_borders false`, `fit_influence_threshold 0.05` and `fit_min_influences 3`; 8 approximates the stock cloud threshold. With flexible borders off, a bone used by fixed points stays an animation control; enabling them permits border rotation and mixed fitting. |
| A3 | Quad ordering and crossing repair, bend tolerance and shorter-diagonal splitting for overly bent all-dynamic quads. `quad_bend_tolerance` defaults to 0.05 as a sine measure; 1 disables bend splitting while retaining ordering repair. |
| A4 | Point/Orient/Aim/Parent/Rotation/two-bone IK/Twist share dependency evaluation and bake ordinary animation, including animated targets, weights and axis-angle parameters. The graph includes final bone hierarchy dependencies; real writer conflicts and cycles fail. |
| A5 | QAngle/VMatrix logs and four corresponding Pack/Unpack operators. QAngles slerp through quaternions; matrices hold the previous key. Matrix indices follow the corrected 4×4 mapping rather than the broken reference indexing. |
| A6 | DMX flex `$variable$` expansion uses the active QC context without mutating cached documents. Command-line `-defvar` stays pinned. Unresolved expressions fail rather than dropping the rule; leading fractional literals and initial unary minus are accepted. |
| A7 | VMT `$clientShader "MouthShader"` supplies material flags/used state and VTX teeth markers, including skin families and material renaming. |
| B1 | Two-node stretch capsules, internal/external per-node spheres, explicit node planes and collision masks. Stickiness is exposed for rigid sphere/capsule and stretch-capsule records; the runtime does not consume per-node sphere/plane stickiness. |
| B2 | Explicit rods/springs, faceless bone-chain ropes, follow/FTL, local translation/rotation response, mass/multipliers, volume feedback, smoothing iterations, extra world radii and legacy stretch, mass damping, uninertial rods and OS rope offsets. |
| B3 | Nearest-surface projection onto render skinning, two-sided volume, envelopes, island filters, unskinned proxies and automatic roots. Generated dynamic bones and render weights obey final MDL bone limits and the VVD three-weight limit; two-sided bindings retain an influence from each side. |
| B4 | Color/String/Time logs, Color Pack/Unpack, negative time scales, nested clip mapping and FilmClip/track/shot skeletal inputs. Color and Time interpolate with integer truncation; String holds. Adjacent shared boundaries belong to the incoming clip; overlapping writers fail. |

`flex_borders` and `prerotate` originate in reference QC. The `advanced`, render projection and configurable fitting authoring controls are this tool's extensions, not stock QC syntax. Complete fields, defaults and examples are in [CSGO_CLOTH_AUTHORING.md](CSGO_CLOTH_AUTHORING.md) and [CSGO_DMX_INPUTS.md](CSGO_DMX_INPUTS.md); source references and scope boundaries are in [CSGO_PORTING_SCOPE.md](CSGO_PORTING_SCOPE.md).

The proxy path retains the 4096-point bound, anchored components, valid sparse adjacent bases, explicit `cloth_enable` and rejection of degenerate/non-manifold geometry. Plane proxies retain rigid single-bone binding. World collision needs colliders supplied by the game; volume feedback needs a FitMatrix. Per-node local translation inherits the global setting, including values below 1. For nonuniform node values whose maximum is exactly 1, the serialized global gate is adjusted with `nextafter(1,0)` while per-node author values remain exact. Spring stretchiness and Source2 world hull/mesh input are outside this fixed Source1 scope.

Rig/animation output is baked. Runtime IK, blending and later QC operations do not re-solve the authoring constraints; raw delta inputs, runtime-procedural dependencies and `$centerbonesonverts` combinations retain their documented restrictions. Reverse rig mode remains unsupported; it is distinct from reverse clip sampling and inverse Twist. Compressed logs remain Vector3/Quaternion-only. Film input handles skeletal data, without a full SFM session/editor, track crossfades, audio, cameras, particles or facial timeline. A standalone film must supply an unambiguous model/joint list; it does not implicitly load a game MDL skeleton.

### v1.2.22 validation

All **325 compatibility, 20 automation and 6 content-mount regressions pass**. Original Plum QC/materials remain unchanged: **126 bones, 572,277 vertices, 18 physics bodies, matching 30 kg MDL/PHY totals and 65 materials with none missing**.

Offline installed CSGO loaded and ran **10 cloth fixtures and 2 rig fixtures**. Captures show projection/mixed-boundary deformation, ropes and Rotation/IK motion changes. After `changelevel de_dust2`, the fixtures were recreated and reported **10 cloth ready and 2 rig ready**, with capture confirmation. Six game settings were restored and read back, the game exited normally with no remaining process, and 62 registered temporary files were removed after hash checks. Advanced collision currently has structural plus loading/running evidence; no quantitative collision A/B was performed. This does not prove frame-by-frame stock equivalence, zero penetration or exact in-game bone angles. See [VALIDATION.md](VALIDATION.md) for the evidence and historical comparisons.

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
| Animation `copy reference [pos] [rot]` | With an explicit named weightlist (v1.2.6), positive weights select channels, matching the tested StudioMDL++ behavior. Without it, the original weighted local-pose extension remains. Keeps destination length and FPS; holds the source's final frame when shorter. References must be earlier, non-declared animations. Defaults to both channels. |
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
- Macro defaults, `$endmacro`, legacy single/double-backslash continuations, duplicate-macro errors, global-variable fallback.
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
| `gameinfo.txt` appid mounting | Ordered search paths, Steam library/AppID resolution and VPK loading are implemented; see resources.cpp and current fixtures. |
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

The 325 compatibility tests generate temporary SMD/QC/DMX fixtures and inspect emitted
MDL flags, bone/animation counts, include-model strings and diagnostics.
Animation tests decompile emitted models back to SMD and compare frame poses,
including channel isolation, final-frame holding and nested branch selection.
Synthetic DMX tests cover smooth normals, wrinkle switches and changed bind-pose
remapping. GMod samples and large-model stress inputs have bounded validation; see IMPROVEMENTS.md. General whole-file binary parity with closed-source compilers is not claimed. There are also 20 automation
unit tests and six content-mount regressions, all passing. Current Plum validation uses unchanged original QC/materials and yields 126 bones, 572,277 vertices, 18 physics bodies, matching 30 kg MDL/PHY totals and 65 materials with none missing. Runtime evidence is summarized above and in [VALIDATION.md](VALIDATION.md). Historically, the user-provided Alyx QC was recompiled successfully (113 bones,
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
| `$DontDestroy`, `-DontDestroy` | Accepts the project's default no-cleanup-on-error policy. v1.2.23 adds durable transaction journals, per-output locks and recovery after process termination before the next compile reads old sequence order. Externally changed files/corrupt journals are preserved and reported; arbitrary hardware failure or power-loss reordering is not guaranteed lossless. |
| `$OverrideFlexControllers` | Reuses an existing controller index and replaces its type and range. |
| `$AllowDuplicationFlexControllers` | Retains distinct controller table entries with the same name. |
| `$AddInvStudioFlexes`, model-block `InvertControllers` | Adds `_Inv` morphs, negative vertex deltas and negative flex rules, including stereo descriptors. Referenced ordinary controllers use range -1..1. v1.2.23 fixed acceptance covers multi-bone/controller-remap and corrective/inverse combinations; arbitrary rigs are not claimed equivalent. |
| `addcontrollerbyflex [type min max]` | Toggles automatic controller creation for subsequent flexes; type/range are required when enabling. Honors the documented range. |
| `$ZeroFlexDecay` | Sets VTA/DMX vertex animation speeds to 255. |
| `$DefaqScale`, `$IgnoreDMXDefaq`, flex `fscale value` | Multiplies flex position and normal deltas by 10; DMX can opt out. Per-VTA-key `fscale` overrides the global multiplier and supports negative values. |
| `$IgnoreDefaultFlexKey` | Opts out of baking a nonzero `defaultflex` into the mesh. Otherwise default deltas become the basis and other flexes are rebased. Frame 0 uses the original mesh. |
| `$EyeballScale positive`, `$IgnoreEyeballScaling`, `$IgnoreEyeballIrisScale` | Controls eye origin scale and independent iris scaling. CE eye switches preserve the authored eye radius. Without these switches existing PulseModel radius scaling remains. Eyeballs authored inside a model/bodygroup block stay scoped to that mesh. |
| `$IgnoreEyelid` | Skips automatic eyelid-to-eye binding while keeping flex descriptors, keys and manual rules. Bounded GMod eyelid cases are tested; other rigs need specific checks. |
| `$ComputeDeltaNormals`, `$ComputeWrinkles`, `$ComputeNormalsAndWrinkles` | Computes smooth base/morph normals and wrinkles from DMX combo wrinkle scales. Normal changes include stationary vertices. |
| Per-model `ComputeDeltaNormals`, `ComputeWrinkles`, `ComputeNormalsAndWrinkles` and `Ignore...` forms | Overrides global computation for that source. Disabling wrinkle computation preserves authored wrinkle fields. |
| `$RemapFlexToGlobal` | Re-skins DMX posed vertices/normals to compiled bind space, then subtracts the transformed base. A root bind rotation test matches CE's (0,-0.25,0) result. |
| `NoAutoDMXRulesLegacy` | Clears previous automatic rigs and controller declarations. Deltas stay loaded; unreferenced flexes can still be culled. Existing `NoAutoDMXRules` keeps PulseModel's per-source suppression semantics. CE instead suppresses previous auto rules in the observed two-model case; this difference is intentional to preserve existing scripts. |
| `BindToOneBone`, `$CollisionBindToOneBone` | Uses each vertex's first imported influence at weight 1. The collision option applies to collision source loads; the per-model option changes the private render source. |
| `RenameMat old new`, `RenameMatByPrefix prefix` | Renames materials only on the private source for that body choice. Many-to-one merges remap geometry, morphs and face ranges; split/LOD regressions cover this path. |
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
| `$RenameMorph old new` | Native mode retains strict global renaming. With preceding `$dmxcompatibility neko`, maps exact FBX/glTF names once, ignores missing names, uses the latest definition and preserves QC declarations. Named flex blocks select keys. Ambiguous destinations fail explicitly. |
| `$prefer_fbx`, `$forcecapsules` | v1.2.8 accepts both with warnings and no arguments. FBX import is automatic; capsules are not generated. |
| `-usenvtristrip` | v1.2.8 historical alias for `-nvtristrip`, selecting NvTriStrip. |
| `$NoFastGltf` | Uses Assimp for subsequent glTF geometry/skin references. Since v1.2.11, original glTF animation accessors are sampled separately to retain LINEAR/STEP/CUBICSPLINE semantics, including quaternions and bake tracks. Parsed scene geometry is shared between private InNode loads. v1.2.23 detects GPU instances and explicitly switches to the native expansion path so instances are retained. |
| `studio file InNode name` | Selects meshes on that scene node and descendants; a missing node is an error. Supported by body/model/bodygroup and NekoModel; available for FBX too. |
| `$FPS N`, `Pick name`, `SampleRate N` | FPS sets subsequent default animation playback and scene sampling. Pick aliases blockname. SampleRate changes import sampling, independently of playback FPS. Default clip is the first non-BindPose animation. Rates must be finite, positive and at most 1000. FBX keeps its original scene rate unless FPS/SampleRate explicitly overrides it. |
| `$UpAxis y\|z gltf`, `$UpAxis y\|z assimp` | Independent scene import axes, default Y-up. A bare UpAxis retains existing model-wide behavior. ufbx FBX retains its native coordinate conversion. |
| `$NekoModel name { ... }` | One bodygroup with private studio choices. Each studio's eyes/lids stay scoped; shared named flex/flexpair declarations apply to all choices and controllers/rules are registered once. Use separate lines for studio and face declarations. Neko eyelid syntax takes three morph/target pairs followed by right and left eye names. |
| Named `flex`, `flexpair` | Uses the source morph name. Stereo glTF/FBX morphs receive smooth balance over the default one-unit X band. Missing morph data creates an empty descriptor with a warning, matching the reference's permissive declarations. Existing SMD/VTA frame syntax remains unchanged. |
| `$NekoDriverBone driver { pose file; trigger angle frame; helpers... }` | Samples driver/helper world transforms including animated ancestors, then resolves them against final model bind parents. Pose and model hierarchies may differ; pose-only sources do not define the model skeleton. Six Neko 2.3.0 reference cases and both command orders pass. Trigger/helper declarations use separate lines. |
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

Static node scale is baked into geometry. Animated scene scale is supported via opt-in sampled vertex-cache baking; see VALIDATION.md. Native MDL bone-scale tracks are not emitted.

Current v1.2.23 scope includes positive-uniform skinned instances, finite mesh-state
switching with a GMod consumer, explicit VRM preparation/runtime helpers and the
extra import paths documented above. Assimp key/boundary and Collada curve cases
extend the earlier glTF interpolation checks. Source-stage clamp ordering, arbitrary
scene/rig equivalence, complete foreign runtimes and universal performance equality
are not promised. The fixed policies and reference evidence are closed in
[FIVE_COMPILER_COMPLETION.md](FIVE_COMPILER_COMPLETION.md). PulseModel updates
retain these maintained changes through the overlay; Neko reference updates are
reviewed manually.

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

## v1.2.0 historical record safety and stress validation

SMD nodes require a valid parent defined before the child. Coordinates and weights must be finite; influences are nonnegative and limited to the loader's 16 input slots. Invalid inputs fail before output. A 256-bone model uses frame animation encoding to avoid the RLE bone-255 terminator collision. Standard MDL/VVD tables cannot encode more than 256 final bones; the writer rejects this even when a larger `$ModelBudget` is requested. 512 source bones can be collapsed to fit the output budget.

A real 172.88 MiB VTA and 130 output materials pass serialization tests. See [RESEARCH.md](RESEARCH.md) for measured partition/loading improvements, the supplied extreme model and reference-program startup limitations.

## v1.2.1 historical record investigation results

LOD replacement chains are flattened; identity mappings are accepted, cycles and conflicting targets fail. Output tests verify bone-palette remapping over DX80/DX90 palette boundaries and LOD replacement, alongside retained IK links and procedural controls.

DMX positions, normals, texture coordinates, weights, orientation and animation values/times must be finite. A corrective rule test evaluates COMBO and DOMINATE numerically and checks the emitted flex geometry. This does not certify arbitrary production rigs or engine rendering.

Oversized RLE records and constant translations outside the half-float range switch the complete animation to frame encoding. Frame position channels use float32 when needed. Compressed IK/local-hierarchy channel offsets must fit the signed 16-bit field: oversized inputs fail before any output replacement. RLE 255-frame runs and section seams are tested by decompiling poses.

PHY string serialization no longer uses fixed 512-byte buffers for keyed strings or joint-merge names. A 600-character surface property and root-bone name survive output. Simulation behavior remains unverified. See RESEARCH.md for benchmark scope and unresolved global clamp, full rig and 512-final-bone work.

## v1.2.2 historical record capacity, clamp and collision behavior

Body combination capacity is 2^31, with signed nonnegative body values; integer multiplication and preset handling are checked. Since v1.2.5, validation checks the actual stored base for each selectable group rather than rejecting solely on the final Cartesian product; presets use checked 64-bit intermediates. Skin family count is capped at 8388608, but the actual table must also fit signed 32-bit offsets and configured MDL/file budgets.

`$UseLegacyClampMethod` performs conservative cross-material splitting after LOD unification. `$MaxVerts limit [clamp]` selects the trigger and chunk cap. Added bodyparts share the original base and alternatives, with blank pieces where needed; these helper groups are visible in viewers and cannot be selected independently. Vertices, flex deltas and eyeball mesh indices are remapped. Default thresholds remain project defaults; historical CE/source preprocessing and in-game parity are not certified.

`localhierarchy` references retain their unweighted bones and new parents under ordinary culling/collapse; self-parenting fails. DMX corner streams require matching lengths and valid indices before normal and flex processing. Empty optional streams retain existing fallback behavior.

`$collisionmodel file { $decomposeconcave $maxconvexpieces 4 }` opts into VHACD decomposition of closed connected meshes. It uses a 100000-voxel budget, 0.01 volume-error tolerance, depth 10 and the requested positive piece cap. It does not affect ordinary `$concave`, and supports per-bone ragdoll decomposition via `$collisionjoints`. Collision mass uses double intermediate arithmetic; nonpositive mass bias or non-finite volume fails. Geometry decomposition is approximate and authored two-body physics and ground contact have GMod verification; arbitrary production collision rigs remain unverified.

The supplied extreme QC now fails at Shoes: 2774532096 body combinations exceed capacity. Its source files are unchanged. Isolated Hair1 geometry passes global clamping, and complete Alyx/Neko examples pass. See RESEARCH.md for tests and remaining work.

## v1.2.3 historical record material merging and glTF extensions

Model-scoped `RenameMat` can merge several material IDs into one name. Vertex and face ranges are regrouped in ascending material order; morph indices and face tags follow the remapping. Vertices are retained rather than welded, preserving normal/UV seams. Other body choices remain private. This does not change top-level `$renamematerial` or `$renametextures` table-renaming semantics.

The fast glTF/GLB/VRM path decodes meshopt compressed buffer views using the bundled meshoptimizer v1.1 codecs. Supported modes: ATTRIBUTES, TRIANGLES, INDICES; filters: NONE, OCTAHEDRAL, QUATERNION, EXPONENTIAL, COLOR. At v1.2.3, EXPONENTIAL and both index modes had dedicated fixture comparisons; v1.2.23 adds OCTAHEDRAL, QUATERNION and COLOR output fixtures. Quantization filters need not reproduce the original floats bit-for-bit. Buffer range, decoded size and stream failures are checked before output.

At v1.2.3, `EXT_mesh_gpu_instancing` expanded unskinned meshes into generated child nodes sharing imported mesh data. Node/ancestor transforms compose with instance translation/rotation/scale. Morph deltas remain attached to each instance. `InNode` includes generated children. Singular scales, zero/non-finite quaternions and malformed accessor types fail explicitly. Generated names avoid collisions; the expanded scene is still subject to the source bone/node limit. Draco and sampled scale/morph-weight baking were added subsequently. Skinned instances were absent at v1.2.3; v1.2.23 implements positive-uniform instances as documented above.

## v1.2.4 historical record resources and baking

See [VALIDATION.md](VALIDATION.md) for mounts, Draco, vertex-cache QC/playback, ragdolls, reference differentials and repeatable performance reports. VTA eyelid poses no longer create an orphan generic descriptor before their actual eyelid registration.

## v1.2.7 historical record explicit reference flex policies

`$dmxcompatibility native|ce|neko` selects flex registration behavior. Native is the default and retains controller/rule deduplication and automatic DMX rules. CE preserves per-body controllers and omits automatic combination rules; Neko preserves per-body controllers and repeated rules. Explicit QC expressions remain supported. Generated scene-baking playback rules are retained in all modes. Selecting a reference mode sets `$flexcullmethod none`; a later explicit `$flexcullmethod` can override that choice. Use this command before model declarations for clarity. It does not claim complete byte-level reference parity. Twenty-eight bounded reference comparisons cover DMX, VTA, stereo, descriptor dependencies, eyelids, IK, LOD, attachments and jiggle combinations.

Scene import merges repeated influences of the same joint before weight selection and rejects negative/non-finite glTF weights. `-perfjson` retains schema 1 and adds `stages` entries with `tag`, `name`, `ms` and `calls`; stage scopes can overlap and must not be summed as exclusive timings. Macro errors show the definition file/line and expansion call chain. Writer preflight rejects invalid geometry, bone hierarchies, bodygroup/LOD/flex indices before output files are touched.

### CE LOD replacement winding (v1.2.12)

`$lod 10 {` followed by `replacemodel mesh.smd low.smd reverse` on its own line reverses the replacement triangle winding. The option is case-insensitive; normals and cached geometry for ordinary replacements are preserved. Three CE reference compiles and DX80/DX90 regressions confirm bounded behavior. The changelog-only replacemesh command remains unconfirmed.

### User game QC regression (v1.2.13)

Legacy continuation macros end at a noncontinued line or a blank physical line; quoted backslashes remain literal. Attachment/hitbox/hitgroup references accept final rename aliases before bone retention, including chained renames. Actual source names take precedence; ambiguous aliases remain unresolved. Case-only renames update output spelling and physics names without false collision errors. Distinct-bone name collisions still fail. Supplied Insurgency 2 and Military Conflict: Vietnam models compile unmodified, with independent serialized-table checks; the game mount matches the supplied logs (Insurgency for both). No in-game validation for these two games is claimed.

### CSGO triangle-order QC (v1.2.14)

`$preservetriangleorder` disables cache, overdraw and legacy triangle-list sorting, including software-skinned strips. Hardware face gathering uses reference depth-first edge traversal in this mode; default traversal remains unchanged. Hardware bone palette changes, material/flex grouping and vertex packing still occur. This is not a guarantee of global original source-face order or automatic game/VTX format selection. A self-authored 32-triangle grid matches the supplied CE x64 ordered output, with both VTX layouts, DX80/DX90, LODs, mixed command case and legacy sorting checks. Frozen input/output expectations are in tests/fixtures/triangle-order*. The supplied Yvette QC compiles unmodified using the Insurgency game mount from its log, with serialized output validation; Plum regression also passes. No CSGO in-game certification is claimed.

### CSGO command entries (v1.2.15 historical state)

The table records v1.2.15 behavior. CONTENT/LOD limits were superseded in v1.2.18; the bounded cloth path is documented in v1.2.19 below.

| Syntax | Behavior / remaining differences |
| --- | --- |
| `$controller 0..4\|mouth bone x\|y\|z\|xr\|yr\|zr start end` | Retains the bone and writes 56-byte controllers and per-axis bone links. Rotational whole-turn ranges set RLOOP. Invalid input/axis/nonfinite bounds fail. |
| `$bonealwayssetup bone`, `$screenalign bone [sphere\|cylinder]`, `$worldalign bone` | Retain named bones and write runtime bone flags; unknown bones fail. |
| `$stripboneprefix prefix`, `$renamebonesubstr old new` | Recursive case-sensitive prefix stripping; case-insensitive substring replacement skips names already containing the replacement. Derived final aliases resolve authored rig/physics references; collisions/empty names fail. Applied with final bone renames, source cache names remain intact. |
| `$collapsebones`, `$collapsebonesaggressive` | Select native leaf-only/aggressive culling. Explicit keeper rules still apply. These modes do not claim all reference bone-collapse heuristics are identical. |
| `$insertbone child unusedInsertedName parent` | Reparents the child. The reference's actual insertion block is disabled; no intermediate bone is synthesized. |
| `$forcerealign bone separator x y z`, `$centerbonesonverts` | Post-rotate bind axes in degrees, or center origins on weighted-vertex bounds (propagating child bounds for unweighted parents). Compensate rest/animation mappings rather than moving render geometry. |
| `$bboxonlyverts`, `$clampworldspace xmin ymin zmin xmax ymax zmax` | Animated bounds exclude bone/hitbox padding, or clamp to the supplied finite ordered world window. |
| `$cliptotextures`, `$zbrush` | Clamp UVs to [0,1] and recalculate tangent bases; or accumulate tangent contributions across equal-position seams. Works per material; defaults are unchanged. |
| `$appendsource file ["offset pos[ x y z ] angle[ x y z ] scale[ f ]"]` | Merge into the first model's source with a private transformed copy. A first model must already exist. Normals/morph deltas follow rotation; negative scale reverses winding. Other bodies using the cached file stay unchanged. |
| `$appendblankbodygroup` | Append a blank choice to the last bodypart; does not create a new bodypart. |
| `$redefineattachment name bone ...` | Replace an existing defined attachment without moving its index; missing names fail. Remaining options use ordinary attachment syntax. |
| `$cd path`, `$contentrootrelative` | Change source lookup directory once, or enable fallback through gameinfo SearchPaths CONTENT directories after ordinary lookup fails. CONTENT paths use existing gameinfo/AppID expansion. CONTENT wildcard/VPK expansion is not implemented. |
| `$phyname stem`, `$internalname name` | Override the physics filename stem, or MDL internal header/full name and external ANI name/path. Main MDL filename continues to follow modelname. |
| `$modelhasnosequences` | Suppress the automatic bind-pose sequence for an otherwise sequence-less model. Explicit sequences remain. |
| `$erroronsequenceremappingfailure` | Existing-model remap failures become errors before output replacement; without it the warning fallback remains. |
| `$fakevta name { appendvta file.obj frame ... }` | Keep OBJ-derived frames in memory; require frame 0, normals and identical face/corner topology. Negative indices and polygon triangulation are supported. Import through flexfile, native VTA or VCA; no intermediate file. OBJ axes follow the reference 90-degree X rotation. |
| `$obsolete`, `$subd` | Emit obsolete/subdivision header flags. Global subd flag support does not implement the complete quad/SubD source importer. |
| `$collisionprecision grid` | Truncate framed collision coordinates onto the nonnegative grid (zero disables) before hull construction; render vertices are unchanged. |
| `$externaltextures`, `$gamma positiveValue` | Warn with legacy/no-effect semantics; neither processes textures. |
| `$skinnedLODs` | Accepted as the existing native behavior: preserve authored skin weights for each LOD. Native defaults intentionally differ from CSGO's root-nearest-weight remapping default. |
| `$cloth`, `$clothplanecollision` | Rejected at v1.2.15. The bounded real FE implementation added in v1.2.19 is described below. |

The 31 supported entries include legacy warning aliases and existing native behavior, not 31 new algorithms or full CSGO parity. Nineteen targeted cases inspect output controllers/flags, geometry, UV/tangents, hierarchy, bounding boxes, physics output changes, lookup, attachment/bodygroup indices, virtual morphs and pre-write remap errors. These are native output regressions against the inspected command contracts; they are not new CE/CSGO binary differential or in-game certification. Reference programs/source files and user model assets are excluded from this repository.

## v1.2.16 historical record: target game VTX selection

`-game` gameinfo FileSystem/SteamAppId 730 and 1012110 select extended VTX (33-byte strip groups, 35-byte strips), even when SearchPaths is absent. Unknown/missing targets retain legacy defaults. Explicit pulseqc vtx_archetype or QC $vtxformat wins over detection, and CLI -vtxformat wins over both. Explicit legacy selection for these targets warns. Full VTX does not emit DX80.

The installed CSGO/MCV loaders require the extended layout for the tested v49 models. Deploy complete matching MDL/VVD/VTX/PHY sets: model viewers may resolve sidecars through the game's model mount even when an MDL was opened using an absolute path. Use unique canonical model names and matching sidecars for isolated tests. Relative HLMV input that falls back to error.mdl is not runtime evidence. See tests/reports/v1.2.16-validation.json for bounded results.

For CSGO player tests, preserve the player/custom_player path category when giving the model a unique name. Moving this fixture into a generic model directory selected old weapon-sequence behavior; an extra stock animation include was unnecessary when the original QC was tested under its correct path.

## v1.2.18: CONTENT and root LOD skinning (historical state)

Supersedes the v1.2.15 CONTENT and `$skinnedLODs` limitations above. CONTENT paths now use the same mount/extraction pipeline as GAME: component wildcards (`*`, `?`), sorted expansion, directory archives, archive aliases and external chunks. CONTENT remains opt-in through `$contentrootrelative`, searched after GAME mounts; loose directory files precede its archives. Numeric archive chunks are not indexed as standalone directories.

CSGO SteamAppId 730 automatically transfers lower-LOD weights from the complete root model before LOD bone remapping. The immutable spatial index ranks distance, UV error, normal error, then latest source index. `$skinnedLODs` preserves authored weights; MCV, GMod and unspecified games retain existing defaults. Two-stage fuzzy vertex selection is now implemented with spatial indexing. Two self-authored UV-boundary cases match the installed stock CSGO compiler (3 versus 6 vertices). Complete binary parity is not claimed. At v1.2.18, FE cloth serialization, quad/SubD patch topology and complete bone-collapse comparison were still open.

187 compatibility cases and six isolated resource-mount cases pass. Plum and Yvette compile with unchanged original QCs and pass output structure checks. No new game runtime test was performed for this version.

CSGO/MCV targets now use a 256-byte extended header with an FE pointer slot that was zero at v1.2.18, before bodygroup presets. Other targets retain their layout. Installed stock models confirm this span. Each game's preset fixture survives 15 seconds under its HLMV/debugger without access violations; temporary game files were removed. This fixes the serialization prerequisite, not the full cloth pipeline.

## v1.2.19 historical record: physics mass, appended sources and bounded CSGO cloth

This section records v1.2.19 behavior and evidence. Its cloth-settings and SubD limitations are superseded where explicitly described in the v1.2.20 section below.

### Surface-derived collision mass

`$automass` and its `$calculatemass` alias now load `scripts/surfaceproperties_manifest.txt` through the existing resource mounts and read its `file` entries. Directory/VPK lookup, archive chunks, case-insensitive material/property names, `base` inheritance and later-definition property overrides are supported. Repeating the same file name does not load it twice. Unspecified properties retain inherited/previous values. Bone-level `$jointsurfaceprop` inheritance also reaches PHY solids.

Density is in kg/m³ and thickness is in Source inches. Positive thickness uses `surfaceArea * thickness`; zero/negative thickness uses hull volume. Both convert cubic inches to cubic meters using `0.0254³`. The reference first sums these material-derived masses, then distributes the total by each solid's `volume * massbias`, with a 1 kg minimum per solid. Consequently, the sum of clamped solid masses can exceed the authored/computed total. MDL `mass` and PHY `totalmass` now agree. Explicit `$mass` keeps the same PHY allocation behavior and does not require surface files.

```qc
$surfaceprop metal
$collisionmodel physics.smd {
    $automass
}
```

Missing manifests warn and fall back to density 2000 with solid-volume mass. Unknown surfaces use `default`, including its mounted definition when available. Missing listed files warn; invalid density/thickness values, non-finite results and inheritance cycles fail before output replacement. This corrects mass generation for all targets, not only CSGO. It does not implement the game's entire surface-property runtime.

### Appended collision sources

Within `$collisionmodel`, `$addconvexsrc file ["offset pos[ x y z ] angle[ pitch yaw roll ] scale[ f ]"] [concave]` accepts its options on the same line. Angles are degrees; the finite nonzero scale may be negative. The offset follows the reference SMD physics coordinate conversion and compensates for the active source scale before final bind-space remapping. Reusing a source does not alter render geometry or another instance.

```qc
$collisionmodel root.smd {
    $mass 20
    $concave
    $addconvexsrc piece.smd "offset pos[ 20 0 0 ] angle[ 0 45 0 ] scale[ 1 ]" concave
}
```

The enclosing `$concave` enables multiple hulls. Concave-marked extras join the root's concave source before cross-file welding; unmarked extras produce independent convex hulls. Without the global gate, the single-body fallback combines the geometry into one hull. Negative scales retain valid winding; malformed/non-finite options fail without replacing existing outputs. Six output regressions check coordinates, active scale/origin, source reuse, cross-file welding, concave gating, winding and failure preservation. `$collisionjoints` ignores these extra sources. The installed stock CSGO binary warns and ignores offset options; this implementation follows the historical CSGO source behavior for offsets, not installed-binary parity. General VPhysics hull/drag equivalence is not claimed.

### Finite-element cloth proxies

`$cloth proxy.dmx` and `$clothplanecollision planes.dmx` now build and serialize real FE nodes, triangle/quad elements, fixed offsets, weighted control-bone fits, collision planes and the CSGO extended-header resource reference. This requires a skeletal model, extended VTX and `-game` detecting SteamAppId 730. MCV, GMod, unspecified targets, static props and legacy VTX are rejected for cloth.

```qc
$body body render.smd
$cloth cloth_proxy.dmx
$clothplanecollision cloth_planes.dmx
```

The initial v1.2.19 cloth proxy was separate from render geometry. Its DMX had to contain triangle/quad faces, valid skinning and an explicit `cloth_enable` map: values at least 0.5 are simulated, lower values are fixed. The combined cloth proxy limit is 4096 points. At v1.2.19, fixed points and plane-proxy points had to bind to one bone. At that version, every simulated component had to reach a fixed anchor; unused points, degenerate faces, mixed fixed/simulated binding on one bone, or fewer than three non-collinear simulated points for a driven bone were rejected. A simulated face may have at most two fixed vertices. Proxy points remain in scaled raw bind space. Scale is captured when each `$cloth` command loads its source, so a later `$scale` does not change an earlier proxy. Model origin/rotation are applied through animation rather than baked into the proxy again, avoiding a double transform. Control names follow final bone renames.

At v1.2.19, supported optional maps were `cloth_mass`, `cloth_drag` and `cloth_gravity`. Automatic node mass comes from the proxy face area; when present, `exp(cloth_mass)` is added as a mass bias. Drag is `30 * cloth_drag`; gravity is used directly. A missing mass map adds no bias. Unknown cloth maps and settings blocks were rejected in that version; supported v1.2.20 additions are listed below.

Plane faces define bone-bound infinite one-sided planes; they are not finite triangle collision meshes. Each face must be planar and bind entirely to one bone. Each mesh in a plane DMX selects its farthest eligible front-facing plane independently for each simulated point; multiple meshes in one file can therefore contribute separate collision constraints. This describes the initial v1.2.19 FE path. v1.2.22 supports multiweight fixed points, mixed/sparse fitting, advanced faceless ropes and render projection; plane-proxy rigid binding and target limits remain. Use the cloth guide for current requirements.

### Validation scope

At v1.2.19, the local Windows suite passed 209 compatibility and 20 automation tests, including six mass, six appended-source and ten FE cases; six separate CONTENT mount regressions also pass. FE tests independently inspect resource ranges/alignment, rest shapes, fixed controls, weighted fits, per-mesh plane selection, face planarity, instruction-time scale, transforms, renamed controls, map semantics and failure preservation. Quad and triangle fixtures with planes each load in installed CSGO HLMV for 15 seconds without access violations; all six temporary game files are removed. HLMV loading does not certify cloth motion in a game simulation. Full CSGO binary/behavioral parity is not claimed.

A shared-geometry fixture compared with the installed stock CSGO compiler produces eight nodes, three static nodes and three rotation-locked nodes in both outputs. Matching by position confirms the same fixed-node state and inverse masses. The two control offsets have the same root parent and offsets; four plane constraints have the same root parent, child positions and distance 4, with normal differences around 1.2e-7. The stock fixture uses DMX model18 with `cloth_enable_in_u` to derive enable values from UV U; NewPageMergeMDL uses its explicit `cloth_enable` map. That stock-only fixture setting is not a supported NewPageMergeMDL settings block. Stock backsolving uses NodeBase plus ReverseOffset, while this implementation emits one FitMatrix with four weights for that fixture. Matching these structural values does not establish identical deformation.

A direct default-surface tetrahedron comparison using the mounted CSGO materials gives 5.462355 kg at edge 10 and 43.698837 kg at edge 20 in both the installed stock compiler and the final NewPageMergeMDL binary, equal to the six printed decimal places. Custom density/thickness cases use independent output checks rather than a claim of matching different stock mount environments. The machine-readable summary is [tests/reports/v1.2.19-validation.json](tests/reports/v1.2.19-validation.json).

## v1.2.20 historical record: FE settings, quad SubD baking and DMX evaluation

This section records v1.2.20. Its rod-map, free-anchor, Twist, curve and compression restrictions were extended in v1.2.21; current mixed fitting, prerotation, graph/value types and clip inputs are documented in v1.2.22 above and the linked authoring guides.

### FE settings and additional maps

At v1.2.20, the v1.2.19 proxy, target and skinning requirements still applied. That version added a separate `$cloth { ... }` block to emit the corresponding FE data:

```qc
$cloth {
    gravity_scale 1
    add_stiffness_rods true
    curvature 0.5
    rigid_edge_hinges false
    world_collision false
    vel_air_drag 0.1
}
$cloth cloth_proxy.dmx
$clothplanecollision cloth_planes.dmx
```

| Settings | Meaning and defaults |
| --- | --- |
| `local_position`, `local_rotation` | Local movement/rotation response; defaults 1 and 0. |
| `surface_stretch`, `thread_stretch`, `gravity_scale` | Native FE solver parameters; defaults 0, 0 and 1. Zero gravity scale is encoded as descriptor scale 1 plus zero gravity on every node, because the engine otherwise replaces a zero scale with 1. |
| `vel_air_drag`, `exp_air_drag`, `vel_quad_air_drag`, `exp_quad_air_drag`, `vel_rod_air_drag`, `exp_rod_air_drag` | Global, quad and rod air-drag parameters; default 0. |
| `rod_vel_smooth_rate`, `quad_vel_smooth_rate` | Velocity smoothing; default 0. The aliases `rod_velocity_smooth_rate` and `quad_velocity_smooth_rate` are accepted. A nonzero rate enables one solver iteration. This intentionally differs from the reference QC path's zero default iterations, which would leave the rate ineffective. |
| `windage`, `wind_drag` | Native wind response parameters; defaults 1 and 0. |
| `add_stiffness_rods`, `curvature`, `rigid_edge_hinges` | Defaults true, 0 and false. Shared triangle/quad edges generate scalar and SIMD distance rods with curvature-dependent bounds. Rigid hinges use rest-length rods and axial bending constraints; disabling rods leaves only the requested axial constraints. |
| `world_collision` | Default false. Enables native world sphere/capsule collision flags, with a collision tree and optional per-node radii. The runtime must supply sphere/capsule colliders; this setting does not author model-bound collision spheres, capsules, hulls or triangle meshes. |

Boolean values accept `true`/`false` or `1`/`0`. Numeric values must be finite and nonnegative, at most 1,000,000; local position/rotation, surface/thread stretch and curvature are restricted to [0,1]. Unknown settings fail. At v1.2.20, `flex_borders`, `prerotate` and `cloth_enable_in_u` were unsupported. v1.2.22 implements the first two; explicit `cloth_enable` remains the supported enable input.

| Additional DMX map | Output semantics |
| --- | --- |
| `cloth_animation_attract` | Per-node vertex attraction is 30 times the map value. |
| `cloth_animation_force_attract` | Per-node force attraction is 30 times the map value. Attraction-enabled virtual nodes receive offsets relative to their strongest skin influence's animated control. |
| `cloth_collision_radius` | Nonnegative per-node collision radius, scaled with the proxy at import time. |
| `cloth_ground_collision` | Values in [0,1]; the legacy world-penetration parameter is `1 - value`. Nodes below 0.999 in that parameter join the ground/world trace list. This is separate from the world shape flags and from explicit plane proxies. |
| `cloth_ground_friction` | Ground friction in [0,1]. Nodes are sorted/grouped using the reference collision-parameter grouping rule. |

Attraction and radius maps accept finite values from 0 to 1,000,000 before the documented scaling. Existing mass, damping and gravity semantics were unchanged in v1.2.20. `cloth_use_rods` and `cloth_anchor_free_rotate` were rejected then and were implemented in v1.2.21. Non-manifold edges are rejected. Rendering still uses fitted skeletal controls, so a single driven bone gives a rigid fit of its simulated point cloud rather than independent motion for each rendered vertex. Mixed anchor/dynamic fits were absent in v1.2.20 and are implemented in v1.2.22; arbitrary CSGO behavior is not implied.

A larger self-authored stock comparison uses 20 proxy points with 16 simulated influences on one bone. Both outputs contain 22 nodes, five static nodes and one full FitMatrix with 16 weights, avoiding stock's small-cloud fallback. Initial positions, inverse masses and fit center/offset match; twenty rods have identical endpoints and scalar differences no greater than 2.98e-8. Explicit zero-gravity maps produce zero dynamic node gravity in both outputs. These initialization checks do not establish identical game motion. Runtime evidence is recorded separately in [VALIDATION.md](VALIDATION.md).

### Quad SubD baking and explicit native output

Enable subdivision with `$subd`, `$model name mesh.dmx subd`, or `subdivisionSurface=true` on the DMX root. Every rendered source and replacement LOD must provide authored DMX quads. The default performs two offline Catmull-Clark iterations and writes ordinary triangle geometry with no subdivision header flag or patch strips. `$subd levels 1`, `2` or `3` selects the iteration count; legacy VTX is allowed for this baked output.

Baking uses shared control geometry and preserves UV seams through face-varying linear subdivision. Skin weights and position morphs follow the subdivision stencils; base and morphed normals are recomputed from the refined geometry. Authored normal creases remain geometric boundaries. Each source and each material mesh is limited to 262,144 refined quads (524,288 final triangles), checked before expansion. Non-quad or triangle-edited input, non-manifold topology, inconsistent winding, conflicting skin weights or position morphs at a welded point, normal-only morphs and merged-part identity data are rejected.

`$subd native` explicitly emits native patches instead; it does not accept `levels`. This mode requires extended VTX from the appropriate `-game` target or `-vtxformat 1`. The tested CSGO legacy game and HLMV crash in their native SubD rendering path for both stock and this compiler's fixtures. The compiler warns about this observed limitation; native output is only suitable for a renderer with working SubD support. The default baked path avoids that rendering path.

The native importer preserves the control mesh through LOD vertex mapping, builds half-edge neighborhoods and writes regular/extraordinary VTX patch strips with actual topology blocks. Boundary sectors, extraordinary valence, normal creases, UV seams, stable ring evaluation starts and watertight UV references are included; UV references are remapped after final VVD ordering. The decompiler exports authored quads and the subdivision marker. Recompilation defaults to baking; add `$subd native` explicitly to reproduce native patches.

Native mode rejects legacy VTX, triangle/non-quad render sources, triangle mesh edits/decimation, repeated corners, non-manifold edges or vertices, inconsistent winding, valence above 16, more than 52 ring references per patch and uint16 overflow. Each material mesh in each LOD is limited to 8,192 native patches by the CSGO SubD texture layout. Legacy limit clamping may not split a patch neighborhood; partition the authored control mesh by material if it exceeds the patch limit or configured per-mesh vertex clamp (`$MaxVerts limit [clamp]`). Supported cases include an open quad, regular interiors, a closed valence-three cube, UV seams, normal creases, reverse winding and replacement LODs.

Stock single-quad and grid comparisons match normalized valence, boundary/corner data, gaps, center offsets, ring order and UV references. Regular/extraordinary strip classification can differ because minimum-ring choices depend on vertex numbering. These structural matches do not make the tested retail native renderer usable. Neither arbitrary-mesh support nor byte-identical stock output is claimed; runtime evidence is recorded in [VALIDATION.md](VALIDATION.md).

### Baked rig constraints with multiple targets

`$datamodeljoints rig.dmx proceduralbones` reads the DMX root's `constraints` array. Full rig import without flags, and the existing full `$datamodel` import path, also include these constraints. The initial v1.2.20 classes were `DmeRigPointConstraintOperator`, `DmeRigOrientConstraintOperator`, `DmeRigAimConstraintOperator` and `DmeRigParentConstraintOperator`, serialized as CSGO procedural types 8, 9, 10 and 12. Current v1.2.22 additionally supports Rotation, two-bone IK and Twist in the unified graph; see the [DMX input guide](CSGO_DMX_INPUTS.md).

Each constraint retains multiple target bones, target weights, position/quaternion offsets and the slave's base pose. Aim additionally supports `aimOffset`, `upVector`, `upSpaceTarget` and `upType` 0 through 3: object rotation, world vector, object position and parent rotation. Referenced bones survive culling and follow final bone renames and realignment. The output requires a skeletal SteamAppId 730 target with the CSGO extended header.

The installed CSGO runtime and the inspected `CalcProceduralBone` path do not solve procedural types 8, 9, 10 and 12. Both stock and this compiler's initial record-only test models left their slaves unmoving. The compiler therefore evaluates these constraints per frame after animation remapping and before QC animation commands, writes the resulting local skeletal poses and leaves `BONE_ALWAYS_PROCEDURAL` clear on these slaves. The records remain rig metadata. Target position averages, exponential quaternion averages and blending toward the slave's base pose when total target weight is below one are evaluated; dependencies include parent, target and up-space bones.

This is offline animation baking. Runtime pose blending, IK, attachments and later QC edits do not re-evaluate the constraint. Raw delta animation inputs, dependencies on runtime procedural bones and `$centerbonesonverts` combinations are rejected; subtracting already baked absolute clips through subsequent QC commands remains an ordinary animation operation. Other targets, reverse rig mode, missing bones, negative/non-finite weights, dependency cycles, conflicting definitions and degenerate aim directions fail. Twist was rejected at v1.2.20; it is now baked, with Rotation and IK, through the current graph. Four self-authored two-target identity cases match stock's serialized payload fields, but that metadata match does not establish a working stock runtime solver. Dynamic pose tests check the separately baked results.

### Offline DMX animation operator evaluation (initial v1.2.20 scope)

The paragraphs below preserve the initial evaluator. For the current seven constraint classes, additional log/Pack/Unpack types, curves/compression and reverse/nested film clips, use the [v1.2.22 DMX input guide](CSGO_DMX_INPUTS.md).

Ordinary `$sequence name anim.dmx` evaluates each `DmeChannelsClip` and bakes its result to regular skeletal animation. This path supports all game targets and is independent of the CSGO runtime constraint records above.

Supported nodes are multi-hop `DmeConnectionOperator` (including array indices), `DmeExpressionOperator`, `DmeTransformOperator`, and Pack/Unpack operators for Vector2, Vector3, Vector4 and Quaternion. Dependencies can be discovered through AnimationSet operator connections; only the active clip's writers are used. Expressions support arithmetic, comparisons, Boolean operators, ternary expressions, and `abs`, `sqr`, `sqrt`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `floor`, `ceil`, `round`, `exp`, `log`, `min`, `max`, `pow`, `atan2`, `clamp`, `inrange`, `lerp`, `elerp` and `rescale`.

Layered logs choose the topmost layer covering the sample time, falling back to layer 0 when no layer covers it; playback clamps to the union of layer time ranges. Empty logs can pass through their input or use `usedefaultvalue`. Float/vector values interpolate linearly, quaternion values use slerp, and integer/Boolean values or `noninterpolatedsegments` use step sampling. At v1.2.20, clip offset and positive time scale were applied; frame rate is limited to 10,000 and each clip to 100,000 frames. At v1.2.20, unsupported connected operators, curve-type interpolation, compressed logs, invalid keys/types, dependency cycles and conflicting writers failed instead of producing a partially evaluated pose. Later versions added the documented curves, compressed Vector3/Quaternion logs and negative/nested time mapping; unsupported inputs still fail explicitly. This is a documented subset, not a complete SFM operator or curve evaluator.

The original Plum Hair QC remains unchanged and compiles in isolation: 126 bones, 572,277 vertices, 18 bodies. MDL/PHY totals both equal the authored 30 kg. Its PHY payload matches v1.2.18 after the checksum-bearing header. See [VALIDATION.md](VALIDATION.md) for reproduction and historical evidence boundaries.


## v1.2.21 historical record: rigid cloth colliders, sparse binding and corrective animation

This section records v1.2.21 implementation and evidence. v1.2.22 adds mixed fitting, final prerotation, configurable fit thresholds, advanced FE/projection and the expanded DMX graph/timeline described above.

### Bone-bound cloth spheres and capsules

```qc
$cloth {
    sphere "pelvis" 0 0 0 12
    capsule "thigh" 0 0 0 8 0 0 28 6
}
$cloth "proxy.dmx"
```

Each sphere takes a bone, local XYZ center and positive radius. Each capsule takes a bone and two XYZ/radius endpoints. Values use the `$scale` active at the directive, once; later scale changes do not rescale existing colliders. Bone renames, retention and final bone-axis changes are applied. These are model-owned rigid collider arrays and work independently of the `world_collision` switch. They do not generate VPhysics collision bodies. Only the existing CSGO AppID 730 skeletal/extended-VTX cloth path is supported.

At most 1024 rigid colliders are allowed. Each center length and radius must be at most 1,000,000 final model units. Missing bones, runtime-procedural collider bones, simulated cloth bones, non-finite values and non-positive radii fail. Capsule centers must be farther apart than the absolute radius difference; use a sphere for contained endpoints. The engine approximates a nearly contained capsule as its larger sphere when the remaining separation is at most 0.5 scaled units. Collision precedes constraint solving, so this does not guarantee that every render vertex stays strictly outside every collider on every frame.

### Sparse controls, free anchors and rod faces

Existing non-collinear controls with at least three influenced points retain FitMatrix backsolving. A control with one or two points, or a collinear influence cloud, uses a NodeBase from the union of vertices in the strongest point's adjacent proxy faces and a ReverseOffset to that point. Ties use input order. The surrounding points must provide a non-collinear basis whose projected axis exceeds the runtime's 0.05-unit threshold. This is a bounded sparse binding choice, not identical to the stock builder's influence-count threshold or general weighted sparse fitting.

Both new maps require finite values in [0,1]. `cloth_anchor_free_rotate` values above 0.5 enable rotation reconstruction for fixed proxy points and reorder them after rotation-locked statics. This does not make the animated parent bone itself cloth-driven. `cloth_use_rods` above 0.5 on any corner replaces that triangle/quad by its complete set of pairwise distance rods (3/6 pairs before static/static omission and shared-pair deduplication). The reference authoring code reads this map but leaves conversion empty; this face-replacement rule is an intentional implementation choice. Stiffness rods do not replace these exact structural lengths. At v1.2.21, `flex_borders`, `prerotate` and unknown cloth maps failed. v1.2.22 implements `flex_borders` and `prerotate`; maps outside the documented set still fail.

### AxisInterp and Twist

`$proceduralbones "corrective.axis"` accepts the legacy non-`.vrd` format below. Axis selection is 1–3; pose indices are 0–5 for +X, -X, +Y, -Y, +Z, -Z. Positions are relative to `basepos`; rotations are degrees. All six poses are required. Existing `.vrd` QuatInterp/Aim behavior is retained.

```text
version 1
proceduralbones
bone "helper" "parent" "control" "controlParent" 1
basepos 0 0 0
axis 0 0 0 0 0 0 0
axis 1 0 0 0 0 0 0
axis 2 0 0 0 0 0 0
axis 3 0 0 0 0 0 0
axis 4 0 0 0 0 0 0
axis 5 0 0 0 0 0 0
end
```

AxisInterp writes type 1 and `BONE_ALWAYS_PROCEDURAL`. It retains and renames dependencies and remaps representable cardinal control-axis changes. The helper must have a parent; the control must precede it in final bone order. Changed authored parents, nonrepresentable control axes or control-parent rotations, conflicting procedures and `$centerbonesonverts` fail explicitly.

Decompilation exports a separate `_axis.bones` file and references it from QC, PulseQC and datamodeljoints output. The legacy `type compiled` decoration tells this importer to preserve the already compiled root-control slot basis; stock ignores that decoration. Invalid/truncated records fail before replacing prior decompiler output. Changed per-animation bone bases that cannot share one native record are rejected.

`$datamodeljoints "rig.dmx" proceduralbones` additionally imports `DmeRigTwistConstraintOperator`: two parent/child targets, `twistJoints` with weight and bind orientation, inverse mode, up vector and parent/child bind rotation. Twist follows the reference rotation solver and is baked into ordinary source animation frames before later QC animation processing. The reference writer is disabled and the runtime switch defaults off, so Twist does not emit active master/slave records or require that switch. Runtime blending, IK and later QC edits do not re-solve it. Reverse rig mode, raw delta source clips, runtime-procedural dependencies, missing bones, cycles and ownership conflicts fail; inverse Twist is distinct from unsupported reverse rig mode.

### DMX curve and compression rules

Curve evaluation is enabled by the log's `curveinfo` element; `curvetypes` without it is inert as in the reference. Curve integers pack inbound mode in bits 8–15 and outbound mode in bits 0–7. Per-key zero uses `defaultCurveType`; outgoing HOLD wins over incoming HOLD, otherwise differing sides blend their results. Float modes 0–15 include Catmull-Rom variants, easing, B-spline, linear, Kochanek-Bartels, simple cubic, tangent, exponential decay and HOLD. Vector3/Quaternion accept 0–13 and HOLD; mode 14 fails for those types because the reference does not define a useful complete-vector/quaternion result. Quaternion spline modes follow the reference SLERP behavior. Float curve values use `minvalue`/`maxvalue` (defaults 0/1), with the reference terminal-key exception. Edge metadata and uneven key timing are interpreted according to the supported reference path.

Vector3/Quaternion compressed logs use a 32-byte scale/base/component-offset header and three signed-16-bit RLE streams. Quaternion components decode to radian Euler angles, then convert to quaternions. Stream offsets, exact key coverage, runs, types, finite values and trailing data are checked; mixed compressed and explicit values fail. These are input-log decoders, not an additional MDL output codec. Other compressed types remain unsupported in v1.2.22. The original v1.2.21 curve/value and clip scope has since expanded as specified in the DMX guide; full curve evaluation still belongs to the documented Float/Vector3/Quaternion paths. Layer selection, bounded sampling and explicit unsupported-operator errors remain.

Independent stock comparisons match both five-frame compressed logs exactly after MDL decompilation. Four common Vector3 curve fixtures match exactly, and five Quaternion fixtures differ by at most 1e-6 radians. A NormalizeX curve with the reference's one-tick terminal edge has large overshoot and differs by up to one final MDL position quantization step (0.030762 in that fixture). Float-second timing follows the reference; extremely close times that collapse in that representation fail explicitly.

Separate in-game checks in CSGO 1.38.8.1 / 8802 on offline `de_dust2` showed seven cloth21 fixtures loading, deforming multiple bones and moving with their entities. The original sphere/capsule fixtures had low visible shells; four additional zero-gravity `contact_on/off` fixtures with identical visible shells showed distinct collision responses. Native NP/stock AxisInterp matched visually at synchronized nominal phases of 0.5/1 seconds. Forward/inverse Twist played in both directions as ordinary baked animation. All seven cloth, four contact and four procedural fixtures loaded again after a map reload. No compiler change was needed for these observations. They do not establish contact on every frame, zero penetration at every point, exact in-game bone angles or complete stock parity.
