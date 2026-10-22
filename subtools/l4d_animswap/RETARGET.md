# Retargeted animation data

```text
l4d_animswap -vanilla extracted_models -rig zoey -replace rochelle -retarget -keepintro -o generated/swap.qci
```

The vanilla directory needs selected survivors and referenced animation MDL/ANI
files. Preserve the generated QCI sequence order in the character QC.

Every retargeted blend-grid cell is now a named animation. Per-cell FPS, movement
commands and supported IK rules remain attached. The sequence retains grid
width, both pose ranges, posecycle, activity/events, autolayer references and
time/pose-driven envelopes. Pose envelopes remain in pose units. Nontrivial
bone weight masks map by target name. Conflicting pose definitions fail.

Optional `_Light.qci` has separate parameter declarations and rebuilds supplied
map-model local clips, including delta bases. Absent Light models remain
optional. Malformed grids/references, unreadable dependencies and write errors
prevent publication and preserve previous outputs.

Existing scope remains: local rotations transfer for matching bone/parent
names, translations use target proportions. Unsupported touch IK targets remain
commented with diagnostics. Delta campaign layers intentionally retaining
included-model fallback still do so. This does not establish parity for every
L4D2 rig/animation combination.

`tests/decompiler_roundtrip_test.py` exports, compiles and decompiles an authored
2×2 grid with differing cell FPS, a masked pose-driven layer and an event.
[Official Zoey-to-Rochelle validation](../../tests/reports/v1.2.38-l4d-production.md)
also rebuilt a complete 10,496-vertex character with 17 sequences, including
3×3 locomotion and 3×4 aim grids. Independent metadata and sampled pose checks
passed. Gameplay transitions, all survivor combinations and unsupported touch-IK
targets remain outside that offline acceptance.
