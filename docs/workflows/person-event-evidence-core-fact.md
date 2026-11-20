# Compatible-detail evidence merging

Apply this incremental patch after `person-event-v2-read-dedup-incremental.patch`.
The review policy is `core-fact-compatible-details-v2`.

Pairs may merge when they describe the same core fact and their additional
details are compatible. Missing a coupon, exact date, duration or other term is
not itself a contradiction. Distinct acts, conflicting values, attribution and
modality still matter. Approval and completion, issuance and redemption, or a
preferred purchase and a warrant exercise remain different facts. A bundle of
independent acts is not merged into one isolated detail.

A merged record keeps its stable ID and every original quotation. Its statement
retains the distinct original statement lines so compatible details are not lost
when the canonical ID came from a shorter description. No statement is generated
by the merger. Citations retain their source, sample, offsets and hashes; support
is collective, not an assertion that every source independently states all details.
The graph schema and existing HTML renderer are unchanged.

The policy is included in pair requests/reports and in the evidence-stage cache
key. A saved all-different result under the earlier strict policy cannot bypass
the new review. Subsequent runs under the same policy still reuse checkpoints.

Run only evidence review on the existing result, without extraction or relations:

```bash
git apply person-event-v2-core-fact-merge-incremental.patch
python -m dotenv -f .env run -- \
  python -m finmy.person_epg.event.evidence_consolidation "$RUN" \
  --allow-model --extra-calls 60
```

Eleven offline checks passed, including preservation of original statements and
quotes, reference rewriting/rendering, policy-change invalidation, and repeated
CLI checkpoint reuse. No live model request was made; the new merge count must
be measured on the actual run.
