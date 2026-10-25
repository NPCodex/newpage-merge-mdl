# 游戏与平台验收矩阵

本表区分**目标模型编译**与**实际游戏行为**。机器可读版本为
[game-platform-matrix.json](tests/reports/game-platform-matrix.json)，每个格子包含状态、
限定范围及证据引用。`passed_bounded` 只表示列出的模型、动作和构建，不能推导全部兼容；
`not_tested` 表示缺少充分证据，不表示已知不兼容。

当前源码为 v1.3.0。历史观察保留原版本与程序身份，**不算作 v1.3.0 重新执行**。
六项改进见 [v1.3.0 台账](tests/reports/v1.3.0-work.md)。下表未新增证据的项目均为历史结果；
v1.2.38 的结果只覆盖原报告的测试日期与输入。

| Windows 游戏目标 | 编译/加载与材质 | flex、LOD、IK/程序骨 | 物理与动画 | 证据边界 |
| --- | --- | --- | --- | --- |
| Garry's Mod | v1.2.38 自制模型加载、材质与网格状态通过；历史 Plum 结果单列 | v1.2.38 表情、LOD、程序骨及固定步长 spring 回调通过；不等于通用 IK | v1.2.38 双刚体与自制播放通过；历史 Plum 21 刚体保留原证据 | [v1.2.38 实机](tests/reports/v1.2.38-gmod-runtime.md)：2026.10.19 引擎，6 客户端/2 服务端检查；实际回调约 237 Hz，四档帧率是独立 Lua 数值测试 |
| Left 4 Dead 2 | v1.3.0 实际 Zoey 玩家使用完整 Rochelle 重定向模型；材质旧证据保留 | 本次未认证 flex、LOD 或通用 IK | 实际步行/跑步/蹲伏、步枪/手枪射击与重装；204 个不同 tick 样本，挂点读回及 L4N 双向重载通过 | [v1.3.0 实机](tests/reports/v1.3.0-gameplay.md)：2.2.4.3/build10097。需临时隔离已有 Necola bridge 启动崩溃；测试后已恢复。fallback 挂点父骨警告仍有，非全部活动/插件/物理认证 |
| CSGO legacy | 历史生产模型、皮肤/bodygroup 及自制模型通过 | 历史 Rotation/IK 可见运动；本表未登记 flex/LOD 的完整游戏验收 | 历史死亡、布料、持枪/移动姿态有界通过 | [布局/游戏](tests/reports/v1.2.16-validation.json)、[布料/程序骨](tests/reports/v1.2.22-validation.json)；无精确逐帧/全点无穿透认证 |
| Military Conflict: Vietnam | 历史 player/arms/legs 编译及模型显示通过 | flex、LOD、IK/程序骨未验收 | 历史第一人称/世界模型观察；ragdoll 模型名和原点读回，未做完整动力学检查 | [v1.2.16](tests/reports/v1.2.16-validation.json)，不能由相同 VTX 布局扩为其他引擎 |
| Insurgency | 历史三个模型编译；进入地图后未确认测试模型加载 | 未验收 | 未验收 | [历史记录](tests/reports/v1.2.23-validation.json)，游戏启动不是模型成功 |
| HL2 / CS:S / TF2 / SFM | 无本表可据以通过的目标实机证据 | 未验收 | 未验收 | 不从通用 Source 输出或其他游戏推导 |
| CS2 / AG2 | v1.2.38 1.1 倍 SAS、helper 和生成 world/UI/view 图加载，完整人物材质可见 | flex、LOD、通用 IK 未验收 | AWP/M4A4/Desert Eagle 持握、射击/重载、M4A4 inspect、蹲伏/站立通过；补齐诊断模型关节后死亡倒地 | [资源验证](tests/reports/ag2-firstperson-v1238.md)、[v1.2.38 实机](tests/reports/ag2-gameplay-v1238.md)：1.41.9.1/build10924；不是所有武器/任意骨架认证，不自动重建模型物理 |

上述游戏的 **Linux 实机格子均为未测试**。Linux 编译器能够执行及生成结构合法文件，
不代表这些游戏已在 Linux 中加载它们。

| 工具平台 | v1.3.0 验证来源 | 保留的历史证据 |
| --- | --- | --- |
| Windows x64 | 本地 MSVC Release 的完整兼容、报告恢复、导入及 Medusa 结果见[台账](tests/reports/v1.3.0-work.md)。发行包在 CI 中重新执行完整包门禁，具体源码与资产散列见对应 Release；本地程序不冒充最终包。 | [v1.2.38 双平台候选](tests/reports/v1.2.38-candidate.md)、[v1.2.37](tests/reports/toolkit-fixes-20261020.md) |
| Linux x64 | 本机没有可用 Linux 运行环境；正式发布受 GCC/Clang、Ubuntu24.04 运行基线、符号、sanitizer、复现和整包门禁约束。实际完成状态见[v1.3.0 Release](https://github.com/NPCodex/newpage-merge-mdl/releases/tag/v1.3.0)。 | [v1.2.38 构建证据](tests/reports/v1.2.38-build-quality.md)，不替代本次 CI |

当前 `insurgency2` 目录内入口 EXE/DLL 为 1 字节占位文件，不能启动实际游戏，
因此保留 Insurgency 的未验收状态；不把目录存在当作安装可用。

更新规则：只在保存了对应版本/程序身份、样本、实际检查和限制后更新单个格子。
资源级、数学/API 桩、编译产物和实际引擎运行分别记录；截图或工具启动不能替代其他层级。
用户模型、游戏资产与参考编译器不进入源码或安装包。
