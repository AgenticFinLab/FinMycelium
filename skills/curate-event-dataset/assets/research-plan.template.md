# Event dataset research plan

## Scope and baseline

Record the baseline input path, its Git object ID or file SHA-256, the historical ID mapping, the research review date, the activity period under study, the current phase and the coverage objective. If the task also limits what could have been known by a particular date, record that evidence cutoff separately.

## Research questions and coverage

Describe the matters under investigation, their boundaries, domain and category targets, and material gaps. Refer to [the event master](events.csv) for individual event definitions.

## Batch progress and open questions

| Phase | Event IDs or candidate scope | Research completed | Duplicate review coverage | Open issues | Next action |
| --- | --- | --- | --- | --- | --- |

Use `baseline` for historical IDs and `expansion` for new IDs. In each of the two coverage columns, enter the IDs whose checks are currently complete. Use single IDs or inclusive ranges separated by commas, for example `event1-event5, event8`. Leave the cell empty until work is complete. Keep planned candidates in the scope column. Link unresolved identities and duplicate decisions to [the issues register](ISSUES.md).

When evidence or scope changes, remove the affected IDs from every coverage cell for the check that must be repeated. Record the reason and next action and restore coverage after the recheck. On resumption, reconcile the last completed batch with the event rows, source references and issue decisions already saved.

At the baseline and final milestones, reconcile distinct reviewed IDs against the expected range. Record the review date, outstanding identity or duplicate decisions, and the basis for the phase conclusion. Overlapping batches count once.

## Evidence and handoff

Refer to [the source index](sources.csv) by source ID. Identify the scope and evidence used for each handoff, outstanding questions, and the actual basis for moving to the next phase.
