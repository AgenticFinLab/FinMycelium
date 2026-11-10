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
| 事件数据 (Data) | Maintain the master table, confirm an event's scope, inspect its current step and initiate the next action. |
| 新建检索 (Search) | Create an individual or batch of search tasks with reusable defaults and per-run overrides. |
| 任务中心 (Tasks) | One list of actual search and build runs; select one to inspect progress, inputs and results. |
| 待审 (Review) | Review material and graph versions, record decisions and preserve revisions. |
| 设置 (Settings) | Separate search defaults from Builder defaults; inspect credential presence. |

The event list opens a separate detail view when you select a row. **返回事件列表**
returns to the same filters. Use **显示 → 批量选择** for multi-event actions; additional
filters and column controls stay in the toolbar. The task list selects its detail
view directly and refreshes the list and detail from the same state snapshot.

Event details open the section appropriate to their current stage. Material and graph
review controls sit beside the content. Search creation shows the effective input
budget beside the research request, with advanced parameters expandable. Task details
separate **概览**, **资料与交接** and **运行记录**; recorded source counts and budget usage
are not completeness or quality scores. Historical searches without a complete-material
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
   a preview until explicitly saved as the current handoff. Saving a preview preserves
   the search status, pause reason and ability to continue. Historical experiment
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
confirmation that they correspond to the event and its current input. Additional
research can be started as an independent search task; construction never triggers
post-build enrichment, and earlier originals and approvals remain preserved.

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
  never automatically replayed; a fresh task is an explicit potentially paid run.
- Batch search preparation is supported. Automatic batch build scheduling and its
  concurrency controls are not connected. Legacy task plans remain in a separate
  history section for inspection or cancellation, never treated as actual executions.
- Provider-reported usage is retained; missing token or monetary information is not
  represented as zero. Credential presence is not a connectivity check.
- Independent searches support event and person targets through the agent. This
  workbench builds single-event graphs; use the [person pipeline](../person_mode.md)
  for native person reconstruction from a name and period.

## Storage, provenance and export

SQLite records are stored in the Git-ignored `output/workbench/` directory.
Set `FINMY_WORKBENCH_HOME` to use another ignored local workspace. Existing tables
are preserved; input snapshots and build tasks use additive tables.

```text
output/workbench/
  workbench.sqlite3
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
