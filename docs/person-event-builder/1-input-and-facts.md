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

启用[证据缺口补搜](3-construction-flow.md)后，新增原文以新 sample 追加。原有 sample、顺序和来源版本保留，运行同时记录原输入和生效输入的哈希。最终图、引文定位与检查都使用同一份生效输入。仅重读原文时沿用原输入哈希。

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
| `intraday` | string，可选，仅 Action | 有据的单日发生窗口可记录 `morning / noon / afternoon / evening` 或当地 24 小时制 `HH:MM[:SS]`。两端精度为 `day`，原措辞保存在 `text` |
| `utc_offset` | string，可选，仅 Action | 日内时间采用的有据偏移量，例如 `-04:00` 或 `Z`。未标时区的时刻只在来源能够确定的同一当地时间框架中比较 |
| `anchor_source_id` | string，可选，仅 Action | 当原刊作者用“今天、昨日、昨晚”等描述单日行动，并采用原刊日期推算时，记录对应的冻结 Source |

“2020 年 3 月发生”表示 `[2020-03-01, 2020-04-01)` 的发生窗口，两端精度均为 `month`；不表示动作持续整月。来源只给出年、月或未知时，不将标准化后的日期伪称为日精度。已知持续到某日且包含该日，程序将排他终点设为下一日，并保留原表述。

若记录为 `duration`，用 `/time` 或 `/time/kind` 的字段支持说明行动在区间内持续；一条覆盖整段时间的已有支持即可。仅支持起止日期的引文仍支持这两个边界。归并保留有据的时间类型，改判类型时沿用已有的有据修正机制。[视觉上的发生窗口与持续区间](../person-event-visualization/1-action-layout.md)

两个不确定发生窗口相交，不能据此生成 `overlaps`。区间包含或先后推导只对相关区间的起止端点均已知时进行；任一区间含未知端点，均标为未验证，不利用另一个已知端点作区间推导，只保留有据的来源关系并标明时间不确定性。未决时间冲突也不能作为确定推导的前提。Stage/Phase 的时间来自边界依据；任务 `scope.period` 仅用于范围约束，不能自动成为阶段事实。文档发表、抓取时间分别保留在 Source 中，不填入 Action 的发生时间。

### 自然时间与历法规范化

提取、归并、组织和关系职责共用以下时间规则，分别遵守各自原有写入范围。自然语言时间可以依据来源上下文和可靠适用的日历规则规范化；计算出的公历边界不必逐字出现在原文中。这不授权根据外部常识补造人物行为，也不新增搜索、计算工具或模型调用步骤。

先明确来源使用的历法、纪年、年份/事件锚点及必要的地区约定，再转成公历范围。不能仅凭来源语言认定历法，也不能用固定年份差或固定天数差替代历史历法规则；转换可能跨公历月或年。季节、节日、季度、财年、旬和相对日期只是常见形式，不是封闭类型表。无法可靠确定的部分保留原文与 Gap，能独立确定的粗范围或单侧界限仍保留。

| 表达及前提 | 当前 Time 表达 | 精度与限制 |
| --- | --- | --- |
| 2022 年第三季度，已确认自然季度 | `[2022-07-01, 2022-10-01)` | 端点精度 `month`；发生窗口，不指定某次行为发生于季度末 |
| 2024 年 2 月下旬，已确认公历语境 | `[2024-02-21, 2024-03-01)` | 端点按旬规则可定位到日，但行为仍在多日窗口内；保留“下旬” |
| 已确认公历约定的 2022 年圣诞节当天 | `[2022-12-25, 2022-12-26)` | `day`；不能将整个假期同样压成当天 |
| 财年第三季度，财年起点未确定 | 保留原表达与缺口；仅保存可独立确认的公历范围 | 不套用自然季度，也不默认财年编号等于同名公历年 |
| 季节、旧历或其他纪年，约定未确定 | 保留可确认的范围或单侧界限，其余 `null` | 不用当前运行日期或研究范围替代缺失锚点 |

中文旬按上旬 1—10 日、中旬 11—20 日、下旬 21 日至月末处理，并应用实际月长和闰年；自然日、工作日与交易日分别判断。持续到某日且包含该日时，将其下一日作为排他终点。日内时段、时钟和时区原话保留在 `text` 和 Evidence。时段按来源精度取值；“当日下午”保留为 `afternoon`，不能换算为某个整点。跨午夜或当地时间无法确定时，可保留较宽的日期范围或相对先后并说明缺口。

`start_precision/end_precision` 描述端点依据；行为的发生粒度由原表述和整个窗口共同表达。年/月规范化仍保留年/月精度；旬的边界可定位到日，不代表行为精确发生在其中某一天。不得取中点、窗口首日或末日作为无依据的实际发生日。可靠历法转换也不自动降低一个已明确“当天”的日期精度。

非原文字面日期的转换、相对时间解析和边界推断，用所属对象的 `support.mode=I` 指向 `/time` 或具体端点，列出证据/前提，并在 `reason` 说明锚点、历法或规则及剩余不确定性。原时间措辞保留在 `Time.text`，原始引文仍是 Evidence；不新增 `time_window`、`approximate` 或 `Time.basis`。推断标记说明取得方式，不等于低可信度，也不能代替依据。转换规则未核实就不得声称使用了外部核验或计算工具。

原刊作者说“昨天下午”时，两端的 `I` 支持要能回到该来源包含相对措辞的正文。程序以冻结的 `Source.published_at` 所表示的民用日期核算日期偏移。若只有更新或抓取日期、原刊当地日期不清，保留原话与可确认的范围。报道转引更早的访谈时，应采用有据的访谈日期并引用相关原文。单凭外层报道发布日期不能确定被访者说“昨天”指哪一天。归并时已支持的日内信息和锚点随行动保留，有依据的更正按已有协议处理。

抽取到一项时间不完整的行动时，继续检查原文能支持的时段、单侧界限或相邻行动。归并同一行动的多个说法时，用相容的依据收紧范围，保留分歧、原话和推断理由。只有相对先后时，关系职责核对两个行动及其方向，包括跨 Phase 的锚点。行动自身的日期可以继续为空。Phase 归属、行动的行列及卡片坐标均不作为时间前提。

这些约定遵循 [层级时间规则](../person-event-structures/1-hierarchy.md#17-时间与包含关系)、[S6/S7/S9](../person-event-structures/7-specification.md) 和 [形式模型的区间及支持规则](../person-event-structures/8-formal-model.md)：保留半开区间与来源粒度，区分发生窗口和真实持续；未知端点仍不参与确定性区间推导。时间规范化不自动生成 Stage/Phase 边界、动作归属或因果关系。程序核对日期、引用、区间及推断支持协议，历法是否适用和推断内容是否成立仍需语义审核。

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

Evidence 的引文取自来源正文。Search 在交接正文前附的 URL、标题、发布日期、获取时间，以及标记段落省略或截取位置的文字，都属于交接说明。来源在正文中写出的日期仍可按原文引用。

若报道正文的“今年”指向该报道的发表年份，Evidence 保留含“今年”的原句。在所支持字段的 `I` 类 `reason` 中记录 `source_id`、冻结的 `published_at` 和年份的推导依据。转述早期访谈时先核对说话的时间，锚点有疑义时保留原话与不确定性。

偏移按 Unicode 码点计数，不按 UTF-8 字节或浏览器 UTF-16 下标计数。只有 `matched` 使用非空偏移，且必须满足 `content[start:end] == quote`；其余状态的偏移为空。原文出现多次时，程序结合上下文定位，不能任取第一处。模型提出的引文和位置必须经程序核对。

定位先尝试精确原文；无精确匹配时，允许把连续空白统一为一个空格后核对，但不连接原本分开的单词，也不替换大小写、标点或语义内容。只在本任务允许阅读区间内定位；最终保存实际原文切片、偏移和哈希，原提案及空白修正进入运行记录。错误的上下文/偏移提示不能推翻唯一合法匹配；多个可能位置且无有效提示时仍为 ambiguous，不猜测。定位兼容不代替证据的语义审核。

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
| `Conflict` | `target: string, alternatives: object[], reason: string`；可选 `related_refs: ObjectRef[]` | 每个 alternative 保存 `value`、`support`，必要时 `gaps`；其中 support 的 target 相对该 alternative 定位，支持整个说法时使用 `/value`；跨对象冲突用 `related_refs` 列明涉及的对象/字段，保留相互冲突的具体说法 |

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
