# Search to schema repair

This patch follows `FinMycelium_PR18_person_pipeline_repair.patch`. It also
supports the observed mixed installation: current search code with the older
`organization_batches.py` and `person_organization.py`. The new organization
guard runs at their common inference boundary and does not require the earlier
detail-index helper to be installed.

Apply from the repository root and restart the running UI/worker process so it
loads the changed Python modules:

```bash
git apply --check FinMycelium_PR18_search_schema_repair.patch
git apply FinMycelium_PR18_search_schema_repair.patch
```

## Behavior

- A Baidu query validation error no longer prevents Bocha from running. A model
  can supply `provider_queries: {"baidu": "shorter equivalent query"}` while
  retaining the original `query` for Bocha. Successful provider responses are
  cached independently. Locally rejected queries do not consume request quota.
  The adapter never deletes search terms to fit a provider limit.
- After repeated invalid actions, inspected originals enter a bounded
  finalization phase using the task's remaining model allowance. The model must
  select eligible source IDs. Unread, invalid, or unselected sources are not
  automatically included. Early-stop handoffs remain `insufficient` with gaps.
  Old `repeated_invalid_action` checkpoints can follow the same path on resume.
- PersonOrganization receives an authoritative catalog of
  `activity_detail.detail_index` values grouped by Activity. Transaction detail
  array positions are explicitly distinguished from those keys. Invalid choices
  produce per-membership errors with the allowed values in the retry request;
  no fact, transaction, quote, or membership is silently deleted to pass checks.
- CLI and UI status reports record Builder `running`, `failed`, or `completed`
  separately from search coverage. A failed Builder retains its output directory
  and the already prepared search materials instead of remaining `not_started`.

Existing 120,000-character limits and disabled-by-default post-build enrichment
are unchanged. Public schema, EPG serialization, and HTML rendering are unchanged.

## Recovering existing work

An existing failed search task resumes with its saved source versions, read
records, and cumulative call counts. It does not get a fresh quota. Completed
or insufficient handoffs remain reusable without new discovery/search calls;
an explicit storyline-search revision can reopen incomplete research.

For a Builder run that already has a complete `FinalEventCascade.json`, the
existing person-recovery entry point can validate and reuse extraction before
rerunning organization. The source directory is preserved:

```bash
python -m finmy.runner.sparse_person_recovery \
  --source-run /path/to/build_output
```

Add `--execute --env-file .env` only when ready to run the organization model.
This recovery does not incorporate newly recovered search evidence into the old
extraction; rebuilding with the revised material is a separate operation.

## Regression coverage

Offline tests cover provider-specific query repair and caching, bounded
finalization of read originals, legacy checkpoint resume, pause and budget
preservation, source-to-Builder handoff, precise transaction/detail-index retry
feedback, and Builder failure reporting. Model responses and external requests
are supplied by deterministic test doubles; these checks do not assert the
semantic quality of a new live EPG.

Validation on this patch: 401 tests and 243 subtests passed. The captured
Activision and charitable-donation checkpoints each completed a simulated
source-selection call with zero new search/fetch requests, retaining 2 and 1
originals respectively (14,670 source characters total). These were isolated
copies; the uploaded runs were not modified. The organization guard was also
tested with the two older organization modules and without
`organization_details.py` installed.
