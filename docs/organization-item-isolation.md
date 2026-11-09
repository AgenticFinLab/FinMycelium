# Item isolation and organization checkpoint reuse

This patch targets the code recorded in `build_output_20261109202959165078`,
including the previously applied summary/resume patch. The two organization
modules in that run predate the detail-catalog integration; this patch includes
that integration and aggregated diagnostics as well. The production base files
were checked against the run manifest's SHA-256 values.

## Relevance failures no longer discard the whole draft

Relevance output is separated into occurrence explanations, proposed background
activities and out-of-phase Activity assignments. All out-of-phase assignments
are saved together in `PersonOrganizationIsolation-Result.json`, alongside their
existing assignments. They do not overwrite assignments already accepted in the
Assignments phase. Differences remain explicit deferred proposals, not silently
merged edits. All original actions, transactions and details stay in the graph.

Valid occurrence explanations and background memberships continue immediately.
Unknown IDs, invalid background placements and conflicting variants are isolated
individually. Duplicate identical rows are deduplicated. Missing or conflicting
occurrence explanations receive one targeted repair call for those IDs only;
later batches still run. A failed repair leaves an explicit English
`Person relevance review pending.` marker. This is execution metadata with no
fabricated supporting quotation or personal-involvement claim. The native schema
does not change. Pending IDs are listed in the private organization plan,
`PersonOrganizationReport.json` and `PersonAcceptance.json`, whose status becomes
`partial_organization_requires_review`. All other validated facts remain usable.

Errors still requiring correction, such as unknown assignment references, report
all violations in one diagnostic instead of reporting only the first row.
This change does not treat unvalidated layouts, malformed facts or failed disk
writes as successful reconstruction.

## Resume without redoing accepted phases

The existing recovery entry now reuses complete saved organization replies after
checking that their source facts, subject, layout, assigned IDs and relevant
context match the current request. Current validators run again. Derived detail
catalogs omitted by older code are recomputed. Truncated replies are not reused.
A complete previously rejected relevance reply can be reused after item isolation.
`PersonOrganizationReuse-Result.json` records the source trace, request/result
hashes and original call status. Reuse does not create fictitious model calls.

```bash
git apply --check FinMycelium_PR18_organization_isolation_fix.patch
git apply FinMycelium_PR18_organization_isolation_fix.patch

python -m finmy.runner.sparse_person_recovery \
  --source-run EXPERIMENT/uTEST/Pipline/build_output_20261109202959165078 \
  --config configs/search_pipeline.yml \
  --output-root EXPERIMENT/uTEST/Pipline \
  --env-file .env \
  --execute
```

No YAML changes are needed. Output goes to a new `build_output_*` directory.
Search, extraction, the completed summary and saved fact repair are reused.
Historical calls still count toward the original budget.

## Independent exports

Native `FinalPersonEPG.json` and `FinalPersonEPG.html` are generated from the
validated person graph independently of the older subject-graph projection.
If that projection rejects an interval, `SubjectProjectionStatus.json` records
the failure and the native graph/HTML remain available. No invalid legacy graph
is emitted, and the original factual timestamps are not rewritten to appease
the older view. Strict native replay supports this recorded export outcome.

## Verification

The regression fixture contains the actual first rejected Relevance-003 response:
all 15 out-of-phase ordinary memberships are isolated at once, while all five
occurrence explanations and the valid background membership remain accepted.
Tests also cover missing/conflicting relevance, targeted repair, timeout followed
by later batches, aggregate diagnostics, cache invalidation, failed legacy export
and strict native replay.

An offline recovery of the supplied full checkpoint reused nine accepted batches
and revalidated the previously rejected third relevance batch, then completed with
nine model-substitute calls for the remaining phases. It preserved the source
directory, extracted 31 episodes/16 stages and the 82 existing activities; one
accepted background activity was added. Native HTML generation and strict replay
passed. No live DeepSeek calls were made during verification.
