# Self-authored meshopt fixtures

`meshopt-plain.gltf` is derived from this project's `scene_bytes(uv=True)`, restricted to MeshA with a 0,1,2 uint16 triangle index stream. It includes positions, normals, morph position/normal deltas, UV and a LINEAR translation animation.

`meshopt-triangles.gltf` and `meshopt-indices.gltf` encode its buffer views using the bundled meshoptimizer v1.1 `meshopt_encodeVertexBuffer`, `meshopt_encodeIndexBuffer` or `meshopt_encodeIndexSequence`. Float streams use `meshopt_encodeFilterExp` with 24 bits and `meshopt_EncodeExpSharedComponent`. Fallback bytes are retained, while extensionsRequired ensures the test exercises compressed views. All model content is authored by this project; no user model is embedded.

The black-box tests compare geometry/UV within float quantization tolerance, flex records and decompiled animations. A corrupted compressed header must fail despite valid fallback bytes.
