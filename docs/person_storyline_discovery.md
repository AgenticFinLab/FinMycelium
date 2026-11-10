# 先发现人物主线，再逐事件检索

输入人物与时期即可运行。Pipeline 页面选择 Person 后，只需填写人名和时期；
时期支持 `2023`、`2023-05`、`2023-05-06` 等时间点，以及 `2022-2023`、
`2022-01-01 至 2023-12-31` 等范围。年份、月份保留原有精度，不伪造具体日期。
命令行使用相同的时期解析：

```bash
python -m finmy.runner.person_storyline_pipeline \
  --request "Buffett 2022-2023" \
  --config configs/search_pipeline.yml \
  --output-dir EXPERIMENT/output/person_storylines
```

该入口把简写转换为人物范围；姓名和年份不会写死。已有完整人物配置也可配合
较长的自然语言请求。简写请求优先于 YAML 中旧的人物信息。

## 执行顺序

1. 使用 `search_config.enhancement.lm_name`（示例为 DeepSeek）发现候选
   storyline，再归纳 domain。投资、项目、角色或持续事项形成具体 event，
   不以年报或会议为容器混合无关事项。每项包含人物关联、范围、检索词和过程问题。
2. 对每个候选 event 调用现有共享搜索 Agent，由它安排查询、阅读、保留来源与停止。
   人物、年份及过程问题随任务传入；候选计划不是原文，不恢复旧 relevance filtering。
3. 对通过原文和引用校验的来源去重，保留 URL、标题、发表日期、文档版本与 event 路由。
   有合格材料就按事件分配同一个初版字符预算，并调用现有 SparseRagBuilder。
   部分完成或证据不足的事件也能交付已经选中的有效材料；未完成事件和缺口单独记录。
4. 将候选目录单独传入人物组织阶段。最终 domain/event 可依据原文合并、拆分、增加或省略，
   使用原有 schema、JSON 和 HTML 流程。候选描述不能充当活动、日期或引文证据。
5. 保存本次构建的 JSON/HTML 并返回，不再发起构图后的补搜、增补或审核。

## 预算和开关

```yaml
search_config:
  mode: agent
  storyline_discovery:
    enabled: true
    max_model_calls: 2  # 独立的发现额度：最多一次发现及一次 JSON 修订
    max_events: 8      # 候选上限而非目标数量；不会因检索额度不足再删候选
  event_search:
    max_search_requests: 12 # 每个事件的 provider 请求上限；双引擎最多六轮 query
    max_read_sources: 12
    max_model_calls: 24     # 包含搜索、阅读决策和原搜索自带的收尾重试
    max_concurrent_events: 2
    reuse_sources: true     # 共享已下载原文；每个事件仍自行阅读和选择
  enhancement:
    providers: [bocha, baidu]
    # 保留模型、联网和其他设置；以下是所有事件共用的初搜总上限
    max_search_requests: 96
    max_read_sources: 96
    max_model_calls: 192
    max_builder_material_chars: 120000
all_content_config:
  max_content_length: 120000
```

每个事件启动前，按全局剩余额度预留不超过 `event_search` 的配额，
不按事件数机械均分，也不要求剩余额度必须凑齐一整份配额。
任务提前完成后释放未用配额，后续候选可继续启动。并发任务的预留也计入全局限制，
失败请求照常计数，续跑不重置累计使用量。每次 query 消耗所选 provider 数量的请求额度。
共享池已有原文时，没有新的 provider 请求额度也可启动只读缓存的事件任务，
但仍需阅读和模型额度。确实无法启动的候选留在队列和报告里，不删除。
并发默认为 2，可配置其他正整数。示例总额度可支持八个事件各使用完整配额。
发现最多另用 2 次模型调用，搜索最多 192 次，总计最多 194 次，均为上限而非必须用完。
`usage.search_model_calls` 只统计搜索，`usage.discovery_model_calls` 单独统计发现，
`usage.total_model_calls` 为两者之和。这与旧版把发现计入搜索调用数的口径不同。
原文最终输入共用 120,000 字符；这是所有事件合计，不是每个事件或所有模型请求累计输入。
显式设置的较低预算仍有效，不会被运行时悄悄扩大。

共享池按原文版本和校验值复用下载结果，不继承其他事件的阅读记录或入选结论。
当前事件模型能看到共享来源的标题和正文预览，必须自行阅读、选择，才能加入该事件交付。
候选过多时分页展示，模型可通过 `list_sources` 查看后续候选；不会因共享目录变大而直接收尾。
正文解码优先考虑 BOM、网页声明及可信编码，避免把 HTTP 默认 Latin-1 当作中文网页编码。
明确的验证码和空目录壳不作为正文；短小但有效的报道仍可使用。
收尾阶段只提供已阅读且可用的来源 ID。混入未阅读来源时，反馈要求修正 `finish`；
若调用耗尽，最多保留模型最后一次选择中可校验的子集，并记录剔除项和缺口，状态仍为证据不足。

构图后的补搜入口与 `--event-followup` 参数已移除。旧 YAML 的 `event_followup`
配置会提示并忽略，不会启动额外搜索。共享搜索 Agent 在初搜内部仍可按缺口继续查询与阅读。

人物 `agent` 模式默认启用主线发现；显式设置 `storyline_discovery.enabled: false`
可直接围绕人物请求进行 Agent 搜索。单事件直接进入 Agent 搜索，不经过人物主线发现。

## 结果与续跑

- `storyline_discovery/plan.json`：候选 domain/event、过程问题与发现调用计数。
- `storyline_discovery/checkpoint.json`、`request_*.json`、`response_*.json`：发现过程记录。
- `initial_event_search/phase_report.json`：各事件状态、配额与累计消耗。
- `storyline_search_report.json`：总预算、已取得原文的数量和未完成事件。
- `search_coverage_report.json`：搜索完成度、各事件缺口及构图状态；构图后也保存到 builder 目录。
- builder 目录中的 `PersonStorylineCandidates-Result.json`、`PersonStorylineResolution-Result.json`：
  候选目录和最终 event ID 对应情况；未保留 ID 不代表该事件不存在。
- 其余 Person EPG JSON、HTML 输出沿用现有 builder。

同一目录、同一请求和配置可复用已完成的发现与搜索，继续尚有额度的中断任务，累计预算不重置。
耗尽额度的任务不会因为重复运行命令就获得新额度。此命令不承诺复用已经完成的 builder。
只有所有事件都完成检索才标记 `finished`；部分成功标记 `partial`，有合格材料仍构图，
返回报告路径、已保留文档数与未完成事件。命令行只要生成了结果就返回退出码 0，
但 `search_complete` 仍为 false，UI 也会显示覆盖缺口。完全没有合格原文才不启动 builder。
证据不足仍如实报告，不把候选描述当作证据，不修改 Person EPG 的原有 schema。
已下载的原文、读取位置、搜索缓存和失败反馈保存在各任务目录，后续继续交给原搜索处理。

服务暂时不可用且没有可用原文时，返回 `waiting`（冷却）、`blocked`（需要处理访问权限）
或 `paused`，CLI 退出码为 2，UI 显示已保存的状态和目录。单个事件不会停用其他事件的
搜索器。有合格材料时仍可部分构建。继续同一目录不会清零已使用的搜索、读取或模型额度。
`search_coverage_report.json` 的 `resume.next_retry_at` 提供冷却截止时间；403 等访问错误
需先恢复对应服务。冷却结束后不会自行发起后台调用，需要显式继续。

旧版运行或明确调整预算时，使用新的输出目录显式接续：

```bash
python -m finmy.runner.person_storyline_pipeline \
  --request "Buffett 2022-2023" \
  --config configs/search_pipeline.yml \
  --resume-search-from EXPERIMENT/output/person_storylines \
  --output-dir EXPERIMENT/output/person_storylines_resumed
```

接续保留原候选 domain/storyline、已完成任务、原文和累计调用数；新额度是包含历史消耗的
累计上限，不是额外赠送的一轮预算。原目录的既有结果不修改，新目录须为空。任务范围必须匹配，
不能借接续更换人物、年份或事件。此入口只接续搜索，不复用原目录中的 EPG 构图结果。
接续会校验历史消耗和新额度，准备完成后才发布新目录，不触发 API。
旧原文若因错误编码或已识别的验证码/空目录壳需要修复，会在新目录中从保存的原始字节
重新解析，归档旧解析及交付，撤销相关旧阅读记录，重新交给模型审阅。
原始文件、版本和历史调用数不变，原目录不改写；修复后的正文不会冒用旧的阅读证明。
尚未创建搜索任务的候选仍可按队列规则等待。
旧版因 provider 故障误标为 `insufficient` 的任务，也可以通过上面的显式接续入口重新打开；
保持原请求文字、人物与时间范围，并使用原预算即可，无需增加额度或重新发现事件。
单份损坏原文会单独记录并隔离，不会阻止其他来源或事件恢复。必要抽取或审核中断时，
Builder 会保存 `BuildInterruption.json` 及可保留的候选；任意抽取位置的自动恢复尚未实现，
不能把这些中间结果当作已完成 EPG。完整抽取之后的组织阶段仍支持原有恢复入口。
交接时读取 `trace.jsonl` 只按真正的换行符分隔记录，避免正文中的 Unicode 行分隔字符
（U+2028/U+2029）导致合法日志被拆坏；原文和日志内容本身不修改。

实现入口为 `finmy/runner/storyline_discovery.py` 与
`finmy/runner/person_storyline_pipeline.py`。发现规则同时记录在仓库内
`finmy/runner/skills/discover-person-storylines/SKILL.md`，无需安装个人插件或新增依赖。

发现默认保留 8 个 event。模型返回更多候选时，先按返回顺序为每个有候选的 domain
保留一个 event，再按原顺序补足剩余名额；不因超量拒绝整份结果，也不额外调用模型筛选。
该顺序是确定性的优先级依据，不宣称是新的语义质量评分。筛选记录及被暂缓的候选保存到
`storyline_discovery/candidate_selection.json`，原始响应完整保留。
若 domain 数本身超过 8，覆盖每个 domain 优先：保留每个 domain 一个并在筛选记录中
明确标注超额；实际搜索仍受原来的总调用预算约束。不会为了满足数量而合并无关领域。
缺少 `event_terms` 时可使用已有 event 标题作为检索词。其他结构错误的修复反馈包含具体字段。
旧版本因候选超量拒绝、已耗尽发现调用额度的运行，在相同请求、配置和输出目录续跑时，
会重新校验已保存响应并筛选，不增加发现调用、不重置使用量。
