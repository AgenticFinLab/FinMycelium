# Concise event overview and person checkpoint resume

Apply this incremental patch after
`FinMycelium_PR18_coverage_reconciliation_fix.patch`, using `git apply`.
No YAML changes or additional dependencies are required.

## Behavior

The final `EventDescriptionReconstructor` receives completed stage overviews
and their quotations found in the input sources. It writes a short overview,
not another list of all actions and transactions. Detailed facts remain in the
episodes and the person activity tables; this change does not impose a fact,
episode, stage or source quota.

An incomplete, empty, invalid or unavailable overview falls back to the first
nonempty description from each completed stage, with duplicate values removed.
The copied fields keep their evidence, reasons and confidence unchanged. If
stage descriptions are empty, the top-level descriptions can be empty; detailed
facts still remain. Truncated model text is never used. Existing graph/evidence
validation and person organization still run normally.

`EventSummaryStatus.json`, `RunManifest.json.event_summary` and output metadata
record the fallback as `status: degraded`, its error type, source fields and
result hash. The model-call ledger retains the actual failed call; no successful
call is invented for the deterministic fallback. Interrupts and checkpoint write
failures are not treated as usable model outputs.

## Resume this failed run

Run from the repository root after applying the patch:

```bash
python -m finmy.runner.sparse_person_recovery \
  --source-run EXPERIMENT/uTEST/Pipline/build_output_20261109195713163015 \
  --config configs/search_pipeline.yml \
  --output-root EXPERIMENT/uTEST/Pipline \
  --env-file .env \
  --execute
```

Omit `--execute` for an offline checkpoint/preflight check. Recovery restores
the original subject, source texts, model, language and budgets from the saved
manifest; the YAML supplies agent defaults and the output location. It creates
a new `build_output_*` directory, leaving the failed run unchanged. The console
prints the new path. A successful person run includes `FinalPersonEPG.json`,
`FinalPersonEPG.html` and the compatible subject projection.

Supported checkpoints are failed person runs with either:

- all extraction roles and stage descriptions complete, but no accepted final
  event overview; or
- a validated `FinalEventCascade.json`, with person completion still pending.

In the first case only the overview and subsequent person steps are executed.
In the second case the completed overview is reused as well. A saved fact-repair
result is replayed against its original input hash instead of being regenerated.
Source artifacts, locators, extraction contracts and hashes are checked before
an API client is initialized. Missing episodes/stage descriptions are diagnosed;
recovery never silently reruns extraction or accepts incomplete extraction as a
complete graph.

Previous calls remain in `OriginalCallLedger.json` and count toward the original
call budget. New calls are in `CallLedger.json`. If the resumed summary fails,
the fallback still allows person completion to proceed. If a later person step
fails, the new directory can itself be resumed. The old failed overview trace is
also retained as `PreviousEventDescriptionAttempt.json` when its filename would
otherwise be reused.

## Verification

Offline regression tests cover summary truncation/transport/validation failure,
checkpoint write failure, compact prompt contents, resume without repeating
extraction, chained recovery, fallback provenance, HTML generation and strict
replay. The supplied 20261109195713163015 checkpoint also passed an offline
end-to-end recovery with model substitutes: 31 episodes, 16 stages and 82
activities were retained, source artifacts stayed unchanged and the generated
graph passed strict replay. This checks execution and data preservation, not
live DeepSeek compatibility or semantic quality of new model responses.
