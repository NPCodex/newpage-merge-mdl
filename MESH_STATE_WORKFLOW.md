# Finite mesh states / 有限拓扑状态

`tools/mesh_states.py` turns a finite list of meshes into a standard Source
bodygroup. Different states may have different triangle counts, materials or a
blank mesh. The included GMod helper selects states using a timestamp. This
does not turn a skeletal animation track into changing topology: all geometry
is stored as bodygroup choices, and playback requires the helper or equivalent
code in the target game. More states increase model size. Normal model format
and game capacity limits still apply.

工具把有限个网格状态编译成普通 bodygroup，可以有不同三角形数量或空白状态。
GMod 播放器按时间调用 `SetBodygroup`；这不是骨骼轨道中的拓扑动画。
其他游戏需要同等的 bodygroup 播放逻辑，编译器不能自动增加其引擎功能。

Create a UTF-8 JSON manifest beside the source meshes:

```json
{
  "modelname": "example/changing_mesh.mdl",
  "group": "mesh_state",
  "states": [
    {"name": "triangle", "source": "triangle.smd"},
    {"name": "quad", "source": "quad.smd"},
    {"name": "hidden", "blank": true}
  ],
  "sequence": [0, 1, 2, 1],
  "fps": 2,
  "loop": true
}
```

`source` resolves relative to the manifest. At least one state needs geometry.
Each state has a unique name and exactly one of `source` or `blank: true`.
`sequence` contains zero-based state indices; its default is every state once.
Repeating indices can revisit the same stored mesh without duplicating it.

```console
python tools/mesh_states.py states.json --out generated
python tools/mesh_states.py states.json --out generated --compiler NewPageMergeMDL.exe --game path/to/garrysmod
```

The first command writes `generated/states.qc` and
`generated/models/example/changing_mesh.meshstates.json`. The second also runs
the compiler in a private output directory, then publishes its model companions,
generated QC and JSON together. Ordinary write failures restore the previous
set; concurrent helper runs for the same targets are rejected. Forced process
termination and power-loss recovery are not guaranteed by this Python helper. It does not copy material assets;
package the model's materials normally. Python 3 is required for the authoring
tool, but not for the Lua player. Do not modify/reorder the generated bodygroup
without regenerating its sidecar.

For irregular timing, replace `fps` with `times`, one time per sequence entry:

```json
"times": [0, 0.2, 0.75, 1.25],
"duration": 2
```

Times must start at zero and strictly increase. A timestamp selects the entry
at that time until the next timestamp (a step change, no interpolation).
`duration` must exceed the final timestamp. Its default is one final frame
after the last sample: `1/fps` with FPS timing, or the final time interval with
explicit times (one second for a single sample). Negative playback time clamps
to zero. At exactly `duration`, looping playback selects the first state;
non-looping playback holds the last state.

Copy `integration/gmod/newpage_meshstates.lua` into the addon's `lua/` folder.
Example client code, with an existing model entity named `ent`:

```lua
local MeshStates = include("newpage_meshstates.lua")
local clip, err = MeshStates.Load(ent:GetModel())
assert(clip, err)
local start = CurTime()
hook.Add("Think", "ExampleMeshStates", function()
    if not IsValid(ent) then hook.Remove("Think", "ExampleMeshStates") return end
    local ok, message = MeshStates.Sample(ent, clip, CurTime() - start)
    if not ok then
        ErrorNoHalt(tostring(message) .. "\n")
        hook.Remove("Think", "ExampleMeshStates")
    end
end)
```

`Load` checks schema and timing. `Sample` verifies that the entity uses the
expected model and bodygroup with the expected number of choices before
changing it. Client-side playback changes the local visual state; synchronized
multiplayer playback requires a shared start time or server-side state updates.
This workflow does not promise per-state physics, attachment or hitbox changes.
