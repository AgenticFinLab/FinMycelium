# Build from local evidence

Run from the repository root in an environment with `requirements.txt` installed.
This entry uses prepared source text directly: no search, collector, summarizer,
database, PDF service or web UI is started. Only the chosen model provider's key
is needed for execution; offline preflight and replay need no key.

## Choose a builder

| Configuration | Builder | Behavior |
|---|---|---|
| `configs/build_only_agent.yml` | Original AgentEventBuilder | `75be1f9` prompts, role order, parsing and assembly; single-call API adapter |
| `configs/build_only_sparse.yml` | Repaired SparseRagBuilder | Sparse routing, role validation and bounded JSON retries; additional context assets disabled |

Both examples select `ark/doubao-seed-2-0-pro-260215`, with a 12,288-token
per-call output cap, temperature 0.2 and top-p 0.95. They do not explicitly set
a thinking mode. Provider availability and supported parameters must be verified
for your account. Change `lm_name` and `generation_config` together if switching
models. Per-role model overrides are not supported.

Each example allows at most 40 model requests and sets a 900-second SDK timeout
per request, with SDK retries disabled. This is not a whole-run deadline or an
exact token/currency budget. Input tokens also count toward cost. The original
adapter does not retry; the sparse builder allows up to three attempts per role
output, all counted against the same 40-request cap. Larger events may need a
higher cap, chosen before execution.

## Prepare the input

Use the shape in [`examples/sparse_input.json`](../../examples/sparse_input.json):

- `user_query`: `user_query_id`, `query_text`, `key_words`, optional `extras`.
- `samples`: a nonempty list with unique `sample_id`, nonempty `raw_data_id` and
  full `content` for each source. Optional source metadata can go in
  `user_query.extras.source_registry`, keyed by `raw_data_id`.

Top-level keys must be exactly `user_query` and `samples`. The example contains
fictional evidence, not an external event. Reuse the same input file for a
two-builder comparison; do not shorten the evidence between runs.

## Preflight and execute

Offline checks, with no model calls or run directories created:

```bash
python -m finmy.runner.build_only_runner --config configs/build_only_agent.yml --input examples/sparse_input.json
python -m finmy.runner.build_only_runner --config configs/build_only_sparse.yml --input examples/sparse_input.json
```

For an actual build, configure `ARK_API_KEY` in your local environment or `.env`,
then explicitly add `--execute`. Existing environment variables take precedence
over `--env-file`. Credentials must not be placed in YAML or input JSON.

```bash
python -m finmy.runner.build_only_runner --config configs/build_only_agent.yml --input /path/to/input.json --env-file .env --execute --gantt
python -m finmy.runner.build_only_runner --config configs/build_only_sparse.yml --input /path/to/input.json --env-file .env --execute --gantt
```

`--gantt` is optional. A rendering failure is recorded in `GanttStatus.json` and
does not invalidate a completed JSON build. Failed builds exit nonzero. There
is no implicit resume or automatic restart of a failed run.

## Outputs and replay

Through this entry, both builders return `BuildOutput.event_cascades` and save
`FinalEventCascade.json`. On success, `BuildOutput.extras` includes:

| Field | Meaning |
|---|---|
| `builder_type` | `AgentEventBuilder` or `SparseRagBuilder` |
| `run_directory` | The builder's output directory |
| `elapsed_seconds` | Construction time from `RunManifest.json`, excluding optional Gantt rendering |
| `usage` | The same call/token summary as `RunManifest.json`; unknown usage remains null |

Both methods save `BuildInput.json`, `RunManifest.json` and `CallLedger.json`.
Method-specific extras and diagnostic files are optional for consumers. Internal
role filenames and `result` state are not a shared interface. `completed` means
construction completed under the selected method's checks, not that both methods
passed identical structural or semantic review. Graph content is not normalized
or rewritten by the adapter.

For Python callers, use `select_builder` from this entry to obtain the selected
implementation. The original class and the full pipeline registry are unchanged;
direct calls to the original class do not acquire the build-only adapter's metadata.
Historical sparse manifests without `builder_type` remain supported for replay.

Each execution has its own directory under `output/build-only/agent/` or
`output/build-only/sparse/`. `RunManifest.json` records inputs/configuration/code
hashes, status, total elapsed time, token accounting and per-role costs. Missing
usage stays `null`, with known subtotals reported separately. Raw responses and
role results are retained locally; they contain the supplied evidence and must
be reviewed before sharing. `output/` is Git-ignored.

- Original: `BuildInput.json`, `CallLedger.json`, `request-*.json`,
  `response-*.json`, role traces, `FinalEventCascade.json` and
  `IntegratedEventCascade.json`.
- Sparse: `BuildInput.json`, role request/response/result traces,
  `ParticipantIdentityMap.json`, `ConstructionCheck.json`, `EvidenceCheck.json`,
  `QualityReview.json`, `AcceptanceDecision.json`, `CandidateEventCascade.json`,
  and `FinalEventCascade.json` when the configured quote policy permits it.

The assembled candidate is retained before final validation, including on a quote
gate failure. It is not an approved graph. Evidence contract v2 locates quotes in
unchanged sources by exact text or whitespace-only normalization and records
sample IDs, source SHA-256, original excerpts and zero-based, end-exclusive Unicode
character offsets. Punctuation, casing, ellipses and paraphrases are not normalized.
Within each source, exact matches take precedence; whitespace-only locations are
used when no exact match exists. Multiple returned locations are retained rather
than silently choosing one.
Query/keyword citations are marked separately and do not count as source support.

`QualityReview.json` lists conservative English-language review candidates for
payment state, dates, relation endpoints and uncited source paragraphs. Aliases,
pronouns and irrelevant paragraphs can cause false positives. This is neither
semantic approval nor a factual coverage score, and it does not rewrite the graph.
Missing quotations are reported separately; the existing strict policy rejects
unlocatable supplied quotes, not every field without a quote. An accepted draft
still requires content review, even if no heuristic issue is found.

Sparse construction contract v2 reuses Participant and Transaction outputs
unchanged. Episode generates relations/descriptions and references those arrays
by exact placeholders. Downstream prompts use value-only projections, retaining
the complete source text and all original role results in the saved artifacts.
Canonical participant ID/name/type bindings are checked across episodes; roles
may change. Known action/transaction dates must overlap their target episode's
checked time window. Coarse dates retain their precision; unknown/unparsed dates
are reported as unchecked, not silently converted to exact timestamps.

`ConstructionCheck.json` records identity bindings, time checks and repeated-action
candidates. It is a structural diagnostic, not an entailment or alias-resolution
oracle. Narrative scope, relation direction and ambiguous identities still need
content review. Old sparse runs without the v2 marker retain their original
replay contract; they are not retroactively certified by the new checks.

Verify stored artifacts and reassemble without model calls:

```bash
python -m finmy.runner.build_only_runner --replay /path/to/build_output_directory
```

Replay reads the recorded builder identity; older sparse manifests without that
field remain supported. It requires a completed run and rejects changed or
missing artifacts and a mismatch with the saved final graph. It does not resume
construction or certify factual quality.

The sparse examples use `evidence_policy: report`: unmatched quotations are
recorded without blocking draft output or triggering extra model calls. The
generation workflow reuses role results and compact context, with prompts for
source quotations, fact status and process coverage. Local source anchoring and
quality diagnostics remain available. Invalid structure, identity references,
or execution integrity still fail their respective checks.

Set `evidence_policy: strict` to opt into blocking quotations absent from the
input after traceable whitespace normalization. Quote presence alone does not
establish semantic support or correct action/time attribution. In either mode,
`FinalEventCascade.json` is the completed draft, not a human-approved dataset EPG.
The original adapter leaves its graph parsing and quality behavior unchanged.

The adapter is opt-in through this entry (or `BuildOnlyAgentEventBuilder` in
Python); it does not replace the original builder in the full pipeline registry.
