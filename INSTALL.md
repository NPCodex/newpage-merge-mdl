# 单包安装 / Install from one archive

## 中文

1. 从 [GitHub Releases](https://github.com/NPCodex/newpage-merge-mdl/releases) 下载适合系统的 **Windows x64 ZIP** 或 **Linux ZIP**，只需一个包。GitHub 自动提供的 **Source code** 链接不是安装包。
2. 完整解压到一个新目录，保持文件和子目录结构。编译器、反编译器、辅助工具、独立 VRML 转换器及其对应源码、准备脚本、GMod Lua 模块、文档、许可、构建清单和包内校验文件已经放在一起。Windows 包还包含 C4D 桥接程序。
3. 在该目录打开终端，为每次编译设置正确的 `-game`：传入目标游戏/模组中包含 **正确 `gameinfo.txt` 的目录**，尤其是 CSGO 与 MCV。`-OutDir` 另设隔离输出目录。

```powershell
.\NewPageMergeMDL.exe "D:/models/model.qc" -game "D:/Games/csgo legacy/csgo" -OutDir "D:/build/model"
```

Linux 使用 `./NewPageMergeMDL` 并换成实际 Linux 路径；若解压工具未保留可执行权限，先为需要运行的程序设置执行权限。

包内根目录提供 `INSTALL.md`、`upstream-manifest.json` 和 `SHA256SUMS.txt`，验证报告在 `tests/reports/`。自动上游合并包的精确项目源码另存于 `sources/NewPageMergeMDL-source.zip`；手动维护版的完整项目源码由发布标签对应的仓库提供。独立 GPL 转换器的对应源码始终随包附带。

v1.2.26 精简包保留所有工具和导入功能，Windows 继续附带原先已验证的 C4D helper。tinyusdz 已静态链接，运行目录仅保留它的 `LICENSE`、`LICENSE-APACHE-2.0`、`SOURCE.md` 和 `THIRD_PARTY_NOTICES.md`，无需下载源码或开发图片来使用 USD 导入。上述完整项目源码与 GPL 转换器对应源码的获取方式不变。

- **更新：** 解压到新目录并使用整套新工具，保留自己的模型和配置；不要只覆盖主程序或混用旧版辅助文件。模型发布也应整套替换匹配的 MDL/VVD/VTX/PHY/ANI，先在目标游戏验证。
- **无需另找插件包：** Windows 直接 C4D 导入使用包内 helper；Linux 需要先在 Windows 将 C4D 转为 GLB。VRML 转换器保持独立程序及 GPL 许可，使用同一个 ZIP 不改变主程序许可。
- **按需依赖：** 普通编译无需 Python。`tools/` 中的 Python 准备脚本需要自行安装 Python 3，安装包未内置 Python。网格状态和 VRM 运行功能需按各自指南安装 `integration/gmod/` 中的 Lua 消费端，并满足目标游戏条件；解压工具不会自动安装到游戏，也不保证所有游戏支持这些功能。
- **资源：** 游戏、用户模型和 Source VMT/VTF 材质由使用者准备。源场景中的着色器不会自动变成 Source 材质。

### v1.2.28 新增：实验性 CS2 AnimGraph2 工具

完整包包含 `subtools/ag2proportions.exe`（Windows）或 `subtools/ag2proportions`（Linux），使用本项目版本号。它用于 CS2 AnimGraph2 比例适配；主编译器的 Source1 `-game` 配置不能替代其 CS2 数据与工具要求，也不能用它修复 GMod/CSGO 的 MDL 手臂动画。

```powershell
.\subtools\ag2proportions.exe --help
.\subtools\ag2proportions.exe --version
```

Linux 对应使用 `./subtools/ag2proportions`。工具需要已安装的 CS2 数据；生成后编译资源还需要兼容的 CS2 Workshop Tools Resource Compiler，Linux 可按帮助使用 `--compiler-runner wine`。`--generate-only` 只跳过资源编译，仍需读取 CS2 数据。

**在输入模型的副本上操作。** 直接传入 `.vmdl` 会原位编辑，并仅保留首次 `<model>.vmdl.bak`；输出资源写入模型旁的同名文件夹。KV3 job 的 `write_model` 默认是 `false`。`--generate-only` 不会关闭已请求的原位修改。工具生成的 setup 说明会列出骨骼、attachment 和第一人称手臂注意事项；比例 clip 只改变平移，不会修复骨轴或重做蒙皮。请在 ModelDoc 编译并验证实际武器动作、重载、蹲伏、移动及第一人称手臂。本工具仍属实验性；帮助/版本检查不等于 CS2 实机验证。

v1.2.34 先预检编译工具链，源文件、VMDL/首次备份与编译产物暂存成功后才统一发布，普通文件错误或编译失败会回滚；首次备份不替换。同一 VMDL 的并发任务会被拒绝；进程被强制终止后，下次处理该 VMDL 会先恢复未完成事务，或清理已经提交的事务。反编译器对同一模型输出目录采用相同的锁定和恢复机制，并保留目录中的用户文件。

事务记录和暂存数据位于输出旁的 `.newpage-output-transactions`，锁文件位于 `.newpage-output-locks`；异常后不要删除这些文件或带 `.newpage-txn-` 的恢复文件。若输出或恢复备份被其他程序改动，工具会停止恢复并保留现场，避免覆盖外部修改。多个文件的发布过程可能被其他读取程序看到；进程中断恢复不代表对断电、硬件故障或不遵守锁定的外部写入提供绝对保证。真实 CS2 资源验证见 [VALIDATION.md](VALIDATION.md)，不等于最终模型或游戏运行验证。

随包许可位于 `subtools/licenses/zstd.txt` 和 `subtools/licenses/ValveResourceFormat.txt`；源码许可位于 `libs/zstd/LICENSE` 和 `libs/keyvalues3/ValveResourceFormat.LICENSE`。无需下载独立辅助包。

详细说明：[编译前必读](README.md#编译前必读)、[格式导入](O5_FORMAT_IMPORTS.md)、[网格状态](MESH_STATE_WORKFLOW.md)、[VRM](VRM_RUNTIME.md)、[兼容边界](COMPATIBILITY.md)。

## English

1. Download **one Windows x64 ZIP or Linux ZIP** for your platform from [GitHub Releases](https://github.com/NPCodex/newpage-merge-mdl/releases). GitHub's automatic **Source code** links are not installation packages.
2. Extract the entire archive into a new directory, preserving its layout. It contains the compiler, decompiler, subtools, separate VRML converter with its corresponding source, preparation scripts, GMod Lua consumers, documentation, licenses, build manifest and internal checksums. Windows also includes the C4D helper.
3. Open a terminal in that directory. Always set `-game` to the target game/mod directory containing its **correct `gameinfo.txt`**, especially for CSGO and MCV. Set an isolated output directory separately with `-OutDir`.

```sh
./NewPageMergeMDL "/models/model.qc" -game "/games/csgo legacy/csgo" -OutDir "/build/model"
```

On Windows, use `NewPageMergeMDL.exe` and your Windows paths. On Linux, restore executable permission for the required programs if your extractor did not preserve it.

`INSTALL.md`, `upstream-manifest.json` and `SHA256SUMS.txt` are at the package root; validation reports are in `tests/reports/`. Automatic upstream archives also contain the exact merged project source at `sources/NewPageMergeMDL-source.zip`. Complete project source for manual releases is available from the repository at the release tag. The separate GPL converter's corresponding source is always bundled.

The smaller v1.2.26 packages retain all tools and import features, including the previously verified Windows C4D helper. tinyusdz is statically linked, so its runtime directory retains only `LICENSE`, `LICENSE-APACHE-2.0`, `SOURCE.md` and `THIRD_PARTY_NOTICES.md`; USD import needs no source or developer-image download. Complete project source and the GPL converter's corresponding source remain available as described above.

- **Updates:** extract into a fresh directory and use the complete new tool set. Preserve your own inputs and configuration; do not mix older helpers with a new compiler. Deploy matching MDL/VVD/VTX/PHY/ANI files together after validation in the target game.
- **Bundled helpers:** Windows C4D input uses the included helper; Linux requires GLB conversion on Windows first. The VRML converter remains a separate GPL program in the same archive; the main program retains its existing license.
- **Optional dependencies:** ordinary compilation needs no Python. Python preparation scripts in `tools/` require separately installed Python 3; Python is not bundled. Install the `integration/gmod/` Lua consumers as described in the mesh-state and VRM guides when using those runtime features. Extraction does not install them into a game, and support is game-specific.
- **Assets:** supply the target game, your models and Source VMT/VTF materials. Source-application shaders are not automatically converted into Source materials.

### Added in v1.2.28: experimental CS2 AnimGraph2 helper

The complete archive includes `subtools/ag2proportions.exe` (Windows) or `subtools/ag2proportions` (Linux), using the project version. It adapts CS2 AnimGraph2 proportions. The Source1 compiler's `-game` option does not replace this helper's CS2 data/tool requirements; this is not a GMod/CSGO MDL arms-animation repair tool.

```sh
./subtools/ag2proportions --help
./subtools/ag2proportions --version
```

Use the `.exe` on Windows. Installed CS2 data is required. Compiling the generated resources also requires compatible CS2 Workshop Tools Resource Compiler binaries; Linux can use `--compiler-runner wine` as documented by `--help`. `--generate-only` skips resource compilation but still reads CS2 data.

**Work on a copy of the input model.** Passing a `.vmdl` directly edits it in place and keeps only the first `<model>.vmdl.bak`; assets are written beside it in a folder named after the model. KV3 jobs default to `write_model=false`. `--generate-only` does not disable requested model editing. Read the generated setup notes for skeleton, attachment and first-person guidance. The proportion clip changes translations; it does not repair bind axes or re-rig the mesh. Compile in ModelDoc and verify actual weapon actions, reloads, crouching, movement and first-person arms. The helper remains experimental; help/version checks do not establish CS2 runtime validation.

Since v1.2.34, compiler dependencies are checked first; sources, optional VMDL/first backup and compiled assets are staged and published with rollback for ordinary errors. The first backup is retained. A concurrent job for the same VMDL is rejected. After forced process termination, the next invocation for that VMDL first restores an unfinished transaction or finishes cleanup of a committed one. The decompiler applies the same locking and recovery to each model output directory while retaining user files in that directory.

Transaction records and work files live beside the output in `.newpage-output-transactions`; locks live in `.newpage-output-locks`. After an interruption, retain these and any `.newpage-txn-` recovery files. If another program has changed an output or recovery backup, recovery stops and preserves the evidence instead of replacing the external edit. Readers can observe a multi-file publication in progress. Process-interruption recovery is not an absolute guarantee against power loss, hardware failure, or external writers that ignore the lock. See [VALIDATION.md](VALIDATION.md) for bounded real-CS2 resource checks; they do not establish final-model or gameplay validation.

Bundled notices are at `subtools/licenses/zstd.txt` and `subtools/licenses/ValveResourceFormat.txt`; source notices are at `libs/zstd/LICENSE` and `libs/keyvalues3/ValveResourceFormat.LICENSE`. No separate helper archive is required.

See [Before compiling](README.en.md#before-compiling), [format imports](O5_FORMAT_IMPORTS.md), [mesh states](MESH_STATE_WORKFLOW.md), [VRM](VRM_RUNTIME.md) and [compatibility](COMPATIBILITY.md).
