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
