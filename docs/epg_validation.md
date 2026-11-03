# Episode consistency validation

Apply this patch after the inference compatibility, P0 relevance-filter and
context-budget patches. It adds a deterministic check at the end of
`AgentEventBuilder.integrate_results()`, so both the live result and
`integrate_from_files()` use the same rules. No new dependency or model call is
required. Existing YAML works unchanged.

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

## Files

In the builder output directory:

| File | Contents |
| --- | --- |
| `RawEventCascade.json` | Complete assembled graph before validation |
| `FinalEventCascade.json` | Graph returned to the pipeline after validation |
| `IntegratedEventCascade.json` | Validated graph reconstructed from saved agent results |
| `epg_validation_report.json` | Before/after issues, duplicate groups, removed originals and summary |

`*-Result.json` files are preserved. The report's original paths refer to the
raw graph; retained-output paths refer to the final graph. Array indices can
change when copies are removed. Remaining issues do not abort graph construction.

## Optional configuration

Inside `builder_config`:

```yaml
epg_validation:
  enabled: true
  deduplicate: true
```

Use `deduplicate: false` to check without merging, or `enabled: false` to disable
the new step. These values must be YAML booleans.

## Offline replay

Run from the repository root with an existing graph and a separate output folder:

```bash
python scripts/validate_epg.py path/to/FinalEventCascade.json --output-dir outputs/epg_checked
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
idempotence, actual builder integration, persistence and offline replay.
