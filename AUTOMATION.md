# 自动更新与发布

目标仓库：https://github.com/Kudvvv/newpage-merge-mdl

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
- 发布不会更新默认分支的源码：最新上游源码和本地补丁的合并结果在 Release 的
  **NewPageMergeMDL-source.zip** 中。GitHub 自动生成的 Source code 包对应控制仓库提交。
- 现有 `release.yml` 仍提供人工草稿发布；自动发布使用独立工作流。

## 本地验证

```powershell
python -m unittest discover -s tests -p test_automation.py -v
python .github/scripts/upstream_release.py --help
```

首次线上运行前，本地已验证辅助脚本及兼容补丁应用流程。线上 Windows/MSVC 和 Linux
构建及 Release 权限，以 GitHub Actions 实际运行结果为准。
