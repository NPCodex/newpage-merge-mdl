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
5. Windows/Linux 都构建全部工具并运行自动化单元测试和模型兼容测试。
6. 两个平台均通过后，发布 GitHub **预发布版本**，含两个平台 ZIP、实际糅合源码 ZIP、
   上游版本/哈希清单、发布说明与 SHA256 校验值。上传完成前保持草稿。
7. PulseModel 与本仓库版本未变时不重复构建、发布；失败不更新已发布状态，后续可重试。

**闭源功能不会被自动移植。** StudioMDL-CE / StudioMDL++ 的下载仅用于版本追踪，
临时保存在 runner 中，不执行、不打包、不重新分发。用户在对话中提供它们的更新内容后，
由维护者实现对应功能并更新源码补丁；它们的版本变化本身不会触发发布。
不能据此宣称 NewPageMergeMDL 已获得相同新增功能。新增功能仍需实现、测试并更新补丁。

## 补丁维护

基准版本在 `automation/upstreams.json` 的 `pulse_base` 中。初始补丁包含当前实现。
以后修改源码后，必须更新补丁，否则自动上游构建仍会使用旧实现。
工作流会检查补丁与当前维护源码一致；发现遗漏更新时会停止发布。

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
- 发布不会更新默认分支的源码：最新上游源码和本地补丁的合并结果在 Release 的
  **NewPageMergeMDL-source.zip** 中。GitHub 自动生成的 Source code 包对应控制仓库提交。
- 现有 `release.yml` 仍提供人工草稿发布；自动发布使用独立工作流。

## 本地验证

v1.2.22 完成固定 A1–A7/B1–B4 共 11 个 CSGO 功能包；最终本地验证为 325 项兼容、20 项自动化、6 项挂载专项，以及原始 Plum 编译和 12 个自制 CSGO 模型的运行/地图重载。发布包包含 `CSGO_PORTING_SCOPE.md`、`CSGO_CLOTH_AUTHORING.md`、`CSGO_DMX_INPUTS.md` 与 `tests/reports/*-validation.json`，不包含游戏或用户资产。报告中的本地 Windows 编译器哈希只对应所记录的本地二进制；GitHub 自动构建的 MSVC/Linux 产物以各自打包验证日志和发布清单为准。以下 v1.2.19–v1.2.21 段落均是历史记录，不代表当前版本或发布状态。


```powershell
python -m unittest discover -s tests -p test_automation.py -v
python .github/scripts/upstream_release.py --help
```

首次线上运行前已验证辅助脚本及兼容补丁应用流程。v1.2.19 的历史结果为 Windows 209 项兼容、20 项自动化回归及 6 项 CONTENT 挂载专项通过，记录见 [tests/reports/v1.2.19-validation.json](tests/reports/v1.2.19-validation.json)。

v1.2.20 将 FE settings/吸引/弯曲/地面参数、零重力回退修复、默认离线 SubD/显式原生补丁与反编译再编译、CSGO 多目标 rig 动画烘焙、DMX 动画算子求值纳入同一兼容套件。完整测试和运行时结果由 [VALIDATION.md](VALIDATION.md) 记录；世界 sphere/capsule flags 的结构检查不能代替运行时碰撞体验证。发布前须为新增及修改的编译器、反编译器、格式和构建文件刷新维护补丁。此记录不表示该版本已在线发布；Windows/MSVC、Linux 构建及 Release 权限仍以 GitHub Actions 实际运行结果为准。

如果 Windows 便携 MinGW/LLVM 构建依赖外部运行时 DLL，执行本地回归前应把该工具链的 `bin` 目录加入 `PATH`，确保反编译器可加载这些 DLL。完整模型回归可用 `python tests/compatibility.py <compiler.exe>` 执行；HLMV 和用户生产模型检查独立记录，不作为无游戏环境中的自动化测试。

## 项目版本与双语文档

当前项目版本为 **v1.2.22**，程序和 Windows 文件版本统一采用该版本，独立于 PulseModel 上游版本号。
`CMakeLists.txt` 的项目版本与 `automation/upstreams.json` 的 `project_version` 应同步维护。
自动发布标签采用 `v1.2.0`、`v1.2.1` 等语义版本。每次检测到新的上游或项目改动，补丁号递增；配置版本作为最低版本，可手动提高主/次版本。上游没有变化则跳过发布，强制重建同一内容沿用已发布的版本和标签。合并源码内的 CMake、发布配置和 README 会同步写入实际发布版本，并重新生成对应补丁。
中文 `README.md` 与英文 `README.en.md` 都会包含在合并源码和二进制发布包中。

## 发布包验证

自动和人工发布均解压实际生成的 ZIP，检查源码 manifest、运行文件与程序版本，并使用包内编译器及反编译器重跑兼容回归。Linux 或 Windows 的构建、回归、打包验证失败都会阻止发布；人工草稿流程从根 CMake 项目读取版本。


v1.2.21 将绑定 sphere/capsule、稀疏布料/自由锚点/杆面、AxisInterp/Twist 和 DMX 曲线/压缩日志纳入相同源码补丁与兼容回归。CSGO 1.38.8.1 / 8802 离线 `de_dust2` 已补充 7 个 cloth21 样例的加载/多骨变形/移动、4 个零重力同壳 sphere/capsule `contact_on/off` 响应对照、原生 AxisInterp NP/stock 的 0.5/1 秒名义相位视觉对照，以及正向/inverse Twist 的正负方向播放检查。地图重载后，7 个布料、4 个接触对照及 4 个程序骨样例均重新载入。它们是有界的人工运行证据，不代替逐帧接触、全点无穿透、精确游戏骨角或 stock 全量等价验证。本轮未改编译器，版本仍为 v1.2.21。

原版编译器数值对照、安装游戏中的运行验证和 Plum 原资产检查保留在本地诊断及本版验证报告，不把游戏或用户资产装入发布包。本地打包不表示已推送或在线发布。
