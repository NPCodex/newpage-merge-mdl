# USD reference fixture

`flattened-instances.usda` and `flattened-instances.usdc` are an independently
authored three-vertex triangle, instanced at translation `(4, 0, 0)`. OpenUSD
26.8 `Usd.Stage.Flatten()` generated the undefined prototype and internal Add
reference; `Sdf.Layer.Export()` wrote the equivalent text and Crate files. They
contain no game or third-party model data.

The expected imported positions are `(4, 0, 0)`, `(5, 0, 0)`, `(4, 1, 0)`.
Undefined prototype roots must not contribute duplicate visible geometry. The
binary fixture also checks that Crate layer parsing preserves prim specifiers.
OpenUSD is not needed to execute the regression test.
