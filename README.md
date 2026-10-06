# NewPageMergeMDL v1.1

[English](README.en.md) | 简体中文

项目版本：**v1.1**。编译器、反编译器和辅助工具统一使用本项目版本号。模型文件格式仍为 v49。

自动更新及 GitHub Release 配置见 [AUTOMATION.md](AUTOMATION.md)。

基于 [PulseModel](https://github.com/ToppiOfficial/PulseModel) 的 Source 模型编译工具，加入 StudioMDL-CE / StudioMDL++ / NekoMDL 兼容功能与自行实现的动画扩展。NekoMDL 对照依据为附带的中文版 v2.3.0 更新日志。

编译器：`NewPageMergeMDL.exe`；反编译器：`NewPageMergeMDL-Decompiler.exe`。
支持 Windows x64 和 Linux 构建，模型输出版本为 v49。Windows 和 Linux 构建由 GitHub Actions 验证。

## 当前功能

- 原 PulseModel 的 SMD / DMX / FBX 编译、模型反编译和辅助工具。
- `$setvariable`、包含文件和动画模型前缀、`$PUSHDInclude`、按骨骼前缀折叠。
- `-cullanims`、`-MostlyOpaque`，重复变量定义警告。
- 自行实现的动画 `copy`、`match pos/rot`、嵌套 `if / else if / else`。
- VTA 同名 `flex` / `flexpair` 多帧：保留独立顶点数据和 StudioMDL 兼容权重区间。
- `$sequence gmtime`，默认保留已有模型的序列顺序，`-noremap` 使用 QC 顺序。
- CE 面部扩展：控制器覆盖/重复、反向表情、`fscale`、零衰减和默认表情烘焙。
- CE 眼球缩放、DMX 法线/皱纹计算、全局骨骼空间表情重映射。
- bodygroup 面部块、独立材质重命名、单骨权重、可选骨骼折叠规则和输出限制。
- glTF / GLB / VRM 快速导入，以及 Assimp 的 OBJ、DAE、PMX 等格式导入；保留原 FBX 导入器。
- NekoMDL 的 `InNode`、`Pick`、`SampleRate`、`$FPS`、`$NekoModel`、`$NekoDriverBone` 和飘骨轴向命令。
- `$PreRenameMaterial`、`$DiscardVertexAnimationNormals`、`$MaxVerts`、`$MaxBones`、`$FileBufferSize`；无花括号条件语句、`$UndefineVariable`、`$Msg` 和 `-Dname value`。
- `-reloadhlmv`（Windows）和 `-playbeep`；`$NoFastGltf` 切换到 Assimp 后备导入。
- 带终端颜色的启动横幅；重定向日志保持纯文本。

完整合并尚未完成，语法和差异见 [COMPATIBILITY.md](COMPATIBILITY.md)。不能保证与 StudioMDL-CE / StudioMDL++ 的全部行为一致。

NekoMDL 附带的完整 `survivor_teenangst.qc` 已通过混合 DMX/GLB 编译验证；用户的 Alyx QC 也保持可编译。自动测试使用自行编写的小模型，不将用户模型或 NekoMDL 二进制打包到仓库。

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
