# Passage retrieval and evidence selection

Evidence delivery combines validated original spans with coverage-aware selection.
The material budget is an upper limit; unused budget may remain.

## Defaults and separate comparisons

The repository profile in `configs/search.yml` enables `retrieval: {mode: bm25}`.
The search-evaluation CLI loads that profile by default while retaining its Kimi
model and generation settings. BM25 ranks passages within a saved source; the
research agent still decides which sources to read and which originals to mark.

`retrieval: {}` or `{mode: topic}` selects the existing topic reader, including
its lexical ranking. A directly constructed `SearchConfig()` still defaults to
the topic reader unless configured. Both readers run locally without additional
model calls or model weights. Retrieval scores do not create delivery marks
automatically. Web providers and source acquisition are unchanged.

Optional BM25 settings, passed to the existing `--config` argument:

```json
{
  "retrieval": {
    "mode": "bm25",
    "top_k": 24,
    "window_chars": 1600
  }
}
```

`top_k` limits passage candidates, not final material length. The accepted options
are `mode`, `top_k` and `window_chars`. Removed retrieval modes and model options
are rejected explicitly. Existing `topic`, `bm25` and empty-config checkpoints
remain resumable with their saved configuration.

Feature-level results and the decision to retain default BM25 are recorded in
[搜索功能演进与效果对比](../experiments/search-feature-comparison.md).

## Baidu and Bocha original bodies

Baidu `content` is stored as a partial original. Bocha `summary` and provider
snippets remain leads. For Baidu/Bocha results without a saved body, search now
fetches the original URL once and caches its parsed text before source selection.
Up to three URLs download concurrently, using the existing 20-second acquisition
timeout (or a shorter configured timeout); saved bodies and failed discovery downloads are reused across searches
and resume. Downloads add HTTP work, not model or search-provider calls.

Search feedback returns source IDs and provider results. Sources remain selectable
through their titles and discovery leads; cached bodies are inspected with `read_source`.
Fetching does not mark a body read. All-provider body previews have been removed,
including from model context when resuming older checkpoints.
The existing `read_source` action inspects the cached text; ordinary original-range
marks then enter the existing delivery selector. Failed downloads keep their leads
and acquisition errors visible. Search summaries never become original evidence.

The later claim-ID checks, incremental fact ledger, mandatory followup return and
checked-subrange selection have been removed. BM25, budgets and the earlier
selection/finish behavior are retained. No new review stage is introduced.

## Metadata and time

Optional `task.retrieval_constraints` and original document/block
`evidence_scope` metadata can specify `entity_id`, `event_id`, `activity_start`
and `activity_end`. IDs are compared only when both sides are explicitly supplied.
Activity intervals filter only when both endpoints are known and non-overlapping.
These fields are never inferred from names, URLs or publication years. An absent
or ambiguous value does not reject a candidate.

Publication is separate: only the user's explicit `publication_start` and
`publication_end` settings filter known publication dates. An activity window of
2008–2013 permits a 2025 retrospective. Existing publication conflicts remain
unknown rather than selecting an arbitrary provider's date.

## Final evidence selection

Delivery still starts exclusively from validated, previously read priority spans.
Optional mark annotations support coverage-aware choice:

```json
{
  "source_id": "runtime-id",
  "block": 3,
  "start": 0,
  "end": 220,
  "reason": "Original completion statement and its condition",
  "fact_ids": ["settlement-completion"],
  "claim_id": "delivered-on-confirmed-date",
  "evidence_role": "outcome"
}
```

Allowed roles: `terms`, `personal`, `condition`, `outcome`, `corroboration`,
`contradiction`, `context`. Equivalent claims share a `claim_id`; planned versus
completed actions, different conditions, dates or opposing statements do not.
An independently verified corroboration may include `independence_key` naming the
original evidence origin. Reprints share one key; different URLs alone do not
establish independence. These annotations remain model advice, not source facts.

Selection recalculates marginal value after every retained mark. New fact coverage
has weight 4, new claims and evidence roles 2, new independent corroboration and
numerical/negation qualifications 1. Cost only decides whether a span fits and
breaks equal-value ties. There is no target length, source quota or filler phase.
The selector stops when nothing with positive value fits. Equivalent descriptions
lose priority; personal statements, conditions, opposing claims and independent
origins can still add value for an already-covered fact. Numeric/date/negation
changes survive even if a model reuses a claim ID incorrectly.

Necessary attribution, dates and qualifications must be included inside the marked
support span, or marked as a specific condition. A `context` mark can earn value
for `fact_ids` not yet covered by selected evidence. Pure background and context
whose facts are already covered add no value; existing duplicate checks still apply.
Marks without semantic annotations remain supported: unique original text is
retained without inventing semantic equivalence. Exact
reposts are deduplicated unless an explicit independent corroboration adds value.

All original files, versions, hashes, marks and omitted ranges remain intact.
`selection.json` records marginal gains, new facts, and `retained`, `redundant` or
`material_limit` decisions. Retained text always comes from original coordinates.

## Read coverage and sentence boundaries

The existing `read_evidence` preview contains only previously read text and adds
`mark_status: marked|partial|unmarked`, calculated from marks in the same source
version. It uses the existing preview budget. The prompt asks the agent to check
all returned spans and add missing useful marks in its next action, including
finish; an unmarked excerpt may still be irrelevant. This adds no model stage
and does not automatically select background or schedule another read.

New annotations may expand clipped prose to closed sentence boundaries inside
the same source block. Each extension must be fully covered by existing reads in
that version. Blank lines delimit paragraphs; tables and unfinished source
tails are not completed by this rule. Saved marks and frozen handoffs keep their
exact coordinates. A repeated mark is matched against its original and aligned
coordinates to avoid retaining both copies.

Alignment preserves the source wording. It does not correct a relevance mistake:
an endpoint already inside company boilerplate may include the rest of that
sentence. The agent still chooses the supporting passage. These checks are local
and introduce no model calls or additional search requests.

## Frozen-source comparison

Use independently reviewed case labels against fixed source versions:

```json
[
  {
    "source_id": "saved-source-id",
    "version": "saved-source-version",
    "query": "What confirms completed delivery?",
    "expected_ranges": [{"block": 12, "start": 0, "end": 240}]
  }
]
```

Run the zero-extra-model baseline first:

```bash
python -m finmy.search.retrieval_eval \
  --run-dir output/search-eval/TASK/runs/initial \
  --cases cases.json --modes topic bm25 --output baseline.json
```

The comparison does not rerun web searches or alter the original run. Each mode
has its own checkpoint next to the report. Reports include original returned
ranges, labeled-evidence character recall and delivered characters. This is recall
against supplied range labels, not whole-web recall or overall precision. Keep the
source versions, labels and read limit fixed across modes.

Offline tests:

```bash
python -m pytest -q tests/test_search_retrieval.py tests/test_search_coverage.py \
  tests/test_search_passage_boundaries.py tests/test_search_evidence_selection.py
```
