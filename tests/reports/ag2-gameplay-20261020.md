# AG2 full-character validation — 2026-10-20

This is bounded validation of the current ag2proportions build against the installed official CS2 SAS model. The tool remains experimental; this is not validation of arbitrary user rigs, all weapons, all accessories, or every animation state.

## Provenance and isolation

- Install: `F:/SteamLibrary/steamapps/common/Counter-Strike Global Offensive 730`.
- Executed build: `D:/newpage-merge-mdl/build-subtool-formats-20261020/NewPageMergeMDL/subtools/ag2proportions.exe`, SHA-256 `440e1297c8377d0843fc69dc5ca7bdf331f6cd0703affde99513298bdbaa4742`.
- Official source path was read from the installed VPK directory: `agents/models/ctm_sas/ctm_sas.vmdl_c` (563655 bytes, archive 3). The `characters/...` path is a separate 4791-byte resource. See `official-model-paths.json`.
- Source mesh/animation DMX files came from the previously extracted official SAS set, copied to new isolated addons. Plain uses the recompiled unmodified full ModelDoc. Scaled uses authored 1.1 mesh/spatial scaling and generated AG2 proportions.
- Initial rig auto-selection correctly rejected five candidate DMX files as ambiguous. An explicit body-DMX job (`scaled-job.kv3`) resolved the input without code changes.
- AG2 and actual CS2 resourcecompiler completed successfully, including whole plain and scaled ModelDoc compilation. Logs: `ag2-explicit-body.log`, `rc-sas_plain.log`, `rc-sas_scaled.log`, `rc-runtime-plain.log`, `rc-runtime-scaled.log`.

## Runtime method and negative control

`ent_fire !player SetModel` made both the plain recompiled model and a confirmed official stock path invisible. This method was rejected as an invalid test control and is not classified as an AG2 defect.

The successful method compiled the plain/scaled ModelDoc to the official logical name inside separate addons (`npmdl_ag2_runtime_20261020` and `npmdl_ag2_scaled_20261020`). Each run started a new process with `-insecure -tools -addon ... +sv_lan 1 +map de_dust2`. Normal CT spawning loaded the model; no official VPK was replaced. Filesystem logs show the selected addon before the base VPK, and `ent_text` identifies `player[303], model: agents/models/ctm_sas/ctm_sas.vmdl`.

## Observed results

| Check | Result | Evidence |
|---|---|---|
| Whole mesh and materials | Plain and scaled full SAS both visibly render in the running local game. | `plain-rifle-standing.png`, `scaled-rifle-standing.png` |
| Runtime proportion difference | Same position, angles and camera settings align background and feet; scaled head/shoulders and skeleton are visibly taller. This supports actual changed character proportions, rather than only observing stock SAS. | `plain-fixed-skeleton.png`, `scaled-fixed-skeleton.png` |
| Proportions resources | Plain resource query matches 0. Scaled matches generated clip and uimodel/worldmodel graphs. | `runtime-plain-console.log`, `runtime-scaled-console.log`, `runtime-plain-comparison-console.log` |
| Pistol/rifle attachment | Complete body holds P2000 and M4A4; M4A4 follows hands during firing and reload in observed poses. This is a gross visual check, not exhaustive attachment tolerance measurement. | `scaled-skeleton-attachments.png`, `scaled-rifle-standing.png` |
| Third-person reload | Shot reduces magazine 30→29; visible reload pose then return to holding pose with 30/93 ammunition. | `scaled-rifle-reload-start.png`, `scaled-rifle-reload-complete.png` |
| Crouch and stand | Full body transitions to sustained crouch holding M4A4, then back to standing. | `scaled-rifle-crouch.png` |
| First-person regression | Arms, M4A4 shooting and reload visibly function in the scaled addon. `hudmodel` still uses stock `animation/graphs/viewmodel/viewmodel.vnmgraph`; this is a no-regression observation, not validation of a generated first-person graph. | `scaled-firstperson-rifle.png`, `scaled-firstperson-reload.png` |

The paired capture settings were `setpos 351.392120 2352.942383 -56.803040; setang 0 -157.5 0`, `cam_idealdist 120`, `cam_idealyaw 145`, `cam_idealpitch 0`. Screenshots are not a calibrated measurement of exact scale.

## Remaining limits

- The installed tools reject `ent_animgraph2_open_graph 303` with `Unrecognized tool 'animgraph2_editor' specified by request - ignored.` No live graph-node debugger result is claimed. The model's named worldmodel entry references the wrapper, the generated resources load, and the character proportions visibly differ; resource residency alone is not described as live-node proof.
- No claim is made for arbitrary custom meshes/rigs, every reload animation, every weapon/accessory, ragdolls, multiplayer deployment, or generated first-person proportion support.
- Direct `+duck` from VConsole was not recognized by this build. The successful crouch check temporarily used `option_duck_method 1` plus the actual Control key, then restored the option to its original value 0.

## Cleanup

All test CS2 and VConsole processes exited. Original game/user configuration hashes match the current-run `settings-before.json`; two changed user settings were restored and two newly created video-tools settings were preserved under diagnostics. Original console log was restored after saving run-specific evidence. The original official directory VPK SHA-256 remains `f0943b4d5a86fe8f4891ab98983b9d132b4450b9b7401a03a530bcd63f293f99`, matching the previous inventory. Isolated addons are retained for reproducibility and are only mounted by their explicit test launch arguments. No original model assets, VPK payloads, gameinfo, or executable binaries were edited. See `cleanup.json` and `runtime-validation.json`.

## Final Windows candidate provenance bridge

The gameplay run above used AG2 reporting **1.2.36** (`440e1297c8377d0843fc69dc5ca7bdf331f6cd0703affde99513298bdbaa4742`). The final Windows candidate reports **1.2.37** (`02fc88c59be2bfed4340cf3f60bce0938c76918a7a48fb885cc1d422b4ec2135`). This version distinction is retained; the gameplay run is not relabeled as an execution of the final candidate.

Both came from `D:/newpage-merge-mdl` using MSVC 19.51.36260.0, Visual Studio 18 2026 x64 Release, `/O2 /Ob2 /MD`. Their compiler command records match after normalizing the build-output directory and the `PULSEMODEL_VERSION` macro (1.2.36 versus 1.2.37). Their PE `.text`, `.data`, `.pdata`, and `.reloc` sections are byte-identical; `.rdata` and `.rsrc` differ, consistent with the changed version/build metadata.

The final candidate was then executed against a fresh copy of the **same pre-AG2 authored job**, in isolated addon `npmdl_ag2_candidate_20261020`. Both generation and the actual CS2 resourcecompiler exited 0. The generated ModelDoc, skeleton DMX, reference/proportions DMX, clip source, and both graph sources are byte-identical to the runtime-tested outputs. The debug report differs only in four absolute addon paths. All three compiled runtime proportion resources (`proportions.vnmclip_c`, `proportions_worldmodel.vnmgraph_c`, `proportions_uimodel.vnmgraph_c`) are byte-identical.

The candidate-generated whole model was also compiled at the **same logical resource name used during gameplay**, `agents/models/ctm_sas/ctm_sas.vmdl`. Its entire file is **not** byte-identical: the `RED2` compilation/dependency metadata block differs. The remaining **27 of 28 resource blocks** match byte-for-byte, including `DATA`, mesh vertex/index/data blocks, animation blocks, `PHYS`, `CTRL`, and `RERL`. Thus the final candidate's generated runtime content matches the material exercised in-game; the distinction about the full compiled file and build version remains explicit.

No game was reopened for this check, and original runtime evidence was preserved. The additional candidate addon remains in the installation's `content/csgo_addons/` and `game/csgo_addons/` trees and requires an explicit test `-addon` launch to load. Machine-readable evidence and logs: `candidate-provenance/summary.json`, `output-comparison.json`, `compiled-model-blocks.json`, `report-path.diff`, `ag2.log`, `rc.log`, and `rc-runtime-path.log`.
