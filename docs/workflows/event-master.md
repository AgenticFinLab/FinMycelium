# Event master

One row defines one event and its intended reconstruction scope in the workbench.

| Group | Fields | Rule |
|---|---|---|
| Identity | `event_id`, `event_name_zh`, `event_name_en`, `aliases` | Stable ID; at least one name to save. Names retain their entered language. |
| Description | `description`, `domain`, `category`, `country_region`, `participants` | Main subjects guide retrieval. Classifications are editable. |
| Scope | `coverage_start`, `coverage_end`, `scope_include`, `scope_exclude` | Intended graph coverage. Preserve year/month/day precision; unknown allowed. |
| Retrieval | `keywords`, `search_language`, `source_hints` | Language: `zh`, `en`, `zh-en`, or unset. Store actual queries and search results separately. |
| Coordination | `owner`, `notes`, `related_events` | Relations include overlap, contains, part-of, possible duplicate or related, with a note. |

Lists (`aliases`, `country_region`, `participants`, `keywords`, `source_hints`)
are stored as arrays. Forms accept one item per line; commas remain part of an item.
CSV/Excel list cells use JSON arrays or one item per line. `related_events` is a
JSON array of `{event_id, relation_type, note}`. Relation codes are `overlap`,
`contains`, `part_of`, `possible_duplicate` and `related`. Links may reference an
external catalog ID; unresolved links are marked as external or awaiting import.
Self-links, duplicate targets and invalid relation types are rejected.

Scope review: pending / needs revision / confirmed. Confirmation requires a
name, description and included scope. Dates can remain unknown; either name
language is sufficient. Review binds to identity, description, classification,
subjects, geography and scope. Changes to these fields require fresh confirmation;
owner/notes-only edits retain approval. Search/build task creation requires
confirmed scope. Keyword edits retain scope approval and change the construction
input snapshot.

Default columns: ID, Chinese name, English name, combined domain/category,
coverage interval, scope review, workflow status, owner and relation count.
Optional columns include all other fields and update time. Row selection opens
details. Exports retain all stored fields regardless of visible columns and add
derived review/version columns. Review status is calculated from local review
records; status columns in imported tables are excluded.

Imports preview explicit column mappings. Map old names, time fields and IDs
to the corresponding language, coverage and identity columns, and confirm any
omitted columns. Earlier workbench records retain their original bodies and
history. Their old name and time fields are shown for manual assignment when
saving an updated record. Graph, review and task snapshots are preserved;
graphs bound to an earlier input format require reassociation and review.
