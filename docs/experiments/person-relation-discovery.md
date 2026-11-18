# Patch 3: relation discovery completion and local Context correction

Apply after the delivered Patch 1 and Patch 2. This rebased edition uses the
`build.py` and `prompts.py` supplied in `patch3-current-files.tar.gz` as its
exact baseline for those files; other files retain the delivered Patch 2 base.
It replaces the previous Patch 3, which did not apply. This patch changes the
actual construction/replay path. Public EPG JSON and HTML rendering are unchanged.

## Behavior

Each relation batch now has a required `relation_review` deliverable, separately
checked from its Context updates. It records one within-phase/cross-phase review
per assigned Action, a disposition for each assigned candidate, and the meaningful
directed pairs inspected. Candidate ownership follows its source Action, falling
back to its known target or the first Action when endpoints are unknown. Targets
remain available across batches and phases; candidates do not restrict discovery.

Accepted outgoing edges must be represented by pair reviews with matching endpoints
and valid relation/evidence references. Missing coverage, invalid references or
pending work prevent completion. Zero edges is allowed after review; no pair/edge
quota is introduced. Receipts are model declarations, not proof of exhaustive
search or semantic correctness. Existing evidence and graph validation still apply.

Rejected Context associations now enter the existing bounded correction loop. This
includes the reproduced `Support.target=/phase_id` inside a ContextRef: support
pointers are local to the association, which has no `phase_id`. Feedback carries
the validation error and rejected proposal; the model must correct it using the
association's evidence. The program does not blindly rewrite pointers or infer
missing support. New Contexts and their dependent associations remain atomic.

Correction requests contain only failed owner fields and/or the failed receipt.
Accepted associations and edges cannot be rewritten by that correction. Rejected
Context/ContextRef IDs stay stable. Original rejections and their resolutions are
retained. Model-authored pending items are not cleared merely by a later omission.
Adopted edges survive pause/failure before a correction; resume replays cached
adoption and retains the shared JSON/adoption retry budget. Exhausted work remains
partial. Existing final graph repair is retained; it cannot replace a missing review.

This patch makes discovery an independently checked deliverable within the same
relation task. It does not yet split discovery and Context into separate model tasks.

## Apply and replay

```bash
git apply --check --ignore-space-change FinMycelium_patch3_relation_discovery_rebased.patch
git apply --ignore-space-change FinMycelium_patch3_relation_discovery_rebased.patch
```

Use a new output directory with the existing frozen organization snapshot:

```bash
python - <<'PY'
from dotenv import load_dotenv
load_dotenv('.env')
from finmy.person_epg.event.relation_experiment import main
raise SystemExit(main([
    'run', 'PBUILD-dee74d7e4a1d_organization-snapshot.json',
    '--output', 'output/relations-test-03', '--allow-model',
]))
PY
```

Add `--resume` only when resuming this new run with unchanged code/configuration.
Do not resume a Patch 2 run under Patch 3 or reuse its relation responses. The
snapshot remains the frozen upstream input; there is no need to regenerate it.

## Outputs and validation

`relation-summary.json` points to the current graph, checks and `discovery_path`.
`state.json.relation_discovery` points to `attempts/NNNN/relation-discovery.json`,
which contains accepted/rejected review attempts and completed/incomplete Action
IDs. These records describe discovery completion only: Context errors can still
make the overall result partial. `adoption.json` retains original field errors
and `resolved_by` entries. Exact task requests, responses and reads remain saved.

Offline tests cover missing/invalid/pending receipts, supported cross-phase edges
without candidates, valid zero-edge reviews, candidate ownership, receipt-only
correction, the nested ContextRef pointer failure, immutable accepted neighbors,
bounded retries and pause/resume. No paid model calls were made to validate this
patch. A live replay is still needed to measure discovery quality and runtime.

```bash
python -m pytest -q \
  tests/test_person_event_relation_discovery.py \
  tests/test_person_event_balanced_evidence.py \
  tests/test_person_event_context.py tests/test_person_event_optimization.py \
  tests/test_person_event_relation_recovery.py tests/test_person_event_relation_experiment.py \
  tests/test_person_event_pipeline.py tests/test_person_event_feedback.py \
  tests/test_person_event_contract.py
```

The broader test collection also needs optional `plotly`, `openai` and `streamlit`
dependencies, absent from the patch-validation environment; those UI/provider
suites were not run. The related offline suites above are the patch's validation.
