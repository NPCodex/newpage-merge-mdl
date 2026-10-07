# NewPageMergeMDL v1.2.9

[English](README.en.md) | 简体中文

项目版本：**v1.2.9**。编译器、反编译器和辅助工具统一使用本项目版本号。模型文件格式仍为 v49。

自动更新及 GitHub Release 配置见 [AUTOMATION.md](AUTOMATION.md)。

基于 [PulseModel](https://github.com/ToppiOfficial/PulseModel) 的 Source 模型编译工具，加入 StudioMDL-CE / StudioMDL++ / NekoMDL 兼容功能与自行实现的动画扩展。NekoMDL 对照依据为附带的中文版 v2.3.0 更新日志。

编译器：`NewPageMergeMDL.exe`；反编译器：`NewPageMergeMDL-Decompiler.exe`。
支持 Windows x64 和 Linux 构建，模型输出版本为 v49。Windows 和 Linux 构建由 GitHub Actions 验证。

目标是以 PulseModel 为基础，整合 CE、NekoMDL、StudioMDL 2013 和 StudioMDL++ 的模型编译功能。按来源追踪的状态和后续顺序见 [五编译器功能清单](FEATURE_MATRIX.md)。

## v1.2.9：Neko 形态键与输出故障保留

在 `$dmxcompatibility neko` 模式下，`$RenameMorph` 按 FBX/glTF 导入原名映射：区分大小写、缺失忽略、同名定义后者覆盖、不连续映射、不改写 QC 声明；命名 flex 块只保留声明的源键。native 全局重命名行为保留。多个源键映射到同名时明确报错。

输出先全部暂存，检查写入、刷新及关闭，再备份并替换文件集；可处理的故障回滚。目录冲突和 Windows VTX 锁定测试确认旧文件不变；不保证断电或强制终止恢复。153 项兼容、20 项自动化回归通过。

## v1.2.8：回归五编译器整合主线

补齐 Neko 历史 QC 指令 `$prefer_fbx`、`$forcecapsules` 的警告式接受，以及旧参数 `-usenvtristrip`。CE `$DontDestroy` / `-DontDestroy` 接入默认保留输出策略。前两者不改变导入或生成胶囊，符合 Neko 2.3.0 当前行为；旧 QC 不再因这些指令中断。150 项兼容回归通过。StudioMDL 2013 两包按同一编译器、不同依赖配置记录。

## v1.2.7：参考面部模式与生产模型验证

新增 `$dmxcompatibility native|ce|neko`，保留默认行为并支持两种参考编译器的规则及控制器策略；CE/Neko 各 14 项对照一致。Claudia 在 GMod 使用真实材质验证面部变化、生成的减面 LOD 和布娃娃；Hair 两份原始 QC 继续通过编译。修复重复关节权重与宏报错来源，增加写出前及序列化文件检查，`-perfjson` 包含各处理阶段耗时。当前 146 项兼容回归、20 项自动化回归。详见 [IMPROVEMENTS.md](IMPROVEMENTS.md)。

## v1.2.6：兼容、物理与发布验证

新增显式 copy weightlist、修复 jiggle 碰撞几何导致的布娃娃异常、改善 include 诊断和长场景动画采样性能。完整 Hair player/NPC 已在 GMod 检查；当前 138 项兼容回归、20 项自动化回归。七项结果及明确保留的问题见 [IMPROVEMENTS.md](IMPROVEMENTS.md)。

## v1.2.5：Hair QC 编译修复

修正误拒绝有效 bodygroup 基数的检查；增加最终组合乘积与预设整数检查回归，当前共 128 项兼容测试。

## v1.2.4：七项改进

- **资源挂载**：SearchPaths 顺序、`|appid_N|`、Steam 多游戏库、目录和 VPK v1/v2（预载/分卷）；`-steamdir` 指定 Steam 路径。
- **Draco glTF**：直接解码压缩几何及属性映射，保留 UV、法线和未压缩形态键；损坏数据明确失败。
- **动画烘焙**：`BakeSceneAnimation <clip> SceneSampleRate <fps>` 将缩放、蒙皮和形态键权重采样为顶点表情帧；输出 `.vertexanim.json` 并附带 GMod Lua 播放器，渲染边界覆盖全部采样帧。
- **布娃娃分解**：`$collisionjoints` 支持 `$decomposeconcave`，按骨骼分解凹形网格并保留质量、父子关系和约束。
- **骨骼与面部验证**：CE/Neko 六组差分比较层级、变换、IK/LOD、jiggle、DMX、控制器和眼睑绑定；修复 VTA 眼睑的多余描述符。既有 corrective/驱动骨/法线数值回归继续通过。
- **游戏实测**：GMod 验证 Alyx 加载、表情/眼睑、强制 LOD；自制样例验证顶点动画、双物理体质量和地面碰撞。白色材质覆盖用于几何检查，未认证用户材质的全部着色效果。
- **性能诊断**：`-perfjson` 报告加载/编译/写入耗时和峰值工作集；生产模型各三次隔离编译并检查输出 SHA256 一致。

当前 **146 项兼容回归、20 项自动化测试**。参数、实测范围和复现方法见 [VALIDATION.md](VALIDATION.md)。

## 原版 PulseModel 功能

保留原版的 SMD / DMX / FBX 编译、模型反编译及辅助工具。快速 SMD 读取、meshoptimizer、动态输出缓冲区、网格分割、`-nodx80`、动画 `reverse`、宏默认参数/`$endmacro`、`nocull`、按网格计算 `$bbox` 和未使用材质清理等均为上游已有能力，不计入本项目新增功能。

## 相比原版 PulseModel 新增的功能

以下对比基于当前合并基线 `52cf296a953fd6c2d072e34cfde5eb8eccc95564`。这里列出已实现的功能及兼容修复；闭源参考编译器的命令由本项目自行实现，不代表完整行为一致。详细参数与差异见 [COMPATIBILITY.md](COMPATIBILITY.md)。

### QC、动画与 StudioMDL++ 兼容扩展

| 功能 | 已支持的内容 |
| --- | --- |
| 变量与诊断 | `$setvariable` 覆盖变量；重复 `$definevariable` 警告并保留首次定义。 |
| 包含文件查找 | `$IncludePrefix` / `-IncludePrefix`、`$IncludeAnimPrefix` / `-IncludeAnimPrefix`；`$PUSHDInclude` 启用当前 pushd 目录查找。 |
| 动画扩展 | `copy reference [pos] [rot]`、`match reference [pos] [rot]`，以及动画内嵌套 `if / else if / else`；具体语义按本项目文档。 |
| 动画裁剪与渲染 | `-cullanims` 强制裁剪未引用动画，保留 `nocull`；`-MostlyOpaque` 覆盖 QC 渲染设置。 |
| 序列排序与 UTC 标记 | 默认按已有 v48/v49 模型保留序列顺序，`-noremap` 使用 QC 顺序；`$sequence gmtime` 及其反编译保留，需要模组支持 UTC 同步。 |
| VTA 兼容修复 | 同名 `flex` / `flexpair` 多帧保留独立顶点增量和权重区间。 |

### StudioMDL-CE 面部、骨骼与输出扩展

| 功能 | 已支持的内容 |
| --- | --- |
| 表情控制器 | `$OverrideFlexControllers`、`$AllowDuplicationFlexControllers`、模型块 `addcontrollerbyflex`。 |
| 反向表情与增量缩放 | `$AddInvStudioFlexes` / `InvertControllers`；`$DefaqScale`、`$IgnoreDMXDefaq`、表情键 `fscale`。 |
| 表情衰减与默认表情 | `$ZeroFlexDecay`；默认表情烘焙及 `$IgnoreDefaultFlexKey`；`NoAutoDMXRulesLegacy` 清除先前自动规则和控制器。 |
| 眼球与眼睑 | `$EyeballScale`、`$IgnoreEyeballScaling`、`$IgnoreEyeballIrisScale`、`$IgnoreEyelid`；眼球绑定保留各模型作用范围。 |
| DMX 法线与皱纹 | `$ComputeDeltaNormals`、`$ComputeWrinkles`、`$ComputeNormalsAndWrinkles` 及模型级覆盖；`$RemapFlexToGlobal` 将表情转换到编译后的绑定空间。 |
| 独立模型选项 | `$body` / `$bodygroup studio` 面部块；`RenameMat`、`RenameMatByPrefix` 独立材质重命名；`BindToOneBone`、`$CollisionBindToOneBone` 单骨权重。 |
| 骨骼与包围盒 | `$CEBoneRules` 显式启用 CE/++ 折叠规则；`$AllowCollapseVertexBone`；`$AlwaysCollapseByPrefix` / 同名启动参数；`$HBoxIgnoreChild`。 |
| 路径与文件上限 | `$PUSHDProcedural`；`$OutDir` / `-OutDir`；`$OutputBufferSize`、`$MDLOutputBufferSize`、`$ANIOutputBufferSize` 在写入前检查大小。 |

CE 兼容开关需显式启用；部分布尔开关重复使用会切换状态。单骨权重属于实验功能，不能据此保证任意复杂 rig 与 CE 一致。

### NekoMDL 导入与脚本扩展

依据附带的**中文版 v2.3.0 更新日志**实现。

| 功能 | 已支持的内容 |
| --- | --- |
| 更多模型格式 | cgltf 快速导入 glTF / GLB / VRM；Assimp 导入 OBJ、DAE、PMX 等格式；`$NoFastGltf` 切换 glTF 到 Assimp。保留原 ufbx FBX 导入器。 |
| 场景与形态键 | 节点变换、静态缩放、蒙皮、命名形态键；缺少 UV/形态键法线可加载，缺少基础法线时生成平滑法线。 |
| 节点及动画选择 | `InNode` 筛选节点及子节点；`Pick` 选择动画；`SampleRate` 控制采样率；`$FPS` 设置后续默认播放/采样帧率；`$UpAxis y/z gltf/assimp` 分别设置向上轴。 |
| 面部与驱动骨 | `$NekoModel` 多 studio、共享表情/规则及各模型独立眼球/眼睑；按源形态键名声明 `flex` / `flexpair`；`$NekoDriverBone`。 |
| 飘骨与动画变换 | `$JiggleBoneRealign`、`$ReverseJiggleBoneRotation`；动画 `NoBoneRealign`、`AppendScale`。 |
| 材质与形态键法线 | `$PreRenameMaterial`；`$DiscardVertexAnimationNormals` 清除增量法线并保留基础法线与位置增量。 |
| 资源上限 | `$MaxVerts limit [clamp]` 按材质分割输出网格；`$MaxBones` / `-maxbones`；`$FileBufferSize` 限制各输出文件大小。算法和默认值差异见下文。 |
| 脚本兼容 | 行式 `$if/$ifdef/$elif/$eldef/$else/$endif`；`$UndefineVariable`、`$Msg`、`-Dname value`；`$Include file iffileexists`；省略布尔预期值的 `$QCAssert`。 |
| 编译后操作 | `-checksequenceorder`；`-reloadhlmv` 通知 Windows HLMV 刷新；`-playbeep` 播放成功/失败提示音。 |

### 本项目的工具与维护功能

- 编译器、反编译器及辅助工具统一命名和使用 **v1.2.7** 版本号；彩色启动横幅，重定向日志保持纯文本。
- 自动拉取 PulseModel、套用维护补丁，完成 Windows/Linux 构建与测试后发布 GitHub Release；冲突或检查失败停止发布。CE/++/Neko 的新增闭源功能仍需人工分析。
- 146 项兼容测试及 20 项自动化测试；测试检查实际模型输出。NekoMDL 的完整 `survivor_teenangst.qc` 已通过混合 DMX/GLB 编译验证，用户的 Alyx QC 也保持可编译。测试和发布包不包含用户模型或参考编译器二进制。

## v1.2.3 缩减未完成项

- **同名材质合并**：模型级 `RenameMat` 支持多个材质指向同一名称；重建材质网格范围，同步三角形、表情顶点和面分组。验证六个顶点、两级 LOD 和 flex，其他身体组选项保持独立。
- **meshopt 压缩 glTF**：快路径直接解码 ATTRIBUTES、TRIANGLES 和 INDICES 流，并应用 NONE / OCTAHEDRAL / QUATERNION / EXPONENTIAL / COLOR 滤波。实测 EXPONENTIAL 属性流及两种索引流，检查几何、UV、flex 和反编译动画；其他滤波路径尚未逐项专项验证。量化滤波会保留源编码自身的误差。损坏流或非法范围会在写入前报错。
- **静态 GPU 实例**：展开无蒙皮的 `EXT_mesh_gpu_instancing`，共享解析后的网格；烘焙每个实例的平移、旋转和缩放，保留形态键与 InNode 子树筛选。验证旋转、镜像缩放及错误四元数；展开后的场景仍受源骨骼/节点数量上限约束。

本轮将“材质重命名合并不支持”从未完成表删除，并缩小 glTF 压缩/实例限制。未认证的游戏表现、Draco、AppID 挂载、动画缩放/权重和复杂 rig 差分仍保留，未以文档修改代替实现。共 127 项兼容回归与 16 项自动发布测试。

## v1.2.2 六项改进

- **Bodygroups**：组合数乘积使用 64 位计算，允许最多 2^31 种组合（body 值 0..2147483647）；31 个二选一组可编译，32 个会在写出前报错。固定单选组不再造成无意义的 preset mask 累加。
- **Skin groups**：在分配皮肤表前检查材质数 × 皮肤数 × 2 字节，应用文件格式及 `$MDLOutputBufferSize` / `$FileBufferSize` 限制；验证 1001 个皮肤及超限不改写已有输出。
- **全局裁剪**：`$UseLegacyClampMethod` 启用跨材质拆分，`$MaxVerts limit [clamp]` 的 limit 控制触发阈值、clamp 控制块大小（最多 65536）。每个 LOD 和 flex 增量随顶点重映射；额外 `_clamped` 身体组共享原组 base 和选项，包括缺失块的 blank，不会让隐藏选项的碎片继续显示。算法采用保守的三角形容量预留，作用于统一后的输出顶点，并非 CE 全部历史行为复刻。
- **复杂动画**：仅被 `localhierarchy` 引用的骨骼及新父骨骼不再被未使用骨骼裁剪/普通折叠丢掉；拒绝将骨骼临时设为自己的父骨。显式 `$alwayscollapse` 仍按原有规则优先。
- **DMX**：在法线合并和表情索引前检查位置、法线、UV、balance、speed 的角点索引数量与范围；扩展有限数值检查到 blendweights、balance、speed，输出具体错误原因。
- **碰撞**：使用 double 累加体积加权质量，防止大 mass bias 产生 NaN；拒绝非正偏置及不可表示的碰撞体积。单刚体 `$collisionmodel` 新增 `$decomposeconcave`，使用已有 VHACD 依赖分解封闭、连通的凹形网格，遵守正值 `$maxconvexpieces`；普通 `$concave` 保持原岛分割行为，v1.2.4 已补齐 ragdoll 分解。

**v1.2.5 修复**：修正完整 Hair QC 被过度严格检查阻止编译的问题。玩家和 NPC 两份原始 QC 均通过编译，分别输出 126 / 124 根骨骼和 572277 个顶点；不修改原始模型。检查实际写入的 bodygroup 基数和预设值，保留诊断。

## v1.2.1 新增功能与修复

- `$UseLegacyStripify` / `-nvtristrip` 使用随源码附带的 NvTriStrip 后端；默认继续使用 meshoptimizer。验证 DX80/DX90、两种 VTX 布局、LOD 和跨硬件骨骼调色板的蒙皮映射。旧算法会移除重复及索引退化面。
- LOD 骨骼替换拒绝循环与冲突，正确解析连续替换；增加 IK 链、驱动骨、骨骼重命名和未使用骨骼折叠的联合输出测试。
- DMX 加载拒绝位置、法线、权重及动画数值中的 NaN/Inf；新增 corrective COMBO/DOMINATE 规则的数值求值测试，尚不代表所有复杂 rig 一致。
- 大位移或超长 RLE 动画自动采用帧编码，超出半精度范围的位置使用 float32；验证 255 帧重复段边界和动画分节。IK/局部层级压缩偏移超过 32767 字节时，在改写输出文件前报错。
- PHY 的长表面属性、根骨名称及合并名称不再被 512 字节临时缓冲截断。
- 动画压缩的范围扫描改为连续访问姿态。128 骨骼、1800 帧专项测试的三次运行中位数从 118.1 ms 降至 109.5 ms，四个输出文件 SHA256 一致；这是压缩阶段的局部测量。

NvTriStrip 来源与移植说明见 `libs/nvtristrip/SOURCE.md`；六项课题的验证范围及剩余工作见 [RESEARCH.md](RESEARCH.md)。

## v1.2.0 新增验证与优化

- SMD/VTA 按行读取，去掉整文件的重复缓冲；拒绝无效父骨、非有限坐标以及越界/负权重，修复超过 16 个骨骼权重时的越界读取。
- 网格分割使用稀疏映射与已分配顶点标记。9000 顶点、分割上限 3 的专项测试从 300.7 ms 降至 15.8 ms，四个输出文件逐字节一致；这是极端小分割测试，不代表所有模型都获得同样提速。
- 实测编译 181,271,943 字节（172.88 MiB）、240 万条实际顶点记录的 VTA；加载优化后的峰值工作集从 880 MB 降至 376 MB，输出逐字节一致。`tests/stress_vta.py` 可独立复现。
- 已验证 130 个输出材质、512 个源骨骼折叠、256 个输出骨骼及最高编号骨骼动画；256 骨骼改用帧动画编码。**512 个最终输出骨骼仍未实现**：标准 MDL/VVD 有 8 位骨骼索引，超过 256 会在写入前明确报错。
- 增加 DMX 多骨骼形态键、网格分割后的 flex/LOD 和碰撞重命名/父子关系回归。用户提供的极限模型已成功编译：126 骨骼、572277 个 VVD 顶点；后续 v1.2.6/v1.2.7 已补充 GMod 几何与物理验证，材质验证仍缺资源。
- 自动发布递增补丁版本，修复旧版标签识别。调查结果及尚未解决的课题见 [RESEARCH.md](RESEARCH.md)。

## 未完成与已知问题

以下按 v1.2.8 的实现及已有验证记录整理；“未验证”表示测试覆盖不足，不表示该功能尚未实现。

| 内容 | 当前状态与剩余工作 |
| --- | --- |
| 五者整合缺口 | CE replacemesh 参考语义及 Neko 复杂驱动骨父级仍需对照；RenameMorph 容错和可处理写盘故障回滚已补齐，断电/强制终止恢复未实现。详见 FEATURE_MATRIX.md。 |
| 额外扩展：蒙皮实例与网格切换 | 不作为五者整合的先决条件；尚未支持蒙皮网格的 `EXT_mesh_gpu_instancing`，也未支持动画中的网格切换；静态非蒙皮实例已支持。 |
| 额外扩展：VRM 运行时行为 | 不作为五者整合的先决条件；完整弹簧骨和专有表情映射的运行时语义尚未实现；已有 VRM 导入与默认形态键权重回归不代表完整 VRM 行为兼容。 |
| 导入格式与插值覆盖 | cgltf 与 Assimp 6.0.4 导入已实现，但尚未逐一验证所有 Assimp 格式、复杂 FBX/VRM 层级及后备路径插值。 |
| 复杂 rig 与碰撞覆盖 | 已有 IK、jiggle、驱动骨、corrective、眼睑、联合面部 rig 和按骨骼 VHACD 回归；任意复杂层级、硬边、自定义法线、控制器重映射和复杂碰撞仍需具体模型验证。单骨权重仍属实验功能。 |
| 跨游戏与参考覆盖 | 已验证指定 GMod 样例，其他游戏和材质着色仍需独立测试；尚未覆盖所有参考编译器的语法边界、诊断文本和性能场景。 |

v1.2.8 生产验证改用 Plum：原始 Hair QC 编译及文件结构检查通过；新增材质在 GMod 加载无缺失，28 个截图状态包含身体组、皮肤和表情，18 个布娃娃刚体稳定。首帧增加材质预热后复测通过。后续不再使用 Claudia 作为生产测试模型。详见 [v1.2.8 验证记录](tests/reports/v1.2.8-validation.json)。

已从问题清单移除：Draco/meshopt 解码、采样式缩放/形态键权重烘焙、NvTriStrip 与跨材质分割、动画大位移边界框修复、阶段耗时与输出完整性检查。显式 CE/Neko 面部模式已通过 28 项参考对照；`copy animation weightlist`、`match pos/rot`、条件语句和 `reverse` 已通过七个 StudioMDL++ 姿态/FPS 样例。验证范围见 [IMPROVEMENTS.md](IMPROVEMENTS.md) 和 [v1.2.7 验证记录](tests/reports/v1.2.7-validation.json)。

## 兼容性选择与使用条件

这些是使用条件或有意保留的实现差异，不属于未修复问题。

- 动画烘焙最多 4096 帧、1600 万个源顶点采样，精度取决于采样率；游戏播放需要控制器驱动代码。`gmtime` 的 UTC 同步也需要模组支持。
- 默认 `native` 面部行为保留 PulseModel 语义；需要参考面部策略时使用 `$dmxcompatibility ce|neko`。`$CEBoneRules` 需要显式启用。
- `$MaxVerts` 控制每材质输出网格分割，实际不超过 65536；`$FileBufferSize` 限制各输出文件字节数。本项目使用动态缓冲区与统一 LOD 顶点字典，不复现参考编译器的源文件预拆分或固定预分配。
- `NoAutoDMXRules` 按源禁用自动规则；需要清除先前自动控制器与规则时使用 `NoAutoDMXRulesLegacy`。`addcontrollerbyflex` 正确处理 min/max，不复现参考二进制的范围解析缺陷。
- 输出为 v49，参考 CE/++ 为 v48；不承诺完整文件逐字节相同。原有 `copy pos/rot` 属于本项目扩展。
- 自动同步合并 PulseModel 源码，冲突或测试失败会停止发布。CE/++ 更新由用户提供后手动分析与实现；VBSP、VVIS、VRAD、BSPZIP 地图工具不在本项目范围内。

完整语法与差异见 [COMPATIBILITY.md](COMPATIBILITY.md)，二进制调查记录见 [BINARY_ANALYSIS.md](BINARY_ANALYSIS.md)。

## 编译源码

Windows：在 Visual Studio 2022 的 x64 开发者终端中，准备 CMake 3.22+ 和 Ninja：

```powershell
cmake --preset x64-release
cmake --build --preset x64-release
```

输出位于 `out/build/x64-release/NewPageMergeMDL/`。

Linux：准备 CMake 和 C/C++ 编译器：

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
```

依赖库已包含在 `libs/`，无需额外包管理器。GitHub Actions 已同步新的名称和打包路径。

## 使用

```powershell
NewPageMergeMDL.exe model.qc -game "C:/Games/MyMod" -vtxformat 1
NewPageMergeMDL-Decompiler.exe model.mdl -smdanimation
```

`.qc` 和 `.pulseqc` 输入扩展继续支持。内部 `pulse` 命名空间保留，避免破坏已有代码接口。

## 测试

```powershell
python tests/compatibility.py out/build/x64-release/NewPageMergeMDL/NewPageMergeMDL.exe
```

146 项兼容测试使用临时 SMD/QC 和自制 DMX，检查实际 MDL/VVD 文件，并反编译动画验证位移、旋转和分支行为；另有 20 项自动发布测试。

已成功编译用户提供的 Alyx QC（113 根骨骼、27,571 个 VVD 顶点）。v1.2.4 另完成 GMod 几何、表情/眼睑与 LOD 验证。

## 来源与许可

原项目作者：Toppi。保留原 [MIT LICENSE](LICENSE) 与第三方库版权声明。
[UPSTREAM_README.md](UPSTREAM_README.md) 保存上游说明，含旧程序名称和旧下载地址，仅供参考。
本项目没有包含 StudioMDL-CE 或 Tools++ 的闭源二进制或源码。
