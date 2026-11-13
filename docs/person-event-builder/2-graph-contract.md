# 2 · 人物 Event 图数据协议

导航：[总览](0-overview.md) · [公共值与事实协议](1-input-and-facts.md) · [检查与输出](5-validation-and-output.md)

本章定义目标 `epg.json`。字段实现 [设计规范 S1–S12](../person-event-structures/7-specification.md) 的含义；Time、Source、Evidence、Support、Gap、Conflict 与 ObjectRef 均引用第 1 章，不另定义第二套。

## 2.1 根对象与引用方式

根对象包含下表全部字段。集合存为数组，内部以稳定 ID 引用；不在多个层级复制完整动作和关系。

| 字段 | 类型 | 约定 |
| --- | --- | --- |
| `schema_version` | string | `person-event-1.0`，程序管理的协议标识 |
| `person` | object | 本次焦点人物身份与本图 Event 索引 |
| `storyline` | object | 上层目录分组信息 |
| `event` | object | 唯一目标事项、范围与完整摘要 |
| `entities` | Entity[] | 被实际引用的人物/组织等身份 |
| `stages / phases` | Stage[] / Phase[] | 局面阶段与行为阶段 |
| `actions / relations` | Action[] / Relation[] | Event 动作图的节点与边 |
| `contexts` | Context[] | Phase 基准和 Action 差量共同引用的上下文 |
| `sources / evidence` | Source[] / Evidence[] | 支撑描述的来源与原文引证 |

`schema_version` 是读写兼容标识，不是人物研究计划中的人工版本号。身份与目录层的定义如下：

| 对象 | 必填字段 | 约定 |
| --- | --- | --- |
| Person | `person_id, name, aliases, event_ids` | 本图只含当前 `event_id`；不暗示这是人物全部事件 |
| Storyline | `storyline_id, person_id, name` | 从已确认目录继承，不生成新的分组 |
| Event | `event_id, person_id, storyline_id, name, scope, time, summary, support` | `scope` 原样继承；摘要可脱离其他 Event 阅读，不能只有标题 |
| Entity | `entity_id, name, type, aliases` | `type` 为 `person / organization / other`；焦点人物实体 ID 与 `person_id` 相同 |

上述名称和 ID 为非空字符串，别名和索引为字符串数组。Event 的 `time` 是 Time，`support` 是 Support[]。可选 `gaps / conflicts` 用于时间、范围内覆盖和具体描述的不确定性；实体存在身份歧义时使用相同记录。目录 ID 的继承不要求模型再找一份证明“该 ID 存在”的来源。

Entity 是身份目录，不承担他人的独立行为，也不把“监管者/对手方”等特定动作中的角色设为实体永久属性。Event 摘要可通过 `premise_refs` 引用已形成的动作、阶段和上下文，依据链必须最终回到证据或明确缺口。

## 2.2 Stage 与 Phase

| 对象 | 必填字段 | 可选字段 |
| --- | --- | --- |
| Stage | `stage_id, event_id, name, description, time, boundary_reason, support` | `gaps, conflicts` |
| Phase | `phase_id, stage_id, name, description, time, boundary_reason, support, baseline_context_refs` | `gaps, conflicts` |

ID 和文字字段为字符串，`time` 为 Time，`support` 为 Support[]。`baseline_context_refs` 使用 2.4 的 ContextRef[]。

- 完整 Event 至少有一个 Stage，每个 Stage 至少有一个 Phase；不能以空集合宣称层级已完成。
- Stage 的 `description` 描述相对稳定的局面，`boundary_reason` 说明起点和终点的局面依据；Phase 分别描述行为模式及其起止边界。终点未知时记 Gap；范围截止不能冒充事项已经结束。
- 切分优先判断局面变化：Stage 起点自然也是其第一个 Phase 的起点。同一变化同时改变局面和做法时按 Stage 处理；只有 Stage 内再次发生行为模式变化才新增 Phase 边界，不重复切分。联合组织不改变这一语义优先级。
- 边界可来自来源明确表述，也可由有据的组织判断形成；后者使用 `I` 并引用前提，不能要求来源必须使用“Stage/Phase”字样。
- 第一阶段可以始于资料可确认的初始局面，不制造一个未观察到的前序阶段。只有一 Stage、一 Phase 也可以；单动作或空动作 Phase 必须说明原因。若两级边界始终相同且没有独立语义，应归并冗余切分或解释保留理由，不省略协议要求的层级。
- 同级 Stage、同一 Stage 内 Phase 按有据的时间先后排列。未知顺序明确标为未验证，数组位置不构成时间证据。不将日期、材料批次、来源发布日期直接当成边界。
- 相关端点均已知时，同级 Stage、同一 Stage 内 Phase 不重叠，Stage 包含于 Event、Phase 包含于 Stage；任一端点未知时不作区间推导，允许有说明的覆盖缺口。
- 子成员由 `Phase.stage_id` 和 `Action.phase_id` 派生，不再维护容易失配的 `Stage.phase_ids` 或 `Phase.action_ids`。

## 2.3 Action

| 字段 | 类型 | 约定 |
| --- | --- | --- |
| `action_id` | string | 稳定行为 ID |
| `name / description` | string | 简短名称及可区分的行为描述 |
| `actor` | object | `entity_id`、`capacity`，以及可选的 `role`、`on_behalf_of` |
| `time` | Time | 发生窗口或持续区间；允许未知 |
| `phase_id` | string | 完整图中的唯一 Phase；未完成检查点可为 null |
| `support` | Support[] | 主体、时间、行为及必要归属判断的依据 |
| `action_type` | string，可选 | 粗分类，不用封闭分类表限制所有事件 |
| `object` | object，条件必填 | `description` 与 `entity_refs`；对象已知时填写，非实体对象的 `entity_refs` 可为空 |
| `delta_context_refs` | ContextRef[]，可选 | 相对所属 Phase 基准的特有上下文 |
| `gaps / conflicts` | Gap[] / Conflict[]，可选 | 具体未知和来源分歧 |

`actor.capacity` 为 `personal / official / delegated / unknown`。`entity_id` 是实际执行者；`role` 为职务/身份说明，`on_behalf_of` 引用其代表的实体。已知职务或代表关系必须保留；相关身份未知时标 Gap，不编造身份。代理行为必须有可追溯到焦点人物的授权或行为归属依据；无法确定归属时留在事实检查点待定，不能仅凭公司行为生成焦点人物 Action。

已知行为对象填入 `object`，已知相关人物通过 Entity 与参与上下文保留其本次角色；不能因字段可省略而在组装时丢弃。对象未知时省略 `object` 并说明 Gap；不为补齐字段创建虚构实体。

他人的独立动作若影响焦点人物，进入相关 Context，而不是为满足关系连通而塞进 `actions` 或实体名单。只有有据归属于焦点人物本人、职务或代理执行的行为进入动作集合。

每个完整 Action 唯一属于一个 Phase。真实持续行为跨 Phase 时，按有据边界拆成各 Phase 内的行为记录，并保留拆分对应和续接关系。若只是粗时间窗口跨界而无法确定真实归属，不擅自拆成多次行为；保留待定记录，输出为部分完成。

目标、动机、资源、约束与结果进入 Context，由 Action 引用。不能把纯心理推断写成实际动作，或在 Action 与 Context 中各维护一份不一致的状态。

## 2.4 Context 与上下文引用

Context 保存可复用的上下文内容；ContextRef 保存该内容怎样作用于某个 Phase/Action。证明某项条件存在，不等于证明它触发了某个动作，两处依据应分别表达。

| Context 字段 | 类型 | 约定 |
| --- | --- | --- |
| `context_id` | string | 稳定 ID |
| `category` | enum | `environment / relations / person_state` |
| `description` | string | 必要的环境、相关他人/组织或主体状态 |
| `entity_refs` | string[] | 引用 Entity，允许为空 |
| `time` | Time | 内容发生或适用的时间 |
| `perspective` | enum | `world / belief / post_hoc / unknown` |
| `support` | Support[] | 内容、时间、认知归属等的依据 |
| `gaps / conflicts` | Gap[] / Conflict[]，可选 | 未知与分歧 |

`world` 表达对世界状况的描述，不能自动推定人物知道；`belief` 表达人物当时已知或相信的信息；`post_hoc` 是对该动作而言事后才出现的信息；无法判断时使用 `unknown` 并说明缺口。这些标签不等于已验证的真实性等级。同一内容的世界状况与人物知情陈述需要区分，不能改一个标签抹掉差别。

| ContextRef 字段 | 类型 | 约定 |
| --- | --- | --- |
| `context_id` | string | 引用 Context |
| `relation_type` | enum | `participation / condition / trigger / constraint / result / knowledge-source` |
| `support` | Support[] | 本次关联的依据；与 Context 内容的支持分开 |
| `entity_id / role` | string，条件必填 | participation 指明参与实体及角色；knowledge-source 必须指明知情实体；确实未知的参与实体/角色可省略但须有对应 Gap |
| `interaction_type` | string，可选 | 如 `communicates_with / transacts_with / delegates_to`，细化参与关系 |
| `qualification` | string，可选 | 相对基准的适用限制、补充或变化说明 |
| `gaps / conflicts` | Gap[] / Conflict[]，可选 | 关联层面的未知与分歧 |

六种语义与方向遵循 [上下文设计](../person-event-structures/3-context-model.md)：参与、条件、触发、约束作用于行为，结果由行为指向状态；知识来源是信息指向人物，附在 Phase/Action 上仅表示本次适用范围。它不是 Action → Action 边。人物/组织在其他关联中有明确角色时同样保留；环境条件等不涉及参与人的关联不强制填写实体或角色。

`C(a) = C(phase(a)) ⊕ ΔC(a)` 由以下规则读取，不另存完整上下文副本：

1. 先检查基准条目在该动作时间和范围内是否适用；未知不当作已经成立。
2. 只有关联含义完全相同才合并支持记录：比较 `context_id / relation_type / entity_id / role / interaction_type / qualification` 及适用范围。不同参与者、角色、交互方式或适用限制分别保留；未知不视为通配符，无法确认等价时不合并。不能仅按 Context ID 和关联类型去重。
3. 差量可以用 `qualification` 限定基准适用范围；变更后的内容另有 Context 和依据，不覆盖原事实。
4. 无法协调的差异保留为 Conflict；不采用“后写覆盖前写”。
5. 结果不自动倒写成先前动作的条件；条件、触发和知识来源需要当时可知的依据，不能用事后信息代替。

Phase 应有最小必要的环境、关系/他人和主体状态基准；缺失的类别说明 Gap，不为填齐三类而编造内容。目标是解释行为，不建立世界状态推演引擎。

## 2.5 Action 之间的 Relation

| 字段 | 类型 | 约定 |
| --- | --- | --- |
| `relation_id` | string | 稳定关系 ID |
| `from_action_id / to_action_id` | string | 同一 Event 中两个不同 Action |
| `type` | enum | 下表所列动作间关系 |
| `basis` | enum | `observed / asserted / inferred / derived` |
| `support` | Support[] | 端点、类型、方向及推导依据 |
| `description` | string，可选 | 必要的关系说明 |
| `gaps / conflicts` | Gap[] / Conflict[]，可选 | 关系层面的未知与分歧 |

| 类型 | `from → to` 的含义 |
| --- | --- |
| `precedes` | from 先于 to；只有这一类型参与时间偏序 |
| `overlaps` | 两个行为确实有时间重叠；对称 |
| `order_unknown` | 这对行为的先后尚不明确；对称，不参与时间偏序 |
| `responds_to` | from 回应 to |
| `enables / triggers / prevents` | from 使能、触发或阻止 to |
| `continues / resumes` | from 延续或恢复 to |
| `interrupted_by` | from 被 to 打断 |
| `joint_action` | 两个已有动作共同构成行为；对称 |

沟通、交易和委托若指向人物/组织，通过参与上下文表达，不能把实体 ID 填入动作端点。对称边可以按稳定 ID 顺序仅存一次，但语义仍为对称。

`basis` 表达关系的获得方式：记录直接呈现、来源明确断言、分析推断、由已知时间区间确定推导。`derived` 限于有明确区间规则的时间关系；不能由日期或其他程序规则自动推出回应、触发等语义关系。推导 `precedes` 要求双方起止端点均已知、无未决时间冲突，且 `from.time.end <= to.time.start`。推导 `overlaps` 还要求确为持续区间，发生窗口相交不够。`derived` 与 `Support.mode` 不同，以 `I` 支持记录列出有据的时间前提和规则。回应等语义关系可为来源陈述，或带证据与理由的明确推断；来源说“导致”不等于已证明真实因果。

原始关系主张与可用于排序的关系视图须分开：

1. 原始主张保留在 `relations`，连同各自来源与支持。相反方向、时间矛盾或先后环在 `event.conflicts` 中记录；`related_refs` 必须列明全部涉事关系，必要时包括动作时间字段。对象自身的字段分歧仍可留在自身 `conflicts`。不删除原始证据来消除冲突。
2. 先后候选集 `P` 仅包含 `precedes` 且 `basis` 为 `observed / asserted / derived` 的有效关系。`inferred` 的先后猜测可显式保留，但不提升为确定顺序。
3. `P_consistent` 排除所有涉及未决时间/顺序冲突的边及依赖冲突时间前提的推导边；环上的边全部保留为冲突主张并从此视图排除，不任意挑选一条删掉。排除和理由必须可回查。`P_consistent` 必须无环；它是派生视图，不另存一套事实图。
4. 时间先后 `≺` 是 `P_consistent` 的传递闭包。`A1 ≺ A2`、`A2 ≺ A3` 已支持 `A1 ≺ A3`，无需另存直接边。仍有冲突时只称该视图为局部/暂定顺序，不声称整个 Event 的先后已确定。

同一对动作可以有多种关系。`A1 precedes A2` 与 `A2 responds_to A1` 可形成合法语义环；原始时间主张也可能因证据冲突成环，无环要求针对的是 `P_consistent`，不是整个原始图。

不为每一对未连接动作补 `order_unknown`。没有直接边不等于顺序未知，应先检查可用先后路径；两向都无路径时才在当前顺序视图中不可比，也不能因此断言并发。重点但未定的顺序可记录关系或 Gap；若 `order_unknown` 与已有确定先后路径并存，需要说明冲突或更新该记录，不能同时把两者当作当前结论。

## 2.6 图的派生与完整性

```text
A(p) = 通过 phase_id 归属于 p 的动作
R(p) = 两端都在 A(p) 的关系
G(p) = (A(p), R(p))

G(s) = 各 Phase 图的并集 + 同 Stage 内跨 Phase 关系
G(e) = 各 Stage 图的并集 + 跨 Stage 关系
```

这些图是同一组动作与关系的视图，不再存独立的事实副本。动作集合允许分支和不连通；不得为绘图连通性或美观补出关系。

完整草稿要求至少一个 Stage、每个 Stage 至少一个 Phase，层级和引用有效、所有保留动作唯一归属，且描述有支持或显式缺口。层级及归属不能含未处理的确定时间矛盾；来源关系的时间冲突可以显式保留并从可用顺序视图排除，不冒充确定顺序。部分结果可以保存相同根结构及未完成内容，但不能声明满足完整图协议；未归属事实和遗漏的步骤须在检查点与检查结果中可见。未知、缺口和冲突不因标记“completed”而消失，完成条件详见 [第 5 章](5-validation-and-output.md)。
