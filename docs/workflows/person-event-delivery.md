# Evidence delivery

Base: PR #25 `4df5d0a` with `person-event-pr25-engineering-incremental.patch` applied.
The earlier delivery patch is not required.

Evidence merging now applies every `same_fact` connected component. Conflicting
`different_fact` / `uncertain` edges are recorded without blocking that component.
Pairs with no `same_fact` path remain separate. Original statements and citations
are retained even if citation verification or post-merge checks fail. This is the
default; there is no mode switch. `checks.json` still reports validation findings,
and the saved result can remain `partial`. Offline HTML regeneration also records
validation findings instead of rejecting the draft.

Replay completed evidence review checkpoints, without any model requests:

```bash
python -m finmy.person_epg.event.evidence_consolidation "$RUN" --saved-review-only
```

This creates another attempt using the saved unmerged postprocess input, if present.
If the latest attempt has no usable output, export from a specific earlier evidence
postprocess attempt to a separate directory:

```bash
python -m finmy.person_epg.event.deliver_evidence "$RUN/attempts/0004" --output output/evidence-delivery
```

Use the attempt containing `evidence-postprocess-input.json`. This exports
`epg.json`, `facts.json`, `evidence-consolidation.json`, and `graph.html` without
changing the experiment state. Missing paid review checkpoints are reported;
no new model calls are made. JSON syntax, review response IDs, file hashes and
checkpoint integrity remain required to load and replay the actual saved data.
