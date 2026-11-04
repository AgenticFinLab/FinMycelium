# 人物模式

`reconstruction.mode: person` 现在直接生成 `SubjectGraph`；同时支持 `company` 模式。默认的 `event` 模式保留原流程。

完整结构、配置、运行命令和验证边界见 [subject_graph.md](subject_graph.md)。

输出：

- 原生主结果为 `FinalSubjectGraph.json`，含统一实体、独立事件、参与角色、具体行为和有时效的关系。
- 每个事件都有证据支持的 `subject_relevance`，个人与公司行为分别归属。
- 结果页提供原生 JSON / HTML 下载，下载 HTML 后查看 Gantt。
- `FinalEventCascade.json` 仅作旧工具兼容投影。
- `scope` 可留空，覆盖人物在指定时期内有资料支持的活动；原 OXY 配置仍可主动限定专题。
- 复用已有输入的 CLI 不补搜，但构图仍调用已配置的模型 API。


## Decision details and follow-up

Person-mode reconstruction preserves documented background in event descriptions and
information, reasoning and conditions in action details. These aspects are optional:
unavailable reasons are not invented, and missing detail is not a validation failure.
The original Gantt hover displays event context and action timestamps/details.

After relevance filtering, one bounded review extracts investment actions and proposes
only material evidence gaps. Repeated object/action pairs are merged. Sources already
collected are skipped. New documents pass the same relevance filter and context budget
before building. Search snippets and model gap summaries are never used as evidence.

```yaml
subject_search:
  max_decision_followup_queries: 2  # API requests total; 0 disables this step
```

This is one additional round, with Bocha 10 / Baidu 20 results per request and the
original full publication window. It reuses the existing parse/time limits. No recursive
follow-up is performed; empty results and failures leave the existing evidence usable.
The original missing-body follow-up remains unchanged.

Review input, proposed gaps and new source lists are saved in `decision_followup/`.
`retrieved_documents.json` contains the combined sources after new documents are added.
A retrieved page does not imply the decision gap is resolved. The builder uses only
documented details. Saved-input CLI builds still do not search.

## Event evidence

The existing planner returns an internal `event_sources` mapping from each event to
all documents covering that occurrence; each detail call receives only those sources.
Older plans fall back to matching title/context evidence, then date evidence; a warning
identifies this less complete allocation. This does not filter by publication year:
later accounts and documents covering multiple events can still be used. The planner
must cite identifying passages from relevant documents, not just a common person/topic.
`subject_event_sources.json` records the allocation. Without matching evidence, detail
construction is skipped and the unsupported event stays in diagnostics.

Claims quoting documents outside that allocation are excluded and retained in
`subject_event_evidence_review.json`, including compound actions mixing two occurrences.
Unsupported participation is excluded along with dependent actions; an event with no
supported participants is retained only in diagnostics. General contextual relations
keep their global evidence. The check also runs after the existing repair step and
adds no model/search calls.
It checks document boundaries, not semantic attribution within one document. The event
prompt requires the passage's own temporal context. Existing output needs rebuilding
from saved `builder_input_contents.json`; rendering alone does not correct its facts.

Actions dated wholly outside their parent event are also retained in
`subject_event_evidence_review.json` and excluded from the published graph, leaving
other records usable. Original dates are preserved in that trace; event intervals
are not widened. A recollection uses its speaking/publication date, with historical
dates in details. Unknown or overlapping coarse dates are not rejected by this check.

## Coverage review

After successful construction, each existing event gets at most one focused model review
using only its assigned sources and current event data. It can append evidenced context,
action details or distinct actions; it cannot change another event or add a new event.
One final graph-wide review then checks for materially omitted occurrences. Existing
events retain their assigned sources; a new
event must declare its supporting source IDs. No existing records or dates are rewritten.
The review returns additions only (at most 12 event groups), using the existing entity
registry, event limit and model configuration. For N existing events this adds N detail
review calls plus the existing single coverage call. Neither step searches or recursively
reviews its additions. The inference adapter's existing JSON retry is unchanged.

Each event supplement passes evidence, reference and time validation before being
accepted. Rejected additions leave the original event intact. Empty or failed review
leaves the constructed graph usable; unavailable information is not filled in.
`subject_event_detail_review.json` records each event's review outcome.
`subject_coverage_review.json` records the final coverage review's accepted event IDs and rejected records/reasons;
the model result trace preserves all proposed additions. `subject_event_sources.json`
includes accepted new events. The raw graph remains the pre-review diagnostic artifact.
This reduces omissions but does not guarantee exhaustive extraction or factual entailment.
Rebuild from saved input to apply the review; rendering existing JSON does not run it.

Both the main build and supplements restore formatting-only quotation differences to
exact spans of supplied text. Adjacent excerpt offsets are joined when packing new
input. Older packed input is matched across markers only after checking that offsets
are contiguous and lengths agree; actual gaps and separate documents are not bridged.
Long English passages also allow lost word spaces, without changing letters, numbers,
case or negation. Ambiguous compact matches remain unresolved. Supplements use only
their event's assigned sources, and their review trace records quotation restorations.

The planner and reviews keep a meeting's statements inside that occurrence. A proposed
new statement sharing a specific evidence passage, speaker and precise date/time with
an existing statement is flagged and retained in rejected records, rather than added
under another title. Similar topics, coarse dates or a purchase versus its later
explanation do not qualify. Existing possible duplicates are listed in
`subject_statement_duplicates.json` and validation warnings; no existing content is
silently deleted. This is an evidence-overlap check, not exhaustive semantic deduplication.

Decision follow-up accepts source-anchored variants of parenthesized bilingual names,
without inventing translations/tickers. A pronoun-only action quote needs an exact,
contiguous `object_context` passage identifying its referent; unrelated mentions do not
qualify. Queries use the matched name, and repeated supported name/action pairs merge.
`decision_gap_review.json` now records `rejected_gaps` with reasons and distinguishes
`no_gap` from `candidates_rejected`. The full date window, Bocha 10 / Baidu 20 and the
existing request cap remain unchanged. Nothing found means no further search round.
