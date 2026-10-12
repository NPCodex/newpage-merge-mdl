# NewPageMergeMDL v1.2.29

English | [简体中文](README.md)

## Before compiling

**For every target game, always pass `-game` with the directory containing that game's correct `gameinfo.txt`.** The argument is a directory, not the `gameinfo.txt` file, Steam library root or `bin` directory. Its AppID selects target behavior, including MDL/VTX layout; its search paths locate required resources. CSGO legacy (730) and Military Conflict: Vietnam (1012110) require their own correct game configuration; borrowing another game's `gameinfo.txt` or setting only `-vtxformat` is insufficient.

```text
NewPageMergeMDL model.qc -game "D:/Games/csgo legacy/csgo" -OutDir "D:/build/model"
```

- `-OutDir` controls output only and cannot replace `-game`. First compile into an isolated output directory while preserving original inputs and existing game models. When deploying, keep the matching MDL/VVD/VTX/PHY/ANI set together; mixing old sidecars can cause loading failures.
- Supply the target game's Source VMT/VTF materials and required mounted resources. Importing a mesh does not convert its source application's shaders or textures into Source materials.
- Format budgets still apply, including at most 256 final bone indices (255 by default), three final weights per vertex and local mesh/index limits. FE cloth targets CSGO skeletal models with extended VTX. Use default offline SubD baking; explicit native SubD patches crash the tested CSGO legacy renderer. See the [capacity ledger](FIVE_COMPILER_COMPLETION.md) and [cloth guide](CSGO_CLOTH_AUTHORING.md).
- [VRM](VRM_RUNTIME.md) and [finite mesh states](MESH_STATE_WORKFLOW.md) require their supplied GMod consumers for runtime behavior. VRML uses the bundled separate converter. Direct C4D input uses the helper included in the Windows package. Linux accepts a GLB converted beforehand on Windows. See the [format guide](O5_FORMAT_IMPORTS.md).
- Launch argument priority is gameinfo, `cfg/commandline.cfg`, then explicit CLI. Use `-nodefaultargs` to disable configuration defaults; CE/Neko differences use explicit compatibility options. See the [default-argument contract](FIVE_COMPILER_COMPLETION.md) and [compatibility notes](COMPATIBILITY.md).
- Preserve `.npmdl-*` journals, staging files and backups after an interrupted compile; the next compile attempts recovery of the model set. If recovery reports a damaged journal or externally changed output, back up the output directory and investigate the error. Do not run multiple compilers against the same output set.

**Project version: v1.2.29.** The compiler, decompiler and bundled tools share this
version.

## Download and install: one complete archive per platform

**v1.2.29 platform status:** the complete Windows archive is built locally with MinSizeRel + ThinLTO, verified using its packaged executables, and includes the exact committed source. GitHub Actions jobs could not start because of an account billing restriction. No verified Linux archive is available for this version; previous Linux archives do not contain this fix. See [current validation](VALIDATION.md).

Choose the current **Windows x64 ZIP** or **Linux ZIP** from [GitHub Releases](https://github.com/NPCodex/newpage-merge-mdl/releases) and extract the entire archive into a new directory. Each archive includes the compiler, decompiler, subtools, separate VRML converter with its corresponding source, preparation scripts, GMod Lua modules, documentation, licenses, build manifest and internal checksums. The Windows archive also includes the C4D helper. No additional release attachments need to be combined. `INSTALL.md`, `upstream-manifest.json` and `SHA256SUMS.txt` are at the package root; reports are in `tests/reports/`. Automatic upstream releases also embed `sources/NewPageMergeMDL-source.zip`; complete project source for manual releases is available from the repository at the release tag. GitHub's automatic **Source code** links are for source browsing, not installation.

For updates, use a fresh directory and the complete new file set; do not overwrite only the compiler or mix helpers from older versions. Ordinary compilation does not require Python; the Python preparation scripts in `tools/` require a separately installed Python 3. Install the GMod Lua consumers according to their guides when using mesh states or VRM runtime features. See [INSTALL.md](INSTALL.md).

A Source model toolchain based on [PulseModel](https://github.com/ToppiOfficial/PulseModel),
with independently implemented StudioMDL-CE / StudioMDL++ / NekoMDL compatibility extensions.
NekoMDL integration follows its supplied Chinese v2.3.0 changelog.
The compiler is `NewPageMergeMDL.exe`; the decompiler is
`NewPageMergeMDL-Decompiler.exe`. Windows x64 and Linux builds are supported;
consult each release's validation record for the platforms actually tested.
See [AUTOMATION.md](AUTOMATION.md) for automatic upstream integration
and GitHub Release configuration.

The objective is one PulseModel-based compiler integrating CE, NekoMDL, StudioMDL 2013 and StudioMDL++ model compilation features. See the [five-compiler feature checklist](FEATURE_MATRIX.md) for source-by-source status and the [v1.2.23 completion ledger](FIVE_COMPILER_COMPLETION.md) for the fixed scope's final conclusions.

## v1.2.29: retain independent collision bodies on procedural hair bones

A `$jigglebone` no longer has its collision geometry merged into its parent solely because it is procedural. Explicit physics constraints, mass settings and merge targets retain their referenced bones. Physics bones and their ancestors receive runtime setup flags so ragdoll creation uses computed bone transforms. Explicit `$jointmerge`, `$jointskip` and forced bone collapse remain effective.

Directly authored joint axes take priority: constraints falling back from missing child bodies no longer overwrite the parent's own limits.

The original Plum `playermodel_f_compile2_hair.qc` now produces **21 bodies** without source edits, restoring the independent `hair_0_1/2/3` bodies and constraints. In GMod `gm_flatgrass`, directly spawned ragdolls and NPC death ragdolls were each observed for 20 seconds with no recorded errors and zero final maximum speed. **394 local compatibility tests passed.** See [validation](VALIDATION.md) for scope and evidence.

CE 0.2 produces 18 bodies from the same original QC because it first removes unused hair bones; an isolated control that explicitly retains those bones produces 21. This fix preserves explicit physics dependencies and does not claim identical default CE output. The reference CE main-branch binary identifies itself as `0.3.0 (Preview)`; that banner is not a formal release tag.

## v1.2.28: merge PulseModel upstream updates

Merges 18 upstream commits from `52cf296` through [`578e86e`](https://github.com/ToppiOfficial/PulseModel/compare/52cf296a953fd6c2d072e34cfde5eb8eccc95564...578e86e38fde086ccfb701d96688817a77e718de), retaining this project's compatibility extensions and default skin hierarchy retention.

- **Sequence bounds:** the default precomputes per-bone vertex boxes and transforms them per frame to reduce vertex skinning work; bounds may be wider. Add `-legacysequencebounds` to compare with the previous algorithm. Project vertex-animation bounds, CSGO world-range diagnostics and related QC policies are retained. See [VALIDATION.md](VALIDATION.md) for measured coverage.
- **DMX and collision:** `$datamodelphysics` reads `physicsPrimitiveList` shapes. `$physicsshape primitive box|sphere|capsule` inside `$physicsmodel` defines bone-bound convex hulls, including `$scale` and ragdoll `$origin`. `$attachment inherit` can reuse an already loaded DMX attachment's bone, flags and local transform. Syntax is in [COMPATIBILITY.md](COMPATIBILITY.md).
- **Shared libraries:** compiler, decompiler and the new tool share DMX support; KV3/zstd support is added. Runtime dependencies are statically linked and retain their third-party notices.
- **Experimental CS2 helper:** both platform packages add `subtools/ag2proportions` (`.exe` on Windows) for CS2 AnimGraph2 proportion adaptation. It is not ordinary Source1 MDL compilation or a GMod/CSGO arms fix. Run `--help`; [INSTALL.md](INSTALL.md) describes requirements, in-place editing and license paths. Successful building or help output does not establish CS2 ModelDoc or in-game validation.

## v1.2.27: retain externally animated arm bones

Weighted skeletal bones and their ancestors now survive by default. A static local idle no longer removes forearm and finger bones needed by weapon animations, `$includemodel` or bonemerge. The original arm QC requires no compatibility switch or source edits. Explicit collapse policies remain available; the target engine's final bone budget still applies. See [compatibility details](COMPATIBILITY.md) and [validation evidence](VALIDATION.md).

The v1.2.25/26 compile, structural and byte-equality checks did not detect this runtime defect. Recompile with this version and replace the matching model files together.

## v1.2.26: smaller complete packages

Published complete archives: Windows **13.83→7.23 MB**, Linux **13.04→4.74 MB**. All tools remain included; the final Windows package reproduces the original Plum/viewarms outputs byte for byte. See [VALIDATION.md](VALIDATION.md).

Distribution builds use `MinSizeRel` with IPO/LTO to reduce executable size while retaining all importers, compiler options and tools. Ordinary `Release` remains available for development. The runtime directory no longer duplicates the statically linked tinyusdz source and developer images; `libs/tinyusdz/` retains `LICENSE`, `LICENSE-APACHE-2.0`, `SOURCE.md` and `THIRD_PARTY_NOTICES.md`. USD import works without those source files.

The separate GPL VRML converter's complete corresponding source and build files remain bundled. Automatic upstream packages still embed the exact merged source; manual release source remains available at the release tag. Windows retains the previously verified C4D helper. Local Plum and viewarms model outputs have been compared file by file with the previous version and are identical; final archive sizes and validation scope are recorded in [VALIDATION.md](VALIDATION.md).

## v1.2.25: viewarms QC compatibility fixes

VRD constraints that omit a dotted namespace such as `ValveBiped.` now follow parent-bone collapse, re-expressing driver rotations and helper poses relative to the surviving parent. Shared `$texturegroup` columns whose base material is unused by the model now warn and are skipped, preserving family count and substitutions for used materials. The original QC and VRD need no changes. See [compatibility notes](COMPATIBILITY.md) and [validation](VALIDATION.md).

## v1.2.24 release size optimization

Release/MinSizeRel builds discard unused functions and data by default; GNU/Clang outputs also omit development symbols. All importers and compiler features remain enabled, with the existing Release optimization level. Use `-DNEWPAGE_COMPACT_RELEASE=OFF` to retain release symbols. Debug/RelWithDebInfo builds are unaffected. Measured sizes and output comparisons are recorded in [VALIDATION.md](VALIDATION.md).

## v1.2.23: fixed five-compiler integration scope

The [completion ledger](FIVE_COMPILER_COMPLETION.md) accounts for every R/E/V/S/O item and the H format/runtime exclusions. New upstream revisions and concrete defects remain maintenance inputs; the known scope is not split into an endless sequence of extra feature batches.

- Adds ++ configured defaults, an explicit Neko condition mode, CE weight policy, large flex splitting, true FBX bind poses and authored scene animation sampling; fixes premature removal of hitbox-, animation- and lower-LOD-only bones.
- Adds interrupted-output recovery, PMX named morphs, skinned GPU instances and a build-derived `-importformats` inventory.
- Fixes false output-recovery errors from Windows short directory names/case aliases, and slow regular-grid vertex lookup from MSVC hash collisions. Symlinks and junctions below the output root remain rejected.
- Includes [finite mesh states](MESH_STATE_WORKFLOW.md), an explicit [VRM runtime](VRM_RUNTIME.md), and [M3D/USD/VRML/C4D import workflows](O5_FORMAT_IMPORTS.md). The GPL VRML converter is a separate executable; the main program retains its existing license.
- Restores the 2013 reference environment and records its measured limits. Unresolved CE replacemesh syntax and unspecified closed-source format details are documented as unknown, not claimed as parity.
- Follow-up runtime verification confirms L4D2 `2.2.4.3 build 10097` standard `prop_dynamic` entities can create the tool's models and read/switch the `mesh_state` bodygroup; the same path has no `m_flexWeight`, so standard L4D2 entities are not claimed to consume vertex expressions. CE `replacemesh` still lacks reproducible public syntax, Neko's registered formats show no new gap, and Insurgency model loading remains unauthenticated. See the [follow-up runtime report](tests/reports/v1.2.23-followup-runtime.json).

The Windows x64 archive includes `NewPageMergeMDL-C4D.exe` beside the compiler, including in automated releases. Linux imports a GLB converted beforehand on Windows. The ordinary CMake build needs no Cineware SDK; rebuilding the C4D helper still requires a separately licensed SDK. See the [O5 import guide](O5_FORMAT_IMPORTS.md) for format and rebuild requirements.

## v1.2.23 follow-up runtime boundaries

The [follow-up runtime report](tests/reports/v1.2.23-followup-runtime.json) adds bounded evidence without expanding the fixed five-compiler scope:

- **L4D2 2.2.4.3 build 10097:** standard `prop_dynamic` entities created the three `states/avatar/basic` mesh-state fixtures. The initial `mesh_state` bodygroup was `1`, and `SetBodygroup(0, 2)` switched it to `2`. This confirms that standard entities can consume mesh-state bodygroup output.
- The same entities all returned `false` for `NetProps.HasProp("m_flexWeight")`. Standard `prop_dynamic` therefore is not a verified vertex-expression/flex consumer; that path needs `CBaseFlex`, an engine extension or a game-specific interface.
- **CE `replacemesh`:** no public syntax, source implementation, issue example or release asset was found in this follow-up. It cannot safely be implemented as a `replacemodel` alias and remains evidence-limited.
- **Neko:** all 64 extensions extracted from the fixed binary descriptor are already covered by the registered set; no new format entry was found.
- **Insurgency:** reliable model-load readback is still missing, so in-game model compatibility remains unauthenticated.

## v1.2.22 historical record: all 11 fixed CSGO porting packages complete

**A1–A7 and B1–B4 are complete** within the [fixed CSGO scope](CSGO_PORTING_SCOPE.md). This closes the 11-package scope; the compatibility boundaries and validation coverage below do not add new porting packages.

- **Cloth input and fitting:** per-document Y/Z `upAxis` for cloth and plane proxies, final FE initialization `prerotate`, `flex_borders`, multiweight fixed points, mixed fixed/dynamic fitting, influence thresholds and sparse-cloud strategies. Quad ordering/crossings are repaired, and overly bent all-dynamic quads split along their shorter diagonal.
- **Advanced FE and render projection:** two-node stretch capsules, per-node internal/external spheres and planes, collision masks and rigid stickiness; explicit rods/springs, faceless bone-chain ropes, follow/FTL, local response, mass, volume feedback, smoothing and legacy settings. Surface projection supports two-sided volume, envelopes, island filters, unskinned proxies and automatic roots, producing actual render skinning.
- **DMX skeletal animation:** Rotation and two-bone IK join Point/Orient/Aim/Parent/Twist in one per-frame dependency graph, including animated targets, weights and rotation parameters. QAngle/VMatrix/Color/String/Time logs, six Pack/Unpack operators, reverse sampling, nested clips and FilmClip/track/shot skeletal inputs bake to ordinary animation.
- **Flex and materials:** DMX flex expressions expand `$variables$` in the active QC context while preserving command-line `-defvar` precedence. VMT `$clientShader "MouthShader"` sets MDL material and VTX teeth markers, including skin families and material renames.

See the [cloth authoring guide](CSGO_CLOTH_AUTHORING.md), [DMX input guide](CSGO_DMX_INPUTS.md) and [COMPATIBILITY.md](COMPATIBILITY.md) for syntax, defaults, source distinctions and limits. The `advanced`, projection and fitting controls are tool extensions; not all authoring syntax is accepted by stock studiomdl.

Final local validation passes **325 compatibility, 20 automation and 6 content-mount regressions**. Original Plum QC/materials are unchanged: **126 bones, 572,277 vertices, 18 physics bodies, matching 30 kg MDL/PHY totals, and 65 materials with none missing**. Offline CSGO loaded and ran **10 cloth and 2 rig fixtures**, with observed projection/mixed-boundary deformation, ropes and Rotation/IK motion changes. After `changelevel de_dust2`, all 10 cloth and 2 rig fixtures were recreated and confirmed ready with captures. Six game settings were restored and read back, the game exited normally, and 62 registered temporary files were removed after hash checks. Advanced collision has structural and loading/running evidence, without quantitative collision A/B. These results do not establish frame-by-frame stock parity, zero penetration or exact in-game bone angles. See [VALIDATION.md](VALIDATION.md).

## v1.2.21 historical record: bound colliders, sparse cloth, AxisInterp / Twist and DMX curves

- **Bone-bound colliders:** `$cloth { sphere ... capsule ... }` emits model-owned spheres and tapered capsules that follow animated bones, including scale, bone renaming and axis remapping.
- **Additional cloth bindings:** one-point, two-point or collinear controls can backsolve bones from adjacent faces. `cloth_anchor_free_rotate` and `cloth_use_rods` are supported. The latter replaces selected faces with distance rods, an explicitly defined completion of an empty reference branch.
- **Corrective bones:** legacy `$proceduralbones` files import six AxisInterp poses and emit native procedural records. DMX Twist uses the reference rotation algorithm to bake ordinary animation without requiring the game's disabled-by-default Twist switch.
- **DMX curves and compressed animation:** bounded Float / Vector3 / Quaternion curve evaluation and three-component RLE Vector3 / Quaternion logs. Corrupt data fails before replacing existing output.

See [COMPATIBILITY.md](COMPATIBILITY.md) for syntax, curve modes and limits, and [VALIDATION.md](VALIDATION.md) for evidence. Historical sections retain each version's behavior at that time.

At v1.2.21, **285 compatibility, 20 automation and 6 content-mount regressions passed**. Original Plum inputs/materials are unchanged. AxisInterp also survives decompilation and stock recompilation. Numeric, structural and in-game evidence is in the [v1.2.21 report](tests/reports/v1.2.21-validation.json).

Offline `de_dust2` checks in **CSGO 1.38.8.1 / 8802** showed seven cloth21 fixtures loading, deforming multiple bones and moving with their entities. Four additional sphere/capsule `contact_on/off` fixtures, using zero gravity and identical visible shells, showed distinct collision responses. Native NP/stock AxisInterp fixtures matched visually at synchronized nominal phases of 0.5/1 seconds. Forward/inverse Twist played in both directions using ordinary baked animation. All seven cloth, four contact and four procedural fixtures loaded again after a map reload. These observations do not establish contact on every frame, zero penetration at every point, exact in-game bone angles or complete stock parity.

## v1.2.20 historical record: FE extensions, SubD baking and DMX constraints and animation

This historical section records the four v1.2.20 compilation paths; see v1.2.22 and the authoring guides above for current extensions:

- **FE cloth settings:** `$cloth { ... }` supports damping/wind, cross-face bending rods and rigid edge hinges. New DMX maps provide animation attraction, node radii and ground settings. `gravity_scale 0` becomes zero per-node gravity because the engine replaces a zero descriptor scale with 1. `world_collision` emits native world sphere/capsule flags, collision trees and radii; collision requires runtime colliders.
- **Quad SubD baking:** `$subd`, `$model name mesh.dmx subd` or DMX `subdivisionSurface=true` default to two Catmull-Clark iterations and ordinary triangles; `$subd levels 1..3` selects the iteration count. UV seams are preserved, skin weights and position morphs are interpolated, and normals are recomputed. Explicit `$subd native` retains native patches for renderers with working SubD support. The tested CSGO legacy HLMV crashes while rendering native patches, so this mode emits a warning.
- **CSGO rig constraint baking with multiple targets:** `$datamodeljoints rig.dmx proceduralbones` imports Point / Orient / Aim / Parent and solves target weights, offsets and Aim parameters into ordinary skeletal animation for CSGO AppID 730 targets. Records 8/9/10/12 are retained as rig metadata because the engine ignores them; slaves do not carry `BONE_ALWAYS_PROCEDURAL`. At v1.2.20, Twist, dependency cycles, missing bones, raw delta inputs and dependencies on runtime procedural bones failed explicitly; the current seven-class scope is described above.
- **DMX animation evaluation:** ordinary `$sequence name anim.dmx` evaluates the active clip's multi-hop connections, expressions, Vector/Quaternion Pack/Unpack and Transform operators offline, including layered logs, step segments and clip time transforms, then bakes ordinary bone frames. This works for all targets. At v1.2.20, unsupported connected operators, compressed logs and curve-type interpolation failed explicitly; subsequent extensions are documented in the current DMX input guide.

These are bounded implementations; [COMPATIBILITY.md](COMPATIBILITY.md) lists syntax, numeric rules and rejected inputs. Added regressions inspect actual MDL/VTX records, decompile/recompile output and animation values. See [VALIDATION.md](VALIDATION.md) for complete test, production-model and runtime evidence. Loading or matching structural data alone does not establish complete runtime parity.

Older version sections preserve their implementation and validation state at the time. Current capabilities are described by the [v1.2.23 ledger](FIVE_COMPILER_COMPLETION.md) and the compatibility-boundaries table.

Final Windows validation: **248 compatibility, 20 automation and 6 content-mount tests passed**. Original Plum inputs/materials remain unchanged; bounded in-game cloth, baked SubD and constraint animation results are recorded in [v1.2.20 validation](tests/reports/v1.2.20-validation.json).

## v1.2.19 historical record: automatic mass, appended collision sources and CSGO FE cloth

This section records v1.2.19 behavior; later cloth settings and SubD support are described above under v1.2.20.

`$automass` / `$calculatemass` now compute mass from mounted surface density and shell thickness, fixing the former 1 kg result for every body. Manifest files, VPK/archive chunks, base inheritance, later property overrides and `$jointsurfaceprop` are supported. MDL and PHY store the same total mass. Explicit `$mass` retains its PHY distribution rules, including the reference 1 kg minimum per body.

`$addconvexsrc` accepts a same-line quoted `offset pos[...] angle[...] scale[...]` and `concave`. Transforms and scaling follow physics-source coordinates. With the global `$concave` enabled, concave-marked sources merge with the root before welding and unmarked extras remain independent convex hulls. Without that gate, all geometry forms one convex hull. Shared render sources are preserved.

`$cloth proxy.dmx` / `$clothplanecollision planes.dmx` now serialize real FE data for skeletal models targeting CSGO AppID 730 through `-game`, with extended VTX. The bounded path supports explicit `cloth_enable`, triangle/quad proxies, fixed points, node constraints, weighted bone backsolving and bone-bound infinite one-sided planes, with at most 4096 proxy points. At v1.2.19, every simulated component needed an anchor; fixed points required one bone; a bone could not bind both fixed and simulated points; each driven bone needed at least three non-collinear simulated points. At v1.2.19, settings blocks, unknown cloth maps and other targets were rejected; native SubD and in-game cloth motion were not certified. See v1.2.22 and the cloth guide above for current multiweight anchors, mixed fits and sparse-cloud behavior, and [COMPATIBILITY.md](COMPATIBILITY.md) for data requirements.

All **209 compatibility and 20 automation tests** pass locally on Windows, including six mass, six appended-source and ten FE cases. Six separate CONTENT mount regressions also pass. The unchanged original Plum QC compiles in isolation and passes structural checks: 126 bones, 572,277 vertices, 18 physics bodies and matching 30 kg MDL/PHY totals. CSGO HLMV loads quad and triangle cloth fixtures with planes for 15 seconds each without access violations; all six temporary game files were removed. These checks establish bounded loading stability, not in-game cloth motion or complete CSGO parity. See [VALIDATION.md](VALIDATION.md) and the [v1.2.19 validation record](tests/reports/v1.2.19-validation.json).

Stock CSGO default-surface tetrahedra with edges 10 and 20 produce total masses of 5.462355 and 43.698837 kg, matching this compiler to six printed decimal places. An equivalent-geometry cloth comparison matches fixed nodes, inverse masses, fixed offsets and plane constraints within floating-point precision. Bone backsolving uses different algorithms, so deformation equivalence remains unverified.


## v1.2.18 historical record: CSGO LOD skinning and CONTENT mounts

For CSGO legacy (gameinfo SteamAppId 730), lower LODs inherit skin weights from the nearest root-model vertex; ties use UV, normal and source index. `$skinnedLODs` preserves authored lower-LOD weights. Other games retain their defaults. Spatial lookup precedes the existing LOD bone remapping. Two-stage root/higher-LOD tolerance matching checks position, UVs, normals, weights and tangents. Small UV-boundary fixtures match the installed stock CSGO StudioMDL; this is not whole-file parity for arbitrary models.

`$contentrootrelative` supports CONTENT `*` / `?` patterns, VPKs and archive chunks. Loose directory files precede archives; GAME lookup precedes CONTENT, which remains opt-in. All 187 compatibility and six mount tests pass; Plum and Yvette compile and pass structural checks. No new in-game validation was performed. At v1.2.18, cloth, full SubD and complete bone-collapse parity were still open.

Supply the correct `-game` directory for CSGO/MCV, even with a separate OutDir; `-vtxformat` alone only selects VTX layout. CSGO/MCV targets now use a 256-byte extended header with an FE pointer slot that was zero at v1.2.18, before bodygroup presets. Other targets retain their layout. Installed stock models confirm this span. Each game's preset fixture survives 15 seconds under its HLMV/debugger without access violations; temporary game files were removed. This fixes the serialization prerequisite, not the full cloth pipeline.

## v1.2.17 historical record: startup description correction

Compiler and decompiler startup messages now use `Source model toolchain` instead of a fixed MDL version label. Model output formats are unchanged.

## v1.2.16 historical record: CSGO / MCV loading crash fix

When `-game` supplies a gameinfo.txt with SteamAppId 730 (CSGO legacy) or 1012110 (MCV), the compiler automatically selects extended VTX headers: 33-byte strip groups and 35-byte strips. The former 25/27-byte default is misinterpreted by these loaders and can crash HLMV or the game even though the MDL version is 49. Other targets keep their defaults. Explicit QC `$vtxformat` / pulseqc `vtx_archetype` override detection; CLI `-vtxformat` has highest priority. Forcing legacy layout for these targets emits a warning.

One compiler supports both targets. Use the actual `.../csgo` or `.../vietnam` directory with `-game`; `-vtxformat 1` only selects VTX layout. Since v1.2.18 the MDL extended header also follows the detected game, so supply `-game` even when setting a separate OutDir. Deploy the complete MDL/VVD/DX90 VTX/PHY set. Mixing a new MDL with an old VTX can still crash. Preserve the CSGO player/custom_player model path: an ordinary test-model directory selects the old player-animation behavior. The original QC needs no extra stock-player animation include.

All 182 compatibility and 20 automation tests pass. Yvette body/three arms QCs and MCV body/arms/legs QCs compile and load in their respective installed HLMV tools; all seven outputs survive 15-second debugger checks without access violations. Actual character rendering and Yvette included-animation playback were separately observed. MCV tests cover players, first-person arms, bots, ragdolls and map reload on mcv_camp/mcv_bridge. CSGO tests on de_dust2/ar_baggage cover player/bot replacement, 11 skins × 18 body combinations in bounded native-entity batches, normal player death and map reload. See the [v1.2.16 report](tests/reports/v1.2.16-validation.json) for CSGO runtime evidence. Plum retains legacy output and passes structural validation with 126 bones / 572,277 vertices. These are bounded model/scenario checks, not universal game compatibility.

## v1.2.15 historical record: CSGO QC compatibility (31 entries; cloth was unfinished then)

Implements 31 of the previously missing 33 command entries: bone controllers/runtime flags, prefix/substr renaming, bind-axis and center adjustments, bounding-box policies, collision precision, appended sources, attachment replacement, CONTENT lookup, internal/physics naming, and virtual VTA generation from OBJ frames. Output changes are serialized into MDL/VVD/PHY. Virtual VTA supports flexfile, native `$vta` and VCA without intermediate files and rejects changed frame topology.

This is not 31 new algorithms. `$externaltextures` warns and ignores as in the reference; `$gamma` has no texture-processing use in this Source pipeline; `$skinnedLODs` corresponds to the existing native per-LOD skin preservation policy. `$insertbone` reparents without inserting a bone, matching the enabled reference code. `$subd` emits the subdivision-surface header flag; the complete quad/SubD importer has not been ported.

At v1.2.15, `$cloth` and `$clothplanecollision` were **unimplemented and rejected**; v1.2.19 adds the bounded FE path described above. They require finite-element nodes, constraints, control-bone backsolving and the CSGO extended-header data, rather than a jigglebone or keyvalues substitute. All 19 new targeted cases, 181 compatibility tests and 20 automation tests pass. Plum (126 bones, 572,277 vertices) and Yvette compile and pass serialized-output checks. No CSGO in-game validation is claimed. See [COMPATIBILITY.md](COMPATIBILITY.md) and the [validation record](tests/reports/v1.2.15-validation.json).

## v1.2.14 historical record: CSGO QC triangle-order compatibility

Adds `$preservetriangleorder` with actual cache/overdraw and NvTriStrip sorting bypass, using reference depth-first edge traversal. It takes precedence over `$UseLegacyStripify`, retaining bone palettes, flex groups and the selected VTX format. Global source-face order across materials/groups is not guaranteed. A self-authored 32-face grid matches CE order; regression covers command case, DX80/DX90, both VTX layouts, LODs and legacy combinations. The original Yvette QC compiles (144 bones, 65,902 vertices), and Plum still compiles. All 162 compatibility and 20 automation tests pass; CSGO in-game behavior has not been tested.

## v1.2.13 historical record: Insurgency 2 / Military Conflict: Vietnam QC fixes

Restores legacy single/double-backslash macro continuations alongside `$endmacro`. Attachments, hitboxes and hitgroups accept final `$renamebone` aliases before bone retention; case-only bone renames are allowed, while collisions with a different bone remain errors. Both supplied original QC/QCI sets compile without input changes and pass MDL/VVD/VTX structure validation. All 161 compatibility and 20 automation tests pass. In-game behavior in these two games has not been tested in this batch.

## v1.2.12 historical record: CE LOD option recovered through binary analysis

Static analysis of the CE x64 LOD parser and three self-authored reference compiles confirm `replacemodel source replacement reverse`. The case-insensitive option belongs on the same command line and reverses replacement LOD winding. Imported normals and shared sources remain unchanged. DX80/DX90 regression checks cover reversed and later ordinary LODs. All 158 compatibility and 20 automation tests pass.

The changelog's `replacemesh` remains unresolved: neither supplied x86 nor x64 binary contains that token, and the inspected x64 parser exposes replacemodel/replacematerial/removemesh. This recovered reverse option is not treated as proof of that changelog entry.

## v1.2.11 historical record: glTF animation interpolation on the Assimp path

Fixes lost STEP markers and CUBICSPLINE tangents with `$NoFastGltf`. Assimp still imports geometry and skins; animation is sampled from original glTF accessors without building a second geometry copy. Eighteen translation checks cover LINEAR, STEP and CUBICSPLINE on both backends across glTF/GLB/VRM. Quaternion animation, unnamed nodes/clips and scale/morph-weight baking are also checked. All 157 compatibility and 20 automation tests pass. Other Assimp formats are not universally verified.

## v1.2.10 historical record: Neko procedural parent compatibility

`$NekoDriverBone` now accumulates pose-animation ancestor transforms and resolves world poses against the final model's bind parents. Animated ancestors and differing pose/model hierarchies are retained. Sampling sources no longer define the model skeleton, including when the command precedes `$body`. Six self-authored Neko 2.3.0 reference cases cover separate parents, parent animation, hierarchy changes, scale, renamed parents and multiple helpers; twelve command-order regression cases pass. Native `$driverbone` sampling semantics remain unchanged. All 154 compatibility and 20 automation tests pass.

## v1.2.9 historical record: Neko morph mapping and output preservation

With `$dmxcompatibility neko`, `$RenameMorph` maps exact imported FBX/glTF names once: missing names are ignored, the latest definition wins, mappings do not chain, and QC declarations remain unchanged. Named flex blocks retain declared keys. Native global renaming is preserved; ambiguous target names are rejected.

At v1.2.9, output files were staged with checked writes, flushes and closes, then backed up and replaced. Handled failures rolled back the set. Directory conflicts and Windows VTX sharing locks preserved prior bytes in tests, but restart recovery after forced termination was absent. All 153 compatibility and 20 automation tests passed. v1.2.23 adds a durable journal and recovery on the next compile; arbitrary hardware failure or power-loss reordering cannot be guaranteed lossless.

## v1.2.8 historical record: five-compiler integration focus

Restores warning-only acceptance of older Neko `$prefer_fbx` and `$forcecapsules` directives, matching Neko 2.3.0 without changing import or generating capsules. `-usenvtristrip` selects the existing legacy backend. CE `$DontDestroy` / `-DontDestroy` accepts the default output-preservation policy. All 150 compatibility tests pass. The two StudioMDL 2013 archives count as one compiler with different dependencies.

## v1.2.7 historical record: reference flex policies and production validation

Adds `$dmxcompatibility native|ce|neko`, preserving native defaults while matching distinct reference rule/controller policies in 14 cases per compiler. Claudia is tested with its actual materials, facial changes, an isolated generated decimated LOD and ragdoll physics in GMod. Both original Hair QCs still compile. Repeated joint weights and macro error provenance are fixed; output preflight and serialized-table checks are expanded. `-perfjson` includes individual processing stages. There are 146 compatibility and 20 automation tests. See [IMPROVEMENTS.md](IMPROVEMENTS.md).

## v1.2.6 historical record: compatibility, ragdolls and package verification

Adds explicit copy weightlists, fixes procedural collision geometry causing unstable ragdolls, improves include diagnostics and long-scene sampling. Complete Hair player/NPC models were tested in GMod. There are 138 compatibility and 20 automation tests. See [IMPROVEMENTS.md](IMPROVEMENTS.md) for all seven areas and unresolved differences.

## v1.2.5 historical record: Hair QC compilation fix

Correct overly strict bodygroup validation; add final-product and preset-integer regressions. The suite then had 128 compatibility tests.

## v1.2.4 historical record: seven improvements

- Ordered SearchPaths, AppID/Steam library discovery, directories and VPK v1/v2 with preload/split archives; `-steamdir` overrides Steam discovery.
- Direct Draco decoding with attribute IDs, normals, UVs and uncompressed morphs; corrupt streams fail explicitly.
- `BakeSceneAnimation <clip> SceneSampleRate <fps>` samples scale, skinning and morph weights into vertex flex frames. Emits `.vertexanim.json`, ships GMod Lua playback and includes sampled render bounds.
- Per-bone `$collisionjoints` VHACD decomposition preserves mass, hierarchy and constraints.
- Six CE/Neko differential fixtures check hierarchy, transforms, IK/LOD, jiggle, DMX, controllers and eyelid bindings. Fixed an orphan VTA eyelid descriptor; existing corrective/driver/normal regressions remain covered.
- Actual GMod Alyx loading, faces/eyelids and forced LOD, plus authored vertex-animation and two-body physics/ground-contact tests. White material override isolates geometry; authored shaders are not comprehensively certified.
- `-perfjson` phase timings/peak working set and isolated repeated production benchmarks with deterministic output checksums.

At v1.2.7: **146 compatibility tests and 20 automation tests.** Usage and bounded results: [VALIDATION.md](VALIDATION.md).

## Inherited PulseModel features

SMD / DMX / FBX compilation, model decompilation and utility tools are retained. Fast SMD loading, meshoptimizer, dynamic output buffers, mesh splitting, `-nodx80`, animation `reverse`, macro defaults / `$endmacro`, `nocull`, mesh-selected `$bbox` and unused-material removal already exist upstream and are not additions by this project.

## Additions compared with original PulseModel

This comparison uses merge baseline `578e86e38fde086ccfb701d96688817a77e718de`. The following features and compatibility fixes are implemented independently; they do not certify full parity with the closed-source reference compilers. See [COMPATIBILITY.md](COMPATIBILITY.md) for arguments and behavioral differences.

### QC, animation and StudioMDL++ compatibility

| Feature | Supported additions |
| --- | --- |
| Variables and diagnostics | `$setvariable` replaces variables; duplicate `$definevariable` warns and preserves the first definition. |
| Include resolution | `$IncludePrefix` / `-IncludePrefix`, `$IncludeAnimPrefix` / `-IncludeAnimPrefix`; `$PUSHDInclude` enables lookup in the current pushd directory. |
| Animation extensions | `copy reference [pos] [rot]`, `match reference [pos] [rot]`, and nested animation `if / else if / else`, with this project's documented semantics. |
| Animation culling / rendering | `-cullanims` forces unreferenced-animation culling while honoring `nocull`; `-MostlyOpaque` overrides QC render settings. |
| Sequence ordering / UTC flag | Preserves order from existing v48/v49 models by default; `-noremap` selects QC order. `$sequence gmtime` survives decompilation; UTC synchronization needs mod support. |
| VTA compatibility fix | Repeated `flex` / `flexpair` names preserve independent frame deltas and weight ramps. |

### StudioMDL-CE face, bone and output extensions

| Feature | Supported additions |
| --- | --- |
| Flex controllers | `$OverrideFlexControllers`, `$AllowDuplicationFlexControllers`, model-block `addcontrollerbyflex`. |
| Inverse flexes / delta scaling | `$AddInvStudioFlexes` / `InvertControllers`; `$DefaqScale`, `$IgnoreDMXDefaq`, per-key `fscale`. |
| Decay / default flex | `$ZeroFlexDecay`; default-flex baking and `$IgnoreDefaultFlexKey`; `NoAutoDMXRulesLegacy` clears previous automatic rules/controllers. |
| Eyes / eyelids | `$EyeballScale`, `$IgnoreEyeballScaling`, `$IgnoreEyeballIrisScale`, `$IgnoreEyelid`; eye binding remains scoped to each model. |
| DMX normals / wrinkles | `$ComputeDeltaNormals`, `$ComputeWrinkles`, `$ComputeNormalsAndWrinkles` and model-level overrides; `$RemapFlexToGlobal` maps flexes into compiled bind space. |
| Per-model options | `$body` / `$bodygroup studio` face blocks; private `RenameMat` / `RenameMatByPrefix`; `BindToOneBone` / `$CollisionBindToOneBone`. |
| Bones / bounds | Opt-in `$CEBoneRules`; `$AllowCollapseVertexBone`; `$AlwaysCollapseByPrefix` and its launch equivalent; `$HBoxIgnoreChild`. |
| Paths / output limits | `$PUSHDProcedural`; `$OutDir` / `-OutDir`; `$OutputBufferSize`, `$MDLOutputBufferSize`, `$ANIOutputBufferSize` check sizes before writing. |

CE compatibility switches are opt-in; some boolean switches toggle when repeated. Single-bone weighting is experimental, and arbitrary complex rigs are not certified equivalent to CE.

### NekoMDL import and scripting extensions

Implementation follows the supplied **Chinese v2.3.0 changelog**.

| Feature | Supported additions |
| --- | --- |
| More formats | Fast cgltf import of glTF / GLB / VRM; Assimp import of OBJ, DAE, PMX and other supported formats; `$NoFastGltf` selects Assimp for glTF. The existing ufbx FBX importer remains. |
| Scenes / morphs | Node transforms, static scale, skins, named morph targets; missing UVs/morph normals are accepted, and missing base normals are generated. |
| Node / animation selection | `InNode` selects a node and descendants; `Pick` selects an animation; `SampleRate` controls sampling; `$FPS` sets subsequent default playback/sampling rates; `$UpAxis y/z gltf/assimp` independently sets import axes. |
| Faces / driver bones | `$NekoModel` supports multiple studios, shared flexes/rules and scoped eyes/lids; named `flex` / `flexpair` bind source morphs; `$NekoDriverBone`. |
| Jiggle / animation transforms | `$JiggleBoneRealign`, `$ReverseJiggleBoneRotation`; animation `NoBoneRealign`, `AppendScale`. |
| Materials / morph normals | `$PreRenameMaterial`; `$DiscardVertexAnimationNormals` removes delta normals while retaining base normals and position deltas. |
| Resource budgets | `$MaxVerts limit [clamp]` splits per-material output meshes; `$MaxBones` / `-maxbones`; `$FileBufferSize` caps each serialized output. Algorithm/default differences are documented below. |
| Scripts | Line `$if/$ifdef/$elif/$eldef/$else/$endif`; `$UndefineVariable`, `$Msg`, `-Dname value`; `$Include file iffileexists`; `$QCAssert` with an omitted expected boolean. |
| Post-compilation actions | `-checksequenceorder`; `-reloadhlmv` notifies Windows HLMV; `-playbeep` signals success/failure. |

### Project tooling and maintenance

- The compiler, decompiler and utilities share the NewPageMergeMDL project naming and current project version; compiler startup messages and redirected logs are plain text, without a colored banner.
- Automatic PulseModel integration through a maintained patch, followed by Windows/Linux builds, tests and GitHub Release publication. Conflicts or failed checks stop publication. New closed-source CE/++/Neko features require manual analysis.
- The historical v1.2.22 result was 325 compatibility, 20 automation and 6 content-mount regressions passing with actual-output inspection. Current results are in [VALIDATION.md](VALIDATION.md). Earlier checks compiled the supplied complete `survivor_teenangst.qc` with mixed DMX/GLB bodies and the user-provided Alyx QC. User models and reference compiler binaries are not redistributed.

## v1.2.3 historical record: fewer incomplete features

- Model-scoped `RenameMat` now supports many-to-one material names. Mesh ranges, triangles, morph vertex indices and face tags are regrouped without affecting other body choices. Tests cover six vertices, two LODs and flex output.
- At v1.2.3, the fast glTF path decoded meshopt ATTRIBUTES, TRIANGLES and INDICES streams and applied NONE/OCTAHEDRAL/QUATERNION/EXPONENTIAL/COLOR filters. EXPONENTIAL attributes and both index modes had output tests for geometry, UV, flex and decompiled animation; v1.2.23 adds individual OCTAHEDRAL/QUATERNION/COLOR fixtures. Encoding quantization remains observable. Invalid ranges and corrupt streams fail before output.
- Static unskinned `EXT_mesh_gpu_instancing` expands shared meshes under per-instance translation, rotation and scale, retaining inherited transforms, morph targets and InNode subtree selection. Rotation, mirrored scale and invalid quaternions have tests. Expanded scenes retain the source node/bone budget.

At v1.2.3, material merging was removed from the unfinished list, while Draco, AppID mounting, animated scale/weights and expanded rig/runtime checks were still open. Those historical items were addressed by subsequent releases; current implementation and evidence boundaries are in the [v1.2.23 ledger](FIVE_COMPILER_COMPLETION.md). The historical count was 127 compatibility and 20 automation tests.

## v1.2.2 historical record: six improvements

- **Bodygroups:** 64-bit combination arithmetic accepts up to 2^31 combinations (body values 0..2147483647). Tests accept 31 binary groups and reject 32 before output. Fixed single-choice parts no longer add meaningless preset-mask digits.
- **Skin groups:** check materials × families × 2 bytes before allocating the table, including configured MDL/file budgets. Tests cover 1001 skins and preservation of prior outputs on rejection.
- **Global clamping:** `$UseLegacyClampMethod` splits across materials. `$MaxVerts limit [clamp]` controls the trigger and piece cap (at most 65536). LODs, flexes and eyeball mesh references move with vertices. Added `_clamped` bodyparts share the original base and choices, with blank alternatives for absent pieces. Conservative triangle reservation operates on the unified output dictionary, rather than reproducing all historical CE source-stage behavior.
- **Animation:** retain bones and parents used only by `localhierarchy`; reject self-parenting. Explicit `$alwayscollapse` retains its existing precedence.
- **DMX:** validate corner counts and index bounds before normal collapsing and flex indexing, covering positions, normals, UVs, balance and speed. Finite-number validation also covers blendweights, balance and speed.
- **Collision:** accumulate volume-weighted mass in double precision to avoid NaN with large biases; reject nonpositive biases and unrepresentable volumes. Single-body `$collisionmodel` gains `$decomposeconcave` using bundled VHACD for closed, connected concave meshes with a positive `$maxconvexpieces`. Ordinary `$concave` retains island splitting; v1.2.4 also supports ragdoll decomposition.

**v1.2.5 fix:** correct an overly strict check that blocked the complete Hair QC. Both original player and NPC QCs compile, with 126 / 124 bones and 572277 vertices, without changing the user models. Validate stored bodygroup bases and preset values while retaining diagnostics.

## v1.2.1 historical record additions and fixes

- `$UseLegacyStripify` / `-nvtristrip` select the bundled NvTriStrip backend; meshoptimizer remains the default. Tests cover DX80/DX90, both VTX layouts, LODs and skin remapping across hardware bone palettes. The legacy algorithm removes duplicate and index-degenerate faces.
- LOD bone replacement resolves chains and rejects cycles or conflicting targets. Added combined output checks for IK chains, procedural drivers, renamed bones and unused-bone collapse.
- DMX loading rejects NaN/Inf in geometry, weights and animation numbers. Corrective COMBO/DOMINATE rules have numeric evaluation tests; comprehensive complex-rig parity remains unverified.
- Large translations and oversized RLE animation records use frame encoding, with float32 positions when half precision would overflow. Tests cover 255-frame repeat boundaries and section seams. Compressed IK/local-hierarchy offsets above 32767 bytes fail before replacing output files.
- Long PHY surface properties, root-bone names and merge names are no longer truncated by 512-byte temporary buffers.
- Animation range scanning visits contiguous poses. A 128-bone, 1800-frame benchmark improves its three-run median from 118.1 to 109.5 ms, with identical SHA256 values for four output files. This measures the compression stage of one fixture.

See `libs/nvtristrip/SOURCE.md` for dependency provenance and [RESEARCH.md](RESEARCH.md) for the six investigations and remaining work.

## v1.2.0 historical record validation and optimizations

- SMD/VTA loading reads lines directly instead of retaining redundant whole-file buffers. Invalid bone parents, non-finite coordinates and invalid weights fail explicitly; more than 16 source weights no longer cause an out-of-bounds read.
- Sparse mesh partition maps and ownership tracking reduce a 9000-vertex, 3-vertex-cap benchmark from 300.7 ms to 15.8 ms, with four byte-identical output files. This measures an extreme partition case, not a universal speedup.
- A 181,271,943-byte (172.88 MiB) VTA with 2.4 million real vertex records compiles successfully. Peak working set falls from 880 MB to 376 MB with byte-identical output. Run `tests/stress_vta.py` to reproduce.
- Tests cover 130 output materials, collapse of 512 source bones, 256 output bones and animation of bone 255. The 256-bone case uses frame animation encoding. **512 final output bones remain unsupported**: standard MDL/VVD byte-sized bone indices require rejection above 256 before writing.
- Added multi-bone DMX morph, split flex/LOD and collision rename/parent regressions. The supplied extreme model compiled with 126 bones and 572277 VVD vertices. Later v1.2.6/v1.2.7 checks covered GMod geometry and physics; the material-asset gap at that time was closed by the v1.2.8 Plum validation.
- Automatic releases increment patch versions and recognize existing versioned tags. See [RESEARCH.md](RESEARCH.md) for investigation results and remaining work.

## Compatibility boundaries and validation coverage

This list reflects v1.2.23 implementation; the [completion ledger](FIVE_COMPILER_COMPLETION.md) records the fixed scope and acceptance results. All 11 CSGO porting packages are complete. These are runtime requirements and limits on extrapolating the evidence, not an additional sequence of feature packages.

| Area | Current status and boundaries |
| --- | --- |
| CSGO cloth | `flex_borders`, `prerotate`, mixed fitting, multiweight anchors, advanced FE, ropes and render-skinning projection are implemented. The target remains skeletal CSGO AppID 730 with extended VTX. Plane proxies require rigid single-bone binding; sparse fits need valid adjacent bases. World collision needs game-supplied colliders and volume feedback needs FitMatrix. Advanced collision lacks quantitative A/B or frame-by-frame zero-penetration proof. See the [cloth guide](CSGO_CLOTH_AUTHORING.md). |
| SubD | Offline Catmull-Clark baking is the default: authored DMX quads, 1–3 iterations and ordinary triangles. Native patches require explicit `$subd native` and extended VTX; the tested CSGO legacy/HLMV native path crashes. Non-manifold input, triangle decimation, excessive growth and unsupported morph/merged-part combinations are rejected. |
| DMX rig and animation evaluation | Point/Orient/Aim/Parent/Rotation/IK/Twist bake through a unified graph. External rig import remains CSGO-only; runtime IK/blending and later QC edits do not re-solve authoring constraints. Raw delta inputs, runtime-procedural dependencies and `$centerbonesonverts` combinations remain rejected. Value types, reverse sampling and nested timelines are expanded; compressed logs remain Vector3/Quaternion-only. Full SFM sessions and track crossfades are outside scope. AxisInterp rejects unrepresentable control-axis changes. See the [DMX guide](CSGO_DMX_INPUTS.md). |
| Reference evidence | Both supplied CE architectures reject the tested `replacemesh` forms. E1 closes as unavailable reference evidence without an invented alias. The 2013 environment and actual capacity were measured; Neko's unfrozen historical format claim cannot establish per-format equivalence. See the [ledger](FIVE_COMPILER_COMPLETION.md). |
| Interrupted output recovery | Durable journals, per-output process locks, commit markers and fingerprint checks are implemented. The next compile recovers before reading old sequence order. Damaged journals or externally changed files are retained and reported. Arbitrary hardware failure/power-loss reordering is not guaranteed lossless; readers do not see an instantaneous atomic replacement of every file. |
| Skinned instances and mesh states | Skinned `EXT_mesh_gpu_instancing` expands into independent bones, geometry and animation, with positive uniform instance scale. Nonuniform scale/shear requires prior baking. [Finite topology states](MESH_STATE_WORKFLOW.md) switch bodygroups through the supplied GMod player and require that explicit consumer. |
| L4D2 runtime boundary | On `2.2.4.3 build 10097`, standard `prop_dynamic` entities created the three states/avatar/basic models and read/switched the `mesh_state` bodygroup. All three lacked `m_flexWeight`, so the standard entity path cannot consume vertex expressions directly. A CBaseFlex entity, engine extension or game-specific interface is required; this evidence does not claim that a GMod Lua consumer runs in L4D2. |
| VRM runtime | The [preparation tool and GMod modules](VRM_RUNTIME.md) implement VRM 0/1 named expressions, binary/override behavior, material adaptation, springs and sphere/capsule collisions. This bounded adapter needs corresponding Source materials; it does not execute Unity/MToon or promise arbitrary frame-for-frame/zero-penetration equivalence. |
| Import formats and interpolation | FBX cluster binds, PMX named morphs, Assimp keys/boundaries and Collada STEP/LINEAR/BEZIER have fixed acceptance cases; glTF STEP/CUBICSPLINE is preserved. Unrepresentable tangents need baking. M3D/USD are built in, VRML converts separately, and C4D editable polygons use the Windows helper; see the [format guide](O5_FORMAT_IMPORTS.md). |
| Complex rigs and collision | Fixed cases cover CE multi-bone/controller remapping, hard edges/authored normals, corrective/eyelid combinations, Neko multi-studio/LOD and nine bone-rule combinations, alongside existing IK/jiggle/per-bone VHACD. These fixtures do not establish complete reference equivalence for every hierarchy or model. Explicit single-bone weighting uses the first imported influence. |
| Cross-game behavior and performance | The original Plum, self-authored models, per-engine runs and fixed benchmarks are recorded in [current validation](VALIDATION.md). Uninstalled games do not count as passed. Reference runs with different bone counts, index coverage or required environments are not treated as equal-output speed comparisons. |

v1.2.8 production validation uses Plum. Its original Hair QC and serialized output checks pass. Supplied materials load in GMod without missing entries; 28 captures cover bodygroups, skins and facial changes, and all 18 ragdoll bodies settle stably. The initial capture was retested with material warm-up. Future production validation uses Plum rather than Claudia. See the [v1.2.8 validation record](tests/reports/v1.2.8-validation.json).

Removed from the issue list: Draco/meshopt decoding, sampled scale/morph-weight baking, NvTriStrip and cross-material partitioning, large-translation animation bounds fixes, phase timings and output integrity checks. Explicit CE/Neko facial profiles pass 28 reference comparisons. `copy animation weightlist`, `match pos/rot`, conditionals and `reverse` pass seven StudioMDL++ pose/FPS cases. See [IMPROVEMENTS.md](IMPROVEMENTS.md) and the [v1.2.7 validation record](tests/reports/v1.2.7-validation.json) for coverage.

## Compatibility choices and usage requirements

These are integration requirements or intentional implementation differences, rather than unresolved bugs.

- Animation baking is capped at 4096 frames and 16 million source vertex samples. Accuracy depends on sampling; game playback requires controller integration. UTC synchronization through `gmtime` also requires mod support.
- The default `native` facial behavior retains PulseModel semantics. Use `$dmxcompatibility ce|neko` for reference facial policies. `$CEBoneRules` is opt-in.
- `$MaxVerts` controls per-material output mesh splitting, with a real ceiling of 65536. `$FileBufferSize` caps each output file's bytes. Dynamic buffers and a unified LOD vertex dictionary do not reproduce reference source pre-splitting or fixed preallocation.
- `NoAutoDMXRules` suppresses automatic rules per source; use `NoAutoDMXRulesLegacy` to clear earlier automatic controllers and rules. `addcontrollerbyflex` honors min/max rather than reproducing the reference binary's range parsing defect.
- Whole-file byte equality with the reference CE/++ outputs is not promised. Existing `copy pos/rot` is a project extension.
- PulseModel source is integrated automatically; conflicts or failing checks stop publication. CE/++ updates supplied by the user require manual analysis and implementation. VBSP, VVIS, VRAD and BSPZIP map tools are outside this project's scope.

See [COMPATIBILITY.md](COMPATIBILITY.md) for syntax and differences, and [BINARY_ANALYSIS.md](BINARY_ANALYSIS.md) for binary investigation evidence.

## Build from source

Windows: use a Visual Studio 2022 x64 developer terminal with CMake 3.22+ and Ninja.

```powershell
cmake --preset x64-compact
cmake --build --preset x64-compact
```

Output: `out/build/x64-compact/NewPageMergeMDL/`. This preset uses `MinSizeRel` and IPO/LTO, requiring matching compiler, archiver and linker support for LTO. The complete Visual Studio 2022 x64 developer toolchain meets that requirement. Use the `x64-release` preset for ordinary Release development builds.

Linux: install CMake and a complete GCC or Clang C/C++ toolchain with LTO support, then run:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=MinSizeRel -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON
cmake --build build -j2
```

Dependencies are vendored in the complete project source's `libs/`; no additional package manager is required. The binary installation archive is not a complete build tree. GCC needs matching LTO plugins and archive tools; Clang needs matching LLVM archive tools and a linker that supports LLVM LTO. For development without LTO, use `-DCMAKE_BUILD_TYPE=Release -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF`.

## Usage

```powershell
NewPageMergeMDL.exe model.qc -game "C:/Games/MyMod" -vtxformat 1
NewPageMergeMDL-Decompiler.exe model.mdl -smdanimation
```

`.qc` and `.pulseqc` inputs remain supported. Internal `pulse` namespaces are
preserved for source compatibility.

## Validation

```powershell
python tests/compatibility.py out/build/x64-release/NewPageMergeMDL/NewPageMergeMDL.exe
python -m unittest discover -s tests -p test_automation.py
```

v1.2.23 passes 369 compatibility, 20 automation, 9 content-mount, 9 Lua, 7 C4D and 9 output-recovery tests. Temporary SMD/QC and synthetic scene fixtures inspect MDL/VVD/VTX/FE data and decompile animations to check positions, rotations and conditions. Current production validation uses unchanged original Plum QC/materials: 126 bones, 572,277 vertices, 18 physics bodies, matching 30 kg totals and 65 materials with none missing. See the [v1.2.23 ledger](FIVE_COMPILER_COMPLETION.md) and [VALIDATION.md](VALIDATION.md) for current results and runtime coverage.

Historically, the user-provided Alyx QC compiled successfully with 113 bones and 27,571 VVD vertices; that compile check alone did not cover in-game loading or rendering.

## Credits and license

Original project: Toppi. The original [MIT LICENSE](LICENSE) and third-party
notices are preserved. `ag2proportions` ships `subtools/licenses/zstd.txt` and
`subtools/licenses/ValveResourceFormat.txt`; source notices are in
`libs/zstd/LICENSE` and `libs/keyvalues3/ValveResourceFormat.LICENSE`.
[UPSTREAM_README.md](UPSTREAM_README.md) keeps upstream
information, including old program names and download links, for reference.
StudioMDL-CE / Tools++ closed-source executables and recovered source are not
included in this project.
