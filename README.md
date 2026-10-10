# NewPageMergeMDL v1.2.27

[English](README.en.md) | 简体中文

## 编译前必读

**无论编译哪款游戏的模型，都请正确设置 `-game`，尤其是 CSGO 和 MCV。** 参数必须是目标游戏/模组中**包含正确 `gameinfo.txt` 的目录**，不是 `gameinfo.txt` 文件本身，也不是 Steam 根目录或 `bin` 目录。请使用目标游戏自己的文件，不要借用其他游戏的 `gameinfo.txt`。编译器根据其中的 AppID 和挂载配置选择目标布局、资源与默认参数；路径缺失或选错，即使产生了文件，也可能无法在目标游戏中正常加载。

```powershell
NewPageMergeMDL.exe "model.qc" -game "D:/Games/csgo legacy/csgo" -OutDir "D:/build/model"
```

上例要求 `D:/Games/csgo legacy/csgo/gameinfo.txt` 实际存在。编译 MCV 或其他游戏时，将 `-game` 换成其对应目录；路径含空格时保留引号。

- **游戏目录与输出目录分别设置。** `-OutDir` 只指定输出根目录，不替代 `-game` 的目标识别和挂载；`$modelname` 决定其下的模型路径。建议先输出到隔离目录，保留现有模型，再在目标游戏验证后整套替换匹配的 MDL/VVD/VTX/PHY/ANI，避免混用旧附属文件。
- **选择正确目标不等于突破引擎限制。** CSGO（730）/MCV（1012110）的扩展 VTX 会按正确 AppID 自动选择，单设 `-vtxformat` 不能代替正确目标配置；FE 布料仍限 CSGO。最终骨预算默认255、每顶点最多3个最终权重等格式限制仍有效。SubD 建议使用默认离线烘焙；已测 CSGO legacy renderer 的原生 SubD 路径会崩溃。不要把一种游戏的产物直接当成另一种游戏的通用模型。
- **材质与资源需完整。** 检查 QC 的材质路径、目标挂载和对应 VMT/VTF；通用场景的材质名称/颜色导入不代表自动生成完整 Source 着色材质。
- **扩展有各自的使用条件。** C4D 需完整 Windows 包中的桥接程序；VRML 使用独立转换器。网格状态与 VRM 运行功能需安装配套 GMod Lua 模块，不会由普通 MDL 文件自动在所有游戏执行。详见 [额外格式](O5_FORMAT_IMPORTS.md)、[网格状态](MESH_STATE_WORKFLOW.md) 和 [VRM](VRM_RUNTIME.md)。
- **排查时注意默认参数与兼容模式。** 参数优先级是 `gameinfo < cfg/commandline.cfg < 显式命令行`，`-nodefaultargs` 可禁用前两者。CE/Neko 的冲突行为由显式兼容选项选择，见 [兼容说明](COMPATIBILITY.md)，不要只凭文件扩展名假定行为相同。
- **保留中断恢复文件。** 意外中断后，下次编译会尝试恢复整套模型；不要手动删除 `.npmdl-*` 日志、暂存或备份文件。若提示日志损坏或输出已被外部修改，先备份输出目录并检查报错；同一套输出不要由多个编译进程同时写入。

项目版本：**v1.2.27**。编译器、反编译器和辅助工具统一使用本项目版本号。

## 下载与安装：每个平台一个完整包

从 [GitHub Releases](https://github.com/NPCodex/newpage-merge-mdl/releases) 选择当前版本的 **Windows x64 ZIP** 或 **Linux ZIP**，完整解压到一个新目录即可使用。Windows 包已经包含 C4D 桥接程序；两个平台包都包含编译器、反编译器、辅助工具、独立 VRML 转换器及其对应源码、准备脚本、GMod Lua 模块、文档、许可、构建清单和包内校验文件，无须拼接其他附件。根目录的 `INSTALL.md`、`upstream-manifest.json`、`SHA256SUMS.txt` 提供安装说明、构建来源与文件校验；报告位于 `tests/reports/`。自动上游合并版还内嵌 `sources/NewPageMergeMDL-source.zip`；手动维护版的完整项目源码由发布标签对应的仓库提供。GitHub 自动显示的 **Source code** 链接供源码浏览，不是安装包。

更新时解压到新目录并使用整套新文件，不要仅覆盖主程序或混用旧辅助程序。普通编译无需 Python；运行 `tools/` 中的 Python 准备脚本需要自行安装 Python 3。网格状态及 VRM 的 GMod Lua 模块按相应指南安装，不会因解压编译器而自动在游戏生效。详见 [安装指南](INSTALL.md)。

自动更新及 GitHub Release 配置见 [AUTOMATION.md](AUTOMATION.md)。

基于 [PulseModel](https://github.com/ToppiOfficial/PulseModel) 的 Source 模型编译工具，加入 StudioMDL-CE / StudioMDL++ / NekoMDL 兼容功能与自行实现的动画扩展。NekoMDL 对照依据为附带的中文版 v2.3.0 更新日志。

编译器：`NewPageMergeMDL.exe`；反编译器：`NewPageMergeMDL-Decompiler.exe`。
支持 Windows x64 和 Linux 构建。Windows 和 Linux 构建由 GitHub Actions 验证。

目标是以 PulseModel 为基础，整合 CE、NekoMDL、StudioMDL 2013 和 StudioMDL++ 的模型编译功能。按来源追踪的状态见 [五编译器功能清单](FEATURE_MATRIX.md)，固定范围的最终结论见 [v1.2.23 结账表](FIVE_COMPILER_COMPLETION.md)。

## v1.2.27：修复外部动画驱动的手臂骨骼丢失

默认保留有蒙皮权重的骨骼及其父骨链，避免仅因本地 idle 静止就删除由武器动画、`$includemodel` 或 bonemerge 驱动的前臂和手指骨。原始手臂 QC 无须添加兼容开关或修改源文件。显式折叠策略仍可用于主动缩减骨架；保留骨数仍受目标引擎预算限制。具体选项和验证证据见 [兼容说明](COMPATIBILITY.md) 与 [验证记录](VALIDATION.md)。

此前 v1.2.25/26 的编译成功、结构合法及新旧产物相同，只证明当时所测范围，没有发现此运行时缺陷。请使用本版重新编译，并整套更新模型文件。

## v1.2.26：完整功能包进一步精简

正式完整包实测：Windows **13.83→7.23 MB**，Linux **13.04→4.74 MB**；所有工具保留，最终 Windows 包的原始 Plum/viewarms 输出与旧版逐字节一致。详细验证见 [VALIDATION.md](VALIDATION.md)。

发布构建使用 `MinSizeRel` 与 IPO/LTO，缩小编译后的程序，保留全部导入器、编译选项和辅助工具。普通 `Release` 构建仍可用于开发。运行目录不再重复携带静态链接的 tinyusdz 源码和开发图片，保留 `libs/tinyusdz/` 中的 `LICENSE`、`LICENSE-APACHE-2.0`、`SOURCE.md` 和 `THIRD_PARTY_NOTICES.md`；USD 导入无需这些源码文件即可运行。

独立 GPL VRML 转换器的完整对应源码及构建文件继续随包提供；自动上游包仍内嵌精确合并源码，手动维护版源码仍由发布标签提供。Windows 继续附带原先已验证的 C4D 桥接程序。Plum 与 viewarms 的本地模型输出已与上一版逐文件比较一致；最终包大小与验证范围见 [验证记录](VALIDATION.md)。

## v1.2.25：手臂 QC 兼容修复

修复 VRD 省略 `ValveBiped.` 等命名空间时，父骨折叠未同步更新辅助骨约束的问题；折叠后的驱动旋转和辅助骨姿态按存活父骨重新计算。共用 `$texturegroup` 中模型未使用的基材质列改为警告并跳过，保留皮肤组数量和实际使用的材质替换。无须修改原始 QC 或 VRD。详见 [兼容说明](COMPATIBILITY.md) 和 [验证记录](VALIDATION.md)。

## v1.2.24 发布体积优化

Release/MinSizeRel 构建默认剔除未使用的函数和数据；GNU/Clang 链接产物同时移除开发符号。保留全部导入器和现有编译功能，不降低 Release 的优化等级。需要保留完整发布符号时使用 `-DNEWPAGE_COMPACT_RELEASE=OFF`；Debug/RelWithDebInfo 不启用此项精简。具体实测体积和输出对照见 [验证记录](VALIDATION.md)。

## v1.2.23：五编译器固定清单收尾

全部已知项目及证据边界统一记录在 [五编译器结账表](FIVE_COMPILER_COMPLETION.md)，包括明确无法由当前格式/引擎独立完成的 H 项。此后以新的上游版本或具体缺陷作为维护输入，不再把本表子项拆成下一批“可挖掘功能”。

- 补齐 ++ 默认启动参数、Neko 条件模式、CE 权重策略、51 万级移动 flex、FBX 真正 bind pose 与通用动画采样；修复仅 hitbox/动画/低 LOD 使用骨被提前删除。
- 新增中断后的多文件输出恢复、PMX 命名 morph、蒙皮 GPU 实例展开；`-importformats` 给出实际构建格式清单。
- 修复 Windows 短目录名/大小写别名导致的输出恢复误报，以及 MSVC 下规则网格顶点哈希碰撞造成的处理迟缓；输出目录内的符号链接和目录联接仍明确拒绝。
- 提供 [有限拓扑状态](MESH_STATE_WORKFLOW.md)、[VRM 表情/弹簧骨运行模块](VRM_RUNTIME.md)；新增 [M3D、USD、VRML 和 C4D 导入路径](O5_FORMAT_IMPORTS.md)。VRML 转换器独立按 GPL 分发，主程序保持现有许可。
- 2013 参考环境已恢复；其实际容量与宣传的差异、CE replacemesh 缺有效语法的证据也已记录。验证结果见当前版本报告，不将参考未知信息算作已兼容。
- 后续运行验证确认 L4D2 `2.2.4.3 build 10097` 的标准 `prop_dynamic` 能创建本工具模型并读取/切换 `mesh_state` bodygroup；同一路径的 `m_flexWeight` 不存在，因此不宣称 L4D2 标准实体支持顶点表情。CE `replacemesh` 仍缺可复现公开语法，Neko 已登记格式没有新的缺口；Insurgency 模型加载仍未认证。详见 [后续运行报告](tests/reports/v1.2.23-followup-runtime.json)。

Windows x64 单包包含 `NewPageMergeMDL-C4D.exe`，解压后与主程序放在一起即可使用；Linux 使用预先在 Windows 转换的 GLB。自动发布同样提供完整 Windows 包，不再要求补装辅助程序。普通 CMake 构建无需 Cineware SDK；独立重建 C4D 桥接程序仍需另行取得 SDK 许可。具体格式和重建条件见 [O5 导入说明](O5_FORMAT_IMPORTS.md)。

## v1.2.23 后续运行时边界验证

后续实测记录见 [运行时报告](tests/reports/v1.2.23-followup-runtime.json)，用于补充边界，不扩大五编译器固定清单：

- **L4D2 2.2.4.3 build 10097**：标准 `prop_dynamic` 成功创建 `states/avatar/basic` 三个 mesh-state 模型；初始 `mesh_state` bodygroup 为 `1`，`SetBodygroup(0, 2)` 可切换为 `2`。这确认标准实体可以消费网格状态的 bodygroup 输出。
- 同一批实体的 `NetProps.HasProp("m_flexWeight")` 均为 `false`。因此不能宣称标准 `prop_dynamic` 能消费顶点表情；需要 `CBaseFlex`、引擎扩展或游戏专用接口。
- **CE `replacemesh`**：本轮仍未取得公开语法、源码实现、Issue 示例或发布资产，不能安全实现为 `replacemodel` 别名，继续标为证据不足。
- **Neko**：固定二进制描述符提取的 64 个扩展名均已覆盖现有登记集合，未发现新的格式入口。
- **Insurgency**：模型加载尚未取得可靠读回证据，仍不宣称游戏内模型兼容。

## v1.2.22 历史记录：完成固定的 11 项 CSGO 移植功能包

[CSGO 移植范围](CSGO_PORTING_SCOPE.md) 中的 **A1–A7、B1–B4 全部完成**。本轮按这 11 项收口；下面保留的兼容边界和测试覆盖范围不另算新增移植待办。

- **布料输入与拟合**：独立代理/平面文档的 Y/Z `upAxis`、最终 FE 初始姿态的 `prerotate`、`flex_borders`、固定点多权重、固定/动态混合拟合、影响阈值与稀疏点云策略；修复四边形排序/交叉，并按弯曲容差沿短对角拆分全动态四边形。
- **高级 FE 与渲染投影**：双节点 stretch capsule、逐节点内部/外部球体和平面、碰撞 mask、刚性碰撞体粘附；显式杆/弹簧、无面骨链绳索、follow/FTL、局部响应、质量、体积反馈、平滑及 legacy 参数。表面投影支持双侧体积、envelope、连通岛、无蒙皮代理和自动根骨，生成实际渲染蒙皮。
- **DMX 骨骼动画**：Rotation、两段骨 IK 与 Point/Orient/Aim/Parent/Twist 在同一依赖图逐帧求值；支持动画化目标、权重及旋转参数。新增 QAngle/VMatrix/Color/String/Time 日志、六个 Pack/Unpack 算子、倒放、嵌套 clip 和 FilmClip/track/shot 的骨骼输入，结果烘焙为普通动画。
- **面部与材质**：DMX flex 表达式在有效 QC 上下文展开 `$变量$`，保留命令行 `-defvar` 优先级；识别 VMT `$clientShader "MouthShader"`，写出 MDL 材质和 VTX teeth 标记，覆盖皮肤组与材质重命名。

具体语法、默认值、来源区别和组合限制见 [布料作者指南](CSGO_CLOTH_AUTHORING.md)、[DMX 输入指南](CSGO_DMX_INPUTS.md) 与 [COMPATIBILITY.md](COMPATIBILITY.md)。`advanced`、投影和拟合策略是本工具扩展接口；并非所有语法都可直接交给 stock studiomdl。

最终本地 **325 项兼容、20 项自动化、6 项挂载回归通过**。Plum 原始 QC/材质未改：**126 骨骼、572,277 顶点、18 个物理体、MDL/PHY 总质量均为 30 kg、65 个材质且无缺失**。离线 CSGO 已加载运行 **10 个布料及 2 个 rig 样例**，观察到投影/混合边界变形、绳索以及 Rotation/IK 动作变化；`changelevel de_dust2` 后再次重建，10 个布料和 2 个 rig 均确认就绪并截图。6 项游戏设置已读回恢复，游戏正常退出，62 个登记临时文件在哈希核对后清理。高级碰撞目前有结构检查及加载运行证据，未做定量碰撞 A/B；这些结果不证明逐帧 stock 等价、全部点零穿透或精确游戏骨角。验证详情见 [VALIDATION.md](VALIDATION.md)。

## v1.2.21 历史记录：绑定碰撞体、稀疏布料、AxisInterp / Twist 与 DMX 曲线

- **骨骼绑定碰撞体**：`$cloth { sphere ... capsule ... }` 生成模型自带的球体和渐变半径胶囊，跟随指定动画骨；支持缩放、骨骼改名及骨轴重映射。
- **更多布料绑定方式**：单点、双点或共线控制点可借助邻接面回解骨骼；新增 `cloth_anchor_free_rotate` 和 `cloth_use_rods`。后者将指定面替换为距离杆，是针对参考空分支补全的明确语义。
- **纠正骨**：旧式 `$proceduralbones` 文件导入 AxisInterp 六轴姿态并输出原生程序骨记录；DMX Twist 按参考旋转算法烘焙为普通动画，不要求游戏启用默认关闭的 Twist 开关。
- **DMX 曲线和压缩动画**：支持 Float / Vector3 / Quaternion 的限定曲线求值，以及 Vector3 / Quaternion 三通道 RLE 压缩 log；损坏数据明确报错并保留已有输出。

语法、曲线类型和限制见 [COMPATIBILITY.md](COMPATIBILITY.md)。验证范围见 [VALIDATION.md](VALIDATION.md)；历史章节保留各版本当时的状态。

v1.2.21 当时 **285 项兼容、20 项自动化、6 项挂载回归通过**，Plum 原始 QC 和材质保持不变。AxisInterp 支持反编译回环，并经原版重编译对照。数值、结构与实机证据见 [v1.2.21 验证报告](tests/reports/v1.2.21-validation.json)。

已在 **CSGO 1.38.8.1 / 8802** 离线 `de_dust2` 观察到 7 个 cloth21 样例加载、多骨变形及实体移动；另用零重力、相同可见壳的 4 个 sphere/capsule `contact_on/off` 样例确认可见碰撞响应差异。原生 AxisInterp 的 NP/stock 样例在同步的 0.5/1 秒名义相位画面一致，正向/inverse Twist 的正负方向播放正常，仍使用普通烘焙动画。地图重载后，上述 7 个布料、4 个接触对照及 4 个程序骨样例均成功重新载入。尚无逐帧接触、全部点无穿透或精确游戏骨角证明，也不代表与 stock 全量等价。

## v1.2.20 历史记录：FE 扩展、SubD 烘焙与 DMX 约束和动画

本节记录 v1.2.20 当时的四条编译路径；当前扩展见上文 v1.2.22 及两份作者指南：

- **FE 布料设置**：`$cloth { ... }` 支持阻尼/风力、跨面弯曲杆和刚性边铰链；DMX 新增动画吸引、节点碰撞半径和地面 maps。`gravity_scale 0` 转为节点重力为零，避开引擎把零比例恢复成 1 的旧默认值逻辑。`world_collision` 写出原生世界球体/胶囊碰撞开关、树和半径，实际碰撞仍需运行时提供碰撞体。
- **四边形 SubD 烘焙**：`$subd`、`$model name mesh.dmx subd` 或 DMX `subdivisionSurface=true` 默认执行两轮 Catmull-Clark，输出普通三角形；`$subd levels 1..3` 调整轮数。保留 UV 接缝、插值蒙皮和位置 morph，重算法线。`$subd native` 显式输出原生 patch，仅供已启用 SubD 的 renderer；已测试的 CSGO legacy 游戏/HLMV 在渲染原生 patch 时崩溃，编译器会提示警告。
- **CSGO 多目标 rig 约束烘焙**：`$datamodeljoints rig.dmx proceduralbones` 导入 Point / Orient / Aim / Parent，将多个目标、权重、偏移及 Aim 参数逐帧求解为普通骨骼动画；限 CSGO AppID 730 骨骼目标。引擎忽略的 8/9/10/12 记录仅保留为 rig 元数据，slave 不设 `BONE_ALWAYS_PROCEDURAL`。在 v1.2.20，Twist、依赖环、缺骨、原始 delta 输入及依赖运行时程序骨明确报错；当前已支持七类约束，见上文。
- **DMX 动画算子求值**：普通 `$sequence name anim.dmx` 可离线求值当前 clip 的多跳连接、表达式、Vector/Quaternion Pack/Unpack 和 Transform 算子，处理分层 log、阶梯片段及 clip 时间变换，再烘焙为普通骨骼帧。此路径适用于所有目标；在 v1.2.20，不支持的连接算子、压缩 log 和 curve-type 插值明确拒绝，后续扩展见当前 DMX 输入指南。

最终 Windows 本地 **248 项兼容、20 项自动化、6 项挂载测试**通过；Plum 原始 QC、供给材质以及游戏内布料、SubD 烘焙和约束动画验证见 [本版记录](tests/reports/v1.2.20-validation.json)。

这是限定范围的移植，具体语法、数值规则和拒绝项见 [COMPATIBILITY.md](COMPATIBILITY.md)。新增回归检查真实 MDL/VTX 数据、反编译再编译及动画数值；完整测试、生产模型和游戏内验证范围以 [VALIDATION.md](VALIDATION.md) 为准，文件加载或结构吻合本身不证明完整运行时行为一致。

以下版本章节保留当时的实现和验证状态；当前能力以 [v1.2.23 结账表](FIVE_COMPILER_COMPLETION.md)及“兼容边界与验证覆盖”为准。

## v1.2.19 历史记录：自动质量、追加碰撞源与 CSGO FE 布料

本节记录 v1.2.19 当时的范围；布料设置和 SubD 的后续扩展见上文 v1.2.20。

`$automass` / `$calculatemass` 现在按挂载的表面材质密度和壳厚计算质量，修复此前每个刚体被固定到 1 kg 的问题；支持 manifest、VPK/分卷、base 继承、后定义覆盖及 `$jointsurfaceprop`。MDL 与 PHY 写入一致的总质量。显式 `$mass` 的 PHY 分配规则保留，各刚体仍有参考的 1 kg 下限。

`$addconvexsrc` 支持同一行的 quoted `offset pos[...] angle[...] scale[...]` 与 `concave`，按物理坐标系处理变换和缩放；启用全局 `$concave` 时，标记为 concave 的源与主源合并后焊接，未标记的附加源保持独立凸体；未启用时所有几何合为一个凸体。不会修改共享的渲染源。

`$cloth proxy.dmx` / `$clothplanecollision planes.dmx` 新增真实 FE 数据输出，限 `-game` 检测到 CSGO AppID 730、扩展 VTX、骨骼模型。支持显式 `cloth_enable` 的三角形/四边形代理、固定点、节点约束、加权骨骼回算和骨骼绑定的无限单面碰撞平面；代理点总数上限 4096。在 v1.2.19，每个动态连通分量必须连接固定点，固定点须单骨绑定，同一骨骼不能兼作固定与动态控制，每个驱动骨须有至少三个非共线动态点。v1.2.19 当时拒绝 settings 块、未知 cloth maps 和其他游戏目标；当时未提供原生 SubD 和动态游戏内效果认证。当前固定点多权重、混合拟合与稀疏云规则见上文 v1.2.22 和布料指南；详细数据约定见 [COMPATIBILITY.md](COMPATIBILITY.md)。

Windows 本地 **209 项兼容回归、20 项自动化回归**通过，包含 6 项质量、6 项附加碰撞源和 10 项 FE 专项；另有 6 项 CONTENT 挂载回归通过。Plum 原始 QC 隔离编译/结构检查通过：126 骨骼、572,277 顶点、18 个物理体，MDL/PHY 总质量均为 30 kg，原 QC 哈希不变。CSGO HLMV 分别加载含碰撞平面的 quad/tri 布料样例各 15 秒，无访问异常，6 个临时游戏文件已清理。这验证加载稳定性，不代表游戏内布料运动或完整 CSGO 行为一致。复现范围见 [VALIDATION.md](VALIDATION.md)，本轮摘要见 [验证记录](tests/reports/v1.2.19-validation.json)。

原版 CSGO 默认材质四面体对照中，边长 10/20 的总质量分别为 5.462355/43.698837 kg，与当前工具相同到打印的 6 位小数。同几何布料对照中，固定点、逆质量、固定偏移及平面约束吻合；骨骼回算采用不同算法，尚不能据此认定变形等价。


## v1.2.18 历史记录：CSGO LOD 蒙皮与 CONTENT 挂载

CSGO legacy（gameinfo SteamAppId 730）的低 LOD 默认从根模型最近顶点获取蒙皮权重，距离相同时按 UV、法线和源索引选择；`$skinnedLODs` 保留低 LOD 自带权重。其他游戏保持原默认行为。查询使用空间索引，之后仍执行对应 LOD 的骨骼重映射。同时实现根 LOD 与更高 LOD 的两阶段容差匹配，检查位置、UV、法线、权重和切线；小型 UV 边界样例与安装目录中的原版 CSGO StudioMDL 对照一致，但不宣称任意模型逐字节相同。

`$contentrootrelative` 支持 CONTENT 路径中的 `*` / `?`、VPK 与分卷，目录内散文件先于归档，GAME 查找先于 CONTENT；未启用时不读取 CONTENT。187 项兼容回归、6 项挂载专项通过；Plum 与 Yvette 编译及结构检查通过。v1.2.18 没有新增游戏内验证；该版本当时尚未完成布料、完整 SubD 和完整骨骼折叠行为对照。

CSGO / MCV 目标还修正为 256 字节扩展头，保留 FE 指针槽（v1.2.18 当时为零），身体组预设写入正确偏移；其他目标保留原布局。两款游戏的预设样例分别通过 15 秒 HLMV 调试器监测，无访问异常，临时游戏文件已清理。这是布料序列化前置修正，不代表 FE 布料功能完成。

## v1.2.17 历史记录：启动信息说明修正

编译器和反编译器启动信息使用 `Source model toolchain`，移除固定 MDL 版本显示；本次不改变模型输出格式。

## v1.2.16 历史记录：CSGO / MCV 加载崩溃修复

`-game` 指向含 `gameinfo.txt` 的游戏目录时，SteamAppId 730（CSGO legacy）和 1012110（MCV）自动选择扩展 VTX：strip-group / strip 分别为 33 / 35 字节。此前默认的 25 / 27 字节布局会被这两款游戏错误解释，即使 MDL 都是 v49，HLMV 和游戏仍可能崩溃。其他目标保留旧默认值；显式 `$vtxformat` / pulseqc `vtx_archetype` 仍优先于检测，CLI `-vtxformat` 优先级最高。对这两个目标强制旧布局会警告。

同一个编译器即可输出这两个目标，不需要另外的编译器。编译时使用实际游戏目录，例如 `NewPageMergeMDL model.qc -game ".../csgo"` 或 `-game ".../vietnam"`；`-vtxformat 1` 只选择 VTX 布局；从 v1.2.18 起还会按 `-game` 目标选择 MDL 扩展头，因此 CSGO/MCV 编译应提供正确的游戏目录，即使另设 OutDir。CSGO 玩家模型保留 `player/custom_player/` 路径；测试时移到普通模型目录会触发旧动画流程，原 QC 无需添加额外玩家动画引用。部署完整的 `.mdl` / `.vvd` / `.dx90.vtx` / `.phy` 文件集，混用旧 VTX 仍会崩溃。

182 项兼容和 20 项自动化回归通过。Yvette 的身体与三份手臂 QC、MCV 的身体/手臂/腿部 QC 均重新编译，并用两款游戏各自的 HLMV 加载；七份输出各监测 15 秒，无访问异常。实际角色渲染及 Yvette 引用动画另经观察。MCV 在 mcv_camp / mcv_bridge 验证玩家、第一人称手臂、机器人、布娃娃及地图重载；CSGO 在 de_dust2 / ar_baggage 验证玩家/机器人、11 种皮肤 × 18 种身体组合（原生动态实体分批加载）、正常玩家死亡及地图重载。运行记录见 [v1.2.16 验证报告](tests/reports/v1.2.16-validation.json)。Plum 保持原布局，126 骨骼、572,277 顶点结构检查通过。这是指定模型和场景的覆盖，不代表所有游戏/模型已验证。

## v1.2.15 历史记录：CSGO 指令兼容（31 个入口；当时尚无布料输出）

本轮补上此前 33 个缺失入口中的 31 个，包含骨骼控制器与运行时标志、前缀/子串改名、绑定轴与骨骼中心、边界框策略、碰撞精度、源模型追加、附件重定义、CONTENT 路径查找、内部/物理文件名以及 OBJ 生成虚拟 VTA。实际写入 MDL/VVD/PHY；虚拟 VTA 支持 flexfile、原生 `$vta` 及 VCA，不产生中间文件，并拒绝帧间拓扑改变。

这不是 31 项新算法：`$externaltextures` 按参考行为警告并忽略；`$gamma` 在该 Source 编译流程中没有纹理处理用途；`$skinnedLODs` 对应本项目已有的逐 LOD 蒙皮保留行为；`$insertbone` 按参考中实际启用的代码只重新挂接，不创建插入骨骼；`$subd` 写入细分表面标志，不代表已移植完整四边形/SubD 导入流水线。

在 v1.2.15，`$cloth` 与 `$clothplanecollision` **当时尚未实现**并明确拒绝；v1.2.19 已新增上文所述的限定 FE 路径。它们需要有限元节点/约束/控制骨回解与 CSGO 扩展头数据，不能用 jigglebone 或保存一段 keyvalues 代替。19 项新增专项回归、181 项完整兼容测试、20 项自动化测试通过；Plum（126 骨骼、572,277 顶点）及 Yvette 编译/结构检查通过。本轮未做 CSGO 游戏内验证。详细语法和差异见 [COMPATIBILITY.md](COMPATIBILITY.md)，逐入口状态见 [验证记录](tests/reports/v1.2.15-validation.json)。

## v1.2.14 历史记录：CSGO QC 三角形顺序兼容

新增 `$preservetriangleorder`，实际跳过 meshoptimizer 缓存/过度绘制排序和 NvTriStrip 排序，采用参考编译器的深度优先边遍历顺序。开关优先于 `$UseLegacyStripify`；不改变骨骼调色板、flex 分组或格式设置，也不保证跨材质/分组保留源文件全局面顺序。32 面自制网格与 CE 输出顺序对照通过，并覆盖大小写、DX80/DX90、两种 VTX 格式、LOD 及 legacy 组合。用户 Yvette 原始 QC 编译通过（144 骨骼、65,902 顶点）；Plum 回归通过。162 项兼容、20 项自动化测试通过；未做 CSGO 游戏内验证。

## v1.2.13 历史记录：叛乱 2 / 军事冲突：越南 QC 修复

恢复传统单/双反斜杠续行宏，保留 `$endmacro` 语法；修复附件、命中盒及 hitgroup 使用 `$renamebone` 最终名称时的解析，并允许仅修改骨骼名称大小写。真实不同骨骼的重名仍报错。两份用户原始 QC/QCI 无需修改即可编译，MDL/VVD/VTX 结构检查通过；161 项兼容、20 项自动化回归通过。本轮不代表这两款游戏内表现已验证。

## v1.2.12 历史记录：反向分析补齐 CE LOD 选项

通过 CE x64 LOD 解析器的静态反汇编与自制模型对照，补齐 `$lod { replacemodel 原模型 替换模型 reverse }`。`reverse` 大小写不敏感，在命令同一行使用；仅翻转替换 LOD 的三角形绕序，保留导入法线，并隔离共享网格，避免影响其他 LOD。普通、reverse、混合大小写三组 CE 输出确认行为，DX80/DX90 回归检查后续普通 LOD 不被翻转。当时 158 项兼容、20 项自动化回归通过。

CE 日志中的 `replacemesh` 仍未确认：提供的 x86/x64 程序未找到该入口；x64 实际解析分支为 replacemodel/replacematerial/removemesh。不能把本轮补齐的 reverse 选项当作该日志条目已经实现。

## v1.2.11 历史记录：Assimp 路径的 glTF 动画插值

修复 `$NoFastGltf` 路径丢失 STEP 标记和 CUBICSPLINE 切线的问题。几何与蒙皮仍由 Assimp 导入，动画使用原始 glTF 采样器精确采样，不生成第二份几何。glTF/GLB/VRM 的 LINEAR、STEP、CUBICSPLINE 位移共 18 组双后端检查通过，另验证四元数、无名节点/动画，以及两个后端的缩放与形态键烘焙。当时 157 项兼容、20 项自动化回归通过；这不代表所有 Assimp 格式已验证。

## v1.2.10 历史记录：Neko 驱动骨父级兼容

修复 `$NekoDriverBone` 只采样局部姿态的问题：现在累积姿态动画的父级世界变换，再转换到最终模型父级的绑定空间，保留父级动画并支持姿态文件与模型的不同层级。姿态采样源不再定义模型骨架，命令写在 `$body` 前后均可。6 组自制参考案例（不同父级、父级动画、层级变化、缩放、重命名、多辅助骨）与 Neko 2.3.0 对照通过，12 组命令顺序回归通过。原生 `$driverbone` 采样语义保留。当时 154 项兼容、20 项自动化回归通过。

## v1.2.9 历史记录：Neko 形态键与输出故障保留

在 `$dmxcompatibility neko` 模式下，`$RenameMorph` 按 FBX/glTF 导入原名映射：区分大小写、缺失忽略、同名定义后者覆盖、不连续映射、不改写 QC 声明；命名 flex 块只保留声明的源键。native 全局重命名行为保留。多个源键映射到同名时明确报错。

v1.2.9 当时将输出全部暂存，检查写入、刷新及关闭，再备份并替换文件集；可处理的故障回滚。目录冲突和 Windows VTX 锁定测试确认旧文件不变；该版本没有强制终止后的恢复。153 项兼容、20 项自动化回归通过。v1.2.23 已增加持久日志和下次编译恢复；任意硬盘损坏或断电重排序仍不能保证无损。

## v1.2.8 历史记录：回归五编译器整合主线

补齐 Neko 历史 QC 指令 `$prefer_fbx`、`$forcecapsules` 的警告式接受，以及旧参数 `-usenvtristrip`。CE `$DontDestroy` / `-DontDestroy` 接入默认保留输出策略。前两者不改变导入或生成胶囊，符合 Neko 2.3.0 当前行为；旧 QC 不再因这些指令中断。150 项兼容回归通过。StudioMDL 2013 两包按同一编译器、不同依赖配置记录。

## v1.2.7 历史记录：参考面部模式与生产模型验证

新增 `$dmxcompatibility native|ce|neko`，保留默认行为并支持两种参考编译器的规则及控制器策略；CE/Neko 各 14 项对照一致。Claudia 在 GMod 使用真实材质验证面部变化、生成的减面 LOD 和布娃娃；Hair 两份原始 QC 继续通过编译。修复重复关节权重与宏报错来源，增加写出前及序列化文件检查，`-perfjson` 包含各处理阶段耗时。当时 146 项兼容回归、20 项自动化回归。详见 [IMPROVEMENTS.md](IMPROVEMENTS.md)。

## v1.2.6 历史记录：兼容、物理与发布验证

新增显式 copy weightlist、修复 jiggle 碰撞几何导致的布娃娃异常、改善 include 诊断和长场景动画采样性能。完整 Hair player/NPC 已在 GMod 检查；当时 138 项兼容回归、20 项自动化回归。七项结果及明确保留的问题见 [IMPROVEMENTS.md](IMPROVEMENTS.md)。

## v1.2.5 历史记录：Hair QC 编译修复

修正误拒绝有效 bodygroup 基数的检查；增加最终组合乘积与预设整数检查回归，当时共 128 项兼容测试。

## v1.2.4 历史记录：七项改进

- **资源挂载**：SearchPaths 顺序、`|appid_N|`、Steam 多游戏库、目录和 VPK v1/v2（预载/分卷）；`-steamdir` 指定 Steam 路径。
- **Draco glTF**：直接解码压缩几何及属性映射，保留 UV、法线和未压缩形态键；损坏数据明确失败。
- **动画烘焙**：`BakeSceneAnimation <clip> SceneSampleRate <fps>` 将缩放、蒙皮和形态键权重采样为顶点表情帧；输出 `.vertexanim.json` 并附带 GMod Lua 播放器，渲染边界覆盖全部采样帧。
- **布娃娃分解**：`$collisionjoints` 支持 `$decomposeconcave`，按骨骼分解凹形网格并保留质量、父子关系和约束。
- **骨骼与面部验证**：CE/Neko 六组差分比较层级、变换、IK/LOD、jiggle、DMX、控制器和眼睑绑定；修复 VTA 眼睑的多余描述符。既有 corrective/驱动骨/法线数值回归继续通过。
- **游戏实测**：GMod 验证 Alyx 加载、表情/眼睑、强制 LOD；自制样例验证顶点动画、双物理体质量和地面碰撞。白色材质覆盖用于几何检查，未认证用户材质的全部着色效果。
- **性能诊断**：`-perfjson` 报告加载/编译/写入耗时和峰值工作集；生产模型各三次隔离编译并检查输出 SHA256 一致。

v1.2.7 时为 **146 项兼容回归、20 项自动化测试**。参数、实测范围和复现方法见 [VALIDATION.md](VALIDATION.md)。

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

- 编译器、反编译器及辅助工具统一使用 NewPageMergeMDL 项目命名和当前项目版本号；编译器启动信息及重定向日志均为纯文本，不显示彩色横幅。
- 自动拉取 PulseModel、套用维护补丁，完成 Windows/Linux 构建与测试后发布 GitHub Release；冲突或检查失败停止发布。CE/++/Neko 的新增闭源功能仍需人工分析。
- v1.2.22 的历史结果为 325 项兼容、20 项自动化及 6 项挂载回归通过；测试检查实际模型输出。当前结果见 [VALIDATION.md](VALIDATION.md)。更早验证中，NekoMDL 的完整 `survivor_teenangst.qc` 通过混合 DMX/GLB 编译，用户的 Alyx QC 也成功编译。测试和发布包不包含用户模型或参考编译器二进制。

## v1.2.3 历史记录 缩减未完成项

- **同名材质合并**：模型级 `RenameMat` 支持多个材质指向同一名称；重建材质网格范围，同步三角形、表情顶点和面分组。验证六个顶点、两级 LOD 和 flex，其他身体组选项保持独立。
- **meshopt 压缩 glTF**：v1.2.3 快路径直接解码 ATTRIBUTES、TRIANGLES 和 INDICES 流，并应用 NONE / OCTAHEDRAL / QUATERNION / EXPONENTIAL / COLOR 滤波。当时实测 EXPONENTIAL 属性流及两种索引流，检查几何、UV、flex 和反编译动画；v1.2.23 已补齐 OCTAHEDRAL/QUATERNION/COLOR 的专项样例。量化滤波会保留源编码自身的误差。损坏流或非法范围会在写入前报错。
- **静态 GPU 实例**：展开无蒙皮的 `EXT_mesh_gpu_instancing`，共享解析后的网格；烘焙每个实例的平移、旋转和缩放，保留形态键与 InNode 子树筛选。验证旋转、镜像缩放及错误四元数；展开后的场景仍受源骨骼/节点数量上限约束。

v1.2.3 当时将“材质重命名合并不支持”从未完成表删除，并缩小 glTF 压缩/实例限制。游戏表现、Draco、AppID 挂载、动画缩放/权重和复杂 rig 差分是该版本当时的后续项目，后续版本已补实现与有界验收；当前结论见 [v1.2.23 结账表](FIVE_COMPILER_COMPLETION.md)。当时共 127 项兼容回归与 16 项自动发布测试。

## v1.2.2 历史记录 六项改进

- **Bodygroups**：组合数乘积使用 64 位计算，允许最多 2^31 种组合（body 值 0..2147483647）；31 个二选一组可编译，32 个会在写出前报错。固定单选组不再造成无意义的 preset mask 累加。
- **Skin groups**：在分配皮肤表前检查材质数 × 皮肤数 × 2 字节，应用文件格式及 `$MDLOutputBufferSize` / `$FileBufferSize` 限制；验证 1001 个皮肤及超限不改写已有输出。
- **全局裁剪**：`$UseLegacyClampMethod` 启用跨材质拆分，`$MaxVerts limit [clamp]` 的 limit 控制触发阈值、clamp 控制块大小（最多 65536）。每个 LOD 和 flex 增量随顶点重映射；额外 `_clamped` 身体组共享原组 base 和选项，包括缺失块的 blank，不会让隐藏选项的碎片继续显示。算法采用保守的三角形容量预留，作用于统一后的输出顶点，并非 CE 全部历史行为复刻。
- **复杂动画**：仅被 `localhierarchy` 引用的骨骼及新父骨骼不再被未使用骨骼裁剪/普通折叠丢掉；拒绝将骨骼临时设为自己的父骨。显式 `$alwayscollapse` 仍按原有规则优先。
- **DMX**：在法线合并和表情索引前检查位置、法线、UV、balance、speed 的角点索引数量与范围；扩展有限数值检查到 blendweights、balance、speed，输出具体错误原因。
- **碰撞**：使用 double 累加体积加权质量，防止大 mass bias 产生 NaN；拒绝非正偏置及不可表示的碰撞体积。单刚体 `$collisionmodel` 新增 `$decomposeconcave`，使用已有 VHACD 依赖分解封闭、连通的凹形网格，遵守正值 `$maxconvexpieces`；普通 `$concave` 保持原岛分割行为，v1.2.4 已补齐 ragdoll 分解。

**v1.2.5 修复**：修正完整 Hair QC 被过度严格检查阻止编译的问题。玩家和 NPC 两份原始 QC 均通过编译，分别输出 126 / 124 根骨骼和 572277 个顶点；不修改原始模型。检查实际写入的 bodygroup 基数和预设值，保留诊断。

## v1.2.1 历史记录 新增功能与修复

- `$UseLegacyStripify` / `-nvtristrip` 使用随源码附带的 NvTriStrip 后端；默认继续使用 meshoptimizer。验证 DX80/DX90、两种 VTX 布局、LOD 和跨硬件骨骼调色板的蒙皮映射。旧算法会移除重复及索引退化面。
- LOD 骨骼替换拒绝循环与冲突，正确解析连续替换；增加 IK 链、驱动骨、骨骼重命名和未使用骨骼折叠的联合输出测试。
- DMX 加载拒绝位置、法线、权重及动画数值中的 NaN/Inf；新增 corrective COMBO/DOMINATE 规则的数值求值测试，尚不代表所有复杂 rig 一致。
- 大位移或超长 RLE 动画自动采用帧编码，超出半精度范围的位置使用 float32；验证 255 帧重复段边界和动画分节。IK/局部层级压缩偏移超过 32767 字节时，在改写输出文件前报错。
- PHY 的长表面属性、根骨名称及合并名称不再被 512 字节临时缓冲截断。
- 动画压缩的范围扫描改为连续访问姿态。128 骨骼、1800 帧专项测试的三次运行中位数从 118.1 ms 降至 109.5 ms，四个输出文件 SHA256 一致；这是压缩阶段的局部测量。

NvTriStrip 来源与移植说明见 `libs/nvtristrip/SOURCE.md`；六项课题的验证范围及剩余工作见 [RESEARCH.md](RESEARCH.md)。

## v1.2.0 历史记录 新增验证与优化

- SMD/VTA 按行读取，去掉整文件的重复缓冲；拒绝无效父骨、非有限坐标以及越界/负权重，修复超过 16 个骨骼权重时的越界读取。
- 网格分割使用稀疏映射与已分配顶点标记。9000 顶点、分割上限 3 的专项测试从 300.7 ms 降至 15.8 ms，四个输出文件逐字节一致；这是极端小分割测试，不代表所有模型都获得同样提速。
- 实测编译 181,271,943 字节（172.88 MiB）、240 万条实际顶点记录的 VTA；加载优化后的峰值工作集从 880 MB 降至 376 MB，输出逐字节一致。`tests/stress_vta.py` 可独立复现。
- 已验证 130 个输出材质、512 个源骨骼折叠、256 个输出骨骼及最高编号骨骼动画；256 骨骼改用帧动画编码。**512 个最终输出骨骼仍未实现**：标准 MDL/VVD 有 8 位骨骼索引，超过 256 会在写入前明确报错。
- 增加 DMX 多骨骼形态键、网格分割后的 flex/LOD 和碰撞重命名/父子关系回归。用户提供的极限模型当时成功编译：126 骨骼、572277 个 VVD 顶点；后续 v1.2.6/v1.2.7 补充 GMod 几何与物理验证，当时的材质资源缺口已由 v1.2.8 Plum 验证补齐。
- 自动发布递增补丁版本，修复旧版标签识别。调查结果及尚未解决的课题见 [RESEARCH.md](RESEARCH.md)。

## 兼容边界与验证覆盖

以下按 v1.2.23 的实现整理，固定范围和验收结果以 [结账表](FIVE_COMPILER_COMPLETION.md)为准。固定的 11 项 CSGO 移植包已全部完成；本表记录运行条件及不可无限推广的验证边界，不再将这些边界拆为后续功能包。

| 内容 | 当前状态与边界 |
| --- | --- |
| CSGO 布料 | `flex_borders`、`prerotate`、混合拟合、多权重固定点、高级 FE、绳索及渲染蒙皮投影均已实现。仍限 CSGO AppID 730 骨骼/扩展 VTX；平面代理须同骨刚性绑定，稀疏回解须有效邻接基。世界碰撞需要游戏提供碰撞体，体积反馈需要 FitMatrix。高级碰撞无定量 A/B 或逐帧零穿透证明。详见 [布料指南](CSGO_CLOTH_AUTHORING.md)。 |
| SubD | 默认离线 Catmull-Clark 烘焙普通三角形，接收 authored DMX 四边形，轮数 1–3。原生 patch 必须显式 `$subd native` 且使用扩展 VTX；已测 CSGO legacy/HLMV 原生路径会崩溃。非流形、三角减面、顶点增长超限及不能可靠传播的 morph/融合部件数据明确拒绝。 |
| DMX rig 与动画求值 | Point/Orient/Aim/Parent/Rotation/IK/Twist 在统一图中烘焙；外部 rig 导入仍限 CSGO 目标，运行时 IK/混合及后续 QC 不重算作者约束，原始 delta、运行时程序骨依赖和 `$centerbonesonverts` 组合仍拒绝。已扩展值类型、倒放和嵌套时间线；压缩 log 仍限 Vector3/Quaternion，不包含完整 SFM 会话或轨道交叉混合。AxisInterp 不能表达的控制骨轴变换仍拒绝。详见 [DMX 指南](CSGO_DMX_INPUTS.md)。 |
| 参考证据 | 提供的 CE 两个架构均拒绝所测 `replacemesh` 语法；E1 以缺少有效参考证据结账，不虚构别名。2013 环境及实际容量已测，Neko 未冻结的历史格式宣传不能变成逐格式等价承诺。详见 [结账表](FIVE_COMPILER_COMPLETION.md)。 |
| 中断输出恢复 | 持久 journal、每输出进程锁、commit 标记和指纹检查已实现；进程被终止后，下次编译同模型会先恢复再读旧序列。损坏日志或外部改动保留并报错；不保证任意硬盘故障或断电重排序无损，也不提供读者视角的多文件瞬时原子替换。 |
| 蒙皮实例与网格状态 | 蒙皮 `EXT_mesh_gpu_instancing` 展开为独立骨骼、几何和动画，支持正的均匀实例缩放；非均匀缩放/剪切须先烘焙。[有限拓扑状态](MESH_STATE_WORKFLOW.md)通过 bodygroup 和随附 GMod 播放器切换，需要显式客户端消费。 |
| L4D2 运行时边界 | `2.2.4.3 build 10097` 的标准 `prop_dynamic` 已验证可创建 states/avatar/basic 三个模型并读取、切换 `mesh_state` bodygroup；三个实体均没有 `m_flexWeight`，所以标准实体路径不能直接消费顶点表情。需要 CBaseFlex、引擎扩展或游戏专用接口；这项证据不等于 GMod Lua 模块可在 L4D2 执行。 |
| VRM 运行时 | 已提供 VRM 0/1 命名表情、binary/override、材质适配、弹簧骨及球/胶囊碰撞的[准备工具与 GMod 模块](VRM_RUNTIME.md)。它是有界适配，需要匹配的 Source 材质；不自动执行 Unity/MToon，也不承诺任意场景逐帧或零穿透等价。 |
| 导入格式与插值 | FBX cluster bind、PMX 命名 morph、Assimp 关键帧/边界与 Collada STEP/LINEAR/BEZIER 已有固定验收；glTF STEP/CUBICSPLINE 保留。未能表达的切线需预烘焙。M3D/USD 内置，VRML 独立转换，C4D 限 Windows 辅助程序的可编辑多边形；见 [格式说明](O5_FORMAT_IMPORTS.md)。 |
| 复杂 rig 与碰撞覆盖 | 已验收 CE 多骨/控制器重映射、硬边/自定义法线、corrective/眼睑组合、Neko 多 studio/LOD 和九类骨规则组合，以及既有 IK/jiggle/按骨 VHACD。固定样例不构成任意层级或模型的全量参考等价。单骨权重仍按显式首影响策略处理。 |
| 跨游戏与性能 | 原始 Plum、自制模型、逐引擎运行及固定性能比较统一记录在 [当前验证](VALIDATION.md)。未安装的游戏不计通过；参考器输出骨数、索引覆盖或环境不同的尝试不计为同等输出性能比较。 |

v1.2.8 生产验证改用 Plum：原始 Hair QC 编译及文件结构检查通过；新增材质在 GMod 加载无缺失，28 个截图状态包含身体组、皮肤和表情，18 个布娃娃刚体稳定。首帧增加材质预热后复测通过。后续不再使用 Claudia 作为生产测试模型。详见 [v1.2.8 验证记录](tests/reports/v1.2.8-validation.json)。

已从问题清单移除：Draco/meshopt 解码、采样式缩放/形态键权重烘焙、NvTriStrip 与跨材质分割、动画大位移边界框修复、阶段耗时与输出完整性检查。显式 CE/Neko 面部模式已通过 28 项参考对照；`copy animation weightlist`、`match pos/rot`、条件语句和 `reverse` 已通过七个 StudioMDL++ 姿态/FPS 样例。验证范围见 [IMPROVEMENTS.md](IMPROVEMENTS.md) 和 [v1.2.7 验证记录](tests/reports/v1.2.7-validation.json)。

## 兼容性选择与使用条件

这些是使用条件或有意保留的实现差异，不属于未修复问题。

- 动画烘焙最多 4096 帧、1600 万个源顶点采样，精度取决于采样率；游戏播放需要控制器驱动代码。`gmtime` 的 UTC 同步也需要模组支持。
- 默认 `native` 面部行为保留 PulseModel 语义；需要参考面部策略时使用 `$dmxcompatibility ce|neko`。`$CEBoneRules` 需要显式启用。
- `$MaxVerts` 控制每材质输出网格分割，实际不超过 65536；`$FileBufferSize` 限制各输出文件字节数。本项目使用动态缓冲区与统一 LOD 顶点字典，不复现参考编译器的源文件预拆分或固定预分配。
- `NoAutoDMXRules` 按源禁用自动规则；需要清除先前自动控制器与规则时使用 `NoAutoDMXRulesLegacy`。`addcontrollerbyflex` 正确处理 min/max，不复现参考二进制的范围解析缺陷。
- 不承诺与参考 CE/++ 输出的完整文件逐字节相同。原有 `copy pos/rot` 属于本项目扩展。
- 自动同步合并 PulseModel 源码，冲突或测试失败会停止发布。CE/++ 更新由用户提供后手动分析与实现；VBSP、VVIS、VRAD、BSPZIP 地图工具不在本项目范围内。

完整语法与差异见 [COMPATIBILITY.md](COMPATIBILITY.md)，二进制调查记录见 [BINARY_ANALYSIS.md](BINARY_ANALYSIS.md)。

## 编译源码

Windows：在 Visual Studio 2022 的 x64 开发者终端中，准备 CMake 3.22+ 和 Ninja：

```powershell
cmake --preset x64-compact
cmake --build --preset x64-compact
```

输出位于 `out/build/x64-compact/NewPageMergeMDL/`。此预设使用 `MinSizeRel` 和 IPO/LTO，要求编译器、静态库工具与链接器均支持并匹配 LTO；Visual Studio 2022 的完整 x64 开发工具链满足此要求。日常开发可将预设改为 `x64-release`，使用普通 Release 构建。

Linux：准备 CMake，以及支持 LTO 的 GCC 或 Clang 完整 C/C++ 工具链：

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=MinSizeRel -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON
cmake --build build -j2
```

依赖库已包含在完整项目源码的 `libs/` 中，无需额外包管理器；二进制安装包不是完整构建树。使用 GCC 时应具备匹配的 LTO 插件与归档工具，Clang 则需匹配的 LLVM 归档工具及支持 LLVM LTO 的链接器。无需 LTO 的开发构建可改用 `-DCMAKE_BUILD_TYPE=Release -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF`。

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

v1.2.23 通过 369 项兼容、20 项自动化、9 项挂载、9 项 Lua、7 项 C4D 和 9 项输出恢复测试。测试使用临时 SMD/QC 和自制场景，检查实际 MDL/VVD/VTX/FE 文件，并反编译动画验证位移、旋转和分支行为。当前生产验证使用未改动的 Plum 原始 QC/材质，得到 126 骨骼、572,277 顶点、18 个物理体、30 kg 一致质量和 65 个无缺失材质；当前结果与运行验证范围见 [v1.2.23 结账表](FIVE_COMPILER_COMPLETION.md)及 [VALIDATION.md](VALIDATION.md)。

历史上已成功编译用户提供的 Alyx QC（113 根骨骼、27,571 个 VVD 顶点）。v1.2.4 另完成 GMod 几何、表情/眼睑与 LOD 验证。

## 来源与许可

原项目作者：Toppi。保留原 [MIT LICENSE](LICENSE) 与第三方库版权声明。
[UPSTREAM_README.md](UPSTREAM_README.md) 保存上游说明，含旧程序名称和旧下载地址，仅供参考。
本项目没有包含 StudioMDL-CE 或 Tools++ 的闭源二进制或源码。
