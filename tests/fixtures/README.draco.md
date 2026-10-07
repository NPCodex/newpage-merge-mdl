# Self-authored Draco regression

`draco-triangle.gltf` contains one authored triangle, normal/UV attributes,
an uncompressed Smile morph and a translation clip. Its compressed attributes
have unique IDs 17, 23 and 31, intentionally outside the glTF accessor range.
`encode_draco_triangle.cpp` is the generator for the embedded Draco payload;
compile it against the bundled Draco library and pass an output `.drc` path.
No downloaded/user model or reference compiler data is included.
