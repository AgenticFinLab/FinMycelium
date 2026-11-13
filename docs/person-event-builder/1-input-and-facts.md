# 1 · 任务输入与统一事实记录

导航：[总览](0-overview.md) · [图协议](2-graph-contract.md) · [构建流程](3-construction-flow.md)

## 1.1 保留的输入入口

任务正文沿用 `user_query + samples`，不要求公共搜索生成图对象。身份和范围放在 `user_query.extras.person_event`，来源映射放在 `user_query.extras.source_registry`。运行配置、输出目录和账本不混入研究要求。

| 路径 | 类型 | 约定 |
| --- | --- | --- |
| `user_query.query_text` | string | 用户原始研究要求及必要任务说明；不替代结构化范围 |
| `user_query.key_words` | string[] | 任务关键词，可为空 |
| `user_query.extras.person_event` | object | 下表定义的已确认任务 |
| `user_query.extras.source_registry` | object | 以 `raw_data_id` 为键的来源记录 |
| `samples` | object[] | 本次实际交接的非空正文片段列表 |

`person_event`：

| 字段 | 类型 | 约定 |
| --- | --- | --- |
| `person_id / person_name` | string | 已确认人物 ID 与名称 |
| `storyline_id / storyline_name` | string | 已确认目录分组 |
| `event_id / event_name` | string | 唯一目标 Event |
| `scope` | object | `period / include / exclude` 三个字符串；`include` 非空 |
| `aliases` | string[] | 人物别名，缺省为空 |

身份字段均必填且非空。`scope.period` 可以是文字时期，不为方便绘图而补造日期。事件发生范围与资料发表范围不同；后来的回顾资料可用于证明范围内行为。模型不能因发现另一事件而替换这些值。研究计划用来说明研究边界，不作为证明世界事实的原始证据。

每个 sample 必须包含唯一非空的 `sample_id`、非空 `raw_data_id` 和非空 `content`。已有 `category / knowledge_field / tag / method` 等可选字段按原入口传递；来源元数据进入 registry，不随意扩展严格的 sample 类型。适配器应保留已有的其他 `extras`，仅明确补充本任务所需字段。

结构设计中的一个“样本”是一个人物 × Event；此处代码字段 `samples` 指交接的文本片段，两者不是同一层级。

## 1.2 冻结与来源对应

冻结后保存确切输入、输入哈希、来源清单和交接映射。工作台另记 `search_task_id`、交接 revision、材料选择记录、来源版本、完整材料位置及解析内容哈希。CLI 可使用本地资料与同等溯源记录，不强制依赖搜索任务数据库。

```text
source_registry[raw_data_id]
  → 一个来源及其冻结版本
  → 一个或多个 samples
  → Evidence(sample_id, quote, offsets)
  → 对象字段的 support
```

最终图的 `source_id` 对应输入的 `raw_data_id`；`sample_id` 不能代替来源身份。同一来源的不同片段可以共同支持一个动作。版本与片段到原文件的映射保存在运行溯源中，不能把修改后的正文当成原 sample 继续使用。

来源注册表的 `source_url` 映射为输出 Source 的 `url`。已有 `document_id` 可保留为溯源信息；`published_at`、`retrieved_at` 和标题缺失时保留空值，不通过推测填充。URL 与本地来源说明至少有一项可用。输入适配器从同一冻结来源版本保留已知的 `origin / source_type / content_status` 等元数据；有记录的字段不能在交接时丢弃，也不能用当前网页状态替代冻结版本。合并 `extras` 时保留其他键，本任务身份与来源映射发生冲突须先校验，不能静默覆盖。

## 1.3 公共值与 ID

下文的 JSON 均使用 UTF-8。允许为空的列表没有条目时保存 `[]`；明确允许未知的标量使用 `null`，并按需要记录缺口；可选字段省略。ID、必填名称、枚举和完整图的最低成员数量仍须满足各表的约束，不能用 `null` 或 `[]` 绕过。不用空字符串伪装已知值，也不将 `null`、字段缺失和空列表混为一谈。叙述性输出使用英文，名称、原文引文、URL 和 ID 保留原样。

目录中的三个 ID 原样继承。动作、证据、阶段等内部 ID 由程序分配；模型可以返回批次内临时引用，由程序集中映射。ID 在同一 run 的重试和恢复中稳定，不因排序而重编号。拆分、合并保留旧新 ID 对应；新 run 的同名内部 ID 不自动表示相同事实。

跨对象的依据引用统一为：

| `ObjectRef` 字段 | 类型 | 约定 |
| --- | --- | --- |
| `collection` | string | `person / storyline / event / entities / stages / phases / actions / relations / contexts` 之一 |
| `object_id` | string | 对应对象的稳定 ID |
| `field` | string | 对象内 JSON Pointer；空串表示整个对象 |

依据引用不得以数组序号代替对象 ID。嵌套字段路径可以使用 JSON Pointer，但对象重排或局部字段修正后必须重新校验。步骤的 `pending / lineage` 和处理操作也使用 ObjectRef，此时 `collection` 还允许 `relation_candidates`，引用可在对应步骤快照中定位；这不允许最终图把候选或已被替代的旧对象当作有效 `premise_refs`。

## 1.4 时间 `Time`

| 字段 | 类型 | 约定 |
| --- | --- | --- |
| `text` | string \| null | 原始时间表述；推导出的组织范围由 support 说明推导依据 |
| `kind` | enum | `occurrence_window / duration / unknown`：发生窗口、持续区间、无法确定语义 |
| `start / end` | date string \| null | ISO 日期；已知范围统一为半开区间 `[start, end)` |
| `start_precision / end_precision` | enum | `year / month / day / unknown`，分别记录端点依据的精度 |

“2020 年 3 月发生”表示 `[2020-03-01, 2020-04-01)` 的发生窗口，两端精度均为 `month`；不表示动作持续整月。来源只给出年、月或未知时，不将标准化后的日期伪称为日精度。已知持续到某日且包含该日，程序将排他终点设为下一日，并保留原表述。

两个不确定发生窗口相交，不能据此生成 `overlaps`。区间包含或先后推导只对相关区间的起止端点均已知时进行；任一区间含未知端点，均标为未验证，不利用另一个已知端点作区间推导，只保留有据的来源关系并标明时间不确定性。未决时间冲突也不能作为确定推导的前提。Stage/Phase 的时间来自边界依据；任务 `scope.period` 仅用于范围约束，不能自动成为阶段事实。文档发表、抓取时间分别保留在 Source 中，不填入 Action 的发生时间。

## 1.5 来源与原文引证

Source：

| 字段 | 类型 | 约定 |
| --- | --- | --- |
| `source_id` | string | 与输入 `raw_data_id` 相同 |
| `title` | string \| null | 原标题 |
| `url` | string \| null | 可回访地址 |
| `origin` | string \| null | 本地或其他来源说明；与 `url` 至少一个非空 |
| `published_at / retrieved_at` | string \| null | 已知日期或带时区时间；缺失不补造 |
| `source_type / content_status` | string，可选 | 资料类别及全文/部分/仅标题或摘要/受阻等获取情况；已知必须传递，未知可省略且按未知解释 |

`content_status` 说明来源获取情况，不说明 Builder 已读全文。`provenance` 按来源保留交接的 sample、选择区间及原文映射；步骤记录再标明这些 sample 中实际处理与未处理的区间。获取全文、交接部分正文、处理全部已交接正文可以同时成立。缺少原文映射时不能声称读完原文；来源详情和运行汇总应分别展示获取、交接和处理范围，见 [检查与输出](5-validation-and-output.md)。

Evidence：

| 字段 | 类型 | 约定 |
| --- | --- | --- |
| `evidence_id` | string | 稳定引证 ID |
| `sample_id / source_id` | string | 片段与来源引用，`source_id` 由映射确定 |
| `quote` | string | 原文；不能放翻译、摘要或模型改写 |
| `start / end` | integer \| null | 相对冻结 `sample.content` 的起止字符偏移，左闭右开 |
| `location_status` | enum | `matched / ambiguous / unmatched` |
| `sample_sha256` | string | 程序计算的确切片段 UTF-8 字节 SHA256 |
| `locator` | object，可选 | 实际获得的页码、章节、段落、原文位置；未知项省略 |

偏移按 Unicode 码点计数，不按 UTF-8 字节或浏览器 UTF-16 下标计数。只有 `matched` 使用非空偏移，且必须满足 `content[start:end] == quote`；其余状态的偏移为空。原文出现多次时，程序结合上下文定位，不能任取第一处。模型提出的引文和位置必须经程序核对。

这里的偏移锚定的是**实际交接片段**。若片段由筛选后的多段正文组装，原网页/PDF 的位置还要沿材料选择映射回查；不得把片段偏移标为网页偏移或页码。一段 Evidence 可被多个对象复用，完整原文留在运行资产中，不复制到每个对象。

## 1.6 支持、缺口与冲突

各语义对象使用 `support` 列表说明哪些字段被什么依据支持，不要求每个标量再包一层 Claim 对象。

| `Support` 字段 | 类型 | 约定 |
| --- | --- | --- |
| `target` | string | 本对象中的 JSON Pointer；空串可指整段描述，不能掩盖关键字段缺证 |
| `mode` | enum | `O / A / I` |
| `evidence_ids` | string[] | 对应 Evidence；可供多个字段复用 |
| `premise_refs` | ObjectRef[]，可选 | 推断所用的已有对象/字段，不得自我支持或形成循环论证 |
| `reason` | string，可选 | 推断规则、理由或必要限定；`I` 必填 |

- `O`：命题描述记录内容，例如“公告写道 X”。
- `A`：命题是来源对世界事实的断言，例如“该交易完成”。
- `I`：分析推断，需要可追溯的证据或前提和理由。

`O/A` 需要可定位来源和引文；引文未定位时保留候选记录并报告问题，不将其算作已具备有效支持。`O/A` 按命题区分，同一命题不能同时使用二者；混合描述应拆开。模式不是来源信誉或置信度等级。`derived` 只用于关系的 `basis`，不加入 `mode`；由时间区间确定推导的关系以 `I` 记录前提与规则，不能因来源未直接说出关系就写成无支持。

对象整体、描述、时间、主体、边界和关系端点可以分别有支持。关键字段不能仅凭同对象另一字段的引用宣称有据。程序可检查引用和定位，是否真正支持命题仍需语义审核。

| 公共记录 | 字段 | 约定 |
| --- | --- | --- |
| `Gap` | `target: string, reason: string` | 指出需要说明的未知或缺证；无有效支持时使用，不伪造占位动作 |
| `Conflict` | `target: string, alternatives: object[], reason: string`；可选 `related_refs: ObjectRef[]` | 每个 alternative 保存 `value`、`support`，必要时 `gaps`；跨对象冲突用 `related_refs` 列明涉及的对象/字段，保留相互冲突的具体说法 |

单个事实字段有未解决冲突时，主字段保留未知或明确的保守表述，不能静默选择一方。来源关系主张可以各自保留完整端点、方向与依据，并通过 Conflict 标明分歧；保存主张不等于将其纳入已确定的关系视图，时间关系规则见 [2.5](2-graph-contract.md#25-action-之间的-relation)。无检索结果不等于否定事实。允许 `support: []` 并记录对应 Gap；允许基于记录表达不确定候选，但不能凭空新增行为填满图。

## 1.7 统一事实检查点

事实记录使用与最终图相同的公共时间、证据、支持和 ID 规则，避免各阶段互相转换成新的叙述摘要。

| 字段 | 内容 |
| --- | --- |
| `schema_version` | `person-event-facts-1.0`，由程序管理 |
| `person / storyline / event` | 固定身份和范围；事实阶段可暂缺最终摘要 |
| `entities` | 统一人物/组织等实体 |
| `actions` | 候选及归并后的动作；`phase_id` 在组织完成前允许为空 |
| `contexts` | 与本 Event 有关的环境、他人行为和主体状态 |
| `relation_candidates` | `candidate_id`、已知动作引用、候选类型/来源表述及 support；尚未确认的端点允许为空并附原因 |
| `sources / evidence` | 实际使用的来源和引文 |
| `pending` | 待解决项目：`refs: ObjectRef[]`、`reason: string`、`evidence_ids: string[]`；尚无可引用对象时 refs 可为空，说明涉及的材料或候选 |
| `lineage` | 程序记录的对象变更：`operation`、`input_refs / output_refs: ObjectRef[]`、`reason`、`step_id`；保留拆分、合并及转为 Context 的旧新对应 |

关系候选的字段为 `candidate_id, from_action_id, to_action_id, type, description, support`，可附 `gaps / conflicts`。未知端点或类型使用 null 并说明 Gap；已知类型沿用图协议的关系类型。description 保留来源关系线索，不因端点尚未确定而丢弃。候选经端点、类型和依据确认后才形成带 `basis` 的正式 Relation。

每个抽取批次先保存结果，再进入统一检查点；批次覆盖哪些 sample 和正文区间由执行记录保存。精确重复、实体身份、相同行为判断分开处理。不同时间的重复行为不能仅因文本相似而合并。事实被移出范围、并入其他记录或仍待判定，均要有去向，不能在后续摘要中消失。

处理操作及部分采用规则见 [3.9](3-construction-flow.md#39-四类结果的最小返回协议)。操作输入、旧对象及未采用结果保留在步骤记录中；lineage 说明对应关系，不证明拆分后的每个对象都继承原对象全部支持。引用重定向必须能确定对应，不能确定的进入 pending。

检查点不是最终图：它允许未归属动作与未定关系；完整图的归属、端点和层级必须满足 [图协议](2-graph-contract.md)。事实提取完成也不代表这些内容已通过审核。
