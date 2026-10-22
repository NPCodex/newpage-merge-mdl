# 游戏与平台验收矩阵

本表区分**目标模型编译**与**实际游戏行为**。机器可读版本为
[game-platform-matrix.json](tests/reports/game-platform-matrix.json)，每个格子包含状态、
限定范围及证据引用。`passed_bounded` 只表示列出的模型、动作和构建，不能推导全部兼容；
`not_tested` 表示缺少充分证据，不表示已知不兼容。

当前开发源码为 v1.2.38。下列“历史”结果保留原报告版本与二进制身份，
**不算作本轮候选重新执行**。最新逐项进展见 [33 项台账](tests/reports/v1.2.38-improvements.md)。

| Windows 游戏目标 | 编译/加载与材质 | flex、LOD、IK/程序骨 | 物理与动画 | 证据边界 |
| --- | --- | --- | --- | --- |
| Garry's Mod | 本轮自制模型加载、材质与网格状态通过；历史 Plum 结果单列 | 本轮表情、LOD、程序骨及固定步长 spring 回调通过；不等于通用 IK | 本轮双刚体与自制播放通过；历史 Plum 21 刚体保留原证据 | [本轮实机](tests/reports/v1.2.38-gmod-runtime.md)：2026.10.19 引擎，6 客户端/2 服务端检查；实际回调约 237 Hz，四档帧率是独立 Lua 数值测试 |
| Left 4 Dead 2 | 本轮完整 Rochelle 网格加载，四个固定位置人物材质可见 | 历史所测 `prop_dynamic` 无 `m_flexWeight`；本轮不验收 flex、LOD、IK | 四种活动的移动/瞄准参数连续更新 240 次，192 条有限附件采样、0 失败 | [本轮离线与实机](tests/reports/v1.2.38-l4d-production.md)：2.2.4.3/build10097；不扩为完整幸存者玩法、活动切换、武器附着、物理或游戏 pose-envelope 验收 |
| CSGO legacy | 历史生产模型、皮肤/bodygroup 及自制模型通过 | 历史 Rotation/IK 可见运动；本表未登记 flex/LOD 的完整游戏验收 | 历史死亡、布料、持枪/移动姿态有界通过 | [布局/游戏](tests/reports/v1.2.16-validation.json)、[布料/程序骨](tests/reports/v1.2.22-validation.json)；无精确逐帧/全点无穿透认证 |
| Military Conflict: Vietnam | 历史 player/arms/legs 编译及模型显示通过 | flex、LOD、IK/程序骨未验收 | 历史第一人称/世界模型观察；ragdoll 模型名和原点读回，未做完整动力学检查 | [v1.2.16](tests/reports/v1.2.16-validation.json)，不能由相同 VTX 布局扩为其他引擎 |
| Insurgency | 历史三个模型编译；进入地图后未确认测试模型加载 | 未验收 | 未验收 | [历史记录](tests/reports/v1.2.23-validation.json)，游戏启动不是模型成功 |
| HL2 / CS:S / TF2 / SFM | 无本表可据以通过的目标实机证据 | 未验收 | 未验收 | 不从通用 Source 输出或其他游戏推导 |
| CS2 / AG2 | 本轮 1.1 倍 SAS、helper 和生成 world/UI/view 图加载，完整人物材质可见 | flex、LOD、通用 IK 未验收 | AWP/M4A4/Desert Eagle 持握、射击/重载、M4A4 inspect、蹲伏/站立通过；补齐诊断模型关节后死亡倒地 | [资源验证](tests/reports/ag2-firstperson-v1238.md)、[本轮实机](tests/reports/ag2-gameplay-v1238.md)：1.41.9.1/build10924；不是所有武器/任意骨架认证，不自动重建模型物理 |

上述游戏的 **Linux 实机格子均为未测试**。Linux 编译器能够执行及生成结构合法文件，
不代表这些游戏已在 Linux 中加载它们。

| 工具平台 | 当前开发验证 | 保留的历史证据 |
| --- | --- | --- |
| Windows x64 | `ddea46e` 的 MSVC Release完整候选包、446项兼容与19项往返通过，下载后核对源码、清单及符号通过，见[候选报告](tests/reports/v1.2.38-candidate.md)。本地功能、真实C4D和游戏观察保留各自程序身份；此前复现检查见[构建报告](tests/reports/v1.2.38-build-quality.md)。 | [v1.2.37 整包及 Plum](tests/reports/toolkit-fixes-20261020.md) |
| Linux x64 | `ddea46e` 的 GCC/Clang 各执行446项兼容用例（444通过、2项Windows专属跳过）与19项往返，完整包和Ubuntu24.04运行检查通过；符号门槛GLIBC2.39 / GLIBCXX3.4.32 / CXXABI1.3.15。`2317571` 的240次sanitizer与复现结果保留在[构建报告](tests/reports/v1.2.38-build-quality.md)，最终文件身份见[候选报告](tests/reports/v1.2.38-candidate.md)。 | v1.2.37 GCC/Clang 各421项及整包检查：[CI](https://github.com/NPCodex/newpage-merge-mdl/actions/runs/39411422872) |

更新规则：只在保存了对应版本/程序身份、样本、实际检查和限制后更新单个格子。
资源级、数学/API 桩、编译产物和实际引擎运行分别记录；截图或工具启动不能替代其他层级。
用户模型、游戏资产与参考编译器不进入源码或安装包。
