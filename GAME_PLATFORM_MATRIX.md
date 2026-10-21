# 游戏与平台验收矩阵

本表区分**目标模型编译**与**实际游戏行为**。机器可读版本为
[game-platform-matrix.json](tests/reports/game-platform-matrix.json)，每个格子包含状态、
限定范围及证据引用。`passed_bounded` 只表示列出的模型、动作和构建，不能推导全部兼容；
`not_tested` 表示缺少充分证据，不表示已知不兼容。

当前开发源码为 v1.2.38。下列“历史”结果保留原报告版本与二进制身份，
**不算作本轮候选重新执行**。最新逐项进展见 [33 项台账](tests/reports/v1.2.38-improvements.md)。

| Windows 游戏目标 | 编译/加载与材质 | flex、LOD、IK/程序骨 | 物理与动画 | 证据边界 |
| --- | --- | --- | --- | --- |
| Garry's Mod | 历史 Plum/自制模型通过，材质有读回与画面 | 历史表情、LOD、程序骨/VRM spring 有界通过；不等于通用 IK | 历史 21 刚体 Plum 及自制播放通过 | [v1.2.12](tests/reports/v1.2.12-validation.json)、[v1.2.23](tests/reports/v1.2.23-validation.json)、[v1.2.29](tests/reports/v1.2.29-validation.json)；新固定步长/减帧尚无本轮游戏观察 |
| Left 4 Dead 2 | 历史三个自制模型加载、模型名读回及可见材质 | 所测 `prop_dynamic` 无 `m_flexWeight`；LOD、IK 未验收 | bodygroup 1→2 读回通过；新混合格点/pose 层的生产动作过渡未验收 | [历史实机与后续](tests/reports/v1.2.23-followup-runtime.json)；不能把 GMod 消费器视为 L4D2 通用接口 |
| CSGO legacy | 历史生产模型、皮肤/bodygroup 及自制模型通过 | 历史 Rotation/IK 可见运动；本表未登记 flex/LOD 的完整游戏验收 | 历史死亡、布料、持枪/移动姿态有界通过 | [布局/游戏](tests/reports/v1.2.16-validation.json)、[布料/程序骨](tests/reports/v1.2.22-validation.json)；无精确逐帧/全点无穿透认证 |
| Military Conflict: Vietnam | 历史 player/arms/legs 编译及模型显示通过 | flex、LOD、IK/程序骨未验收 | 历史第一人称/世界模型观察；ragdoll 模型名和原点读回，未做完整动力学检查 | [v1.2.16](tests/reports/v1.2.16-validation.json)，不能由相同 VTX 布局扩为其他引擎 |
| Insurgency | 历史三个模型编译；进入地图后未确认测试模型加载 | 未验收 | 未验收 | [历史记录](tests/reports/v1.2.23-validation.json)，游戏启动不是模型成功 |
| HL2 / CS:S / TF2 / SFM | 无本表可据以通过的目标实机证据 | 未验收 | 未验收 | 不从通用 Source 输出或其他游戏推导 |
| CS2 / AG2 | 历史 SAS 全人物与材质通过；本轮生成 view 图/自定义 helper 完整资源编译通过 | flex、LOD、通用 IK 未验收 | 历史手枪/步枪、射击/重载/蹲伏通过；本轮生成第一人称图及死亡布娃娃待实机 | [历史 SAS](tests/reports/ag2-gameplay-20261020.md)、[本轮资源验证](tests/reports/ag2-firstperson-v1238.md)；不是 Source1 MDL 编译 |

上述游戏的 **Linux 实机格子均为未测试**。Linux 编译器能够执行及生成结构合法文件，
不代表这些游戏已在 Linux 中加载它们。

| 工具平台 | 当前开发验证 | 保留的历史证据 |
| --- | --- | --- |
| Windows x64 | 本地 MSVC Release、动态 CRT、IPO 关闭；导入、缓存、USD 和 AG2 资源等定向回归通过。最终完整包与未完成 SDK/游戏验收另行记录。 | [v1.2.37 整包及 Plum](tests/reports/toolkit-fixes-20261020.md) |
| Linux x64 | 配置的最低验收系统为 Ubuntu 24.04，所需符号门槛 GLIBC 2.39 / GLIBCXX 3.4.32 / CXXABI 1.3.15；本轮最终候选运行待验收。 | v1.2.37 GCC/Clang 各 421 项及整包检查：[CI](https://github.com/NPCodex/newpage-merge-mdl/actions/runs/39411422872) |

更新规则：只在保存了对应版本/程序身份、样本、实际检查和限制后更新单个格子。
资源级、数学/API 桩、编译产物和实际引擎运行分别记录；截图或工具启动不能替代其他层级。
用户模型、游戏资产与参考编译器不进入源码或安装包。
