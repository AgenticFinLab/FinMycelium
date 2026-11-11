# Event workbench

A local, single-user workspace for the event dataset workflow:

**Confirm scope → Search → Review material and freeze input → Build draft EPG → Review and revise → Accept and export.**

## Start

From the repository root, in the existing FinMycelium Python environment:

```bash
python -m finmy.workbench --port 8537
```

Open `http://localhost:8537`. The service listens on loopback only. Opening pages,
saving configuration and creating tasks do not call external services. Execution
requires a separate start action and permission to use external interfaces.

## Pages and daily operation

| Page | Responsibility |
| --- | --- |
| 数据集 (Dataset) | Read the configured EPG-dataset catalog, select one ordinary or person event, confirm scope and prepare a search. |
| 事件数据 (Data) | Maintain the master table, confirm an event's scope, inspect its current step and initiate the next action. |
| 新建检索 (Search) | Create an individual or batch of search tasks with reusable defaults and per-run overrides. |
| 任务中心 (Tasks) | One list of actual search and build runs; select one to inspect progress, inputs and results. |
| 待审 (Review) | Review material and graph versions, record decisions and preserve revisions. |
| 设置 (Settings) | Configure the local dataset root, separate search defaults from Builder defaults, and inspect credential presence. |

The event list opens a separate detail view when you select a row. **返回事件列表**
returns to the same filters. Use **显示 → 批量选择** for multi-event actions; additional
filters and column controls stay in the toolbar. The task list selects its detail
view directly and refreshes the list and detail from the same state snapshot.

Event details open the section appropriate to their current stage. Material and graph
review controls sit beside the content. Search creation shows the effective input
budget beside the research request, with advanced parameters expandable. Task details
separate **概览**, **资料与交接** and **运行记录**; recorded source counts and budget usage
are not completeness or quality scores. Simple searches without a complete-material
record show that absence explicitly. A document may contribute multiple input entries.

The launcher applies a workbench-only light theme. Shared presentation lives in
`finmy/workbench/ui.py` and `style.css`; it does not change other UIs or graph renderers.

1. Import a CSV/XLSX master table or create an event. Confirm its research scope.
   The [event master](event-master.md) defines supported fields and relationships.
2. Start a search from the event, or select several events and choose batch search.
   Batch creation shares configuration, while each event retains its own scope,
   usage and outputs. It creates individual tasks; it does not silently start them.
   Search also accepts an independent research request without a master-table event.
3. In Tasks, start, step, pause or continue a search. Runtime records and results
   are visible there. Search completion means material is ready for inspection,
   not that evidence is exhaustive or approved. Detailed traces are expandable.
4. Inspect sources and the current budgeted handoff. Advanced source selection is
   a preview until explicitly saved as the current handoff. Historical experiment
   viewing remains a separate read-only auxiliary tool.
5. Adopt material into the linked event and review the actual input under Data →
   Material/input. Re-adopting a revised handoff deselects superseded passages from
   that task, retaining all original rows and reviews. Materials from other manual
   uploads remain available. Scope changes require a new search before adoption.
6. Approving evidence saves an immutable input snapshot with its hash and review ID.
   Material changes invalidate current approval without rewriting older snapshots.
7. Create an AgentEventBuilder or SparseRagBuilder task from the confirmed input.
   Select its model independently of search. Creating a task saves input, scope,
   model/configuration and code fingerprints, with no model call. In Tasks, inspect
   the snapshot, allow model calls and explicitly start the build.
8. The build-only worker runs in a separate process. It does not perform search.
   On success it imports a draft graph bound to the exact saved input and records
   its run directory, elapsed time and reported model usage. It never approves the
   graph. If materials changed during execution, the draft remains bound to the old
   input and cannot pass review against the new one.
9. Inspect graph content and evidence; save revisions with a parent version and
   review the result. Only current scope, evidence and graph approvals permit final
   export. A valid file, completed run or visualization is not semantic acceptance.

Existing evidence can be uploaded directly and existing graphs can be imported;
search and build are not mandatory repetitions. Imported graphs require explicit
confirmation that they correspond to the event and its current input. Supplementary
search creates another task; it does not erase earlier originals or approvals.

## Select an event from EPG-dataset

1. In **设置 → 接口与工作区**, save the local EPG-dataset root. This is a path on
   the machine running the workbench, shared by ordinary and person events.
2. Open **数据集**. Ordinary events come from `event-epg/events.csv`; person events
   come from `person-epg/people.csv`, the person's `events.csv`, and the matching
   event description in `research-plan.md`. An empty catalog stays empty: there is
   no fallback to `data/events/`. Existing upload/manual-entry workflows remain available.
3. Select an event, optionally filtering a person's events by storyline. Preview
   the planning description, cited source leads, and summary destination. Adjust
   the activity period and included/excluded scope for this task. Activity periods
   do not automatically filter publication dates.
4. Confirm the scope and destination. **保存检索任务** freezes the selected catalog
   identity, relevant plan text, source-file hashes, scope, and search configuration
   without execution. **确认并开始搜索** saves and explicitly starts the task when
   external calls are enabled. Both use the existing common search form and controller.
5. Follow the task in **任务中心**. The dataset page also lists earlier searches
   for the selected event. Ordinary event tasks have local workbench scope records
   separate from their catalog IDs and can use the existing material-review path.
   Person tasks retain their person/storyline/event identity and can prepare a
   separate [native single-event build](person-event-build.md) after material
   confirmation. Each saved native draft has an expanded single-event Gantt;
   it can be regenerated from the JSON without model calls. Content review remains
   pending; no review Skill or automatic final acceptance is introduced.

Saving task-specific edits never modifies the source CSV or research plan. Later
catalog changes do not change existing task snapshots. Catalog status values do
not grant workbench scope, evidence, or graph approval.

### Automatic search summaries

On a terminal search outcome, the background worker generates an English summary
from saved records, without an additional model or Skill call. It saves locally
first and publishes to the selected event:

- Ordinary event: `event-epg/events/<event_id>/search-summary.md`.
- Person event: `person-epg/<person>/<storyline>/<event>/search-summary.md`.

The summary records the latest output, source URLs and acquisition states, input
counts, gaps/stop notes, and a short run index. Incomplete or failed searches retain
their actual status. Existing human notes outside the generated region are kept;
retries do not duplicate run entries, and an older retry does not replace a newer
output. The latest search output is separate from any adopted build input.

Task details show **数据集检索汇总**, its save path and this task's report. If dataset
publication fails, the local results remain available; **重新保存汇总** retries only
saving. Background saving does not require the page to stay open. It neither starts
construction nor marks a graph accepted, and never commits or pushes Git changes.
Unlinked independent searches keep their existing local-only behavior.

## Execution and recovery boundaries

- Search uses the existing controller and its cumulative limits. Pause waits for
  the active request to finish. See [search workflow](search-enhancement.md).
- Builds reuse the corresponding `configs/build_only_agent.yml` or
  `configs/build_only_sparse.yml` defaults, including call/time limits. Sparse
  retains local retrieval and `evidence_policy: report`. The workbench model field
  currently accepts Ark model/endpoint IDs, consistent with its existing settings.
- Build inputs and approval are checked again before execution. If source code
  changed after task creation, create a new task against that version.
- Builds currently support cancelling an unstarted task, not pausing a running
  model workflow. Page changes do not stop the worker. Failed/interrupted tasks are
  never automatically replayed. Ordinary event builds require a fresh task;
  native person-event builds support explicit checkpoint recovery with cumulative
  usage retained, as described in [person event construction](person-event-build.md).
- Batch search preparation is supported. Automatic batch build scheduling and its
  concurrency controls are not connected. Legacy task plans remain in a separate
  history section for inspection or cancellation, never treated as actual executions.
- Provider-reported usage is retained; missing token or monetary information is not
  represented as zero. Credential presence is not a connectivity check.
- Catalog-linked person events use the native single-event construction path.
  Choosing a person/company target in a standalone search does not by itself
  create that catalog association or change the ordinary event Builder.

## Storage, provenance and export

SQLite records are stored in the Git-ignored `output/workbench/` directory.
Set `FINMY_WORKBENCH_HOME` to use another ignored local workspace. Existing tables
are preserved; input snapshots and build tasks use additive tables.

```text
output/workbench/
  workbench.sqlite3
  dataset.json                    local dataset-root setting
  search/                         task originals, versions, input and traces
    profile.json                  reusable search defaults
  builds/BUILD-.../
    input.json                    frozen actual input
    config.json, snapshot.json    Builder settings and provenance
    preflight.json, worker.log
    output/                       native Builder artifacts and run manifest
```

Event exports include master records, source records, input snapshots, review
history, search summaries, build records and all graph revisions. `FinalEPG.json`
appears only after current scope, evidence and graph approval. Exported run paths
point to local artifacts; back up the entire workspace separately to retain raw
responses and complete native traces. Stop active runs before backing up.

Credentials remain in `.env` or process environment variables and must not be
included in source control. Local databases, raw evidence, responses, runs and
machine-specific notes stay ignored. This is a single-user local workbench, not an
authenticated shared-server service.

## Offline verification

In the existing environment, without real search or model calls:

```bash
python -m pytest -q -p no:cacheprovider \
  tests/test_workbench.py tests/test_workbench_workflow.py \
  tests/test_search_control.py tests/test_search_document_handoff.py \
  tests/test_search_budget.py
```

These checks cover preserved data, approval invalidation, immutable inputs,
Agent/Sparse input preflight, draft attribution after input changes, failed workers
and explicit execution gates. They do not certify live model availability or final
EPG content quality.
