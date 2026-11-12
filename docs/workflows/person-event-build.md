# Build one person event

The dataset workbench can pass a reviewed search result to a native person-event
build. A task reconstructs exactly the confirmed `person / storyline / event`.
It uses the Person EPG storage contract (`person-epg-3.0`), independently of the
ordinary AgentEventBuilder and SparseRagBuilder event paths.

## Workbench flow

1. Select a person event in **数据集**, confirm its scope, and run common search.
2. Open the search task's material view. Inspect the saved originals, budgeted
   input, omissions and gaps. In **构建本条人物 event**, choose the build model and
   confirm the actual material. **保存人物构建任务** creates a frozen task without calls.
3. In **任务中心**, explicitly allow model calls and choose **开始人物构建**.
4. Inspect the draft JSON and its standalone Gantt, checks, source handoff and
   call records. A completed execution is still a draft requiring content review.

Search configuration and build configuration remain separate. The workbench
exposes the build model, cumulative call limit (40), output token limit (12,288)
and per-call context-character ceiling (160,000). JSON validation retries allow
at most three attempts per phase; the per-call timeout is 900 seconds. These
are execution limits, not quality targets. No step increases the confirmed input
material budget or performs external supplementary search.

The material confirmation freezes the search handoff revision, exact sample text,
source versions and hashes, catalog identity, research scope and source registry.
Later search reassembly does not rewrite that build task. Activity periods remain
textual scope guidance when they do not provide exact boundaries; they are not
publication filters and are not padded to invented dates.

## Construction and recovery

```text
Confirmed event + original input
  -> source-bound factual occurrences, actions and transactions
  -> reconcile identity and duplicate facts
  -> place relevant activities in the fixed event
  -> supported stages, summary and activity relations
  -> native JSON + structural/evidence reports -> standalone event Gantt
```

The layout is determined from confirmed IDs. There is no event-discovery or
whole-person layout call. Source-grounded facts that remain unassigned retain a
reason; the program does not manufacture a new event to place them. `storyline_id`
is stored in Hu's native `domain_id` field. This mapping preserves the public
schema while using the agreed terminology in task preparation.

Recovery preserves accepted factual checkpoints and reusable organization replies.
Input, code, model settings, checkpoint hashes and saved draft integrity are checked.
An explicit recovery can raise the cumulative call ceiling, but never resets used
calls. Changed inputs or implementation require a new task. Earlier draft attempts
remain available. A hard call/context limit stops further submissions; it is not
a quality certificate. Provider failures and incomplete phases are recorded as
failed, partial or insufficient outcomes rather than silently treated as success.

Quote alignment verifies retained text locations, not truth or semantic entailment.
Unresolved quotations are reported for review. The ordinary Sparse evidence policy
and search implementation are unchanged.

## Files

Native build artifacts stay in the ignored experiment area by default:

```text
.local-experiments/person-epg/<task_id>/
  input.json
  config.json
  snapshot.json
  state.json
  canonical-checkpoint.json
  PersonOrganizationCheckpoint-Result.json
  attempts/0001/
    epg.json
    gantt.html
    checks.json
    ... phase outputs and evidence reports
```

The task database and worker coordination remain in the existing workbench
workspace. Original downloaded documents remain in search storage; the input and
provenance identify which saved text was used. No automatic final-graph collection,
CSV status update or Git operation occurs. Content-review automation and a review
Skill are deferred; the workbench keeps the result as a draft pending review.

## Standalone Gantt

Every saved completed or partial draft is rendered independently. The expanded
stage/activity timeline uses the original full event visualizer's Plotly style,
participant symbols and relation styling. It reads native Person EPG tables;
activities are not converted into EventCascade episodes. This is a single-event
view, with no storyline/event/stage collapsing or whole-person aggregation.

Activity rows retain action, transaction or context identity. Participant and
transaction arrows occupy a separate lane, where positions do not imply dates.
Stage spans are derived from dated member activities. Unknown times stay visible
without assigned dates; month/year precision and time windows remain intervals.
The record selector also exposes retained, unassigned facts and relations that
cannot be placed on the timeline. Selecting a record shows its fields, original
quotes, source links and offsets in the actual retained input.

The HTML includes Plotly and opens offline. Its graph and file hashes are recorded
in `state.json`, so the workbench only shows HTML matching the saved JSON. A
rendering failure preserves the draft and build status. **从已保存 JSON 重新生成 Gantt**
regenerates only the visualization, without search/model calls or changes to
recorded model usage. Both JSON and HTML remain drafts pending content review.

## Implementation

The native schema, canonical fact logic, evidence binding, bounded organization
and checkpoint reuse derive from Hu's `feat/person-epg-yuntao` at
`77a234d882b305fa08c70bbaa545526ba0d67e37`. The schema files are retained unchanged;
serialization and time/evidence helpers are extracted from their former modules.

The implementation under `finmy/person_epg/` adapts those components to a fixed
single event and an independent build-only entry. It does not import Hu's research
discovery runner, whole-person orchestration, compatibility EventCascade export
or collapsible visualization. Public search remains under `finmy/search/`.

## Offline checks

From the repository root, using the project environment:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider \
  tests/test_dataset_catalog.py tests/test_dataset_summary.py \
  tests/test_dataset_workbench.py tests/test_person_event_build.py \
  tests/test_person_event_gantt.py tests/test_person_event_workbench.py
```

The tests use temporary catalogs, synthetic sources and injected model responses.
They check scope/input identity, source references, recovery, budget retention,
summary saving and JSON/Gantt consistency without real search or model calls.
They do not establish real-case content quality, coverage or cost.
