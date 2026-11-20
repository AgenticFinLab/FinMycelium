# Event workbench

A local, single-user workspace for the event dataset workflow:

**Confirm scope → Search → Review material and freeze input → Build draft EPG → Review and revise → Accept and export.**

## Start

From the repository root, in the existing FinMycelium Python environment:

```bash
python -m finmy.workbench --port 8537
```

Open `http://localhost:8537`. The service listens on loopback only. Opening pages,
saving configuration and creating tasks do not call external services.
On first start, select the local EPG-dataset root; subsequent starts reopen its
workspace. The optional `--dataset-root /path/to/EPG-dataset` launcher argument
saves the same setting. Execution
requires a separate start action and permission to use external interfaces.

## Pages and daily operation

| Page | Responsibility |
| --- | --- |
| 数据集 (Dataset) | Choose **普通事件** or **人物事件**. Select a catalog event to inspect its scope, prepare a search or continue work on its materials and drafts. |
| 任务中心 (Tasks) | **运行记录** lists search and build tasks with their progress and results. **待处理** opens the next scope, material or graph review for local ordinary events and the specific person drafts selected for content review. |
| 设置 (Settings) | Select the local dataset, set reusable search and build defaults, and check which credentials are configured. |

For a standalone question or a batch of local ordinary events, open **任务中心 → 独立与批量检索**.
Selecting several events with confirmed scopes saves one task per event. Per-task overrides are available under **调整配置**.

For a person event, open the confirmed search handoff and review its material before saving a build task. The default Ark Kimi K3.1 Pro configuration uses low reasoning for per-source extraction, one full-handoff supplement and high reasoning for subsequent stages. It uses ordinary prompt-based JSON, up to 60 calls, 65,536 output tokens per call and 240,000 context characters. Extraction batches are 12,000 characters and local reading is capped at 60 reads and 160,000 characters total. Open **调整构建配置** to change this task. Saving freezes the selected handoff and settings. Start the build separately from its task detail.

Under **数据集 → 普通事件 → 本机事件记录**, the local event list opens a detail view when you select a row. **返回事件列表**
returns to the same filters. Use **显示 → 批量选择** for multi-event actions; additional
filters and column controls stay in the toolbar. The task list opens the selected run in a separate detail view.

Event details open the section appropriate to their current stage. Material and graph
review controls sit beside the content. Search creation shows the effective input
budget beside the research request, with advanced parameters expandable. Task details
separate **概览**, **资料与交接** and **运行记录**; recorded source counts and budget usage
are not completeness or quality scores. Simple searches without a complete-material
record show that absence explicitly. A document may contribute multiple input entries.

The launcher applies a workbench-only light theme. Shared presentation lives in
`finmy/workbench/ui.py` and `style.css`; it does not change other UIs or graph renderers.

1. Open **数据集 → 普通事件 → 本机事件记录** to import a CSV/XLSX master table or create an ordinary event. Confirm its research scope.
   The [event master](event-master.md) defines supported fields and relationships.
2. Start a search from the event, or select several events and choose batch search.
   Batch creation shares configuration, while each event retains its own scope,
   usage and outputs. It creates individual tasks; it does not silently start them.
   Search also accepts an independent research request without a master-table event.
3. In Tasks, start, pause or continue a search; use **重试** after a failure.
   Retry preserves the saved task and cumulative usage. Runtime records and results
   are visible there. Search completion means material is ready for inspection,
   not that evidence is exhaustive or approved. Detailed traces are expandable.
4. Inspect sources and the current budgeted handoff. New enhanced searches use
   the v3 evidence-priority policy with a default limit of 90,000 characters. The
   material panel shows the policy used for the selected revision. Advanced source selection is
   a preview until explicitly saved as the current handoff. Historical experiment
   viewing remains a separate read-only auxiliary tool.
5. Adopt material into the linked event and review the actual input under **资料与输入** in the local event record. Re-adopting a revised handoff deselects superseded passages from
   that task, retaining all original rows and reviews. Materials from other manual
   uploads remain available. Scope changes require a new search before adoption.
6. Approving evidence saves an immutable input snapshot with its hash and review ID.
   Material changes invalidate current approval without rewriting older snapshots.
7. Configure the EPG-dataset root in Settings, then create an AgentEventBuilder
   or SparseRagBuilder task from the confirmed input.
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
2. The workbench opens on **数据集**. Ordinary events come from `event-epg/events.csv`. The workbench reads bilingual names and coverage dates or the compact template’s event name and period. Person events
   come from `person-epg/people.csv`, the person's `events.csv`, and the matching
   event description in `research-plan.md`. Local imports and manual entries appear under **本机事件记录**.
3. Select an ordinary event from the catalog, or choose **人物事件**, select a person, and open an event in the storyline table. Preview its research description and source leads. For a person event, click **准备检索** or **重新检索** to open the form for that event. The
   activity period and included/excluded scope come from the catalog and research
   plan by default; edit only for an intentional scope change. Activity periods
   do not automatically filter publication dates.
4. For a new search, the scope and source leads are prefilled. The summary shows the effective model, providers and limits. Open **调整配置** for per-task overrides. Confirm the scope and destination. **保存检索任务** freezes the selected catalog
   identity, relevant plan text, source-file hashes, scope, and search configuration
   without execution. **确认并开始搜索** saves and explicitly starts the task when
   external calls are enabled. Both use the existing common search form and controller.
5. An ordinary catalog event shows its latest task under **继续工作** and offers **新建另一项检索**. A person event shows its collected material, graph status and run history together. Open a task for details, or use **重新检索** to prepare another search. Ordinary event tasks have local workbench scope records
   separate from their catalog IDs and can use the existing material-review path.
   Person tasks retain their person/storyline/event identity and can prepare a
   separate [native single-event build](person-event-build.md) after material
   confirmation. Each saved native draft has a [scrollable event graph](person-event-visualization.md)
   that can be regenerated from the JSON without model calls. Content review remains
   pending; no review Skill or automatic final acceptance is introduced.

Saving task-specific edits never modifies the source CSV or research plan. Later
catalog changes do not change existing task snapshots. Catalog status values do
not grant workbench scope, evidence, or graph approval.

### Automatic search summaries

On a terminal search outcome, the background worker generates an English summary
from saved records, without an additional model or Skill call. It saves locally
first and publishes under the dataset's Git-ignored output directory:

- Ordinary event: `output/search/event-epg/events/<event_id>/search-summary.md`.
- Person event: `output/search/person-epg/<person>/<storyline>/<event>/search-summary.md`.

Search completion does not change formal event directories. After input confirmation,
saving a build task collects an adopted search snapshot as described below.

The summary records the latest output, source URLs and acquisition states, input
counts, gaps/stop notes, and a short run index. Incomplete or failed searches retain
their actual status. Existing human notes outside the generated region are kept;
retries do not duplicate run entries, and an older retry does not replace a newer
output. The latest search output is separate from any adopted build input.

Task details show **数据集检索汇总**, its save path and this task's report. If dataset
publication fails, the local results remain available; **重新保存汇总** retries only
saving. Background saving does not require the page to stay open. It neither starts
construction nor marks a graph accepted, and never commits or pushes Git changes.
Independent searches do not publish a catalog summary; when a workbench dataset
is configured, they still export their task records under `workbench/search/`.

Search tasks retained only for comparison can be marked **不参与构建** in their task
panel. This reversible choice removes them from pending-material checks and has
its own task filter; retrieval status, material, usage and downloads remain intact.
Restore the task before starting it again or adopting its material for a new build.
Existing adopted material and build snapshots are unaffected. The choice and its
history are exported with the shared search records.

### Adopted search and reviewed graphs

Catalog-linked search material can be explicitly confirmed and collected before
creating a build. The event's `search/` saves the exact `builder-input.json`,
source index, summary and manifest. Saving a confirmed build continues to collect
its actual input. From **数据集 → 人物事件**, **用已收录材料创建构建** freezes the catalog copy
and its confirmation receipt for a new task. This also works on a checkout
without the producing search run. Starting that task is a separate action.
Original source downloads and unselected bodies remain ignored;
retries and reassembly never silently replace a collection.

Completed person drafts can be marked **舍弃** and later restored without changing
their execution status. After external content review, upload the version-bound
`review.md` and confirm collection of `epg.json`, `gantt.html`, and `review.md` to
`epg/`. The registry and the interface then recognize that accepted version.
Search and graph collections can be withdrawn with a reason; their exact bytes
are archived locally and lightweight receipts are retained.

See [Catalog collection and withdrawal](catalog-collection.md) for the controls,
review binding, protected files and distinction between collection and execution.
The content review Skill remains separate work. These actions never launch a
model and do not force partial output into draft or accepted status.

## Execution and recovery boundaries

- Search uses the existing controller and its cumulative limits. Pause waits for
  the active request to finish. See [search workflow](search-enhancement.md).
- Builds reuse the corresponding `configs/build_only_agent.yml` or
  `configs/build_only_sparse.yml` defaults, including call/time limits. Sparse
  retains local retrieval and `evidence_policy: report`. The workbench model field
  lets users select a model service and its model ID independently for search and
  construction. Saved configuration uses `provider/model`; bare IDs in older
  settings still mean Ark. TokenHub reads `HUNYUAN_API_KEY` and `HUNYUAN_BASE_URL`
  from the local environment. No key or endpoint is written to task settings.
  The interface shows credential presence without querying models or starting calls.
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

## Model selection

Search settings and search-task forms share one set of TokenHub presets. Build
settings, ordinary event builds and person-event builds share another:

| Purpose | Display name | TokenHub model ID |
|---|---|---|
| Build | GLM-5.3 | `glm-5.3` |
| Build | Kimi K3.1 Pro | `kimi-k3.1-pro` |
| Build | DeepSeek V4 Pro 0813 (direct supply) | `deepseek-v4-pro-202606` |
| Build | Hy4 | `hy4` |
| Search | GLM-5.3-Flash | `glm-5.3-flash` |
| Search | DeepSeek Flash (direct supply) | `deepseek/deepseek-flash` |

Select **Tencent TokenHub**, then the desired preset. Saved model names have the
`tokenhub/` prefix; the API receives the exact ID above, including any `/` inside
it. **自定义** remains available and preserves previously saved custom models.
Switching model service requires a model selection; existing defaults and budgets
are not overwritten. All TokenHub models use the configured regional base URL and
key. Presets are not a live account availability check.

The shared model adapter applies the following sampling policy to these presets
in search, person-event builds and ordinary Agent/Sparse builds. It overrides
inherited `temperature` / `top_p` values, including those in `extra_body`.

Ark presets use the [official Agent sampling recommendation](https://console.volcengine.com/ark/region:cn-beijing/docs/agent-model-invocation-practice):

| Ark model ID | temperature | top_p |
|---|---|---|
| `doubao-seed-2-0-pro-260215` | 1.0 | 0.95 |
| `doubao-seed-2-1-lite-260915` | 1.0 | 0.95 |
| `glm-5-2-260617` | 1.0 | 0.95 |
| `deepseek-v4-pro-ga-260813` | 1.0 | 0.95 |
| `deepseek-v4-1-flash-261017` | 1.0 | 0.95 in thinking mode; 1.0 when disabled |

Seed 2.0 Pro fixes these values server-side. For DeepSeek V4.1 Flash, explicit
`thinking.type=disabled` or `reasoning_effort=none` selects `top_p=1.0`; the adapter
preserves the caller's thinking controls. With the OpenAI Python SDK, put the
nonstandard `thinking` object in `extra_body`. The thinking-mode value of 0.95 follows
the Agent recommendation, rather than the no-tools service default of 1.0. See the
[Chat API model exceptions](https://docs.volcengine.com/docs/ark/chat-api?lang=zh) and
[thinking controls](https://docs.volcengine.com/docs/ark/deep-thinking?lang=zh).
Legacy bare Ark IDs use the same policy. Person-event builds obtain sampling from
the adapter; they do not impose a separate temperature on the selected model.

| TokenHub models | temperature | top_p | Basis |
|---|---|---|---|
| `glm-5.3`, `glm-5.3-flash` | 1.0 | 0.95 | Model-specific recommended defaults |
| `deepseek-v4-pro-202606`, `deepseek/deepseek-flash` | 1.0 | 1.0 | Recommended temperature and platform-default top_p |
| `hy4` | 0.9 | 1.0 | Model guide's temperature and platform-default top_p |
| `kimi-k3.1-pro` | Fixed 1.0 | Fixed 0.95 | Omitted from requests as recommended by the model guide |

See the [GLM guide](https://cloud.tencent.com/document/product/1823/132061),
[DeepSeek guide](https://cloud.tencent.com/document/product/1823/132248),
[Hy4 guide](https://intl.cloud.tencent.com/zh/document/product/1300/80695),
[Kimi guide](https://cloud.tencent.com/document/product/1823/132232) and
[platform parameter defaults](https://cloud.tencent.com/document/product/1823/135872).
Unlisted model IDs retain their supplied sampling configuration, or service
defaults when no sampling parameters are supplied.
The direct adapter falls back to 8192 output tokens. For new Kimi person Event
tasks, the builder selects low effort for extraction and high effort for the
remaining stages. See the [person Event build settings](person-event-build.md).

For TokenHub Kimi K3.1 Pro, the adapter sends the configured output limit as
`max_completion_tokens`. It uses `reasoning_effort` for optional thinking-depth
control; Kimi's older `thinking` controls are rejected before a request.

## Storage, provenance and export

The configured EPG-dataset owns workbench runtime data and shared task records.
SQLite and original material remain ignored; portable JSON/CSV records belong in
Git. FinMycelium retains only an ignored local pointer at
`output/workbench-location.json`. An explicit `FINMY_WORKBENCH_HOME` still selects
a custom runtime directory, with shared records exported to its configured dataset.

```text
EPG-dataset/output/                 ignored runtime and drafts
  workbench/
    workbench.sqlite3
    dataset.json                   local dataset-root setting
    search/                        original material, versions, input and traces
      profile.json                 reusable search defaults
    builds/                        worker coordination
    record-exports/                export success/failure status
  search/<catalog-event-path>/search-summary.md
  builds/<BUILD-or-PBUILD-task-id>/
    input.json                     frozen actual input
    config.json, snapshot.json     Builder settings and provenance
    worker.log
    output/                        ordinary Builder artifacts and run manifest
    attempts/                      person-event JSON, Gantt and checks
EPG-dataset/workbench/              portable records for Git
  search/
    README.md                      generated task index: event, model, status, input size
    <YYYYMMDD-HHMMSS>_<event-name>_<short-task-id>/
      task.json                    identity, scope, configuration and fingerprints
      summary.json                 execution status, usage, gaps and input manifest
      sources.csv                  source URLs and acquisition/input status
  build/
    README.md                      generated index: event, model, status and source search
    <YYYYMMDD-HHMMSS>_<event-name>_<BUILD-or-PBUILD-task-id>/
      task.json, summary.json
  events/<workbench-event_id>/
    event.json                     editable record and revision history
    sources.csv, graphs.json       indexes, not original source or graph bodies
    reviews.json                   decisions and frozen-input manifests
  plans/<task_id>.json              legacy plans, separate from executions
```

Saving tasks, search completion/pause and committed workbench edits or reviews
refresh their shared records without a model call. Missing token/cost reports
remain unknown. Settings → **更新共享记录** retries export without rerunning tasks.
Search and build record names use creation time in Asia/Shanghai and remain stable across
retries and configuration/status changes. Full task IDs and ignored runtime paths
are unchanged; old ID-only shared folders migrate when exported.
Frozen collection manifests retain their historical contents and hashes; their
build task IDs resolve through the build index even when an old path was renamed.
New collection manifests use the readable build-record path directly.

After a build task is successfully saved, its exact search handoff is displayed as
**已确认用于构建** rather than **待检查材料**. This is derived from saved confirmation,
handoff revision and input hash, without changing the search execution status.
Failed or cancelled builds retain material confirmation. Reassembling a new handoff
requires confirmation of that new version. **不参与构建** overrides participation
without deleting previous confirmations or saved builds. Shared search records
and their index reflect the same decision; no additional review action is required.

Export failures preserve saved work and appear in Settings. Shared records support
inspection and provenance; they are not a full runtime backup or instructions to
start/approve work. They omit source bodies, raw responses, credentials and absolute
machine paths. Git commits and pushes remain explicit actions.

For a legacy workspace, close the service before moving its entire runtime tree.
Preserve the SQLite file and task directories together, verify any saved absolute
artifact references, then select the dataset. Startup detects the old database
instead of silently creating an empty replacement. Selecting another dataset keeps
the previous workspace intact and requires active runs to finish first. Each build
retains its frozen artifact path. Formal collection remains separate.

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
  tests/test_search_budget.py tests/test_workbench_storage.py
```

These checks cover preserved data, approval invalidation, immutable inputs,
Agent/Sparse input preflight, draft attribution after input changes, failed workers
and explicit execution gates. They do not certify live model availability or final
EPG content quality.

## Offline person-event completion

Open the finished person build from **任务中心 → 运行记录** and expand **检查与收尾**.
The panel shows how much of the input was read, the structural error count and
the outstanding records. Repeated extraction attempts for the same retained fact
appear together. Select an item to inspect its sources and original passages.

- **Retain a Context with a gap.** Select the supported Context and describe
  what the sources establish and which part remains unknown.
- **Decline a proposed change to supporting evidence.** Compare the existing
  fact, evidence and gaps with the proposed citations. You can keep the fact
  and its current support when the proposal only resubmits that fact or tries
  to mix quoted record contents with a claim about what happened. Read and
  acknowledge any associated correction notes individually.
- **Keep a matter open.** If a citation deserves incorporation, the record is
  ambiguous or other work is outstanding, leave it pending. **下载本次收尾清单**
  exports the version, artifact references, check results and pending proposals
  for offline review.

Enter a reason and reviewer name, then choose **保存处置并重新检查**. Each save
creates a successor under the run's `revisions/`, records the decision and
preserves the parent artifacts. The workbench rechecks the graph, remaining
material and pending work without search or model calls. Only a run that meets
all completion checks becomes a draft. Content review and catalog collection
follow separately.

After an offline revision, further model construction uses a new task from the
confirmed input. Resuming old model checkpoints must not overwrite a human
revision or silently discard its dispositions.
