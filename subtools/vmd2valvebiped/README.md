# VMD conversion

```text
vmd2valvebiped -vmd dance.vmd -mdl character.mdl
vmd2valvebiped -vmd dance.vmd -mdl character.mdl -pmx original.pmx -dmxmodel 22
vmd2valvebiped -mode camera -vmd camera.vmd -camera-scale 1 -o camera.dmx
vmd2valvebiped -mode face -vmd expression.vmd -mdl character.mdl -o expression.dmx
```

Body mode defaults to a standard ValveBiped target with both leg IK chains.
`-pmx` supplies the MMD source rest pose; repeat `-vmd` for batches. `-start` and
`-end` select an inclusive frame interval. Effective body, overridden face,
camera and IK tracks determine shared duration; shorter tracks hold their final
value. Body mode merges `_face.vmd` and replaces cameras with `_camera.vmd`.

Camera mode needs no MDL: it emits an unanchored camera/FOV DMX and same-stem SMD.
`-camera-scale` is Source units per MMD unit; coordinates map X/Y/Z to X/Z/Y.
`-camerafov bone` adds a FOV child to SMD. Orthographic tracks are rejected.
Face mode reads explicit MDL controller names/ranges and writes model 22 DMX
with facial channels only, requiring no IK or humanoid bones. Use `-facemap` or
`-faceset facs|visemes` as needed. Empty/unmapped facial output fails.
Standalone modes use named VMDs directly, with no automatic sidecars or body
compile/audio/walkframe options.

## Custom named humanoid rig

```text
vmd2valvebiped -vmd dance.vmd -mdl custom.mdl -mapping humanoid.map
```

Example profile:

```text
vmd_humanoid_mapping 1
leg_mode ik
role Pelvis "hips"
role Head1 "head"
role L_Thigh "left upper leg"
role L_Calf "left knee"
role L_Foot "left ankle"
role R_Thigh "right upper leg"
role R_Calf "right knee"
role R_Foot "right ankle"
motion_scale 1
upright auto
basis 1 0 0 0 0 1
```

Version header and `leg_mode ik|fk` are required. Roles name target MDL bones;
omitted roles use `ValveBiped.Bip01_<role>`. Required anatomy is Pelvis, both
Thigh/Calf/Foot chains and Head1/Neck1/Spine4 as an upper reference. Legs must be
direct Thigh → Calf → Foot chains. Explicit profiles need no embedded MDL IK
metadata. `fk` retains FK regardless of VMD IK switches.

Other roles: Spine/Spine1/Spine2/Spine4/Neck1; L_/R_ Clavicle, UpperArm, Forearm,
Hand; Finger0/01/02, Finger1/11/12, Finger2/21/22, Finger3/31/32, Finger4/41/42
(with the Finger prefix on each number). Unknown/duplicate roles, reused target
bones, invalid hierarchy and missing explicit names fail validation.

`motion_scale` is a positive finite multiplier on automatic target/source leg
scale. `upright keep` disables automatic stand-up. `basis` is target-space left
XYZ followed by up XYZ, orthogonal unit vectors after stand-up correction; omit
to infer anatomy axes. `#` comments are supported; maximum profile size is 64 KiB.

This explicitly maps humanoid anatomy, not arbitrary rigs or quadrupeds.
Authored fixtures verify aliases, chains, FK-only and axis/scale effects.
A [real Blender-authored asymmetric rig](../../tests/reports/v1.2.38-blender-vmd.md)
also checks bind weights, fixed feet, bone direction and numeric FK skinning.
That eight-bone leg fixture does not certify production rigs or game visuals.

## Optional body DMX reduction

`-reducepos <source units>` and `-reduceangle <degrees>` default to zero.
Reduction checks original keys and quarter intervals; independent tests check
eighth intervals. Endpoints and IK switch neighborhoods stay. Walkframe/sound
generation preserves all sampled keys. Facial/FOV tracks and SMD stay exact.
Standalone modes reject reduction flags.

Batch destinations are preflighted and published through durable transactions;
a later conversion/write failure preserves old outputs. `-compile` locates the
packaged `NewPageMergeMDL` compiler.
