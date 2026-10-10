# 五编译器功能整合清单 / Five-compiler integration checklist

目标：以 PulseModel 为源码基础，将 CE、NekoMDL、StudioMDL 2013、StudioMDL++
可用的模型编译功能整合到 NewPageMergeMDL。版本：v1.2.27。

发布采用每个平台一个完整 ZIP，安装及更新均完整解压到新目录，见 [INSTALL.md](INSTALL.md)。Windows 包含 C4D 桥接程序；Windows/Linux 均包含主程序、反编译器、辅助工具、独立 VRML 转换器及其对应源码、准备脚本与 GMod Lua 模块，以及文档、许可、`upstream-manifest.json`、`SHA256SUMS.txt` 和 `tests/reports/`。自动上游合并版内嵌 `sources/NewPageMergeMDL-source.zip`；手动维护版完整源码来自发布标签。Linux 的 C4D 输入仍须先在 Windows 转为 GLB；Python 脚本仍需自行安装 Python 3。单包化与体积优化均不扩展下表的游戏运行时认证范围。

v1.2.26 发布构建及 `x64-compact` 预设采用 `MinSizeRel` 与 IPO/LTO，保留全部导入器和工具。安装包运行目录中的 tinyusdz 仅保留 `LICENSE`、`LICENSE-APACHE-2.0`、`SOURCE.md` 和 `THIRD_PARTY_NOTICES.md`，省去运行无需的源码与开发图片；完整项目源码的获取规则不变，GPL VRML 转换器对应源码继续随包附带。Windows C4D 使用原先已验证的 helper。Plum 与 viewarms 的本地模型输出逐文件一致，最终体积与验证范围见 [验证记录](VALIDATION.md)。

v1.2.25 修复真实手臂 QC：VRD 短名父骨在折叠时同步解析并重算姿态；共用皮肤表的未使用基材质列警告后跳过，保留实际使用的替换与全部行。CE 会保留未使用的皮肤材质登记，本工具继续裁剪；详见 [验证记录](VALIDATION.md)。

v1.2.24 仅精简 Release 链接产物，保留五编译器固定功能范围及全部导入器；不改变下表中的功能状态和已知兼容边界。

这份表按需求来源追踪功能，不以测试数量或基础设施数量代表整合完成度。
“已实现”指存在实际编译路径；“有差异”表示实现策略或默认值不同；
“待确认”表示资料不足或参考程序未复现。未列出的历史缺陷不能自动算作已修复。
兼容性测试通过也不等于所有格式、模型、游戏均通过。

本轮五编译器 R/E/V/S/O 固定总账及 H 边界见 [FIVE_COMPILER_COMPLETION.md](FIVE_COMPILER_COMPLETION.md)。所有已知类别均在该表结账；未公开参考信息保留未知，不伪装兼容。

本轮 CSGO 固定范围 A1–A7/B1–B4 共 11 包已全部完成；原可选扩展 B 区已获授权并交付。完整范围与排除项见 [CSGO_PORTING_SCOPE.md](CSGO_PORTING_SCOPE.md)，新增布料语法见 [CSGO_CLOTH_AUTHORING.md](CSGO_CLOTH_AUTHORING.md)。

## 需求来源 / Requirement sources

| 来源 | 核对依据 |
| --- | --- |
| PulseModel | 固定基线 `52cf296a953fd6c2d072e34cfde5eb8eccc95564` 的源码及 UPSTREAM_README.md；持续通过维护补丁合并更新。 |
| StudioMDL-CE | 用户提供的 0.3.0 命令指南、changelog 和参考程序；见 COMPATIBILITY.md 与 BINARY_ANALYSIS.md。 |
| NekoMDL | 用户提供的中文版 ChangeLog.txt v2.3.0、NewCommands.qci 和参考程序。历史版本条目按当前行为复核，不能假定旧实现仍有效。 |
| StudioMDL 2013 | [Cra0 原始页面](https://cra0.net/blog/posts/archived/2014/studiomdl-2013/)。2012 libs / 2013 两包的 EXE SHA256 相同，作为同一来源；不同依赖配置单独记录。 |
| StudioMDL++ | [Tools 页面中 StudioMDL++ 的专属 Changelog](https://ficool2.github.io/HammerPlusPlus-Website/tools.html)，以及用户提供的 Oct 3 2026 参考程序。其他工具的条目不能算作 StudioMDL++ 需求。 |
| CSGO Source1 补充移植 | 参考树 `f82112a2388b841d72cb62ca48ab1846dfcc11c8` 的活跃编译与 FE 构造路径；v1.2.22 的 11 个固定功能包见 [完成清单](CSGO_PORTING_SCOPE.md)。其底层能力扩展不计作第六个“五编译器”需求来源。 |

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
| SMD 读取与编译性能 | 已有快速按行加载及专项优化；修复规则网格顶点在 MSVC 哈希桶的严重碰撞，保持首次出现的顶点顺序。相对 ++ 的整体提速幅度未确认。 |
| 顶点/材质/网格/动画容量与输出缓冲 | 动态容器与分割已实现，具体格式字段有边界；不是固定 32 MB 分配。 |
| AppID 资源挂载 | 已实现 resources.cpp：Steam 安装路径、gameinfo 搜索顺序及 VPK。 |
| `-nodx80`、取消 SW VTX、未使用材质清理 | 已实现。 |
| `reverse`、`match pos/rot`、`copy`、动画条件 | 已实现；copy 命名 weightlist 等七个姿态/FPS 对照通过。原生 copy 通道扩展另有语义。 |
| 宏默认值、`$endmacro`、全局变量回退 | 已实现；v1.2.13 恢复传统单/双反斜杠续行宏。重复宏报错、重复变量警告与 `$setvariable` 已实现。 |
| 数字 contents、可选 activity weight/attachment offset | 已实现 QC 解析。 |
| `-noremap`、`-cullanims`/`nocull`、`gmtime` | 已实现；UTC 播放需模组支持。 |
| 选择网格计算 bbox、大位移边界框 | 已实现；v1.2.23 增加首个越界骨/零基帧/位置和有适用条件的 skipboneinbbox 提示，触发当前世界坐标范围裁剪。 |
| cmdlist 容量检查、缺失 weightlist 骨骼警告 | 动态命令列表及语法校验已实现；不复刻参考固定数组上限。 |
| 源骨骼、扩展名省略、权重阈值 | 源容量保护、碰撞/LOD 扩展名解析已实现；新增显式 $boneweightpolicy native|neko|ce，见固定总账 S1。 |
| 强制折叠和各类依赖骨骼保留 | v1.2.27 默认保留有权重的骨骼及父骨链，修复外部驱动手臂的前臂/手指误删；显式折叠模式和 `$CEBoneRules` 的优先级语义保留。证据范围见 VALIDATION.md。 |
| 骨骼重命名/碰撞、空身体组、超量网格等修复 | v1.2.23 按固定 V5 六类输入验收；不以有限用例宣称任意历史崩溃均等价。 |

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
| `$lod replacemodel ... reverse` | **v1.2.12 补齐**：静态控制流及三组 CE 输出确认，反转替换 LOD 绕序、保留法线、隔离共享源。 |
| `$lod replacemesh` | **待确认**：日志列为修复，但提供的 0.3.0 二进制未识别本轮候选用法，x86/x64 均未找到命令字符串，x64 LOD 分支已反汇编核对；后续仍未发现公开语法、源码实现、Issue 示例或发布资产。不能猜成 replacemodel 别名。现有 replacemodel/replacematerial 不受影响。 |
| `$DontDestroy` / `-DontDestroy` | **v1.2.8 接入**默认不清理输出策略；编译/预检失败保留既有输出。v1.2.9 增加检查写入及可处理故障回滚，目录冲突/Windows 文件锁回归通过；不保证断电或强制终止恢复。 |
| 历史 VTA/DMX、分割、LOD、缩放缺陷修复 | 多 VTA、默认姿态、flex 重映射等有对应实现/回归；其余历史修复仍按具体输入核对，不仅检查开关存在。 |

## NekoMDL：按中文日志核对

| 功能组 | 状态 / 当前路径 |
| --- | --- |
| glTF/GLB/VRM、FBX 与 Assimp 场景格式 | 已实现导入，含无 UV/形态键法线；尚未逐格式验证所有 Assimp 格式。FBX 使用 ufbx；v1.2.11 保留 Assimp glTF 几何导入并用原始采样器修复 STEP/CUBICSPLINE，glTF/GLB/VRM 双后端数值检查通过。 |
| 场景节点、蒙皮、形态键、动画、LOD | 已实现；InNode、Pick、SampleRate、FPS、按后端 UpAxis 与缓存已接入。 |
| `$NekoModel`、named flex/flexpair、眼球/眼睑 | 已实现；多 studio 面部作用域与显式 Neko 面部策略已测试。 |
| `$NekoDriverBone`、jiggle 轴向、NoBoneRealign/AppendScale | 已实现；v1.2.10 修复动画父级及不同姿态层级，6 组参考数值对照和 12 组命令顺序回归通过；任意 rig 全面一致不作保证。 |
| `$RenameMorph`、`$PreRenameMaterial`、舍弃形态键法线 | 已实现；RenameMorph 早于本轮已在基线源码中存在，旧表漏记。v1.2.9 在显式 neko 模式补齐导入原名映射、缺失忽略、大小写敏感、不连续映射及命名 flex 筛选；native 行为保留，目标重名明确拒绝。 |
| 顶点/flex/材质/skin 容量、MaxVerts/MaxBones/FileBufferSize | 已实现动态容器与预算；部分默认值/裁剪阶段不同，见 COMPATIBILITY.md。 |
| 行条件、变量、可选 include、assert、消息 | 已实现 `$if/$ifdef/$elif/$eldef/$else/$endif`、UndefineVariable、`-D`、iffileexists 等。 |
| 便携输出、modelname/outdir、序列顺序、HLMV/beep | 已实现；默认序列顺序保留策略与 Neko 不同，`-noremap` 可选择 QC 顺序。 |
| OBJ 材质名、科学计数、大小写扩展名、中文路径 | 已有导入/数值/路径实现；各平台和格式的完整组合覆盖仍需扩充。 |
| `$prefer_fbx`、`$forcecapsules`、旧 strip 参数 | **v1.2.8 补齐**：前两者按当前参考接受并警告，不改变导入/生成胶囊；`-usenvtristrip` 映射既有 NvTriStrip。 |
| 历史 Blender/FBX SDK 切换与 DLL 配置 | 属于历史实现路线，不作为要求恢复的外部依赖；当前导入器直接编译源模型。 |

## 运行时后续核验 / Runtime follow-up verification

| 目标 / 项目 | 结果与边界 |
| --- | --- |
| L4D2 2.2.4.3 build 10097 网格状态 | 标准 `prop_dynamic` 可创建 `states/avatar/basic` 并消费 `mesh_state` bodygroup（初始 `1`，`SetBodygroup(0, 2)` 可切换到 `2`）。三个实体均无 `m_flexWeight`，因此不能宣称标准实体消费顶点表情；需要 `CBaseFlex`、引擎扩展或游戏专用接口。 |
| CE `replacemesh` | 后续仍无公开语法、源码、Issue 示例或发布资产；继续证据不足，不能作为 `replacemodel` 别名。 |
| Neko 固定二进制格式 | 提取的 64 个扩展名均已覆盖现有登记集合，未发现新的格式入口。 |
| Insurgency 游戏内模型加载 | 仍无可靠读回证据，未认证；历史 QC 编译/结构检查不等于运行时兼容。 |

详细记录见 [v1.2.23 后续运行时报告](tests/reports/v1.2.23-followup-runtime.json)。

## StudioMDL 2013：同一程序、不同依赖配置

| 页面公开能力 | 状态 |
| --- | --- |
| 材质容量提升 | 当前 130 材质输出专项通过；页面未给出具体新上限，不能据此宣称完全相同。 |
| 大 VTA | 172.88 MiB、240 万条真实顶点记录已编译并检查输出。 |
| 页面第三项容量声明与运行依赖 | 既有调查结论保留在 RESEARCH.md，不重复开启已讨论的格式限制课题。v1.2.23 已用2012包隔离bin依赖恢复同EXE；130材质拒绝、255骨通过/256以上拒绝、大VTA9000移动顶点通过/30000移动拒绝。CSGO DLL配置另记访问违例。 |

## 固定清单结账 / Fixed integration ledger

R/E/V/S/O 已统一纳入 [完成总账](FIVE_COMPILER_COMPLETION.md)，不再保留旧的“后续顺序”。
`$qccompatibility`、`$fbxcompatibility`、`$boneweightpolicy` 是显式策略；材质/面部/分割/LOD组合、九类骨规则、2013依赖恢复及有限性能对照已有固定证据。
独立扩展现有有限拓扑播放器、VRM客户端、蒙皮实例、恢复journal与额外格式路径；运行适配不是未经修改引擎的原生能力。
CE replacemesh及闭源未公开精确格式集合继续标为证据不足，需要新资料才改变结论。CSGO固定11包保持关闭。

English: the tables track advertised compiler capabilities separately from project
extensions. Existing implementations, intentional differences and unresolved
reference evidence are not interchangeable. The first v1.2.8 integration batch
restores legacy Neko script acceptance, its old strip switch and CE DontDestroy acceptance; it does not claim
complete five-compiler parity. The two 2012/2013 archives count as one compiler.

The v1.2.9 batch adds explicit Neko morph mapping and checked output staging/rollback. Power loss and forced termination recovery are not guaranteed.

The v1.2.10 batch resolves sampled Neko driver/helper world poses against model bind parents and isolates pose-only skeleton ownership. Six reference cases pass; this is bounded rig evidence, not universal parity.

The v1.2.11 batch retains Assimp geometry while sampling original glTF animations; STEP and CUBICSPLINE loss is fixed. Other-format interpolation and complex hierarchy coverage remain open.

The v1.2.12 batch recovers and implements CE replacemodel reverse from binary control flow and actual reference outputs; the separately advertised replacemesh entry remains unresolved.

## v1.2.13：实际游戏 QC 兼容修复

叛乱 2 / 军事冲突：越南的原始 QC 编译及输出结构检查通过：传统续行宏、改名后附件/命中盒/hitgroup 引用、仅大小写骨骼改名已修复。游戏内渲染/物理仍未在这两款游戏验证；不是新增的五编译器行为全覆盖声明。

## v1.2.14：CSGO QC 指令补齐

`$preservetriangleorder` 已接入统一 VTX 输出：跳过缓存/过度绘制/NvTriStrip 排序，保留参考边遍历顺序。32 面自制 CE 顺序对照、两种 VTX 格式及 LOD/legacy 组合通过；Yvette 用户 QC 与 Plum 编译及结构检查通过。不宣称全局源面顺序或所有模型与 CSGO 游戏内行为一致。

## v1.2.15：此前 33 个 CSGO 缺失入口的逐项处理

v1.2.15 当时补上 31 个入口，剩余 `$cloth` / `$clothplanecollision` 两个入口当时未实现；v1.2.19 新增下文列出的限定 FE 路径。支持入口中包含 reference warning-only 的 `$externaltextures`、无纹理处理用途的 `$gamma`，以及既有 native LOD 蒙皮行为的 `$skinnedLODs`；不能据此称为 31 个新算法。`$insertbone` 只执行参考中启用的 reparent 行为，v1.2.15 的 `$subd` 当时仅提供全局 header flag，完整 quad/SubD 导入当时尚未实现；v1.2.20 的新路径见下文。详细语法/行为差异见 COMPATIBILITY.md，全部 33 个名字与状态记录于 tests/reports/v1.2.15-validation.json。

新增 controller、runtime bone flags、prefix/substr alias、reparent/realign/center、bbox/UV/tangent、collision grid、source append、attachment/bodygroup、CONTENT、naming、no-sequence、strict remap 和 in-memory OBJ VTA/VCA 输出回归。181 项完整兼容、20 项自动化测试及 Plum/Yvette 编译结构检查通过；未取得 CSGO cloth 或游戏内行为验证，不宣称全面 CSGO 移植。

Historical v1.2.15 next step was real FE cloth and plane data. v1.2.19 added that core; v1.2.20 extends its settings and adds native quad/SubD geometry. Remaining limits are listed in the latest section below.

## v1.2.16：目标游戏 VTX 布局 / Target-game VTX layout

CSGO legacy / MCV 的 `gameinfo.txt` SteamAppId 自动选择扩展布局，CLI / QC 显式选择保留。旧布局造成的指定模型加载崩溃已修复；不要混装 MDL 和旧 VTX。七份模型经对应 HLMV 监测，实际角色与引用动画经观察，并记录游戏内限定场景；详见 tests/reports/v1.2.16-validation.json。布料、完整 SubD 和其他既有未完成项不因本轮加载修复而标为完成。

## v1.2.18：CONTENT 与 CSGO LOD 权重

CONTENT 通配符、VPK 和分卷查找已补齐，并保留按需启用和查找优先级。CSGO AppID 730 默认按根模型最近顶点传递低 LOD 权重，`$skinnedLODs` 保留作者权重；其他目标保持原行为。187 项兼容回归、6 项专项及 Plum/Yvette 编译结构验证通过。v1.2.18 当时尚未完成复杂组合下的容差匹配与骨骼折叠全面对照、FE 布料及原生 quad/SubD 输出，不以这两个子功能替代全部移植。

CSGO / MCV 目标还修正为 256 字节扩展头，保留 FE 指针槽（v1.2.18 当时为零），身体组预设写入正确偏移；其他目标保留原布局。两款游戏的预设样例分别通过 15 秒 HLMV 调试器监测，无访问异常，临时游戏文件已清理。这是布料序列化前置修正，不代表 FE 布料功能完成。

## v1.2.19：真实质量、附加碰撞源与限定 FE 布料

本节保留 v1.2.19 当时的实现与验证；当前扩展和限制见下文 v1.2.22 及固定范围清单。

| 功能 | v1.2.19 当时状态与剩余范围 |
| --- | --- |
| `$automass` / `$calculatemass` | 已实现按挂载的 density/thickness 计算总质量；manifest、VPK/分卷、base 继承、重复定义覆盖、骨骼 surfaceprop 与 MDL/PHY 总质量一致。保留参考的 volume×massbias 分配及每刚体 1 kg 下限。 |
| `$addconvexsrc` | 已实现 quoted offset 的位置/角度/缩放、活动源缩放补偿、独立源副本和 concave 标记；全局 `$concave` 下合并标记源后跨文件焊接，未启用时合为单凸体；`$collisionjoints` 忽略附加源。offset 依据历史源码，安装的原版会警告并忽略 offset，未声称原版二进制/VPhysics hull/drag 等同。 |
| `$cloth` | 已实现 CSGO AppID 730 骨骼目标的显式 cloth_enable 三角形/四边形 DMX 代理、固定点、FE 元素及加权控制骨回算和扩展头序列化。上限 4096 代理点；按 `$cloth` 指令当时的 scale 导入；锚定连通分量、单骨固定点、分离固定/动态控制骨及非共线拟合要求明确检查。 |
| `$clothplanecollision` | 已实现骨骼绑定的无限单面碰撞平面；每面要求共面且同骨绑定，同一 DMX 的多个网格分别选择各模拟点前方最远的有效平面。不是有限三角形碰撞网格。 |
| 布料剩余项 | v1.2.19 当时拒绝 settings 块、未知 maps 和其他游戏目标；没有动态游戏内布料运动认证，也没有完整 CSGO 布料行为/逐字节等同声明。 |
| 原生 Quad/SubD | v1.2.19 当时未实现完整导入与 patch topology；FE 四边形代理不等于渲染网格的 SubD 输出。 |

209 项兼容回归、20 项自动化回归通过，包括 6 项质量、6 项附加碰撞源和 10 项 FE 专项，另有 6 项 CONTENT 挂载回归通过。quad/tri 含 plane 样例各经 CSGO HLMV 15 秒检查，无访问异常；6 个临时游戏文件全部清理。Plum 原 QC 哈希不变，隔离编译/结构检查通过，MDL/PHY 总质量均为 30 kg。HLMV 加载、输出结构及旧版本游戏记录不替代本版动态布料游戏验证。

原版 CSGO 默认材质四面体边长 10/20 的总质量为 5.462355/43.698837 kg，与当前工具相同到打印 6 位小数。同几何布料对照确认固定节点、逆质量、2 个固定偏移和 4 个平面约束一致（法线仅有浮点误差）；stock NodeBase/ReverseOffset 与当前加权 FitMatrix 回算不同，变形等价仍未验证。

## v1.2.20：FE 扩展、Quad/SubD 烘焙、DMX rig 与动画求值

本节记录 v1.2.20 的历史范围；表中的拒绝项只描述该版本，后续扩展见下文 v1.2.21/v1.2.22。`flex_borders`、`prerotate`、混合骨拟合及固定点多权重现已由 v1.2.22 完成。

| 功能 | v1.2.20 当时实现 | v1.2.20 当时边界 |
| --- | --- | --- |
| FE 设置与弯曲 | `$cloth { ... }` 写出局部响应、拉伸、重力、风力、阻力及速度平滑参数；共享边产生 scalar/SIMD 杆，支持曲率范围和刚性轴向铰链。新增动画位置/力吸引及目标偏移。 | 当时要求 4096 代理点内、锚定连通分量、单骨固定点、分离固定/动态骨及非共线拟合。`flex_borders`、`prerotate`、`cloth_use_rods`、`cloth_anchor_free_rotate` 在 v1.2.20 尚未支持，已由 v1.2.21/v1.2.22 接入。非零速度平滑率启用一次迭代，与参考 QC 默认零迭代有意不同。 |
| FE 碰撞与零重力 | 新增 ground 参数分组、节点半径、碰撞树掩码；`world_collision` 启用世界 sphere/capsule flags。`gravity_scale 0` 编码为节点 gravity=0、descriptor scale=1，避开引擎旧默认值回退。 | 世界球体/胶囊需要运行时提供碰撞体，不等于编译器已生成这些形状；plane 仍为无限单面平面。仅 CSGO AppID 730 骨骼模型/扩展 VTX。 |
| Quad/SubD | `$subd`、`$model ... subd` 或 DMX `subdivisionSurface=true` 默认两轮 Catmull-Clark 烘焙普通三角形；`$subd levels 1..3` 调轮数，传播蒙皮/位置 morph、保留 UV 接缝并重算法线。`$subd native` 显式输出原生 patch。 | 烘焙要求 authored quad，每源最多 262144 refined quads；拒绝非流形、冲突焊接权重/morph、normal-only morph及融合部件身份。原生模式仅供可用的SubD renderer：已测CSGO legacy/HLMV会崩溃并有编译警告；要求扩展VTX、每mesh/LOD≤8192 patches、valence≤16、每patch≤52环引用，不接受levels。 |
| CSGO 多目标 rig | `$datamodeljoints rig.dmx proceduralbones` 或全 rig 导入 Point/Orient/Aim/Parent，按多个目标、权重、偏移、base pose、Aim up 和骨骼依赖逐帧烘焙普通骨骼动画；支持保骨、改名和 realign。 | 限 CSGO 骨骼目标。引擎忽略 8/9/10/12，记录仅作元数据，slave 不设 ALWAYS_PROCEDURAL。烘焙在 QC 动画操作之前，不会随运行时 IK/混合或后续 QC 修改重算。Twist、reverse、raw delta、运行时程序骨依赖、centerbonesonverts组合、缺骨、非法权重、依赖环及冲突报错。 |
| DMX 动画求值 | 当前 DmeChannelsClip 的多跳 Connection、Expression、Vector/Quaternion Pack/Unpack、Transform 算子逐帧求值；处理分层 log、线性/slerp/阶梯采样及 clip 时间变换，烘焙普通骨骼帧，适用于所有目标。 | 不支持的连接算子、curve-type 插值、压缩 log、无效键/类型、环和冲突 writer 报错；不是完整 SFM 求值器。 |

功能回归核对实际序列化数据、SubD 反编译再编译和动画数值。20 点 FE 对照中，stock 与本工具均走 16 权重 FitMatrix，初始化点/逆质量/中心偏移一致，20 条杆仅有浮点误差；单 quad 与 grid 的 SubD 邻域字段亦经归一化对照。此类结构证据与游戏内动态证据分开记录，最终测试与运行场景见 [VALIDATION.md](VALIDATION.md)。

本版最终 Windows 验证：248 项兼容、20 项自动化、6 项挂载测试通过，Plum 原始资产不变。游戏内布料、默认 SubD 烘焙及四类约束烘焙的实际覆盖和限制见 [VALIDATION.md](VALIDATION.md)。


## v1.2.21：绑定碰撞体、布料绑定与动画扩展

本节保留 v1.2.21 的历史实现和验证；本轮完成状态见下一节。

| 功能 | 本版实现 | 明确边界 |
| --- | --- | --- |
| 绑定球体/胶囊 | `$cloth` 块中的 `sphere` / `capsule`；骨局部中心、半径、指令时缩放、保骨/改名/轴重映射；真实 FE rigid collider 数据。 | CSGO 骨骼模型；≤1024 个；禁止绑定动态布料骨和运行时程序骨；近包含胶囊由引擎近似为大球；不保证每帧所有渲染点零穿透。 |
| 稀疏布料与 maps | 单点/双点/共线控制点使用邻接 NodeBase+ReverseOffset；自由旋转固定代理点；指定面改为完整距离杆图并去重。 | 要求非退化邻接；不改变现有有效 FitMatrix；杆面规则补全参考空分支，不宣称完全等同参考 builder。 |
| AxisInterp | legacy `$proceduralbones` 六轴姿态读入和原生程序骨写出，支持保骨/改名、缩放、可表达的轴重映射。 | 依赖排序、父骨匹配和cardinal轴限制；不可表达的变换明确报错。 |
| Twist | DMX parent/child + 多slave、inverse、bind/up参数，按参考求解后烘焙普通动画。 | 不依赖游戏默认关闭的Twist开关；运行时IK/混合和后续QC不重算；reverse rig、原始delta及程序骨依赖拒绝。 |
| DMX曲线/压缩 | Float 0–15曲线，Vector3/Quaternion 0–13/hold；三通道RLE日志输入解码；异常流保留旧输出。 | mode14仅Float；压缩限Vector3/Quaternion；不是任意SFM求值器或新MDL输出压缩。 |

最终测试、原版数值对照、Plum 和游戏验证见 [VALIDATION.md](VALIDATION.md)。

本版最终 285 项兼容、20 项自动化、6 项挂载回归通过；AxisInterp 默认QC/PulseQC/datamodeljoints反编译回环及stock重编译通过。CSGO 1.38.8.1 / 8802 离线 `de_dust2` 已观察 7 个 cloth21 样例加载、多骨变形及移动；零重力、相同可见壳的 4 个 sphere/capsule `contact_on/off` 样例呈现不同碰撞响应。原生 AxisInterp NP/stock 在同步 0.5/1 秒名义相位视觉一致，正向/inverse Twist 的正负方向播放正常，仍为普通烘焙动画。地图重载后，7 个布料、4 个接触对照及 4 个程序骨样例均重新载入。尚未证明逐帧接触、全点无穿透、精确游戏骨角或 stock 全量等价。

## v1.2.22：CSGO 固定 11 包全部完成

| 包 | 已完成能力 | 验证入口与保留边界 |
| --- | --- | --- |
| A1：完成 | 布料/平面代理按自身 Y/Z-up 转换；`prerotate pitch yaw roll` 旋转最终 FE 初始姿态。 | [cloth_scope_cases.py](tests/cloth_scope_cases.py)：主模型/代理混合轴与非零旋转。prerotate 不重建此前生成的局部约束。 |
| A2：完成 | `flex_borders`、固定/动态混合 Fit、固定点多权重、拟合阈值及可调小点云门限。 | 同一 scope 模块检查静态/动态权重分区、运行时中心与稀疏回解；实机观察混合边界变形。默认 flex_borders=false、影响阈值 .05、门限 3，设 8 可采用参考小点云分界。 |
| A3：完成 | quad 顺序/交叉修正、弯曲容差及全动态弯曲面沿短对角线拆分。 | 同一 scope 模块检查 topology/rest shape；退化、非流形和代理锚定要求保留。 |
| A4：完成 | Rotation、两段骨 IK 与 Point/Orient/Aim/Parent/Twist 动画图依赖求值。 | [procedural_scope_cases.py](tests/procedural_scope_cases.py) 及 CSGO Rotation/IK 姿态变化；输出普通烘焙动画，后续 QC、运行时 IK/混合不重新求解。 |
| A5：完成 | QAngle/VMatrix 日志值与 Pack/Unpack 算子。 | [dmx_scope_cases.py](tests/dmx_scope_cases.py)；VMatrix 使用正确的 4×4 输入/输出索引语义，修正参考实现问题。 |
| A6：完成 | DMX flex expression `$变量$` 在 QC 上下文展开。 | [csgo_closure_cases.py](tests/csgo_closure_cases.py)；保留有效规则，无法解析明确报错，替代旧版整条丢弃行为。 |
| A7：完成 | MouthShader texture flags/used 与 VTX `MESH_IS_TEETH`。 | 同一 closure 模块覆盖 skin family、材质重命名及输出标记；既有 `$mouth` 保留。 |
| B1：完成 | 高级双节点 stretch capsule、逐节点 in/out sphere/plane、mask、rigid/stretch capsule stickiness。 | [cloth_advanced_cases.py](tests/cloth_advanced_cases.py)；真实 FE 记录、骨改名/重新对齐及运行样例。逐节点 sphere/plane 不开放运行时不消费的粘附参数。 |
| B2：完成 | 显式 rod/spring、无面 rope 朝向、follow/FTL、质量/倍率、局部响应、体积反馈、平滑迭代、世界半径及 legacy stretch/质量 damping/uninertial/OS offset。 | 同一 advanced 模块及独立多骨绳链实跑；体积反馈需 FitMatrix，世界碰撞需游戏供给碰撞体。局部平移数组保留精确作者值，并处理运行时非均匀响应的入口条件。 |
| B3：完成 | 代理最近表面/双侧体积投射、envelope、连通岛、无蒙皮代理与自动根骨。 | [cloth_projection_cases.py](tests/cloth_projection_cases.py) 检查最终 VVD 权重、两侧比例、错过保留蒙皮及折叠后骨数限制；实机多骨变形。最多三个最终权重，双侧绑定保留每侧贡献。 |
| B4：完成 | Color/String/Time 日志、Color Pack/Unpack、倒放、嵌套 clip 时间映射及 FilmClip/track/shot 输入。 | [dmx_scope_cases.py](tests/dmx_scope_cases.py) 的连接和时间采样数值验证；扩展输入不等于完整 SFM 会话求值器。 |

本版最终 325 项 compatibility、20 项 automation、6 项 mount 验证通过。原始 Plum 隔离编译与结构检查通过：126 骨、572277 顶点、18 个物理刚体、质量 30 kg、65 材质，原始资产保持不变。

10 个布料和 2 个 rig 样例已在 CSGO 离线实跑，观察代理/投射多骨变形、混合边界变形、高级碰撞可见壳与绳链，以及 Rotation/IK 姿态变化。本轮执行 `changelevel de_dust2` 后，10 个布料（READY10）与 2 个 rig（READY2）重新创建并经截图确认；6 项设置恢复并读回核对，正常 `quit` 后进程退出码为 0，62 个登记临时文件经哈希核对后删除。高级碰撞证据仍限于加载/运行与输出结构，未作定量接触效果或零穿透认证。详细记录见 [VALIDATION.md](VALIDATION.md)。

固定排除项为 Source2、引擎运行时 solver、SFM 编辑器、已知崩溃的原生 SubD renderer、参考中未接通或空 TODO 路径、无活跃求解分支的 reverse rig，以及无范围上限的逐帧/逐字节对齐。默认离线 SubD 烘焙和已实现的 inverse Twist 不属于这些排除项。上述边界不再拆成新的待移植批次。

English: v1.2.22 completes all eleven authorized CSGO scope packages, including the four originally optional extensions. The final 325 compatibility, 20 automation and 6 mount checks pass. Ten cloth and two rig fixtures ran in offline CSGO and were recreated and visually confirmed after map reload. Advanced collision evidence remains structural and observational, without quantitative contact guarantees. See the fixed scope and cloth authoring guide for supported inputs and exclusions.
