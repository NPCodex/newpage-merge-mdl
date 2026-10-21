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

**Validation status:** editable polygons and failure diagnostics pass the checked-in
regressions. Real Cinema 4D generator/deformer cache comparisons are still pending
an activated Cinema 4D installation; do not treat the candidate traversal as
validated against Cinema 4D 2026. See [VALIDATION.md](VALIDATION.md).

Skin weights and animated objects are explicitly rejected, rather than silently
producing a static unskinned model. Export the rig and animation as FBX or glTF
from Cinema 4D for the existing compiler import path. Skeletal C4D import remains
a separate stage requiring bind-pose and sampled-pose comparisons. Cinema 4D
shader rendering is not implemented.

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
The helper is separate because the Cineware MSVC C++ ABI cannot be linked into
the main project's LLVM/MinGW binary. Linux builds import a GLB previously
converted on Windows.

CI stages the linked executable from the dedicated
`NewPageMergeMDL-C4D-v1.2.34-win64.zip` asset on the project's `v1.2.34` release.
`automation/windows-extras.json` pins both the ZIP and executable SHA256 values.
The exact release/asset name is resolved through GitHub's API; neither a moving
latest release nor an unverified helper is accepted. The helper archive must be
uploaded before workflows use this pin. Main Windows packages already include
the verified helper, so end users do not need the separate build-input archive.
For verification before upload, use:

```text
python .github/scripts/fetch_windows_extras.py --archive NewPageMergeMDL-C4D-v1.2.34-win64.zip --dist dist
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
