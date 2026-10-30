# StudioMDL++ supplied screenshot audit — 2026-10-30

Historical v1.3.1 findings below are retained as the pre-fix control.
The three concrete diagnostic gaps were subsequently addressed in
[v1.3.2](v1.3.2-studiomdlpp.md); engine-specific exclusions remain.

Audit only, against NewPageMergeMDL source v1.3.1 at `ce0c289`. No compiler
implementation, version, package or publication changed. The supplied screenshot
is the requirement source; its date and corresponding StudioMDL++ binary identity
are not established. The public [Tools page](https://ficool2.github.io/HammerPlusPlus-Website/tools.html)
retrieved today still says 26 October 2026 and does not list several of the
screenshot's final items. The screenshot must therefore be tracked separately
from the [previous October integration](v1.3.1-studiomdlpp.md).

## Findings

Three concrete gaps remain: file-case mismatch warnings, degenerate IK warnings,
and diagnostic provenance for late-resolved weightlist errors. Parser diagnostics
already preserve provenance for their covered failures, but this does not extend
to every error raised during compilation. In particular the screenshot's unknown
weightlist example is not covered by the existing diagnostic implementation.

Native animated skeletal scale and MVZ `$retarget` remain explicitly unsupported
extensions. Output-directory spelling/semantics and default procedural directory
resolution are documented differences rather than newly missing implementations.
The exact causes of the screenshot's two unspecified historical crashes cannot
be recovered from the log text alone.

## Complete screenshot checklist

| # | Screenshot item | Current result / boundary |
| --- | --- | --- |
| 1 | `-outdir` | Equivalent direct-root mode is `-OutDirModels`; `-OutDir` retains CE QC-relative root plus `models/`. Not a drop-in command-line alias. Previous direct-output suite covers the distinction. |
| 2 | Animated scale (MVZ) | Not implemented in the current output format. Non-unit DMX skeletal scale fails explicitly; ordinary SMD trailing scale fields remain rejected. |
| 3 | `$retarget` (MVZ) | Not implemented; specific unsupported-target error, separate from offline L4D retargeting. |
| 4 | Deterministic MDL | Already checked using repeated authored fixtures in the previous report; no universal determinism claim. |
| 5 | Syntax location/context, including unknown weightlist example | **Partial.** Existing parser source/caret diagnostics work, but a macro expanding to `weightlist missing_mask` produces only `unknown weightlist "missing_mask" in @idle`, without line/column, excerpt/caret or macro expansion site. |
| 6 | Macro/include handling in parsing errors | Existing parser/lexer cases covered; **do not generalize to late compilation errors**, as item 5 demonstrates. |
| 7 | EOF without newline macro fix | Already covered by four forms in `test_spp_macro_invocations_accept_eof_without_a_newline`. |
| 8 | Remove weightlist limit | Dynamic lists; previous regression resolves mask 257 and checks serialized weight. Format/memory limits still exist. |
| 9 | `-cullanims` removes unused weightlists | **Output effect covered in a bounded probe.** Adding an unused .25 root mask and an unreferenced animation using it leaves the complete MDL byte-identical (1,640 bytes) with `-cullanims`. Internal authored declarations are not explicitly pruned: the writer emits sequence-referenced weight arrays, not every named input declaration. |
| 10 | Infer 1D blendwidth | Already covered for 4/5/6/9 inputs; explicit width and 2D grids retain separate rules. |
| 11 | `$proceduralbones` resolves directories | Opt-in `$PUSHDProcedural 1`; CE default retained. An included QCI alone does not change the source directory. |
| 12 | `<baseang>` | Implemented for the documented VRD path and previously compared; bare AxisInterp `baseang` remains outside the supported claim. |
| 13 | Procedural `$scale` | Existing trigger scale plus corrected aim basepos scale; directional vectors remain directions. |
| 14 | Unknown animation block warns | Implemented; previous valid selection or ordinary default retained. Full multi-clip default equivalence remains unestablished. |
| 15 | Clear `$jointconstrain` error if parent missing | **Already present.** Authored disconnected-root tetrahedron fixture reports the constrained bone, absent parent body and selected root. |
| 16 | File case mismatch warning | **Missing in tested Windows source lookup.** QC requests `mesh.smd`, disk contains `Mesh.SMD`; compilation succeeds without a warning. This is file-name handling, distinct from bone-name case-alias rejection. No Linux run performed here. |
| 17 | Degenerate IK chain warning | **Missing for tested zero-length links.** Three distinct bones with coincident bind positions compile as an IK chain without warning. `LinkIKChains` checks ancestor count, but not geometric degeneracy. |
| 18 | texturegroup crash fix | Existing skin-group safety paths and two targeted tests pass. The screenshot supplies no reproducer; cannot certify the identical historical crash was fixed. |
| 19 | SMD parsing crash fix | Existing strict parent/numeric/skeleton validation and three targeted tests pass. The screenshot supplies no reproducer; cannot certify every SMD crash or the identical historical fault. |
| 20 | Compile more than 128 bones | **Already possible within project limits.** Fresh 129-output-bone fixture passes with `$MaxBones 256` and culling disabled. Existing 512-source-bone collapse/overflow regression passes. Not unlimited output bones or game-runtime certification. |

## Evidence and validation

The tested standalone Windows compiler is the retained v1.3.1 snapshot:

`C:/Users/Kud/Desktop/CODEMDL/.diagnostics/studiomdlpp-20261027/upgraded-v1.3.1/NewPageMergeMDL.exe`

SHA-256: `9d3d1d100b56f5cd00987195e3730ba90041435bc64ec4f282cd50cdb8af8c40`.
Source inspection confirms the relevant late diagnostic, IK and physics branches.
This audit did not rebuild the compiler or execute an unknown/new reference binary.

Authored probes, commands, logs, outputs and result JSON are retained locally in
`D:/newpage-merge-mdl/local-build/studiomdlpp-screenshot-audit/` (`audit.py`,
`results.json`). Seven compile invocations cover case mismatch, macro weightlist
context, zero-length IK, 129 bones, two culling controls and missing collision
parent. All use isolated synthetic game roots; no original user input is changed.
Expected compilation failures establish diagnostics rather than successful models.

Six existing focused regressions were rerun against the snapshot and passed:

- `test_shared_skin_group_ignores_absent_columns_and_keeps_rows`
- `test_shared_skin_group_does_not_relax_row_or_rename_errors`
- `test_smd_invalid_parent_is_diagnostic_not_crash`
- `test_smd_all_numeric_records_reject_corruption_and_preserve_output`
- `test_smd_missing_skeleton_rejects_mesh_and_animation_preserving_outputs`
- `test_512_source_bones_collapse_and_extended_output_fails_explicitly`

The old 494-test total is historical, not a fresh full-suite run. No production
model, game, Linux, package or runtime validation is inferred from these probes.
