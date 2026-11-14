# Build one person event

A task reconstructs one confirmed `person / storyline / event`, using
`person-event-1.0` and the [engineering contract](../person-event-builder/0-overview.md).
The ordinary AgentEventBuilder and SparseRagBuilder paths retain their own protocols.

## Workbench flow

1. Configure the local EPG-dataset path, select an event in **数据集**, confirm its scope, and run common search.
2. Inspect retained material, actual builder input and gaps. Under **构建本条人物 event**, choose the independent build model and limits, then confirm the material. **保存人物构建任务** freezes the task without model calls.
3. In **任务中心**, explicitly allow calls and select **开始人物构建**.
4. Inspect JSON, expanded Gantt, checks, source handoff and cumulative calls. Execution, completeness and rendering have separate statuses. A draft still requires content and evidence review.

Choose the model service and its console model ID separately. TokenHub uses
`lm_name="tokenhub/<console-model-id>"`, with local `HUNYUAN_API_KEY` and
`HUNYUAN_BASE_URL` (HTTPS origin or `/v1` base). Search and construction may select
different model services. TokenHub thinking models can count reasoning toward the
output limit; a truncated response remains incomplete, with reported usage retained.
Provider selection does not enable external search inside construction.

The workbench exposes model, cumulative calls, per-call output tokens and context
characters, extraction batch size, local reading limits and the optional repair round.
Defaults live in `EventBuildConfig`: 40 model calls, 12,288 output tokens, 160,000
context characters, 12,000-character body batches with 400-character overlap,
24 local reads and 48,000 cumulative read characters. A local read returns at most
4,000 text characters; local search returns at most four snippets. Metadata also
counts toward the cumulative read-character budget. JSON attempts are capped at
three per semantic task, transport timeout at 900 seconds, and final repair at one round.

These are limits, not quality targets. Character counts are not token counts.
Search and build settings remain separate. Construction does not add external
sources or increase the confirmed input budget.

## Construction and recovery

```text
Freeze identity, scope, source metadata and actual input
  -> extract candidates across every handed body range
  -> exact deduplication and scoped semantic consolidation where needed
  -> jointly organize Stage / Phase and assign each Action
  -> complete typed relations and baseline / delta Context
  -> assemble, check, optionally repair once -> JSON and Gantt
```

Four semantic roles propose scoped records or operations. The program assigns IDs,
locates quotes, checks references and applies independent valid groups. Rejected
neighbors remain in step responses and pending reports. Models can read upstream
records and frozen sample ranges; later roles can retrieve local snippets. They
cannot modify input, write files or perform external search. Local retrieval does
not replace initial continuous body extraction.

Calls are durably reserved before submission. Format retries, tool follow-up calls,
repair and resumed calls share the cumulative limit. Missing usage stays unknown;
no unsupported monetary cost is reported. Transport failures do not automatically
refund or repeat calls.

**准备恢复构建** may raise the cumulative call ceiling. Used calls and per-task format
attempts remain. Response checkpoints require matching input, implementation,
prompt, semantic configuration and upstream dependencies. Corrupt responses are
rejected. Changed input or code requires a new run. Previous attempts remain
available, and restarting does not renew the final repair allowance.

Unprocessed body ranges, unassigned actions and failed required work produce a
partial result. Legal unknowns, gaps and explicit conflicts may remain in a
structurally complete draft. Quote matching proves location, not semantic entailment.
Checks explicitly list what was not evaluated.

## Files and direct use

Workbench artifacts use the configured dataset's ignored `output/builds/`.
Its SQLite and search originals live in `output/workbench/`; portable task and
execution records are exported to `workbench/` for Git review (see
[workbench storage](event-workbench.md#storage-provenance-and-export)).
Direct Python calls default to FinMycelium's ignored `output/builds/`:

```text
<output_root>/builds/<run_id>/
  input.json
  config.json
  provenance.json
  state.json
  checkpoints/
  attempts/0001/
    facts.json
    epg.json          # when a graph exists, including a marked partial graph
    checks.json
    gantt.html
    steps/
```

When the user confirms the material and saves a workbench build task, its fixed
search record is collected into the catalog event's `search/` (`search-summary.md`,
`sources.csv`, `manifest.json`, `builder-input.json`). The input JSON preserves the exact
confirmed payload, including text and person/source metadata, with hashes in the manifest.
Runtime output remains in the paths above.
After content and evidence review, collect final `epg.json`, `gantt.html`, and
`review.md` under the event's `epg/`, then update accepted paths in `events.csv`.
Saving or executing a build does not perform graph acceptance.

The workbench also retains its task snapshot. Provenance preserves supplied search
handoff records, source versions and hashes alongside exact input and sample hashes.
Acquisition, handed ranges and processed ranges are distinct: obtaining a source
does not mean its full text was read. Originals remain in search storage.

```python
import json
from pathlib import Path
from dotenv import load_dotenv
from finmy.person_epg.build import run_event
from finmy.person_epg.event.runtime import EventBuildConfig

load_dotenv('.env', override=False)
payload = json.loads(Path('confirmed-input.json').read_text())
state = run_event(payload, config=EventBuildConfig(), allow_network=True)
```

An explicit directory may be supplied. Use the same directory and `resume=True`
to recover it. Without an injected offline model, execution requires
`allow_network=True`; saving a task grants no such permission.

No build writes to the accepted `person-epg/` catalog, changes CSV execution status,
performs Git operations or invokes a content-review Skill. Formal collection and
whole-person aggregation remain separate work.

## Gantt and historical graphs

Standalone HTML includes Plotly and opens offline. It expands
**Event → Stage → Phase → Action**. Each interval comes from that record's supported
time. Occurrence windows and durations use distinct marks. Unknown times remain in
a separate visible group; partial results are labeled.

The record selector exposes Context, effective baseline/exclusion/delta associations,
support modes, gaps, conflicts, relations, original quotes, source links and sample
offsets. Conflicting precedence claims remain inspectable but do not define the
consistent order view. Display omissions do not delete graph records.

JSON, checks and HTML bind to the same exact graph-file bytes. Rendering failure
preserves graph and build status. **从已保存 JSON 重新生成 Gantt** only redraws the
saved graph, without model calls or changes to usage.

Historical `person-epg-3.0` graphs retain their validator, hash interpretation and
renderer. They are not silently converted. Their checkpoints cannot resume in the
new protocol; rebuilding creates a new task from confirmed original input. The
separately named legacy builder entry supports offline regression of historical assets.

## Offline verification

Using the project environment from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider \
  tests/test_person_event_contract.py tests/test_person_event_runtime.py \
  tests/test_person_event_adoption.py tests/test_person_event_pipeline.py \
  tests/test_person_event_rendering.py tests/test_person_event_build.py \
  tests/test_person_event_gantt.py tests/test_search_build_contract.py
```

Tests use the authored design example, synthetic responses and temporary directories.
They verify contracts, ownership, quote alignment, partial adoption, limits, recovery
and artifact correspondence without real search or model calls. They do not establish
real-case content quality, coverage or cost.
