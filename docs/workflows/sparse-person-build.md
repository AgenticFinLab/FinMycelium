# Sparse RAG person construction

Use `configs/search_pipeline.yml` for the full pipeline with `SparseRagBuilder`.
The current branch's `configs/pipline.yml` still explicitly selects the legacy
builder; a local copy must select Sparse explicitly to run this workflow.
Person reconstruction uses the seven existing sparse roles,
then organizes their extracted facts into the existing `person-epg-3.0` contract.
The schema, fixed Buffett JSON and HTML renderers keep their existing formats.
The rendering-routing follow-up is based on PR #18 commit
`28fad8fda4e5f04ab8ee0151bf2c3f6a3c5e68e4` and connects the native renderer
introduced in `a712ece7279bac790063c5a35a2ac3c94cef9265`.

Apply from the repository root on that commit or a compatible descendant:

```sh
git apply --check FinMycelium_person_html_routing_fix.patch
git apply FinMycelium_person_html_routing_fix.patch
```

The follow-up changes result routing and export selection. Public schemas,
existing JSON data, HTML/JS assets and renderer implementations remain unchanged.
The Buffett fixture is a byte-for-byte copy of the supplied preview.

## Direct source-text input

Use `configs/person_sparse.yml` as a complete builder configuration. Set the model,
output limits and `builder_config.reconstruction.subject` for the intended person,
period and topic before execution. All sparse roles and the organization step use
the same configured backend. The organization call and invalid-output retries count
toward `max_calls`; a completed graph is still a draft requiring content review.

Input keeps the existing `BuildInput` shape: `user_query` plus nonempty `samples`
containing `sample_id`, `raw_data_id` and the exact source `content`. The supplied
`buffett_person_epg_preview.json` is an output fixture, not source-text input.

```sh
# Offline validation and credential-presence check; no model request.
python -m finmy.runner.sparse_build_runner \
  --config configs/person_sparse.yml --input path/to/BuildInput.json

# Execute reconstruction from the supplied sources.
python -m finmy.runner.sparse_build_runner \
  --config configs/person_sparse.yml --input path/to/BuildInput.json \
  --env-file .env --execute --gantt

# Offline reconstruction of saved results, with artifact integrity checks.
python -m finmy.runner.sparse_build_runner --replay output/person-sparse/build_output_RUN_ID
```

This entry does not fetch sources, install dependencies or manufacture missing
evidence. Follow [Sparse RAG setup](sparse-rag-build.md) for runtime installation.
`report` preserves structurally valid drafts with evidence diagnostics; `strict`
blocks unresolved quotes. Quote location does not prove semantic support.

## Existing saved-content and Web entry

The existing person backend now chooses the configured builder, defaulting to
Sparse when `builder_type` is omitted. Explicit `AgentEventBuilder` still selects
the legacy person path. Company mode requires the legacy builder; a configuration
that explicitly selects Sparse for company reconstruction is rejected.

The saved-content CLI keeps its existing list-of-strings input:

```sh
python -m finmy.subject_graph.runner \
  --config configs/search_pipeline.yml \
  --scope-config configs/person_buffett_oxy.scope.yml \
  --input path/to/builder_input_contents.json \
  --query 'Reconstruct Buffett’s documented involvement in the Occidental investment.'
```

This command calls the model immediately. The direct sparse entry above provides
the explicit preflight/`--execute` workflow. Saved-content input preserves the
provided strings but cannot recover source URLs or publication metadata absent
from those strings; use the full BuildInput entry to retain source registration.

## Results and compatibility

- `FinalEventCascade.json` preserves the seven-role reconstruction.
- `FinalPersonEPG.json` contains the existing normalized facts, evidence, domains,
  events, stages, activity membership and supported activity links.
- `FinalSubjectGraph.json` is a display projection for the existing person view;
  it is not a replacement for the full Person EPG.
- `FinalPersonEPG.html` uses the native hierarchical renderer over the complete
  Person EPG. CLI `--gantt` writes the same format to `gantt.html`.

Web results prefer `BuildOutput.extras.person_epg`, then fall back to the legacy
SubjectGraph/Event paths when a Person EPG is absent. Historical directories
prefer `FinalPersonEPG.json` over `FinalSubjectGraph.json` and `FinalEventCascade.json`.
Explicit file selection still opens exactly that file. Invalid Person EPG data
is reported rather than silently replaced with a legacy projection.

Existing completed results can use the new renderer without additional model calls:

```sh
python -m finmy.person_epg render path/to/FinalPersonEPG.json --output person_timeline.html
```

The organizer references existing fact IDs. It does not invent actors, transactions,
dates or background occurrences to fill a hierarchy. Unassigned activities remain
in the factual package; optional stage assignments may be null. A model-generated
activity relation requires its own supporting evidence.

Do not export a Person EPG to the old display format and then import it back to
save the result: the old format has no slots for the complete organization.

## Fixed regression fixture

The Buffett preview is preserved at `tests/fixtures/buffett_person_epg_preview.json`
with SHA256
`ce9b0ed055f39fedfd4fda91d93dc55954b0504814199e6e4b6143213032c20c`.
It covers 35 actions, 3 transactions, 7 background activities and 9 activity links.
Only 25 of its 276 evidence spans have document offsets. Tests preserve those
locations and the unresolved state of the remaining evidence, without inventing
source documents.

```sh
python -m unittest discover -s tests -p 'test_sparse_person*.py' -v
python -m unittest discover -s tests -p 'test_sparse_estimate_time.py' -v
python -m finmy.person_epg validate tests/fixtures/buffett_person_epg_preview.json
```

These offline checks cover interface and execution behavior. Assess generated
facts and automatic organization separately against the original source material;
do not provide the expected fixture organization as the model's answer input.

The lifecycle tests sequence synthetic model responses through the actual builder,
organization, grounding, serialization and replay code. When `lmbase` is absent,
`tests/sparse_test_dependencies.py` supplies container classes only; it cannot
initialize a model transport. The tests do not claim to validate the real provider
adapter or live model output. Install the repository's documented runtime before
executing a live reconstruction.

Patch verification on 2026-11-08: 56 new offline tests passed. A selected regression
run covering the new tests plus existing schema, display, evidence and Sparse
execution tests passed 250 tests (124 subtests). Five tests were excluded from that
combined run: four `GroundingIntegrationTest` cases need the unavailable real
`lmbase` adapter, and the missing legacy example test described below. This is not
a claim that the repository's entire test suite or live model integration passed.

The base commit has a separate failing legacy example test:
`test_person_epg_contract.py::PersonEPGContractTest::test_example_loads_and_all_views_execute`
expects the absent `examples/data/person_epg/buffett_oxy.json`. This failure was
reproduced on the unmodified base commit. The supplied preview is intentionally
kept as its own fixture rather than substituted for that missing example.
