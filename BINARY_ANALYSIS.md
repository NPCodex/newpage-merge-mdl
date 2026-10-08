# Current integration status (v1.2.12)

The investigations below are historical evidence. Current status is tracked in
FEATURE_MATRIX.md and COMPATIBILITY.md. AppID mounts, explicit bone retention,
NvTriStrip/global clamping and seven StudioMDL++ animation cases now have
implementations/validation; earlier unresolved lists are not current TODOs.

New Neko 2.3.0 probes confirm prefer_fbx warns that it is deprecated and
forcecapsules warns and skips. v1.2.8 accepts those directives without changing
geometry and supports the historical usenvtristrip spelling. Three Neko regressions
check unchanged serialized geometry and existing FBX/strip behavior.

CE's log advertises a replacemesh repair, but candidate one/two-argument LOD
probes fail while the corresponding replacemodel fixture succeeds. No ASCII
case-insensitive replacemesh string was found in the supplied executable. This
is unresolved evidence, not proof of a particular syntax or implementation.

The two 2012/2013 package executables have the same SHA256. Track them as one
compiler with separate game dependencies; see RESEARCH.md.

---

# StudioMDL++ compatibility investigation

The user supplied a local executable on 2026-10-06. It identifies itself as
Breadworks studiomdlplusplus (Oct 3 2026), is PE32+ x64, and has SHA256
`77791bdd9c0e09b6ae4efbadad9674d9398fc06bee74d3f6598ac2bacd128713`.
The executable is not distributed by this project. This report describes observed
behavior and independently authored implementations, not recovered original source.

## Confirmed behavior implemented

- The `gmtime` parser branch at VA `0x1400d2f49` ORs `0x100100` into sequence
  flags. Isolated compiles confirm ordinary=0, realtime=0x100 and gmtime=0x100100.
  NewPageMergeMDL emits these bits and preserves gmtime through decompilation.
  The compiler flag alone cannot implement UTC synchronization in an engine;
  the target mod must support it.
- The `-noremap` option describes disabling preservation of existing sequence
  order. Recompiling idle/walk as walk/idle preserves idle/walk by default;
  with the option it emits walk/idle. Matching is case insensitive. Removed
  sequences disappear and new sequences follow survivors in input order.
  NewPageMergeMDL reproduces this for local sequences, including autolayer
  references, and validates old-model offsets before reading them.

Tests cover emitted flags, decompile/recompile, changed sequence order, removed
and new names, v48 old headers, autolayers, and a corrupted old sequence table.
The reference executable emits v48 models; NewPageMergeMDL emits v49. Whole-file
byte equality is neither expected nor claimed.

## Still unresolved

AppID mounts, unconditional alwayscollapse and other bone-retention rules,
bounding-box diagnostic thresholds, and cmdlist diagnostics need further targeted
experiments. Existing copy/match/conditional animation extensions remain independently
specified; their full syntax/output parity has not yet been established. Performance
and engine loading are not certified by these small compiler fixtures.


## StudioMDL-CE 0.3.0 investigation

The local x64 reference executable has SHA256
`bc5cbbcb1444d539d35a36afdc7a84b7419839fd1b15674e2d0ec6ffc37e0758`.
Only this report and independently authored source/fixtures are distributed.
No executable, recovered function bodies or complete disassembly is included.

- QC dispatch entries are 32-byte records containing command and handler pointers.
  `$RemapFlexToGlobal` dispatches to VA `0x14008b2d0`, which toggles byte
  `0x1403ef836`. The consumer at `0x140058dda` inside `0x140058c60` adds
  deltas to the source base, transforms the posed vertex and subtracts the
  transformed base. A 90-degree authored root bind rotation changes (0,0,.25)
  to (0,-.25,0); the new implementation passes this differential fixture.
- Controller tests confirm first-definition retention, replacement in place
  under OverrideFlexControllers and duplicate table entries when enabled.
- Inverse flexes negate position/normal deltas and append CONST(-1), MUL to
  the matching rule. Ordinary referenced controller ranges become -1..1.
- VTA `fscale 2` doubles position and normal deltas. DefaqScale multiplies
  them by 10. ZeroFlexDecay changes per-vertex speeds to 255.
- Nonzero defaultflex becomes the VVD basis and is subtracted from subsequent
  flexes. IgnoreDefaultFlexKey keeps the original basis and the default key.
- Eye scale tests with origin (1,2,3), model scale 2 and eye scale 3 confirm
  origin (3,6,9), authored radius 1 and iris scale 2/3. IgnoreIrisScale keeps 2.
- A synthetic triangle moving its first vertex by z=.25 yields three normal
  deltas approximately (.235596,.235596,-.057190). Wrinkle scale 2 produces
  the stored value 8192. Tests include per-model computation opt-outs.
- The `addcontrollerbyflex` branch around VA `0x1400805a2` initializes min=0,
  max=1, then writes both parsed range values to the min slot at
  `0x1410809e4`. Runtime input -1,2 produces min=2,max=1. The new compiler
  intentionally honors the documented range -1,2.
- Two-model tests distinguish NoAutoDMXRules (keeps controllers, suppresses
  prior auto rules in CE) and NoAutoDMXRulesLegacy (clears controllers/rules).
  PulseModel's per-source NoAutoDMXRules behavior is retained; the explicit
  Legacy option clears earlier auto rigs and controllers.

The normal/wrinkle code, controller registration and bind-space conversion are
independently written implementations. Arbitrary DMX corrective rigs, hard edges,
custom authored normals, collision physics, large vertex sets and engine rendering
are not certified identical. Legacy NvTriStrip/global clamp algorithms remain
unimplemented and their switches fail explicitly. Compatibility details and
intentional differences are listed in COMPATIBILITY.md.

IgnoreEyelid differential tests retain the controller and `%upper` rule while
binding the eye to `dummy_eyelid` with targets (-1,0,1), instead of the authored
upper descriptor/targets. The regression fixture checks both rule preservation
and the disabled eye binding.
# NekoMDL reference notes (2026-10-06)

Source of requirements: supplied Chinese `nekomdl/ChangeLog.txt` v2.3.0 and
`example_qc/NewCommands.qci`; the English changelog was not used as authoritative.
Reference executable SHA-256:
`36b7eaad13af84a492733a09bfe56d11b1c3b7e1d8bfe0070b99188198f9aa77`.

Isolated, self-authored QC probes established:

- Jiggle local realignment 10/20/30 applied to a bone with source Euler
  0.2/0.3/0.4 radians emits 0.53632557/0.49104747/1.04254591 radians.
  This is local rotation composition, rather than Euler component addition.
- Pitch [-10,30] and yaw [-20,40] degrees become [-30,10] and [-40,20]
  under ReverseJiggleBoneRotation. Bind geometry/pose is otherwise unchanged.
- A glTF stereo morph at X=-1,1,0 writes balance bytes 0,255,127.
- The complete supplied survivor_teenangst example accepts missing named flex
  data; this implementation preserves empty descriptors with warnings too.
- Read-only disassembly around VA `0x1400a4c39..0x1400a4c99` identifies
  FindWindowExA("mx_class", model title), fallback class search, and
  PostMessageA(WM_COMMAND=0x111, wParam=0x3f9). A self-created hidden test window
  confirmed this project's notification arrives as command 1017.

The independent implementation uses official Assimp v6.0.4 and MIT cgltf pinned
to `85cd62382dfea638278962690cf515023f33ed00`; vendored sources/licenses are
included. It contains no decompiled Neko code and does not distribute or invoke
the reference executable. Assimp's poly2tri header has one portability fix:
an explicit iosfwd include. Remaining differences are listed in both READMEs
and COMPATIBILITY.md, including dynamic buffers, mesh splitting, defaults,
fallback interpolation and complex rig/engine verification.

## v1.2.9 follow-up

Nine self-authored glTF reference cases establish Neko exact-name import mapping, ignored missing names, non-chaining, unchanged QC declarations and named-key selection. The explicit neko profile now follows these rules. Checked output staging and rollback handle write/replacement failures; Windows sharing-lock and directory-collision regressions preserve existing output bytes. These checks do not establish reference crash/power-loss recovery semantics.

## v1.2.10 procedural sampling evidence

Self-authored SMD cases expose a real NekoDriverBone mismatch: animated ancestors and differing pose hierarchies require world-pose accumulation followed by conversion into the model bind-parent space. Six reference cases cover separate parents, animated parents, differing hierarchy, scale, parent renaming and multiple helpers. Frozen numeric evidence is in tests/fixtures/neko-driver-reference.json. The pose sampling source is isolated from the model bone table, including when declared before the body. Native driverbone behavior is unchanged; arbitrary rigs remain outside this bounded certification.

## v1.2.11 glTF fallback interpolation

The vendored Assimp glTF2 importer keeps cubic center values but discards tangents and STEP interpolation metadata. Self-authored output comparisons show v1.2.10 produces linear translation samples for both STEP and CUBICSPLINE. The maintained fallback now keeps Assimp geometry/skin import while sampling original glTF accessors with the existing evaluator, without a duplicate mesh allocation. Authored-value regressions cover three container types, three translation modes, quaternion STEP/cubic, unnamed nodes/clips and scale/morph baking. This improves authored glTF behavior; it is not evidence that the Neko binary preserves these modes identically.

## v1.2.12 CE LOD parser control flow

Both supplied CE binaries lack ASCII/UTF-16 replacemesh tokens. The x64 parser refers to replacemodel at 0x140084d6a and removemesh at 0x140085061. The replacemodel branch calls 0x1400844a0; its same-line optional-token comparison at 0x1400845fa references reverse at 0x14029c9e8. Independent implementation accepts that option and privately copies replacement faces before swapping winding.

Self-authored triangle compiles confirm ordinary/reverse/mixed-case behavior: ordinary LOD indices [0,2,1], reversed [0,1,2]; emitted normal directions remain positive Z. DX80/DX90 regression verifies a later normal LOD still uses original winding. This supplies a real missing option, not recovered original source or a guessed replacemesh alias. Raw disassembly and reference executables remain outside the repository.

## v1.2.14 preserved triangle lists

The supplied CSGO reference files declare the no-argument `$preservetriangleorder` switch and a triangle-list optimization bypass. Independent implementation in the maintained VTX builder skips cache/overdraw/NvTriStrip sorting and uses reference depth-first neighbor visitation without recursive stack growth. A self-authored 32-face grid compiled with the supplied CE x64 binary provides ordered coordinate expectations in tests/fixtures/triangle-order-reference.json. Both maintained VTX layouts and ordinary/repeated LODs match those coordinates. Default ordering remains unchanged. Reference source/binaries and user assets are not included in this change.
