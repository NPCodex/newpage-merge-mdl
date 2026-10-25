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

`sublayer-only.usda` / `.usdc` contain no local prims and reference the test's
generated `good.usda`. They cover the valid empty Crate TokenVector used for
root `primChildren`, and ensure a sublayer-only root still imports geometry.
`sublayer-offset.usda` / `.usdc` contain a sublayer with nonzero time offset;
the importer must reject it and preserve previous output. The text reader
rejects the offset during parsing; the Crate reader reaches the composition
guard. Both pairs were authored here and exported using OpenUSD 26.8:

```python
from pxr import Sdf
layer = Sdf.Layer.FindOrOpen("sublayer-only.usda")
layer.Export("sublayer-only.usdc")
layer = Sdf.Layer.FindOrOpen("sublayer-offset.usda")
layer.Export("sublayer-offset.usdc")
```
