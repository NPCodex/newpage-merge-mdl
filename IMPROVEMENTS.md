# v1.2.6：七项改进与实际验证 / Seven improvement areas

这是一轮兼容、性能和验证改进，不代表所有参考编译器及游戏行为已经完全一致。
This release improves compatibility, performance and verification; remaining
differences are listed explicitly below.

| 方向 / Area | 本轮结果 / Result |
| --- | --- |
| 完整生产模型 / Production models | 原始 Hair player/NPC QC 编译并进入 GMod；两份共 50 个身体组、皮肤、表情及 LOD 状态检查。材质缺失，未认证完整着色效果。Hair QC 未定义额外 LOD，强制 LOD 请求仅作加载检查；真实多 LOD 切换另有自制夹具验证。 |
| 复杂面部与骨骼 / Facial and bone compatibility | CE/Neko 各 10 个样例，新增多 DMX、立体表情、IK/LOD/jiggle/attachment 联合场景，并比较实际规则操作。20 项对照中 16 项语义一致，4 项存在下述差异。 |
| 动画语义 / Animation semantics | 增加 StudioMDL++ 的显式 `copy animation weightlist`；正权重作选择掩码，不插值。七个参考样例的解码姿态及 FPS 一致。原有 `copy animation [pos] [rot]` 扩展保留。 |
| 场景导入 / Scene import | 验证共享同一 skin 的多个 glTF/VRM 节点；拒绝冲突的共享关节 bind pose、奇异 inverse-bind 和无效时间轴。增加自制 FBX 层级、非均匀缩放和法线回归。 |
| 诊断 / Diagnostics | 保留命令的文件来源，修复 include 末尾报错被错误归到根 QC 的问题；显示 include 祖先；bodygroup 编译阶段报错保留 QCI 行号；碰撞合并循环明确报错。 |
| 性能 / Performance | glTF sampler 数据在一次加载中解包一次；共享转换器改用二分查找关键帧。64 通道、3000 关键帧专项三次中位数从 11.11 s 降至 1.92 s，输出 SHA256 一致。完整 Hair 模型未取得可宣称的提速。 |
| 发布质量 / Release quality | 自动及人工发布均验证实际 ZIP 内的编译器/反编译器、版本、源码来源和运行文件，解压后重跑兼容套件。人工流程改用项目版本；Linux 失败会阻止发布。增加自制 90000 顶点、三 LOD、20 皮肤回归，不分发用户素材。 |

## 生产模型物理修复 / Production ragdoll fix

完整 Hair 模型原来为 jiggle 头发骨骼创建三个额外独立物理体，在实际游戏中产生
数千单位水平位移。现在将这种骨骼的碰撞几何合入物理祖先，同时保留渲染骨骼和
jiggle 数据；显式 joint merge 也按链解析，拒绝循环。

实际 GMod 对照：玩家和 NPC 均为 18 个物理体；十秒后的最大水平位移分别约为
36.86、34.61，速度为零。CE 编译同一玩家模型为 18 个物理体，位移约为 49.14。
这些是当前模型和测试地图的结果，不是所有布娃娃的稳定性保证。

Procedural collision geometry is folded into physical ancestors while keeping
render/jiggle bones. Both supplied models settle with 18 bodies; the CE reference
also has 18. Joint-merge chains are resolved and cycles rejected.

## 仍需处理 / Remaining work

- 当前模型输入目录没有 VMT/VTF，游戏报告缺失材质。几何、选择和物理已检查，完整
  材质渲染仍需对应资源；截图和用户模型仅保留在本机。
- CE 对照的自动 DMX 规则及多 DMX 重复控制器存在差异；Neko 对照的显式 DMX 规则
  及多 DMX 重复控制器存在差异。报告保留差异，不计作通过。项目的控制器去重和
  自动规则行为暂时保留，需要进一步结合真实面部模型确认。
- EXT_mesh_gpu_instancing 的蒙皮扩展、网格动画切换、完整 VRM 专有语义及任意复杂
  FBX/面部层级仍未完成。共享 skin 的普通节点测试不等同于该扩展支持。
- 本轮未认证所有生产动画、实际 shader、启用 jiggle 模拟时的所有显示状态及其他游戏。

The missing-material and remaining DMX-rule/controller differences are recorded
as unresolved. Skinned GPU instancing, mesh swaps and complete VRM-specific
semantics remain open. No blanket engine-compatibility claim is made.

## 复现 / Reproduction

```powershell
python tests/compatibility.py path/to/NewPageMergeMDL.exe
python -m unittest discover -s tests -p test_automation.py
python tests/reference_animation_differential.py compiler.exe --reference studiomdl++.exe --decompiler decompiler.exe --work isolated-animation
python tests/reference_differential.py compiler.exe --reference reference.exe --work isolated-face
python tests/prepare_production_game.py compiler.exe --qc player.qc --qc npc.qc --game game-directory --work isolated-game
python tests/verify_production_game.py game-directory/data/newpage_production_validation --output report.json
```

`reference_differential.py` 发现差异时返回非零，并写出报告。
生产游戏测试安装明确命名的临时 autorun；结束游戏后删除
`lua/autorun/server/newpage_production_validation.lua`，避免正常游戏启动时运行测试。
数据摘要见 `tests/reports/v1.2.6-validation.json`。
