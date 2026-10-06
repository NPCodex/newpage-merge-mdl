# NewPageMergeMDL

自动更新及 GitHub Release 配置见 [AUTOMATION.md](AUTOMATION.md)。

基于 [PulseModel](https://github.com/ToppiOfficial/PulseModel) 的 Source 模型编译工具，加入 StudioMDL-CE / StudioMDL++ 兼容功能与自行实现的动画扩展。

编译器：`NewPageMergeMDL.exe`；反编译器：`NewPageMergeMDL-Decompiler.exe`。
支持 Windows x64 和 Linux 构建，模型输出版本为 v49。Windows 和 Linux 构建由 GitHub Actions 验证。

## 当前功能

- 原 PulseModel 的 SMD / DMX / FBX 编译、模型反编译和辅助工具。
- `$setvariable`、包含文件和动画模型前缀、`$PUSHDInclude`、按骨骼前缀折叠。
- `-cullanims`、`-MostlyOpaque`，重复变量定义警告。
- 自行实现的动画 `copy`、`match pos/rot`、嵌套 `if / else if / else`。
- VTA 同名 `flex` / `flexpair` 多帧：保留独立顶点数据和 StudioMDL 兼容权重区间。
- `$sequence gmtime`，默认保留已有模型的序列顺序，`-noremap` 使用 QC 顺序。
- 带终端颜色的启动横幅；重定向日志保持纯文本。

完整合并尚未完成，语法和差异见 [COMPATIBILITY.md](COMPATIBILITY.md)。不能保证与 StudioMDL-CE / StudioMDL++ 的全部行为一致。

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

测试创建临时 SMD/QC，检查实际 MDL 文件，并反编译动画验证位移、旋转和分支行为。

## 来源与许可

原项目作者：Toppi。保留原 [MIT LICENSE](LICENSE) 与第三方库版权声明。
[UPSTREAM_README.md](UPSTREAM_README.md) 保存上游说明，含旧程序名称和旧下载地址，仅供参考。
本项目没有包含 StudioMDL-CE 或 Tools++ 的闭源二进制或源码。
