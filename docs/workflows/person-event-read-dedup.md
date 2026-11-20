# Deduplicate source reads

This incremental patch is based on `person-epg-yuntao-evidence` commit
`35732ae8fb10e00c97ad8ee12f8c0f5b7bf02a11` plus the retry5 patch.

Source reading now charges `max_read_chars` by the union of delivered character
ranges, keyed by sample ID and the SHA-256 of the frozen sample text. Reading
0–4000 twice costs 4000 characters; subsequently reading 3000–5000 adds 1000.
Search snippets and explicit sample reads share this accounting. Other record
reads retain their existing serialized-character accounting.

Every delivery remains in `state.reads`. Its `chars` field retains the original
serialized size; `budget_chars` records the newly charged amount. The current
total is `state.read_budget.charged_chars`. Old runs are recalculated from their
existing read results and immutable input without rewriting historical entries.
New source-read entries also record their sample versions.

Before a model request, overlapping text already present in `task.body` or
earlier `read_results` is omitted from subsequent read results. Partial overlaps
retain every new character with exact original offsets. Fully covered ranges
carry an `already_supplied` notice; identical repeated entries are omitted.
Saved read results remain complete. Separate tasks each receive the text they
need. This reduces duplicate prompt content, not all repeated input across tasks.

Read-call and read-round limits are unchanged. Repeated requests still consume
those limits, so the model cannot loop indefinitely on cached material. Tasks
already exhausted by `read_rounds` remain limited on resume.

## Continue an existing experiment

After stopping the old process, keep `RUN` pointing at the existing output folder:

```bash
git apply person-event-v2-read-dedup-incremental.patch
python -m dotenv -f .env run -- \
  python -m finmy.person_epg.event.resume_transport "$RUN" \
  --allow-model --extra-calls 60
```

The existing explicit upgrade path backs up state and retains the checkpoint
namespace. Completed responses/stages remain reusable. Pending paid responses
written with the old prompt layout are matched against their original layout.
The original input stays unchanged; the new attempt is saved in the same run.

Offline checks cover overlapping intervals, version separation, search/sample
overlap, task-body compaction, concurrent task delivery, old read-ledger recovery,
prefetched response reuse, and existing read-round/runtime behavior. All 49
selected checks passed. No live model request was made. Replaying the supplied
26 read records changes charged characters from 95,217 to 28,582; this is a
budget-accounting comparison, not a measured reduction in the API bill.
