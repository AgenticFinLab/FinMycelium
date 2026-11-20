# Person Event: run, resume, inspect and render

This is the current operations guide. Older patch-named documents describe the
history of individual changes; a checkout containing these changes does not need
those patch files. Extraction, evidence equivalence, adoption and conflict rules
are unchanged by the engineering cleanup.

## Run once

From the repository root, place the original corpus in `input.json`. Install the
project and lmbase as described in the main README; keep provider credentials in
`.env`.

```bash
RUN="output/event-$(date +%Y%m%d-%H%M%S)"
python -m dotenv -f .env run -- python - "$RUN" <<'PY'
import json, sys
from pathlib import Path
from finmy.person_epg.event.build import run_event
state = run_event(json.loads(Path('input.json').read_text()), directory=sys.argv[1],
                  allow_network=True, stop_after_organization=False)
print({k: state.get(k) for k in ('execution_status', 'result_status', 'output', 'reason')})
PY
```

## Inspect without spending API credits

```bash
python -m finmy.person_epg.event.status "$RUN"
python -m finmy.person_epg.event.status "$RUN" --json
```

The report separates the latest attempt, its failures, effective budgets and
historical artifacts. `latest_hierarchy_artifact` is the most recent rendered
graph containing both Stage and Phase records; this is a display property, not
a claim of semantic completeness. A later failed attempt does not replace that
reference. `latest_rendered_artifact` can contain an incomplete hierarchy.
Evidence merge counts are printed with their attempt path.

Errors include the provider exception type, HTTP status, request ID and retry
eligibility. Each failed call has a separate `CALL-xxxxxx-error.json`; local
exceptions include stack locations without locals or raw SDK messages. The
existing `transport` fields and task reason codes remain available to consumers.
For 401/403, inspect credentials, provider permissions or account balance before
resuming. Increasing budgets cannot resolve authentication failures.

## Resume

Stop an existing worker before running:

```bash
python -m dotenv -f .env run -- \
  python -m finmy.person_epg.event.resume_transport "$RUN" --allow-model \
  --extra-calls 60 --extra-read-calls 40 --max-read-rounds 4
```

`--extra-calls` ensures at least that many model requests remain. Similarly,
`--extra-read-calls` ensures additional read deliveries remain. `--max-read-rounds`
raises the total per-task allowance; already spent rounds are retained.
`--extra-read-chars N` increases the existing unique-character budget by N.
Repeatedly specifying it adds another N characters.

The current transport defaults are 900 seconds total per request, 60 seconds
without output growth, and five transport retries. These defaults are defined
once in `event/config.py`; resume entry points use its shared resolver. The
evidence-only entry point retains its saved total timeout, as before. Progress
prints once per minute. The CLI shows effective limits, including extensions;
historical semantic request bodies remain unchanged for checkpoint reuse.

The exact PR #25 head `4df5d0a` can resume through this engineering upgrade without
reissuing completed matching model requests. The original response dependency
identity is retained; the running implementation identity is recorded separately.
Ordinary resume still rejects unrelated implementation changes. Pure graph
renderer and status-command edits are excluded from the execution fingerprint;
rendering continues to record its own dependency digest.

## Evidence-only replay and offline HTML

```bash
python -m finmy.person_epg.event.evidence_consolidation "$RUN" --saved-review-only
python -m finmy.person_epg.event.graph_html \
  "$RUN/attempts/0004/epg.json" -o "$RUN/attempts/0004/graph-sources.html"
```

Use the attempt path reported by `status`, rather than assuming the latest
attempt is the one to present. Saved-review-only requires matching review
checkpoints; it never falls back to a paid request.

## Offline regression checks

```bash
python -m pip install -r requirements-event-tests.txt
python scripts/check_person_event.py
```

The CI job runs the same existing Event suite plus operational regression cases.
The two lmbase SDK integration modules (`test_person_event_effort.py` and
`test_person_event_json_mode.py`) are excluded from this lightweight job; run them
in a full project environment with lmbase installed. No API credentials are
required for the offline job. All domain checks continue to use saved fixtures
or injected models.
