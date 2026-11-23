# Passage retrieval and evidence selection

Based on `person-epg-yuntao-search` at `8bca5d8`, with marginal-value selection.
There is no material-length target.

## Defaults and separate comparisons

`retrieval: {}` keeps the existing `topic` reader, including its lexical ranking.
The optional `bm25` mode ranks saved original windows directly. Both modes run
locally without additional model calls or model weights. Retrieval scores do not
create delivery marks automatically. Web providers and source acquisition are
unchanged.

An opt-in JSON config, passed to the existing `--config` argument:

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
support span, or marked as a specific condition. Standalone `context` background
adds no evidence value. Marks without these new annotations remain supported:
unique original text is retained without inventing semantic equivalence. Exact
reposts are deduplicated unless an explicit independent corroboration adds value.

All original files, versions, hashes, marks and omitted ranges remain intact.
`selection.json` records marginal gains, new facts, and `retained`, `redundant` or
`material_limit` decisions. Retained text always comes from original coordinates.

## Frozen-source comparison

Use independently reviewed case labels against fixed source versions:

```json
[
  {
    "source_id": "saved-source-id",
    "version": "saved-version-sha256",
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
python -m pytest -q tests/test_search_retrieval.py tests/test_search_coverage.py
```
