# Cross-source evidence consolidation

Apply `person-event-v2-evidence-semantic-merge-incremental.patch` **after**
`person-event-v2-transport-guard-resume-incremental.patch`. The stall120/partial-output
patch is not part of this baseline or this patch. Existing timeout, stall timeout,
reasoning effort, concurrency, read-round and minute-progress settings are retained.

## Run on an existing result

Stop the old process. Keep `RUN` pointing at its output directory, which already
contains `state.json` and the original `input.json`. No replacement input is needed.

```bash
git apply --check person-event-v2-evidence-semantic-merge-incremental.patch
git apply person-event-v2-evidence-semantic-merge-incremental.patch

# Stage 1: inspect the candidate plan; no API calls or file mutations.
python -m finmy.person_epg.event.evidence_consolidation "$RUN" --plan

# Stage 2: only review/merge existing evidence, then save JSON/checks/HTML.
python -m dotenv -f .env run -- \
  python -m finmy.person_epg.event.evidence_consolidation "$RUN" \
  --allow-model --extra-calls 30
```

The second command does not repeat extraction, fact consolidation, organization
or relations. It reads the current graph and facts, preserves the immutable input
and previous attempt files, and writes another attempt in the same run directory.
`--extra-calls 30` raises the cumulative call ceiling to at least `calls_spent + 30`;
it grants headroom, not an instruction to send 30 requests. Repeating this command
resumes the same evidence-review input, reuses successful response checkpoints,
and preserves merges from successful batches if another batch fails. A fully
completed review reuses its stage checkpoint without model calls.

An explicit implementation upgrade backs up state and records the new execution
code identity. Existing code namespaces/checkpoints remain available. This command
adds only the final evidence review to the saved result; it does not claim that
old unresolved upstream tasks or incomplete source coverage have been repaired.
A previously partial result can therefore remain partial after successful merging.

## Inspect the JSON, sources and HTML

```bash
python - "$RUN" <<'PY'
import json, sys
from collections import Counter
from pathlib import Path
root = Path(sys.argv[1])
state = json.loads((root / 'state.json').read_text())
graph = json.loads((root / state['output']).read_text())
report = json.loads((root / state['evidence_consolidation']['path']).read_text())
print({k: report[k] for k in ('candidate_pairs', 'reviewed_pairs', 'merged_records',
                             'multi_source_before', 'multi_source_after', 'failed_tasks')})
print('Different sources per evidence:', dict(Counter(
    len({c['source_id'] for c in e['citations']}) for e in graph['evidence'])))
for evidence in graph['evidence']:
    sources = sorted({c['source_id'] for c in evidence['citations']})
    if len(sources) > 1:
        print(evidence['evidence_id'], sources, evidence['statement'])
print('JSON:', root / state['output'])
print('Checks:', root / state['checks'])
print('HTML:', root / state['visualization']['output'])
PY
```

Open the printed HTML path. It is the existing event process diagram, despite its
`gantt.html` filename. Source cards are rebuilt from the merged graph. One canonical
evidence ID can now appear under two or more source cards, each with that source's
unchanged quotation. The original source IDs, sample IDs, text, offsets and hashes
are retained; no model-written replacement quotation is accepted.

## Implementation

The ordinary `run_event` pipeline runs this stage after relations and final repair.
`relation_experiment run` also invokes it after relations. A prepare-only run still
stops after organization, so its subsequent relation run includes the new stage.

Candidate selection starts with reverse context/action/phase/relation support
links, supplemented by lexical neighbors. Each evidence selects up to four
neighbors; only cross-source pairs are considered. This is bounded retrieval, not
an exhaustive equivalence search. The plan is saved in
`evidence-consolidation-plan.json`. Batches contain at most 32 pairs and are also
bounded by request characters; full candidate statements and quotations are kept.
For the supplied 107-evidence graph, the selector yields 216 pairs in 9 batches.

The existing FIFO scheduler runs the batches concurrently using the saved worker
limit. The model must judge every assigned pair as `same_fact`, `different_fact`
or `uncertain`, with a reason. Identical strings are not required. Merely sharing
a context, date or company never causes a merge. Complete input records are
supplied; this stage does not issue reading follow-ups. Format corrections and
transport failures use the existing bounded retry mechanisms and global budget.

The program merges only positively reviewed equivalents, blocks explicit
contradictory equivalence chains, chooses a deterministic surviving ID, retains its
statement, unions original citations and rewrites typed evidence references in
both graph and facts. Duplicate IDs in support lists are removed. It validates
original citation offsets/hashes and rejects new validation errors before adoption.
The facts lineage and `evidence-consolidation.json` retain the old-to-new mapping;
final checks and relation-review projections use canonical IDs while historical
adoption records remain unchanged. This is a new execution stage, not a new graph
schema layer. The model's semantic judgments still require content review.

## Verification performed

Offline tests cover semantic pair acceptance, different/uncertain cases,
contradictory transitive merges, invalid IDs, forbidden read requests, quotation
validation, typed-reference rewriting, original-input preservation, diagram
serialization, independent batch failure and budget/resume checkpoint reuse.

An additional offline test used the supplied 107-evidence HTML and unchanged
19-document input (SHA-256
`ef910ea7c1905fa0e2d9f2774e5b6dd66832ea54273597fee04b80138ba5771f`).
With one explicitly authored equivalence decision about Buffett's praise of
Goldman, it produced 106 evidence records, one with two distinct sources, zero
graph validation errors, and both source cards referencing that same evidence ID.
This verifies merging/rendering on the real data; it is not a live Kimi semantic
quality evaluation. No live provider request was made.
