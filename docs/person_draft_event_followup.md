# 保留初版 EPG，按已有事件增补

这版将初次生成与补搜分为独立预算，取消补搜后的整图重建。
人物、公司、事件名称或阶段数量均未写死。参考 HTML 用于说明过程细节，
不作为固定的活动数或阶段模板。

## 应用基线

当前 `FinMycelium_event_relevance_clock_fix.patch` 直接叠加在已安装
`FinMycelium_incremental_event_enrichment.patch` 的代码上，无需撤销上一版：

```bash
git apply --check FinMycelium_event_relevance_clock_fix.patch
git apply FinMycelium_event_relevance_clock_fix.patch
```

如果工作目录仍停在“第一步完成后”，先应用已交付的
`FinMycelium_postbuild_event_followup.patch`，再应用
`FinMycelium_incremental_event_enrichment.patch`，最后应用这份计时修复；
不要在旧的 `event_centered_search` 或 `unbounded` 方案上直接叠加。
有本地修改导致 check 失败时先处理冲突，不能用强制覆盖代替检查。

## 流程与预算

1. 原始搜索、P0 与 builder 正常生成初版 Person EPG；原初始检索额度保持完整。
2. 读取初版已有 event，以名称、实体、具体活动和年份线索进行补搜。
   只有名称的薄事件也可检索，无需用户预先填写 event 列表。
3. 补搜使用独立的检索和 P0 计数，只处理新增来源。
4. 新资料进入单独约 60,000 字符证据池，不重新截断或替换第一轮证据。
5. 对有新来源且有剩余额度的 event，分别提交一次增补提议、一次模型审核。
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
  max_elapsed_seconds: 300  # 补搜采集阶段，不含后续模型处理
  max_relevance_elapsed_seconds: 300  # 补充 P0 单独从筛选开始计时
  max_relevance_model_calls: 12
  max_model_calls: 24      # 所有 event 的增补提议＋审核总次数
  max_output_tokens: 8192  # 单次输出还受原 generation_config 较小上限约束
  queries_per_event: 2
```

字符按 Python Unicode 字符计算，包含分配后的来源包装，不是 token。
60,000 是本阶段去重后的证据池容量，不是所有模型调用累计输入量：
同一来源可服务多个相关 event，提议与审核也会重用证据。
旧事件相关的原文摘录可复用，每个 event 最多带入 12,000 字符的旧证据摘录；
同时提供既有活动，用于检查重复和矛盾。模型调用仍另有上述有限上限。

初始 builder 的 `max_calls` 与补充 `max_model_calls` 分别计数。
初次构图已用完自身额度，不会自动禁止独立的补充阶段。
预算耗尽时报告具体未执行的 event；不会宣称所有事件均已深挖。
补搜和补充 P0 分别使用有限计时器，P0 批次之间不会重新开始计时。
筛选失败/待审、筛选额度耗尽与已判无关的来源分别报告。

## 从现有资料续跑

本次日志显示：补搜获得 9 篇、45,327 字符原始资料，但搜索耗尽计时后，
旧代码把同一个过期计时器传给 P0。P0 零调用，全部资料标成 REVIEW，
随后被 wrapper 排除，误报 `no_new_relevant_sources`。本补丁修正这条链路。

可复用本次已完成的初版和补搜资料，不再执行搜索、网页解析或初始构图：

```bash
python -m finmy.runner.resume_event_enrichment \
  --input-dir /path/to/pipeline_output_2026110821211808196944 \
  --config /path/to/your_pipeline.yaml \
  --output-dir /path/to/new_resume_output
```

把路径替换为本机实际路径，先解压运行包。`--config` 使用带有模型配置的原 pipeline YAML；
人物与时间范围直接恢复自归档，不重新解释用户请求。输出目录必须为空或尚不存在。
该命令只重新执行补充 P0 与事件增补/审核，仍受各自调用和时间上限约束；
原运行文件不变。命令会打印最终 HTML 和报告路径。

新增状态 `relevance_time_budget_exhausted`、`relevance_call_budget_exhausted`、
`relevance_processing_failed`、`unreviewed_sources` 区分筛选阻塞原因。
`no_new_relevant_sources` 保留给已审查且无相关来源的情况。
`resume_provenance.json` 记录复用路径及本次新增搜索/解析/初始构图调用数（均为零）。

真实归档资料的离线回放已验证：同样 9 篇、12 块可执行 3 批 P0 并进入增补函数。
回放使用模拟分类结果，只证明计时与执行链路，不证明 9 篇都相关或最终内容质量。

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
- 明确的中英文日期规范化后保留年月日精度；不从发表日期推算行动日期，
  不为缺失日期自动补年、月或日。
- 单个 event 提议无效、审核拒绝或调用失败时保留原内容，其他已成功补充的事件不回滚。
  补充阶段不能把成功的初版变为构图失败。

原有全部行保留是机械保障；来源是否可信、引文是否充分支持结论，
仍然需要内容评估。第二次模型审核不是独立人工核验，也不能证明输出质量已达到参考 HTML。

## 输出与复核

初版目录和根目录的 `builder_input_contents.json` 等证据文件保留。
新增主要文件：

- `initial_person_epg.json`：初版图快照。
- `draft_event_search_plan.json`：实际查询、逐事件搜索状态和遗漏原因。
- `event_enrichment/relevance/`：只针对补充资料的 P0 记录。
- `event_enrichment/context_budget_report.json`：额外证据池分配。
- `event_enrichment/supplementary_input_contents.json`、`supplementary_sources.json`：补充输入。
- `event_enrichment/event_XXXX_propose_request.json` / `review_request.json` 与响应：事件提议与审核。
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
本次计时修复后的相关检查共 257 项测试、236 个子测试通过；展示测试运行实际页面 JavaScript。
这些测试证明实现约束，不等同于真实重建结果已达到参考 HTML 的细节质量。
