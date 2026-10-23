# Authoring helpers

These Python 3 helpers run locally using the programs from the same package.
Use isolated output directories. The native binary interfaces remain available;
these commands provide common authoring workflows and JSON summaries.

## OBJ / GLB mesh processing

```sh
python tools/mesh_workflow.py simplify character.obj --output preview/lod.obj --ratio 0.5
python tools/mesh_workflow.py decompose collision.glb --output preview/hulls.obj --max-hulls 16
```

`--meshtool PATH` selects an explicit executable. By default the helper uses
`subtools/meshtool` (`.exe` on Windows). `--summary PATH` changes the default
`result.mesh.json` summary. `--timeout` limits each native invocation.

OBJ supports polygon faces, negative indices, UVs, normals, groups and material
names. Polygons are triangulated; invalid or degenerate n-gons are rejected.
GLB supports static triangle scenes, node transforms and instances, normals and
UV0. Bake animation, skinning and morphs before using this workflow. Sparse
accessors and external GLB buffers require prior expansion/embedding.

Simplification preserves material/group boundaries and locks mesh borders by
default. `--unlock-borders` relaxes this. The requested ratio is a target, not a
guaranteed final face count. The summary records input/output counts and the
native meshoptimizer normalized error for each group; this is not a measured
world-space Hausdorff bound. Texture files and GLB shaders are not converted.

Decomposition exports each convex hull as a named OBJ group with oriented
triangle faces. The exporter checks that the faces contain every hull point.
`--concavity` and `--resolution` control native decomposition. UVs, normals and
materials are not applicable to the generated collision hulls.

The geometry and summary publish together. Invalid input, native failure or
ordinary publication failure preserves the previous result.

## Local Source material collection

```sh
python tools/material_collect.py --root game --material characters/face --output collected
python tools/material_collect.py --root override/materials --root game --mdl models/person.mdl --output collected
```

Roots are searched in command-line order, first match wins. A root can be a
game directory containing `materials/`, or the materials directory itself.
The collector supports Source MDL versions 48 and 49 and follows the model's
texture names and `$cdmaterials` search order. Direct `--material` requests can
be repeated. The destination must be isolated from source material roots.

The collector copies VMT/VTF bytes without conversion, follows Patch `include`,
and gathers known texture-valued shader keys from all conditional branches.
Add custom shader parameters with repeated `--texture-key '$mytexture'` options.
Dynamic `_rt_*` resources and `env_cubemap` are recorded instead of copied.
Case-insensitive matching is supported; ambiguous case aliases in the same
root are rejected. The report records selected files, SHA256, root priorities,
shadowed sources, missing references and cyclic includes.

Output defaults to `collected/materials/` and
`collected/materials-manifest.json`. Missing references or include errors
produce a report and exit 2 while preserving existing material files.
`--allow-missing` copies the available subset when references are missing, still
exits 2, and does not override parse/cycle errors. Complete collection exits 0.
This validates local dependency resolution, not in-game shader rendering or
every custom shader's resource vocabulary. VPK extraction is a separate step.

## Incremental multi-model builds

Create a JSON plan. All relative paths resolve from the plan's directory;
each job has a separate, non-overlapping output directory:

```json
{
  "schema": 1,
  "jobs": [
    {
      "id": "player",
      "qc": "sources/player/model.qc",
      "game": "game",
      "output": "build/player",
      "args": ["-nodx80"],
      "watch_roots": ["sources", "game"],
      "complete_search_roots": true
    },
    {
      "id": "prop",
      "qc": "sources/prop/model.qc",
      "game": "game",
      "output": "build/prop",
      "watch_roots": ["sources", "game"],
      "complete_search_roots": true
    }
  ]
}
```

```sh
python tools/incremental_build.py models.json --compiler ./NewPageMergeMDL
```

On Windows use `NewPageMergeMDL.exe`. `--force` bypasses reuse. `--timeout`
limits each compile. The default dedicated metadata directory is
`.newpage-batch/` beside the plan; `--cache-dir` selects another.
`--report` must remain inside that directory. It defaults to
`batch-report.json` and contains built/skipped/failed counts, cache decisions,
native diagnostic codes and locations, plus bounded stdout/stderr tails.
Independent jobs continue after one fails; any failure makes the batch exit 2.
Each model publishes through the compiler's existing transaction. The complete
batch is not a single all-model transaction.

Caching is disabled unless `complete_search_roots` is explicitly true and all
actual native dependencies lie under `watch_roots`. This declaration means the
author has included every directory that may affect lookup, including game
mounts, include search directories and configuration. The helper cannot prove
arbitrary engine mount coverage. Omit the assertion when unsure: compilation
still runs, and the report explains why reuse is unavailable.

The helper verifies native dependency content hashes after compilation, then
stores SHA256 identities for later comparisons. It also tracks search-directory
entry names/types, compiler/helper identities, arguments, cwd and a digest of
the environment (not raw environment values). Add `toolchain_files` for helper
executables/libraries outside the portable package layout. Changes to actual
dependency content rebuild only its users. Adding a file to a shared search
root conservatively invalidates all jobs watching that root, so a newly added
higher-priority resource cannot silently reuse old output. Watched symlinks or
junctions disable caching because their recursive coverage is unproven.

Missing or modified output files rebuild their model. Only the wrapper-owned
output/cache/report paths are excluded from directory scanning. Source files
inside excluded paths, virtual dependencies and native uncacheable modes do
not produce a reusable cache. Do not place source assets in the cache directory.
Hashing large inputs has a cost; no universal speed-up is claimed.

## Interrupted helper publication

VRM/vertex-animation helpers and these wrappers share persistent publication
recovery. Before replacing output groups they write an adjacent journal,
fingerprints and backups. The next invocation reserving any member acquires
all group locks and restores an interrupted uncommitted group, or finishes
cleanup for a committed group. A second interruption during recovery is
recoverable. An external edit that conflicts with recorded fingerprints stops
automatic recovery and preserves the journal/backups for inspection.

Do not delete `.newpage-helper-*` files or `*.newpage-helper-journal` pointers
while recovery is needed. File contents are flushed; directories are also
flushed on supported non-Windows systems. This does not promise survival of
every filesystem, storage-device or power-loss failure.

## Compiler reports and local diagnostics

```sh
./NewPageMergeMDL model.qc -game game -OutDir build -perfjson perf.json -dependencyjson dependencies.json -diagnosticsjson
python tools/diagnostic_bundle.py --manifest upstream-manifest.json --log compile.log --compiler NewPageMergeMDL --output diagnostics.zip
```

`-perfjson` records stage timings, peak process memory and scene-cache counters.
`-dependencyjson` records observed compiler dependencies and published outputs;
the incremental wrapper adds content SHA256 and search-root coverage checks.
Keep both reports outside source files, their dependencies and model outputs.
Conflicting file aliases fail, and a failed compile keeps previous reports.

`-diagnosticsjson` preserves the readable log and adds one `@diagnostic` JSON
footer with stable category codes, severity, stage, source and exit status.
Recognized QC `file(line):` diagnostics retain the exact nested source location;
unknown locations use a null line. The batch wrapper also records bounded log
tails and built/skipped/failed totals. A category code is not a claim that every
legacy log message has a unique structured diagnostic.

The diagnostic bundle is a local ZIP containing allowlisted build identity and
only explicitly selected UTF-8 `.txt`/`.log` files up to 2 MiB each. The optional
compiler argument records its hash, not executable bytes. Common token/password
patterns and local paths are redacted. It does not collect models, textures,
settings or an environment dump, and does not upload the archive. Inspect any
selected free-form log before sharing; arbitrary application-specific secrets
cannot be identified by a finite pattern list. Matching PDB/debug archives are
separate build products when available, identified by the corresponding program
and symbol manifest, not by filename alone.
