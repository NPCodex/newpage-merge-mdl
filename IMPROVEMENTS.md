# v1.2.7：六项改进结果 / Six improvement areas

这一轮解决已记录的参考面部差异，并扩大真实游戏和输出完整性验证。
历史记录保留在 README、VALIDATION 和 `tests/reports/v1.2.6-validation.json`。

| 方向 / Area | 当前结果 / Result |
| --- | --- |
| 4 项 DMX 差异 | 新增 `$dmxcompatibility native/ce/neko`。CE 不生成普通自动组合规则；Neko 保留重复规则；参考模式保留按 body 注册的控制器。CE/Neko 各 14 项对照一致，包含先前 4 项差异。默认 native 行为保留。 |
| 实际游戏表现 | Claudia 使用原有 VMT/VTF，隔离复制材质并重写引用，不覆盖现有资源。6 个截图状态验证真实材质、面部与生成的减面 LOD；18 个物理体稳定。Hair 两份原始 QC 仍可编译，材质缺失未被替代材质掩盖。 |
| 复杂骨骼与面部 | 新增面部+IK/LOD/attachment/jiggle、立体表情联合 rig、描述符依赖与眼睑联合 rig；比较实际规则操作、层级、变换、控制器和眼睑绑定。已有 corrective/驱动骨数值回归保留。 |
| 场景导入 | 重复关节在多个 JOINTS/WEIGHTS 流中的权重先合并再筛选；负数和非有限 glTF 蒙皮权重明确失败。glTF/GLB/VRM 验证共享 morph mesh 的节点默认权重及采样烘焙。缩放/权重动画继续通过 BakeSceneAnimation 输出。 |
| 性能 | 缩放关键帧验证从每个采样帧移到循环外。64 通道、3000 原始关键帧专项三次中位数从 v1.2.6 的 1.893 s 降至 0.317 s，输出 SHA256 一致。JSON 增加逐处理阶段耗时与调用次数；生产模型记录峰值工作集。 |
| 诊断与输出检查 | 宏错误指向定义文件行号，并列出嵌套调用链。写出前检查非有限几何、蒙皮、循环父链、身体组、LOD 与 flex 索引；独立检查实际 MDL/VVD/VTX 的表范围、层级、索引、顶点数及校验值。破损文件回归验证检查器拒绝错误。 |

## 使用 / Usage

```qc
$dmxcompatibility native // default, preserves project behavior
// $dmxcompatibility ce
// $dmxcompatibility neko
```

参考模式设置 `$flexcullmethod none`，后续显式 `$flexcullmethod` 可覆盖。
生成的场景烘焙播放规则不会被 CE 模式取消。这是面部注册策略选择，
不是整个编译器的版本切换或所有模型的逐字节一致保证。

Reference profiles select distinct flex registration policies. Native remains
the default. CE omits ordinary automatic combination rules, while Neko preserves
repeated rules; both preserve per-body controllers. Generated baked-scene rules
survive all modes. A later explicit flex-culling command can override the profile.

## 真实模型与性能证据 / Production evidence

- Claudia：113 根输出骨骼、27571 个 VVD 顶点。隔离测试脚本添加
  `decimateallmodel 0.5`：GMod 读取 28623 / 14305 个三角形。
  这是生成的测试 LOD，输入未附带作者提供的低模。
- 面部近景：表情改变 22959 个像素，重复中性截图改变 2192 个像素，
  超过 `4 * noise + 100`。截图检查眼睛、皮肤、衣服和头发，没有缺失材质；
  未宣称所有 shader、灯光或其他游戏均经过认证。
- 布娃娃：18 个物理体，最终速度为零，最大水平位移约 46.39。
- 原始 Hair player/NPC QC：各三次隔离输出，SHA256 稳定，与 v1.2.6
  的生产输出相同。中位数约 5.83 / 4.97 s；Claudia 约 0.456 s。
  不宣称这些生产模型已取得显著提速。
- 146 项兼容回归与 20 项自动化回归；实际发布包还会重跑兼容套件。
  用户模型、材质、截图及参考编译器不分发。

Claudia is verified with real materials, facial changes, a generated decimated
LOD and stable ragdoll physics in GMod. The long-scene benchmark improves from
1.893 s to 0.317 s with identical output. Both complete Hair inputs remain
deterministic; no significant production-model speedup is claimed.

## 仍需具体处理的范围 / Remaining scope

- Hair 材质仍未找到；Claudia 的成功不能代替 Hair 的完整着色验证。
- 蒙皮 `EXT_mesh_gpu_instancing`、网格动画切换、VRM spring bone/专有
  表情映射等完整语义尚未实现。基础几何/蒙皮/形态键导入和烘焙回归
  不等于完整 VRM 运行时支持。
- 采样烘焙仍依赖采样率和播放器；任意 FBX 层级、复杂生产面部及其他
  游戏需有具体输入和引擎实测，不能从这 28 项样例推断全部兼容。
- 输出完整性检查不能证明每种可表示数据都有正确游戏表现。
  阶段计时可能嵌套，不能将所有 `stages.ms` 相加当作总耗时。

Remaining work includes missing Hair materials, skinned instancing, mesh swaps,
complete VRM-specific runtime semantics, arbitrary complex rigs and other engines.
Serialized integrity checks do not certify every possible engine behavior.

## 复现 / Reproduction

```powershell
python tests/compatibility.py compiler.exe
python -m unittest discover -s tests -p test_automation.py
python tests/reference_differential.py compiler.exe --reference ce.exe --dmx-profile ce --work isolated-ce
python tests/reference_differential.py compiler.exe --reference neko.exe --dmx-profile neko --work isolated-neko
python tests/validate_outputs.py path/to/model.mdl
compiler.exe model.qc -game game-directory -perfjson metrics.json
python tests/prepare_production_game.py compiler.exe --qc model.qc --game game-directory --work isolated-game --name material_test --material-dir path/to/materials --material-prefix models/author/model --test-lod-factor 0.5
python tests/verify_production_game.py game-directory/data/newpage_production_validation --output report.json --require-materials --require-face-change --require-lod-reduction
```

测试结束删除 `lua/autorun/server/newpage_production_validation.lua`。
摘要：`tests/reports/v1.2.7-validation.json`。游戏 LOD 网格读取依据
[GMod util.GetModelMeshes 文档](https://wiki.facepunch.com/gmod/util.GetModelMeshes)。
