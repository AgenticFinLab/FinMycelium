# Focused regression suite

Tests prioritize observable results, saved evidence, and recovery. Production code
and JSON fixtures are unchanged by this test-only cleanup. Test Python shrinks
from 24,539 to 17,033 lines; 23 redundant modules are retired.

## Coverage owners

| Boundary | Maintained tests |
| --- | --- |
| Person facts, organization and export | `test_person_fact_pipeline`, `test_person_canonical_acceptance`, `test_person_canonical_organization`, `test_person_canonical_full_flow` |
| Single-event build and replay | `test_sparse_rag_builder_full_flow`, `test_sparse_rag_builder_replay_regression`, `test_sparse_runtime_entry`, `test_epg_validation` |
| Resume without searching or repeating accepted work | `test_person_canonical_recovery`, `test_sparse_person_recovery`, `test_storyline_search_resume`, `test_resume_event_enrichment` |
| Agent scheduling, budgets and source reuse | `test_event_search_scheduling`, `test_initial_storyline_search`, `test_shared_event_sources`, `test_failure_isolation_flow` |
| Search failures and partial evidence | `test_search_failure_isolation`, `test_search_phase_isolation`, `test_search_interrupted_finalization`, `test_search_seed_failure_isolation` |
| Source identity, quotes and handoff | `test_source_documents`, `test_search_source_provenance`, `test_pipeline_source_handoff`, `test_search_build_contract`, `test_security_counterparty_grounding` |
| Optional enrichment, item repair and fuzzy dates | `test_event_refinement`, `test_event_enrichment_repair`, `test_event_enrichment_temporal`, `test_event_additions_temporal` |
| Schema, HTML and old result compatibility | `test_person_epg_contract`, `test_person_epg_validation`, `test_person_epg_visualizer`, `test_person_cli_rendering`, `test_subject_graph_recovery` |
| User entry points | `test_person_pipeline_app`, `test_enhanced_subject_ui`, `test_search_workbench`, `test_workbench_ui` |

The old SubjectGraph semantic-review matrix, prompt wording checks, estimator
checks, and repeated helper-level validation permutations are intentionally
reduced. Legacy import/render/build smoke checks remain. This is a smaller
coverage policy, not a claim that every removed assertion has an exact replacement.

When fixing a regression, extend the owning behavioral test or add a small case
there. Create another module only for a genuinely distinct public boundary.
Do not duplicate the same rejection in helper, adapter and full-flow suites.
Keep a captured failure when synthetic input would miss the actual failure shape.
Shared test setup must remain available to its importers; pruning test methods
does not authorize deleting their fixtures or setup helpers.

## Running

With project and test dependencies installed, run from the repository root:

```bash
python -m pytest tests
```

The provider adapter tests require the real `lmbase` package, while responses and
network calls are mocked. `sparse_test_dependencies` supplies containers only; it
cannot validate a missing provider implementation. Rendering and SQL tests use
the committed `fixtures/buffett_person_epg_preview.json`, not optional examples.

Cleanup validation ran each of the 121 remaining modules in an isolated process
with outbound socket connections blocked: 700 tests passed. Six modules need
the unavailable full `lmbase` dependency in that environment; the same failures
were reproduced before pruning. They remain in the suite, without new skips or
relaxed assertions. Live model quality was not evaluated.
