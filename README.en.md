# NewPageMergeMDL

<p>
<img src=".github/images/newpage-compiler.png" width="80" alt="NewPage compiler">
<img src=".github/images/newpage-decompiler.png" width="80" alt="NewPage decompiler">
</p>

English | [简体中文](README.md)

A Source model toolchain based on [PulseModel](https://github.com/ToppiOfficial/PulseModel),
combining independently implemented features from StudioMDL-CE, NekoMDL,
StudioMDL 2013 and StudioMDL++. It includes a compiler, decompiler and four subtools.
See the [feature matrix](FEATURE_MATRIX.md) for supported features and boundaries.

## Download and install

Download a complete archive from [GitHub Releases](https://github.com/NPCodex/newpage-merge-mdl/releases).
**Available platforms, validation status and release notes are listed in Releases.**
GitHub's automatic **Source code** downloads are not installation packages.

Extract the entire archive into a new directory, preserving its layout. Keep the
compiler, decompiler, helpers, scripts and licenses together; do not mix versions.
The Windows package also includes the C4D helper; Linux uses GLB converted on
Windows first. See [installation](INSTALL.md) for package contents and requirements.

Ordinary compilation does not require Python. The preparation scripts under
`tools/` require Python 3; VRM and mesh-state playback require the documented
GMod Lua consumers.

Supported workflows include SMD/DMX/FBX/glTF/GLB/VRM and Assimp scene import,
skeletal animation, flexes, LODs, materials/skins and collision. CSGO cloth,
offline SubD and DMX rig baking have specific authoring requirements. Run
`NewPageMergeMDL.exe -importformats` for the formats enabled in your build.

<a id="before-compiling"></a>

## Read before compiling

- **Always pass `-game` with the target game's directory containing its correct
  `gameinfo.txt`.** Pass the directory, not that file, the Steam root or `bin`.
  AppID and search paths select target behavior and resources. CSGO legacy and
  Military Conflict: Vietnam require their own game configuration.
- `-OutDir` changes the output location, not the target game. Start with isolated
  output and preserve original inputs; `$modelname` determines the model path.
  Deploy matching MDL/VVD/VTX/PHY/ANI files
  together; stale companion files can prevent loading.
- Supply the target game's Source VMT/VTF materials and required mounted resources.
  Importing a mesh does not convert its original shaders and textures.
- Format and engine limits still apply: the default final bone budget is 255
  (up to 256), with three final weights per vertex and bounded local mesh indices.
  FE cloth targets CSGO skeletal models with extended VTX. Use default offline
  SubD baking; native SubD patches crash the tested CSGO legacy renderer.
- CE/Neko behavior uses explicit compatibility options. Launch argument priority
  is gameinfo, `cfg/commandline.cfg`, then explicit CLI; `-nodefaultargs` disables
  configuration defaults. See [compatibility](COMPATIBILITY.md).
- Preserve `.npmdl-*` recovery journals, staging files and backups after an
  interrupted compile. The next compile attempts recovery; investigate reported
  conflicts before changing recovery files. Do not target one output set from
  multiple compiler processes.
- The decompiler, AG2 and VMD/L4D use persistent recovery and reject concurrent
  runs for the same target. Preserve the journals, staging files and backups
  identified by diagnostics, then rerun the same job. Investigate external-edit
  conflicts first; tool-specific file locations are in [installation](INSTALL.md).

## Compile and decompile

Run these PowerShell examples from the extracted package root, replacing the
input/game paths and preparing the output directories:

```powershell
.\NewPageMergeMDL.exe "D:/work/model.qc" -game "D:/Games/MyMod" -OutDir "D:/build/model"
.\NewPageMergeMDL-Decompiler.exe "D:/models/model.mdl" -outdir "D:/build/decompiled"
```

The compiler accepts `.qc` and `.pulseqc`. The decompiler accepts model files or
folders, writing per-model folders beneath a `decompiled <version>` wrapper.
Keep the input model's required VVD/VTX/ANI companions available. Add
`-smdanimation` to export animation clips as SMD instead of DMX. `-nomesh` and
`-noanimation` deliberately skip those parts.

On Linux, use `./NewPageMergeMDL`, `./NewPageMergeMDL-Decompiler` and Linux paths.
Restore executable permissions if the archive extractor did not preserve them.

## Subtools

The following commands also run from the package root. Prepare inputs and output
folders first. On Linux, omit `.exe` and use `./subtools/<tool>`.

### vmd2valvebiped — MMD animation conversion

Converts VMD motion to DMX. The default target is ValveBiped with left/right leg
IK chains; `-mapping` supplies explicit custom humanoid bone roles.

```powershell
.\subtools\vmd2valvebiped.exe -vmd "D:/motions/dance.vmd" -mdl "D:/models/character.mdl" -o "D:/build/dance.dmx"
```

Use `-pmx "D:/models/original.pmx"` to supply the original MMD rest skeleton.
Reference the generated DMX in your QC and compile it. `-dmxmodel 22` enables
supported facial tracks. Repeat `-vmd` for batch conversion without `-o`; outputs
then go beside each VMD. Per-frame leg IK switches select IK/FK; orthographic
cameras and non-finite inputs fail explicitly. Camera keys produce `_camera.smd`; `-camerafov dmx` also
adds camera/FOV DMX. Run without arguments for the full options.

Add `-compile "my_animation" -game "D:/Games/MyMod"` to invoke the packaged
`NewPageMergeMDL` directly. Keep `-game` pointed at the actual target game.
Converted sources and compiled assets are published together after success;
ordinary failures preserve the previous output set.

Use `-mode camera` without an MDL for camera-only input, or `-mode face` for
facial tracks only. See the [VMD guide](subtools/vmd2valvebiped/README.md) for
time ranges, mapping profiles and optional DMX key reduction.

### l4d_animswap — L4D2 survivor animation setup

Generates a QCI that maps a survivor rig to another survivor's animation setup.
The extracted input folder must contain the required `survivor*.mdl` files and
their referenced animation/gesture MDLs.

```powershell
.\subtools\l4d_animswap.exe -vanilla "D:/L4D2/extracted-survivors" -rig zoey -replace rochelle -o "D:/build/zoey_to_rochelle.qci"
```

`-rig` names your model's skeleton; `-replace` names the survivor being replaced.
Add the QCI to your QC with `$include`. The default `-skip 2` reserves the first
two sequence slots for your model. Follow the generated comments, replace
`REPLACE ME` entries, or use `-ref` / `-usenoanimation` where appropriate.

`-retarget` also exports supported scene animations to a neighboring `anims/`
folder; externally stored animations require the corresponding `.ani` files
beside the input MDLs. `-all -outdir "D:/build/survivor-qci"` generates a batch.
Run without arguments for options and survivor names.

Supported blend grids and pose layers are retained by `-retarget`; see the
[retargeting contract](subtools/l4d_animswap/RETARGET.md) for limits.

### meshtool — binary mesh-processing interface

A helper for callers that encode its binary request format. It does **not** read
MDL, OBJ or FBX files directly.

```powershell
.\subtools\meshtool.exe simplify "D:/work/request.bin" "D:/build/response.bin"
.\subtools\meshtool.exe decompose "D:/work/request.bin" "D:/build/response.bin"
```

The commands use different request/response layouts: see
[simplification](subtools/meshtool/mesh_simplify.cpp) and
[convex decomposition](subtools/meshtool/convex_decompose.cpp) before constructing
requests. Simplification returns indices/error; decomposition returns point
clouds from which the caller constructs convex hulls. Success returns exit code
0; invalid requests and processing failures return a nonzero exit code.

For OBJ/GLB input use `python tools/mesh_workflow.py simplify input.obj --output
lod.obj --ratio 0.5`. See [authoring workflows](AUTHORING_WORKFLOWS.md) for geometry
exports, error summaries, material collection and incremental batch builds.

### ag2proportions — experimental CS2 AnimGraph2 proportions

Generates proportion clips and worldmodel/UI graphs from your model's skeleton
DMX. Requires installed CS2 data and, for compilation, compatible CS2 Workshop
Tools. Copy your VMDL project into a separate addon under
`content/csgo_addons/`, retaining relative DMX references. Work on that copy:

```powershell
$cs2 = "D:/SteamLibrary/steamapps/common/Counter-Strike Global Offensive"
.\subtools\ag2proportions.exe "$cs2/content/csgo_addons/my_model_test/models/agent.vmdl" --debug
```

Passing a VMDL directly edits it in place and preserves only its first `.bak`.
Generated sources go into a same-named folder beside the model; compiled resources
go under `game/csgo_addons/<addon>`. Read the generated
`debug/MODEL_SETUP.txt` for subsequent ModelDoc setup.

To generate sources without editing the model, save this as `job.kv3` in the
`content/csgo_addons/my_model_test/` addon root:

```text
<!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} format:generic:version{7412167c-06e9-4698-aff2-e63eb59037e7} -->
{
    vmdl = "models/agent.vmdl"
    write_model = false
}
```

```powershell
.\subtools\ag2proportions.exe "$cs2/content/csgo_addons/my_model_test/job.kv3" --generate-only --debug
```

`--generate-only` skips resource compilation; it still needs CS2 data and does
not disable model editing when `write_model` is true. Job paths are relative to
the job file; optional `model_dmx` selects a skeleton and `proportions` a pose DMX.
This is a CS2 tool, not a Source1 MDL arm fix. It adapts translation proportions,
not bind axes or mesh rigging. Finish in ModelDoc and check the complete
model and its actions in game. See [installation](INSTALL.md) for staging,
process-interruption recovery and same-target locking. The bounded
[SAS gameplay validation](tests/reports/ag2-gameplay-v1238.md) covers only its
listed model/actions. A separate `first_person = true` job requires explicit
arms `model_dmx` and an enabled `hudmodel` graph; see the
[AG2 guide](subtools/ag2proportions/README.md). Its
[resource-validation report](tests/reports/ag2-firstperson-v1238.md) is distinct
from actual gameplay acceptance in the [game matrix](GAME_PLATFORM_MATRIX.md).
Use `--help` for further options, including the Linux compiler runner.

## Documentation

| Topic | Guide |
| --- | --- |
| Installation and package contents | [INSTALL.md](INSTALL.md) |
| Features by upstream and fixed scope | [Feature matrix](FEATURE_MATRIX.md), [completion ledger](FIVE_COMPILER_COMPLETION.md) |
| QC syntax, compatibility choices and limits | [COMPATIBILITY.md](COMPATIBILITY.md) |
| Tests and actual game-validation coverage | [Game/platform matrix](GAME_PLATFORM_MATRIX.md), [VALIDATION.md](VALIDATION.md) |
| Scene cache, vertex baking and bounded USD composition | [SCENE_IMPORT.md](SCENE_IMPORT.md) |
| Selective decompilation, quality reports and key reduction | [DECOMPILER_EXPORTS.md](DECOMPILER_EXPORTS.md) |
| Mesh processing, local materials and incremental builds | [AUTHORING_WORKFLOWS.md](AUTHORING_WORKFLOWS.md) |
| CSGO cloth and DMX inputs | [Cloth authoring](CSGO_CLOTH_AUTHORING.md), [DMX inputs](CSGO_DMX_INPUTS.md) |
| M3D/USD/VRML/C4D import requirements | [O5_FORMAT_IMPORTS.md](O5_FORMAT_IMPORTS.md) |
| VRM and finite mesh-state playback | [VRM runtime](VRM_RUNTIME.md), [mesh states](MESH_STATE_WORKFLOW.md) |
| Upstream integration and release automation | [AUTOMATION.md](AUTOMATION.md) · [Pre-release validation](tests/reports/v1.2.38-candidate.md) |

## Build from source

Windows: use a Visual Studio 2022 x64 developer terminal with CMake 3.22+ and Ninja.

```powershell
cmake --preset x64-compact
cmake --build --preset x64-compact
```

Output: `out/build/x64-compact/NewPageMergeMDL/`. The compact preset uses
MinSizeRel and IPO/LTO; `x64-release` provides an ordinary development Release build.

Linux: use CMake and a complete GCC or Clang C/C++ toolchain with matching LTO tools.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=MinSizeRel -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON
cmake --build build -j2
```

Dependencies are vendored under `libs/` in the complete project source. For a build
without LTO, use `-DCMAKE_BUILD_TYPE=Release -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF`.
Rebuilding the Windows C4D helper additionally requires a separately licensed
Cineware SDK; see the [format guide](O5_FORMAT_IMPORTS.md).

## Credits and license

Original project: Toppi. The original [MIT license](LICENSE) and third-party
notices are retained. The separate VRML converter keeps its GPL license and
corresponding source. AG2 notices are included under `subtools/licenses/`.
Reference CE/Tools++/Neko executables and recovered source are not bundled.
[UPSTREAM_README.md](UPSTREAM_README.md) preserves upstream information for reference.
