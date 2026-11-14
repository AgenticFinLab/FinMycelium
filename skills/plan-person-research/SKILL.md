---
name: plan-person-research
description: Research a person's public life or a defined scope using a personal agent's own web search and browsing tools. Discover and organize storylines and events, then deliver a sourced Markdown research plan. Use for planning or revising person EPG research before construction, without launching FinMycelium search or Builder tasks.
---

# Plan person research

Actively research public sources to turn the user's objective into a plan that can be discussed, confirmed, and executed one event at a time. Use this same skill and template for every person; express case differences in the inputs and deliverables.

Codex or another personal agent executes this skill with its own search, page-opening, and document-reading capabilities. Do not use FinMycelium's Baidu, Bocha, Exa, or person-planning APIs for this discovery step. The project pipeline receives the confirmed plan and subsequently acquires evidence and constructs the selected event.

For initial research or a revision, use the [prompt templates and session settings](references/launch-template.md). Keep case inputs in the prompt and shared research guidance in this skill.

## Language policy

- Write the research plan in English by default, including storyline and event names, scope descriptions, research questions, explanations, and status labels. A non-English conversation does not by itself change the deliverable language; follow an explicit user request for a different output language.
- Use an established English form of a person's name when available, while retaining the original name and relevant aliases. Do not invent an official English name.
- Preserve evidence quotations and source titles in their original language. If an English translation or explanation is useful, label it separately and keep the original; a translation must not replace the cited evidence.
- Preserve established IDs, URLs, and source locators exactly; finalize initial event IDs as described below. Search and read in languages appropriate to the sources; English output does not imply English-only research.

## Terminology and research units

Use the hierarchy `person → storyline → event` consistently:

| Level | Meaning |
| --- | --- |
| person | The individual being researched; retain their identity, aliases, and existing person_id. |
| storyline | A thematic thread in the person's experiences, grouping events with a shared activity direction or subject. It organizes and aggregates events; it is not itself the construction unit. |
| event | A concrete process centered on an identifiable matter, object, or objective, with an explainable scope. It is the unit for independent search, construction, review, and JSON/Gantt output. |

For example, an illustrative hierarchy is `Warren Buffett → Investment and capital allocation → Occidental Petroleum investment process`. This explains the naming levels; actual candidates still require source research. A storyline is a grouping, while an event is a concrete research matter.

Events in a storyline need not form a causal chain or occupy a continuous period. A storyline may initially contain only one discovered event; do not invent others to fill the catalog. An event may span years, contain multiple stages and actions, or remain ongoing. It does not require a known ending and is not synonymous with a single action.

Use three boundary checks:

- **Concrete matter:** Can the event be described as a specific undertaking or process? Sharing a person, company, or year is not enough to combine independent matters.
- **Process continuity:** Negotiation, agreement, execution, and later adjustments may belong to the same matter. Separate reports or years do not automatically create separate events; independent projects involving the same company do not automatically form one event.
- **Independent scope:** Can a downstream task state what to investigate, the relevant period, and adjacent matters excluded? A topic such as all of a person's investments is usually a storyline-level scope; a single agreement signing may be an action within an event. Judge the actual research subject rather than applying these examples mechanically.

Do not split or merge events merely because of duration or document volume. A long event may initially be researched within an explicit period, retaining its relationship to the full matter instead of inventing a separate event for each task window. For initial delivery, choose a defensible scope or omit a matter whose boundary remains unusable; changes to confirmed scopes still require user confirmation.

This step establishes the research catalog and its boundaries. Do not invent the event's stages, actions, transactions, or graph relations in advance.

## Inputs and deliverables

The only required input is enough information to identify the person; a formal ID is not required to begin. Research objectives, time or topic limits, existing master tables or plans, and reference materials are optional inputs. Read them when supplied. Clarify ambiguity when it would materially change the subject or scope, rather than requiring a lengthy intake form.

If only a name is supplied, explore the person's publicly documented life and report the coverage actually achieved. Seek meaningful experiences and continuing processes rather than an inventory of everyday activities. Do not automatically restrict research to finance or impose predefined storylines. Follow explicit topic or period limits when supplied. Separate activity dates from publication dates: later retrospectives, interviews, and summaries are valid sources, with their retrospective nature identified; they do not automatically extend the activity scope.

Discover candidate storylines and events during initial research; the user need not provide them beforehand. When revising a confirmed plan, preserve stable IDs and confirmation states, distinguish additions from proposed boundary changes, and explain those changes. Keep the research plan focused on the current person, objective, scope, and findings. Do not create a separate intake report or require confirmation after every research step.

Use the [research plan template](assets/research-plan-template.md) for the main deliverable: person and scope, a storyline table, an event master table with individual descriptions, sources, gaps, and matters awaiting confirmation. Deliver the plan pending event selection and scope confirmation by default. A planning draft is not a final graph artifact.

Use `EPG-dataset/person-epg/` as the common root for all person research directories. Within the actual EPG-dataset checkout, create or reuse `<person_directory>/` and save `research-plan.md` there. Reuse an existing directory for the same person; name a new one with the person's established English name when available. For example, Warren Buffett's plan belongs at `EPG-dataset/person-epg/Warren Buffett/research-plan.md`. Create missing root and person directories as part of saving the deliverable. Preserve confirmed decisions and stable IDs when revising; do not create a second EPG-dataset inside FinMycelium.

Name storyline and event directories exactly as `storyline_name` and `event_name` in `events.csv`, without ID prefixes. Keep IDs in the catalog, plan, and directory-tree comments. Use distinct, filesystem-safe names within each parent; when renaming, update the plan, CSV, directories, and affected path references together.

Save the plan even when event selection is pending. Keep source downloads, caches, and logs in ignored working directories. Initially show a proposed storyline/event directory tree. After revision self-review, retain only events meeting step 3's planning conditions and create a directory for every retained event, preserving existing contents. Show the resulting directory tree in the plan. This preparation needs no separate directory approval; task confirmation and graph construction remain later steps.

At the same time, prepare `events.csv` from the [progress CSV template](assets/event-progress-template.csv), with one row per catalog event, and a short `README.md` from the [person entry template](assets/person-readme-template.md). Take IDs, names, storyline membership, and periods from the plan. New, unstarted rows use `planned`; unassigned owners and unavailable artifact paths stay blank.

After saving or updating the Source index, run `python <skill_directory>/scripts/export_sources.py <person_directory>/research-plan.md` to generate the adjacent `sources.csv`. Use the [export helper](scripts/export_sources.py); it runs offline with the Python standard library. The plan remains the sole source of truth: regenerate this CSV instead of editing it, and link it from the person README. It exports `source_id`, `title`, `url`, `publication_info`, `reading_note`, and `support_note`; publication information stays combined exactly as written in the index, without guessing a date or publisher. `--check` verifies that the export is current without writing files.

Use the CSV as the maintained progress index, with README navigation and any summaries based on it; detailed execution history belongs in run records. Reconcile updates by event ID, retaining actual progress, ownership, and artifact references. Explain catalog changes that affect those records. Progress states are `planned`, `in_progress`, `in_review`, `needs_revision`, and `accepted`; `accepted` denotes content/evidence approval and collection of the final JSON, Gantt, and review record. Artifact paths are relative to the person's directory and use `<storyline>/<event>/epg/` for reviewed JSON, Gantt and review records. The later workbench step maintains adopted search records under the event's `search/`; planning does not create those artifact files.

## Web research method

These are research responsibilities, not a fixed number of search rounds or a rigid sequence. Adapt queries and reading depth to the subject, available material, and user constraints.

### 1. Establish the person's research context

Resolve the name, aliases, important roles, and relevant organizations to avoid identity confusion. Use sourced biographical overviews, official disclosures, public interviews, historical records, and reliable reporting to understand significant experiences and changes within the requested scope.

Build an understanding of the subject before choosing categories. Do not impose a fixed biography outline and then search for material to fill every category. Model knowledge can help generate queries, but is not a source that has been checked.

### 2. Discover concrete events

Look for experiences with a continuing object, objective, or identifiable boundary, such as a particular investment, project, tenure, collaboration, charitable arrangement, or dispute. Record the person's actual connection to each matter instead of attributing every organizational action to the individual.

Follow names, organizations, projects, dates, agreements, and reporting leads found in the material. Seek sources covering different periods or perspectives. Read relevant page or document content; search titles and snippets are discovery leads, not automatically sufficient evidence.

An annual report, a meeting, or a shared date does not automatically make unrelated matters one event. Conversely, a continuing matter mentioned across years or multiple sources should not become duplicate events. If a meeting's own process is the research subject, assess its boundary as a candidate in its own right.

### 3. Assess candidate relevance and boundaries

For each event proposed for the plan, explain what it concerns, how the person participated or is connected, its approximate period, what belongs within its scope, which adjacent matters should remain separate, and what further research needs to establish.

Find traceable sources for these judgments. Investigate important or disputed attributions and scope decisions further. Prefer more direct material where possible, and do not count syndicated copies as independent corroboration. Judge the strength and relevance of support rather than imposing a fixed number of sources. One clear, direct source may suffice for planning; multiple syndicated articles may still leave attribution unresolved.

Distinguish observable actions, participants' public statements, media reporting, and research inferences. Do not treat a public statement as proof of private motivation or infer causation from chronology alone. Retain the date precision supported by the sources.

A candidate is ready to propose for user confirmation when:

- Read source material supports the existence of the concrete matter, beyond model memory or search titles.
- The person's connection is explainable and supported, distinguishing personal participation, role or responsibility, public statements, and organizational actions.
- The research scope is explainable: the matter, approximate period, main questions, and distinction from adjacent events.

Use `Public-source support` for candidates meeting these planning conditions. During initial research, `To verify` may mark unresolved existence, personal connection, or scope. By the end of revision, resolve the issue, narrow the event to a supported and usable scope, or omit it from the event table, event descriptions, CSV, and directory tree. If useful, briefly state the exclusion and its reason in coverage notes; do not create a deferred-task queue. Missing detailed actions, exact dates, or transaction terms can remain downstream research questions without preventing a supported planning candidate. This step does not need to acquire all evidence required by the Builder; source support is separate from user confirmation and graph acceptance.

### 4. Organize storylines and resolve duplication or overlap

Group the discovered events into storylines, explaining what each grouping covers and how it differs from the others. Revisit candidate groupings when new evidence changes the picture. Do not prescribe a fixed number of groups or invent matters to make the structure symmetrical.

Keep different years, reports, and phases of the same event together when appropriate. Similar names alone do not justify merging, and related matters need not be the same event. Assign each event one primary storyline in the master table. Describe connections across groups separately and choose a clear primary membership before delivery rather than duplicating the event.

If a confirmed plan needs a rename, split, or merge, propose the change and its reason explicitly. Do not silently replace stable IDs or expand a confirmed task's scope.

### 5. Review the plan and decide when to stop

Before delivery, make one substantive review across four areas:

- **Catalog and boundaries:** Check storyline groupings and events that may be duplicated, too broad, or unnecessarily fragmented.
- **Sources and personal connection:** Check that recommended events and the person's connection have support in read material; do not substitute organizational actions for personal actions.
- **Coverage and omissions:** Revisit the requested periods, roles, and topics. Check whether popular matters dominate the research or significant experiences remain unexplored. Use targeted follow-up research for important gaps, allowing new material to revise the initial interpretation.
- **Delivery consistency:** Check that the master table, event descriptions, IDs, and source references agree, and that supported findings, research leads, and decisions awaiting confirmation are distinguishable.

Repair specific problems and recheck affected content as needed. Repeated full reviews or a fixed number of PASS results are not acceptance criteria.

Distinguish topics not yet searched, searches with no results, access failures, insufficient public evidence, and conflicting sources. Failure to find material does not establish that an event did not occur. A research plan does not claim exhaustive knowledge of a person's life.

Stop research and deliver the plan for confirmation when the recommended events meet the planning-readiness conditions in step 3, overall coverage has been reviewed, and important gaps have been investigated or their unresolved status and reasons are stated. At final delivery, remaining event questions concern evidence details within usable scopes; unresolved planning leads belong only in brief coverage notes. Do not impose a universal event count or search indefinitely.

Respect the user's time and tool limits. If these limits or insufficient material prevent completion, deliver partial findings with the completed scope, unfinished work, and limitations identified; do not present a partial investigation as a completed coverage review.

## Revising an existing plan

Use this same skill and template for initial research and revisions. For a revision, re-read the current skill, template, and existing plan. Make one consolidated self-review across the four areas in step 5, identifying issues yourself even when no external review feedback is supplied. Retain useful findings and confirmed decisions.

Assess review feedback against the sources, scope, and planning-readiness conditions above; reviewer suggestions are not automatically required changes. Correct demonstrated factual, identity, citation, and handoff inconsistencies. Treat alternative groupings, event splits, or additions as research judgments, explaining material choices rather than requiring a particular catalog.

Use targeted follow-up and recheck affected content. The default planning cycle ends after initial research, one revision self-review, and directory preparation. Deliver the reviewed plan as the current research plan, retaining open questions for later event-level research. The goal is a usable research handoff; resolving every uncertainty about the person's life is not required. Do not automatically add another review or polishing round. Later updates should respond to user requests, significant new evidence, or concrete problems affecting use.

Finish revision by filtering the catalog using step 3, finalizing initial event IDs, and checking that every retained event has a matching description, CSV row, and directory. Do not carry unresolved planning candidates into the final event catalog or add another review round. Detailed evidence gaps within usable scopes can remain for downstream search. Summarize material changes, prepared directories, and remaining questions; no content change is required when none is justified. Keep proposed changes pending confirmation while preserving earlier confirmations as described below.

## Markdown deliverable requirements

Present the current research findings, scope, coverage cutoff, and substantive uncertainties concisely. Keep editing history in Git and delivery summaries, with adopted input snapshots in task records. Explain prior decisions only when they help the reader understand the current scope or an unresolved choice.

Follow the shared template, with detail proportional to the research subject:

- Person identity, research objective, overall scope, existing IDs, and the research coverage cutoff.
- A storyline catalog and an event master table containing retained events, with consistent names, periods, and primary memberships.
- Each event's cited overview, connection to the person, explicit research scope, further questions, search leads, and unresolved matters.
- Clickable sources and concise locators explaining what each source supports. Do not fabricate page visits, quotations, publication dates, or verification results.
- Actual research coverage, duplication or overlap decisions, and matters requiring user confirmation.

The final event catalog contains planning-ready events with `Public-source support`. This does not mean the user has selected or confirmed them, that construction evidence is complete, or that a graph has passed review.

The master table is an index; each event description follows the template's four core sections: Event overview, Connection to the person, Research scope, and Further research. Keep source-supported findings separate from proposed scope and unanswered questions. Use the shared source IDs beside factual statements and preserve useful findings already obtained; planning need not withhold known facts merely because detailed evidence acquisition happens later. Do not turn the overview into a speculative stage/action structure or treat it as a substitute for construction evidence.

State whether a selected period covers the whole event or only part of it. Ask specific follow-up questions without presupposing unverified actions or causes. Reuse the common person identity and source index, keeping event references consistent with the master table. Avoid independently maintaining the same catalog in multiple files. Include a compact `person → storyline → event` directory tree derived from the final catalog, with matching names, IDs, and primary memberships. Tree entries show names and ID comments only, without repeated source-support or existence statuses. Every retained event has a prepared directory; creation does not imply task confirmation. An additional overview diagram is optional.

## Stable identifiers and catalog mapping

Look up person identities in the current `EPG-dataset/person-epg/people.csv` and reuse registered IDs. Keep graph-internal IDs and any authorized identity migration mappings in task or catalog records; they are not research findings.

For newly registered entries, use:

| Object | ID convention |
| --- | --- |
| person | The dataset's person-registration convention, currently `PERSON-0001`, `PERSON-0002`, and so on. |
| storyline | `<person_id>-S0001`, with a sequence allocated within that person. |
| event | `<person_id>-E0001`, with a separate sequence allocated within that person. |

Check existing registrations before allocating IDs. For a new catalog, use provisional event IDs during research, then number the retained events consecutively from `<person_id>-E0001` through the final event count after revision. Number across the person, not separately within each storyline. Update the plan, cross-references, CSV, and tree together.

Once a catalog has been delivered and adopted, preserve its IDs; later regrouping, retries, or model changes do not renumber existing events. Do not overwrite IDs referenced by confirmed tasks or outputs to close a gap. An explicitly authorized reorganization retains an old-to-new mapping in local or task records, outside the research narrative. Store storyline membership separately from event identity.

Keep the following responsibilities distinct:

- **Research plan:** Candidate storylines and events, scopes, supporting sources, research questions, and confirmation records.
- **`EPG-dataset/person-epg/people.csv`:** Person registration, ownership, coverage, status, and research-plan links.
- **Each person's `events.csv`:** Event execution progress and accepted JSON/Gantt/review paths.
- **Each person's `sources.csv`:** Generated tabular export of the plan's Source index; event-to-source references remain in the plan.
- **Root and person `README.md` files:** Navigation to the registries, research plans, and collected outputs.
- **Task records:** Actual IDs, the adopted plan snapshot, inputs, configuration, outputs, and costs.

Carry names, memberships, and scope from the adopted plan into the catalogs; update execution and artifact status from actual work. Avoid separately maintaining full research descriptions in each location. Update navigation links when an authorized registration changes; avoid manually duplicating CSV progress data in Markdown. Creating directories and saving the research plan does not register its candidate events, migrate existing assets, or imply graph acceptance.

## Confirmation and handoff

Present the main storylines and events, significant uncertainties, and suggested research priorities. Priorities are recommendations, not a substitute for user confirmation. Focus user confirmation on the catalog, material boundaries, and priority tasks. Carry out routine searching, reading, and fact checking without per-step approval; seek clarification promptly when identity ambiguity or a material scope change would alter the research task.

The user may confirm only a subset of events. Record confirmed event IDs, scopes, and the actual confirmation basis in the same plan. Other planning-ready events remain unselected and do not block the confirmed subset. Confirmation does not upgrade source-support labels or imply graph acceptance.

Each downstream task retains the plan content and confirmed scope actually used in its run record, so later plan edits do not change ongoing work. Record agreed scope changes against the affected task. Git references or content hashes can support this traceability.

After confirmation, select one event from the same plan and hand off its confirmed `person_id / storyline_id / event_id`, names, cited overview, scope, connection to the person, research questions, source leads, and material unresolved issues. FinMycelium then performs formal search, input assembly, and construction for that task. Planning summaries and reference links do not replace actual construction evidence.

This skill delivers the research plan, prepared directories, event progress CSV, generated source CSV, and README entry after self-review, and the confirmed task description when available. Graph construction, final content review, and formal artifact collection belong to subsequent workflow steps. The project's integration layer handles field and interface mappings.

## Package resources and helper code

Keep research guidance and decision rules in this file and the shared output format in the template. If repeated formatting, ID-reference, or handoff checks later justify code, add it under this skill's `scripts/`. Put substantial supporting methodological guidance in `references/` when needed.

Helper scripts should solve concrete repeated tasks, not turn research into a hidden model API call. Keep the research instructions within this package. Executing this skill does not depend on FinMycelium's automatic planning or construction programs.
