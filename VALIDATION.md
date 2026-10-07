# v1.2.4：新增功能与验证 / Features and validation

## 资源查找 / Resource lookup

QC 文件旁的资源和显式 include/source 目录优先，随后按 `-game` 目录中
`gameinfo.txt` 的 `FileSystem/SearchPaths` 声明顺序查找。支持 Game/Mod/Content
搜索项、`|gameinfo_path|`、`|all_source_engine_paths|`、`|appid_550|/left4dead2`。
AppID 查找读取 Steam 的 libraryfolders 和 appmanifest，支持其他磁盘的游戏库。
Steam 根目录可通过 `-steamdir <path>` 或 `NEWPAGE_STEAM_PATH` 指定；Windows
默认读取当前用户 Steam 注册表项。未安装的 AppID 输出警告并跳过。

目录及其根目录 VPK、显式 VPK、`*_dir.vpk`/分卷、VPK v1/v2 和 preload 均可读取。
档案索引及数据范围经过检查，资源按需解包到独立临时缓存，退出时清理自己的缓存。
目录 `*` 展开子目录；未实现任意通配符、压缩 VPK 或 GMod 专有 mount.cfg 语义。

Local script/explicit paths precede ordered gameinfo mounts. AppID lookup discovers
installed games across Steam libraries; missing apps warn. VPK extraction is lazy
and isolated. This implements compiler resource search, not the entire runtime
mount system of every Source game.

## Draco 与动画烘焙 / Draco and animation baking

glTF 的 `KHR_draco_mesh_compression` 三角形直接通过 bundled Draco 解码。属性映射
使用 Draco unique IDs，保留法线、UV、蒙皮属性及外部未压缩形态键。损坏流、数量/类型
不匹配明确失败。自制回归使用超出 accessor 范围的 unique IDs，防止混淆两种索引。

```qc
$modelname example/animated.mdl
$body body animated.gltf BakeSceneAnimation Move SceneSampleRate 30
$sequence idle idle.smd
```

`BakeSceneAnimation` 选择具名 clip；静态序列用于引擎渲染时的骨骼姿态。烘焙包含
节点变换、蒙皮、动画缩放、形态键权重、位置与法线增量，输出 NWAY 表情帧和
`animated.vertexanim.json`。末尾不足一个采样周期时仍保留精确终点时间。glTF 快速路径
对 LINEAR/STEP/CUBICSPLINE 先采样，再生成线性相邻表情帧。提高采样率可减少误差；
运行时线性帧插值不会无损保留 STEP 跳变或任意三次曲线。

每 clip 最多 4096 帧、1600 万个源顶点采样；零缩放、找不到的 clip 和无效权重明确失败。
采样目标扩展渲染边界和半径，避免只使用 bind mesh 时发生过早裁剪。
骨骼动画不再叠加相同烘焙运动。网格替换动画尚未支持。

GMod 客户端使用发布包的 `integration/gmod/newpage_vertexanim.lua`：

```lua
local playback = include("newpage_vertexanim.lua")
local metadata = assert(playback.Load(entity:GetModel()))
-- 每帧调用；调用方管理循环、暂停、时间和 entity 生命周期。
playback.Sample(entity, metadata.clips[1], seconds)
```

将 Lua 放入模组可 include 的目录，将 JSON 与模型一同安装。其他游戏需要等价的
控制器驱动代码。GMod 的原生与网络表情控制器输入范围不同，播放器已分别处理；见 [SetFlexWeight 文档](https://wiki.facepunch.com/gmod/Entity:SetFlexWeight)。Baking is sampled vertex-cache playback, not native bone-scale
tracks. Other runtimes must drive the two documented flex controllers themselves.

## 布娃娃 / Ragdolls

```qc
$collisionjoints physics.smd {
    $mass 10
    $rootbone root
    $maxconvexpieces 4
    $decomposeconcave
}
```

按每个物理骨骼的局部空间调用 VHACD，再进入原有体积/质量、父子排序和约束输出流程。
普通 `$concave` 的岛分割行为保留。VHACD 使用 100000 voxel、深度 10、0.01 体积误差
及指定 piece cap；分解是近似算法，复杂输入应检查实际凸体，而非保证最优分解。

## 验证 / Verification

默认兼容回归 **127 项**，自动化回归 **16 项**。新增样例覆盖挂载搜索顺序、第二个
Steam 库、VPK v1/v2/分卷/preload/损坏数据、Draco 属性/UV/形态键/损坏流、位移与
缩放/权重/蒙皮烘焙、采样元数据、渲染边界、性能 JSON、眼睑描述符和多骨凹体分解。

`tests/reference_differential.py` 使用自制样例分别对照用户提供的 CE 和 NekoMDL。
六组为骨骼/attachment、jiggle、IK/LOD、VTA 表情、眼睑和 DMX。比较骨骼顺序、父子、
bind transform、procedural 类型、IK/flex 数量、描述符顺序、控制器范围及眼球/眼睑
目标与绑定；两份参考均通过。既有数值回归验证 corrective、domination 和驱动骨。
这些是明确样例的检查，不是任意复杂 rig 或逐字节文件兼容认证。

2026-10-07 在本机 Garry’s Mod x64 / gm_flatgrass 实测：

- Alyx：113 个骨骼、61 个控制器；白色材质覆盖下正常绘制，表情/眼睑状态和强制 LOD 0/1 截图有几何像素差异。
- 自制顶点动画：0、0.5、1 秒三个采样时刻可见，播放输出各不相同。
- 自制 LOD：高精度 L 形网格实际替换为低精度四面体，截图检查明显几何差异。
- 自制双骨凹形布娃娃：两个物理体各 mass=5，volume≈3.007805，落到地图地面，位置保持有限值。

测试脚本为 `prepare_game_validation.py` 和两个 `game_validation_*.lua`；需要用户的
face QC 和已安装的 GMod，未纳入无游戏环境的 CI。安装在明确命名的
`newpage_validation_v124` 目录。报告/截图只在本机保存；不分发用户模型或参考程序。
使用 `prepare_game_validation.py ... --autorun` 安装专用 InitPostEntity 测试入口，
关闭测试游戏后移除 `lua/autorun/server/newpage_validation_v124.lua`，避免普通游戏触发测试。
启动参数应包含 `-noworkshop -noaddons +r_jiggle_bones 0 +flex_smooth 0 +map gm_flatgrass`；
重复 neutral 截图量化光照/渲染噪声，顶点动画还检查实际屏幕位移和中点线性关系。
实际材质着色、其他游戏、任意生产模型和所有动画/物理状态仍需独立验证。

## 性能 / Performance

`-perfjson report.json` 输出 schema/version、load_ms、compile_ms、write_ms、total_ms、
peak_working_set_bytes、骨骼和顶点数量。加载阶段包含资源挂载及 QC/source 读取。
Windows 使用峰值 working set，Linux 使用 getrusage peak RSS；二者不能直接等同。

```powershell
python tests/benchmark_models.py NewPageMergeMDL.exe --qc model.qc --runs 3 --report benchmark.json
python tests/reference_differential.py NewPageMergeMDL.exe --reference reference.exe --work isolated-diff
```

基准把输出重定向到独立临时目录，以三次运行中位数和每轮输出 SHA256 检查可重复性。
本机三份生产输入为 Alyx、Neko 的完整 survivor_teenangst 和独立 Hair DMX 夹具；实际
测量汇总见 `tests/reports/v1.2.4-validation.json`。它们不是跨机器速度承诺，也不代表
与其他编译器的系统性能对比。用户原始模型及 QC 不会加入源码或发布包。
