# Relation evidence allocation (patch 2)

Apply after Patch 1 on `183f213ca7a35d5803161d0dc7ac892bd4c6a321`.
This increment changes the production relation request builder and therefore also
the workbench build and Patch 1 replay. It does not change the public graph schema,
relation acceptance rules, Context repair, or relation discovery completion rules.

## What changes

Each assigned Action receives its shortest complete directly cited Evidence quote
first, including citations in retained conflicts. Candidate membership does not
affect this allocation. Additional quotes are offered one per Action per round,
followed by Phase evidence and other dependencies. Shared evidence is sent once
and credited to every Action that cites it. No quote, offset, or upstream record is
rewritten; full records remain available through the existing local read tools.

The optional allocation remains one quarter of the context budget. Minimum Action
coverage may exceed that optional allocation, within the existing initial-request
limit and with the original read headroom preserved. Navigation previews compress
before ownership shrinks. If multiple Actions cannot each receive a quote, the
builder reduces the batch while retaining the global Action navigation index.
If even a single Action's full quote cannot fit, it remains explicitly omitted and
available through `read_records` or `read_sample`; the Action is not dropped.

Saved requests contain `context_selection.evidence_by_owner`, with available and
included counts and omitted Evidence IDs. `uncovered_action_ids` means existing
evidence was not delivered; `actions_without_evidence` means no direct citation was
present. Counts measure supplied records, not evidence sufficiency or model reading.
The source locations remain in `facts_index.evidence_index` for paged source reads.

## Run the comparison

Keep the same snapshot and model settings. Use a NEW output directory after code
changes; `--resume` is only for an unchanged implementation. From the repository
root, the following explicitly loads the local `.env` without changing the library
or workbench environment-loading policy:

```bash
python - <<'PY'
from dotenv import load_dotenv
load_dotenv('.env')
from finmy.person_epg.event.relation_experiment import main
raise SystemExit(main([
    'run', 'PBUILD-dee74d7e4a1d_organization-snapshot.json',
    '--output', 'output/relations-test-02', '--allow-model',
]))
PY
```

The filename is an example; any valid organization snapshot works. Compare the
saved requests, `relation-summary.json`, `checks.json` and actual edges against
the baseline. Patch 1 continues to disable final repair; malformed ContextRef
support targets can still produce a partial result. This increment does not
promise new edges or repair those errors.

## Offline validation

Regression cases cover uneven evidence counts, candidate/order bias, shared
citations, exact quote preservation, missing versus omitted evidence, oversized
quotes, bounded batches and global navigation. Existing context, optimization,
pipeline, recovery, feedback and snapshot replay tests remain applicable.

Using the backfilled 26-Action snapshot, rebuilding requests without any model
calls under the local Patch 1 baseline supplied at least one directly cited quote
to 11/26 Actions in the first batch; Patch 2 supplies 26/26. Both assign 26 Actions
and four Phases in that batch. The uploaded historical run supplied 22/26 under
its recorded request/code; it is not the identical-code control. No live quality,
latency or token-cost improvement is claimed from this offline comparison.
