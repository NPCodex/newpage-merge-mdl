# 2026-10-20 工具整批修复验证

源码基线：`f78853858ac1961890aa0124a732abee1a135afc`（v1.2.36 替换构建）。本轮源码版本为 1.2.37；此报告不代表已发布。原始复现使用正式 Windows 包，修复验证使用本轮重新构建的程序。

## 固定范围与结果

| 编号 | 项目 | 实现与验证 |
| --- | --- | --- |
| F1 | DMX 动画名称歧义 | 名称检查和选择统一大小写规则，重复/保留名明确失败；不同动画位移对照通过。 |
| F2 | 低 LOD 独立蒙皮 | 导出有效 `$skinnedlods`；CSGO/GMod 编译、反编译、重编译后保留各 LOD 权重。 |
| F3 | VMD 非有限输入 | PMX 骨位置、目标绑定变换、比例及最终姿态检查；NaN/Inf/比例溢出拒绝并保留旧输出。 |
| F4 | 错配 VVD/VTX | 核对头部、LOD/模型数量和 MDL checksum，错配失败且不发布部分结果。 |
| F5 | DMX DAG 循环 | 骨架/网格路径检测循环、多父级及深度；自环、深链、重复子级有明确诊断。 |
| F6 | 坏 attachment/hitbox/PHY | 非空坏表、错误骨引用和损坏 PHY 明确失败；缺 PHY 单独警告无法验证碰撞完整性，MDL 本身不能证明曾有碰撞。 |
| F7 | Release 日志复发 | 以现用平台包内 manifest 源提交取增量，跨平台核对来源，隐藏提交标识去重并清除 CI 标记；上传前保存旧正文/来源检查点，首次或部分替换失败后重试仍保留完整增量，不从旧标签盲目追加。 |
| F8 | 文档一致性 | 精确源码统一指向包内源码归档及 manifest；区分原生工具持久恢复与 Python helper 的普通失败回滚；补齐包内 Markdown 验证报告，避免文档链接失效。 |
| F9 | 同模型内部输出覆盖 | 一次分配根网格及完整 LOD 名称族，预留 physics/joints，动画独立命名且预留合成绑定动画；大小写别名不覆盖，QC 引用一致。 |
| F10 | 平台条件否定 | 解析受支持的平台条件、否定与布尔组合；未知/损坏表达式不静默启用。 |
| F11 | SMD/VTA 宽松数值 | 全段校验数值完整性、范围及有限性并报告文件/行；保留合法行尾注释和 VTA 帧标签。 |
| F12 | FBX 动态缩放 | 采样时检查不能表达为 MDL 骨动画的缩放/剪切变化，明确要求预烘焙。 |
| F13 | FBX 帧数溢出 | 转整数前检查时长、帧率及帧数，超限/非有限值失败。 |
| F14 | 共享动画解码 | movement、RLE、FrameAnim、外部块及 IK 范围校验并传播失败，反编译器/L4D 不再把损坏动作输出为成功的静止动画；解码使用独立内存预算。 |
| F15 | Helper 模型/JSON 不成套 | 隔离编译，统一发布模型伴随文件、生成源和 JSON；锁住 JSON 等普通失败保留整套旧结果。 |
| F16 | Helper 覆盖源输入 | 预检输入/生成输出的实际路径及文件别名，拒绝覆盖原 VRM/glTF。 |
| F17 | Lua 元数据不足 | VRM/vertexanim 在修改实体前验证结构、必需字段、时间和数值；Lua 5.1 + API 桩测试，不称为游戏实测。 |
| F18 | AG2 VPK CRC | 对 preload 与资源正文拼接后的完整资源核对 CRC32；真实官方资源正确 CRC 通过，篡改 CRC 失败且保留旧输出。 |
| E1 | VMD IK/FK | 解析逐帧开关并保持到下一键，左右腿独立；关闭时使用腿/膝/足 FK，重新启用恢复 IK。 |
| E2 | 相机投影 | 当前 SMD/pulsecamera 输出端不能保留正交，遇正交键明确失败；未伪称已增加正交渲染支持。 |
| E3 | AG2 完整模型与实机 | 完整带网格 SAS 原比例/1.1 比例模型均已实际进入本地 CS2；同机位骨架对照显示比例差异，P2000/M4A4 持握、射击、重载、蹲伏/起立观察通过。第一人称仅为原版 viewmodel 无回归对照；没有宣称生成第一人称图或 live graph 节点调试通过。 |
| E4 | 默认动画时序 | 未显式指定播放 FPS 时继承有时序的源动画采样率；显式 QC FPS/默认 FPS 覆盖保持有效。 |

## 验证边界

- Windows 实际 ZIP 解压后的整包验证通过：兼容测试 421/421（包括本次 9 组输入、时序与平台条件回归）、其他 unittest 70 项，以及 subtools integrity 61、CLI 63、publication 21 项均通过；清单/SHA256、版本和 VRML 转换 smoke 同时通过。
- 本机 Windows 候选使用 MSVC Release、IPO 关闭、动态 CRT（MultiThreadedDLL），需要 VC++ 运行库。这是本机验证候选；正式发布流程仍使用静态 CRT 配置。首次整包验证源码为 `02bccf6`，后续仅日志流程、打包和文档修订不改变这组已验证的原生源码。
- VMD 新功能 7 组及既有 18 种错误输入通过；VPK v1/v2、preload/正文组合共 36 例通过。
- 已保存的 Plum 原始文件副本（131 文件，约 151 MB）内容哈希未变。native/CE/Neko 三模式均编译、结构校验和完整反编译通过；原 `Desktop/gmod` 目录目前已不存在，使用的是先前保存且有原始哈希的精确副本。
- 新反编译专项覆盖真实权重往返、同模型输出冲突及损坏输入时旧输出保留；没有将所有外部 MDL 的任意损坏组合宣称为已经验证。
- Python helper 的普通失败回滚不承诺强杀/断电后的持久恢复；既有 VMD/L4D 原生事务恢复不受此修复缩减。
- AG2 的 [完整人物实机报告](ag2-gameplay-20261020.md) 记录有效对照、动作截图、资源来源和限制。它仍为实验性工具：当前安装缺少 `animgraph2_editor`，不扩为任意自定义骨架、全部武器或生成第一人称图认证。CS2/VConsole 已退出，原配置和官方目录 VPK 哈希不变；隔离 addon 仅通过显式测试参数加载。
- Linux GCC、Clang 均已完成全工具构建、恢复与格式测试、实际归档验证及 ELF/依赖/执行权限 smoke，每套均通过 421 项兼容测试。首轮 [CI 39410334048](https://github.com/NPCodex/newpage-merge-mdl/actions/runs/39410334048) 对应 `02bccf6`；包含发布/打包收尾及 Python 3.12 / Lua 5.1 回归的最终 [CI 39411422872](https://github.com/NPCodex/newpage-merge-mdl/actions/runs/39411422872) 对应 `78aa1e5`，两套均成功。最终仅补充实机报告与链接，不修改这组已验证的原生源码。
- Release 重试 14 项、automation 48 项、真实 Lua 5.1 元数据/数学 13 项及三份 workflow 语法检查通过。正式流程固定 Python 3.12 / Lupa 2.6 并显式导入 Lua 5.1，避免依赖缺失时跳过测试。

复现及机器日志保留在本机 `.diagnostics/toolkit-audit-20261020` 与 `.diagnostics/toolkit-fixes-20261020`。长期自动回归位于 `tests/compiler_input_cases.py`、`tests/decompiler_roundtrip_test.py`、`tests/vmd_motion_features_test.py`、`tests/ag2_vpk_test.cpp`、`tests/helpers_publication_test.py`、`tests/runtime_metadata_test.py` 和 `tests/test_replacement_notes.py`。
