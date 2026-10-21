# 场景导入、缓存与顶点动画

QC 导入文件的骨骼名称和动画名称按实际选择器的大小写规则检查。同一个文件内，`Hand`/`hand` 之类的骨名歧义会失败；不同文件合法共用同一骨架仍可合并。动画不能重名，也不能使用合成姿态的保留名 `BindPose`。未命名动画的自动名称同样参与冲突检查。错误会指出源文件与冲突名称。

声明了蒙皮的 DMX 顶点必须提供完整、类型正确的关节索引和权重数组。正权重必须指向已映射骨骼，权重必须有限且非负；零权重占位索引可以为 `-1`。每个蒙皮顶点至少需要一个正权重。显式空蒙皮与未蒙皮输入仍可使用。不会以补零或任意根骨掩盖损坏数据。

挂载 VPK 中的资源会校验完整 preload 加正文的 CRC32，覆盖 VPK v1/v2、内置正文与分卷。校验失败会停止编译并保留此前发布的模型文件；CRC 只检查内容一致性，不代表来源认证。

## 控制场景缓存

```qc
$SceneCacheMiB 256
$body first scene.gltf InNode MeshA
$body second scene.gltf InNode MeshB
```

默认预算为 256 MiB；`$SceneCacheMiB 0` 禁用解析缓存，合法范围为 0–16384。预算以保留的 `aiScene` 数组和对象估算，不是进程内存硬上限；导入器的临时内存、已转换的 Source 模型、分配器开销不包含在内。超过预算的单个场景可以正常导入，但不会留在缓存中。其余条目按最近使用顺序淘汰。

一次 QC 加载拥有独立的缓存生命周期；成功或失败退出后都释放解析场景。不同 `InNode` 可共享解析结果；导入后端、采样率和是否需烘焙权重不同的请求不混用。复用前检查已记录输入的时间戳与大小，包括外置 buffer、MTL 和挂载文件。不要在编译过程中并发改写输入。

`-perfjson report.json` 的 `scene_cache` 对象提供 `hits`、`misses`、`evictions`、`stale`、`bypasses`、`estimated_retained_bytes`、`estimated_peak_retained_bytes`、`budget_bytes` 与 `import_seconds`。这些数据用于测量实际项目；不会据此预先承诺加速。不同采样率仍可能各保留一份解析场景，其总量受预算限制。

## 按误差减少顶点动画帧

```qc
$body model motion.gltf InNode MeshA BakeSceneAnimation Move SceneSampleRate 60 BakeSceneTolerance 0.01 0.1
```

`BakeSceneTolerance` 的两个数分别是**导入缩放后的模型单位位置误差**和**法线方向误差（度）**。两者必须有限且非负，法线误差不能超过 180 度；该选项必须与 `BakeSceneAnimation` 一起使用。不写该选项时继续输出原有均匀采样。

先按 `SceneSampleRate` 生成参考帧，再检查所有选定顶点的位置及法线插值误差，保留首尾和满足误差界限所需的中间帧。法线单独变化也参与判断。界限针对这些参考时刻，不保证原曲线在任意连续时间点的误差；MDL 最终量化及游戏渲染也不包含在这个导入阶段的误差数值中。

当前在原生 glTF/GLB/VRM 动画及 `$NoFastGltf` 的原始 glTF 动画采样路径中识别插值方式。含 STEP 的 clip 保留全部参考帧；不能确认插值模式的其他导入器也保守保留全部帧并打印说明。极端曲线达到减帧计算预算时同样保留全部帧。

`.vertexanim.json` 的 `times` 可以不均匀，随包的 `integration/gmod/newpage_vertexanim.lua` 按相邻时间点计算局部插值比例。附加的 `sample_checks` 记录参考采样率、原帧数、保留帧数、是否应用减帧及最大参考采样误差。应用程序应使用 `times`，不要把帧序号除以固定帧率来推算减帧后的时刻。

## USD 组合的明确范围

普通 `.usd`/`.usda`/`.usdc` 文件支持静态网格的有界递归单引用：外部文件相对引用、显式 prim 路径、`defaultPrim` 与同层内部引用；支持 explicit/prepend/append/add 单一 reference。可使用作者在文件中指定的 variant 选择，按声明的 variantSets 顺序处理强度；未选定的 variant 不贡献内容。本地扩展同名 variantSet 时，选定名称同时传递到引用层。

引用根的局部变换、负缩放、`active` 覆盖和 `resetXformStack` 会保留；`instanceable` 引用展开为普通网格实例，其直接本地子节点意见按 USD 的实例规则忽略。普通非实例引用保留本地新增子节点。对已有引用子节点进行同名覆盖需要更完整的上下文组合，目前会明确拒绝，不能借此覆盖其激活状态、实例定义或其他意见。OpenUSD 展平生成的未定义原型仅作为引用来源，不额外导出为网格。

重复的 USD 叶节点名使用完整 prim 路径消歧，例如 `InNode /Second/Triangle`。外部引用层经过同一个文件读取接口，加入编译依赖报告。

缺文件、缺 prim、缺作者指定的 variant、循环引用均明确失败。当前不支持 subLayers、payload/inherits/specializes/value clips、单 prim 上多个 reference arcs（包括本地与变体分别贡献 reference）、reference 时间偏移、嵌套 variant sets、PointInstancer 或引用骨架的路径重映射；遇到这些内容请先用制作软件/OpenUSD 展开对应部分。组合预算为最多 128 个源层、64 层引用/节点深度、65536 次 prim 展开及单层 512 MiB。USDZ/内存输入中的引用、变体与 subLayers 仍须预先展开。

这不等同完整 OpenUSD 或材质着色系统。固定验证使用自制 USDA、独立 OpenUSD 展开结果及真实 Blender 导出的有界静态场景，核对世界顶点覆盖；复杂制作软件场景、完整材质网络、骨骼组合及游戏内表现仍应单独验收。具体证据见 [导入验证记录](tests/reports/v1.2.38-import-validation.md)。
