# v1.2.38 generated AG2 graphs: actual CS2 observation

Observed on 2026-10-21 and 2026-10-22 in Windows CS2 1.41.9.1, build 10924,
revision 11150591, on `de_dust2`, using isolated local addons and `-insecure`.
This extends the [resource validation](ag2-firstperson-v1238.md); it does not
replace that report's bone/clip/graph checks with visual inference.

## Generated world and first-person graphs

The full SAS fixture has all five meshes scaled by 1.1 and an authored
`npmdl_validation_helper` bone. ResourceCompiler retains 98 bones. It is a
bounded modification of the CS2 skeleton, not an arbitrary bind-axis rig.
The tested AG2 program SHA256 is
`251469ffdaf568f9878ca229da788cf5e36191088bd47f03b2146c5a5342c683`.

The actual game `resource_list proportions` reports all five generated resources:
world/UI/viewmodel graphs and their world/view clips. The complete custom model
SHA256 is `f5513b848639c515e9450b2343f2841cd832eda4d435f5a52c5a3f525d88ff3d`.
The following actions were observed with this generated-view addon:

| Action | Bounded observation |
| --- | --- |
| AWP | First-person holding, shot/recoil and reload; ammunition changes and reload completion recorded. Third-person holding observed. |
| M4A4 | Draw, shot/recoil, reload completion and inspect observed. |
| Desert Eagle | Draw, first-person shot/recoil, reload completion and third-person holding observed. |
| Full character | Visible complete mesh/materials, standing and crouching transitions. |

The tests do not establish a calibrated attachment-position tolerance, all
weapons/skins, arbitrary skeleton adaptation or live animation graph-node traces.
The game logs include unknown `e_face_idle`/`e_body_idle` parameter messages;
these observations do not prove full UI/face graph parity.

## Death physics and fixture correction

The initial custom source reconstruction already omitted `PhysicsJointList` and
`PhysicsBodyMarkupList` before AG2 processing. Its 15 collision shapes alone did
not establish a complete ragdoll. The initial standing-after-death observation
therefore could not be attributed to the generated animation graph.

A separate `npmdl_ag2_ragdoll_v1238` addon restores the original SAS body's
metadata and 14 joints (12 conical, 2 revolute), scaling joint anchors by 1.1.
Its mesh, skeleton, collision shapes and generated graphs retain the custom
fixture's values. Resource-level comparison verifies all joint non-frame fields
and body scalars, total authored mass 272, and anchor error at most 0.000291
Source units. This is a correction to the diagnostic fixture, not an AG2 feature
that reconstructs missing physics automatically.

The repaired compiled model SHA256 is
`d2acc7b8ca7e28c8f28850f2ec71f4d36b95c859e45a2b820cb1b7215451e87d`.
On 2026-10-22 the game loaded the same five generated graph/clip dependencies.
After the player was killed, the character visibly fell and lay on the floor.
The death-camera interval was extended to observe the transition. Screenshot
`extended-death-1.png` records the body on the ground; the later spectator camera
does not measure physical settling. No precise joint trajectory, collision
penetration bound or exhaustive death-animation coverage is claimed.

## Evidence and cleanup

Local evidence is under `.diagnostics/ag2-firstperson-v1238` in the development
workspace: `gameplay-20261021` contains the weapon/action screenshots and console
log; `ragdoll-gameplay-20261022` contains the before/death screenshots, console
log, launch arguments and cleanup record. The recorded demos remain in the
isolated addons. `.diagnostics/ag2-ragdoll-v1238` records original-asset CRC
provenance, the fixture repair and independent compiled-PHYS comparisons.

Both completed sessions exited normally. Saved configuration hashes were
restored and the official directory VPK hash remained unchanged. The earlier
interrupted `ragdoll-gameplay-20261021` directory is not counted as a completed
test and its older backups were not restored over the user's later state.
Valve models, demos and screenshots remain local and are not distributed in the
source tree or release packages.
