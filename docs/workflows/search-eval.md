# Search-only evaluation

Run from the repository root with the existing project environment and `.env`:

```bash
python -m finmy.search.eval --task examples/search_eval/buffett_goldman.json
```

The task is the ordinary research task JSON (`target_type`, `target_name`,
`query_text`, optional `key_words`, `seed_urls`, `catalog`, `research_scope`).
The example is a fixture, not an algorithm-specific entity rule. No extraction
or Builder stage runs.

## Two evaluation modes

`--eval_mode manual` is the default. Search runs and exports the task, exact
final text, original locations, full acquired reference pool, source choices,
remaining gaps, factual checks, lead decisions, duplicate fraction, token usage
and timings. No Judge is called. `status=finished` means search/export completed;
`evaluation_status=manual_review_pending` explicitly leaves quality ungraded.
Upload the run folder/combined output for human or conversational review.

`--eval_mode auto` uses the existing Kimi configuration to grade **only the
selected originals**, with task-derived atomic fact questions. Switch modes
without `--fresh` to add judgments to the same search result:

```bash
python -m finmy.search.eval --task examples/search_eval/buffett_goldman.json --eval_mode auto
```

For an occasional full reference-pool evaluation, append `--eval_scope pool`.
This is more expensive; the default `selected` scope never reports pool recall
or provider ranking estimates. Both scopes use the same cached task rubric.
Ordinary Workbench defaults are unchanged. The CLI defaults search and Judge
to `ark/kimi-k3-1-pro-261024` and uses the existing API keys. Search settings,
including `retrieval`, load from the repository's `configs/search.yml` by default;
the evaluation keeps its Kimi model and generation defaults. `--config` accepts
SearchConfig JSON/YAML overrides, including an explicit model override.

The repository profile enables BM25 passage reading. Confirm the effective mode
in `output.json` under `search_config.retrieval`, and inspect `passage_retrieval`
events in the saved trace to confirm execution. For a topic-reader comparison,
pass an override containing only `retrieval: {mode: topic}` to retain the same
evaluation model. See [搜索功能演进与效果对比](../experiments/search-feature-comparison.md)
for the feature-level comparison, repeated-run results and current retained fixes.

## Output, cache and recovery

The combined report is `output/search-eval/<task-id>/output.json`.
Use `--output path.json` to choose another report path. Raw search artifacts and
checkpoints are preserved. Repeating a command reuses completed work; changing
only evaluation mode/scope does not change search identity. Changing search
code/config creates a new search run. `--fresh` explicitly starts another trial.

Validated labels are cached by task, rubric, model policy, exact unit text and
attribution context under `output/search-eval/judge-cache`. Batch order and
unrelated document edits do not invalidate unchanged units. Changed text,
context or rubric does invalidate them. Valid rows survive failed batches;
only unresolved rows are retried. API failures have a separate bounded retry
budget. No cache value can bypass quote/schema validation.

This release uses `search-eval-2` judgments with atomic questions. Old broad
rubrics are left on disk but not reused as atomic-fact judgments.

## Repeated runs

Keep the task, code, model and search configuration fixed, and start an independent
trial with `--fresh`:

```bash
python -m finmy.search.eval \
  --task examples/search_eval/buffett_goldman.json \
  --eval_mode manual --fresh
```

`--fresh` creates a new task ID with a random suffix and preserves previous runs.
Keep each printed output path with its run number. Every `--fresh` invocation
starts another trial. An ordinary invocation without it continues or reuses the
deterministic task ID for the same task, configuration and code.

Compare effective task/configuration and code identity in the saved reports.
Keep the same fact questions and evidence-family grouping, distinguish partial
from complete support, and show every run alongside the per-run arithmetic mean.
Record model cost separately from provider/read wait time. Name versions by their
features; keep code identifiers in the saved artifacts for reproducibility.

The manual feature-comparison table scores deduplicated delivered evidence in a
shared pool of 31 original-evidence groups and 20 fixed facts. If the pool grows,
recompute all historical rows with the same denominator. These delivery metrics
are separate from the automatic Judge/provider metrics below.

## Metrics

- Atomic fact coverage: each question asks one fact. Requested dates, individual
  actions, explicitly named documents and completion versus planning are assessed
  separately. Unsupported/conflicting facts remain visible.
- Useful/direct-evidence character fractions: **unit-level** grade weighted by
  selected characters; these do not claim every character is evidentiary.
- `exact_support_quote_char_fraction`: actual validated quote spans divided by
  delivered body characters. Overlapping quote spans count once. This measures
  cited-text density, not semantic completeness.
- Topic mismatch: wrong entity/person, event, attribute or explicit scope.
- `pool` only: quote recall within the saved pool and Precision/Recall/nDCG/AP/
  reciprocal rank/hit rate at 1, 3, 5, 10 for actual provider lists. Unknown source
  bodies yield null ranking metrics. Short lists are padded with misses.

Question coverage is not exhaustive world knowledge; quote recall is not unique
fact recall. Keep task/rubric and comparison pool fixed for controlled comparisons.
The Judge sees originals/context, never search ranks or selection flags.

## Search changes and compatibility

- Provider length limits are local: whitespace compaction for Baidu;
  if still too long, record `skipped_length` and keep full queries for other
  providers. No name, number, negation or quoted phrase is truncated. A shorter
  Baidu-specific variant can still be supplied when that provider is needed.
- Query reads locate explicit contract aliases and local attribution, return
  matching original spans before peripheral context, and expose exact continuation
  locations. Weak lexical candidates are labeled as hints, not verified evidence.
- Final body delivery uses validated, previously read priority spans. The prompt
  asks for focal-person statements, conditions and execution status; retrieval
  hits alone do not select evidence. New-fact `context` marks may be retained,
  and new prose annotations may complete sentences inside the same read block.
  See [passage selection](search-retrieval-selection.md) for the exact rules.
- Finish records atomic `fact_checks` and `source_lead_decisions`. Explicitly
  unresolved leads or planned/missing/conflicting requested facts prevent a
  `supported` stop. A future announcement must not be presented as completed fact.
  Semantic status remains a model assessment, not a claim of programmatic proof.
- New tasks use `entity_attribute_windows_v2`; saved v1 plans retain their old
  selection behavior. Read budgets, checkpoint accounting and Builder topology
  are not reduced or replaced.

Offline checks:

```bash
python -m pytest -q tests/test_search_eval.py tests/test_search_topic.py tests/test_search_improvements.py
```
