# Decompiler export workflows

Default full-project export:

```text
NewPageMergeMDL-Decompiler model.mdl -outdir exported -qualityreport
```

`-qualityreport` saves `export-report.json` and prints one `@quality {...}` JSON
record per attempted model (schema 1): success/exit code, warnings, renamed bones,
recovered bind/IK information, unsupported reconstruction details, missing
sidecars and files actually written. Original unsafe names use
`original_bytes_hex` so invalid bytes cannot corrupt JSON. Export success still
requires model and game validation; it does not prove visual parity.

A failed model prints a failed record with an empty `written_files` list and
keeps previous output, including the previous successful report. Other models
continue. Command-line/batch-preflight errors can stop before any per-model
record. Explicit `-nomesh`/`-noanimation` skips are warnings; their QC still needs
external assets. Missing required VVD/VTX/ANI or invalid active vertex weights
fails extraction. Detailed quality metadata covers Source 44–49; GoldSrc reports
its metadata limitation explicitly.

## Select assets

```text
NewPageMergeMDL-Decompiler model.mdl -sequence walk -sequence idle -outdir exported
NewPageMergeMDL-Decompiler model.mdl -animation a_walk -outdir exported
NewPageMergeMDL-Decompiler model.mdl -bodygroup 0 -lod 1 -outdir exported
```

Selectors are repeatable; bodygroup/LOD indices are zero-based. Animation names
are the unique full-export names. Sequence names match stored labels without
case sensitivity. Selecting a sequence includes its blend cells, recursively
referenced local autolayers and required delta subtract/bind bases.

Selectors produce a separate `<model>_assets` folder, enable the report, and
write no QC. This is an asset collection, not an independently recompilable
project. Animation selectors export clips; mesh selectors export meshes; combine
both for both. A bodygroup exports all its nonblank models. An LOD filter applies
to selected bodygroups (all if no bodygroup was specified).

Included-model declarations remain external and are reported as unsupported
local reconstruction. Invalid selections fail before publication. Selectors
require Source models and cannot combine with `-nomesh`/`-noanimation`. Existing
user files and older unrelated exports are retained; `written_files` lists only
this run's outputs.

## Preserve explicit input paths

```text
NewPageMergeMDL-Decompiler library/a/model.mdl library/b/model.mdl -preservepaths library -outdir exported
```

This keeps `a/` and `b/` under the versioned wrapper. Inputs must resolve beneath
the supplied root. Folder inputs already retain their relative subtree. Entire
batches are checked for colliding or overlapping output folders.

## Optional DMX bone key reduction

```text
NewPageMergeMDL-Decompiler model.mdl -reducepos 0.01 -reduceangle 0.05 -outdir exported
```

Position tolerance uses source model units; angular tolerance uses degrees.
Zero disables approximate reduction for that channel (both default to zero).
Exact constant-track compression remains the default. Flex tracks and SMD are
not reduced. Reduction checks each source key and quarter of each source
interval on the stored DMX tick timeline. Independent tests compare eighth
intervals. These interpolation checks do not bound game constraints or deformed
mesh surface error. Values remain original samples; only redundant keys are
removed. First/last keys, event neighborhoods, time-driven layer ramps, IK phases
and movement boundaries remain. Clip duration, FPS and QC event metadata remain.

Validation lives in `tests/decompiler_roundtrip_test.py`, including malformed
vertex preservation, report success/failure, selector closure/path isolation,
L4D 2×2-grid roundtrip and independent reduced-key interpolation checks.
