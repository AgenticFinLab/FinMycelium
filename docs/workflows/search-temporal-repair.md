# Search progress and evidence-led extraction repair

Apply after `FinMycelium_PR18_search_schema_repair.patch` (development baseline
`4b57d4a`), from the repository root:

```bash
git apply --check FinMycelium_PR18_search_temporal_repair.patch
git apply FinMycelium_PR18_search_temporal_repair.patch
```

Restart existing UI and worker processes after applying the patch.

## Search progress

The source catalog reports its size and end explicitly, including when it fits
on one page. An invalid page offset no longer wraps to the first page. Repeated
catalog views or rereads that reveal no new material trigger bounded finalization
instead of spending the remaining model allowance on the same operation.

Final context includes actual provider-request, read and source counts. For an
empty handoff, operational coverage is derived from these counters and the
original event questions. The model's raw explanation remains in the trace;
an empty eligible-source list is not reported as proof that no search occurred.

Provider failures record HTTP status, a sanitized error code and a category.
Authentication, permission and balance/quota failures suspend the affected
provider for this search revision. Transient failures use a cooldown and a
bounded failure circuit. Sibling event tasks share provider health, while cached
results and other providers remain usable. Skipped requests do not consume quota.
No raw API error body or credential is persisted. Explicit configuration/search
revision reopens the service without resetting cumulative usage.

## Extraction before schema assembly

An action outside a provisional episode boundary can trigger one evidence-led
scope review for that role invocation. The reviewer decides whether the evidence
belongs to the same episode and whether its label or time range should change.
Changed fields need supplied source evidence and an explanation. Normalized,
relative and quarter dates need not occur literally in a quote. Candidate facts,
IDs and evidence are not rewritten to fit a boundary.

An approved revision is revalidated, recorded with the previous skeleton, and
propagated to the checked skeleton and outward parent bounds. Unapproved or
invalid proposals retain the original scope checks and correction path.
The saved revised skeleton is the one used by subsequent extraction and replay.

Securities `counterparty` relations receive a targeted evidence review before
acceptance. Buying an issuer's stock alone does not establish that the issuer
was the seller or received payment. Direct issuance, subscription and repurchase
can still support that relationship. Unsupported or uncertain assertions return
specific feedback to the extraction model; the program does not silently delete
relations or purchase facts. Unchanged reviewed candidates reuse their decision.

Both reviews use the existing model-call ledger and total budget. Their artifacts
are distinct from extraction-role outputs and remain compatible with replay and
person recovery. These are model-assisted semantic checks, not guarantees that
every factual interpretation is correct.

Public schema, final JSON layout and HTML rendering are unchanged. Existing
character limits are unchanged. Post-build enrichment has since been removed.
Tests use local sources and simulated model/provider responses; no live paid
requests are required for the regression suite.

Validation: 612 tests and 343 subtests passed, including strict replay and
organization-only recovery after scope revision. SDK-specific transport tests
were excluded because the local environment uses explicit `lmbase` container
doubles rather than an installed live adapter. No online model run was performed.
