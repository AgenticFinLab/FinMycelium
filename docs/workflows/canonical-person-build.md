# Evidence-first person construction

Person mode now uses one factual lifecycle:

1. Import saved facts, or extract evidence-bound occurrences from the supplied sources.
2. Reconcile factual identity, transfer recipients and occurrence membership.
3. Place canonical activities into events, allowing several events to reference one activity.
4. Derive stages and event summaries from confirmed memberships.
5. Generate supported relations and a short overview; export the existing Person EPG JSON and HTML.

The single-event builder remains available in event mode. Person mode no longer runs the seven-role EventCascade extraction followed by a separate coverage expansion and late full-graph fact repair. `FinalEventCascade.json`, when representable, is a derived compatibility export.

## Apply to the previously patched PR #18 checkout

This is a normal Git diff for a checkout with the preceding organization-isolation and missing-dependency fixes already applied. It is not a mail-format patch.

```bash
git apply --check FinMycelium_PR18_person_canonical_flow.patch
git apply FinMycelium_PR18_person_canonical_flow.patch
```

## Reuse the latest saved run without searching again

Run from the repository root:

```bash
python -m finmy.runner.sparse_person_recovery \
  --source-run EXPERIMENT/uTEST/Pipline/build_output_20261109205319998425 \
  --config configs/search_pipeline.yml \
  --output-root EXPERIMENT/uTEST/Pipline/reorganized \
  --env-file .env \
  --reorganize \
  --execute
```

The source can be a completed draft or a failed build with reusable facts. The command imports `FinalPersonEPG.json` when present, otherwise the verified extraction checkpoint. It does not search, parse URLs, or rerun the old extraction chain. It does make model calls for unresolved factual reconciliation and the new organization. `--reorganize` invalidates saved organization responses, not accepted canonical facts. Subsequent continuation can omit it to reuse unaffected organization work.

Output goes into a new `build_output_*` directory under the requested output root. The CLI prints `run_directory` and the actual `html` path. Open `FinalPersonEPG.html` there. Omit `--execute` for an offline preflight only. Omit `--env-file` if credentials are already in the environment. Existing YAML remains accepted; the obsolete `person_coverage_repair` and `person_fact_repair` options no longer select separate post-processing passes.

To verify a completed output without any model calls:

```bash
python -m finmy.runner.build_only_runner --replay PATH_TO_NEW_BUILD_OUTPUT
```

## Checkpoints and local failures

`PersonCanonicalFacts.json` stores the factual package; `PersonCanonicalAudit.json` records source coverage, item decisions, unresolved work and content hashes. A checkpoint is complete only when its phase and status are both completed and its inputs and package hashes match. Unfinished source chunks and unresolved items remain resumable. Historical calls are retained separately; `--max-new-calls` optionally sets the new continuation's call budget.

Organization responses depend on the current facts, semantic instructions and phase version. A changed fact invalidates affected descendants. An invalid activity selection, relation, or summary is recorded locally; it does not remove unrelated accepted facts. Whole-provider failure or the absence of any usable facts can still leave an incomplete run, with its reusable checkpoint saved.

`EventSummaryStatus.json`, `PersonAcceptance.json` and `PersonOrganizationIsolation-Result.json` distinguish completed execution, pending work and summary fallback. Native JSON/HTML and the stricter compatibility export have independent outcomes. Successful rendering does not certify semantic correctness.

The offline regression cases include repeated financial reports, historical actions mentioned at later meetings, separate Activision holdings/disclosure scenes, recipient-specific charitable transfers, cross-event fact reuse, relation direction, interrupted checkpoints and partial model responses. They validate implementation behavior using saved evidence and controlled responses; they do not substitute for inspecting a real provider run.
