# NewPageMergeMDL compatibility

This fork uses PulseModel commit `c8b969c4961360bf7fd1275d012b6b17dbc15a65`
as its base. It does not include StudioMDL-CE or Tools++ binaries or claim
complete behavioral parity. Implementations use public documentation and the
StudioMDL++ changelog supplied by the user on 2026-10-06.

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

PulseModel's `$donotcollapse` still wins over force-collapse, including prefix
collapse. This differs from StudioMDL++'s unconditional `$alwayscollapse` rule.
Launch equivalents of IncludePrefix and IncludeAnimPrefix are not yet implemented.

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
| Sequence `gmtime` | Exact binary flag value and target mod contract. |
| `gameinfo.txt` appid mounting | Search-path rules and installed-game fixtures. |
| `-noremap` | PulseModel currently does not read an existing output model to remap sequences; default sequence-order behavior needs comparison. |
| Bone collapse rules | An explicit compatibility mode is needed to preserve existing PulseModel scripts. |
| Bounding-box warnings / cmdlist checks | Diagnostic parity and extreme-input fixtures; dynamic vectors already avoid fixed-array overflow. |
| CE face/flex extensions | Eye scaling, inverted flexes, zero decay, controller overrides, DMX normals/wrinkles switches and per-reference material edits still need implementation and fixtures. |
| CE output options | Dynamic writers avoid fixed buffers; legacy buffer-size options and CE output-path semantics are not implemented as silent no-ops. |
| Other Tools++ tools | VBSP/VVIS/VRAD/BSPZIP are map tools, outside this model compiler port. |

## Build and validation

Windows x64 Release builds succeeded with portable LLVM-MinGW 20260922 and
CMake 4.4.4. No system-wide toolchain was installed. Original MSVC presets remain.

```powershell
cmake --preset x64-release
cmake --build --preset x64-release
python tests/compatibility.py out/build/x64-release/NewPageMergeMDL/NewPageMergeMDL.exe
```

The 23 black-box tests generate temporary SMD/QC fixtures and inspect emitted
MDL flags, bone/animation counts, include-model strings and diagnostics.
Animation tests decompile emitted models back to SMD and compare frame poses,
including channel isolation, final-frame holding and nested branch selection.
Engine loading, large models, DMX flexes and binary parity with closed-source
compilers remain unverified.

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
