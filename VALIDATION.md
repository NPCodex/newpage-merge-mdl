# v1.2.23 当前验证

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
