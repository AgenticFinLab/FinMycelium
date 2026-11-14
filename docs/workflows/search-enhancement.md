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
4. Select useful sources, preserving original text rather than generating replacement summaries.
5. Identify important remaining gaps; return to search when useful, or finish with unresolved gaps.
6. Retain the complete selected material, then allocate the Builder input within its budget.

The workbench uses continuous execution with Start/Continue, Pause and Retry for failed
tasks. Retry continues the saved task rather than clearing it. CLI/Python single-step
execution and pause/resume use the same persisted state.
The agent assists relevance and gap decisions; it is not a factual completeness verifier.
Directed reading uses the same within-document relative BM25 threshold as material allocation
(half the best score), with neighboring context and no fixed match-count cap. Already-read
strong matches do not promote weak matches into the next read. Explicit locations remain
available; filtered or unmatched text is not evidence that a fact is absent.

| Location | Responsibility |
|---|---|
| `finmy/search/state.py` | Task/config validation, saved state, cumulative usage |
| `finmy/search/tools.py` | Common Baidu Web Search, Bocha Web Search and Exa Search adapters |
| `finmy/search/sources.py` | HTML/PDF/TXT acquisition, original versions, hashes and read locations |
| `finmy/search/agent.py` | Shared decision prompt, search/read/finish actions, bounded recovery |
| `finmy/search/protocol.py` | Search model output settings and single-action JSON decoding |
| `finmy/search/handoff.py` | Complete manifest, source provenance and existing Builder contract |
| `finmy/search/budget.py` | Deterministic paragraph allocation; no model or network calls |
| `finmy/search/control.py`, `pipeline.py`, `__main__.py` | Lifecycle, writer locks, Python and CLI entry points |
| `finmy/workbench/search_*.py` | Search controls, progress, material review and local experiment history |
| `finmy/runner/search_pipeline_runner.py` | Opt-in enhanced search alongside the original simple chain |
| `configs/search.yml` | Search-only defaults, independent of Builder configuration |

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
`ark/doubao-seed-2-1-lite-260915`; the existing build-only examples select their own model.
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
| `providers` | `[bocha]`; select any combination of `baidu`, `bocha`, `exa` |
| `max_results` | 5 per query per provider |
| `max_search_requests` | 12 per task, shared across providers, initial search and follow-up |
| `max_read_sources` | 20 distinct sources; rereading a source does not consume a new source slot |
| `max_model_calls` | 40 attempted search-side model requests, including failures |
| `max_read_chars` | 12,000 per source-read operation |
| `max_builder_material_chars` | 90,000 across sample contents, including source labels and omission markers |
| `max_model_context_chars` | 100,000 for the serialized decision context and system prompt |
| `generation_config.max_tokens` | 4,096 answer tokens on the current Ark Seed model; reasoning is separate |
| `timeout` | 120 seconds per request |
| `allow_network` | `false`; preparation does not execute services |

Saved tasks and profiles retain their recorded settings; new defaults do not silently
rewrite them. Characters, model tokens, request counts and fees are different measures.
Selecting all three providers consumes three requests per uncached query round.

Search decisions use one JSON action per model response. The TokenHub presets
`deepseek/deepseek-flash` and `deepseek-v4-pro-202606` use
`response_format: {type: json_object}` with `thinking: {type: disabled}`, following
the [TokenHub DeepSeek JSON-mode guidance](https://cloud.tencent.com/document/product/1823/132248).
This search-only policy overrides conflicting output-format and thinking settings at
request time, including on resume; it leaves saved task settings, sampling defaults,
budgets and Builder requests intact. Other models retain their configured protocol.
The trace records the effective request controls as `request_options`.

The decoder accepts a single JSON object, optionally enclosed in one JSON code fence.
It rejects empty content, duplicate keys, multiple objects, commentary and XML/DSML
tool markup without guessing an action. Invalid responses use the existing bounded
retry loop and cumulative call accounting; no separate repair-model call is added.
The prompt requests only the next action and waits for program feedback. Research-plan
citation labels are separate from runtime source IDs; planning notes are not proof of
reading in the current run. JSON mode is requested from the provider, but returned content
still passes strict decoding and validation before execution.

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

All selected providers receive the same query for initial search and follow-up. Baidu
uses Web Search standard with rewrite off by default; Bocha uses Web Search with summary;
Exa uses Search auto with text contents. Summaries/snippets are discovery leads. Baidu's
72-unit query limit is checked before requests (CJK U+4E00..U+9FFF counts two, other
characters one); overlong queries are rejected for correction, not silently truncated.
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

In the workbench, select **新建检索** to create searches; use **任务中心** to start/continue,
inspect progress, read sources and review omissions. Reusable defaults live in **设置**.
From **事件数据**, confirm scope and choose one or several events to prepare searches.
New-task advanced settings expose the request timeout and context limit; stopped tasks can revise them under **调整运行上限**. Saved profiles
retain their configured values until explicitly changed.
The handoff panel describes the recorded material allocation, and **设置 →
接口与工作区** includes Ark, TokenHub, Baidu, Bocha and Exa configuration presence without displaying
keys. Workbench simple mode runs fixed queries without a search model, using the common
providers/readers and the existing span-based handoff. Enhanced mode uses source-level
budget allocation. The original simple full runner keeps its own existing behavior.
Material adoption into an event's review list is explicit
and does not automatically approve evidence or launch a Builder. After confirming
the actual input, create a separate Builder task. See [event workbench](event-workbench.md)
for versioned inputs, draft review and execution boundaries.

## Reading relevant passages and stopping

The shared `read_source` action accepts either `query` or a sequential `location`.
A query ranks temporary text windows in the saved body using lexical relevance and
returns original passages with nearby context, keeping their version, page/block and
character offsets. It uses the same per-read character limit and distinct-source quota,
without a search API or an additional model call. An uncached source still requires the
ordinary fetch. No fixed number of matching passages is imposed; the read budget applies.

Query reads prefer matching text that has not already been read. They have no sequential
`next_location`, since the returned passages can be disjoint; use another query or an
explicit location for further inspection. `no_match` is a vocabulary-dependent result,
not proof that a fact is absent. Temporary windows do not rewrite stored parsing.

The agent sees saved-body availability, actual characters read and a preview from a
previously read passage. `reviewed` only means that a nonempty passage was inspected.
Before stopping, it should examine promising unread sources and relevant sections for
core process gaps, especially personal actions versus corporate transactions. There is
no minimum source count and no requirement to read every candidate or whole document.
`finish.reason_detail` records why remaining leads do not justify further reading;
older callers may omit it. These semantic decisions remain advisory, with existing
budgets and forced finalization unchanged. Saved handoff bodies are still packaged
independently of what the model has read.

## Complete material and input budgeting

`finish` supplies inspected `source_ids`, gap notes and a stop reason. The program
packages each selected saved body, not only the excerpt seen by the search model.
It removes only empty paragraphs, exact navigation labels and long exact repeated
paragraphs, and deduplicates identical document bodies. Original files remain intact.

The complete manifest pins original versions, block references, source headers and
retrieval queries. It is independent of the input budget and reconstructs the selected
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

Budget allocation is applied only when complete material exceeds the limit:

- Allocate half the budget across sources using max-min fair quotas. For catalog tasks,
  use the event name and included scope, keywords and attempted search queries; exclusions
  and planning prose are not positive retrieval queries. Unstructured tasks retain their
  original query. The full original task is still passed to the Builder.
- Select BM25 text windows. Per document and query, consider all anchors with
  at least half the highest score, plus one neighboring block on each side. There is
  no fixed anchor-count cap; source allocation and the total character budget limit
  what is retained. These are
  deterministic relevance heuristics, not factual support scores. When no lexical match
  exists, allow only a bounded opening-block preview.
- Keep a compact source whole when it fits its fair share of the final budget, before
  expanding long-document windows. This avoids discarding clauses from short notices
  while spare budget remains.
- Share the remaining space, first completing anchor context, then adding ranked windows
  in stable source-ID rounds. Do not expand beyond those windows merely to fill the budget.
  Restore original block order and mark omitted gaps.
- Count headers and omission markers toward the budget. Keep omitted paragraphs in the
  complete material, distinguishing relevance selection from material-limit omissions.
  Do not cut selected blocks, generate replacement summaries or raise the limit automatically.

If everything fits, preserve the full input unchanged. Allocation uses a deterministic heuristic,
not a guarantee of semantic completeness. `selection.json` records allocations and
omissions. Queries are frozen in new complete manifests; old manifests fall back to their
original task and keywords, never later searches. The allocation policy is frozen in
new manifests; existing manifests without that field retain their prior allocation
behavior. Reassembly retains previous revisions. No extra model call is used for assembly.

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
`search/` receives `search-summary.md`, `sources.csv` and `manifest.json` for the
adopted handoff. This collection is separate from all-attempt workbench records
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
