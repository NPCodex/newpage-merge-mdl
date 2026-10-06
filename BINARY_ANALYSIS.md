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
