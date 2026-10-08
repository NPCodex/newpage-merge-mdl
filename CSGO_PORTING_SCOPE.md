# CSGO 固定移植范围：v1.2.22 完成清单

日期：2026-10-08。基线：v1.2.21 维护源码，CSGO 参考树 `f82112a2388b841d72cb62ca48ab1846dfcc11c8`。用户授权的 A1–A7 与 B1–B4 全部 11 包已完成实现与本轮验证。B 区保留原先“可选扩展”的来源分类，完成状态与 A 区相同，不再是待选或待实现范围。

这份清单固定本轮交付范围，区分参考编译路径、本工具开放的底层扩展与保留边界。不承诺穷尽尚未出现的模型缺陷，也不把整个游戏引擎或 SFM 编辑器作为移植目标。布料作者语法见 [CSGO_CLOTH_AUTHORING.md](CSGO_CLOTH_AUTHORING.md)。

顶层 QC 表核对：参考中 122 个未注释的指令名，在当前工具中均有入口；仅有名称覆盖不等于所有子选项、算法和复杂组合完全一致。此前的 33 个缺失入口已不再是剩余清单。

## A. 参考编译路径的 7 个功能包：全部完成

| ID | 固定子项 | v1.2.22 实现与验证 | 状态 |
| --- | --- | --- | --- |
| A1 | 布料及平面代理的 DMX `upAxis`；`$cloth prerotate` | 代理按各自 Y/Z-up 转到主模型绑定空间，覆盖 Y/Z 主模型与混合轴输入。`prerotate pitch yaw roll` 只旋转最终 FE InitPose 的位置和姿态，保留先前构造的局部约束；非零旋转结构对照及运行样例已覆盖。 | 完成 |
| A2 | `flex_borders`、固定/动态混合 Fit；固定点多权重、影响阈值、小点云回解策略 | 支持混合权重分区与固定边界自由旋转；固定点选最强父骨。`flex_borders` 默认 false，混合骨保持动画控制；启用后共同拟合。阈值默认 .05，小点云门限默认 3、可设 8，稀疏/共线云用邻接基回解。含不等静态权重的运行时中心规则验证及实机混合变形。 | 完成 |
| A3 | FE 四边形顺序修正、弯曲容差、动态弯曲 quad 短对角拆分 | 已接入 AdjustQuads 对应预处理，默认容差 .05；1 禁止弯曲拆分而保留顺序修正。交叉面修复、短对角线及输出 rest shape 有专项验证，退化和非流形检查保留。 | 完成 |
| A4 | Rotation/IK 与既有 Point/Orient/Aim/Parent/Twist 在 DMX 动画图中的依赖求值 | 已实现 Rotation、两段骨 IK、pole target/offset/weight 及连接图逐帧输入求值，烘焙普通骨骼动画。数值/依赖用例通过；CSGO 离线实跑观察到 Rotation/IK 改变姿态。运行时 IK/混合不会重新求解作者约束。 | 完成 |
| A5 | QAngle/VMatrix 日志与四个 Pack/Unpack 算子 | 两类值与四个转换算子已进入动画图求值；按正确 4×4 索引及输入/输出语义实现 VMatrix，保留对参考实现问题的修正。日志、连接及变换输出有数值验证。 | 完成 |
| A6 | DMX flex expression 的 `$变量$` 与 QC 上下文贯通 | 保留表达式并在有效 QC 变量上下文展开，无法解析明确报错，替代原来警告后丢弃整条规则的行为；变量作用域与输出规则有回归验证。 | 完成 |
| A7 | MouthShader 材质标记 | 已识别 VMT `$clientShader "MouthShader"`，写出对应 texture flags/used 与 VTX `MESH_IS_TEETH`，覆盖 skin family、材质重命名和输出标记。既有 `$mouth` 保留。 | 完成 |

A1–A7 均已落入实际输入、编译和输出路径。完成指这里固定的子项与验证范围，不代表所有 stock 模型、组合或逐帧游戏行为等价；没有具体输入或缺陷证据时，不自动增加新的移植包。

## B. 原可选底层扩展的 4 个功能包：已授权并全部完成

| ID | 固定子项 | v1.2.22 实现及来源区别 | 状态 |
| --- | --- | --- | --- |
| B1 | 双节点 stretch capsule；逐节点内部/外部 sphere、plane；collision mask；rigid stickiness | 通过本工具 `$cloth advanced` 作者接口输出真实 FE 碰撞记录。rigid sphere/capsule 与 stretch capsule 开放 stickiness；运行时不消费的逐节点 sphere/plane 粘附参数不开放。两端独立动画、骨改名/重新对齐和 mask 有结构验证；高级碰撞样例已在 CSGO 加载运行，尚无定量碰撞效果验证。 | 完成 |
| B2 | 显式 rod/spring、无面 rope 朝向、follow/FTL、局部平移/旋转、质量/倍率、体积反馈、平滑迭代、世界半径、legacy stretch/质量 damping/uninertial/OS offset | 已开放完整固定子项，写出运行时数组、标志和质量相关约束权重；兼容代理点、普通骨和显式虚拟节点。无面多骨绳链及 legacy 对照已实跑。高级作者语法、局部响应门控和运行边界见布料指南。 | 完成 |
| B3 | 最近表面投影、双侧体积、envelope、连通岛；无蒙皮代理/自动根骨 | 已生成独立点控制骨和最终渲染权重；envelope 错过保留原蒙皮。双侧绑定在三个最终权重内保留两侧比例；源骨折叠后检查最终格式上限。输出权重专项及 CSGO 多骨投射变形通过。参考 stock QC 固定 backsolved-joints-only，本入口明确属于工具扩展。 | 完成 |
| B4 | Color/String/Time 日志、Color Pack/Unpack、倒放采样、嵌套 clip 时间映射、FilmClip/track/shot 输入 | 已接入日志/算子与所列时间线输入，并烘焙普通动画；有采样、嵌套映射及连接图数值验证。扩展输入不等于实现完整 SFM 编辑器或会话运行时。 | 完成 |

## C. 已有实现的边界，集中记录，不另算新功能包

| 范围 | 当前保留的限制或差异 |
| --- | --- |
| FE 输入与策略 | 保留 4096 代理点、代理连通分量需锚定、有效邻接基、非流形/退化输入拒绝及显式 cloth_enable/共享属性一致性要求。固定点多权重和混合 Fit 已由 A2 实现，平面碰撞代理仍要求同骨刚性绑定。完整逐帧 stock 布料运动、全部点零穿透尚未证明。 |
| 高级 FE 的运行依赖 | 体积反馈需要 FitMatrix；世界碰撞体仍由游戏供给。局部平移默认继承全局值，逐节点不均匀且最大值为 1 时修正运行时入口门控，数组保留作者值。高级碰撞有结构和加载运行证据，不能扩大为定量接触效果证明。 |
| AxisInterp | 原生记录需要可表达的 cardinal 轴映射、正确父级和骨序；不可表达的轴/动画基变化明确拒绝。现有导入、写出、反编译回环和实机证据保留。 |
| Rig 烘焙组合 | A4 的 Rotation/IK 与图依赖已完成。原始 delta、运行时程序骨依赖及 centerbonesonverts 等组合仍有限制；后续 QC、运行时 IK/混合不会重新求解。其他组合按具体资产处理，不承诺通用实时 rig。 |
| SubD | 默认离线烘焙已完成。normal-only morph、融合源部件身份、三角形编辑后拓扑等仍受限制；原生 patch 的容量/valence 是格式或渲染器约束。扩展这些输入属于现有烘焙路径增强，不等于发现了新的 stock 功能。 |
| LOD、骨折叠、物理 | 根 LOD 权重、模糊顶点匹配、骨折叠、质量及附加碰撞源已有实现；复杂组合、PHY hull/drag、误差和字节级输出差异尚不等于全面一致。具体反例归缺陷处理，不重复列为未实现模块。 |
| 反编译回环 | AxisInterp/SubD 的已完成范围不自动代表 FE 作者代理或 rig 约束元数据都能完整还原。恢复作者级布料输入属于工具新增反编译能力，CSGO studiomdl 本身没有对应反编译器，故不列源码移植欠账。 |

## D. 明确排除的项目

- 已实现的 FE maps、NodeBase/ReverseOffset、自由旋转锚点、杆面、球/胶囊、无限平面、AxisInterp、Twist、Float/Vector3/Quaternion 曲线与压缩日志不再计数。
- `prerotate` 已按参考 write.cpp 的活跃写出阶段完成。此前仅查解析文件而称其“未使用”的判断已撤回，不再列为未实现或未接通选项。
- `reverse rig` 仅见枚举/属性赋值，参考 Operate 没有反向求解分支；不能视为现成算法。它与已完成的 inverse Twist 不同。
- UV mapping、collapse tiny edges、remove unused bones 等未接通选项；被注释的 OrientClothBones；Kelager/旧 FE edge；未实现的 spring Stretchiness；注释中的 cloth_plane_collision_enable，不作为成熟功能移植。
- `cloth_use_rods` 在参考中的转换是空分支；本项目已经给出明确实现，不再当作剩余工作。
- 保存的 channel OFF/PASS/RECORD：参考编译导入强制 CM_PLAY。log infinite 左/右边界是运行时状态，不能直接算漏读 DMX 属性。
- Source2 分支、游戏引擎运行时 solver/世界 hull 或 mesh 碰撞体供给、实时 IK/约束重算，以及已知会崩溃的原生 SubD renderer，均不纳入本轮编译器移植。默认离线 SubD 烘焙路径保留。
- SFM 编辑器、相机/音频/输入设备、Source2 ModelDoc、控制台主机输出、旧平台依赖和游戏本身，均不纳入当前 Windows/Linux Source1 模型工具范围。
- SIMD 打包、调度、碰撞树优化、增加测试数量，以及无固定资产边界的无限逐帧/逐字节对齐，不作为新的用户功能完成标准。

## 本轮验证与证据强度

- 最终 325 项 compatibility、20 项 automation、6 项 mount 验证通过。
- 原始 Plum 资产隔离编译与结构检查通过：126 骨、572277 顶点、18 个物理刚体、总质量 30 kg、65 材质；原输入保持不变。
- 10 个布料与 2 个 rig 样例已在 CSGO 离线实跑，覆盖代理/投射多骨变形、混合边界变形、高级碰撞可见壳与绳链，以及 Rotation/IK 姿态变化。
- `changelevel de_dust2` 后，10 个布料（READY10）和 2 个 rig（READY2）样例重新创建并经截图确认。6 项设置恢复后读回核对，正常 `quit` 后进程退出码为 0；62 个登记临时文件经哈希核对后删除。
- 高级碰撞目前只有加载/运行和序列化结构证据，尚无定量效果、全点零穿透或 stock 全量运动等价证明；重载通过不扩大这一证据范围。

详细验证记录见 [VALIDATION.md](VALIDATION.md)，作者输入见 [CSGO_CLOTH_AUTHORING.md](CSGO_CLOTH_AUTHORING.md)。

## 证据入口

参考链接固定到本次树版本；当前实现路径相对本仓库。

| 项目 | 参考 | 当前实现 |
| --- | --- | --- |
| A1 | [compileclothproxy.cpp:37](https://github.com/perilouswithadollarsign/cstrike15_src/blob/f82112a2388b841d72cb62ca48ab1846dfcc11c8/utils/studiomdl/compileclothproxy.cpp#L37)、[write.cpp:3653](https://github.com/perilouswithadollarsign/cstrike15_src/blob/f82112a2388b841d72cb62ca48ab1846dfcc11c8/utils/studiomdl/write.cpp#L3653) | [cloth.cpp](mdlcompiler/cloth.cpp)、[cloth_scope_cases.py](tests/cloth_scope_cases.py) |
| A2/A3 | 本地参考 compileclothproxy.cpp:248、617、679；femodelbuilder.cpp:1624、2858、2962 | [cloth.cpp](mdlcompiler/cloth.cpp)、[cloth_scope_cases.py](tests/cloth_scope_cases.py) |
| A4 | 本地参考 dmerigconstraintoperators.cpp:1382、1755、1844 | [dmxrig.cpp](mdlcompiler/dmxrig.cpp)、[dmxeval.cpp](mdlcompiler/dmxeval.cpp)、[procedural_scope_cases.py](tests/procedural_scope_cases.py) |
| A5/B4 | 本地参考 dmepackoperators.cpp:18、191、275；dmeunpackoperators.cpp:18、196、285；dmelog.cpp:9018 | [dmxeval.cpp](mdlcompiler/dmxeval.cpp)、[dmx_scope_cases.py](tests/dmx_scope_cases.py) |
| A6 | [studiomdl.cpp:6466](https://github.com/perilouswithadollarsign/cstrike15_src/blob/f82112a2388b841d72cb62ca48ab1846dfcc11c8/utils/studiomdl/studiomdl.cpp#L6466) | [dmxloader.cpp](mdlcompiler/dmxloader.cpp)、[qcloader.cpp](mdlcompiler/qcloader.cpp)、[csgo_closure_cases.py](tests/csgo_closure_cases.py) |
| A7 | [write.cpp:3248](https://github.com/perilouswithadollarsign/cstrike15_src/blob/f82112a2388b841d72cb62ca48ab1846dfcc11c8/utils/studiomdl/write.cpp#L3248)、[optimize.cpp:1975](https://github.com/perilouswithadollarsign/cstrike15_src/blob/f82112a2388b841d72cb62ca48ab1846dfcc11c8/utils/studiomdl/optimize.cpp#L1975) | [writevtx.cpp](mdlcompiler/writevtx.cpp)、[csgo_closure_cases.py](tests/csgo_closure_cases.py) |
| B1/B2 | 本地参考 authphysfx.cpp:1471–1583；femodelbuilder.cpp:265、873、1310、1381、1435、1775、1937、2113、2788、3049、3153；softbody.cpp:1591、2375、2583、2794、3074 | [clothadvanced.cpp](mdlcompiler/clothadvanced.cpp)、[cloth.cpp](mdlcompiler/cloth.cpp)、[cloth.h](libs/format/cloth.h)、[cloth_advanced_cases.py](tests/cloth_advanced_cases.py) |
| B3 | 本地参考 compileclothproxy.cpp:973、1103、1178；studiomdl.cpp:10991 | [clothprojection.cpp](mdlcompiler/clothprojection.cpp)、[cloth_projection_cases.py](tests/cloth_projection_cases.py) |

本地参考文件保存在原诊断工作区的 `.diagnostics/csgo-reference/`；顶层指令审计在 `.diagnostics/v1221-scope-qc-audit.json`。v1.2.21 的基线审计保留为历史证据；本清单记录 v1.2.22 的固定范围与完成状态。
