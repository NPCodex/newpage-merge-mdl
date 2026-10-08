# CSGO DMX 骨骼动画输入指南

本文描述 v1.2.22 的有限输入范围：A4 的 Rotation/两段骨 IK 与统一约束图、A5 的五种日志值和六个转换算子、B4 的倒放及 FilmClip/track/shot 时间映射。求值结果写入普通骨骼动画；这不是完整 SFM 场景播放器。

## QC 导入

外部 rig 驱动 SMD 或其他骨骼动画：

```qc
$modelname "example/rigged.mdl"
$body mesh "mesh.smd"
$datamodeljoints "rig.dmx" proceduralbones
$sequence motion "motion.smd" fps 30
```

同一 DMX 包含 rig、通道和动画参数：

```qc
$modelname "example/animated_rig.mdl"
$body mesh "mesh.smd"
$datamodeljoints "motion.dmx" proceduralbones
$sequence motion "motion.dmx" blockname "motion" fps 30
```

仅导入带嵌套时间线的骨骼动画也可以直接使用 `$sequence motion "scene.dmx" blockname "film名称" fps 30`。`blockname` 选择 DMX 顶层动画名称；省略时选择首个非 BindPose 动画。DMX 中的 `frameRate` 决定导入采样率，QC `fps` 决定编译后的播放速度，应按需求一致设置。

外部 `$datamodeljoints` rig 的骨名必须能映射到模型骨架。编译器保留所需的未加权控制骨、解析 `$renamebone` 别名，并在求值时还原作者的骨骼坐标系，再将结果变换到最终骨骼坐标系。此入口仍要求 CSGO 目标和骨骼模型；`$centerbonesonverts` 与原始 delta 输入被明确拒绝。

已在 DMX 源动画中求值的 rig 算子带有烘焙标记，再次通过 `$datamodeljoints` 导入同一 rig 时不会用静态默认参数覆盖逐帧结果。

## 七种 rig 算子

| 类名后缀，均以 DmeRig 开头 | 输入与结果 |
| --- | --- |
| PointConstraintOperator | `slave`、多个 `targets`；目标的 `targetWeight/vecOffset` 决定 slave 世界位置。 |
| OrientConstraintOperator | 多目标旋转、`targetWeight/oOffset` 与 slave base orientation 混合，写 orientation。 |
| AimConstraintOperator | 当前 slave position 指向加权目标；支持 `aimOffset`、`upVector/upType/upSpaceTarget`，写 orientation。 |
| ParentConstraintOperator | 按目标坐标系应用位置/旋转 offset，写 position 和 orientation。 |
| RotationConstraintOperator | `axies` 为 Vector3 数组，`rotations` 为等长 float 数组，角度单位为度；按数组顺序将轴角旋转左乘到结果，写 slave orientation。属性名沿用源码的 `axies` 拼写。 |
| IKConstraintOperator | `startJoint/midJoint/endJoint` 必须组成两段骨链；支持多个加权目标、`poleVector` 或 `pvTarget`、`startOffset/midOffset`，写起始骨和中间骨 orientation。 |
| TwistConstraintOperator | 两个 parent/child targets、多个 `twistJoints`；支持 `weight/orientation`、`inverse`、父/子 bind rotation 与 up vector，写普通骨骼姿态。 |

`slave`、IK joint holder 和普通 target holder 通过 `target` 引用 DAG；DAG 通过 `transform` 引用 DmeTransform。普通 target 权重属性为 `targetWeight`，Twist slave 权重为 `weight`。

IK 将超出可达范围的距离限制在两段骨的可达长度内。零长度骨、目标与起点重合、无法确定弯曲平面的 pole vector 会报错，不会输出非有限姿态。

通道可驱动目标骨姿态，也可以驱动算子参数、holder 权重、offset、base orientation、Rotation 数组项等数值属性。算子与 Connection/Expression/Pack/Unpack 在同一帧依赖图中求值，文件中的元素顺序不决定执行顺序。连接到未知算子的有效通道、属性写入冲突、反馈环会报错。

Point 与仅写 orientation 的算子可以作用于同一 DAG 的不同属性。两个有效算子或通道同时写同一属性仍会报错。多个外部 rig 文档通过骨骼依赖排序，两个文档共同拥有同一输出骨被拒绝。最终骨架的 parent 依赖也参与判环，避免 `$hierarchy` 引入编译后反馈。

Rotation、IK、Twist 不要求新增引擎程序骨类型。Point/Orient/Aim/Parent 原有的记录仅保留作元数据，动画通道保持有效。游戏中的运行时 IK、姿态混合和后续 QC 动画操作不会再次运行此图。

## 日志值与转换算子

现有 Float、Int、Bool、Vector2、Vector3、Vector4、Quaternion 值继续可用。新增类型的标量属性、数组引用和日志采样如下：

| 日志类 | 值类型 | 无 curveinfo 时的采样 |
| --- | --- | --- |
| DmeQAngleLog | `qangle` / `qangle_array`，pitch/yaw/roll，单位为度 | 转为四元数做 slerp，再转回 QAngle；角度可以规范化，例如 350° 表示为 -10°。 |
| DmeVMatrixLog | `matrix` / `matrix_array`，16 个分量 | 保持前一个键值。 |
| DmeColorLog | `color` / `color_array`，RGBA 字节 | 分量插值后截断为字节。 |
| DmeStringLog | `string` / `string_array` | 保持前一个字符串；可用于连接到表达式的 `expr`。 |
| DmeTimeLog | `time` / `time_array` | 按 1/10000 秒 tick 插值并截断。 |

每类日志使用同名加 `Layer` 后缀的层元素。`times` 可使用 tick 的 int 数组或 time 数组；`values` 必须与 times 数量一致且类型一致。键时间必须严格递增。层选择、默认值与 `noninterpolatedsegments` 延续已有规则。只对 Float/Vector3/Quaternion 使用已有的完整曲线实现；Time 的曲线分支依参考泛型实现保持前值。对参考不适用曲线的 QAngle/Color/Matrix/String 值，curveinfo 不改变普通采样规则。压缩日志仍限参考支持的 Vector3/Quaternion 通道格式。

新增的六个类为：

| Pack / Unpack 类后缀 | 合并属性 | 拆分属性 |
| --- | --- | --- |
| ColorOperator | `color` | `red/green/blue/alpha`，float |
| QAngleOperator | `qangle` | `x/y/z`，float，对应 pitch/yaw/roll |
| VMatrixOperator | `vmatrix` | `m00` 到 `m33`，按行列对应 4×4 矩阵 |

完整名称例如 `DmePackColorOperator`、`DmeUnpackVMatrixOperator`。Color pack 将 float 乘以 255.999、限制到 0–255 后截断；unpack 除以 255.999。Matrix 按明确的 16 单元映射实现，没有复制参考源码中越界索引和未初始化局部矩阵的错误。QAngle pack/unpack 只拆装角度分量，不自动把目标骨的 quaternion 属性改成 QAngle。

普通日志与算子图最终只保存骨骼 position/orientation。Color、String、Matrix、Time 可以作为计算过程中的值；摄像机、灯光、材质、音频和面部控制器的动画不会自动变成 MDL 骨骼通道。

## 时间线结构、倒放与边界

支持 `animationList.animations` 中的 DmeChannelsClip，以及 FilmClip/shot 下的有限骨骼通道层级：

```text
FilmClip
  trackGroups / subClipTrackGroup
    TrackGroup.tracks
      Track.children
        FilmClip（shot）或 ChannelsClip
```

入口也识别根元素自身的 clip，以及根的 `activeClip/filmClip/movie` 引用。嵌套结构按 `trackGroups/tracks/children/clips/shots` 和 `subClipTrackGroup` 遍历；不把普通 scene DAG 的 children 当作动画 clips。

动画专用输入没有根 `model/skeleton` 时，可以从 scene 层级中选择唯一的 DmeModel，或包含 jointList 的 DmeGameModel。多个模型候选会报错，避免把不同角色骨架合并到一条动画；不从磁盘游戏 MDL 隐式补出缺失骨架。

每一级 timeFrame 都应用：

```text
childTime = (parentTime - start) * scale + offset
```

时间逐级组合，以 1/10000 秒为精度。`scale` 可为负数，表示倒放；必须有限且非零。`duration` 必须非负。子 clip 只在父时间落入它的区间时贡献通道；没有有效写入的间隔恢复该文档的基础属性值。

相邻 clips 共用的边界采样由开始的 clip 接管，独立 clip 的最终端点仍可采样。重叠区间若写同一骨骼属性或同一算子输入则明确报冲突；不实现 SFM 轨道混合权重或自动 crossfade。日志本身在键值覆盖区间外保持边界值，顶层动画按根 clip 的时长输出。

单个 clip 采样率上限为 10,000 fps，输出上限为 100,000 帧；单日志层最多 1,000,000 个键，嵌套深度上限为 128。时间越界、空引用和层级环会报错。

## 验证入口与明确排除

`tests/dmx_scope_cases.py` 覆盖新增值类型、六个转换算子、倒放、嵌套时间映射、独立 Film scene、相邻边界与重叠/循环拒绝；`tests/procedural_scope_cases.py` 检查 Rotation/IK、动态参数、Point 读取 IK 输出、scale/realign/rename 和退化输入。`tests/prepare_rig_runtime.py` 生成自写的可见 Rotation/IK 运行夹具及 manifest，生成器本身不安装游戏文件。

不支持 reverse rig mode；它不同于 `Twist.inverse` 和负时间 scale。源码中只有枚举或空分支的功能没有被视为已完成算法。鼠标键盘输入、录制/编辑器 undo、完整 SFM 会话恢复、粒子、音频、摄像机效果、面部时间线输出、运行时 rig 重求解均不在本输入范围。
