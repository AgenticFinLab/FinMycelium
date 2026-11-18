# Relation-stage replay (patch 1)

Base: `183f213ca7a35d5803161d0dc7ac892bd4c6a321` on `person-epg-muhan`.
This patch adds experiment plumbing, without changing relation prompts, evidence
allocation or acceptance rules. Later patches can run against the same snapshot.

## Prepare once

Use a native frozen Builder input (`input.json`, not the resulting EPG). Save the
actual build settings in `baseline-config.json`, including `lm_name`,
`api_json_mode`, output/context/read limits. The example deliberately leaves model
selection and budgets to that file; saved task settings remain authoritative.

```bash
python -m finmy.person_epg.event.relation_experiment prepare input.json \
  --config baseline-config.json --output output/relation-baseline --allow-model
```

This executes extraction, consolidation and organization and stops before relations.
It prints the snapshot path relative to the output directory. The state also records
`organization_snapshot` and its file hash. Normal new builds now save the same
snapshot immediately after organization, with no extra model call. Only snapshots
with validated graph/facts, processed source ranges and no unresolved upstream work
can enter an experiment. A saved snapshot may fail validation; preparation then exits
nonzero and retains all diagnostic artifacts.

Historical runs without this artifact need one new baseline preparation from their
frozen input. This patch does not infer the pre-relation state from a final graph,
copy old state files or bypass code fingerprints. A snapshot fingerprint detects
accidental changes; it is not a signature authenticating externally supplied data.

## Run each variant in a new directory

Copy the printed snapshot path into the command below. `relation-config.json` is a
JSON object of explicit overrides, for example `{"max_calls": 10}`. Use identical
settings for baseline and later variants, including service/model and JSON mode.

```bash
python -m finmy.person_epg.event.relation_experiment run \
  output/relation-baseline/attempts/0001/organization-snapshot.json \
  --config relation-config.json --output output/relations-baseline --allow-model
```

The runner calls the existing `Construction.relate()` and normal adoption/validation.
It freezes upstream hierarchy and disables final repair (`final_repair_rounds=0`);
all compared stage variants must use this same setting. Full-build validation,
including the usual final repair, remains a later separate step. A failed or
truncated invocation stays failed/partial rather than a successful zero-edge result.

Upstream calls are recorded separately. Each new experiment starts with zero
**downstream** usage; reads, format correction and follow-up calls share its total
budget. Existing output directories require `--resume`. Resuming uses the saved
experiment configuration; explicit overrides may increase cumulative call limits
under the existing runtime rules, but cannot change model, JSON mode or code.
Use a fresh output directory after applying another patch.

Outputs include the native `epg.json`, checks, Gantt and existing step request/read/
response records, plus `relation-summary.json`. The summary records source and
experiment code identities, snapshot identity, effective configuration, calls,
reads, read characters, raw per-call token usage and cumulative model time.
`invocation_elapsed_seconds` describes this invocation, not all earlier resumes.
Missing usage remains unknown. No monetary cost or semantic-quality score is
invented. Inspect requests under `attempts/*/steps/` to compare supplied evidence;
inspect `state.json` for all local reads. All source baseline files remain untouched.

Both commands require `--allow-model` for real model calls. Offline Python callers
can inject a model for regression checks. Preparation and reruns do not automatically
approve or collect results into the dataset.

## Verify

```bash
python -m pytest -q tests/test_person_event_relation_experiment.py \
  tests/test_person_event_pipeline.py tests/test_person_event_context.py \
  tests/test_person_event_optimization.py
```
