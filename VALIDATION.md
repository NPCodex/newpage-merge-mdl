# v1.2.29 当前验证

本轮修复程序骨碰撞几何被无条件并入父体、物理骨缺少运行时计算标志，以及缺失子体的约束覆盖父体显式轴的问题。显式物理引用参与骨骼保留；实际物理骨和父链补齐 setup mask；显式合并、跳过和强制折叠仍有效。

- 本地 Windows x64 **394 项兼容回归、30 项自动化及 10 项固定 helper 分发测试通过**。新增回归覆盖独立程序骨、collision-only 骨、父链、合并目标、静态模型及约束优先级，不替代最终发行包或其他平台检查。
- 原始 Plum `playermodel_f_compile2_hair.qc` 使用正确 GMod gameinfo 和隔离输出，无须编辑 QC/QCI/DMX 即生成 **21 个刚体**，恢复 `hair_0_1/2/3` 独立碰撞体。131 骨、572,277 顶点通过输出结构检查；131 个登记源文件散列未变，249 个材质文件与游戏安装内容一致。
- **对照边界：** 官方 CE `0.2` 标签 `3149dcb` 对原始 Hair1 输入生成 18 个刚体；同一输入副本追加头发骨 `$bonemerge` 后为 21 个，证明已保留程序骨可以拥有独立刚体。Hair0 对照同样为 21 个。本版主动保留显式物理依赖，不宣称与 CE 默认裁剪结果相同。CE 主分支 `a901817` 的程序 banner 为 `0.3.0 (Preview)`，不是正式发布标签。
- 与 CE 0.2 保留骨对照按骨名匹配的 **20 个关节约束逐值相同**，Head1 保留 x ±50°、y ±20°、z -26°/30°，三根头发分别保留三轴 ±30°。头部体积由旧版 1174.147583 降为 459.116486 立方英寸（CE 458.890137）；每根头发为独立 8 点、12 三角形 hull。
- **GMod 实机：** 引擎 `2026.10.10`、`gm_flatgrass`，CE 保留骨对照／旧版／最终修复版分别运行普通 ragdoll 和 NPC 死亡 ragdoll，各观察 20 秒。6 个场景零记录错误，最终最大速度均为 0；修复版最大水平位移为 **35.49 / 74.32 Source 单位**，CE 为 **36.68 / 81.92**。相同尺寸、相同相机参数的三视口显示服务器实际碰撞网格及记录的冻结姿态：旧版为拉长的头部凸包，CE 与修复版为头部加 3 个独立头发体。此证据限该模型和场景，不证明所有布娃娃永远稳定或逐帧等价。
- 原始 `viewarms_compile.qc` 在最终修复版与 v1.2.28 生成的 MDL、VVD、DX80／DX90 VTX **逐字节一致**，仍为 55 骨、214,697 顶点；保留前臂、手指和程序骨关系。
- **Windows 完整包：** llvm-mingw 20260922 UCRT x86_64 的 MinSizeRel + ThinLTO 全工具构建通过。直接解压并运行包内程序，通过 394 项兼容回归、7 项 C4D 测试、VRML 转换/编译、AG2 启动/版本及来源/清单检查。C4D 沿用固定已验证 helper。精简版主程序 SHA256 为 `8bcf346db308e8398f2a32ab12452f6285700a512667e89c28bf84be089c7c57`；同名隔离 Plum 的 5 个模型文件与已运行 GMod 的候选产物逐字节一致，手臂 4 个文件与 v1.2.28 逐字节一致，131 个源文件未变。该结论限这些输入，不表示所有优化配置输出均逐字节相同。
- **平台限制：** [GitHub Actions 发布运行](https://github.com/NPCodex/newpage-merge-mdl/actions/runs/38269374215) 因账户付款/额度限制在执行步骤前被阻止，并非编译或测试失败。v1.2.29 尚未构建或发布 Linux 二进制；不能沿用旧版本验证作为本轮 Linux 证据。Windows 包内附精确提交源码、来源清单与校验和。

游戏测试使用独立临时 addon，结束后核对删除任务文件并恢复保存的游戏设置；模型、参考程序及截图只保留本机，不随源码或 Release 分发。机器可读摘要见 [v1.2.29-validation.json](tests/reports/v1.2.29-validation.json)。历史验证保留如下。

## v1.2.28 历史验证

合并 PulseModel 从 `52cf296` 到 `578e86e38fde086ccfb701d96688817a77e718de` 的 18 个提交：序列包围盒优化及 `-legacysequencebounds` 回退、DMX/QC 物理图元、attachment 继承、共享 DMX/KV3/zstd 库和实验性 CS2 `ag2proportions`。保留维护版的骨骼保留策略、CSGO 范围诊断、顶点动画边界和 SubD 往返支持。

- 本地 Windows x64 llvm-mingw 的 MinSizeRel + ThinLTO 静态构建通过 **389 项兼容回归、30 项自动化、10 项固定 helper 分发测试**。新增测试检查实际包围盒、物理 hull 几何/体积、attachment 矩阵及二进制/文本 SubD 的四边形、控制点、法线和 UV。
- 修复合并时 `$bboxonlyverts` 与快速算法组合产生空范围的问题：该选项自动使用精确顶点计算。普通快速算法产生保守范围，可能比传统算法更大；可用 `-legacysequencebounds` 对照。范围诊断和烘焙顶点动画边界回归通过。
- 原始 `viewarms_compile.qc` 与 Plum `playermodel_f_compile2_hair.qc` 使用正确 GMod gameinfo、隔离输出分别执行快速/传统两种路径。手臂 **55 骨、214,697 顶点**，Plum **131 骨、572,277 顶点**；与 v1.2.27 的骨层级、flags、bind pose、程序骨参数、几何及具名权重逐值相同，快速序列范围包住传统范围。50 个登记输入散列未变；这不是所有资源文件的完整清单，也不据小样本宣称普遍加速。
- `ag2proportions --help` / `--version` 独立启动通过，版本为 **1.2.28**；补齐 MinGW Unicode 入口、静态运行库、包内许可和 Linux 子工具执行权限检查。它仅为实验性 **CS2 AnimGraph2** 工具；本轮没有执行完整 CS2 Workshop Resource Compiler 工作流，不能视为 GMod/CSGO 手臂修复功能。
- 本地完整 Windows ZIP 解压后，包内二进制再次通过 **389 项兼容回归、7 项 C4D 测试**，VRML 转换/编译、AG2 启动/版本、包清单与许可验证通过。刷新后的 overlay 通过一致性检查；`prepare --force` 从新上游重建的 **2,661 个构建源码文件**与维护仓库一致。

本轮没有新增游戏内验证，v1.2.27 实机证据仍为历史记录。C4D helper 沿用已验证的固定发行文件。Windows/MSVC 与 Linux 最终包由各自 GitHub Actions 构建及实际包回归门槛验证，不套用本地二进制散列。机器可读证据见 [v1.2.28-validation.json](tests/reports/v1.2.28-validation.json)。

## v1.2.27 历史验证

正式发布 [v1.2.27-r1](https://github.com/NPCodex/newpage-merge-mdl/releases/tag/v1.2.27-r1) 的 Windows/MSVC 与 Linux 云端构建、381 项模型回归及实际包验证通过（[运行记录](https://github.com/NPCodex/newpage-merge-mdl/actions/runs/38036357921)）。下载的 Windows 正式包再次编译原始手臂及 Plum，产物与完成下述游戏验证的本地构建逐文件 SHA256 相同，输入未变。完整 ZIP 为 Windows **7,239,882 字节**、Linux **4,748,043 字节**；全部工具保留，包内清单及来源哈希已验证。

本轮修复用户原始 `viewarms_compile.qc` 的运行时手臂变形。旧版默认把本地 idle 不动的加权骨折叠：CE 为 **55 骨**，v1.2.25/26 仅 **17 骨**，丢失双侧前臂、锁骨、30 根手指骨和 4 根袖末端骨；前臂及手指权重被移到其他骨骼。默认策略现保护加权骨及祖先，无需修改原始 QC/QCI/VRD。明确指定的裁剪模式仍可折叠。

- **381 项兼容、26 项自动化回归通过**。新增测试检查最终骨层级及 VVD 的实际具名权重，覆盖无动画、静止动画、引用动画、QC/PulseQC、低 LOD 使用骨、显式裁剪、CE 例外及非骨骼 mesh DAG。
- 修复版与 CE 均为 **55 骨**，名称、父级和 flags 全相同；`poseToBone` 最大绝对误差 **4.7684e-5**。4 组各 7 个 quatinterp 触发器的驱动一致，数值误差不超过 **1.9074e-6**；8 个 jiggle 的已启用参数一致。
- **214,697 顶点**按位置、法线、UV 全部一对一匹配，最大几何差 **8.0109e-5**。原始权重不逐值相同：CE 剔除小于 `.001` 的微小权重，本工具默认保留。仅为比较按 CE 阈值过滤归一后，全部具名权重误差不超过 **1.1755e-7**，零不匹配。没有擅自把全局权重策略改成 CE。
- **GMod 实机验证**：在 `gm_flatgrass` 中同时创建 CE、旧版和修复版模型，加载 `c_arms_animations` 及手枪、SMG1、霰弹枪、撬棍的实际引擎动画。共 **295 个姿态 × 295 个对应蒙皮采样点**，覆盖全部 30 根手指及双臂主要加权骨。旧版相对 CE 的最大采样偏差为 **56.7905 Source 单位**；修复版为 **0.0056393**，无缺失采样点，骨矩阵最大差 **1.1444e-5**。屏幕并排渲染确认旧版明显变形、修复版与 CE 形状吻合。此为真实引擎动画/bonemerge验证，未覆盖所有第三方武器；采样比较排除独立推进的袖子 jiggle 状态，也不代表所有顶点逐帧完全相同。
- Plum 原始全身 QC 同样隔离编译及结构检查通过。骨数 **126→131**，恢复双眼、围巾根骨和左右腿 roll 骨，均真实承载网格权重；无旧骨丢失。此修复会改变合法模型输出，不再以与旧版逐字节一致作为正确性依据。

原始输入保持不变，用户模型与参考程序不加入源码或发布包。游戏验证使用专属临时 addon；测试结束后核对恢复 22 个原配置文件并清理测试文件。机器可读证据见 [v1.2.27-validation.json](tests/reports/v1.2.27-validation.json)。发布标签的源码为 `3a48c703d55e4a5251b7f398f547f121c0c02f2b`；之后的报告更新只补充正式包数据，不改变二进制。

## v1.2.26 历史验证

正式发布 [v1.2.26-r1](https://github.com/NPCodex/newpage-merge-mdl/releases/tag/v1.2.26-r1) 的 Windows/MSVC 与 Linux 云端构建、模型回归和实际包验证均通过（[运行记录](https://github.com/NPCodex/newpage-merge-mdl/actions/runs/37973400445)）。最终 Windows 包再次编译原始 Plum/viewarms，所有输出与 v1.2.25 逐字节一致，检查输入未变。

| 完整包 | v1.2.25-r1 ZIP | v1.2.26-r1 ZIP | ZIP 减少 | 新版解压大小 |
| --- | ---: | ---: | ---: | ---: |
| Windows x64 | 13,830,563 | 7,230,469 | 47.7% | 17,003,566 |
| Linux x64 | 13,043,397 | 4,738,544 | 63.7% | 12,432,069 |

表中单位为字节。Windows 上版为 llvm-mingw、本版为 MSVC，发布包对比包含工具链差异；相同本地 llvm-mingw 工具链的整包为 13,830,563→7,952,979 字节（42.5%）。完整资产哈希、二进制哈希及云端来源已记录到本页末尾所链接的 v1.2.26 JSON。

本轮精简保持全部导入器、编译/反编译功能、三个子工具、独立 VRML 转换器和 Windows C4D helper。运行包不再重复携带 tinyusdz 开发源码和图片；保留主许可证、来源及内嵌依赖版权声明，GPL 转换器的对应源码仍完整附带。自动上游包的精确源码归档仍保留全部构建输入。

本地 Windows x64 llvm-mingw 实测主程序：v1.2.25 为 **16,739,840 字节**；修正 pugixml 静态库误导出后普通 Release 为 **16,591,872 字节**；采用 `MinSizeRel -Os + ThinLTO` 为 **12,794,880 字节**，相对原版减少 **23.6%**。VRML 转换器从 755,712 减到 568,832 字节。两者各 406 个多余导出已消除，显式共享库导出宏仍可使用。发布流程使用 MinSizeRel + IPO；普通 Release 开发构建保留。

- 候选二进制通过 **377 项兼容性、7 项 C4D** 测试，以及包内 VRML 同款转换/编译、Unicode 路径及坏输入输出保护检查。**26 项自动化、10 项固定 helper 分发测试**通过。
- 原始 Plum 和 viewarms 使用已安装 GMod 的正确 gameinfo，在隔离目录编译；所有实际 MDL/VVD/VTX/PHY 文件与 v1.2.25 的 SHA256 逐个相同。额外记录的 50 个 QC/VRD/手臂输入及性能对照中的 161 个实际资源依赖均未变。
- Plum 每种构建预热一次，再交替计时三次：普通 Release 中位 **2.336 秒**，精简构建中位 **2.382 秒**（+1.94%）；均值仅相差 +0.16%。全部输出字节一致。这是单模型小样本，不能推广为所有输入的速度保证。
- C4D 的分节优化没有体积收益；IPO 仅节省 40,960 字节，压缩后约 14 KB。两轮实验均通过 7 项测试；本轮沿用原已验证 helper 和固定分发来源。

这些大小和耗时对应本地 llvm-mingw 构建；云端 MSVC/Linux 的最终安装包体积及 SHA256 以发布说明为准，程序独立构建并通过实际打包验证。本轮没有新增游戏内验证。机器可读证据见 [v1.2.26-validation.json](tests/reports/v1.2.26-validation.json)。

## v1.2.25 历史验证

原始 `viewarms_compile.qc` 在 v1.2.24 复现 `Bip01_L_Twist` 找不到短名父骨 `Bip01_L_Forearm`；CE x64 可编译。修复父骨折叠的名称解析，以及共用皮肤表中未使用基材质列的误拒绝后，同一原始 QC 使用已安装 GMod 的正确 `gameinfo.txt`、隔离输出完整编译通过。

- 输出结构检查通过：17 根骨骼、214,697 个顶点、4 个 quatinterp 辅助骨约束，每个 7 个 trigger；42 组皮肤的全部实际 mesh 材质映射与 CE 相同。
- 新增 8 项回归覆盖短名/完整名父骨、连续折叠、同后缀骨骼身份、旋转与平移数值、严格名称和真实缺失诊断，以及未使用皮肤列、材质合并和错误行宽。
- **377 项兼容性、20 项自动化测试通过**。Plum 全身模型的 5 个实际模型文件与 v1.2.24 逐字节 SHA-256 一致。50 个检查输入（QC、QCI、VRD、手臂源模型/动画）哈希未变。

CE 会登记没有 mesh 引用的皮肤材质；本工具仍裁剪这些登记，保留实际使用映射和全部皮肤编号。骨骼保留策略沿用既有默认值，不据此宣称完整 CE 骨架/动画等价。本轮验证编译及序列化结构，没有新增游戏内画面认证。机器可读记录见 [v1.2.25-validation.json](tests/reports/v1.2.25-validation.json)。

## v1.2.24 历史验证

本轮为发布体积优化，保留全部导入器和原有 Release `-O3` 优化等级。Windows x64 llvm-mingw 20260922 UCRT 实测：

| 主编译器 | 字节 | MiB |
| --- | ---: | ---: |
| v1.2.23 本地原始产物 | 27,856,896 | 26.57 |
| 仅移除符号的实验副本 | 21,965,312 | 20.95 |
| v1.2.24 函数/数据分节、链接清理与符号移除 | 16,738,816 | 15.96 |

主程序减少 **39.9%**。这不是完整发布包的压缩率，其他编译器/平台的体积需分别测量。`.pdata` 异常展开信息、`.rsrc` Windows 资源和重定位段仍保留。反编译器为 942,080 字节，VRML 转换器为 755,712 字节；独立 MSVC 构建的 C4D helper 本轮未重编。

新二进制通过 **369 项兼容性、20 项自动化、7 项 C4D 桥接测试**。Plum 原始 `playermodel_f_compile2_hair.qc` 使用已有隔离 AppID 4000 gameinfo 挂载桌面 gmod 资源，在两个独立输出目录分别由旧、新二进制编译；**11 个输出文件逐字节 SHA-256 完全一致**，原 QC SHA-256 未变。单次编译时间不用于性能提升结论。本轮未重新启动游戏，不将此前实机结果计为新验证；Linux/MSVC 构建仍需各自 CI 验证。机器可读结果见 [v1.2.24-validation.json](tests/reports/v1.2.24-validation.json)。

`NEWPAGE_COMPACT_RELEASE=OFF` 可恢复原构建策略；Debug/RelWithDebInfo 不受此次精简影响。五编译器功能范围及已知兼容边界沿用 v1.2.23 固定结账，不因体积变化扩大兼容性声明。

## v1.2.23 历史验证

本轮固定五编译器清单见 [FIVE_COMPILER_COMPLETION.md](FIVE_COMPILER_COMPLETION.md)，机器可读结果见 [v1.2.23-validation.json](tests/reports/v1.2.23-validation.json)。本地 Windows x64 编译器通过 **369 项兼容回归、20 项自动化、9 项 CONTENT 挂载、9 项 Lua、7 项 C4D、9 项输出事务恢复测试**。专项数量单独列出，不作为新增功能数量。

| 范围 | 结果与边界 |
| --- | --- |
| 默认参数及兼容策略 | gameinfo/cfg/CLI 优先级、Neko 条件、CE 归一化权重过滤和两条 FBX 导入策略通过；互斥默认值采用明确选项。 |
| 容量与骨骼 | 32769、65537、511451 移动 flex 顶点验证实际增量/索引/几何与 VTX；局部 uint16 边界仍保留。低 LOD、显式 hitbox 和动画使用骨的提前裁除已修复。NoBoneRealign 数值对照使用输出 MDL 本身的量化精度上界。整数格点哈希补充最终位混合，消除 MSVC 桶碰撞退化而不改变顶点相等规则或输出顺序。 |
| 场景与动画 | FBX cluster bind 与 rest 分离、双骨/多采样、Collada STEP/LINEAR/BEZIER、PMX 命名 vertex/group morph、四种 meshopt filter、蒙皮实例展开及 VRM 1.0 显式弹簧链通过。非均匀/反射物理变换需要烘焙或自定义适配。 |
| 额外格式 | M3D、固定 tinyusdz 的 USDA 单根/多根场景、独立 VRML 转换/编译通过。实际 Assimp 注册表为 50 项、77 个唯一扩展名；不是每种格式完整行为认证。VRML 独立构建成功，源码及依赖随包提供。 |
| C4D | 自制四边形文档验证几何、层级、材质颜色/名称、UV/法线、节点筛选、错误保护、临时清理、Unicode/空格路径。SDK 和示例/文档不分发。完整本地 Windows ZIP 附静态桥接，CI 包无桥接；程序化生成器、蒙皮、动画和着色网络不在 importer 范围。 |
| 输出恢复与路径 | MSVC 九项真实进程中断/并发/路径别名测试通过；Windows 8.3 短名和大小写别名共享恢复与锁，输出根目录下 junction/symlink 仍拒绝；损坏 journal 或外部修改文件保留并报错。MinGW 主程序嵌入 UTF-8 manifest；L4D2 VPK 中两个历史 Latin1 文件名不再使无关资源索引崩溃，附安全路径回归。 |
| Plum 原始生产输入 | 126 bones、572277 vertices、18 physics bodies；MDL/PHY 总质量均 30，65 个材质均可解析且引用贴图完整。原始 QC 与 249 个供给材质文件散列未变。 |
| 参考边界 | CE replacemesh 候选语法均失败，保留未知。2013 依赖恢复后确认 max64 材质、255 最终骨、9000 移动顶点的大 VTA；30000 移动顶点触发 max10000。Neko 128 个不同 skin 行成功，256/1024 测试崩溃，只报告成功下界。 |
| 性能 | 对原始 Plum 和自制 90000 顶点模型，成功配置各三次顺序测量。Plum 本工具/CE 中位 1.713s/10.850s、峰值 628.6/696.1 MiB；最终骨数 126/104 不同，不作为等同输出倍数。其他参考失败和 Neko VTX 覆盖不足均记录。 |

| 本轮游戏 | 实测结果 |
| --- | --- |
| Garry's Mod，2026.10.08 | `gm_flatgrass` 离线：6 项客户端及 2 项服务端检查通过。bodygroup 读回序列 0/1/2/1/0，LOD 0/1、jiggle 骨矩阵、2 物理体/质量 10 及落地有限坐标通过。VRM flex 读回约 .8，独立材质 RGB=(1,.2,.1)、alpha=.7、UV=(1.25,1.5)，真实弹簧回调产生有限 tail；画面确认红色三角与蓝色模型，无缺失材质棋盘。 |
| L4D2，2.2.4.3 / build 10097 | `c1m1_hotel` 离线：states/avatar/basic 三个自制模型均创建为 `prop_dynamic`，模型名读回正确；VScript 读取 `mesh_state` bodygroup 初值 1，并用 `SetBodygroup(0, 2)` 成功切到 2。三个标准实体的 `NetProps.HasProp("m_flexWeight")` 均为 false，因此 L4D2 的标准 `prop_dynamic` 路径不能直接消费顶点表情；这不是 GMod Lua 模块可在 L4D2 执行的声明。 |
| Insurgency，build 9810 | 自有实例进入 `contact`，三模型已编译并临时安装，但 netconsole 指令无回显；并发用户输入及 Steam 启动弹窗阻挡进一步 UI 检查。模型加载/动画/材质/物理均未认证。 |
| HL2 / CS:S / TF2 / SFM | 本轮未发现对应已安装应用清单，未运行；不记为通过。 |
| CSGO / MCV | 沿用各历史章节所述证据，没有将它们计为本轮新执行。 |

GMod 的 `GetSubMaterial` 在客户端读回服务器值，空字符串不代表客户端覆盖失败。材质模块返回实际克隆记录用于检查，并允许 `previousOverrides` 显式保存原客户端覆盖；这不是禁止客户端专用模型的理由。弹簧验收没有逐帧参考等价或零穿透保证。自有测试进程结束后，登记的临时文件与配置按清单清理/恢复，详情见报告。

## 2026-10-09 后续验证

后续运行记录见 [`tests/reports/v1.2.23-followup-runtime.json`](tests/reports/v1.2.23-followup-runtime.json)。L4D2 的 bodygroup 消费路径已确认；标准 `prop_dynamic` 没有 `m_flexWeight` 网络属性，所以不能把 GMod 的 VRM/顶点动画消费者直接移植为 L4D2 通用模块。需要 CBaseFlex 实体、引擎扩展或目标游戏提供的专用接口后，才有继续实现的条件。CE `replacemesh` 公开资料和 Neko 已提取格式描述符也完成复核，没有出现新的可移植入口。

最后两项原生修复后，最终编译器离线重编 states/avatar/basic 三个实机样例，13 个 MDL/VVD/VTX/PHY 文件与之前真实安装的文件逐个 SHA256 相同。报告保留实机与复编两份编译器散列；这不是重新启动游戏的验收。

最终发行包会解压并运行包内编译器、VRML 脚本/转换器和随附 C4D 桥接的测试。云端 Windows/MSVC 与 Linux 产物拥有独立的构建、测试和包清单，不套用本地二进制散列。

原始证据保存在本机 `.diagnostics/v1223-*`、`c4d-bridge-validation/`、`runtime-v1223/`、`integration-reference-20261009/` 与 `integration-performance-v1223/`。公开报告保留散列和有界结论，用户素材及参考二进制不进入仓库。以下均为历史记录。

# v1.2.22 历史验证

最终 Windows x64 二进制通过 **325 项兼容回归、20 项自动化回归、6 项 CONTENT 挂载专项**。完整记录见 [v1.2.22-validation.json](tests/reports/v1.2.22-validation.json)。固定的 A1–A7、B1–B4 共 11 个功能包已完成，逐项范围与排除项见 [CSGO_PORTING_SCOPE.md](CSGO_PORTING_SCOPE.md)；输入说明见 [布料指南](CSGO_CLOTH_AUTHORING.md) 和 [DMX 指南](CSGO_DMX_INPUTS.md)。

| 范围 | 结果与边界 |
| --- | --- |
| 布料坐标、拟合与四边形 | Y/Z-up 独立转换、最终 InitPose `prerotate`、混合 fixed/dynamic Fits、`flex_borders`、多重固定影响、参考阈值/小点云策略、交叉修正和短对角拆分纳入黑盒回归。 |
| 高级 FE 与直接投射 | 显式 rods/springs、rope/follow/FTL、质量与局部响应、节点 sphere/plane、绑定碰撞及 legacy 参数通过结构与数学检查。双面投射保留两侧比例并适配 VVD 三权重；空蒙皮与生成骨骼路径通过。非均匀 local-position 数组的最大值为 1 时，描述符使用 `nextafter(1,0)` 绕过引擎跳过数组的门控，数组值保持精确。 |
| DMX、rig 与时间轴 | 七类 rig 的依赖图、动态目标/权重/参数、最终层级循环检查；QAngle/Matrix/Color/String/Time 日志与 Pack/Unpack；倒放、Film/shot 嵌套和边界归属通过。Aim 使用同一 authored basis 的实际 slave 平移，修正旧测试混合坐标的预期。 |
| flex 与材质 | DMX 缓存不携带可变 QC 展开结果；逐次导入的变量快照、缺变量失败、NoAutoDMXRules、前导小数/一元负号，以及 Patch/include、`$clientShader`、挂载资源、跨 skin family 的 MouthShader teeth 标志通过。 |
| Plum 原始生产输入 | 隔离编译：126 bones、572277 vertices、18 physics bodies；MDL/PHY mass 均为 30，65/65 材质解析、引用贴图完整。原始 QC 与 249 个供给材质文件哈希不变。 |
| CSGO 实机 | 1.38.8.1 / build 8802，离线 `de_dust2`。10 个自制 cloth22 样例加载并播放：直接投射与混合拟合可见变形，固定控制保持平面，高级布料与两种绳链运行；实体上移 12 单位后模拟保持可见且有限。Rotation 指针在名义 1/3 秒方向改变，IK 两段骨随目标改变姿态。 |
| 地图重载 | `changelevel de_dust2` 后重建并显示 10 个布料和 2 个 rig 模型，分别记录 `READY 10/2` 与重载画面。 |
| 清理 | 62 个登记临时文件按哈希核对后移除；6 项设置读回恢复，正常 `quit` 后 CSGO 进程为 0。任务游戏日志已归档移出游戏，临时控制口凭据已删除。 |

实机证据只覆盖上述样例。高级碰撞壳的加载不等于完成碰撞 A/B；未测全部节点穿透、平衡形状、精确游戏骨角或完整 stock 逐帧等价。名义相位由延时暂停取得，没有读回 cycle。初期诊断脚本的 Squirrel 小数写法和控制台分号错误已修正，最终脚本及重载成功；没有观察到模型专属引擎错误。FE 仍限 CSGO，rig 为编译期烘焙；后续 QC、运行时混合或 IK 不重新求解。本地未新增 Linux 运行，跨平台构建以相应 GitHub Actions 记录为准。

本机原始证据：`.diagnostics/v1222-compatibility.log`、`v1222-automation.log`、`v1222-content-mounts.log`、`v1222-plum/validation.json` 和 `runtime-v1222/results.json`。报告保存二进制及证据哈希；原始游戏日志、参考二进制和用户模型不进入发布包。以下版本均为历史记录。

# v1.2.21 历史验证

最终 Windows x64 二进制通过 **285 项兼容回归、20 项自动化回归、6 项 CONTENT 挂载专项**。机器可读记录见 [v1.2.21-validation.json](tests/reports/v1.2.21-validation.json)。用户解除启动阻挡后，已在 CSGO 1.38.8.1 / 8802 离线 `de_dust2` 完成本节所列布料、原生 AxisInterp 和烘焙 Twist 的画面/运动检查。初始坐标审计未发现错误，本轮未修改编译器，版本仍为 v1.2.21。

| 范围 | 结果与边界 |
| --- | --- |
| 布料，22 项筛选回归 | 骨骼绑定球/渐变半径胶囊 ABI、指令时缩放、改名/骨轴处理、1/2点和共线回解、任意刚体变换的 NodeBase/ReverseOffset 数学、自由锚点排序、杆面替换/去重/质量权重、异常输入保留输出通过。 |
| AxisInterp，6 项；Twist，9 项 | 原生六轴记录、cardinal realign、编译后root轴标记与无效组合拒绝通过；Twist正常/inverse、非平凡旋转、改名、换父、任意realign、全模型旋转、指令/动画scale及realign opt-out符合独立世界姿态数值检查。 |
| AxisInterp反编译，5 项 | 默认QC、PulseQC、datamodeljoints均可回编；root control轴槽保持、含空格/点的名字、nomesh引用及坏记录拒绝通过。原版实际回编的位置最大误差4.77e-7、Quaternion点积误差约1.1e-7；初始NP/stock原生176字节记录和骨flags相同。 |
| DMX，40 项筛选回归 | 包含既有依赖/约束回归；新增Float16种曲线、混合入出/hold/default/clamp/edge、非均匀时间、Vector/Quaternion行为、压缩log及255游程边界、类型/范围/截断/非有限值拒绝和已有输出保护。筛选数与其它专项可能交叠，不相加作为总测试数。 |
| 原版DMX数值对照 | 两个5帧压缩Vector3/Quaternion输出完全相同；4种常用Vector3曲线相同，5种Quaternion曲线最大1e-6 rad差。NormalizeX默认末端1tick边界产生大幅过冲，float时间精度已修正，剩余最大0.030762差为一个最终MDL位置量化档。 |
| Twist实际编译产物 | 反编译采样帧30/90：正向/inverse驱动约±80°，纠正骨约±20°/±60°；游戏中另外观察到相应正负方向运动，尚未读取精确游戏骨角。 |
| Plum原模型 | 原始`playermodel_f_compile2_hair.qc`隔离编译：126 bones、572277 vertices、18 physics bodies，MDL/PHY质量均30；65/65材质解析，引用贴图完整。原QC与249个材质文件不变。 |
| 游戏内布料 | 7 个 cloth21 样例加载、多骨变形及实体移动可见。原 sphere/capsule 样例的可见壳较低，因此另用零重力、相同可见壳的 4 个 `contact_on/off` 样例对照，观察到明显碰撞响应差异。尚无逐帧接触或全部代理点/渲染点无穿透证明。 |
| 游戏内 AxisInterp | 原生 NP/stock 样例同步播放 `motion`，在 0.5/1 秒名义相位视觉一致。通过 `SetAnimation` 加延迟 `SetPlaybackRate 0` 停止，没有读回 cycle，不能当作精确帧、游戏骨姿态或完整 stock 等价结论。 |
| 游戏内 Twist | 正向/inverse 样例在正负方向均可正常播放；使用普通烘焙动画，不依赖游戏默认关闭的 Twist 开关。该观察不改变后续 QC、运行时 IK/混合不重算的限制。 |
| 地图重载 | 7 个 cloth21、4 个接触对照及 4 个程序骨样例均成功重新载入，分别记录 `READY 7/4/4` 和 `reload-{cloth,contact,procedural}.png`。这是重新载入检查，不增加逐帧数值结论。 |
| 清理与设置恢复 | 67 个登记的临时模型/材质/脚本/配置文件按哈希核对后移除；CSGO 正常 `quit` 后确认进程数为 0。6 项临时设置已读回恢复：`sensitivity=2.5`、`engine_no_focus_sleep=50`、HUD=1、viewmodel=1、drawothermodels=1、wireframe=0。 |

布料仍限定CSGO骨骼/扩展VTX目标；稀疏回解依赖有效邻接面，杆面规则是针对参考空分支的明确定义。AxisInterp拒绝无法表达的骨轴/层次变化；Twist在后续QC操作之前烘焙，运行时IK/混合不重算。压缩日志限Vector3/Quaternion，指数衰减曲线限Float。没有新Linux实跑或完整源码/引擎等同行为声明。

# v1.2.20 历史验证

最终 Windows x64 二进制通过 **248 项兼容回归、20 项自动化回归、6 项 CONTENT 挂载专项**。在同一 CSGO legacy 离线 `de_dust2` 会话完成布料、约束动画及默认 SubD 输出的画面验证；临时安装的 187 个模型、材质、脚本和配置文件已按哈希核对后清理，游戏已正常退出。机器可读记录见 [v1.2.20-validation.json](tests/reports/v1.2.20-validation.json)。

| 范围 | 最终结果与边界 |
| --- | --- |
| FE 布料，16 项专项 | 设置块、动画吸引、弯曲杆/刚性铰链、地面/半径/碰撞树、零重力及既有代理/绑定/平面检查通过。`gravity_scale 0` 改成描述符比例 1、每节点重力 0，避免游戏将零比例恢复成默认重力。 |
| Quad/SubD，17 项专项 | 原生 topology、边界/UV/法线折痕、LOD、反编译 quad roundtrip、原生 8192 patch 上限；默认 Catmull-Clark 的 1–3 轮平滑、蒙皮/位置 morph、UV 接缝、跨材质连续几何和增长限额通过。 |
| DMX，21 项筛选回归 | 包含 5 项既有 DMX 回归及 16 项新增依赖/约束检查。覆盖 Point/Orient/Aim/Parent 的动态加权结果、非交换旋转 offset、clip 作用域、分层 log、连接/表达式/Pack-Unpack、循环、冲突和数值边界。约束与 `$centerbonesonverts` 的已知错误组合明确拒绝。 |
| 原版布料数据对照 | 自制 20 点代理：双方 22 nodes/5 static、1 FitMatrix/16 weights，按位置对应的逆质量、拟合中心/偏移/权重相同，20 条杆约束最大数值差约 2.98e-8。SIMD 分组/求解顺序不同，不声明逐帧运动相同。 |
| 游戏内布料 | 显式播放 121 帧根骨动画；观察正常重力、零重力、Z=40 绑定平面三组模型、实体移动与复位，地图重载后重新加载三组。已确认可见运动和固定控制随模型移动。样例的 16 个动态渲染点共用一个拟合骨，不能据此认证所有代理点的完整弯曲或所有渲染顶点不穿平面；运行时提供的世界球体/胶囊碰撞未实测。 |
| 原生 SubD 运行时发现 | Stock/NP 的圆滑立方体、弧面四个原生模型，在可见 HLMV 绘制时均于 `studiorender.dll+0x43cad` 写空指针。已装 `LockSubDBuffer` 实现是直接返回 NULL 的 stub。早期隐藏窗口 15 秒未崩溃不能算渲染通过。默认 `$subd` 因此改为离线细分；`$subd native` 只适用于真正提供 SubD 支持的 renderer，并有明确警告。 |
| 默认 SubD 游戏渲染 | 两轮离线细分的立方体呈圆滑曲面，弧面完整显示；模型线框确认真实三角细分。最终编译器重编的 MDL/VVD/VTX 与观察时的文件逐字一致。 |
| 四类约束游戏验证 | Stock 与初版 NP 的 8/9/10/12 程序骨记录未驱动 helper；参考 `CalcProceduralBone` 也没有这些分支。改为离线烘焙并清除对应 `BONE_ALWAYS_PROCEDURAL` 后，在约 1 秒/3 秒两姿态确认 Point 跟随高度、Orient 转向、Aim 朝向目标、Parent 平移/旋转；地图重载后继续播放。后续 QC 修改、运行时混合及 IK 不重新求解约束。 |
| Plum 原始生产模型 | 最终二进制隔离编译原始 `playermodel_f_compile2_hair.qc`：126 骨骼、572277 顶点、18 个物理体；结构检查通过，MDL/PHY 总质量 30 kg。65/65 材质可解析，已检查的纹理引用存在且 VTF 头有效；原 QC 与 249 个供给材质文件哈希不变。PHY 与 v1.2.19 完全相同。 |

当前结果是指定输入与已安装 Windows 游戏的验证，不代表所有 Source 引擎、DMX 算子或布料资产完整等价；未新增 Linux 本地执行。原生 SubD 和程序骨记录的运行时限制已转为上述默认可播放的烘焙路径，而不是将“编译成功”当成“引擎执行成功”。

复现兼容、自动化和独立输出检查：

```powershell
python tests/compatibility.py path/to/NewPageMergeMDL.exe
python -m unittest discover -s tests -p test_automation.py -v
python tests/validate_outputs.py isolated/models/model.mdl
```

本机证据保存在 `.diagnostics/v1220-compatibility.log`、`v1220-plum/validation.json`、`runtime-v1220/results.json`、`runtime-v1220-subd/viewer-load-report.json` 和对应画面/诊断日志。源代码参考、用户资产和临时游戏模型不进入发布包。以下版本章节均为历史记录。

# v1.2.19 历史验证

Windows 本地完整 **209 项兼容回归、20 项自动化回归**通过。下列新功能已包含在同一套件中；另有 6 项 CONTENT 挂载回归通过：

| 范围 | 本轮验证 |
| --- | --- |
| 自动质量，6 项 | 体积八倍/面积四倍缩放、材质密度/壳厚、骨骼 surfaceprop 继承、massbias、重复定义覆盖、外部分卷 VPK、未知/缺失材质回退、非法输入保留旧输出；同时检查 MDL 与 PHY 总质量。 |
| 附加碰撞源，6 项 | offset 坐标系和活动缩放、源缓存隔离、concave 全局开关与标记、跨源焊接、负缩放绕序、origin/bind 重映射以及失败时旧输出保留。 |
| FE 布料，10 项 | 独立检查资源偏移/对齐、三角形/四边形 rest shape、固定控制、加权骨骼回算、多网格单面平面选择/共面约束、指令时缩放、导入变换、骨骼改名、map 参数、错误拒绝和旧文件保留。 |
| 原版 CSGO 结构对照 | 同几何得到 8 节点/3 static/3 rotation-locked；按位置比较，固定状态和逆质量一致，2 个固定偏移及 4 个平面约束一致，法线浮差约 1.2e-7。骨骼回算算法不同，未认证变形等价。 |
| CSGO HLMV | 自制 quad/tri 布料样例均包含碰撞平面，各加载 15 秒，无访问异常；6 个临时游戏文件已清理。仅证明这两个样例的加载稳定性，未认证游戏内布料运动。 |
| Plum 生产编译 | 原始 `playermodel_f_compile2_hair.qc` 通过 stdin 追加隔离 OutDir：126 骨骼、572,277 顶点、18 个物理体，MDL/VVD/VTX 结构检查通过，MDL/PHY 总质量均为 30 kg。原 QC SHA256 前后相同；未修改或安装原资产。 |

Plum 的 PHY 除校验值字段外与 v1.2.18 逐字相同；36.828571 kg 的各刚体质量合计高于 30 kg 总质量，是每刚体至少 1 kg 的既有参考规则。质量修复保留该规则。最终二进制与 CSGO 原版使用实际挂载默认材质的自制四面体对照：边长 10 时两者总质量均为 5.462355 kg，边长 20 时均为 43.698837 kg，相同到打印的 6 位小数，确认边长翻倍时质量变为八倍；自定义材质的密度/壳厚使用独立输出回归验证，未将不同挂载环境的结果误作相同材质对照。

原版对照通过 model18 DMX 的 `cloth_enable_in_u` 设置将 UV U 转换为 enable；当前编译器使用等价的显式 `cloth_enable` map，不支持该 settings 块。两者的 2 个 CtrlOffsets 均绑定 root，偏移相同；4 个平面均绑定 root，子节点位置及距离 4 一致。原版使用 NodeBase + ReverseOffset 回算，当前样例写入 1 个 FitMatrix 与 4 个权重，不能由节点/质量/平面匹配推导出运动一致。

FE 当前只接受 `-game` 识别为 CSGO AppID 730 的骨骼模型和扩展 VTX，使用显式 `cloth_enable` 的三角形/四边形 DMX 代理；设置块、未知 maps、其他目标以及不满足锚定/骨骼拟合约束的输入会失败。完整 SubD、完整布料设置/二进制行为对照和动态游戏验证仍未完成。详细语义见 [COMPATIBILITY.md](COMPATIBILITY.md)。

## 复现与证据边界

```powershell
python tests/compatibility.py path/to/NewPageMergeMDL.exe
python -m unittest discover -s tests -p test_automation.py -v
python tests/validate_outputs.py isolated/models/model.mdl
```

如果 Windows 便携 MinGW/LLVM 构建依赖外部运行时 DLL，需把所用工具链 `bin` 目录加入 `PATH`，让反编译回归找到这些 DLL。生产验证保留原始 QC/QCI/DMX，传入原 QC 路径并用 `-stdin` 追加 `$OutDir "isolated-directory"`；保存原 QC 前后 SHA256、编译日志及独立输出检查结果。历史游戏测试不自动覆盖本轮 FE 模拟。用户资产、参考二进制和临时游戏文件不进入源码/发布包。

本轮机器可读摘要为 [tests/reports/v1.2.19-validation.json](tests/reports/v1.2.19-validation.json)。本机原始记录为 `.diagnostics/v1219-mass-tests.log`、`.diagnostics/v1219-plum/compile.log`、`.diagnostics/v1219-plum/validation.json`、`.diagnostics/runtime-v1219/results.json` 及 `.diagnostics/v1219-cloth-audit-anim/compare-results.json`。这些 `.diagnostics` 文件属于本机验证产物；本文件保留可复现的方法和限定结论。以下章节均为历史记录，不表示当前测试数量或当前未完成项。

# v1.2.7 历史验证

146 项兼容回归、20 项自动化回归；显式 CE/Neko 模式共 28 项对照一致，StudioMDL++ 七项动画对照继续通过。Claudia 真实材质、面部近景、生成减面 LOD 与物理验证通过；Hair 原始输出不变。数据摘要：`tests/reports/v1.2.7-validation.json`；范围及复现见 [IMPROVEMENTS.md](IMPROVEMENTS.md)。

# v1.2.6 历史验证

138 项兼容回归、20 项自动化回归；七项新结果及未完成范围见 [IMPROVEMENTS.md](IMPROVEMENTS.md)。历史验证记录保留如下。

# v1.2.5 编译修复验证 / Compilation regression fix

128 项兼容回归、16 项自动化回归通过。用户原始 player 和 NPC Hair QC 分别输出 126 / 124 根骨骼、572277 顶点；两份均在隔离输出目录通过编译。报告：`tests/reports/v1.2.5-validation.json`。原始 QC、QCI 和 DMX 未修改。

Both original Hair QCs now compile without modifying their source assets. Bodygroup validation checks stored bases and preset values. This compilation fix does not extend the earlier engine-validation scope.

# v1.2.4：新增功能与验证 / Features and validation

## 资源查找 / Resource lookup

QC 文件旁的资源和显式 include/source 目录优先，随后按 `-game` 目录中
`gameinfo.txt` 的 `FileSystem/SearchPaths` 声明顺序查找。支持 Game/Mod/Content
搜索项、`|gameinfo_path|`、`|all_source_engine_paths|`、`|appid_550|/left4dead2`。
AppID 查找读取 Steam 的 libraryfolders 和 appmanifest，支持其他磁盘的游戏库。
Steam 根目录可通过 `-steamdir <path>` 或 `NEWPAGE_STEAM_PATH` 指定；Windows
默认读取当前用户 Steam 注册表项。未安装的 AppID 输出警告并跳过。

目录及其根目录 VPK、显式 VPK、`*_dir.vpk`/分卷、VPK v1/v2 和 preload 均可读取。
档案索引及数据范围经过检查，资源按需解包到独立临时缓存，退出时清理自己的缓存。
v1.2.4 当时支持目录 `*` 展开；v1.2.18 已补齐 CONTENT 的 `*` / `?` 及 VPK/分卷。压缩 VPK 和 GMod 专有 mount.cfg 语义仍未实现。

Local script/explicit paths precede ordered gameinfo mounts. AppID lookup discovers
installed games across Steam libraries; missing apps warn. VPK extraction is lazy
and isolated. This implements compiler resource search, not the entire runtime
mount system of every Source game.

## Draco 与动画烘焙 / Draco and animation baking

glTF 的 `KHR_draco_mesh_compression` 三角形直接通过 bundled Draco 解码。属性映射
使用 Draco unique IDs，保留法线、UV、蒙皮属性及外部未压缩形态键。损坏流、数量/类型
不匹配明确失败。自制回归使用超出 accessor 范围的 unique IDs，防止混淆两种索引。

```qc
$modelname example/animated.mdl
$body body animated.gltf BakeSceneAnimation Move SceneSampleRate 30
$sequence idle idle.smd
```

`BakeSceneAnimation` 选择具名 clip；静态序列用于引擎渲染时的骨骼姿态。烘焙包含
节点变换、蒙皮、动画缩放、形态键权重、位置与法线增量，输出 NWAY 表情帧和
`animated.vertexanim.json`。末尾不足一个采样周期时仍保留精确终点时间。glTF 快速路径
对 LINEAR/STEP/CUBICSPLINE 先采样，再生成线性相邻表情帧。提高采样率可减少误差；
运行时线性帧插值不会无损保留 STEP 跳变或任意三次曲线。

每 clip 最多 4096 帧、1600 万个源顶点采样；零缩放、找不到的 clip 和无效权重明确失败。
采样目标扩展渲染边界和半径，避免只使用 bind mesh 时发生过早裁剪。
骨骼动画不再叠加相同烘焙运动。网格替换动画尚未支持。

GMod 客户端使用发布包的 `integration/gmod/newpage_vertexanim.lua`：

```lua
local playback = include("newpage_vertexanim.lua")
local metadata = assert(playback.Load(entity:GetModel()))
-- 每帧调用；调用方管理循环、暂停、时间和 entity 生命周期。
playback.Sample(entity, metadata.clips[1], seconds)
```

将 Lua 放入模组可 include 的目录，将 JSON 与模型一同安装。其他游戏需要等价的
控制器驱动代码。GMod 的原生与网络表情控制器输入范围不同，播放器已分别处理；见 [SetFlexWeight 文档](https://wiki.facepunch.com/gmod/Entity:SetFlexWeight)。Baking is sampled vertex-cache playback, not native bone-scale
tracks. Other runtimes must drive the two documented flex controllers themselves.

## 布娃娃 / Ragdolls

```qc
$collisionjoints physics.smd {
    $mass 10
    $rootbone root
    $maxconvexpieces 4
    $decomposeconcave
}
```

按每个物理骨骼的局部空间调用 VHACD，再进入原有体积/质量、父子排序和约束输出流程。
普通 `$concave` 的岛分割行为保留。VHACD 使用 100000 voxel、深度 10、0.01 体积误差
及指定 piece cap；分解是近似算法，复杂输入应检查实际凸体，而非保证最优分解。

## 验证 / Verification

v1.2.4 当时的兼容回归 **127 项**，自动化回归 **16 项**。新增样例覆盖挂载搜索顺序、第二个
Steam 库、VPK v1/v2/分卷/preload/损坏数据、Draco 属性/UV/形态键/损坏流、位移与
缩放/权重/蒙皮烘焙、采样元数据、渲染边界、性能 JSON、眼睑描述符和多骨凹体分解。

`tests/reference_differential.py` 使用自制样例分别对照用户提供的 CE 和 NekoMDL。
六组为骨骼/attachment、jiggle、IK/LOD、VTA 表情、眼睑和 DMX。比较骨骼顺序、父子、
bind transform、procedural 类型、IK/flex 数量、描述符顺序、控制器范围及眼球/眼睑
目标与绑定；两份参考均通过。既有数值回归验证 corrective、domination 和驱动骨。
这些是明确样例的检查，不是任意复杂 rig 或逐字节文件兼容认证。

2026-10-07 在本机 Garry’s Mod x64 / gm_flatgrass 实测：

- Alyx：113 个骨骼、61 个控制器；白色材质覆盖下正常绘制，表情/眼睑状态和强制 LOD 0/1 截图有几何像素差异。
- 自制顶点动画：0、0.5、1 秒三个采样时刻可见，播放输出各不相同。
- 自制 LOD：高精度 L 形网格实际替换为低精度四面体，截图检查明显几何差异。
- 自制双骨凹形布娃娃：两个物理体各 mass=5，volume≈3.007805，落到地图地面，位置保持有限值。

测试脚本为 `prepare_game_validation.py` 和两个 `game_validation_*.lua`；需要用户的
face QC 和已安装的 GMod，未纳入无游戏环境的 CI。安装在明确命名的
`newpage_validation_v124` 目录。报告/截图只在本机保存；不分发用户模型或参考程序。
使用 `prepare_game_validation.py ... --autorun` 安装专用 InitPostEntity 测试入口，
关闭测试游戏后移除 `lua/autorun/server/newpage_validation_v124.lua`，避免普通游戏触发测试。
启动参数应包含 `-noworkshop -noaddons +r_jiggle_bones 0 +flex_smooth 0 +map gm_flatgrass`；
重复 neutral 截图量化光照/渲染噪声，顶点动画还检查实际屏幕位移和中点线性关系。
实际材质着色、其他游戏、任意生产模型和所有动画/物理状态仍需独立验证。

## 性能 / Performance

`-perfjson report.json` 输出 schema/version、load_ms、compile_ms、write_ms、total_ms、
peak_working_set_bytes、骨骼和顶点数量。加载阶段包含资源挂载及 QC/source 读取。
Windows 使用峰值 working set，Linux 使用 getrusage peak RSS；二者不能直接等同。

```powershell
python tests/benchmark_models.py NewPageMergeMDL.exe --qc model.qc --runs 3 --report benchmark.json
python tests/reference_differential.py NewPageMergeMDL.exe --reference reference.exe --work isolated-diff
```

基准把输出重定向到独立临时目录，以三次运行中位数和每轮输出 SHA256 检查可重复性。
本机三份生产输入为 Alyx、Neko 的完整 survivor_teenangst 和独立 Hair DMX 夹具；实际
测量汇总见 `tests/reports/v1.2.4-validation.json`。它们不是跨机器速度承诺，也不代表
与其他编译器的系统性能对比。用户原始模型及 QC 不会加入源码或发布包。
