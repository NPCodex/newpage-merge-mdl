# CSGO 布料作者接口

本工具把 Source1/CSGO FE 约束写入 MDL。`$cloth proxy.dmx` 使用独立代理反算模型骨架；高级接口也可以直接把已有骨链编译成没有面代理的绳子。运行布料需要支持该 FE 格式的 CSGO 运行时；编译器不代替游戏提供世界碰撞体。

`flex_borders`、`prerotate` 来自参考 QC。本文的 `advanced`、投影设置和可调拟合策略是本工具开放参考 FE 能力的扩展语法，不能原样交给 stock studiomdl。

## 基本约定

```qc
$cloth {
    flex_borders true
    fit_influence_threshold 0.05
    fit_min_influences 3
    quad_bend_tolerance 0.05
    advanced {
        node "$cloth_p2" { mass 2 damping 0.1 }
    }
}
$cloth cloth_proxy.dmx
```

也可以单独写 `$cloth advanced { ... }`。高级块可以重复出现；同名 `node` 的后续字段覆盖之前的字段，未再次指定的字段保留。命令名称不区分大小写，节点匹配也不区分大小写。节点名建议加双引号。

- 普通节点名引用模型骨骼。未被代理使用的骨骼可用 `node` 明确声明为模拟节点；仅作为约束父节点引用且未声明的骨骼作为固定控制节点保留。
- `"$cloth_pN"` 引用代理的第 N 个位置，编号从 0 开始，多个布料代理按导入顺序累计；平面碰撞代理不计入。它不是面角编号。修改代理顶点顺序后需要同步这些引用。
- `node "名称" { position x y z ... }` 创建显式虚拟节点，位置是模型绑定空间中的绝对坐标。它可以参与约束，但不会凭空生成渲染骨骼。`parent` 让其动画参考姿态跟随已有骨骼/虚拟父链。
- 所有位置、长度、半径在声明时乘当时的 `$scale`；后续 `$scale` 不追溯改变它们。方向、权重、质量、迭代次数和粘附系数不随尺度变化。`rod ... auto` 使用缩放后的初始节点间距。
- 碰撞球心和节点平面方程使用父节点的骨局部空间；编译时会处理骨骼重新对齐。显式 `node position` 使用模型绑定空间，两者不要混用。
- 数值必须有限。一般非负标量的输入上限是 1,000,000；坐标分量允许负数，范围为 ±1,000,000（缩放前）。更窄的范围见各表。

## 代理、坐标轴和拟合

每个布料/平面代理根据自身 DMX `upAxis`（`Y` 或 `Z`）转换到主模型绑定空间。转换独立于模型整体 `$upaxis`/旋转；不要手动再给同一代理叠加一次全局旋转。

| 设置 | 默认 / 范围 | 行为 |
| --- | --- | --- |
| `flex_borders bool` | `false` | 自动允许边界固定点旋转，并把同骨骼的固定和动态顶点共同纳入拟合。适合裙腰、袖口等混合边界；不等同于单独的 `cloth_anchor_free_rotate` 图。 |
| `fit_influence_threshold value` | `0.05` / `[0,1]` | 忽略低于阈值的骨骼拟合影响。固定点可以有多个权重；动画位置的父控制采用最强影响骨骼。 |
| `fit_min_influences count` | `3` / 整数 `[3,4096]` | 少于该影响数或不形成有效面的拟合云改用邻接基和反向偏移。设为 `8` 可采用参考的小点云分界。有效邻接基仍需足够且不共线。 |
| `quad_bend_tolerance value` | `0.05` / `[0,1]` | 修正四边形顺序；过度弯曲、没有固定点的四边形沿较短对角线拆成三角形。`1` 禁止弯曲拆分，顺序修正仍执行。它是相邻三角法线夹角正弦的容差，不是角度数。 |
| `prerotate pitch yaw roll` | `0 0 0` / 有限角度，单位度 | 按 Source QAngle 旋转最终 FE 初始位置与姿态，执行在约束构建之后；约束形状、拟合参数、骨局部碰撞数据不重建。`0 90 0` 是绕 Z 轴的 90° yaw。 |

`flex_borders false` 时，同一骨骼只要用于固定点，就保留为动画控制，不再同时作为动态拟合骨骼。原有十种布料属性图和 `cloth_enable` 仍可使用；高级节点设置可以在其结果上指定参数。

## 直接投影渲染蒙皮

```qc
$cloth {
    projection true
    projection_envelope 8
    projection_two_sided true
    projection_island -1
    projection_root "root"
}
$cloth proxy.dmx
```

| 设置 | 默认 / 范围 | 行为 |
| --- | --- | --- |
| `projection` 或 `project_render` | `false` | 将渲染顶点投影到代理表面，并生成所需的布料控制骨/权重。 |
| `projection_envelope` | `0` / `[0,1000000]` | 投影最大距离，模型单位；`0` 表示不限制。超过距离的顶点保留原蒙皮。 |
| `projection_two_sided` | `true` | 在位于相对的两侧表面之间时允许双侧体积绑定；关闭后选择最近表面。 |
| `projection_island` | `-1` / 整数 `[-1,4096]` | `-1` 搜索全部连通分量；非负数限制为按代理点遍历顺序编号的分量。 |
| `projection_root` | 空 | 为无蒙皮代理指定固定根骨；省略时工具生成 `$cloth_root`。 |

投影是本工具扩展。生成的动态渲染控制使用 `$cloth_vN` 名称；不要在原模型中占用这些生成名称。它与只反算已有骨架的默认模式不同，输出的骨数量和蒙皮会改变。

双侧绑定独立搜索相反朝向的内部表面，不会被较近的同侧邻面遮蔽；两侧按距离反比混合。Source1 VVD 最多保存三个骨权重，因此工具保证双侧各留至少一个影响，剩余位置给占比较大的一侧，再在各侧内部归一以保留体积混合比例。单面投影保留最大的三个影响。生成骨骼仍受最终 MDL 骨数量上限约束（默认 255，允许最大配置时 256）；允许临时源骨较多不等于输出可突破此限制。

## 高级节点

```qc
$cloth advanced {
    node "root" { simulated false }
    node "strand1" { mass 2 damping 0.2 local_position 1 local_rotation 0 }
    node "$extra" { position 12 0 20 parent "root" mass 1 }
}
```

| `node` 字段 | 未指定时 / 范围 | 含义 |
| --- | --- | --- |
| `simulated bool` | 新声明节点为 `true`；已有代理点保持原状态 | `false` 固定节点保持动画位置；`true` 参与模拟。先决定静态分区，再生成约束。 |
| `position x y z` | 从同名模型骨绑定姿态取得 | 显式虚拟点的模型绑定空间位置。 |
| `parent name` | 无 | 虚拟点的动画控制父节点；虚拟父链归并到真实控制，循环会报错。 |
| `mass value` | 代理按面积/质量图计算；独立节点为 `1` | 显式正质量，覆盖自动质量。范围 `[0.0000001,1000000]`，不是固定点开关。 |
| `mass_multiplier value` | `1` / 同上 | 乘在显式质量或自动质量上；在面、杆和弹簧权重生成之前生效。质量使用一致的相对单位。 |
| `damping value` | 代理图值或 `0` | FE 指数点阻尼系数。不同于 `cloth_drag` 图的输入，此值直接使用，不再乘 30。 |
| `gravity value` | 代理图值或 `360` | 重力加速度，模型单位/秒²。 |
| `force_attract value` | 代理图值或 `0` | 向动画参考位置的力吸引系数，直接 FE 值，不再乘 30。 |
| `vertex_attract value` | 代理图值或 `0` | 向动画参考位置的位置吸引系数，直接 FE 值。虚拟节点需要动画父绑定。 |
| `local_position value` | 全局 `local_position`，通常 `1` / `[0,1]` | 在普通世界空间运动中，`0` 随模型整体平移，`1` 保留完整平移惯性；传送和局部动画空间仍由游戏处理。 |
| `local_rotation value` | 全局 `local_rotation`，通常 `0` / `[0,1]` | 模型整体旋转中传给该节点的比例，`0` 保留旋转惯性，`1` 全跟随。 |
| `collision_radius value` | 代理图值或 `0` | 节点附加碰撞半径，模型单位。用于碰撞树包围体及刚体/世界形状接触。 |
| `collision_mask mask` | 普通模拟点 `65535`；仅用于拟合的控制默认 `0` | 整数 `[0,65535]`。刚体碰撞只影响与碰撞体 mask 有共同位的节点；`0` 关闭该节点的这类接触。不会替代显式 node sphere/plane 的 child 选择。 |
| `legacy_stretch value` | 不声明则不启用旧伸缩数组；声明时为非负值 | Source1/Dota 旧式约束位置修正转速度的伸缩反馈系数。显式 `0` 表示不把约束位置修正反馈为速度，与完全不启用旧模式不同。它不是弹簧硬度。 |

局部响应、碰撞半径和 legacy stretch 针对模拟节点。质量与 `mass_damping` 配合时也影响阻尼；修改质量会改变约束的反作用分配。

非均匀的 `local_position` 数组中若仍有值为 `1` 的节点，参考运行时会因全局最大值恰好为 `1` 而跳过普通平移的逐节点处理。本工具把描述符中的分支门控值设为紧邻 `1` 的较小浮点数，数组内作者值保持不变，让各节点按实际指定值响应。这是针对 Source1 分支条件的编译兼容修正；全体均为 `1` 时不改变默认行为。

## 显式杆、弹簧和绳链

```qc
$cloth advanced {
    rod "$cloth_p2" "$cloth_p3" auto 0.8 1 1 0.9
    spring "$cloth_p2" "$cloth_p3" 20 3
    rope { "root" "strand1" "strand2" }
    follow "root" "strand1" 0.4
    ftl true
}
```

| 命令 | 参数与作用 |
| --- | --- |
| `rod a b length contraction biasA biasB relaxation` | `length` 是最大长度（模型单位）或 `auto`；必须非零。最小长度=`length×contraction`，收缩比例 `[0,1]`。两个非负 motion bias 乘各节点逆质量后决定位置修正比例。`relaxation` 为 `[0,1]`，`0` 不产生约束。对同一节点对的显式 rod 覆盖自动生成的 rod。 |
| `spring a b stiffness damping` | 初始距离为静止长度。非负硬度和阻尼是力系数，编译时按双方逆质量及指数点阻尼转成 FE 加速度/节点权重。不会接收参考中未实现的 spring stretchiness。 |
| `rope { root child ... }` | 至少两节点。根固定、之后节点模拟；每段自动生成保长 rod，并输出用于重建骨骼方向的 rope 索引。骨骼 X 轴沿绳段方向。子节点不能同时属于两条 rope 或同时作为矩阵拟合控制。可与显式 rod 配合调整段长/松弛。 |
| `follow parent child weight` | child 必须模拟；`weight` 为 `[0,1]`，默认语法中必须给出。按父到子的顺序传递运动增量，`0` 删除该 child 的跟随关系；循环报错。 |
| `os_offset parent virtualChild` | 输出旧 Source1 rope offset 记录。child 必须是显式虚拟节点或 `$cloth_pN`；它替代普通父局部偏移。运行时用父动画位置加游戏供给的 rope offset，因此仅在复现对应旧资产语义时使用。 |

两端都固定的 rod/spring 不产生力记录；两个 motion bias 都为零或弹簧系数全为零也不会产生有效约束。重复的 spring 节点对采用最后声明。

## 高级碰撞

```qc
$cloth advanced {
    node "$cloth_p2" { collision_mask 1 }
    stretch_capsule "left" "right" 2 3 1 0.25
    rigid_sphere "pelvis" 0 0 4 8 1 0.1
    rigid_capsule "thigh" 0 0 0 3 0 0 16 5 1 0
    node_sphere "pelvis" "$cloth_p2" in 0 0 0 20
    node_sphere "pelvis" "$cloth_p3" out 0 0 0 6
    node_plane "pelvis" "$cloth_p4" 0 0 1 0
}
```

| 命令 | 参数与作用 |
| --- | --- |
| `stretch_capsule a b radiusA radiusB mask stickiness` | 两端圆心分别采用节点 a/b 的模拟位置，适合随两根骨变化的碰撞体。半径非负且至少一个为正，mask 是 `[0,65535]` 的整数。两个节点相同则按球处理。 |
| `rigid_sphere parent cx cy cz radius mask stickiness` | 跟随单个父骨动画姿态的球；圆心为父骨局部坐标，半径必须为正。 |
| `rigid_capsule parent ax ay az radiusA bx by bz radiusB mask stickiness` | 两端均在同一个父骨局部空间。编译时连同端点排序半径；运行时退化为被较大端球包含的情形时使用球接触。 |
| `node_sphere parent child in cx cy cz radius` | 将指定模拟 child 限制在父骨局部球内；FE 存储 `1/radius²`。 |
| `node_sphere parent child out cx cy cz radius` | 将指定模拟 child 推到父骨局部球外；FE 存储半径。 |
| `node_plane parent child nx ny nz offset` | 在父骨局部空间约束 `normal·position >= offset`；非零法线自动单位化，offset 同比例归一化。 |

`stickiness` 为 `[0,1]`，`0` 滑动，较大值在接触时增加粘附；参考运行时在约 `0.01` 以下走滑动路径。这个参数只提供给实际使用它的 rigid/stretch 碰撞。逐节点 sphere/plane 的 Source1 路径不读取该字段，因此其语法没有粘附参数。

节点 sphere/plane 指定一个 child，不通过 mask 扩散到全部布料。rigid/stretch 接触会读取碰撞树各节点的 mask，并跳过碰撞体自身的端点。每种碰撞均保留对应的真实 FE 记录，不转成仅用于显示的辅助网格。

## 高级全局参数

```qc
$cloth advanced {
    ftl true
    uninertial false
    mass_damping false
    volumetric 0.25
    smoothing 2 3
    world_radius 2
    add_world_radius 0.5
}
```

| 设置 | 默认 / 范围 | 行为 |
| --- | --- | --- |
| `ftl bool` | `false` | 启用 Follow-The-Leader 运行时标志，并为代理模拟点保留动画 CtrlOffset。与 `follow` 独立，后者是显式逐节点跟随关系。 |
| `uninertial bool` | `false` | 旧式无惯性约束位置修正。显式声明 legacy stretch（包括 `0`）会自动启用相应兼容行为。 |
| `mass_damping bool` | `false` | 旧质量相关阻尼：输出点阻尼再乘节点逆质量；默认采用直接 FE 点阻尼。 |
| `volumetric value` | `0` / `[0,1]` | 将拟合骨骼变换反馈给模拟点的体积拟合量；只有模型存在 FitMatrix 时才有该反馈对象。不是世界实体积碰撞。 |
| `smoothing rodIterations quadIterations` | 平滑率非零时各 `1`，否则 `0` / 整数 `[0,65535]` | 覆盖杆/面速度平滑迭代次数；平滑率仍用普通 `$cloth` 的 `rod_vel_smooth_rate`、`quad_vel_smooth_rate`。设次数而平滑率为零不会产生平滑。 |
| `world_radius value` | `2` / 非负 | 世界球/胶囊接触的附加半径基值，模型单位。 |
| `add_world_radius value` | `0` / 非负 | 在基值上再加这一距离；与节点 `collision_radius` 叠加。需要普通 `$cloth` 的 `world_collision true` 和游戏供给的碰撞体才发生世界接触。 |

## 可直接编译的无面绳链例子

把以下三个文件放在一个空目录中，然后运行 `NewPageMergeMDL.exe rope.qc -game .`。模型仅使用骨链和显式 rod/rope，不需要布料 DMX 面代理。示例骨链沿 +X，符合运行时 rope 的 X 轴方向约定。

`gameinfo.txt`：

```text
GameInfo { FileSystem { SteamAppId 730 } }
```

`rope.qc`：

```qc
$modelname cloth_examples/rope
$body rope rope.smd
$sequence idle rope.smd
$cloth advanced {
    node "root" { simulated false }
    node "link" { mass 2 damping 0.2 }
    node "tip" { mass 1 damping 0.2 }
    rope { "root" "link" "tip" }
    follow "root" "link" 0.2
}
```

`rope.smd`：

```text
version 1
nodes
0 "root" -1
1 "link" 0
2 "tip" 1
end
skeleton
time 0
0 0 0 20 0 0 0
1 12 0 0 0 0 0
2 12 0 0 0 0 0
end
triangles
debug/debugwhite
0 0 -1 20 0 0 1 0 0
1 12 -1 20 0 0 1 1 0
1 12 1 20 0 0 1 1 1
debug/debugwhite
0 0 -1 20 0 0 1 0 0
1 12 1 20 0 0 1 1 1
0 0 1 20 0 0 1 0 1
debug/debugwhite
1 12 -1 20 0 0 1 0 0
2 24 -1 20 0 0 1 1 0
2 24 1 20 0 0 1 1 1
debug/debugwhite
1 12 -1 20 0 0 1 0 0
2 24 1 20 0 0 1 1 1
1 12 1 20 0 0 1 0 1
end
```

输出在 `models/cloth_examples/rope.*`。这是一个编译器输入示例；查看动态绳链需要在支持 FE 的游戏场景中创建该模型并运行模拟。

## 输出与验证范围

高级杆/弹簧输出标量及 SIMD 约束；rope 输出方向重建索引并从 free-node 列表移除相应节点；质量在面和杆权重计算前应用。follow、碰撞、局部响应、节点半径、旧式伸缩和 OS offset 分别对应 Source1 FE 运行时读取的数组/标志。

`tests/cloth_advanced_cases.py` 检查这些输出的节点引用、数值、标志和尺度；`tests/cloth_scope_cases.py` 检查坐标轴、最终 prerotate、混合边界拟合、阈值和四边形预处理。结构验证不等于所有资产的逐帧动态或零穿透已经得到证明。

本接口不开放参考中的空实现、Source2 专属世界 hull/mesh 分支或未消费的 spring stretchiness。输入中的零长杆、循环跟随/虚拟父链和非法节点引用会明确报错。
