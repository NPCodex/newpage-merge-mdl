# VRM expressions and spring bones

`tools/vrm_runtime.py` prepares VRM 0.x and VRM 1.0 assets for the compiler and
the explicit GMod client runtime in `integration/gmod/`. Python 3 is required
for preparation; the generated model uses ordinary Source bones and flexes.
Games do not automatically run a `.vrm.json` file.

```text
python tools/vrm_runtime.py avatar.vrm --out generated/avatar --modelname avatars/example --compiler NewPageMergeMDL.exe --game GAME_DIRECTORY
```

The tool accepts GLB/VRM and JSON glTF containing VRM metadata. It writes an
editable `avatar.gltf`, `avatar.qc`, and `models/avatars/example.vrm.json`.
Input/output aliases are rejected before writing, including an input named
`avatar.gltf` inside `--out`; choose a separate output directory. Generation,
optional compilation and runtime JSON are staged together. Ordinary publication
failures restore the previous output set, and concurrent helper writers are
rejected. This Python transaction does not guarantee forced-termination or
power-loss recovery.
`--scale` defaults to 39.3700787402 (metres to Source inches). The generated QC
cancels the compiler's default 90-degree yaw and converts glTF Y-up to Source
Z-up. Keep these transforms if using the associated physics metadata.

Each node gets a stable `vrm_node_N` bone name. The sidecar records its original
name. Each mesh instance receives independent morph names so a VRM 1 expression
targeting one node does not accidentally affect another instance. VRM 0 binds
address meshes and therefore apply to every instance of the named mesh. Source
bone/flex limits still apply. Bones needed by springs, colliders and centers are
retained explicitly. Material names become `vrm_material_N`, with original names
and base colors recorded for material authoring. Supply corresponding Source
VMT/VTF assets; this tool does not convert Unity shaders or image files to VTF.

## Expressions

VRM 0 blend-shape groups and VRM 1 preset/custom morph binds become ordinary
named Source flex controllers. The runtime supports binary weights, additive
bind weights and VRM 1 blink/look-at/mouth overrides. Existing glTF animated
morph-weight channels are removed with a warning because expression controls
own those channels; skeletal animation channels remain.

```lua
local vrm = include("newpage_vrm.lua")
local materials = include("newpage_vrm_materials.lua")
local data, err = vrm.Load(entity:GetModel())
assert(data, err)
local adapter, detachMaterials = materials.New(entity, data)
assert(adapter, detachMaterials)
local ok, message = vrm.SetExpressions(entity, data, {happy = 0.8}, adapter)
assert(ok, message)
```

Copy the supplied Lua files to your addon's `lua/` directory. The material helper
clones materials per entity and restores overrides when `detachMaterials()` is
called. It handles color/alpha, self-illumination color and UV scale/offset via
Source shader parameters. Set `options.slots[vrmMaterialIndex] = sourceSlot`
when automatic material-name matching is not appropriate; indices are zero based.
GMod's client `GetSubMaterial` reports the server's value even after a local
override ([engine issue 3362](https://github.com/Facepunch/garrysmod-issues/issues/3362)).
The helper restores that readable baseline by default. If another client script
has already overridden a slot, pass its exact value in
`options.previousOverrides[sourceSlot]` to preserve and restore it. The optional
third return value contains `materials[sourceSlot] = {name, material}` for
inspecting the cloned materials without relying on the affected getter.
Existing VMTs must enable the corresponding transparency/self-illumination
behavior. Arbitrary MToon properties and UV transforms with pre-existing rotation
or shear produce an explicit unsupported-binding error. Callers can supply their
own material adapter for a custom shader; bindings and their effective weights
remain available without pretending Source shaders are MToon.

An optional expression clip is a JSON list of keys:

```json
[{"time":0,"weights":{"happy":0}}, {"time":1,"weights":{"happy":1}}]
```

Use `--expression-clip clip.json --fps 60` to bake samples into the sidecar, then
`vrm.SampleClip(entity, data, seconds, loop, adapter)` to play them. The final
sample is at the exact duration, even if it is not an integer frame. Missing
expression weights are zero. Sampling blends scalar weights; binary and override
rules are applied at playback. This is flex playback, not baked skeletal physics.

## Spring simulation

```lua
local attached, err = vrm.Attach(entity, data)
assert(attached, err)
-- When replacing/removing the model:
attached.detach()
detachMaterials()
```

The client helper runs from `BuildBonePositions`, with stiffness, drag, gravity,
joint radii, sphere/capsule colliders, collider groups and optional moving centers.
It updates parents before children, maintains bone length, propagates the result
to descendants and handles repeated bone callbacks in one frame. VRM 0 bone roots
are expanded through their descendants; a joint's first child defines its rest
tail, with a 0.07 m virtual tail for terminal/zero-length joints.
VRM 1 uses consecutive entries in the declared `joints` chain as head/tail
pairs, including skipped scene nodes. The final entry only defines a tail and
is not simulated; a single-entry chain has no segment. The default VRM 1 drag
is 0.5. Non-descendant chains and overlaps through skipped nodes are rejected.

Physics is a bounded Verlet/projection adapter with steps no larger than 1/60 s,
two collision projection passes and a reset after gaps over 0.25 s. Dense or
contradictory collider arrangements can retain penetration. It is not guaranteed
to match another VRM runtime frame for frame. Bake nonuniform/sheared/reflected spring or
collider transforms before preparing the model; non-unit runtime entity scale is
rejected. Uniform authored scale is incorporated into local offsets and radii.
Entity transforms rotate model-space gravity into the world. World collision,
network synchronization and Unity component execution are not supplied by the
unchanged Source renderer.

For a custom scheduler, use `NewSpringState` and `StepSprings` within a valid
bone-building callback. A missing compiled bone or controller is an error, rather
than a silently ignored binding. Refer to the release validation report for the
distinction between deterministic Lua tests and actual GMod execution.
