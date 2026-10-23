# CS2 AnimGraph2 proportions

This experimental tool generates translation-only additive proportions over the
installed CS2 graphs. It needs CS2 Workshop Tools, and the model must be inside
`content/csgo_addons/<addon>/`. It does not reskin a mesh or correct bind axes.

```text
ag2proportions character.vmdl --debug
ag2proportions body-job.kv3 --debug
```

A VMDL argument edits the model. A job gives explicit control:

```text
{
    vmdl = "models/character.vmdl"
    model_dmx = "models/character_body.dmx"
    write_model = true
}
```

Job paths are relative to the job. `model_dmx` defaults to the best body mesh
candidate; ambiguous candidates require an explicit choice. `proportions` may
name a single held-pose DMX. `vnmskel` may name a compiled skeleton exactly
matching the installed selected skeleton. The regular mode generates world/UI
wrappers, reconciles stock hierarchy, and keeps authored helper Bone nodes.

## First-person arms

```text
{
    vmdl = "models/character.vmdl"
    model_dmx = "models/character_arms.dmx"
    first_person = true
    write_model = true
}
```

This mode requires explicit arms DMX with both `arm_upper`, `arm_lower` and
`hand` chains (`_L`/`_R`). Full body bones are optional. It references the installed
viewmodel graph and writes a separate `<model>_viewmodel` directory. With
`write_model`, the model must already have an enabled `AnimGraph2` named
`hudmodel`; only that graph filename changes. Existing world/UI graphs and
model skeleton remain in place. Run body and first-person jobs separately when
both need proportion adjustments.

The view graph has shoulder/straighten helpers and a reversed upper-arm branch.
The generated pose uses the original arms rig's upper-arm length for both
branches in the stock axes. Authoring-root placement does not become a shoulder
offset. Other supported bone translations retain the source rig's local axes;
incompatible bind axes still need author correction. Shoulder graph placement,
weapon graph helpers and attachment tuning are not automatic mesh fitting.

## Publication and validation

The first input backup is `<model>.vmdl.bak`. Source files, compiled resources and
model edits are published together after successful validation. Failure rolls
back, and interrupted transactions recover on the next run. Jobs sharing the
same target are locked.

`--generate-only` writes sources and removes stale generated compiled files for
that output folder in the same transaction. Compile again before using them.
`--compiler-runner wine` can run the installed Windows ResourceCompiler on
Linux. `--debug` includes diagnostic skeleton, report and setup notes.

Resource compilation and static track checks are only part of validation. Check
the final mesh model in an isolated local game: body and arms, pistol/rifle/knife,
reload, recoil/inspect, crouch, attachments and death ragdoll. Do not replace a
working character solely because the resource compiler accepted the graph.
