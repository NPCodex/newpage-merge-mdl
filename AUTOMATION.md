# 自动更新与发布

目标仓库：https://github.com/NPCodex/newpage-merge-mdl

`.github/workflows/upstream-release.yml` 每六小时检查 PulseModel 的更新，也可通过 Actions
中的 **Upstream sync and automatic release → Run workflow** 手动启动。
推送相关源码或补丁到 `main` 时也会启动。定时任务需要工作流位于默认分支；
GitHub 的调度可能延迟，长时间无活动的公开仓库可能被自动停用定时任务。

## 自动化实际执行的内容

1. 查找 PulseModel 默认分支的最新提交，下载并检出精确版本。
2. PulseModel 或本仓库维护代码发生变化时，获取 StudioMDL-CE 默认分支的 ZIP
   （其仓库包含 Preview 二进制），作为本次构建的来源对照记录。
3. 同时获取 ficool2/misc_tools 的 `v1` Release 中 Tools++ Windows/Linux 资产，
   记录资产 ID、大小、更新时间和下载校验值。这两项闭源项目不单独触发发布。
4. 对最新 PulseModel 执行 `git apply --3way --index automation/compatibility.patch`，
   保留 NewPageMergeMDL 名称及已实现的兼容扩展。冲突即失败，不丢弃本地修改。
5. Windows/Linux 都用 `MinSizeRel` 与 IPO/LTO 构建全部工具，并运行自动化单元测试和模型兼容测试。
6. 两个平台均通过后，发布 GitHub **正式版本**，每个平台只上传一个完整 ZIP。
   实际糅合源码 `sources/NewPageMergeMDL-source.zip`、根目录的 `upstream-manifest.json`
   与 `SHA256SUMS.txt`、`tests/reports/` 中的验证报告均放入平台包内，
   不再作为独立附件；发布说明列出平台包及其 SHA256。上传和校验完成前保持草稿。
7. 按 PulseModel 提交及实际发布输入判断变化：原生源码、构建配置、运行脚本、资源、许可、版本和依赖固定信息。合并提交编号、文档、测试及 CI/发布控制脚本的变更本身不触发新版；失败不更新已发布状态，后续可重试。

精确构建来源仍由 `controller_sha` 与原有 `fingerprint` 记录，去重使用独立的
`release_inputs_sha256`。已发布的维护包可从通过校验的包内源码补算；缺少源码的旧包
保留严格来源比较。自动合并包保存原始控制器输入指纹，避免其已合并上游、已调整版本号的
源码在下次检查时造成重复发布。Windows/Linux 的完整源码与来源仍须一致。
GitHub Release 的公开标签决定重建目标，包内历史 `dev-<SHA>` 只作为构建来源保留。
仅修改文档或发布流程后若确需重建附件，应明确手动使用 `force`；它不会自动改成新版本。

内容指纹对已识别的源码、着色器、构建模板和许可文本统一 CRLF/LF 换行；二进制及未知类型
保留原始字节。可能与二进制扩展名重合的历史脚本和手册按精确路径识别。Dev 与手动发布
在编译前运行 `verify-checkout-source`，将实际工作区输入与 Git HEAD 的 LF 源码归档核对，
提前发现文本类型遗漏或未提交的构建输入；打包时仍再次校验包内源码身份。

手动维护构建和 Dev 构建共用 `.github/scripts/package_maintained.py` 的完整清单与整包验证；Dev 附件明确命名为开发产物，不自动发布 Release。Linux 失败会阻止成功状态，四个 subtools 均必需。Windows runner 固定 `windows-2025`，Linux 固定 `ubuntu-24.04`，所需 ELF 符号门槛见 `automation/linux-runtime.json`；本轮真实执行结果见 [平台矩阵](GAME_PLATFORM_MATRIX.md)。

手动发布修订号同时考虑 tag 和 API 中的草稿，只有完整来源 SHA 匹配的草稿才可复用；上传前再次检查草稿/来源，两个平台附件上传并核对服务端 digest 后才更新说明。已发布版本或不同来源的占位不能被当作同一次重试。离线流程回归不等同已执行远端并发冲突试验。

**闭源功能不会被自动移植。** StudioMDL-CE / StudioMDL++ 的下载仅用于版本追踪，
临时保存在 runner 中，不执行、不打包、不重新分发。用户在对话中提供它们的更新内容后，
由维护者实现对应功能并更新源码补丁；它们的版本变化本身不会触发发布。
不能据此宣称 NewPageMergeMDL 已获得相同新增功能。新增功能仍需实现、测试并更新补丁。

## 补丁维护

基准版本在 `automation/upstreams.json` 的 `pulse_base` 中。初始补丁包含当前实现。
以后修改源码后，必须更新补丁，否则自动上游构建仍会使用旧实现。
工作流会检查补丁与当前维护源码一致；发现遗漏更新时会停止发布。

v1.2.28 将基线从 `52cf296a953fd6c2d072e34cfde5eb8eccc95564` 更新到 `578e86e38fde086ccfb701d96688817a77e718de`，合并期间解决包围盒、DMX/反编译器和构建文件的重叠修改。对应维护补丁必须相对新基线重新生成，并通过 `refresh_overlay.py --check` 和自动准备流程验证。更新基线或下载成功本身不代表兼容回归、发布包或游戏运行验证通过，结果以 [VALIDATION.md](VALIDATION.md) 与本次 Actions 日志为准。

在网络可用且工作区有 Git 的环境运行：

```powershell
python .github/scripts/refresh_overlay.py
```

该脚本在临时目录检出固定基准，只对 `libs`、编译器、反编译器、辅助工具和根 CMake
文件生成补丁，不改动当前仓库的 Git 历史。测试、说明和自动化文件由主仓库直接提供。
上游删除或重构了我们修改的代码时，需要人工解决冲突并更新 `pulse_base` 和补丁。

## GitHub 设置

- 首次将本目录提交并推送到目标仓库的 `main` 分支。
- 仓库 Actions 应允许运行工作流。发布 job 使用仓库自带的 `GITHUB_TOKEN`，请求
  `contents: write`；不需要个人访问令牌。若组织策略限制权限，需要仓库管理员调整策略。
  已发布清单通过带认证的 GitHub API 读取，支持私有仓库。
- 自动上游发布不会更新默认分支的源码：每个平台包都在 `sources/NewPageMergeMDL-source.zip`
  内嵌最新上游源码与本地补丁的精确合并结果，
  不再另挂源码 ZIP。GitHub 自动生成的 **Source code** 链接对应控制仓库提交，
  不是安装包，也不能替代实际构建源码。自动上游包和手动维护包均内嵌
  `sources/NewPageMergeMDL-source.zip`，以包内 manifest 的源码提交及哈希为准；
  同标签替换构建后尤其不能用旧 tag 代替。独立 GPL 转换器的对应源码始终随平台包提供。
- 现有 `release.yml` 仍提供人工草稿发布；自动发布使用独立工作流。

## 本地验证

v1.2.23 按 [FIVE_COMPILER_COMPLETION.md](FIVE_COMPILER_COMPLETION.md)完成五编译器固定清单的实现、策略与有界验收；当前测试和运行证据见 [VALIDATION.md](VALIDATION.md)。v1.2.22 完成 A1–A7/B1–B4 共 11 个 CSGO 功能包时的历史结果为 325 项兼容、20 项自动化、6 项挂载专项，以及原始 Plum 编译和 12 个自制 CSGO 模型的运行/地图重载。报告中的本地 Windows 编译器哈希只对应所记录的本地二进制；GitHub 自动构建的 MSVC/Linux 产物以各自打包验证日志和发布清单为准。以下 v1.2.19–v1.2.21 段落均是历史记录，不代表当前版本或发布状态。

发布包包含编译器、反编译器、全部辅助工具、独立 GPL VRML 转换器、[INSTALL.md](INSTALL.md)、两份 README、兼容说明、CSGO 范围及作者指南、`FIVE_COMPILER_COMPLETION.md`、`MESH_STATE_WORKFLOW.md`、`VRM_RUNTIME.md`、`O5_FORMAT_IMPORTS.md`、`SCENE_IMPORT.md`、`DECOMPILER_EXPORTS.md`、`AUTHORING_WORKFLOWS.md`、`GAME_PLATFORM_MATRIX.md`、各 subtool 用法及 `tests/reports/` 中的验证报告。`tools/` 提供准备/转换工具及其源文件，`integration/gmod/` 提供客户端模块；独立 VRML 转换器及其所需 `libs/assimp/contrib/pugixml/` 的对应源码和许可始终附带。根目录提供 `upstream-manifest.json` 与 `SHA256SUMS.txt`。所有平台包内的 `sources/NewPageMergeMDL-source.zip` 另含精确构建源码、固定版本的 `libs/tinyusdz/` 及其他构建依赖和许可。Python 准备脚本需用户自行安装 Python 3；不打包游戏、用户模型或参考编译器。

Windows x64 完整包还包含 `NewPageMergeMDL-C4D.exe`。CI 根据 `automation/windows-extras.json` 固定的来源和 SHA256 复用已按许可构建并测试的产品二进制，不下载/安装 Cineware SDK。主程序与其他开源工具仍由当前源码构建；Windows C4D helper 缺失或哈希不符时必须失败，不能把缺少 helper 的 CI 包作为第二个用户下载。Linux 导入 Windows 预转换的 GLB。SDK 的头文件、静态库、示例和文档均不进入源码包或二进制包。相关范围和独立构建方法见 [O5_FORMAT_IMPORTS.md](O5_FORMAT_IMPORTS.md)。

v1.2.26 的两个发布工作流使用 `MinSizeRel` 与 `CMAKE_INTERPROCEDURAL_OPTIMIZATION=ON`；本地 `x64-compact` 预设采用相同策略。构建环境需提供相互匹配、支持 LTO 的编译器、归档工具和链接器，普通 Release 开发构建仍可选择。C4D 独立 helper 继续复用上述已验证二进制，不随此策略重建。

平台包的运行目录不再重复附带 tinyusdz 源码与开发图片；USD 后端已静态编入程序。`libs/tinyusdz/` 中保留 `LICENSE`、`LICENSE-APACHE-2.0`、`SOURCE.md` 和 `THIRD_PARTY_NOTICES.md`，包括原本嵌在源码中的第三方声明。独立 GPL VRML 转换器及 pugixml 的对应源码、构建文件和许可继续随包分发。所有包内的精确构建源码仍包含完整 tinyusdz；精简仅针对运行目录的重复内容。

v1.2.28 的 Windows/Linux 包还包含实验性 `subtools/ag2proportions`（Windows 为 `.exe`）。构建并静态链接共享 DMX/KV3/zstd 支持，打包必须保留 `subtools/licenses/zstd.txt` 和 `subtools/licenses/ValveResourceFormat.txt`，验证器检查新工具的存在、`--help` 和项目版本。该工具的 CS2 数据与 Workshop Tools 由使用者自行准备，不能放入安装包。CI 的构建及烟雾检查不代表真实 VMDL、ModelDoc 或 CS2 游戏内验证；使用条件与原位修改注意事项见 [INSTALL.md](INSTALL.md)。


```powershell
python -m unittest discover -s tests -p test_automation.py -v
python .github/scripts/upstream_release.py --help
```

首次线上运行前已验证辅助脚本及兼容补丁应用流程。v1.2.19 的历史结果为 Windows 209 项兼容、20 项自动化回归及 6 项 CONTENT 挂载专项通过，记录见 [tests/reports/v1.2.19-validation.json](tests/reports/v1.2.19-validation.json)。

v1.2.20 将 FE settings/吸引/弯曲/地面参数、零重力回退修复、默认离线 SubD/显式原生补丁与反编译再编译、CSGO 多目标 rig 动画烘焙、DMX 动画算子求值纳入同一兼容套件。完整测试和运行时结果由 [VALIDATION.md](VALIDATION.md) 记录；世界 sphere/capsule flags 的结构检查不能代替运行时碰撞体验证。发布前须为新增及修改的编译器、反编译器、格式和构建文件刷新维护补丁。此记录不表示该版本已在线发布；Windows/MSVC、Linux 构建及 Release 权限仍以 GitHub Actions 实际运行结果为准。

如果 Windows 便携 MinGW/LLVM 构建依赖外部运行时 DLL，执行本地回归前应把该工具链的 `bin` 目录加入 `PATH`，确保反编译器可加载这些 DLL。完整模型回归可用 `python tests/compatibility.py <compiler.exe>` 执行；HLMV 和用户生产模型检查独立记录，不作为无游戏环境中的自动化测试。

## 项目版本与双语文档

当前源码项目版本为 **v1.2.39**，程序和 Windows 文件版本统一采用该版本（含 `ag2proportions`），独立于 PulseModel 上游版本号。发布状态及本次验收范围见 [Release](https://github.com/NPCodex/newpage-merge-mdl/releases/tag/v1.2.39) 与 [Neko 2.4 移植验证记录](tests/reports/v1.2.39-neko24.md)。
`CMakeLists.txt` 的项目版本与 `automation/upstreams.json` 的 `project_version` 应同步维护。
自动发布标签采用 `v1.2.0`、`v1.2.1` 等语义版本。检测到新的上游或发布输入内容时，补丁号递增；配置版本作为最低版本，可手动提高主/次版本。输入内容没有变化则跳过发布，强制重建同一内容沿用已发布的版本和公开标签。合并源码内的 CMake、发布配置和 README 会同步写入实际发布版本，并重新生成对应补丁。
中文 `README.md` 与英文 `README.en.md` 都会包含在合并源码和二进制发布包中。

## 发布包验证

自动和人工发布均解压实际生成的 ZIP，检查源码 manifest、内部文件校验、工具和文档完整性、运行文件与程序版本，并使用包内编译器及反编译器重跑兼容回归。Windows 包还必须具备固定校验的 C4D helper。Linux 或 Windows 的构建、回归、打包验证失败都会阻止发布；人工草稿流程从根 CMake 项目读取版本。用户只需选择平台并完整解压，安装/更新步骤见 [INSTALL.md](INSTALL.md)。


v1.2.21 将绑定 sphere/capsule、稀疏布料/自由锚点/杆面、AxisInterp/Twist 和 DMX 曲线/压缩日志纳入相同源码补丁与兼容回归。CSGO 1.38.8.1 / 8802 离线 `de_dust2` 已补充 7 个 cloth21 样例的加载/多骨变形/移动、4 个零重力同壳 sphere/capsule `contact_on/off` 响应对照、原生 AxisInterp NP/stock 的 0.5/1 秒名义相位视觉对照，以及正向/inverse Twist 的正负方向播放检查。地图重载后，7 个布料、4 个接触对照及 4 个程序骨样例均重新载入。它们是有界的人工运行证据，不代替逐帧接触、全点无穿透、精确游戏骨角或 stock 全量等价验证。本轮未改编译器，版本仍为 v1.2.21。

原版编译器数值对照、安装游戏中的运行验证和 Plum 原资产检查保留在本地诊断及本版验证报告，不把游戏或用户资产装入发布包。本地打包不表示已推送或在线发布。


v1.2.30 将固定基线推进到 `4fe14de0f9b0533699dc81380d9510b024d8deeb`，采用上游的 Windows 图标资源支持，嵌入项目所有者提供的 NewPage 自有图标，并重新生成维护补丁。项目仍使用统一版本号，不直接采用上游两个工具的独立版本号。

自动准备流程保留 `assets/branding` 中的 NewPage 原图与生成脚本；安装包携带 README 图标预览和品牌源文件。发布完成时使用正式版本标记；只有版本号不低于当前 Latest 时才将它设为 Latest，旧版本重试不会覆盖较新的 Latest。

v1.2.31 将固定基线从 `4fe14de` 推进到 `174f8c0ea337f33505bd52c41bd254d3ba0128ab`，移除未构建、未发行的 `importqc` 与过时注释。上游同时删除的 `meshtool` 由 NewPage 继续维护，源码、启用的构建入口和包内程序都必须保留，并记录在相对新基线重新生成的维护补丁中。新基线的自动准备与补丁一致性检查仍须通过；本次同步没有模型编译算法或自有图标变化。
