# Passage retrieval and evidence selection

Based on `person-epg-yuntao-search` at `8bca5d8`. The marked-span delivery fix
is already present in that commit; this change adds optional retrieval stages
and marginal-value selection. There is no material-length target.

## Defaults and separate comparisons

The existing task format and search command continue to work. `retrieval` is an
optional `SearchConfig` dictionary. Its default mode is `topic`, which keeps the
existing topic reader and makes no embedding or rerank calls. Validate task scope,
original windows and baseline selection before opting into the extra stages.

| Mode | Passage candidates | Extra model work |
|---|---|---|
| `topic` | Existing entity/attribute reader | None |
| `bm25` | BM25 over original windows | None |
| `hybrid` | BM25 + local dense retrieval, reciprocal-rank fusion | Local embeddings |
| `bm25_rerank` | BM25 then evidence reranking | Existing search LLM |
| `hybrid_rerank` | Fused candidates then evidence reranking | Local embeddings + search LLM |

This operates inside saved-source reading; web providers, source acquisition and
Builder execution are unchanged. Numbers, dates and names remain in the lexical
index. Dense results are not subjected to the old literal-entity gate, so indirect
wording can reach the reader. Neither retrieval scores nor reranker labels create
priority marks automatically.

An opt-in JSON config, passed to the existing `--config` argument:

```json
{
  "retrieval": {
    "mode": "hybrid_rerank",
    "embedding_model_path": "/absolute/path/to/local-sentence-transformer",
    "device": "cpu",
    "query_prefix": "",
    "passage_prefix": "",
    "top_k": 24,
    "window_chars": 1600,
    "embedding_batch_size": 32,
    "rerank_batch_size": 8
  }
}
```

Install the optional `sentence-transformers` package and supply local weights.
No weights are downloaded by this implementation. Configure query/passage prefixes
for the chosen encoder if it requires them. The API used is documented at
https://sbert.net/docs/package_reference/sentence_transformer/model.html .
`top_k` is per recall channel, not a final material quota. The union is reranked.
The encoder uses CPU by default to avoid unexpectedly taking the training GPU.
Missing weights/dependencies and malformed model responses fail explicitly.

Reranking uses the existing `lm_name`, generation configuration, network switch
and model-call budget. Finalization calls remain reserved. Successfully validated
batches are cached separately from evaluation judgments. Failed calls still count;
unjudged candidates remain unknown if the reserve is reached. Reranking checks
entity **and event** identity, requested attributes and direct evidence. Affirmative
mismatches require quoted original support; missing information is retained.

Caches bind to input/model identity; original source versions/coordinates identify
candidates. Embedding cache identity includes the local model directory's file
sizes and modification times. Replace weights normally (do not preserve all file
metadata when modifying bytes). If manually modifying weights in place, remove the
trial's embedding cache. Only validated cache records are reused.

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

After baseline validation, explicitly compare the costly variants:

```bash
python -m finmy.search.retrieval_eval \
  --run-dir output/search-eval/TASK/runs/initial \
  --cases cases.json --config hybrid-config.json \
  --modes bm25 hybrid bm25_rerank hybrid_rerank --output comparison.json
```

The comparison does not rerun web searches or alter the original run. Each variant
has its own checkpoint/caches next to the report. Reports include original returned
ranges, labeled-evidence character recall, delivered characters, local embedding
time, and reranker calls/tokens. This is recall against supplied range labels, not
whole-web recall or overall precision. Labels must be independent of the selector;
synthetic unit fixtures demonstrate mechanics, not real embedding-model gains.
Keep the encoder, source versions, labels and read limit fixed across variants.

Offline tests:

```bash
python -m pytest -q tests/test_search_hybrid.py tests/test_search_coverage.py
```
