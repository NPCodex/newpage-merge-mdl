# 五编译器功能整合清单 / Five-compiler integration checklist

目标：以 PulseModel 为源码基础，将 CE、NekoMDL、StudioMDL 2013、StudioMDL++
可用的模型编译功能整合到 NewPageMergeMDL。版本：v1.2.8。

这份表按需求来源追踪功能，不以测试数量或基础设施数量代表整合完成度。
“已实现”指存在实际编译路径；“有差异”表示实现策略或默认值不同；
“待确认”表示资料不足或参考程序未复现。未列出的历史缺陷不能自动算作已修复。
兼容性测试通过也不等于所有格式、模型、游戏均通过。

## 需求来源 / Requirement sources

| 来源 | 核对依据 |
| --- | --- |
| PulseModel | 固定基线 `52cf296a953fd6c2d072e34cfde5eb8eccc95564` 的源码及 UPSTREAM_README.md；持续通过维护补丁合并更新。 |
| StudioMDL-CE | 用户提供的 0.3.0 命令指南、changelog 和参考程序；见 COMPATIBILITY.md 与 BINARY_ANALYSIS.md。 |
| NekoMDL | 用户提供的中文版 ChangeLog.txt v2.3.0、NewCommands.qci 和参考程序。历史版本条目按当前行为复核，不能假定旧实现仍有效。 |
| StudioMDL 2013 | [Cra0 原始页面](https://cra0.net/blog/posts/archived/2014/studiomdl-2013/)。2012 libs / 2013 两包的 EXE SHA256 相同，作为同一来源；不同依赖配置单独记录。 |
| StudioMDL++ | [Tools 页面中 StudioMDL++ 的专属 Changelog](https://ficool2.github.io/HammerPlusPlus-Website/tools.html)，以及用户提供的 Oct 3 2026 参考程序。其他工具的条目不能算作 StudioMDL++ 需求。 |

## PulseModel：保留基础功能 / Preserved foundation

| 功能组 | 整合状态与入口 |
| --- | --- |
| QC、SMD、DMX、FBX，骨骼与动画编译 | 已保留；qcloader、smdloader、dmxloader、fbxloader、compile。 |
| flex、眼球/眼睑、procedural、IK、LOD、碰撞 | 已保留并扩展；对应 compile/write 路径及兼容回归。 |
| meshoptimizer、自动网格分割、动态输出缓冲 | 已保留；CE/Neko 选项复用同一编译管线，不调用外部参考编译器。 |
| 反编译器和附属工具 | 随项目保留；不能用附属工具数量代替主编译器功能整合。 |

## StudioMDL++：按公开模型编译日志核对

| 功能组 | 状态 / 当前路径 |
| --- | --- |
| SMD 读取与编译性能 | 已有快速按行加载及专项优化；相对 ++ 的整体提速幅度未确认。 |
| 顶点/材质/网格/动画容量与输出缓冲 | 动态容器与分割已实现，具体格式字段有边界；不是固定 32 MB 分配。 |
| AppID 资源挂载 | 已实现 resources.cpp：Steam 安装路径、gameinfo 搜索顺序及 VPK。 |
| `-nodx80`、取消 SW VTX、未使用材质清理 | 已实现。 |
| `reverse`、`match pos/rot`、`copy`、动画条件 | 已实现；copy 命名 weightlist 等七个姿态/FPS 对照通过。原生 copy 通道扩展另有语义。 |
| 宏默认值、`$endmacro`、全局变量回退 | 已实现；重复宏报错、重复变量警告与 `$setvariable` 已实现。 |
| 数字 contents、可选 activity weight/attachment offset | 已实现 QC 解析。 |
| `-noremap`、`-cullanims`/`nocull`、`gmtime` | 已实现；UTC 播放需模组支持。 |
| 选择网格计算 bbox、大位移边界框 | 已实现；参考警告阈值和诊断文本仍需对照。 |
| cmdlist 容量检查、缺失 weightlist 骨骼警告 | 动态命令列表及语法校验已实现；不复刻参考固定数组上限。 |
| 源骨骼、扩展名省略、权重阈值 | 源容量保护、碰撞/LOD 扩展名解析与 0.0001 阈值已实现。 |
| 强制折叠和各类依赖骨骼保留 | 已实现 `$CEBoneRules` 显式策略；默认保留 PulseModel 策略，复杂骨骼组合仍需模型对照。 |
| 骨骼重命名/碰撞、空身体组、超量网格等修复 | 对应路径有回归或提前错误保护；所有历史崩溃/输出诊断尚未逐项复现，不按日志标题宣称全面等同。 |

## StudioMDL-CE：命令与算法

| 功能组 | 状态 / 当前路径 |
| --- | --- |
| body/bodygroup 面部块、多 studio、控制器覆盖/重复 | 已实现；显式 CE 面部策略与组合 rig 对照已加入。 |
| 逆向 flex、自动控制器、默认 flex、衰减和缩放 | 已实现 AddInvStudioFlexes/InvertControllers、addcontrollerbyflex、IgnoreDefaultFlexKey、ZeroFlexDecay、DefaqScale/IgnoreDMXDefaq/fscale。 |
| 法线、皱纹和绑定空间重映射 | 已实现全局/局部 compute 与 Ignore 选项、RemapFlexToGlobal；复杂自定义法线仍需实模。 |
| 眼球缩放、瞳孔缩放、眼睑关闭 | 已实现 EyeballScale 及 Ignore 系列；GMod 有限定样例。 |
| `NoAutoDMXRules` 与 Legacy | 两种行为均有实现；native 按源禁用，Legacy 清除先前自动规则/控制器，有意保留差异。 |
| 单骨绑定、碰撞单骨绑定 | 已实现，实验性；不把参考自身的实验功能写成全面认证。 |
| 私有材质重命名/前缀、include 前缀 | 已实现，包含多对一材质合并和 flex/LOD 重映射。 |
| 骨骼前缀折叠、保留策略、hitbox 子骨排除 | 已实现。 |
| 输出路径/缓冲上限、pushd include/procedural | 已实现；采用动态缓冲而非固定预分配。 |
| NvTriStrip 与全局分割 | 已实现；全局分割作用于统一 LOD 字典，非参考源文件预拆分逐字复现。 |
| `$lod replacemesh` | **待确认**：日志列为修复，但提供的 0.3.0 二进制未识别本轮候选用法，且未找到命令字符串。不能猜成 replacemodel 别名。现有 replacemodel/replacematerial 不受影响。 |
| `$DontDestroy` / `-DontDestroy` | **v1.2.8 接入**默认不清理输出策略；编译/预检失败保留既有输出。v1.2.9 增加检查写入及可处理故障回滚，目录冲突/Windows 文件锁回归通过；不保证断电或强制终止恢复。 |
| 历史 VTA/DMX、分割、LOD、缩放缺陷修复 | 多 VTA、默认姿态、flex 重映射等有对应实现/回归；其余历史修复仍按具体输入核对，不仅检查开关存在。 |

## NekoMDL：按中文日志核对

| 功能组 | 状态 / 当前路径 |
| --- | --- |
| glTF/GLB/VRM、FBX 与 Assimp 场景格式 | 已实现导入，含无 UV/形态键法线；尚未逐格式验证所有 Assimp 格式。FBX 使用 ufbx，glTF 使用 cgltf 或 Assimp。 |
| 场景节点、蒙皮、形态键、动画、LOD | 已实现；InNode、Pick、SampleRate、FPS、按后端 UpAxis 与缓存已接入。 |
| `$NekoModel`、named flex/flexpair、眼球/眼睑 | 已实现；多 studio 面部作用域与显式 Neko 面部策略已测试。 |
| `$NekoDriverBone`、jiggle 轴向、NoBoneRealign/AppendScale | 已实现；复杂父级驱动骨仍需具体参考输出。 |
| `$RenameMorph`、`$PreRenameMaterial`、舍弃形态键法线 | 已实现；RenameMorph 早于本轮已在基线源码中存在，旧表漏记。v1.2.9 在显式 neko 模式补齐导入原名映射、缺失忽略、大小写敏感、不连续映射及命名 flex 筛选；native 行为保留，目标重名明确拒绝。 |
| 顶点/flex/材质/skin 容量、MaxVerts/MaxBones/FileBufferSize | 已实现动态容器与预算；部分默认值/裁剪阶段不同，见 COMPATIBILITY.md。 |
| 行条件、变量、可选 include、assert、消息 | 已实现 `$if/$ifdef/$elif/$eldef/$else/$endif`、UndefineVariable、`-D`、iffileexists 等。 |
| 便携输出、modelname/outdir、序列顺序、HLMV/beep | 已实现；默认序列顺序保留策略与 Neko 不同，`-noremap` 可选择 QC 顺序。 |
| OBJ 材质名、科学计数、大小写扩展名、中文路径 | 已有导入/数值/路径实现；各平台和格式的完整组合覆盖仍需扩充。 |
| `$prefer_fbx`、`$forcecapsules`、旧 strip 参数 | **v1.2.8 补齐**：前两者按当前参考接受并警告，不改变导入/生成胶囊；`-usenvtristrip` 映射既有 NvTriStrip。 |
| 历史 Blender/FBX SDK 切换与 DLL 配置 | 属于历史实现路线，不作为要求恢复的外部依赖；当前导入器直接编译源模型。 |

## StudioMDL 2013：同一程序、不同依赖配置

| 页面公开能力 | 状态 |
| --- | --- |
| 材质容量提升 | 当前 130 材质输出专项通过；页面未给出具体新上限，不能据此宣称完全相同。 |
| 大 VTA | 172.88 MiB、240 万条真实顶点记录已编译并检查输出。 |
| 页面第三项容量声明与运行依赖 | 既有调查结论保留在 RESEARCH.md，不重复开启已讨论的格式限制课题。参考启动仍需按两包对应的游戏依赖核对；不得把启动失败当作不支持某功能的证据。 |

## 后续工作顺序 / Next integration work

1. **实际 QC 兼容缺口**：CE replacemesh 的真实语义；Neko 复杂驱动骨父级行为。每项先取得参考输出，再接入统一管线。
2. **导入覆盖**：对 Neko 明确列出的 Assimp 场景格式优先验证真实几何/蒙皮/形态键/动画组合；明确当前后备插值差异并修正可复现案例。
3. **已实现功能组合**：验证面部块、材质重命名、网格分割与 LOD 同时使用；必要的回归用于证明移植功能，不新增无关测试体系课题。
4. **参考环境**：按游戏依赖恢复 StudioMDL 2013 对照，复核页面公开能力；两包只计一个功能来源。

完整 VRM 运行时、蒙皮 GPU 实例和动画网格切换可保留为额外扩展，但当前资料
未证明它们是五者已经提供的独有编译功能，**不能把它们当作整合完成的先决条件**。
游戏验证、诊断、性能和自动发布只支持上述整合主线。

English: the tables track advertised compiler capabilities separately from project
extensions. Existing implementations, intentional differences and unresolved
reference evidence are not interchangeable. The first v1.2.8 integration batch
restores legacy Neko script acceptance, its old strip switch and CE DontDestroy acceptance; it does not claim
complete five-compiler parity. The two 2012/2013 archives count as one compiler.

The v1.2.9 batch adds explicit Neko morph mapping and checked output staging/rollback. Power loss and forced termination recovery are not guaranteed.
