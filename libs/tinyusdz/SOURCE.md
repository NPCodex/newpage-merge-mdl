# tinyusdz

Pinned upstream: https://github.com/lighttransport/tinyusdz/tree/6050eef932f7d2788656d63297aa488fb0961ed1

Only `src/` and license notices are vendored. The Assimp source list builds these files without network access.
Archive SHA256: `420d382d09a0b6a83b5039f879ff0f0378f065c70061c792fc5ac7227fb5b343`.

License: Apache-2.0 for tinyusdz, with the original notices retained for embedded dependencies.
`LICENSE` retains the upstream copyright notice; `LICENSE-APACHE-2.0` contains the full license terms, copied unchanged from the bundled Apache-2.0 license text.
`THIRD_PARTY_NOTICES.md` retains the binary redistribution notices for the compiled dependencies, including MIT/BSD notices embedded only in headers. Binary packages contain these notices instead of the development source and images; the USD importer is compiled into Assimp and needs no tinyusdz files at runtime. The full source remains here and in automatic releases' embedded source archive.
Local portability modification: files using standard iterator adaptors explicitly include `<iterator>` instead of relying on transitive includes (`tydra/render-data.cc`, `value-pprint.cc`, and affected embedded headers). This is required by the LLVM/libc++ toolchain.
`io-util.hh` uses the compiler-defined `_WIN32` for `MMapFileHandle`'s Windows field. The upstream `WIN32` check depended on whether `windows.h` had been included first, causing incompatible struct layouts and invalid mapped-file pointers with LLVM/MinGW.
