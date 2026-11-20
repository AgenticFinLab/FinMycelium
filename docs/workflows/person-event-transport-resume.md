# Bounded requests and resume after this transport upgrade

Each event-builder request runs in an isolated, terminable subprocess. It is
terminated when answer and reasoning character counts both stop increasing for
180 seconds, or when the entire invocation reaches `timeout` (900 seconds in the
resume command below). Empty stream chunks and keepalive traffic do not extend
the output-stall deadline. A short termination/kill cleanup can follow the deadline.
The existing SDK I/O timeout remains set as well.

Timeouts, transient connection/stream errors, HTTP 429 and server errors receive
at most one automatic retry, queued behind other ready work. Authentication,
configuration errors and output-length truncation are not automatically retried.
Every retry has a new call ID with `retry_of`; it consumes the existing global
model-call budget. Its budget is retained across resume. A fresh explicit resume
can attempt the failed request again, but does not reset automatic retry counts.
Reading follow-ups and correction budgets remain unchanged.

If organization exhausts its retry, completed upstream work is retained and
dependent relations remain blocked. Other independent task failures are local.
Minute-by-minute progress also reports time without answer/reasoning growth.

## Resume the current run

Stop the old process first and retain its output directory. Apply this patch on
top of the read-round and 60-second progress patches. With `RUN` pointing to the
existing run, execute:

```bash
python -m dotenv -f .env run -- python -m finmy.person_epg.event.resume_transport "$RUN" --allow-model
```

This command reads the original input from the run directory. It does not need
another copy of input.json and never creates a new run directory. It refuses to
wait behind a still-running old process, which must finish or be stopped first.

The explicit `resume_transport_upgrade=True` path backs up the previous state
under `recoveries/transport-guard-*/state-before.json`. It retains `code_sha256`
as the original semantic checkpoint namespace, records the actual upgraded
implementation in `execution_code_sha256` and `execution_upgrades`, and keeps
input, prompt, adoption and model settings unchanged. Completed stage snapshots,
accepted response checkpoints and saved prefetched responses are reusable.
Only requests without a reusable response need another model call. This explicit
upgrade option is for the transport-only patch, not unrelated semantic changes.

The new `stall_timeout` and `max_transport_retries` settings are operational and
do not change semantic checkpoint fingerprints. The command expects the existing
run's saved `timeout` to be 900, as in the current read2-900 runs; it does not
silently rewrite fingerprints for runs with different semantic settings.

## Validation

Offline tests launch real child processes that remain silent or emit empty chunks
or continuously growing output. They check termination, the 900-second-deadline
mechanism using shortened test values, result/usage delivery, one-retry behavior,
and resume from organization with zero repeated extraction/consolidation calls.
No live provider request is required for these checks.
