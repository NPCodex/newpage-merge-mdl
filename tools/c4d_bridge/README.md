# Windows Cinema 4D bridge

`NewPageMergeMDL-C4D.exe` converts a saved Cinema 4D document to GLB through
Cineware 22 and Assimp. Put it beside `NewPageMergeMDL.exe` to reference `.c4d`
files directly from QC. It can also be called separately:

```text
NewPageMergeMDL-C4D.exe input.c4d output.glb
```

The output must not exist. The main compiler creates an exclusive temporary
directory, imports the resulting GLB and removes its own temporary files. Its
dependency report retains the original C4D input.

Supported static scope: editable polygon objects, hierarchy transforms, normals, UVs,
material names, per-polygon material assignments and basic diffuse colors. Texture
tags are applied in document order: named polygon selections restrict their
scope, and the last applicable tag wins. Missing selections are ignored; uncovered
polygons use the default material. Material boundaries retain UVs and authored
normals, or smooth normals generated before splitting the mesh. The importer converts centimeters to
meters and C4D handedness to the common scene coordinate system. Textures and
shader networks are not baked into Source materials; supply appropriate Source
materials separately.

The candidate importer traverses saved generator and deformer caches. Deformer
caches take precedence; source geometry is not emitted again when a cache replaces
it. Texture tags inherited from the generator and its parents are resolved on the
evaluated polygon selections. Save the evaluated project for Cineware with the
required plugins installed. A generator or plugin without usable polygon caches
fails with an explicit diagnostic. This is a static snapshot of the saved state:
the bridge does not run Cinema 4D generators, third-party plugins or simulations.

The bridge also imports a bounded rig subset: one editable polygon object with
one weight tag and one direct Skin child, ordinary joints/null hierarchy, and
linear relative position/HPB rotation/scale tracks. Skin must use linear blending,
joint coordinates, object transform and no bone scaling. The skinned mesh and its
parents must remain at static geometry bind transforms. Weights must sum to one
within `1e-4`, with at most four positive joint weights per point; quantized sums
inside that tolerance are normalized. Joint inverse binds include the geometry
bind transform. Source-point weights survive UV, normal and material corner
splitting. A saved deformed cache is not used as bind geometry.

One `C4D_Timeline` clip is sampled at the document frame rate, plus original key
times, from the earliest to latest key (rebased to zero). The supported rate is
1–240 fps, at most one hour/100000 samples and one million node samples. Linear
Euler keys become sampled quaternions; intermediate GLB interpolation is not a
claim of exact continuous C4D curve evaluation. Object names must be unique;
the synthetic root name `<C4DRoot>` is reserved.
Constraints, expressions, takes, layers, muted/solo tracks, time remapping,
nonlinear keys, quaternion-mode curves, shear, extra deformers, multi-mesh skins,
dual-quaternion blending, plugins and simulation are explicitly rejected in rigs.
Bake those cases to FBX/glTF in Cinema 4D. Shader rendering remains unsupported.

```qc
$body model rig.c4d
$sequence idle rig.c4d fps 30
```

Animated scale can be exported to GLB, but Source skeletal animation cannot store
scale keys. Request the compiler's existing vertex animation path explicitly:

```qc
$body model rig.c4d BakeSceneAnimation C4D_Timeline SceneSampleRate 30
```

**Validation status:** the bounded importer is compared against the preserved
Cinema 4D 2027 two-joint scene and its three independently evaluated poses, as
well as static generator/deformer references. Separate SDK fixtures cover
nonidentity bind transforms, split UV/material corners, TRS and rejected rigs.
The licensed application has been removed; these are repeatable comparisons
against its saved results, not a new live application run or arbitrary-rig
certification. See [VALIDATION.md](VALIDATION.md).

## Building

The helper requires Windows x64 MSVC and an independently obtained and licensed
Cineware 22 SDK. The SDK is **not** part of this repository or source archive.
Read and accept its license before building or distributing a linked helper.
The official Cineware 22.008 SDK's VS 2019 static-runtime libraries are compatible
with the VS 2022 toolchain used for the validated build. Use a VS x64 developer
command prompt, CMake 3.20+ and the Windows SDK:

```text
cmake -S tools/c4d_bridge -B build-c4d -G "Visual Studio 17 2022" -A x64 -DASSIMP_CINEWARE_ROOT=C:/SDK/Cineware_22_008
cmake --build build-c4d --config Release
```

The Release executable is `build-c4d/Release/NewPageMergeMDL-C4D.exe`. It links
Cineware, Assimp, JPEG, zlib and the MSVC runtime statically. Do not package SDK
headers, static libraries, documentation or vendor examples with the executable.
The helper remains a separate program, allowing the main compiler to use a
different toolchain without linking against Cineware's MSVC C++ ABI. Linux
builds import a GLB previously converted on Windows.

CI stages the linked executable from a dedicated helper asset on a project
release. `automation/windows-extras.json` identifies that asset and pins both
the ZIP and executable SHA256 values.
The exact release/asset name is resolved through GitHub's API; neither a moving
latest release nor an unverified helper is accepted. The helper archive must be
uploaded before workflows use this pin. Main Windows packages already include
the verified helper, so end users do not need the separate build-input archive.
For verification before upload, use:

```text
python .github/scripts/fetch_windows_extras.py --archive NewPageMergeMDL-C4D-v1.3.0-win64.zip --dist dist
```

## Validation

```text
python tests/c4d_bridge_test.py build-local/NewPageMergeMDL/NewPageMergeMDL.exe -v
```

`tests/fixtures/cineware-static.c4d` is this project's self-authored quad with a
translated parent, diffuse material and UVs. Its generating source is
`fixture.cpp`, enabled with `-DNEWPAGE_C4D_BUILD_FIXTURE=ON`; it uses no SDK
example model or documentation. Regenerate it with `c4d-fixture.exe output.c4d`.
The tests inspect GLB material/hierarchy and compiled MDL/VVD geometry, as well
as Unicode paths, node selection, dependencies, cleanup and failure recovery.

`tests/fixtures/cineware-materials.c4d` is another self-authored, genuine Cineware
document. Generate it with `c4d-fixture.exe output.c4d materials`. Its folded
polygon strips cover unrestricted/restricted/overlapping/missing selections,
default materials, a final unrestricted override, authored and generated normals,
UVs and parent transforms. Tests check both the exported GLB and compiled MDL/VVD.

The `cineware-reject-*.c4d` fixtures are generated by the same SDK-based source
using `missing-cache`, `invalid-index`, `short-uv`, `skin` and `animated` modes.
They check explicit rejection and preservation of previous compiled models.
These files contain no real evaluated cache and are not evidence of cache support.

The `cineware-rig*.c4d` files are also self-authored by `fixture.cpp`, using its
`rig`, `rig-badweights`, `rig-dualquat`, `rig-spline`, `rig-constraint`,
`rig-duplicate`, `rig-rootname`, `rig-muted` and `rig-bind` modes. The positive document has
nonidentity mesh/joint binds, two materials, a UV seam and linear TRS keys.
Its expected transforms are computed independently in the regression test.

For an independently generated application reference, run this project's script
in licensed Cinema 4D's Python interpreter:

```text
c4dpy.exe author_fixtures.py NEW_OUTPUT_DIRECTORY
```

It creates a translated/rotated pair of cube generators, one with a bend modifier,
and a separate two-joint animated strip. It saves evaluated caches and records
Cinema 4D's Current State to Object geometry, hierarchy, materials, UVs, normals
and pose samples. The script creates a new output directory and never modifies
existing documents. It requires an active Cinema 4D license and must be run before
claiming those fixtures or comparisons exist.
