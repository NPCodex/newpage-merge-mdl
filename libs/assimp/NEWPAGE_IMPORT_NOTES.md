# Local scene importer changes

NewPageMergeMDL keeps the Assimp importer registry as the source for its `-importformats` report. Main-compiler builds explicitly disable the GPL VRML importer. The independent VRML process is built from `tools/vrml_converter/`; its MeshLab source is never linked into Assimp or the main compiler.

The Collada loader uses the custom `NPMDL_SCENE_SAMPLE_RATE` import property to bake the original transform chain. LINEAR, STEP and BEZIER channels preserve their authored interpolation; Bezier sampling solves the control-point time curve. Unsupported interpolation modes fail with an author-side bake diagnostic instead of silently becoming linear curves.

The USD loader uses the offline pinned tinyusdz source in `libs/tinyusdz/`. It preserves all root nodes and reports failed/empty conversions without indexing an empty root array. tinyusdz portability fixes and the exact upstream revision are documented in that directory's `SOURCE.md`.

These contracts are checked with self-authored fixtures in `tests/scene_integration_cases.py`. They are bounded importer checks, not a claim of complete interchange-format parity.
