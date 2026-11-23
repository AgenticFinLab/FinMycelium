# 2 · 关系、参与者与 Context

[总览](0-overview.md) · [Action 排布](1-action-layout.md) · [页面与证据](3-view-and-evidence.md)

每条表达事实的线都应能回到具体的图数据。Action 关系回到关系 ID，身份与对象线回到 Action 字段，背景适用线回到特定 ContextRef，溯源线回到引文或来源引用。反向核对时，每条原始关联均应能从页面或详情定位，即使本页无法画出两个端点。视觉标记的颜色、线型与默认可见性见[全图图例](4-visual-legend.md)。

## 2.1 Action 之间的关系

| 类型 | 从图上的 from 读向 to | 方向 |
| --- | --- | --- |
| `precedes` | from 先于 to | 有向 |
| `overlaps / order_unknown` | 两个行动确有时间重叠／这对行动先后未定 | 对称 |
| `responds_to` | from 回应 to | 有向 |
| `enables / triggers / prevents` | from 使能、触发或阻止 to | 有向 |
| `continues / resumes` | from 延续或恢复 to | 有向 |
| `interrupted_by` | from 被 to 打断 | 有向 |
| `joint_action` | 两个既有行动共同构成一项行为 | 对称 |

Action 关系用紫色线，标签依次写起点 Action、谓词和终点 Action，例如 `A04 continues A21`。有向关系的箭头指向 to，对称关系无箭头。`inferred` 关系和 `order_unknown` 用虚线，其余 `observed / asserted / derived` 关系用实线。虚线的具体含义可从谓词和详情确认。多种关系可连接同一对行动，每项记录都能单独选中并检查。[关系矩阵](../person-event-structures/2-action-graph.md) · [关系与支持字段](../person-event-builder/2-graph-contract.md)

- **同一 Phase。** 打开即显示关系，线从一张 Action 卡连接到另一张。上下分支时端点仍落在对应卡上。回应、延续可以向左，过程箭头无需沿时间轴向右。
- **跨 Phase。** 本端 Action 与顶部已有的对端 Phase 标签连线，保留关系原方向。标签仍写两个 Action 和谓词。两端页面都提供查看、跳转到对端 Action 及返回入口。页底无需再列一份跨页关系，卡片正文也无需插入跳转标签。
- **路由。** 优先避开卡片正文、刻度和其他箭头的端点。空间不足时，标签可移入相邻空位，用短引线指回本关系。缩放、滚动或展开阶段导航后，标签仍跟随原线。浏览器不得把标签定位到远处的页面角落。只为布线绕行不会改变语义方向。

## 2.2 Context 的作用范围

Context 描述影响行动理解的背景事实。图中同时编码两个不同维度。**作用范围**说明这段背景适用于哪里，**类别**说明它描述环境、人物关系还是主体状态。[上下文模型](../person-event-structures/3-context-model.md)

| 本页范围 | 位置和外观 | 如何读出关联 |
| --- | --- | --- |
| Phase 基准 | 浅蓝底、粗顶边。多行动页放在 `Shared phase context`。单行动页把可继承的条件或约束放到该 Action 上方，注明 `Phase-wide`。 | 条件或约束用带谓词的赭色虚线连接到每项有效继承的 Action。选择标签或分支可查 Phase 原引用及其证据。 |
| Action 显式关联 | 暖色卡，靠近引用它的一项或多项 Action | 前提、触发、约束优先靠近目标行动上方，结果靠近下方。无论最终放在哪一行，都由带类型的连接说明作用。 |
| 本页附加参考 | `Additional context` 区，灰底、虚线边框 | 例如因日期或共用引文而可供参照。没有明确适用记录时，不连向任何 Phase 或 Action。 |

背景类别由左侧色条及文字表示。底色、左侧条、线上谓词和视角可以独立组合，具体颜色及页面英文见[范围与类别图例](4-visual-legend.md)。`world` 表示来源描述的世界状况，`belief` 表示人物当时已知或相信，`post_hoc` 标记事后回顾，`unknown` 表示视角未明。颜色和卡片位置均不能把事后结果变成人物当时已知的信息。

每页同一 Context 只放一张卡，保留它在本页承担的全部角色。同一基准条件或约束适用于多项行动时，共用一条带谓词的主线，再分支到各行动。若某 Action 自身也记录完全相同的用途、角色、交互和限定，显示线可以共用，详情保留 Phase 与 Action 两处记录。资格、角色不同或引用带有争议时可分别查阅。跨页复用同一 Context 时，各页仅展示本页适用关系。[基准、差量与例外](../person-event-builder/2-graph-contract.md)

适用范围逐条按 `context_ref_id` 核对。排除或适用性未决的引用跳过该行动的分支，另一条有效引用仍可连到该行动。背景的日期未定可与明确的适用范围并存。没有有效继承者时，基准保留在 Phase 层。纯阶段级用途即使只含一项行动，也保留原来的端点。

没有显式引用的背景，可依自身日期或与 Phase 共用的原文片段放在最能定位的页面供查阅。无法唯一定位时留在 `Event background`。这种排版匹配只改变查阅入口。同一实体碰巧与该背景同页，也不会生成参与或因果关系。

## 2.3 Context 与主体的端点

| 记录 | 实际端点和显示 |
| --- | --- |
| `condition` | Context → Action。说明使行动可行或可理解的条件，通常画在行动上方。 |
| `trigger` | Context → 记录的 Action 或 Phase。只记录整个阶段的触发时，箭头止于 Phase。 |
| `constraint` | Context → Action。说明哪些选项受到限制或被排除。与 `condition` 一样，继承线标签附 `Phase-wide`，详情指向原 Phase 引用。 |
| `result` | Action 或 Phase → 结果 Context。端点取自实际记录结果的层级。结果在另一处又作为条件时，应另有相应关联。 |
| `participation` | 已记录的参与实体 → Action，保留角色。Phase 级参与指向共享区内的 Phase 卡。详情保留关联的背景描述、限定与引文。 |
| `knowledge-source` | 信息 Context → 记录的获知者。该背景引用于哪一个 Phase 或 Action，另由适用范围说明。 |
| Action 的 `actor / object` | 执行者实体 → Action，Action → 对象实体。二者来自 Action 自身字段。参与、被提及或是某组织负责人，都不足以自动补成 `actor`。 |
| `about` 及代表身份 | `Context.entity_refs` 可产生 Context → 实体的提及线。`actor.on_behalf_of` 在主体详情列为 `Represented party`，可与执行者的身份、职务分别追溯。 |

参与者节点用圆形。焦点人物与其他人物或组织使用记录的身份。Context 的 `Recorded uses` 逐条列出原图中的用途。即使同一机构既任顾问又任资助方，也保留两个角色、限定及各自支持的位置。缺少收信人或参与方时，详情保留 `Recipient not recorded` 或 `Participant not recorded`，不猜箭头端点。

共享 Context 可列出 `Entities mentioned`。平时其提及线收起，聚焦对应实体才显示。选中共享卡时，只有仍继承至少一条有效基准引用的 Action 获得范围高亮。若所有相关引用均有效排除，则列为 `Excluded`。若没有可确认继承的引用且仍有未决例外，则列为 `Scope unresolved`。点击 Action 可回查相应例外。只对几个行动适用的背景，由这些行动分别显式引用同一 Context，无需扩展成 Phase 基准。

同一 Phase 先排 Action，再放 Context。单个行动有专属条件或触发时，背景放在行动组上缘、靠近该行动所在列。结果放在下缘。同列有多个行动需要上下比较时，它们之间保留给行动和时间标记。多个行动复用同一背景时，卡片靠近相应用途的列，所有显式引用各按原谓词回连。Phase 基准沿用上面的继承规则。

有一种可以利用横向空位的情况。图中同时记录了“前项 → 背景（result）”和“背景 → 后项（condition）”，另有独立的时间或先后依据使两项行动在同一行有序。若两卡之间已有一列空位，且放卡不会占用任何行动在该行的时间跨度或拆开上下比较的行动，背景可以放在那里。其余情况放到组外靠近条件所对应的行动。两条原有连线始终保留。背景从不新增时间列、行动步骤或先后关系。
