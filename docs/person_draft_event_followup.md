# 保留初版 EPG，按已有事件增补

这版将初次生成与补搜分为独立预算，取消补搜后的整图重建。
人物、公司、事件名称或阶段数量均未写死。参考 HTML 用于说明过程细节，
不作为固定的活动数或阶段模板。

## 搜索与人物构图入口

本流程已与 main 的共享搜索实现合并，无需另行应用历史 patch。
`configs/search_pipeline.yml` 使用 `search_config.mode: agent`，
模型、provider 和搜索限制在 `search_config.enhancement` 中独立配置；
示例明确选择 DeepSeek 和 Bocha，并允许联网，运行前需要配置对应密钥。
设置 `mode: simple` 可继续使用旧采集器。

CLI 的 `run_search_pipeline` 和现有重建页面均读取
`builder_config.reconstruction`：person 使用人物组织、Person EPG schema、
规范 JSON 与专用 HTML；company 保持 AgentEventBuilder 的原生公司路径。
选择公司时须同时配置 `builder_type: AgentEventBuilder`。
搜索的 `target_type` 不替代 builder 的主体、覆盖期和范围配置。

初次搜索使用原始请求和配置主体，完成后将选中的原文直接送入初版预算分配。
随后直接读取初版已经存在的 event，为每个 event 调用同一套共享搜索算法；
薄事件只有名称也可以检索。新算法自行决定搜索、阅读、补缺与停止，
不再叠加旧的 decision-followup 搜索。
事件覆盖期是检索范围提示，只有显式的搜索发表日期配置才过滤页面发表时间。

共享搜索保存选中来源的完整正文与版本；初版和补充阶段分别进行一次最终证据分配。
来源标题、URL、发表时间和版本随筛选、预算重排进入 builder，
不会按输入序号错配。发表日期不是事件日期；不完整日期不会补成虚构时间戳。
搜索暂停、失败、额度耗尽且未完成交付、或无可用原文时，初版不启动构图。
补搜部分完成时只接收已完成 event 的原文，并报告未完成的 event。

## 流程与预算

1. 原始搜索与 builder 正常生成初版 Person EPG；原初始检索额度保持完整。
2. 读取初版已有 event，以名称、实体、具体活动和年份线索进行补搜。
   只有名称的薄事件也可检索，无需用户预先填写 event 列表。
3. 补搜使用独立的检索计数，只处理新增来源；相关性由搜索 Agent 判断。
4. 新资料进入单独约 60,000 字符证据池，不重新截断或替换第一轮证据。
5. 对有新来源且有剩余额度的 event，先各提交一轮增补提议和模型审核，再用剩余额度定向修订失败项。
   提议为空或结构/引文预检失败时不再调用审核。所有尝试均计入额度。
6. 只合并通过审核的有据活动、细节、关系和可选阶段；最终使用现有 Person EPG 页面渲染。

默认配置（已有显式设置仍有效）：

```yaml
all_content_config:
  max_content_length: 60000  # 初版证据上限
  max_document_chars: 12000

event_followup:
  enabled: true
  max_content_length: 60000  # 额外新增证据池，所有 event 共用
  max_document_chars: 12000
  max_search_calls: 12
  max_parse_calls: 40
  max_search_model_calls: 30  # agent 搜索决策总次数，与增补提议/审核独立
  max_elapsed_seconds: 300  # 补搜采集阶段，不含后续模型处理
  max_model_calls: 24      # 所有 event 的提议、审核、修订、重审和重试总次数
  max_repair_rounds_per_event: 1  # 初次尝试之后的修订轮数，0 禁用，允许 0..3
  max_output_tokens: 8192  # 单次输出还受原 generation_config 较小上限约束
  queries_per_event: 2
```

`queries_per_event` 仅用于 simple 采集器；agent 模式由共享搜索模型安排查询。
搜索、阅读、搜索模型调用上限由所有 event 共用，不会按 event 数倍增。
每次查询消耗所选 provider 数量的请求额度；额度不足的 event 会明确跳过。
补搜任务的配额与累计消耗落盘，暂停后重新进入同一目录不会重置预算。

字符按 Python Unicode 字符计算，包含分配后的来源包装，不是 token。
60,000 是本阶段去重后的证据池容量，不是所有模型调用累计输入量：
同一来源可服务多个相关 event，提议与审核也会重用证据。
旧事件相关的原文摘录可复用，每个 event 最多带入 12,000 字符的旧证据摘录；
同时提供既有活动，用于检查重复和矛盾。模型调用仍另有上述有限上限。

初始 builder 的 `max_calls` 与补充 `max_model_calls` 分别计数。
初次构图已用完自身额度，不会自动禁止独立的补充阶段。
预算耗尽时报告具体未执行的 event；不会宣称所有事件均已深挖。
补搜使用有限计时器；不再设置独立的相关性筛选调用或时间额度。

## 从现有资料续跑

补充来源直接进入字符预算分配与事件增补，不再经过第二次相关性分类。

可复用本次已完成的初版和补搜资料，不再执行搜索、网页解析或初始构图：

```bash
python -m finmy.runner.resume_event_enrichment \
  --input-dir /path/to/pipeline_output_2026110821211808196944 \
  --config /path/to/your_pipeline.yaml \
  --output-dir /path/to/new_resume_output
```

把路径替换为本机实际路径，先解压运行包。`--config` 使用带有模型配置的原 pipeline YAML；
人物与时间范围直接恢复自归档，不重新解释用户请求。输出目录必须为空或尚不存在。
该命令只重新执行补充来源预算分配与事件增补/审核，仍受字符和增补调用上限约束；
原运行文件不变。命令会打印最终 HTML 和报告路径。

旧的 relevance 配置与标签不再参与执行，也不再生成相关性分类报告。
`resume_provenance.json` 继续记录复用路径及本次新增搜索/解析/初始构图调用数（均为零）。

## 保留与增补约束

- 原 graph、event、stage、活动、交易、详情、来源与证据行保持原样。
  新内容通过追加记录加入，不让模型重写整张图。
- 已有活动可追加细节；原来采用 `detail_mode=selected` 的活动会同时追加显示选择。
- 新增活动支持个人行动、公司行动、交易和背景进展，演员来自有据实体。
  无法确认的参与者不会默认填主体人物。
- 新阶段可组织新增活动，也可把新增活动关联到已有阶段。
  原活动的阶段归属保留；本轮不重新编排整张图的阶段成员。
- 展示层按有据日期把新增活动/阶段插入到较晚的旧项前面，保留旧项之间的相对顺序。
  时间不明或时间范围重叠时保持稳定排序，不改写规范图里的原记录。
- 新模型引文必须出现在这次请求可见的来源正文/旧证据摘录中，
  再定位到准确来源字符区间。模型产生的查询或事件名称不算原始证据。
- 复用可确定重复的已有活动，新增事件关联；不为复述建立重复事实。
  同一交易的部分数值/单位矛盾会被确定性拒绝，其余语义重复和冲突由审核检查。
- 时间处理复用已有主体时间策略：支持模糊窗口、相对日期和有依据的历法转换，
  规范值不必逐字出现在引文里。引文本身仍须真实存在；转换、锚点、精度与事件归属由审核检查。
  不把发表日期默认作为行动日期，也不为未知日期补造年月日。
- 单个 event 提议无效、审核拒绝或调用失败时保留原内容，其他已成功补充的事件不回滚。
  补充阶段不能把成功的初版变为构图失败。

原有全部行保留是机械保障；来源是否可信、引文是否充分支持结论，
仍然需要内容评估。第二次模型审核不是独立人工核验，也不能证明输出质量已达到参考 HTML。

## 增补中的时间与事件归属

先根据原文中的交易、持续事项和发展过程判断是否属于同一 event，再处理时间。
初版成员活动覆盖的日期范围只是当前观察结果，不是新增活动的准入条件。
提议用 `event_reason` 说明新增活动与当前事件的联系；同一人物、公司或相似主题本身不够。
请求明确区分当前可引用的 `allowed_activity_ids` 与跨事件查重用的 `known_activities`。
用户显式设定的研究范围仍保持原样，模型不能把自动推导的事件范围当作该约束。

增补提议的 `activities[].time` 兼容旧字符串和 null，推荐采用已有的可验证时间字段形状：

```json
{
  "value": "2022-07",
  "evidence_source_contents": ["2022年7月下旬，公司完成了这笔投资。"],
  "reasons": ["原文明确给出年月；下旬为21日至该月最后一天，确切执行日未知。"],
  "time_window": {
    "start": "2022-07-21", "end": "2022-07-31",
    "original": "2022年7月下旬", "approximate": true
  },
  "window_semantics": "uncertainty"
}
```

时间引文必须包含在对应活动的可见引用中；转换结果不需要字面相同。
锚点、历法和规则应在 `reasons` 中解释，并交由现有审核调用检查。
程序只检查可表示的日期/区间、字段一致性和引文定位，不用有限的节日或季节白名单替代模型判断。
无法可靠确定日期时可以使用 unknown/null，保留其他有据活动内容。
该扩展只涉及增补输入协议，最终 Person EPG schema 不变；原文、窗口和理由进入已有时间与证据字段。

规范 event/stage 表没有独立的起止日期列。JSON 保留其成员活动时间，HTML 重新渲染时
按成员活动计算分组范围，因此已接纳的更早或更晚活动会相应改变范围，无需改写旧事实。
`event_enrichment_report.json` 的逐事件 `time_coverage` 记录接纳前后的 observed、primary、context
范围及变化；这是已知活动的证据覆盖范围，不宣称事件真实起止或持续时间。
未知日期不会被填为发表时间，背景活动单独列示，窗口的模糊性和原始表达继续保留。

时间处理不需要额外模型调用或整图重建。下述有界修订共用原增补调用额度，
独立的 60,000 + 60,000 字符证据预算与增补调用总上限保持不变。

## 失败项修订与合格部分保留

所有 event 先获得原有的首轮机会，再按事件顺序处理待修订项，默认最多一轮。
每轮在同一个 `CallLedger.json` 中计费；不重置预算，不重新搜索，也不调用初版 builder。
准备发起修订前须同时留出修订和后续审核的两次额度；已有候选只需重审时保留一次额度。

- 引用、schema 或合并检查失败：把上一份提议、具体错误和原有可见证据交给模型。
  模型应修正有原文依据的问题，删除无法支持的项，保留独立有效内容。
  修订后的完整提议重新执行引用、日期、结构检查，再进行语义审核。
- 审核定位了局部问题：可返回 `rejected_paths`，例如 `/details/2` 或 `/activities/0/details/1`。
  路径只能来自请求中的 `proposal_items`。程序剔除指定项、依赖它的活动/细节/关系，
  以及不再被引用的新实体和阶段，再把剩余候选完整送审。删除问题项本身不代表审核通过。
- 审核只给出整体否决或文字意见：兼容旧的 `{approved, issues}` 响应，改走定向修订。
- 审核超时、连接失败、限流或服务端临时错误：在额度允许时复用候选重审。
  不盲目重复 400/401/403 请求；保存有界错误诊断。无效审核 JSON 也只能重审，不能当作批准。

每次重试使用相同来源片段，更新已接纳图的上下文，避免覆盖其他 event 的成功补充。
只有所有检查通过且收到明确的完整批准，候选才写入最终图；失败、额度不足或轮数耗尽时，
保留之前已接纳的内容。设置 `max_repair_rounds_per_event: 0` 可恢复单次提议/审核行为。

逐事件 `attempts` 记录每轮动作、问题反馈、审核和调用次数；`repair_stop_reason` 区分
额度不足、修订轮数耗尽和禁用修订。`accepted_subset` 记录通过重审的保留部分，
路径沿用删除前那份提议的索引；每次实际审核均以该次请求的 `proposal_items` 为准。

## 输出与复核

初版目录和根目录的 `builder_input_contents.json` 等证据文件保留。
新增主要文件：

- `initial_person_epg.json`：初版图快照。
- `draft_event_search_plan.json`：实际查询、逐事件搜索状态和遗漏原因。
- `event_enrichment/sources/`：补充原文、文档 ID、声明的范围与检索来源档案。
- `event_enrichment/context_budget_report.json`：额外证据池分配。
- `event_enrichment/supplementary_input_contents.json`、`supplementary_sources.json`：补充输入。
- `event_enrichment/event_XXXX_propose_request.json` / `review_request.json` 与响应：事件提议与审核。
- `event_enrichment/event_XXXX_rNN_repair_request.json` / `review_request.json` 与响应：逐轮修订和重审。
  `event_XXXX_rNN_subset.json` 保存待重审的保留候选；原始请求/响应不会被覆盖。
- `event_enrichment/CallLedger.json`、`event_enrichment_report.json`：真实调用尝试和逐事件结果。
- `event_enrichment/final/FinalPersonEPG.json`、`FinalPersonEPG.html`：合并后的规范图和页面。
- 根目录 `event_refinement_report.json`、`evidence_supply_usage.json`：选中结果及分阶段预算统计。

如果某个有据背景活动没有已知参与者，旧版 SubjectGraph 投影可能不可用；
规范 Person EPG 仍然保留，原因写入 `SubjectProjectionStatus.json`。
旧 `event_cascades` 和 Sparse builder traces 仍仅描述初版，不冒充增补后的完整回放。

## 验证范围

回归验证覆盖：完整 builder 仅执行一次、旧行原样保留、独立预算与耗尽行为、
来源/局部引用/日期、重复交易数值量级、审核失败、跨事件事实复用，以及 UI/CLI 同一路径。
测试使用离线模型适配器与现有有效 EPG fixture，不调用真实搜索或付费模型。
搜索衔接回归还覆盖新旧入口路由、暂停/空交付、跨事件共享配额、来源版本传递，
以及实际 Person EPG 校验与 JSON/HTML 输出。
这些测试证明实现约束，不等同于真实重建结果已达到参考 HTML 的细节质量。
