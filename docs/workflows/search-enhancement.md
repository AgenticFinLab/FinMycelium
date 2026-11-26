# Search enhancement

Enhanced search combines Baidu / Bocha / Exa acquisition, source-level handoff,
and material allocation within a 90,000-character Builder input budget.
It prepares material for draft EPG construction and review. It does not change Builder
algorithms, EPG schemas or visualization formats.

The original full runner still defaults to `simple`; enhanced search is opt-in with
`search_config.mode: agent`. Event, person and company research tasks share acquisition.
This branch provides ordinary event construction through AgentEventBuilder and
SparseRagBuilder; person-specific construction remains in its separate implementation.

## Workflow and code layout

The same search-side agent and tools serve all cases. The logical steps are:

1. Record the research object, original requirement and optional scope.
2. Generate a process-oriented query and search all selected providers.
3. Acquire and inspect saved source bodies; record partial content and failures.
4. Review inspected sources and record explicit exclusions; preserve original text for handoff.
5. Identify important remaining gaps; return to search when useful, or finish with unresolved gaps.
6. Retain the complete selected material, then allocate the Builder input within its budget.

The workbench uses continuous execution with Start/Continue, Pause and Retry for failed
tasks. Retry continues the saved task rather than clearing it. CLI/Python single-step
execution and pause/resume use the same persisted state.
The agent assists relevance and gap decisions; it is not a factual completeness verifier.
Candidate reading prioritizes likely evidence gain for important unresolved questions.
Cached-body availability and provider identity are not relevance scores. Unfetched
candidates retain their titles, URLs and discovery hints; the decision context counts
all unread candidates, cached unread bodies, unfetched candidates and failed fetches
separately. Compact unread hints and fetch errors remain visible at finalization.
When fetching is enabled, discovery tries the original URL once for Baidu or Bocha
results that lack a saved body and have no earlier fetch attempt. A cached body
still needs to be inspected before its passages can be marked for delivery.
The agent can use the existing `read_source` to fetch a promising uncached URL, or
trace an original through an explicit link or a targeted `search`. These operations
consume the existing budgets. There are no provider quotas or additional reviewer
calls. Important unattempted, inaccessible or insufficiently supported leads belong
in `gaps`; unused candidates do not prevent handoff.
Narrative deliverables, gap explanations and selection reasons use English. Queries
and reading keywords follow the source language; English output does not require
English-only retrieval. When an English query has low yield and mainly Chinese
results, an important gap can justify a Chinese reformulation with useful original
names/aliases. No provider is restricted to one language and bilingual duplication
is not mandatory. Long-body lexical matching does not translate: use source-language
keywords or explicit reading locations. Apply the same evidence standards across
languages, trace useful secondary accounts to accessible original records, and keep
original titles, quotations and body text. Any translation is labeled separately.
The `search` action accepts optional `provider_queries`, mapping selected providers to
language or alias variants of the same question. Unspecified providers receive `query`.
Each actual query is validated, cached and recorded separately, using the same provider
budgets and result limits. This does not add a translation model call or require bilingual
duplication. Provider observations expose Chinese discovery hints and actual attempted
queries; they are navigation signals, not evidence-quality scores. Inspect results before
spending the remaining query rounds so important gaps and inaccessible originals can
receive a targeted follow-up.

For person events, assess personal participation during initial inspection, alongside
chronology. Prioritize an important personal-action gap before spending the remaining
query rounds on additional terms or peripheral endpoints; a complete chronology is not
required first. This is decision guidance, not a fixed query quota or a claim that each
case has private negotiations. Public decisions, communications, commitments, responses
and adjustments may be supported across investment, family, charity or other storylines.

The default BM25 reader ranks windows within a saved source. By default it considers
up to 24 windows per query, subject to the read-character limit. Unread matches take
priority. A verification replay reports `already_read`. The historical topic reader
also supports a 40% within-document threshold with neighboring context for tasks
without a scoped reading plan. Either reader accepts an explicit original location.
Each read reports returned characters and newly inspected original characters, including
explicit-location rereads. The agent may verify known text and mark important passages.
Three consecutive operations adding no original text, new candidate or validated priority
mark produce a redirect hint; six require finalization with `low_gain` or `insufficient`
and unresolved gaps. Query/cursor changes and replayed text alone do not reset this counter.
New original intervals or new valid marks do. This persisted operational limit does not
certify coverage, change the handoff contract or prevent progressive reading of long files.

In Agent feedback, already-inspected ranges may be replayed once for verification. Further requests covered
by that replay return compact `replay_suppressed` feedback instead of the same body.
The record follows source/version/ranges across other operations and restarts; changing
keywords or cursors does not reset it. Newly inspected text always passes. New validated
priority ranges on that source permit another verification; duplicate marks, changed
reasons and marks on other sources do not. Annotations remain accepted independently
of body replay. This bounds repeated payloads, not the total number of useful reads,
and does not delete evidence, infer missing facts or introduce another stopping rule.
Simple search and explicit source-reader calls retain original text on every read, including
repeated pause/resume; a compact Agent response is never treated as a missing document.

Before first inspection of a partial search-returned body, the reader attempts the
original public URL once with a request timeout capped at 20 seconds, also subject
to the configured timeout and size limit. A recognizable expanded body is
saved as a new version; blocked, shorter or unrelated responses leave the cached text
available. Already-inspected versions and explicit cursors remain stable. Acquisition
attempts are logged; no additional search/model request is made. This does not guarantee
access to full interviews or paywalled content: the agent must retain the acquisition
limitation and may follow an accessible original or transcript within the existing budget.

All three providers use the same public-body reader. HTML decoding checks the byte-order
mark, valid UTF-8, page charset declarations and explicit HTTP charset hints, then uses
byte-based detection if necessary. Requests' implicit Latin-1 does not override a page's
encoding. The saved parse records the selected decoder and its basis.

Beautiful Soup preserves visible text in semantic `main`/`article` containers, including
questions outside a nested article. Clear navigation, advertisements and hidden elements
are removed; substantive sidebars, qualifications, headings and table rows remain.
For pages without these containers, [Trafilatura](https://trafilatura.readthedocs.io/en/latest/corefunctions.html)
selects body text with recall favored and tables retained. Extracted wording and order
must match the visible original; otherwise the reader falls back to visible DOM text.
Table cells remain separated, with row/column metadata. Paragraph and row locations refer
to the saved parse, not byte offsets in raw HTML. HTML title, author and explicitly labeled
publication metadata are retained; publication claims remain separate from event dates,
retrieval dates and modification dates, and conflicts with provider dates stay visible.

HTTP success alone is not a usable body. Obvious challenges, error pages, script-only shells,
invalid decoding and empty parses receive distinct statuses and cannot become read evidence
or enter the Builder handoff. The agent sees `not_attempted`, `access_failed`, `parse_failed`
and `obtained` separately, alongside the detailed result. Short genuine notices are allowed;
these checks do not certify factual accuracy or complete extraction. Browser rendering and
OCR are not part of this reader.

The reader supplies bounded title/author/observed-link hints. Following a link records its
parent source and version, even if the destination was already a search candidate. A link
or canonical declaration does not prove independent reporting or original authorship.
There is no automatic crawl: existing search/read operations and budgets still apply.
Rejected partial-body expansion downloads are retained under `acquisitions/` with their
raw hash and parse diagnostics, while the usable cached version and its locations remain
unchanged. Previously saved source versions are reused, never silently reparsed by an
updated extractor. Use a new search task to evaluate the new acquisition behavior.
Acquisition errors record HTTP status, error category and retry eligibility without
response bodies or exception strings. A source with no cached body gets at most two
fetch attempts per saved run, with the second reserved for transient network/server
errors; denied or missing pages are not fetched repeatedly. `Retry-After` is respected
without sleeping inside the reader. Failed partial-body expansion still keeps the cached
original. The agent can search a title, author or quote for an accessible original, or
follow an observed link to another part; no page URL or missing text is invented.

Source choice precedes character allocation. There is no separate retained-source
count cap; the separate reading budget still limits which sources can enter the pool.
Review all inspected sources for useful actions, qualifications, outcomes and independent
or conflicting support. Judge added personal-action evidence separately from new event
terms. Repeating transaction terms or being a secondary source is not by itself a reason
to drop a useful attributed statement; retain its qualifications or trace the original.
Commentary and speculation are not promoted to facts. A statement spanning several matters can
support this event with its shared scope intact. At agent finish, all inspected current
source bodies enter the candidate pool unless explicitly excluded with a short reason
in `source_exclusions` (`{"source_id": "reason"}`). `source_ids` lists proposed retained
sources; unmentioned inspected bodies are conservatively retained rather than silently
lost. Unread candidates are not admitted. Explicit exclusions, automatic retention and
source versions are frozen in `source_review`; these are relevance decisions, not fact
verification. Known unread-source exclusions are stored separately as
`uninspected_exclusions`, with `evidence_reviewed=false`; their explanations do not
prove the body was inspected or inaccessible. Unknown IDs and unread-source admission
still fail validation. Cleanup, duplicate removal and the usual character allocation follow.
More free space can accommodate more retained sources, but reassembly of a frozen
manifest cannot promote unread URLs or reverse a source-selection decision. Legacy
span handoffs and explicit programmatic source lists retain their existing semantics.

| Location | Responsibility |
|---|---|
| `finmy/search/state.py` | Task/config validation, saved state, cumulative usage |
| `finmy/search/tools.py` | Common Baidu Web Search, Bocha Web Search and Exa Search adapters |
| `finmy/search/sources.py` | HTML/PDF/TXT acquisition, original versions, hashes and read locations |
| `finmy/search/html.py` | HTML decoding, body extraction, quality diagnostics and observed links |
| `finmy/search/reading.py` | Located query reads, cached rereads and bounded original excerpts |
| `finmy/search/progress.py` | Provider language observations and persisted research progress |
| `finmy/search/agent.py` | Shared decision prompt, search/read/finish actions, bounded recovery |
| `finmy/search/evidence.py` | Account for inspected sources and exclusions; validate passage priorities against saved originals |
| `finmy/search/protocol.py` | Search model output settings and single-action JSON decoding |
| `finmy/search/handoff.py` | Complete manifest, source provenance and existing Builder contract |
| `finmy/search/budget.py` | Deterministic whole-block allocation with source quotas and priority passages; no model or network calls |
| `finmy/search/assembly_windows.py` | Replay compatibility for saved window-policy manifests |
| `finmy/search/control.py`, `pipeline.py`, `__main__.py` | Lifecycle, writer locks, Python and CLI entry points |
| `finmy/workbench/search_*.py` | Search controls, progress, material review and local experiment history |
| `finmy/runner/search_pipeline_runner.py` | Opt-in enhanced search alongside the original simple chain |
| `configs/search.yml` | Search-only defaults, independent of Builder configuration |

New tasks with an identified research entity save a scoped plan. The agent marks
inspected original passages, and the program selects among them within the
90,000-character limit. It checks question support against the ranges actually
delivered. The workbench keeps the plan's selection policy when the budget changes.
See [Passage retrieval and evidence selection](search-retrieval-selection.md).

Tasks without a scoped plan use `evidence_priority_windows_v3`. This policy ranks
additional passages by BM25 for each source and reading question. It keeps marked
passages and their context, then expands eligible whole blocks at 50%, 40% and 30%
of the best score for that question in that source, while space permits.
Saved v4 manifests replay their original scoring, which additionally weights each
paragraph by the squared fraction of query-term IDF weight it covers.

## Credentials and configuration

Copy `.env.example` to `.env` only when creating a new local environment. Keep existing
credentials when updating the example. Fill the selected services' keys:

| Variable | Used by |
|---|---|
| `ARK_API_KEY` | Default search model; also Builders configured with an Ark model |
| `HUNYUAN_API_KEY` | TokenHub models used by search and/or construction |
| `HUNYUAN_BASE_URL` | TokenHub HTTPS origin or `/v1` base for the key’s region |
| `BAIDUSEARCH_API_KEY` | Baidu Web Search |
| `BOCHA_API_KEY` | Bocha Web Search |
| `EXA_API_KEY` | Exa Search and the text returned by that search call |

Search `lm_name` and `builder_config.lm_name` are independent. Search defaults to
`ark/deepseek-v4-1-flash-261017` with high thinking and JSON output. Ark
`glm-5-3-flash-260828` retains low thinking without forced JSON mode. These
search-only settings leave Builder requests unchanged; build-only examples select
their own model. Existing saved tasks and local profiles
retain their recorded model unless explicitly changed in settings.
Use `tokenhub/<console-model-id>` to select TokenHub independently for either stage;
model IDs containing `/` retain that namespace. These are model services, separate
from the Baidu/Bocha/Exa search services. Model selection is independent of the search
limits below. TokenHub uses OpenAI Chat Completions; its thinking models may include
reasoning in the output token limit. Account/model availability needs a separately
authorized connectivity check; configuring a key does not verify access. See the
[TokenHub protocol documentation](https://cloud.tencent.com/document/product/1823/135872).
Only selected providers need keys. The workbench loads the repository `.env` on an
explicitly enabled start, without overriding existing environment variables. The search
CLI reads process environment variables; it does not automatically load `.env`.

| Search setting | Default / meaning |
|---|---|
| `providers` | `[baidu, bocha, exa]`; any subset remains selectable |
| `retrieval` | `{mode: bm25}` for new tasks. For tasks with a scoped plan, the agent marks inspected originals and reviews coverage before finishing. |
| `max_results` | `{baidu: 3, bocha: 3, exa: 5}` per query; a saved integer still applies equally to all selected providers |
| `max_search_requests` | 24 per task, shared across providers, initial search and follow-up |
| `max_read_sources` | 40 distinct sources; rereading a source does not consume a new source slot |
| `max_model_calls` | 80 attempted search-side model requests, including failures |
| `max_read_chars` | 16,000 per source-read operation |
| `max_builder_material_chars` | 90,000 across sample contents, including source labels and omission markers |
| `max_model_context_chars` | 180,000 for the serialized decision context and system prompt |
| `generation_config.max_tokens` | 8,192 including reasoning on the default Ark DeepSeek model; semantics differ by model |
| `timeout` | 120 seconds per request |
| `allow_network` | `false`; preparation does not execute services |

Default settings and new-task forms share the same configuration fields, including output
tokens, context size and per-read size. The form can preview model policy without loading
credentials or invoking a service; recorded request options show what was actually sent.
Saving defaults refreshes parameter controls while preserving research drafts. Saved tasks
and profiles retain their recorded settings; new defaults do not silently rewrite them. Characters, model tokens, request counts and fees are different measures.
Selecting all three providers consumes three requests per uncached query round;
24 provider requests allow at most eight full rounds.
The 5/3/3 result limits allow up to 88 returned entries before deduplication; they do
not require eight rounds, 88 distinct URLs or a matching number of retained sources.

After a code update, restart the workbench before creating a new experiment so its
loaded search modules match the installed code. Inspect the saved task settings and
`selection.json` budget policy; a file-based code fingerprint alone does not prove a
long-running process reloaded every module. Existing runs retain their saved handoffs.

Search decisions use one JSON action per model response. The TokenHub presets
`deepseek/deepseek-flash` and `deepseek-v4-pro-202606` use
`response_format: {type: json_object}` with `thinking: {type: disabled}`, following
the [TokenHub DeepSeek JSON-mode guidance](https://cloud.tencent.com/document/product/1823/132248).
These search-only policies override conflicting output-format and thinking settings at
request time, including on resume; they leave saved task settings, sampling defaults,
budgets and Builder requests intact. Other models retain their configured protocol.
The trace records the effective request controls as `request_options`.

The decoder accepts a single JSON object, optionally enclosed in one JSON code fence.
It rejects empty content, duplicate keys, multiple objects, commentary and XML/DSML
tool markup without guessing an action. Invalid responses use the existing bounded
retry loop and cumulative call accounting; no separate repair-model call is added.
The prompt requests only the next action and waits for program feedback. Research-plan
citation labels are separate from runtime source IDs; planning notes are not proof of
reading in the current run. JSON mode is requested from the provider, but returned content
still passes strict decoding and validation before execution. Reads may include an optional
`gap` explanation. Position reads use `location: {"block": 0, "offset": 0}`; cursor
fields at action level are moved into `location` when unambiguous, with a trace record.
An empty query beside a cursor is omitted; nonempty query/cursor combinations and conflicting
positions remain errors. Unread-source exclusions are saved as uninspected candidate notes,
not content reviews, and do not block finish. Unknown IDs and unread-source admission remain errors. Finish uses `reason_detail`; the explanatory alias
`finalization_reason` is also accepted, with `reason_detail` taking precedence. Explanations stay
in the run record, never in source evidence, and cannot override the controlled stop
reason or budgets. Unknown action fields are reported explicitly for correction.

Invalid action output and correctable action parameters are fed back to the model and
continue within the cumulative model-call budget. Consecutive-error counts are diagnostic;
they do not stop the task. No automatic restart loop or hidden SDK retries are added.
Missing credentials, invalid local service settings and API request/access rejections
(HTTP 400/401/403/404/422) stop for operator correction. Website acquisition failures
remain source outcomes; they are not API-credential failures.
After correcting the cause, use Retry on the same task. All attempted calls, prior logs,
source versions and budget usage are retained; retry does not grant a new budget.
The workbench loads `.env` without overriding process variables: after changing a key
there, restart the workbench to load it, then retry. Legacy tasks stopped by consecutive
errors can also be retried under this policy.

Selected providers receive the common query unless a same-question variant is supplied
in `provider_queries`, for both initial search and follow-up. Baidu
uses Web Search standard with rewrite off by default; Bocha uses Web Search with summary;
Exa uses Search auto with text contents. Summaries/snippets are discovery leads. Baidu's
72-unit query limit is checked before requests (CJK U+4E00..U+9FFF counts two, other
characters one); overlong queries are rejected for correction, not silently truncated.
When Baidu is selected, the decision model is instructed to supply its short variant
in the same search action, preserving entities, dates, negation and essential conditions.
Baidu `content` and Exa `text` are cached as partial original text with provider/field
provenance. The first read still attempts the original URL; failed acquisition keeps
the cached excerpt and its locations. Bocha summaries remain discovery leads:
selected URLs use the existing HTML/PDF fetcher, and failed reads return `search_leads`
outside evidence spans. No bulk fetching or additional LLM rewriting stage is added.
Bocha domain-filter mapping is not supported. Publication filters are optional and
independent of event dates: later retrospective material can support an earlier event.

## Prepare, run and review search

A task JSON needs `target_type` (`event`, `person`, `company`), `target_name` and
`query_text`, the user's original research requirement. Optional `key_words`, `seed_urls`
and `local_files` provide hints or starting material. Additional scope fields are kept
for the decision model; they do not automatically set publication filters.

For example, save `output/search/task.json` in the ignored runtime directory:

```json
{
  "target_type": "event",
  "target_name": "Microsoft–Activision acquisition",
  "query_text": "Trace the proposal, regulatory decisions, deal changes and closing during 2022–2023. Later retrospective sources are allowed.",
  "key_words": ["Microsoft", "Activision", "acquisition"],
  "coverage_start": "2022",
  "coverage_end": "2023"
}
```

Validate without calling services or creating a run:

```sh
python -m finmy.search --task output/search/task.json --task-id case-001 --config configs/search.yml
```

Actual execution requires credentials in the process environment and `--execute`.
For Python callers that keep keys in `.env`, load it explicitly with
`dotenv.load_dotenv('.env', override=False)` before calling the CLI `main(...)` or
`finmy.search.pipeline.run_search(...)`. Python API execution also requires
`allow_network=True` in the explicit search configuration. No Builder runs from this entry.

`--steps N` pauses after N model actions. Resume using the same task/run ID and omit
`--task`; usage is retained. `run_batch` processes distinct task IDs sequentially and
reports individual outcomes. Linux/WSL file locks reject simultaneous writers to the
same task. Pause takes effect after the current operation.

After the first search, follow-up queries require a concrete `gap` reason. SDK retries
are disabled; correctable failures consume the same total model-call budget. The final one or two
model requests are reserved for `finish`. Context pressure first switches to compact
finalization; if that still exceeds the limit, execution pauses before a request.
These controls bound work; they do not force a successful handoff after a failure.

For catalog work, open **数据集**, choose **普通事件** or **人物事件**, and prepare the search from the selected event.
Use **任务中心 → 独立与批量检索** for an independent question or a batch of local ordinary events with confirmed scopes.
In **任务中心 → 运行记录**, start or continue a task, inspect progress and sources, and review omissions.
Reusable defaults live in **设置**.
New-task advanced settings expose the request timeout and context limit; stopped tasks can revise them under **调整运行上限**. Saved profiles
retain their configured values until explicitly changed.
The handoff panel describes the recorded material allocation, and **设置 →
接口与工作区** includes Ark, TokenHub, Baidu, Bocha and Exa configuration presence without displaying
keys. Workbench simple mode runs fixed queries through the common providers and
readers and delivers selected original spans. In enhanced mode, tasks with a scoped
plan deliver marked passages. Tasks without a scoped plan use whole-block allocation
within the handoff budget.
Material adoption into an event's review list is explicit
and does not automatically approve evidence or launch a Builder. After confirming
the actual input, create a separate Builder task. See [event workbench](event-workbench.md)
for versioned inputs, draft review and execution boundaries.

## Reading relevant passages and stopping

The shared `read_source` action accepts either `query` or a sequential `location`.
The default BM25 reader ranks passages even in short documents. To read an entire
notice or see qualifications beyond a match, start at `{"block": 0, "offset": 0}`
and follow `next_location` while more text remains. A query with the legacy topic
reader and no scoped plan returns `full_saved_text` when the saved body fits in one
read. Both readers preserve the source version, original block and character
offsets, and respect the per-read character limit and distinct-source quota. A
partial body keeps its acquisition status even after all its saved text has been read.

Query reads prefer matching text that has not already been read. Once the matching
passages have been inspected, they can replay bounded original passages with
`match_status: already_read` and `replayed: true`. Replays do not consume a new source
slot, fetch the website again, or inflate unique reading coverage. Empty results do not
erase the previous useful preview. They have no sequential
`next_location`, since the returned passages can be disjoint; use another query or an
explicit location for further inspection. `no_match` is a vocabulary-dependent result,
not proof that a fact is absent. Temporary windows do not rewrite stored parsing.

The agent sees saved-body availability, read/unread character counts and bounded
`read_evidence` excerpts with exact block/start/end and reusable `read_location` cursors.
The excerpts contain inspected originals, including at finalization, and share the
existing context budget. Compact attempted search/read questions remain available at
finalization; they are not assertions that those questions were answered. `reviewed`
only means that a nonempty passage was inspected.
Before stopping, it should examine promising unread sources and relevant sections for
core process gaps, especially personal actions versus corporate transactions. There is
no minimum source count and no requirement to read every candidate or whole document.
`finish.reason_detail` records why remaining leads do not justify further reading;
older callers may omit it. These semantic decisions remain advisory, with existing
budgets and forced finalization unchanged. The complete source manifest preserves
the saved bodies. The scoped Builder handoff contains selected, inspected passages.

Person-event catalog tasks automatically ask for both the event process and evidenced
actions of the focal person within the confirmed scope. Questions adapt to the storyline;
transactions and particular action categories are not required. Decisions, authorization,
communication, commitments, responses and adjustments may be relevant. Corporate acts do
not establish personal attribution by themselves. Retain useful context, independent
corroboration and conflicting accounts even when they add no new personal action.
Personal participation is an independent research objective. Once basic event facts
are established, important personal questions take priority over more repetitions of
the same event facts. Interviews, public statements and retrospective accounts can add
useful evidence alongside official records. Do not require private correspondence,
exact dates, a minimum number of actions or proof of personal execution of every event.
At finish the model supplies an advisory `person_evidence` status (`supported`,
`limited` or `unattempted`) and detail on personal evidence, attempts and remaining gaps.
Missing/invalid assessments are recorded as `not_assessed`; no automatic semantic
acceptance is inferred from a successful run or from the presence of annotations.

After inspecting relevant seed material, direct further queries/reading toward important
unanswered questions. Different questions may require different sections of a long source.
Distinguish gaps not attempted, attempted but unsupported, and inaccessible sources.
Forced finalization persists its trigger across action errors and pause/resume. It does
not switch back to research because an error response is shorter. An explicit increase
to the triggering context/model-call budget can reopen research, with a trace record.
`termination_trigger` records the program trigger separately from `stop_reason` and the
model's evidence assessment; summaries and the workbench show both. A successful handoff
at a limit is not certification of full coverage. Historical runs without a recorded trigger
remain unspecified rather than receiving an inferred success claim.

## Priority original passages

The existing decision/finish response may include `priority_passages`, for example:

```json
{"source_id":"runtime-source-id","block":3,"start":0,"end":200,
 "reason":"Adds the person's response and its qualification"}
```

Each entry must refer to an inspected interval in a saved source; the program pins
its version. Optional explicit versions must match. The reason is model advice,
stored separately from source text, and is never copied into Builder evidence.
Invalid entries receive diagnostic feedback without aborting the valid search/read
action or remaining handoff. Final `source_ids` and explicit `source_exclusions`
account for retention; inspected sources omitted from both remain candidates.
Omitted or superseded annotations remain visible in the omission record.
The generated search summary reports annotation retention and the advisory personal
participation assessment; exact locations and allocation outcomes remain in `selection.json`.

Marking happens during existing model decisions, without a separate selection agent
or hidden model call. The prompt asks for marks after useful reads, then only missing
marks at finish. Concise gap/detail strings avoid repeating the chronology under the
shared reasoning/output-token limit. Legacy callers can omit the field.
The model sees only bounded excerpts, not necessarily each
complete source. Annotations can help preserve valuable evidence but cannot certify
factual completeness or turn a corporate action into a personal action.

## Complete material and input budgeting

`finish` supplies proposed `source_ids`, optional reasoned `source_exclusions`, gap
notes and a stop reason. The program completes the inspected-source pool, then
packages each selected saved body, not only the excerpt seen by the search model.
It removes only empty paragraphs, exact navigation labels and long exact repeated
paragraphs, and deduplicates identical document bodies. Original files remain intact.

The complete manifest pins original versions, block references, source headers and
retrieval queries, validated priority locations and advisory personal-evidence assessment.
It is independent of the input budget and reconstructs the selected
saved bodies without duplicating the evidence tree. “Complete” describes that saved
selection; provider-returned text remains `partial` and is not certified full-page text.

PDF parsing retains the page number and character offsets into extracted page text.
It prefers paragraph-like boundaries and uses sentence/line boundaries for long passages,
with a soft target of 1,600 characters per block. This is text segmentation, not recovery
of PDF layout semantics; words and table rows are not cut to enforce that target.
Saved raw bytes and parsed versions are immutable. Reusing a saved version preserves
its original parser, locations, status and retrieval time.

New handoffs freeze source titles, retrieval times and reported publication dates with
the selected text. Provider dates agree at day precision or remain unknown/conflicted,
with their original values and providers retained for review. No date is inferred from
an event period, URL or PDF filename. Publication metadata does not verify an event date.

### Whole-block allocation for tasks without a scoped plan

The following rules apply to `evidence_priority_windows_v3` when complete
material exceeds the budget. Scoped plans select marked ranges even when all
saved text would fit.

- Allocate half the budget across sources using max-min fair quotas. Each source uses
  its own successful reading questions and the confirmed research scope for core content.
  Long-document expansion uses only that source's questions; when none exist, it falls
  back to the research scope. Multiple questions are retained without a fixed count cap.
  Questions from other sources, superseded versions or reads without passages do not
  expand that document. Search queries remain in the acquisition history.
- Freeze the positive research scope in `scope_queries` and source/version questions in
  `reading_queries`. For catalog tasks, scope uses the event name, included scope and
  keywords, with person identity bound to that event. Exclusions and planning prose are
  not positive queries. Unstructured tasks retain their original query; the full task
  still reaches the Builder. The allocation's `query_plan` records the actual core and
  expansion queries for each source.
- Select BM25 text windows. Per document and query, consider all anchors with
  at least 50% of the highest score in the initial assembly pass, plus one neighboring
  block on each side. There is no fixed anchor-count cap; source allocation and the
  total character budget limit what is retained. These are deterministic relevance
  heuristics, not factual support scores. When the first context block explicitly
  refers backward (for example, "at that point"), shared-space windows include one
  additional preceding block when it fits; this expansion is not recursive.
  When no lexical match
  exists, allow only a bounded opening-block preview.
- Keep a compact source whole when it fits its fair share of the final budget, before
  expanding long-document windows. This avoids discarding clauses from short notices
  while spare budget remains.
- Prioritize validated marked paragraphs from the remaining budget, with adjacent
  original context when it fits: try two blocks on each side, then one, then the marked
  paragraph alone. Keep complete paragraphs and restore original order.
  The source core allowance remains protected; priorities cannot increase the budget.
  Record any priority paragraph that cannot fit. Invalid/missing suggestions fall
  back to the ordinary allocation; unmarked relevant material remains eligible.
- Share the remaining space, first completing anchor context, then adding ranked windows
  in stable source-ID rounds. With spare budget, lower the assembly threshold to 40%,
  then 30%, appending eligible windows without removing or reallocating any selected
  blocks. Count only newly added text and retain whole blocks; skip windows that do
  not fit. Stop at the budget or when no eligible window fits at the 30% floor,
  without padding. Restore original block order and mark omitted gaps.
- Record the policy, assembly code hash and each threshold stage. Without priority
  locations, v3 follows the same progressive allocation. Requesting workbench
  reassembly of an older unscoped manifest creates a new v3 revision retaining its
  source versions, complete-material manifest and previous handoff files. Upgrading an
  older manifest without frozen scope queries uses its saved research task for fallback.
  Stored balanced and earlier evidence-priority policies retain their historical allocation
  rules when replayed without an override.
- Count headers and omission markers toward the budget. Keep omitted paragraphs in the
  complete material, distinguishing relevance selection from material-limit omissions.
  Do not cut selected blocks, generate replacement summaries or raise the limit automatically.

If everything fits, preserve the full input unchanged. Allocation uses a deterministic heuristic,
not a guarantee of semantic completeness. `selection.json` records allocations and
omissions. Queries are frozen in new complete manifests; old manifests fall back to their
original task and keywords, never later searches. The allocation policy is frozen in
new manifests; existing manifests without that field retain their prior allocation
behavior. Reassembly retains previous revisions. No extra model call is used for assembly.
V3 allocates whole saved blocks. A historical manifest with a window policy
supports replay at its original offsets. A scoped manifest retains its own
selection policy when the workbench creates a revision at a different budget.
Interrupted model responses retain their available usage and finish reason in the
error trace. Responses already logged before an action-validation error are not charged
again in that error record; recorded usage is not an account invoice.

## Hand off to Agent or Sparse

`builder_input.json` has exactly two top-level fields: `user_query` and `samples`.
Each sample contains `sample_id`, `raw_data_id`, and `content` with original text and
source/version labels. Gap notes and allocation metadata stay in sidecar records.
The existing loader constructs `BuildInput(UserQueryInput(...), [DataSample(...)])`;
no schema conversion or new Builder implementation is required.

After reviewing the search status, material and gaps, use the existing build-only entry.
Both commands below are offline preflight checks; neither executes a Builder:

```sh
python -m finmy.runner.build_only_runner --input output/search/case-001/runs/initial/builder_input.json --config configs/build_only_agent.yml
python -m finmy.runner.build_only_runner --input output/search/case-001/runs/initial/builder_input.json --config configs/build_only_sparse.yml
```

Expect `offline_preflight_pass`. Empty samples, duplicate sample IDs or malformed input
are rejected. No credentials are required for offline preflight. Passing this check
confirms the input/configuration contract, not online model compatibility or graph quality.
Actual build execution is a separate action requiring `--execute` and the configured
model credentials; the build-only entry supports explicit `--env-file .env` loading.

For the existing full runner, set `search_config.mode: agent` and supply search options
under `search_config.enhancement`. Once search finishes, it passes the budgeted contents
and original query to `FinmyPipeline.lm_build_pipeline_with_contents`; the old search
trimming policy is not applied again. Paused, failed, insufficient or limit-stopped search
does not create the Pipeline. This full route still performs existing query summarization,
optional Matcher processing and database storage before the Builder. With Matcher enabled,
material may be selected again. The build-only route is the direct route for a reviewed
search package: it retains the search sample IDs and text without those extra stages.

For the native person-event path, the workbench freezes the confirmed single-event scope
and adds `user_query.extras.person_event` and `source_registry` through
`finmy.person_epg.input.freeze_search_input`. Source metadata comes from the selected
handoff, including publication and retrieval dates; the original sample text is unchanged.
Legacy handoffs can recover provider dates, recording the consulted metadata in provenance.
Search `target_type: person` alone does not configure a person Builder.

## Storage and verification

```text
output/search/<task_id>/
  sources/<source_id>/<version>/       original bytes and parsed paragraphs
  runs/<run_id>/
    run.json, trace.jsonl, responses/  task/config/version, usage and actions
    complete_material.json            fixed complete-material references
    selection.json                    allocation, gaps and omissions
    builder_input.json                existing Builder input contract
    handoffs/<revision>/              prior handoff revisions
```

Dataset-linked workbench tasks also generate a local `search-summary.md` and
publish the lightweight summary under EPG-dataset's Git-ignored
`output/search/<catalog-event-path>/` directory. Source texts and raw responses
remain in search storage. The worker saves summaries independently of
page rendering. Workbench databases and search originals live in the dataset's
ignored `output/workbench/`; portable task/scope/configuration records, source indexes
and execution summaries are also exported under
`workbench/search/<YYYYMMDD-HHMMSS>_<event-name>_<short-task-id>/` for Git review.
Creation times use Asia/Shanghai; model and status changes do not rename a task.
`workbench/search/README.md` automatically indexes events, models, statuses and input sizes.
Full task IDs and runtime directories remain unchanged. Existing ID-only shared record
directories migrate on export; `finmy.workbench.records.migrate_search_records(dataset_root)`
can migrate saved records without runtime files or service calls.
Direct command-line search keeps its existing output location. See [dataset selection and automatic summaries](event-workbench.md#select-an-event-from-epg-dataset).

When confirmed material becomes a workbench build task, the event's formal
`search/` receives `builder-input.json`, `search-summary.md`, `sources.csv` and
`manifest.json` for the adopted handoff. The input file contains the exact confirmed
Builder payload and is covered by the manifest hashes. This collection is separate from all-attempt workbench records
and from the event's reviewed `epg/` artifacts. Search reruns do not overwrite it.
See [adopted search and reviewed graphs](event-workbench.md#adopted-search-and-reviewed-graphs).

Runtime files, raw responses, machine-specific notes and experiments stay outside Git.
The shared repository holds code, configuration, documentation and small offline tests.
SQLite/database files and their journal, WAL and SHM sidecars are ignored, including
when a custom workspace sits outside `output/`. Keep other custom runtime assets in
an ignored directory or outside the source repository.
Daily search uses workspace tasks. **辅助工具 → 历史实验回看（只读）** is an
optional, separate view of `.local-experiments/search-enhancement/*/runtime/*/runs/initial`.
It reads saved records without rerunning or changing them. **按来源直接组装（不调用模型）**
provides a read-only preview of complete/budgeted input and omissions, including for
historical experiments.

Run the focused offline search and handoff checks from the repository root:

```sh
python -m pytest -q -p no:cacheprovider \
  tests/test_search_enhancement.py tests/test_search_agent_regressions.py \
  tests/test_search_document_handoff.py tests/test_search_budget.py \
  tests/test_search_materials.py \
  tests/test_search_control.py tests/test_search_build_contract.py \
  tests/test_non_ui_search_runner.py
```

Offline checks cover provenance, budget enforcement, deterministic replay, recovery and
both Builder input preflights. No real Builder call is needed for contract verification.
Small-case search success does not establish exhaustive factual coverage. Gap judgments
remain advisory, partial/failed acquisition is visible, and draft EPGs still require review.
Browser rendering, OCR and dedicated professional-source connectors are outside this
version. External source text is treated as data, never as instructions to execute tools.
