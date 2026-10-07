# v1.2.2 六项改进与验证

| 课题 | 本轮完成 | 验证 |
| --- | --- | --- |
| Bodygroups | 64 位组合计算，2^31 容量保护，固定组 preset mask 处理 | 31 个二选一组通过，32 个超限，已有输出不改写 |
| Skin groups | 分配前按材质数与皮肤数检查表大小和配置预算 | 1001 个皮肤通过；超预算保留已有输出 |
| 全局裁剪 | `$UseLegacyClampMethod` 跨材质分块；同步选择、LOD、flex、眼球索引；稀疏映射避免每块复制整个字典 | 两材质、两 LOD、表情、blank 选择；用户 Hair1 的 22307 顶点拆为三个 10000 上限块 |
| 复杂动画 | 保留 localhierarchy 引用的无权重骨骼；拒绝自父级 | 检查最终骨骼及局部层级父索引；失败保留输出 |
| DMX | 法线合并前角点数组长度/范围检查；balance/speed 有限数值检查；错误传递 | 短法线索引、负索引、越界位置索引及 NaN 提前拒绝；生产 DMX 示例通过 |
| 碰撞 | double 质量累加；非正 mass bias/不可表示体积诊断；显式 `$decomposeconcave` VHACD 分解 | 大偏置仍输出有限质量；封闭 L 形网格输出多个凸块，体积更接近原形 |

本轮共 104 项兼容回归、16 项自动发布测试。Alyx 和 Neko 完整示例继续通过。用户原始极限 QC 有 **2774532096** 种组合：Shoes 组 base 为 396361728、7 个选项，全部组合无法以正值 int32 body 表示，新保护会拒绝。原文件未修改，单独提取其 Hair1 DMX 验证大网格裁剪。此前 v1.2.1 的编译成功记录不代表全组合游戏内可用。历史 `game/shared/animation.cpp` 的 SetBodygroup/GetBodygroup 使用 int body 及整数除法/取模，支持这一正值范围检查。

全局裁剪作用于统一后的 LOD 字典，保守预留三角形容量；与历史源文件预拆分阶段不同。附加身体组共享原 base，会出现在查看器中，选择并非独立。`$decomposeconcave` 是单刚体显式选项，封闭网格、100000 voxel、0.01 误差、depth 10；复杂 ragdoll、任意 rig、游戏物理/渲染和 512 最终骨骼仍未认证或未支持。

English: v1.2.2 adds checked body/skin capacity, opt-in global clamping with synchronized alternatives and remapped LOD/flex/eye data, local-hierarchy bone retention, DMX corner validation, robust mass arithmetic and opt-in connected concave decomposition. The original extreme QC intentionally fails its 2774532096 combination count; isolated Hair1, Alyx and Neko remain useful passing fixtures. Full historical source-stage parity and engine behavior are still unverified.

---

# v1.2.1 六项课题调查与验证

本轮进一步检查历史 StudioMDL 的骨骼、UnifyLODs、DMX、NvTriStrip、动画写入和碰撞实现。历史核心编译器文件作为参考留在独立调查目录；NvTriStrip 作为依赖加入 `libs/nvtristrip`，来源和可移植修改见其 `SOURCE.md`。

| 课题 | 本轮完成 | 尚未完成或未验证 |
| --- | --- | --- |
| 复杂骨骼与动画 | 联合检查 IK、驱动骨、骨骼重命名和折叠后的索引；拒绝超范围 IK/局部层级压缩偏移 | 任意复杂 rig 与参考编译器、引擎行为的全面差分 |
| LOD / 蒙皮 / VTX | 骨骼替换链解析、循环/冲突诊断；检查 DX80/DX90 两种 VTX 布局和跨调色板骨骼索引映射 | 更广泛生产模型及游戏 LOD 切换表现 |
| 复杂 DMX 表情 | 非有限数值预检查；COMBO/DOMINATE corrective 规则数值求值与 flex 几何检查 | 全部 corrective rig、自定义硬边、游戏眼睑表现 |
| 旧版网格算法 | 接入 NvTriStrip，支持 `$UseLegacyStripify` / `-nvtristrip`，一次初始化配置避免并行数据竞争；重复/退化输入可正常结束 | 跨材质全局裁剪 `$UseLegacyClampMethod` 仍未实现；不承诺与所有历史版本完全一致 |
| 动画压缩与写入 | 长 RLE/大位移动画帧编码和 float32 位置回退；255 帧边界与分节验证；连续姿态扫描优化 | 格式本身的压缩 IK 偏移限制仍存在；512 最终骨骼仍未实现 |
| 碰撞 | 消除 PHY 属性、根名与合并名的固定缓冲截断；600 字符输出检查 | 游戏物理模拟与复杂碰撞全面差分 |

## 本轮验证

- 97 项兼容回归与 16 项自动发布测试。测试检查模型字段、VTX/VVD 骨骼映射、表情数值和反编译姿态，包含无效输入不改写已有输出文件的检查。
- 本地再次成功编译用户极限模型 `playermodel_f_compile2_hair.qc` 和 Alyx 模型；输出隔离，不分发用户模型。游戏内加载尚未验证。
- 动画压缩专项：128 骨骼 / 1800 帧，同一输入、构建选项和机器，优化前三次 117.5 / 118.1 / 118.9 ms，优化后 109.9 / 109.5 / 109.3 ms，中位数降低约 7.3%。四个输出文件 SHA256 一致。测量针对压缩范围扫描阶段，不代表所有模型或整体编译速度。
- 标准 MDL/VVD 的 8 位骨骼索引限制没有改变。大于 128 MB 的 VTA 和 130 材质能力继续保留；旧版测试结果见下文。

## English summary for v1.2.1

All six topics were investigated, with targeted fixes and output regressions. The release adds the bundled NvTriStrip backend, validates LOD replacement chains and skin palettes, rejects non-finite DMX values, evaluates corrective flex rules, safely handles oversized animation records and long PHY strings, and improves contiguous animation range scanning. The 128-bone/1800-frame compression benchmark falls from 118.1 to 109.5 ms (three-run medians) with four byte-identical outputs. Full global clamp, arbitrary rig/physics parity, engine validation and 512 final bones remain unresolved.

---

# v1.2.0 技术调查与验证

此前参考历史 CS:GO StudioMDL 的结构与用户提供的参考二进制，以输出测试和前后测量确认修改；历史核心编译器参考文件、参考程序、用户模型均不放入发布包。v1.2.1 新增的 NvTriStrip 依赖随源码发布。

| 课题 | 已完成工作 | 剩余工作 |
| --- | --- | --- |
| 骨骼与动画 | 校验 SMD 父索引；256 输出骨骼及 bone 255 动画反编译验证；超过 16 权重不再越界读取 | 任意复杂 procedural/IK rig 差分；SMD 父骨必须先于子骨 |
| DMX 表情与眼睑 | 多骨骼绑定空间形态键位置验证，重映射后的法线/皱纹回归；已有眼睑规则输出测试 | 复杂 corrective rig、自定义硬边法线和游戏内眼睑 |
| 顶点分割与重映射 | 稀疏索引、顶点归属标记和孤立顶点游标；分割后的 flex/LOD 输出检查 | 跨材质旧全局裁剪未实现；NvTriStrip 已在 v1.2.1 接入 |
| 碰撞 | 多实体 PHY 骨骼重命名、父子关系、根名称及约束回归 | 游戏物理行为与复杂碰撞差分 |
| 文件写入与诊断 | 拒绝 NaN/Inf、无效蒙皮；256 以上输出骨骼在任何文件写入前报错 | 与 CE/++ 的完整诊断文字一致性 |
| 性能 | 小分割专项耗时、VTA 加载峰值内存和字节一致性测试 | 不宣称普遍提速或比参考编译器更快 |
| VTA >128 MB | 181,271,943 字节 / 2,400,000 条真实顶点记录成功编译，检查 30000 个最终 flex 顶点及位移 | 游戏内加载和更多生产模型 |
| 材质限制 | 130 个输出材质的 MDL 数量字段验证；保持动态容器 | 未认证引擎可加载的材质上限 |
| 512 骨骼 | 验证 512 源骨骼经折叠输出；256 输出骨骼最高编号帧动画正确 | **512 最终骨骼未实现**：MDL 排序名称表与 VVD 蒙皮骨骼索引为 uint8；需要额外格式/引擎方案 |

## 测量结果

- 网格分割专项：9000 顶点 / 3000 三角形，`$MaxVerts 3`。同一机器、编译选项与输入下，三次运行中位数从 300.7 ms 降为 15.8 ms；四个输出文件 SHA256 一致。该场景刻意制造大量小网格，不代表所有模型 19 倍提速。
- VTA 专项：30000 顶点 / 80 帧。优化前后编译时间 3.168 / 2.939 秒，峰值工作集 880,447,488 / 376,025,088 字节；四个输出文件一致。直接按行读取消除整文件重复缓冲。可执行 `python tests/stress_vta.py <compiler> --work <new-test-dir>` 复现，不在默认 CI 中生成此大文件。
- 用户极限模型 `playermodel_f_compile2_hair.qc`：成功生成 126 骨骼、572277 个 VVD 顶点，MDL 1,548,640 字节。用户模型只用于本地隔离输出验证，不分发；编译通过不代表游戏运行通过。
- 常规回归包含 85 项模型兼容测试和 16 项自动发布测试。

## 2012 / 2013 参考包调查

两份压缩包中的 `studiomdl.exe` 是相同的 32 位程序，SHA256 为 `039b0216d354dd5a51dea7474422d0167b821d37a72e710dad056ecb03dea19e`。骨骼错误路径在地址 `0x433160` 附近仍比较 `0x100`（256）并使用 256 的错误参数，因此仅凭包名或更新说明不能证实 512 最终骨骼支持。

用户授权后，已尝试在独立目录执行附带 DLL 的帮助和最小模型；包括隐藏控制台方式，均返回 1、没有日志或模型输出。参考程序在当前依赖环境无法启动，尚未取得可验证的 512 输出样本。此限制不影响本项目的独立 VTA/材质/骨骼回归，但不能将其描述为已完成参考差分。

## English summary

The batch adds source validation, safe 256-bone animation output, sparse mesh partitioning and reduced SMD/VTA loading memory. A real 172.88 MiB VTA, 130 materials, 512 source bones after collapse, DMX morphs, flex/LOD splitting, collision renaming and the supplied extreme model have output tests. A partition stress case improves from 300.7 to 15.8 ms with identical output; VTA peak working set falls from 880,447,488 to 376,025,088 bytes. These are specific local measurements, not general compiler speed guarantees.

512 final bones remain unsupported because standard MDL/VVD tables use byte-sized bone indices. Both supplied reference executables have the same SHA256 and a static 256-bone diagnostic guard; execution exits silently before compilation in the current dependency environment. Legacy global clamping, comprehensive complex-rig parity and in-game validation remain open.
