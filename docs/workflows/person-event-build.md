# Build one person event

For current CLI commands, effective budgets, errors and saved artifacts, see
[run, resume, inspect and render](person-event-operations.md).

A task reconstructs one confirmed `person / storyline / event`, using
`person-event-1.0` and the [engineering contract](../person-event-builder/0-overview.md).
The ordinary AgentEventBuilder and SparseRagBuilder paths retain their own protocols.

## Workbench flow

1. Configure the local EPG-dataset path, select an event in **数据集**, confirm its scope, and run common search.
2. Inspect retained material, actual builder input and gaps. Under **构建本条人物 event**, choose the independent build model, output mode and limits, then confirm the material. **保存人物构建任务** freezes the task without model calls.
3. In **任务中心**, explicitly allow calls and select **开始人物构建**.
4. Inspect JSON, the interactive event graph, checks, source handoff and cumulative calls. Execution, completeness and rendering have separate statuses. A draft still requires content and evidence review.

Choose the model service and its console model ID separately. TokenHub uses
`lm_name="tokenhub/<console-model-id>"`, with local `HUNYUAN_API_KEY` and
`HUNYUAN_BASE_URL` (HTTPS origin or `/v1` base). Search and construction may select
different model services. TokenHub thinking models can count reasoning toward the
output limit; a truncated response remains incomplete, with reported usage retained.
Provider selection does not enable external search inside construction.

Person builders receive streaming responses for all configured model services.
Reasoning chunks keep the connection active but are not mixed into the JSON answer.
Only a normally exhausted stream with `finish_reason=stop` and a nonempty text
answer proceeds to JSON validation; interrupted, truncated, refused and tool-call
responses never create a successful response checkpoint. Reported cumulative usage
is retained once, and missing usage remains unknown. There is no automatic retry
or fallback to a second non-streaming request.

Call records retain transport phase, chunk/character counts, first-chunk and total
elapsed times, finish reason, available request/response IDs and HTTP status.
Failures also retain exception class names along the cause chain. Diagnostics
exclude raw error messages, URLs, headers, credentials and reasoning text.


The workbench exposes model, cumulative calls, per-call output tokens and context
characters, extraction batch size, local reading limits and the optional repair round.
Ark build presets are Seed 2.1 Pro, Seed Evolving, DeepSeek V4 Pro and Kimi K3.1 Pro.
A workspace without saved build settings selects `ark/kimi-k3-1-pro-261024` by default;
saved workspace preferences and existing task configurations remain authoritative.
The native `EventBuildConfig` uses the same default model.
Search presets and TokenHub choices are independent. Historical model IDs remain
usable through the custom model field. The output mode, reasoning policy and
construction limits are saved when the task is created.

**模型输出模式** defaults to **普通（提示词约定 JSON）**: each role is prompted to
return JSON, without an API `response_format` override. For Ark Kimi K3.1 Pro,
**API JSON 模式** sets `api_json_mode=True` and sends
`response_format={"type":"json_object"}` on every role call, including reading
follow-ups and repairs. This is an API format constraint, not a full graph schema
or evidence guarantee. Both modes use the same prompts, validation, budgets,
sampling and thinking settings; a rejected request does not silently fall back.
The choice is saved in task configuration, step requests, call records and
checkpoint dependencies. Historical tasks without the flag use ordinary mode.
To compare modes, create two new tasks from the same confirmed input and current
implementation, with identical model and limits; change only this option. Switching
mode requires a new task, not a resume of the other mode's checkpoints.

For new Ark and TokenHub Kimi K3.1 Pro tasks, **构建思考档位** defaults to
**按阶段（当前全部 low）** in the workbench and the Python entry point.

| Build stage | API `reasoning_effort` |
|---|---|
| Extract facts from each body range | `low` |
| Consolidate actions and organize Stages and Phases | `low` |
| Discover relations, assign Context and perform the final targeted repair | `low` |

Read follow-ups and corrections use the effort of their owning stage. For a
comparison run, select a fixed `low`, `high` or `max`, or select **服务端默认**
to let the provider choose. Other models use the service default.

The task configuration stores the policy (`reasoning_effort="by_stage"` for
the Kimi default). Each step request and call record stores the actual effort.

Set `extraction_workers=6` for up to six in-flight requests (default one, maximum
10). A coordinator owns the task states, a FIFO queue, and persisted events;
workers only perform model transport. Extraction ranges, disjoint consolidation
groups and relation scopes run within their stage. Reading follow-ups, JSON
corrections and semantic corrections re-enter the same queue and share its limit.
A slow request does not block adoption of other responses. The next stage starts
when the current stage's tasks have reached terminal states.

A timeout, incomplete completion, or exhausted response correction allowance marks
that task failed. Other tasks continue. Transport failures are not automatically
retried in the same invocation; resume retries them while reusing accepted work.
A transport failure in organization blocks relations. Rejected hierarchy proposals
may first use the existing targeted organization repair; relations wait for a
usable hierarchy. A failed relation scope leaves
other scopes available. Local context limits affect their own tasks; exhausted
run budgets produce `execution_status=limit`. Otherwise a completed run with
failures has `execution_status=finished`, `result_status=partial`.

`state.json` includes `events`, `task_states`, and `stages`. Task states include
`queued`, `running`, `waiting_read`, `retrying`, `processing`, `succeeded`,
`failed`, `limited`, `blocked`, `paused`, and `interrupted`. Call records separate
`queued_at` from `started_at`. `checks.json.task_failures` lists failed, limited,
and blocked tasks. Completed stages have hashed snapshots under `checkpoints/`;
partially completed stages reuse per-call checkpoints and saved responses.
Storage/integrity/program errors still stop the run. Pause stops dispatch and
retains in-flight replies for resume.

Apply this incremental patch after the FIFO and readable-sample patches, and use
a new run directory. Existing runs have a different code fingerprint. The input
file remains the original frozen builder `input.json`.

Offline state-machine smoke check (no model calls, no pytest):

```bash
python -m finmy.person_epg.event.state_machine_smoke "$OLD/input.json" \
  --output "output/state-smoke-$(date +%Y%m%d-%H%M%S)"
```

Expected: one failed timeout task, two succeeded tasks, one local read, and
`passed: true`. This checks scheduling and failure isolation, not graph semantics.
For a real end-to-end run, reuse the previous input and configuration in a new
output directory:

```bash
PREV="$RUN"
RUN="output/e2e-events-$(date +%Y%m%d-%H%M%S)"
python -m dotenv -f .env run -- python - "$PREV/input.json" "$PREV/config.json" "$RUN" <<'PYRUN'
import json, sys
from pathlib import Path
from finmy.person_epg.event.build import run_event
state = run_event(json.loads(Path(sys.argv[1]).read_text()),
    directory=sys.argv[3], config=json.loads(Path(sys.argv[2]).read_text()),
    allow_network=True, resume=False, stop_after_organization=False)
print({k: state.get(k) for k in
       ('execution_status', 'result_status', 'output', 'checks', 'reason')})
PYRUN
```

The policy is part of the checkpoint identity. Resume uses the saved policy,
including the provider default for historical tasks with a missing or null
effort. Choose a new task to change the policy. The output mode and call limits
are configured separately.

Defaults live in `EventBuildConfig`: 40 model calls, 12,288 output tokens, 160,000
context characters, 12,000-character body batches with 400-character overlap,
24 local reads and 48,000 cumulative read characters. A local read returns at most
4,000 text characters; local search returns at most four snippets. Metadata also
counts toward the cumulative read-character budget. JSON attempts are capped at
three per semantic task, transport I/O timeout at 900 seconds, and final repair at one round.

`max_read_rounds=2` allows at most two reading follow-ups per semantic task.
Each response containing a batch of valid `read_requests` spends one round,
regardless of its number of pages. Corrections and resume share the same durable
round budget. A third request for reading marks only that task `limited` with
reason `read_rounds`; other tasks continue and adopted records remain available.
Format/correction budgets are unchanged. Set `max_read_rounds=0` to disable follow-ups.
When copying an older run configuration, explicitly override `timeout` to `900`
and `max_read_rounds` to `2`; an explicit saved timeout overrides the default.
The timeout remains the existing transport I/O timeout, not a new task deadline.

These are limits, not quality targets. Character counts are not token counts.
The context cap includes instructions, task metadata and serialized records, not just
the extraction batch. A `model_context_chars` stop can happen before the first API
request; inspect attempted calls before attributing it to the model service.
The standard resume control raises cumulative calls only, not the context cap.
For an unstarted task saved with the wrong context budget, create a new task from
the same confirmed input with the intended settings.
Search and build settings remain separate. Construction does not add external
sources or increase the confirmed input budget.

## Construction and recovery

New runs save `organization-snapshot.json` before the first joint relation and
Context task. Its fingerprint binds the input, facts, hierarchy and source run.
For a comparison, run the same snapshot into separate fresh directories. Each
run records its delivered evidence and per-action review in the step requests
and `relation-discovery.json`. Unresolved upstream proposals must be dealt with
before using the isolated replay command.

```bash
python -m finmy.person_epg.event.relation_experiment run "$SNAPSHOT" \
  --output output/joint --config relation-settings.json --allow-model
python -m finmy.person_epg.event.relation_experiment review output/joint \
  --output output/joint-reviewed --allow-model
```

The optional review spends at most two model calls. The first call sees the
actions and located quotations without candidate or accepted edges. The second
receives the same evidence, the independent findings, the named edge endpoints
and their Context associations. The review records proposed additions,
corrections, withdrawals and uncertainties, then applies validated changes to
a separate graph. The successor includes the frozen facts, coverage, outstanding
dispositions, graph checks and a Gantt bound to its graph hash. Follow
`state.json` to the graph and `review.json` for the parent hashes and decisions.
A partial parent can yield a comparison but requires its own outstanding work
to be resolved. A draft
still goes through the event content review. Kimi uses `low` for this
independent assessment unless the review configuration specifies an override.

```text
Freeze identity, scope, source metadata and actual input
  -> extract candidates across every handed body range
  -> optional single full-handoff supplement
  -> exact deduplication and scoped semantic consolidation where needed
  -> jointly organize Stage / Phase and assign each Action
  -> complete typed relations and baseline / delta Context
  -> assemble, check, optionally repair once -> JSON and Gantt
```

The optional `full_corpus_supplement` runs after the fresh continuous reads and
before consolidation. It sends all handed documents with an index of existing
facts in one request, within the common call and context limits. With Kimi's
staged effort it runs at low. Its receipt records the character count, accepted
or rejected proposals, or the reason it was skipped. New person Event builds enable this pass by default. Clear the checkbox in the
workbench or set `full_corpus_supplement=False` in Python to skip it. Saved tasks
use their recorded setting. Tasks predating the option keep it disabled.

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
rejected. Preparation and startup reject a changed workbench implementation before
queuing a worker. Changed input or code requires a new run. Previous attempts remain
available, and restarting does not renew the final repair allowance.

The backend also contains narrowly scoped, explicit migrations for record-reading
and relation-task repairs. These require verified predecessor code and artifact
hashes, preserve prior attempts and record the migration before ordinary resume.
They are not a general code-mismatch bypass or a workbench control for arbitrary
budget changes; unsupported changes still require a new task.

For a run stopped by output truncation, an explicit backend `output-limit-v1`
preparation may increase only `max_new_tokens` for the verified preceding
implementation. It retains original state/configuration, requests, checkpoints and
usage; an offline replay must reach the same unfinished step with identical adopted
facts and graph before publication. It does not start a worker. After preparation,
the ordinary resume/start controls apply. This does not change global defaults or
permit input, model, prompt or other budget changes.

While a person build is queued or running, **暂停构建** requests a stop between
model calls. The current response, validation and checkpoint publication finish;
no next request, format retry or local-reading follow-up is submitted after the
pause boundary. Wait for **已暂停** before shutting down. If the last required call
finishes the build, it may complete normally instead. A transport failure remains
a failure rather than being hidden as a pause. **准备恢复构建** followed by an explicit
start reuses valid checkpoints and retains cumulative usage. Closing the interface
alone does not pause its independent worker.

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

Native builds save a standalone scrollable event graph in `gantt.html`.
Stage and Phase navigation opens action, context and evidence cards. Readers
can follow a relation across Phases and expand a source to inspect its quoted
text. The workbench preview and download show the same HTML. See the
[interactive viewer](person-event-visualization.md) for layout and navigation.

JSON, checks and HTML bind to the same exact graph-file bytes. **从已保存 JSON
重新绘图** regenerates the saved view locally and preserves the graph, calls
and build status. A drawing failure is recorded independently of construction.

Historical `person-epg-3.0` graphs retain their validator, hash interpretation and
renderer. They are not silently converted. Their checkpoints cannot resume in the
new protocol; rebuilding creates a new task from confirmed original input. The
separately named legacy builder entry supports offline regression of historical assets.

## Interactive EPG visualization

Use the [standalone EPG guide](person-event-visualization.md) to export a saved event,
inspect evidence, or verify the fixed slide layout locally.

## Offline verification

Using the project environment from the repository root:

```bash
7z x '/path/to/PBUILD-dee74d7e4a1d(1).7z' -o'/tmp/person-event-real'
PERSON_EVENT_REAL_RUN_DIR=/tmp/person-event-real/PBUILD-dee74d7e4a1d \
  PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider \
  tests/test_person_event_real_run.py
```

The real-run test reads the original `input.json`,
`attempts/0004/epg.json` and `attempts/0004/facts.json` in that extracted
directory. Keep these three files exactly as extracted. It checks the frozen
input's SHA-256 and validates the original single-source Evidence records. It makes no model calls and writes nothing to the run directory.

For the broader offline unit suite:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider \
  tests/test_person_event_contract.py tests/test_person_event_runtime.py \
  tests/test_person_event_adoption.py tests/test_person_event_pipeline.py \
  tests/test_person_event_rendering.py tests/test_person_event_build.py \
  tests/test_person_event_gantt.py tests/test_search_build_contract.py
```

The broader unit suite uses the authored design example, synthetic responses and
temporary directories to verify contracts, ownership, quote alignment, partial
adoption, limits, recovery and artifact correspondence. The real-run regression
checks provenance and structural compatibility, not historical content quality,
coverage or cost.

## Collection decisions

Search material can be confirmed and collected independently of build creation.
Stopped drafts can be discarded or restored; reviewed person Event graphs can be
explicitly collected and withdrawn with version-bound records. See
[Catalog collection and withdrawal](catalog-collection.md). Runtime status and
content acceptance remain separate.
