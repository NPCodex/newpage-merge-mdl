# NewPageMergeMDL v1.1

[English](README.en.md) | 简体中文

项目版本：**v1.1**。编译器、反编译器和辅助工具统一使用本项目版本号。模型文件格式仍为 v49。

自动更新及 GitHub Release 配置见 [AUTOMATION.md](AUTOMATION.md)。

基于 [PulseModel](https://github.com/ToppiOfficial/PulseModel) 的 Source 模型编译工具，加入 StudioMDL-CE / StudioMDL++ / NekoMDL 兼容功能与自行实现的动画扩展。NekoMDL 对照依据为附带的中文版 v2.3.0 更新日志。

编译器：`NewPageMergeMDL.exe`；反编译器：`NewPageMergeMDL-Decompiler.exe`。
支持 Windows x64 和 Linux 构建，模型输出版本为 v49。Windows 和 Linux 构建由 GitHub Actions 验证。

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

- 编译器、反编译器及辅助工具统一命名和使用 **v1.1** 版本号；彩色启动横幅，重定向日志保持纯文本。
- 自动拉取 PulseModel、套用维护补丁，完成 Windows/Linux 构建与测试后发布 GitHub Release；冲突或检查失败停止发布。CE/++/Neko 的新增闭源功能仍需人工分析。
- 73 项兼容测试及 12 项自动化测试；测试检查实际模型输出。NekoMDL 的完整 `survivor_teenangst.qc` 已通过混合 DMX/GLB 编译验证，用户的 Alyx QC 也保持可编译。测试和发布包不包含用户模型或参考编译器二进制。

## 未完成与已知问题

| 内容 | 当前状态与限制 |
| --- | --- |
| NekoMDL 导入兼容 | 使用 cgltf 快速路径和 Assimp 6.0.4 后备路径，不使用闭源编译器源码。已验证基础场景变换、蒙皮、命名形态键、节点筛选和动画采样；尚未逐一认证所有 Assimp 格式、复杂 FBX/VRM rig 与游戏内表现。 |
| glTF 动画与压缩 | 快速路径支持位移/旋转的 LINEAR、STEP、CUBICSPLINE，静态缩放烘焙进网格。动画缩放、形态键权重和网格切换会明确报错，需要先烘焙或改用 QC flex 控制器。Draco、meshopt 压缩与 GPU 实例扩展需要先展开源模型。Assimp 后备路径可能改变 STEP/CUBICSPLINE 插值，建议优先使用快速路径。 |
| NekoMDL 算法与默认值 | `$MaxVerts` 控制每材质输出网格的分割上限，实际不超过 65536；不复现 Neko 的源文件预拆分/裁剪算法。`$FileBufferSize` 限制各输出文件字节数，不预分配固定内存。保留本项目动态缓冲区、骨骼折叠和序列排序默认值；需要保留加权骨骼时启用 `$CEBoneRules`。 |
| NekoMDL 面部与驱动骨 | 基础双侧权重及飘骨旋转/约束已对照二进制输出；多 studio、眼睑和驱动骨有输出测试，但复杂 driver/procedural/IK 层级尚未做全面差分。 |
| 旧版网格算法 | CE `$UseLegacyStripify`（NvTriStrip）、`$UseLegacyClampMethod`（全局顶点裁剪）和 Neko `-nvtristrip` 尚未实现；使用这些开关会明确报错。 |
| `gameinfo.txt` AppID 挂载 | 尚未实现，不能依靠 AppID 自动找到其他游戏资源。 |
| 完整语法与输出兼容 | 动画 `copy`、`match pos/rot` 和条件语句采用本项目定义的语义；尚未认证与 StudioMDL++ 完全一致。输出为 v49，不能与 CE/++ 的 v48 文件逐字节比较。 |
| 复杂面部与 DMX | 已验证基础法线、皱纹、逆向表情和眼睑规则；复杂 corrective rig、硬边、自定义法线、控制器重映射及游戏内眼睑表现仍需更多验证。 |
| 材质重命名 | 同一模型中把多个材质合并到同一个目标名称会报错，尚不支持合并材质网格范围。 |
| `NoAutoDMXRules` | 保留 PulseModel 的单源规则禁用语义，与 CE 在多模型场景下禁用先前自动规则的行为不同；`NoAutoDMXRulesLegacy` 会清除先前自动控制器和规则。 |
| `addcontrollerbyflex` | 按文档正确处理 min/max；不复现 CE 二进制把两者写入 min 字段的缺陷。 |
| 骨骼、碰撞与大模型 | CE 折叠规则通过 `$CEBoneRules` 显式启用；单骨权重选项属于实验功能。复杂 procedural/IK/LOD、碰撞物理及极大模型还没有全面差分和压力测试。引擎支持范围仍受模型格式字段限制。 |
| 诊断与性能 | 边界框和 cmdlist 诊断尚未完成全部兼容验证；没有进行各编译器之间的系统性能对比。 |
| 游戏加载与 UTC 动画 | 编译成功不代表已在游戏内验证；`gmtime` 的 UTC 同步需要目标模组支持。 |
| 自动更新 | 自动合并 PulseModel 源码；发生补丁冲突或测试失败时停止发布。CE/++ 仅跟踪参考版本，新闭源功能仍需手动分析和实现。 |
| 其他 Tools++ 工具 | VBSP、VVIS、VRAD、BSPZIP 属于地图工具，不在本模型编译器的合并范围内。 |

完整语法、限制与有意保留的差异见 [COMPATIBILITY.md](COMPATIBILITY.md)，二进制调查记录见 [BINARY_ANALYSIS.md](BINARY_ANALYSIS.md)。

## 编译源码

Windows：在 Visual Studio 2022 的 x64 开发者终端中，准备 CMake 3.22+ 和 Ninja：

```powershell
cmake --preset x64-release
cmake --build --preset x64-release
```

输出位于 `out/build/x64-release/NewPageMergeMDL/`。

Linux：准备 CMake 和 C/C++ 编译器：

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
```

依赖库已包含在 `libs/`，无需额外包管理器。GitHub Actions 已同步新的名称和打包路径。

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

56 项兼容测试使用临时 SMD/QC 和自制 DMX，检查实际 MDL/VVD 文件，并反编译动画验证位移、旋转和分支行为；另有 12 项自动发布测试。

已成功编译用户提供的 Alyx QC（113 根骨骼、27,571 个 VVD 顶点）。这项验证不包含游戏内加载或渲染。

## 来源与许可

原项目作者：Toppi。保留原 [MIT LICENSE](LICENSE) 与第三方库版权声明。
[UPSTREAM_README.md](UPSTREAM_README.md) 保存上游说明，含旧程序名称和旧下载地址，仅供参考。
本项目没有包含 StudioMDL-CE 或 Tools++ 的闭源二进制或源码。
