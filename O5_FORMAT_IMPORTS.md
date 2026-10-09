# O5：额外格式导入的固定范围

本页关闭五编译器整合清单中 M3D、USD、VRML、C4D 的额外格式项目。导入结果仍须满足 MDL 的骨骼、材质、网格和动画表达限制；注册了格式解析器不等于完整复现对应制作软件。

## 查看当前二进制的真实格式清单

```text
NewPageMergeMDL -importformats
```

输出来自实际链接的 Assimp importer registry，并单列 DMX/SMD/VTA、ufbx、cgltf 等原生入口。扩展名可能由多个 importer 接受，不能把扩展名数量当作独立完整格式数量。固定验收记录在 `tests/scene_integration_cases.py`。

v1.2.23 的实机输出包含 50 个 Assimp registry 条目、77 个不重复扩展名；原生入口与可选 C4D 桥接另列。Neko 2.0 的历史说明只给出“40 多种”和指向 Assimp master 的动态链接，没有冻结解析器版本或逐格式清单，因此这里报告本工具当前二进制的真实注册表，不宣称逐格式复刻 Neko。

## M3D / A3D

内置启用已随 Assimp 源码提供的 Model 3D importer，接受二进制 `.m3d` 和 ASCII `.a3d`。标准场景入口可直接使用：

```text
$modelname example
$UpAxis z assimp
$body model triangle.a3d
```

固定样例验证自制 ASCII 三角形几何。材质、蒙皮和动画取决于该 Assimp importer 实际保留的数据；本次没有宣称所有 M3D 扩展都有对应的 Source 运行行为。

## USD / USDA / USDC / USDZ

内置启用 Assimp 的 tinyusdz 后端，固定版本为 `6050eef932f7d2788656d63297aa488fb0961ed1`。所需源码与许可证在 `libs/tinyusdz/`，配置和构建不访问网络。tinyusdz 主体采用 Apache-2.0，嵌入依赖保留各自许可证。

```text
$modelname example
$UpAxis z assimp
$body model scene.usda
```

固定验收覆盖 USDA 三角网格、单根/多根父节点平移及空场景错误处理。复杂 USD composition、材质着色网络、层变体以及动画的可用范围由固定 tinyusdz/Assimp 后端决定；本工具不会把 USD 场景系统转换为完整的游戏运行时。`InNode`、网格筛选、材质重命名等共用场景选项仍可使用。

## VRML97 / Classic VRML

`.wrl` / `.x3dv` 通过独立的 `NewPageVRMLtoX3D` 程序转换，再由主编译器的 X3D importer 导入。转换程序使用 MeshLab 的 Parser/Scanner（固定 `ad55b47a9b0700e7b427db6db287bb3a39aa31e7`），采用 Assimp 的 Qt → pugixml 补丁。该程序按 GPL-3.0-or-later 单独分发；GPL 解析代码不链接进主编译器或 Assimp。

只转换：

```text
NewPageVRMLtoX3D source.wrl converted.x3d
```

转换后编译（需要 Python 3）：

```text
python tools/vrml_import.py source.wrl --output converted.x3d --compiler NewPageMergeMDL.exe --game GAME_DIRECTORY --modelname vrml_import --upaxis y
```

`--converter` 可指定转换程序位置。脚本在 X3D 旁创建 QC，已有同名 QC 会在转换前明确拒绝覆盖。转换器解析后先写同卷临时文件，完整写入并关闭后才原子替换输出；解析、写入及替换失败保留原输出。输入和输出指向同一文件会拒绝。Windows 参数使用 UTF-16，支持中文和空格路径。固定样例验证三角网格、层级平移、桥接编译、中文路径及错误输入的输出保留。

分发源：`tools/vrml_converter/` 的全部源文件和 GPL 许可证，以及 `libs/assimp/contrib/pugixml/` 的源文件和 MIT 许可证。可用项目 CMake 重建这个独立目标；它不依赖专有 SDK。VRML 的 Script、传感器和交互路由不是 MDL 的运行功能。

独立重建（C++17 工具链，保持上述源目录相对布局）：

```text
cmake -S tools/vrml_converter -B build-vrml
cmake --build build-vrml --config Release
```

## C4D

Windows 的 C4D 导入使用独立的 Cineware 辅助程序，将场景中的显式可编辑多边形转换为 GLB，再使用共用场景导入路径。专有 SDK 本体留在本地构建环境，不放进源码仓库或通用源码包。Linux 可导入预先转换的 GLB。

本次本地构建并验证的完整 Windows x64 发行包包含 `NewPageMergeMDL-C4D.exe`。自动 CI 的 Windows/Linux 构建不下载 Cineware SDK，因此 Windows CI 包不含该程序；需要直接读取 C4D 时，将完整 Windows 包中的辅助程序放到主程序旁即可。可用 `-importformats` 检查本次安装是否具备桥接入口。

将 `NewPageMergeMDL-C4D.exe` 放在主程序旁，QC 中直接引用 `.c4d` 即可。主程序按原始 C4D 路径缓存，自动清理本次转换的临时 GLB，依赖清单保留原始文件。辅助程序也可单独调用：

```text
NewPageMergeMDL-C4D source.c4d converted.glb
```

单独调用时输出文件必须不存在。源码及重建命令位于 [tools/c4d_bridge/README.md](tools/c4d_bridge/README.md)；独立构建要求 Windows x64 MSVC 和单独许可的 Cineware 22 SDK，通过 `ASSIMP_CINEWARE_ROOT` 指定 SDK 路径。SDK 头文件、静态库、示例和文档不随程序分发。

固定验收覆盖可编辑多边形、层级变换、UV/法线、材质名称与基本漫反射颜色，以及中文/空格路径、原始依赖保留和失败时旧输出保护。C4D 厘米及左右手坐标系经 GLB 统一后进入模型编译。当前 importer 不遍历程序化生成缓存，因此生成器必须先在 C4D 中转为可编辑多边形。骨骼蒙皮、动画、模拟及完整着色网络烘焙不在此路径内；Source 材质需另行准备。
