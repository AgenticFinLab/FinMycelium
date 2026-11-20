# 60-second output stall, complete JSON reuse, two retries

This incremental patch applies after
`person-event-v2-evidence-semantic-merge-incremental.patch`. It does not require
the earlier un-applied stall120 patch.

When neither answer nor reasoning grows for 60 seconds, the request is terminated.
A separate 900-second total deadline remains. Progress still prints once per minute.
Empty chunks/keepalives do not extend the output-growth deadline.

The parent retains answer deltas before terminating the child. The exact recovered
text is saved to the call's `response.json`. If it parses as a complete JSON object,
it goes through the existing role and adoption checks. A valid result is accepted
without another model call, even when the stream's final termination marker is
missing. Diagnostics retain the real finish reason and record `output_recovered`
and `recovery_status`; the code does not fabricate a successful provider finish.

If the recovered JSON is incomplete, the same request is retried at most twice:
one initial request plus two retries, three invocations maximum. Empty/transient
transport failures and incomplete-JSON failures share this retry allowance. It is
saved across resume, consumes the existing global call budget, and uses the FIFO
scheduler. Exhausted incomplete-JSON attempts cannot enter the ordinary formatting
retry loop. Failed calls retain their body; they are not successful checkpoints.
Refusals, tool-call responses and provider-declared length truncation retain their
existing handling. A complete but schema-invalid JSON object still goes through
the existing validation/correction mechanism.

The runtime default and both resume commands now select `stall_timeout=60` and
`max_transport_retries=2`. Operational settings remain excluded from semantic
checkpoint fingerprints. Completed evidence-review responses and upstream stages
remain reusable. Existing ordinary `run_event(..., resume=True)` callers retain
saved settings unless explicitly overridden; use the commands below to upgrade.

## Resume only evidence merging

Stop the old process and keep the existing `RUN` value:

```bash
git apply --check person-event-v2-stall60-retry2-incremental.patch
git apply person-event-v2-stall60-retry2-incremental.patch
python -m dotenv -f .env run -- \
  python -m finmy.person_epg.event.evidence_consolidation "$RUN" \
  --allow-model --extra-calls 30
```

This resumes the existing evidence-review input and reuses completed reviews.
It automatically reads the original input from the run directory.

For the whole pipeline's unfinished work instead, use:

```bash
python -m dotenv -f .env run -- \
  python -m finmy.person_epg.event.resume_transport "$RUN" --allow-model
```

Offline tests verify actual child-process termination, complete JSON recovery,
exactly two incomplete retries, mixed empty/partial failure budgets, saved-response
replay, checkpoint reuse, and no accidental format-retry amplification. No live
Kimi request was made.
