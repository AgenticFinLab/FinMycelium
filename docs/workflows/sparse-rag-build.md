# Sparse Text Reconstruction

SparseRagBuilder combines sparse routing with optional local retrieval augmentation
for multi-agent event reconstruction. It selects detail tiers by stage and episode,
uses compact context and reuses role results to reduce repeated generation.
The draft EPG contains stages, episodes, participants, actions, relationships,
supported transactions and source quotations. Outcomes remain in action details
and descriptions, following the shared `agent_build/structure.py` contract.

## Install and Configure

Use Python 3.11+ in a dedicated environment. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e ../lmbase
```

The last command assumes a sibling checkout of `AgenticFinLab/lmbase`. The offline
adapter tests were exercised against commit
`5137b8c84b70b1c46b025247233777d1764783ad`; other versions need the same tests.
No dependency installation or download happens in the sparse text entry.

Use `configs/sparse_pipeline.yml` as a starting point. Change `lm_name` and its YAML
anchor together, and set a token limit appropriate to the chosen model. The sample
uses `deepseek/deepseek-chat`; it is not a claim of current provider availability.
All seven roles currently share one backend and generation configuration.
Conflicting per-role overrides are rejected rather than ignored.

Only the matching provider key is needed for this entry:

| `lm_name` prefix | Environment variable |
|---|---|
| `deepseek/` | `DEEPSEEK_API_KEY` |
| `ark/` | `ARK_API_KEY` |
| `openai/` | `OPENAI_API_KEY` |
| `qwen/` | `QWEN_API_KEY` |
| `aihubmix/` | `AIHUBMIX_API_KEY` |

Provider URLs follow the installed lmbase adapter. Put credentials in a local
`.env`, never in YAML, source documents or Git. Pass `--env-file .env` to load it;
already exported environment variables take precedence. Key presence checks do
not prove authentication, quota or model compatibility. MinerU, search keys and a
database are not needed by the direct text entry.

## Input and Commands

`examples/sparse_input.json` is a small **fictional** storm case. Its format is the
existing `BuildInput`: `user_query` and a nonempty `samples` array. Each sample has
a unique `sample_id`, a `raw_data_id` and nonempty `content`. Optional sample fields
follow `finmy/generic.py`. Keep source URL, acquisition date and licence metadata in
`user_query.extras.source_registry`, indexed by `raw_data_id`.

The runner does not fetch external sources, summarize, translate or truncate the
input text. Every role sees the complete content with source IDs. When enabled,
local retrieval selects evidence cards from those inputs for the current role and
stage or episode; it supplements rather than replaces the full text. If the
combined prompt exceeds the model context, the request fails rather than silently
discarding evidence. Check source size and provider limits before a real run.

```bash
# Offline: imports, input/config validation, writable output root, key presence.
python -m finmy.runner.sparse_build_runner \
  --config configs/sparse_pipeline.yml --input examples/sparse_input.json

# Real calls: execute only after agreeing model, input and budget.
python -m finmy.runner.sparse_build_runner \
  --config configs/sparse_pipeline.yml --input examples/sparse_input.json \
  --env-file .env --execute

# Offline: validate and reassemble a completed run, without rewriting its files.
python -m finmy.runner.sparse_build_runner --replay output/sparse/build_output_RUN_ID
```

Each execution creates a separate `build_output_*` directory under `save_folder`.
The default `output/` is Git-ignored. Choose an ignored directory for custom paths.
There is no automatic resume, background job, parallel execution or transport retry.
Create a new builder for a new run; keep failed runs for diagnosis.

`--gantt` optionally renders `gantt.html` after successful construction using the
existing visualizer. Its result is recorded separately in `GanttStatus.json`.
Rendering failure does not invalidate or overwrite the graph. The HTML is a display
artifact, not a substitute for the JSON or content review.

## Roles and Routing

1. `SkeletonReconstructor` organizes stages and episodes.
2. `SkeletonChecker` audits the skeleton.
3. For each episode, `ParticipantReconstructor` reconstructs identities and actions;
   `TransactionReconstructor` extracts supported transfers; `EpisodeReconstructor`
   assembles the episode and relationships.
4. `StageDescriptionReconstructor` describes each completed stage.
5. `EventDescriptionReconstructor` describes the assembled event.

Later roles receive a compact participant identity registry, not accumulated
action histories. Stage and event descriptions use value-only views of assembled
content. Original role results and their evidence remain saved unchanged.

`enable_sparse_routing: false` requests standard detail in all roles. With routing
enabled, local evidence signals select detail tiers. `minimal` transactions still
run the transaction role; only an explicit skip in a saved plan omits it. No transfer
evidence should produce an empty array, not an invented financial transaction.
`EpisodeExecutionPlan-Result.json` records the actual plan. Locators use stage and
episode positions plus original IDs, so locally repeated episode IDs do not collide.

For new runs, Episode must return the exact placeholders
`Results of ParticipantReconstructor` and `Results of TransactionReconstructor`.
Assembly reuses the preceding role arrays unchanged; Episode generates the remaining
fields and relationships within the checked skeleton's scope. Historical replay
retains the recorded assembly contract.

`output_language` controls narrative text and reasons; entity names and verbatim
quotes retain their original language. Structural field names do not change.
Role schemas are derived from the shared dataclasses. Prompts allow non-financial
events and do not prescribe a fixed stage count.

## Bounds and Failure Handling

| Setting | Meaning |
|---|---|
| `max_new_tokens`, `max_tokens` or `max_completion_tokens` | Exactly one output cap, shared across roles; provider semantics apply |
| `max_calls` | Total submissions, including invalid-output retries; default 300 |
| `max_json_attempts` | 1 to 3 attempts per role invocation, default 3 |
| `request_timeout_seconds` | One request timeout, at most 3600 seconds; default 900 |
| `enable_context_assets` | Add local evidence cards; default true |
| `evidence_policy` | `report` by default: save the draft and quote diagnostics; `strict` optionally blocks unmatched quotes |

The `sparse_pipeline.yml` example allows up to 300 requests and enables evidence
cards. The [build-only](build-only.md) sparse example allows up to 40 and disables
cards. Both use the same builder and default to `report`.

A structurally invalid response can trigger a bounded, recorded retry. Balanced
JSON recovery and removal of outer Markdown fences are deterministic parsing, not
additional model calls. Empty responses, non-`stop` completion reasons, refusal,
tool requests and transport failures stop the run. SDK retries are disabled.
A timeout has unknown usage unless a response supplied it; do not assume it is free
or resubmit automatically. These limits are not a monetary budget guarantee.

## Results and Checks

| File | Contents |
|---|---|
| `BuildInput.json` | Original query, complete text and source identities |
| `RunManifest.json` | Status, input/config/prompt fingerprints, code identity, duration, usage and artifact hashes |
| `CallLedger.json` | Each attempt, role, status, duration, usage and completion reason |
| `ROLE-*.json` | Actual messages and original provider response; retry attempts have separate names |
| `ROLE-*-Result.json` | Parsed role outputs and episode locators |
| `EpisodeExecutionPlan-Result.json` | Effective episode routing and detail tiers |
| `ParticipantIdentityMap.json`, `ConstructionCheck.json` | Identity bindings, episode time checks and repeated-action candidates |
| `EvidenceCheck.json` | Quote locations in sources, unmatched quotations and fields without quotations |
| `QualityReview.json` | Local review hints for dates, payment status, relation endpoints and uncited paragraphs |
| `CandidateEventCascade.json`, `AcceptanceDecision.json` | Assembled draft before final validation, and the save decision after checks |
| `FinalEventCascade.json` | Completed graph after structure/reference checks and the configured evidence policy |

Total tokens remain `null` if any call's usage is missing. Known subtotals and
unknown-call counts are recorded separately; per-call reasoning/cache usage is
retained when the provider supplies it. No currency price is assumed. A hard process
kill may leave a `running` manifest or `pending` ledger entry: that is incomplete,
not successful, and must not be automatically retried.

Structural checks cover dataclass shapes, skeleton names, indices, IDs and endpoints.
Identity bindings and known episode time bounds are checked; unknown or unparsed
dates remain unchecked. Quotation matching allows exact text or whitespace-only
normalization and records source IDs, hashes and original character offsets.
Query metadata, unmatched quotes and fields without quotes are reported separately.

Default `report` mode preserves the final draft despite unmatched quotes; optional
`strict` mode blocks its save. Local diagnostics do not rewrite the graph or call a
model. Quality hints use English cues and can misidentify aliases or date wording.
**A located quote is not proof of factual correctness**, and uncited paragraphs are
not a measure of omitted facts. Review the draft before dataset publication.

Strict replay requires a completed manifest and unchanged artifacts, validates
the role sequence, locators and graph, and compares assembly against the saved
final JSON. It makes no new model calls. The Python method `integrate_from_files()`
without `strict=True` also accepts older result directories without manifests or
plans for compatibility; that legacy assembly is **not** the strict acceptance path.

## Optional Full Pipeline

`configs/sparse_pipeline.yml` also supplies every `FinmyPipeline` configuration
section. `FinmyPipeline(config).lm_build_pipeline_with_contents(...)` ingests text,
stores `RAW_DATA`, `MEAT_SAMPLE` and `USER_QUERY` in SQLite, summarizes the query,
then runs the builder. SQLite tables are created by the existing data manager.
`db_config.url` is authoritative; `DB_HOST` and similar dotenv fields are not read.
Create the database parent directory when using a custom path. The other example
configs now use `data/finmy.sqlite3`; create `data/` before using them.

This path adds a query-summary model call outside the builder's ledger; matching
can add more if enabled. Use the direct text entry for builder-only accounting.
PDF initialization is deferred only for SparseRagBuilder; supplying PDF sources
still requires the PDF service configuration. Other builders retain their existing
initialization behavior. Retrieval and summary strategies are not changed here.

## Offline Regression

```bash
python -m pytest tests -q
```

Tests include real lmbase message formatting and the sparse adapter, replacing only
the SDK transport with synthetic responses for end-to-end tests. They cover two
stages, source preservation, context opt-out, schema/reference failures, bounded
calls, missing usage, SQLite text ingestion and deterministic replay. They do not
measure live model quality, speed or cost. Run a separately approved small real-data
comparison before adopting this entry for large-scale construction.
