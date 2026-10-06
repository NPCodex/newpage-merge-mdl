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
| CE legacy mesh algorithms | `$UseLegacyStripify` (NvTriStrip) and `$UseLegacyClampMethod` are not implemented and fail explicitly. Current output uses meshoptimizer and mesh splitting. |
| Other Tools++ tools | VBSP/VVIS/VRAD/BSPZIP are map tools, outside this model compiler port. |

## Build and validation

Windows x64 Release builds succeeded with portable LLVM-MinGW 20260922 and
CMake 4.4.4. No system-wide toolchain was installed. Original MSVC presets remain.

```powershell
cmake --preset x64-release
cmake --build --preset x64-release
python tests/compatibility.py out/build/x64-release/NewPageMergeMDL/NewPageMergeMDL.exe
```

The 56 black-box tests generate temporary SMD/QC fixtures and inspect emitted
MDL flags, bone/animation counts, include-model strings and diagnostics.
Animation tests decompile emitted models back to SMD and compare frame poses,
including channel isolation, final-frame holding and nested branch selection.
Synthetic DMX tests cover smooth normals, wrinkle switches and changed bind-pose
remapping. Engine loading, large-model stress tests and general whole-file binary
parity with closed-source compilers remain unverified. There are also 12 automation
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
