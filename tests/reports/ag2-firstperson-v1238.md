# AG2 第一人称与自定义骨架：资源验证

状态：生成图、完整模型资源和数值回归已通过；本报告不包含真实游戏动作验收。
资源级成功不能代替手持武器、重载、蹲伏、附件、死亡布娃娃的游戏表现。

## 实现与发现

- KV3 job 新增 `first_person=true`，必须显式提供 arms `model_dmx`。
  输出独立 `<model>_viewmodel` 目录，引用安装中的 viewmodel 图及骨架。
  `write_model` 仅修改已有启用的 `hudmodel` AnimGraph2 文件名。
  不改变模型的 body/UI 绑定及模型骨架；完整人物可以分别运行 body 和 arms job。
- 第一人称 wrapper 保留官方图的 20 个控制参数，链为
  `ReferencedGraph(viewmodel) → LayerBlend(Additive, weight=1)`。
  此链不添加世界模型的 SnapWeapon 节点。
- 实际安装的 viewmodel 图将上臂拆为 shoulder/straighten 辅助节点，且上臂分支反向。
  初始试验仅复用 body 重挂算法时，前臂平移错误达到约 70.47 单位；虽然 RC 接受，
  数值检查判定不合格。修正为从原 arms rig 的模型空间关节距离计算真实上臂长度，
  在 stock 局部轴上驱动两条对应分支，保留图的 shoulder 位置。
  修正后的 1.1 倍样本最大平移为 1.17859554，符合上臂长度差。
- 自制非 stock Bone 节点暴露了已有 write_model 问题：原节点被删，生成的
  SkeletonFile 默认禁用，导致最终模型丢失 helper。现生成 Bone 节点时也携带用户
  自定义节点及必要祖先。完整模型 RC 输出中已确认该 helper 存在。

## 样本与结果

使用已安装 CS2 的 SAS 全网格源资产副本，所有五个网格 import_scale=1.1。
显式 arms 源为 `ctm_sas_firstperson_default_gloves_arms2.dmx`；world 源为
`ctm_sas_thirdperson_body.dmx`。自定义样本额外加入
`npmdl_validation_helper` Bone，位移 `[3,0,0]`，`do_not_discard=true`。
这是有限的 CS2 命名骨架变体，不代表任意自定义骨架/绑定轴都可自动适配。

| 候选 | 模型骨数 | 已生成绑定 | 资源编译 |
| --- | ---: | --- | --- |
| firstperson | 94 | hudmodel；body/UI 为官方图 | 完整 VMDL：1 compiled / 0 failed |
| custom | 98 | worldmodel、uimodel、hudmodel | 完整 VMDL：1 compiled / 0 failed；自定义 helper 保留 |

两者 view clip 均为 56 条静态轨，44 条非零平移，恒等旋转；最大平移
1.17859554。Graph 使用 `animation/skeletons/characters/viewmodel.vnmskel`。
custom 的 world clip 为 75 条静态轨。结构解码核对了实际 `_c` 资源。

独立断言：

- ModelDoc 修改前后按 KV3 结构比较，first_person 仅改变 hudmodel filename。
- 缺少显式 arms 或启用的 hudmodel 返回失败，原模型及旧输出不被替换。
- generate-only 清理本模式生成的旧 `_c`，保留 body 输出及用户文件；随后 full 模式
  成功重新编译两个 view 资源。
- `tests/ag2_view_pose_test.cpp` 使用 arms-only 合成 rig，验证左右不同上臂长度、
  两条图分支、前臂长度、任意源原点平移不影响比例，以及退化上臂拒绝。
- 旧 world/UI 流程的八项真实 RC/事务回归通过：stock、改变比例、generate-only
  首跑/重跑、缺编译器、exit 37、Windows sharing violation 回滚、旧输出作输入。
  安装文件检查前后 SHA256 相同。此次回归不新增强杀/断电保证。

## 可复核材料

本机诊断目录：`C:/Users/Kud/Desktop/CODEMDL/.diagnostics/ag2-firstperson-v1238`。
`final-summary.json`、`summary.json`、`*-final.json`、`*-final.log` 对应最终候选；
无 `final` 后缀的初期资源转储可能保留已修正的失败试验，不可当最终结果。
旧 world/UI 八项回归位于 `.diagnostics/ag2-regression-v1238/summary.json`。

最终 AG2 开发二进制 SHA256：
`251469ffdaf568f9878ca229da788cf5e36191088bd47f03b2146c5a5342c683`。
该哈希仅标识本次开发验证产物，最终发布构建应重新记录自己的 manifest。

完整游戏候选位于 CS2 `content/csgo_addons/` 及 `game/csgo_addons/` 的：

- `npmdl_ag2_firstperson_v1238`
- `npmdl_ag2_custom_v1238`

两者逻辑模型路径均为 `agents/models/ctm_sas/ctm_sas.vmdl`。
custom 编译模型 SHA256：
`f5513b848639c515e9450b2343f2841cd832eda4d435f5a52c5a3f525d88ff3d`。
原始游戏 VPK、官方安装工具及用户原始资产均未被替换。Valve 资产不进入源码或发布包。

后续[本轮实机报告](ag2-gameplay-v1238.md)记录生成图在 AWP/M4A4/Desert Eagle 的
握持、射击、重载及 M4A4 inspect，完整人物蹲伏和修复测试模型物理数据后的死亡
布娃娃。其范围是明确列出的动作与模型，不是任意武器附件或骨架认证。
