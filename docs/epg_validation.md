# Episode consistency validation

Event mode preserves the assembled model output without automatic validation or
transaction merging. The existing offline tool below remains available for explicit
checks. Person mode uses its separate SubjectGraph validation and review pipeline.
The former `builder_config.epg_validation` setting no longer affects construction.

## Behavior

- Check transaction timestamps against the containing Episode. Year/month dates
  remain intervals; invalid, missing and partly overlapping dates are reported.
- Check hierarchy bounds and participant references. Concurrent Stages and
  Episodes are allowed.
- Deduplicate across Episodes when timestamps, resolved participants, instruments,
  transaction types and specific numerical evidence support the same transaction.
  `stock purchase` and `share purchase` are treated as equivalent type labels.
- Prefer an existing occurrence in the narrowest Episode that contains its time.
  Retain supporting details/evidence and record removed occurrences in the report.
- Keep ambiguous candidates, different trades on the same day, and aggregate
  records that overlap individual trades. Report unresolved time problems without
  changing dates or relocating transactions based only on a timestamp.

This is a structural consistency check. It does not verify whether a generated
date is the true trade date, correct actor roles, or rewrite generated prose.
The transaction/cascade schema remains unchanged. Cross-Episode references are
recorded in the report rather than added as duplicate transaction objects.

## Offline replay

Run from the repository root with an existing graph and a separate output folder:

```bash
python scripts/validate_epg.py FinalEventCascade.json --output-dir outputs/epg_checked
```

This writes a validated `FinalEventCascade.json` and `epg_validation_report.json`.
It does not search, call a model, or overwrite the input or existing output files.
Add `--no-deduplicate` for a check-only replay.

## Tests

```bash
python -m unittest discover -s tests -p 'test_epg_validation*.py' -v
```

The tests use synthetic examples and stub model dependencies. They cover temporal
precision, identity/amount conflicts, aggregate records, evidence preservation,
idempotence, unchanged Event output/persistence and explicit offline replay.
