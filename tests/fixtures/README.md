# Regression fixtures

Keep one complete Buffett graph, and make failure fixtures contain only the facts
and evidence needed to reproduce their named problems. JSON stays indented for
review; reducing whitespace is not a substitute for reducing irrelevant data.

| Fixture | Purpose |
| --- | --- |
| `buffett_person_epg_preview.json` | Full fixed package for schema, projection, recovery, and rendering compatibility. Its checksum is tested. |
| `person_canonical_cases.json` | Real faulty output for duplicate annual results and meetings, Activision/Abel historic scene placement, June/November recipient splitting, and reversed proposal/response direction. |
| `organization_transaction_detail_replay.json` | Captured transaction details incorrectly selected as activity details; validates complete diagnostics and explicit model retry. |
| `relation_batch_overflow.json` | Captured cross-batch relation candidates and coarse/unknown-time failures. |
| `episode_scope_buyback_conflict.json` | Buyback scope conflict at episode reconstruction. |

The canonical fixture retains 18 activities and 17 activity details, including
different details on duplicate reports and all aggregate transaction details.
Peripheral actions, unused entities/times, and their unused evidence were removed.
Source text consists of verbatim retained quotes; contained duplicate excerpts are
omitted and every span offset is recomputed against the resulting document.
`test_person_canonical_acceptance` checks package validity, evidence closure, exact
quote offsets, and the behavior of each retained failure case.

The old `person_relevance_failure_20261109.json` replay belonged to the removed
separate Relevance phase. Its useful isolation cases now use minimal inputs to
the current `partition_placements` path in `test_organization_item_isolation`.
Targeted repair, pending metadata, cache invalidation, and native export tests
remain. Retry diagnostics have one captured replay in
`test_organization_call_guard`; detail selection tests focus on local IDs and
projection semantics rather than duplicating that retry loop.
