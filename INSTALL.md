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

- **更新：** 解压到新目录并使用整套新工具，保留自己的模型和配置；不要只覆盖主程序或混用旧版辅助文件。模型发布也应整套替换匹配的 MDL/VVD/VTX/PHY/ANI，先在目标游戏验证。
- **无需另找插件包：** Windows 直接 C4D 导入使用包内 helper；Linux 需要先在 Windows 将 C4D 转为 GLB。VRML 转换器保持独立程序及 GPL 许可，使用同一个 ZIP 不改变主程序许可。
- **按需依赖：** 普通编译无需 Python。`tools/` 中的 Python 准备脚本需要自行安装 Python 3，安装包未内置 Python。网格状态和 VRM 运行功能需按各自指南安装 `integration/gmod/` 中的 Lua 消费端，并满足目标游戏条件；解压工具不会自动安装到游戏，也不保证所有游戏支持这些功能。
- **资源：** 游戏、用户模型和 Source VMT/VTF 材质由使用者准备。源场景中的着色器不会自动变成 Source 材质。

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

- **Updates:** extract into a fresh directory and use the complete new tool set. Preserve your own inputs and configuration; do not mix older helpers with a new compiler. Deploy matching MDL/VVD/VTX/PHY/ANI files together after validation in the target game.
- **Bundled helpers:** Windows C4D input uses the included helper; Linux requires GLB conversion on Windows first. The VRML converter remains a separate GPL program in the same archive; the main program retains its existing license.
- **Optional dependencies:** ordinary compilation needs no Python. Python preparation scripts in `tools/` require separately installed Python 3; Python is not bundled. Install the `integration/gmod/` Lua consumers as described in the mesh-state and VRM guides when using those runtime features. Extraction does not install them into a game, and support is game-specific.
- **Assets:** supply the target game, your models and Source VMT/VTF materials. Source-application shaders are not automatically converted into Source materials.

See [Before compiling](README.en.md#before-compiling), [format imports](O5_FORMAT_IMPORTS.md), [mesh states](MESH_STATE_WORKFLOW.md), [VRM](VRM_RUNTIME.md) and [compatibility](COMPATIBILITY.md).
