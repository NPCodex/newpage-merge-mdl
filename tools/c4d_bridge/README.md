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

Supported scope: editable polygon objects, hierarchy transforms, normals, UVs,
material names, per-polygon material assignments and basic diffuse colors. Texture
tags are applied in document order: named polygon selections restrict their
scope, and the last applicable tag wins. Missing selections are ignored; uncovered
polygons use the default material. Material boundaries retain UVs and authored
normals, or smooth normals generated before splitting the mesh. The importer converts centimeters to
meters and C4D handedness to the common scene coordinate system. Textures and
shader networks are not baked into Source materials; supply appropriate Source
materials separately. Convert procedural generators to editable polygon objects
in Cinema 4D before saving. Generated caches, skinning, animation, simulation and
Cinema 4D shader rendering are not implemented by this importer.

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
