# meshtool binary file protocol

`meshtool simplify request.bin response.bin` and
`meshtool decompose request.bin response.bin` are internal batch interfaces.
They do not read OBJ, SMD or MDL files. All fields have little-endian byte order,
without padding. `u32`/`i32` are unsigned/signed 32-bit integers; `f32` is a finite
IEEE-754 binary32 value. The supported executables use 64-bit little-endian
hosts; unsupported byte order is rejected. Format versions below are independent
of the application's release version.

## Simplify, request version 1

1. `u32 magic = 0x4D535750` (bytes `PWSM`), `u32 version = 1`.
2. `u32 vertex_count`, then `vertex_count` triples of `f32 x, y, z`.
3. `u32 run_count`, then each run: `u32 index_count`, `u32 target_index_count`,
   `u32 flags`, followed by `index_count` values of `u32 vertex_index`.

Indices must be inside the shared vertex pool. `index_count` must be divisible
by three; the target must not exceed it. Flags are `0` or `1` (lock borders).
The target is an index budget, not a guaranteed resulting triangle count.

Response: `u32 magic`, `u32 run_count`, then for each run `u32 kept_index_count`,
`f32 error`, and the kept `u32` indices. The response has no version field;
the caller selects its layout through the validated request version.

## Decompose, request version 2

1. `u32 magic = 0x44435750` (bytes `PWCD`), `u32 version = 2`, `u32 job_count`.
2. For each job: `u32 vertex_count`, that many `f32 x, y, z` triples,
   `u32 triangle_count`, that many `i32 a, b, c` index triples, then
   `f32 concavity`, `u32 max_hulls`, `f32 decimate`, `u32 resolution`.

Indices must be nonnegative and inside that job's vertex pool. Empty jobs
(zero vertices and triangles) produce zero hulls. A nonempty job requires at
least four vertices and one triangle. Integer algorithm parameters must fit a
signed 32-bit integer; the underlying VHACD defaults/clamping remain in effect.

Response: `u32 magic`, `u32 job_count`, then each job's `u32 hull_count`; each
hull has `u32 point_count` followed by that many `f32 x, y, z` triples. Hulls are
point clouds: callers reconstruct faces. There is no response version field.

## Limits and failure behavior

| Limit | Maximum |
| --- | ---: |
| Entire request file | 512 MiB (536,870,912 bytes) |
| Vertices per pool/job | 4,194,304 |
| Simplify runs | 1,048,576 |
| Indices per simplify run | 16,777,216 |
| Decompose jobs | 262,144 |
| Triangles per decompose job | 8,388,608 |

File sizes are checked before allocation using 64-bit quantities. Counts are
checked before reading their arrays. Truncated data, trailing bytes, invalid
magic/version, nonfinite numbers and invalid indices fail. Whole-file size is
also the aggregate input limit; these caps are not a promise of bounded CPU
time for arbitrary valid geometry.

Exit status **0** means a complete response was published. Status **1** means
invalid arguments/input, algorithm failure or an output error; the diagnostic
is on stderr and is not a stable machine-readable error enum. These exit
statuses retain the existing caller contract. Failed operations preserve an
existing response file through temporary-file publication. No partial binary
error response is emitted. The request and response paths should be distinct.
