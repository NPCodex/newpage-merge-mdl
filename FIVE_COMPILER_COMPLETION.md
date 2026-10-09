# 五编译器固定清单结账：v1.2.23

本次范围固定为 2026-10-08 总账的 R1–R6、E1–E3、V1–V7、S1–S6、O1–O5；
用户随后授权实现 O 区。以下列出实现、可复现证据、明确策略及边界。
CSGO A1–A7/B1–B4 的前一轮 11 包保持关闭，不重新拆出待办。
PulseModel 固定基线 `52cf296a953fd6c2d072e34cfde5eb8eccc95564` 已作为主体保留。
参考程序和生产模型素材不在源码或发行包中。

## R：实现与修复

| ID | 交付及固定验收 |
| --- | --- |
| R1 | 读取 gameinfo 的 `Tools/studiomdl` 及 `cfg/commandline.cfg` 中 `CommandLine/<QC stem>/studiomdl`。优先级 gameinfo < cfg < 显式 CLI，同层后值胜；QC stem 忽略大小写、不带 `.qc`。引号参数、名字匹配、CLI 覆盖与 `-nodefaultargs` 有回归，八组 ++ 对照确定优先级。 |
| R2 | `$qccompatibility native|neko`。neko 模式覆盖裸 ON、未定义左值、OR 未定义操作数、已胜出后的 elif、`1e2 == 100` 及引号基线；native 保留严格未知变量错误。 |
| R3 | 移除错误的全模型 32768/65536 flex 顶点预算。最终 mesh 的 uint16 局部索引仍严格限制。32769、两材质+LOD 共 65537、分割的 511451 个移动顶点检查索引、增量、完整几何及 VTX 三角总数；不是任意游戏接受该容量的保证。 |
| R4 | ufbx 使用独立 cluster bind/geometry-to-bone 矩阵；检测共享骨绑定冲突。场景 rest 与 bind 不同的双骨、两个动画采样及没有 NodeAttribute 但被蒙皮引用的骨均有固定验收。 |
| R5 | Assimp key STEP/LINEAR/SLERP 与 DEFAULT/CONSTANT/LINEAR/REPEAT 边界；Collada 原始 STEP/LINEAR/BEZIER 在读取时按采样率求值。缺少可表达切线的插值要求作者预烘焙，避免伪装为线性。原有 glTF STEP/CUBICSPLINE 保留。 |
| R6 | 现有世界坐标范围裁剪警告增加首个越界帧（从 0 计）、骨名和位置；顶点越界标注主影响骨，骨 bounds 越界给出有适用条件的 `$skipboneinbbox` 提示。不会声称它能消除越界顶点或作者 hitbox。 |

示例配置：

```text
"Tools" { "studiomdl" "-nodx80" }
```

```text
"CommandLine" { "avatar" { "studiomdl" "-rootlod 1" } }
```

第二段放在游戏目录 `cfg/commandline.cfg`，匹配 `avatar.qc`。默认参数从显式选择的
game 读取一次，不递归追随配置中的 `-game`。可用 `-nodefaultargs` 禁用。

## E：参考资料结论

| ID | 结论 |
| --- | --- |
| E1 | CE x86/x64 的 `replacemodel` 控制样例成功，三类候选 `replacemesh` 用法均拒绝，两程序无对应 ASCII/UTF16 命令字。现有日志不足以确定可实施语法；保留“参考证据未解决”，不猜成 `replacemodel` 别名。需要新的有效版本/语法/输入才会改变这个结论。 |
| E2 | 同一个 2013 EXE 搭配 2012 包依赖置于隔离 `bin/` 已恢复编译。实测 130 材质被 max64 拒绝；255 最终骨通过，256/257/512 拒绝；约 172.9 MiB VTA、30000 几何顶点+9000 移动顶点通过，30000 移动顶点被 max10000 拒绝。当前 CSGO DLL 配置仍访问违例，分别记录。这些受限参考能力没有暴露本工具的新移植缺口。 |
| E3 | Neko “40 多种格式”指向浮动 Assimp 文档，未给版本化集合；不能从宣传恢复精确集合。本工具 `-importformats` 实测 50 个 Assimp registry 条目、77 个唯一扩展名，原生入口另列。Neko 128 个不同 skin 行成功写出；256/1024 行测试访问违例，因此只确定成功下界 128，不宣称精确上限。未测格式不宣称完整等价。 |

## V：有限验收

| ID | 验收范围 |
| --- | --- |
| V1 | CE 多骨 controller remap、corrective/inverse、硬边/自定义法线、wrinkle/眼睑组合。 |
| V2 | Neko 两个 studio、flex/flexpair/眼睑、RenameMorph、材质预改名、分割与一层 LOD 组合；两个不同源分别声明 replacemodel。 |
| V3 | 九类骨规则组合。发现并修正早期裁骨丢失仅用于低 LOD、显式 hitbox 和动画的骨；后续 force-collapse 策略继续生效。 |
| V4 | PMX 蒙皮及命名 vertex/group morph（补齐 Assimp 未拷贝 morph 的缺口）；FBX 多 take/InNode/采样率/轴；通用边界；meshopt OCTAHEDRAL/QUATERNION/COLOR 及现有 EXPONENTIAL。 |
| V5 | 碰撞改名、512 源骨、staticprop+blank、90000 顶点/30000 面、procedural 错误名顺序、无效动画错误及已有输出保留。 |
| V6 | GMod 本轮6项客户端/2项服务端检查与画面通过，覆盖状态、VRM表情/材质/弹簧、LOD及双刚体；L4D2三模型在离线地图实体创建、模型名读回及画面通过。Insurgency仅进入contact，模型加载未认证；未安装HL2/CS:S/TF2/SFM未运行。历史CSGO/MCV证据不计作本轮；详情见发布验证报告。 |
| V7 | 原始 Plum 和自制 90000 顶点 SMD，成功配置各三次。Plum 本工具/CE 中位 1.713s/10.850s，峰值 628.6/696.1 MiB；大 SMD 0.224s/0.475s、80.7/211.4 MiB。Plum 最终骨分别126/104，不能宣称同等输出倍数。Neko Plum 缺 dmxconvert，++ Plum 拒 MaxVerts，++ 大 SMD 超限；Neko 大 SMD 虽 exit0，VTX 仅覆盖65536唯一局部顶点，尝试时间不作同等输出比较。记录对应测试二进制散列，未声称最终所有平台普遍更快。 |

## S：明确选择

| ID | 策略 |
| --- | --- |
| S1 | `$boneweightpolicy native|neko|ce`：前两者阈值 .0001，ce 在已归一化导入权重上额外剔除小于 .001 的影响并再次归一化，至少保留最强影响。按源读取时捕获并进入缓存键；不是对未归一化作者数据的逐字节 CE 模仿。 |
| S2 | 面部模式 `$dmxcompatibility native|ce|neko`、CEBoneRules、眼球开关继续显式选择。NoAutoDMXRules 是按源关闭自动规则；Legacy 会清先前规则/控制器，不能等同 CE 保留控制器的观察行为。 |
| S3 | 统一 LOD 字典后分割，保持有效几何。Neko 的源阶段预分割次序不是输出字节一致承诺。 |
| S4 | `$fbxcompatibility native|neko`：native 使用 ufbx 与文件帧率，neko 使用 Assimp 与默认30Hz或显式 SampleRate；`$UpAxis ... assimp` 作用于该兼容后端。固定24/30/60帧率及Y/Z轴样例。 |
| S5 | 保留255默认骨预算、动态容器、默认序列顺序保护；可显式设预算及 `-noremap`。不倒退到 Neko 默认129或旧固定缓冲。 |
| S6 | 不复制 CE addcontrollerbyflex 范围解析缺陷；保留 copy 的扩展语义。本工具 MDL49、++ MDL48，不要求全文件相同。 |

## O：获授权的扩展

| ID | 交付与边界 |
| --- | --- |
| O1 | 蒙皮 GPU 实例离线展开成独立骨/几何/动画，局部蒙皮组合固定为 `N*I*inverse(N)*J*inverseBind`。支持正的均匀实例缩放；非均匀缩放/剪切需先烘焙，不能用普通刚体骨轨道保留任意仿射动画。NoFastGltf 遇实例自动提示并改用原生展开，避免静默丢实例。 |
| O2 | `tools/mesh_states.py` + GMod bodygroup 播放器：有限拓扑状态、blank、显式时间或fps、重复顺序与循环/末帧保持。见 [工作流](MESH_STATE_WORKFLOW.md)。 |
| O3 | VRM 0/1 命名表情、binary/override、采样表情片段、独立材质适配、弹簧骨/球胶囊碰撞/center/父子传播客户端。见 [VRM_RUNTIME.md](VRM_RUNTIME.md)。有界物理近似、需要模组与匹配Source材质；不声称任意Unity/MToon运行时透明复现。 |
| O4 | 输出事务持久 journal、每输出进程锁、hash保护、commit标记；下次编译在读旧序列前恢复中断。九项真实进程中断/并发/路径别名验收。损坏日志或被外部修改的文件保留并报错；不保证任意硬盘损坏、断电重排序下绝对无损。 |
| O5 | M3D、USD内置；VRML独立GPL转换器；Windows C4D使用独立Cineware桥接。SDK仅在本地构建，不发布SDK示例或文档。依赖版本、许可证及各格式固定验收见 [O5_FORMAT_IMPORTS.md](O5_FORMAT_IMPORTS.md)。 |

## H：当前格式和引擎下的边界

| ID | 不作为后续隐藏待办 |
| --- | --- |
| H1 | 不改模型格式和引擎，不能让 uint8 最终骨索引表示512/1024可蒙皮骨；大量源骨可先折叠。 |
| H2 | 每顶点3最终权重、mesh/strip局部16位编号、8 LOD、相关16位索引、32位文件偏移及bodygroup范围不能无限扩展。R3全局flex限制已单独修复。 |
| H3 | 未改引擎不会自动执行UTC、任意骨缩放/顶点动画、FE世界碰撞、作者约束、完整VRM/Unity行为；客户端适配和离线烘焙有明确契约。 |
| H4 | 现有renderer的原生SubD分配stub需引擎修复；默认离线SubD已可用。 |
| H5 | 五者互相冲突的默认值和算法不可能同时成为同一个默认，也不能保证所有文件、所有帧相同。 |

上述已知类别一次性结账。E1及E3未公开信息不会被改写成“全部兼容”，也不在没有新证据时
自动衍生新批次。未来新的上游版本或具体输入缺陷属于新证据维护；不是本表藏着另一批功能。
