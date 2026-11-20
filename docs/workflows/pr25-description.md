# Suggested PR description

Person Event builds preserve completed work across slow requests, partial failures
and interrupted runs. Evidence retains the original single-source quotation
contract. HTML presents Evidence and Sources in separate layers, without cross-source merging.

- Stage tasks share a FIFO coordinator with isolated transports, bounded retries
  and checkpoints that retain completed model responses.
- Source-to-sample navigation, read deduplication and persistent budgets keep
  local retrieval usable without repeatedly charging the same source ranges.
- A read-only status command shows actionable errors and available artifacts;
  renderer changes have a separate dependency fingerprint.

Validation: `python scripts/check_person_event.py` runs offline regression checks.
See [operations](person-event-operations.md) for fresh builds, resume and HTML export.
