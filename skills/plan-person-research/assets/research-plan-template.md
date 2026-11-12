# {{person_name}}: Research plan

> Use this shared structure with detail appropriate to the person and available research. Replace placeholders and remove authoring instructions before delivery. Present current findings, keeping editing history in Git and the delivery summary. Write in English by default, retaining original names, source titles, and quotations as needed. Record source support separately from user confirmation; pending or partial confirmation applies to the relevant events and scopes.

Save this plan as `EPG-dataset/person-epg/<person_directory>/research-plan.md`, creating the root and person directory if needed according to the Skill. Write catalog ID fields and the Primary storyline ID as plain identifiers without backticks or explanatory text; keep explanations in the appropriate prose fields.

## 1. person and research scope

| Field | Content |
| --- | --- |
| person_id | {{Registered person ID from person-epg/people.csv, or an explicitly marked temporary ID}} |
| Name and aliases | {{Established English name when available, original name, relevant aliases, and any necessary identity distinctions}} |
| Research objective | {{The experiences or processes the user wants to understand}} |
| Coverage | {{Full life history / period / topic and research coverage cutoff; retain supported date precision}} |
| Scope notes | {{Inclusion criteria, necessary background, and explicit exclusions}} |
| Confirmation status | {{Pending confirmation, or a brief summary of partial/full confirmation referring to section 7}} |

## 2. storyline catalog

Group events by a shared activity direction or subject; a storyline is an organizing thread, not an individual construction task. Reuse registered storyline IDs; newly registered storylines use `<person_id>-S0001` and subsequent sequence values. Mark temporary references explicitly.

| storyline_id | Name | Meaning and boundary |
| --- | --- | --- |
| {{ID}} | {{A meaningful English name}} | {{Matters included and distinctions from other storylines}} |

## 3. event master table

| event_id | storyline_id | Event name | Relevant period | Scope overview | Support status | Main sources |
| --- | --- | --- | --- | --- | --- | --- |
| {{ID}} | {{Primary storyline ID}} | {{Specific continuing matter, named in English}} | {{Precision supported by the sources}} | {{What can be researched independently}} | {{Public-source support / To verify}} | {{Source IDs}} |

For a new catalog, finalize consecutive event IDs from `<person_id>-E0001` after revision filtering, independent of storyline membership; preserve established IDs when updating an adopted catalog. Keep all references consistent. `To verify` may appear in an initial draft. Final delivery includes only events with `Public-source support`, an explainable personal connection, and a usable scope. Resolve, narrow, or omit other candidates during revision. Missing fine-grained evidence details may remain research questions. Source support does not record user confirmation or graph acceptance. Execution progress, ownership, and collected artifact paths are maintained in the person's `events.csv`; detailed run records stay with the task.

### Directory layout

Use `storyline_name` and `event_name` from `events.csv` exactly as directory names; place IDs in the tree comments, not in directory names. Label an unprepared initial tree as proposed once above the tree. After revision, the tree shows the actual directories for every retained event, together with the README and progress CSV. Tree comments contain IDs only; omit source-support and existence statuses. Omitted candidates have no entries in the final tree. Directory preparation and task confirmation remain separate.

```text
EPG-dataset/person-epg/
└── {{person_directory}}/
    ├── README.md
    ├── events.csv
    ├── sources.csv
    ├── research-plan.md
    └── {{storyline_name}}/  # {{storyline_id}}
        └── {{event_name}}/  # {{event_id}}
```

## 4. event research descriptions

Repeat the following block for each candidate. Keep it concise, with detail proportional to the matter. Reuse the plan's person identity, source index, and the event master table's support status; do not maintain a second catalog here. Unknowns should be explained rather than filled with invented facts.

### {{event_id}} · {{event_name}}

**Primary storyline:** {{storyline_id and name, matching the catalog}}.

#### Event overview

{{Briefly explain the concrete matter using what the read sources establish. Include relevant background, major developments, or the latest documented state when they help explain the process. Cite source IDs beside the statements they support. Do not force a trigger, causal explanation, or resolution when unknown.}}

#### Connection to the person

{{Explain the person's supported role or connection, citing sources. Distinguish personal actions, formal responsibilities, attributed statements, and actions by an organization or other participants. If only an organizational connection is established, say so; do not infer personal decisions or motives from the person's title. Note material attribution uncertainty.}}

#### Research scope

- **Activity period:** {{The event's known or approximate period, with supported date precision; identify ongoing or unknown endpoints. If this task covers only part of a longer event, distinguish the selected window from the full event and explain the selection. A publication date or the last source found is not automatically an event boundary; later retrospective sources remain eligible.}}
- **Included:** {{The concrete matters and necessary context to investigate within this event. Make the scope usable for subsequent search without prescribing the graph's stages or actions.}}
- **Excluded and related events:** {{Material adjacent matters outside this task, and related event IDs when already available. Explain relevant overlap or the reason for separation without duplicating an event under another storyline. If no material boundary issue has been identified, say so briefly.}}

#### Further research

- **Questions:** {{Specific unresolved process questions grounded in the overview or scope. Phrase them without assuming unverified actions, motives, or causal relations occurred. Explain what remains to be established; do not impose a fixed number or repeat questions already answered without a reason for further verification.}}
- **Search leads:** {{Relevant names, aliases, organizations, documents, or source IDs, with a brief indication of what they may clarify. Distinguish read sources from unvisited leads in the shared source index. Query suggestions are optional; do not invent document titles or links.}}
- **Open issues and decisions:** {{Material conflicts, evidence limitations, or grouping/scope choices still requiring confirmation. Distinguish these from ordinary details for later search; refer to an existing question instead of repeating it. If none is identified, state that briefly.}}

Supported process facts may appear in the overview. Do not generate a completed EPG, preassign stages, or fabricate action, transaction, or relation structures. Reference the shared source index in section 6 rather than creating a separate bibliography for each event.

## 5. Coverage and matters awaiting confirmation

{{Briefly explain why the plan is ready for confirmation or why this is a partial delivery. State material limitations and unfinished work; a partial investigation must not be presented as exhaustive coverage.}}

- Periods, topics, and source types actually researched: {{Briefly describe the work completed, including the coverage review actually performed}}.
- Underexplored areas, access failures, or conflicts: {{Distinguish not searched, no results, inaccessible sources, and insufficient evidence}}.
- Material exclusions, if useful: {{Briefly name omitted matters and why they could not form usable events; no event IDs or pending-task list are needed}}.
- Groupings, event boundaries, or plan changes requiring user confirmation: {{List material choices affecting subsequent tasks}}.
- Suggested events to research first: {{Optional, with a concise reason}}.

## 6. Source index

| Source ID | Original title and link | Publisher and publication date | Actual reading and locator | Supported judgment |
| --- | --- | --- | --- | --- |
| {{SRC-ID}} | {{Original-language title and a clickable source-page or document link; a separately labeled English gloss is optional}} | {{State unknown when unavailable}} | {{Body read / snippet only / access restricted; section, page, or paragraph as available}} | {{Related event or person identity and what the source supports}} |

Generate the adjacent `sources.csv` from this table using the Skill’s export helper after updates; edit the index here rather than maintaining a second source list.

Keep quotations accurate, in their original language, proportionate, and compliant with source-use limits. Label any English translation separately and retain the original quotation. Mark discovery-only sources explicitly; do not describe a search snippet as a full document you have read.

## 7. Handoff after confirmation

If no events have been confirmed, state Pending confirmation and the pending decisions; omit the empty confirmation table. Otherwise, record the actual decisions below. A decision may cover several event IDs together. Do not invent a confirmer, confirmation date, or formal ID, or treat confirmation of selected events as confirmation of the whole catalog.

| Confirmed event IDs | Confirmed scope | Confirmation basis |
| --- | --- | --- |
| {{Explicitly confirmed IDs}} | {{The selected event descriptions and any explicitly approved scope limits}} | {{Actual user decision or supplied approval record; date/reference when available}} |

Unconfirmed events remain pending and do not block tasks for the confirmed subset. Keep the event master table's source-support status separate from this record. Preserve the confirmed scopes and decision basis.

Keep the adopted plan content and confirmed scope in each task's run record; subsequent plan edits do not automatically change that task.

Each handoff references the same event's `person_id / storyline_id / event_id`, names, cited overview, scope, connection to the person, research questions, and source leads from above, including any material unresolved issue. Avoid creating another independently maintained catalog. Runtime models, search providers, and construction budgets are selected in the subsequent task configuration.

Use the adopted plan to populate catalog identity and scope fields. Event progress and accepted artifact paths belong in the person's `events.csv`; actual inputs, configuration, outputs, and costs belong in task records. Preserve existing registrations and graph-internal identifiers through explicit mappings rather than rewriting old assets.
