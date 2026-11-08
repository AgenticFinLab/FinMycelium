# Sparse RAG person construction

The standard `configs/pipline.yml` and `configs/search_pipeline.yml` now select
`SparseRagBuilder`. Person reconstruction uses the seven existing sparse roles,
then organizes their extracted facts into the existing `person-epg-3.0` contract.
The schema, fixed Buffett JSON and HTML renderers keep their existing formats.
This patch is based on PR #18 commit
`e6e3b51e2cce4b5c75fefe41b419e12a0581d057`.

Apply from the repository root on that commit or a compatible descendant:

```sh
git apply --check FinMycelium_sparse_person_default.patch
git apply FinMycelium_sparse_person_default.patch
```

No dependency, public schema, existing JSON, HTML, renderer or Web UI files are
changed. The included Buffett fixture is a byte-for-byte copy of the supplied
preview. This patch does not push commits or publish a deployment.

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
  --config configs/pipline.yml \
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
- The existing renderer can produce `FinalSubjectGraph.html`. It displays the
  facts supported by its current interface; it does not gain new Domain/Stage
  rendering features from this patch.

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
