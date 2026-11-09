# Source context budget

The search Agent selects relevant sources. The former standalone relevance classifier
has been removed; neither its configuration nor archived CORE/CONTEXT/REVIEW labels
can drop or reorder selected material.

`source_documents.prepare_documents` archives unchanged source bodies, assigns document
IDs and retains URL, publication metadata, source ID/version and event routes. It also
writes the declared request and reconstruction scope needed by resume. No model is called.

Initial and supplementary evidence retain separate 120,000-character budgets. Metadata
and excerpt wrappers count toward the limit. Each source receives a seed allocation
before long documents expand; supplementary event allocation alternates events and
search phases. Event terms prioritize exact source windows. Other long sources use the
shared search BM25 block ranker with the original request, keywords and retrieval queries.
The allocator records exact raw-text character ranges; routing and ranking are not
factual verification. Evidence validation and enrichment review remain independent.

```yaml
all_content_config:
  max_content_length: 120000
  max_document_chars: 12000
  min_document_chars: 2000
```

Outputs: `retrieved_documents.json`, `context_budget_report.json`,
`builder_input_contents.json`, `event_profile.json`, `reconstruction_profile.json`.
Supplementary source archives live in `event_enrichment/sources/`.

To repack saved material without model calls:

```bash
python -m finmy.runner.context_budget --input-dir RUN_DIR --max-chars 120000
```

The CLI prefers `retrieved_documents.json` and accepts an old `filtered_documents.json`
as a fallback. It does not load old relevance decisions. The allocator's old positional
`decisions` argument remains accepted but is ignored, for callers replaying old archives.
Old `relevance_filter` and `event_followup.max_relevance_*` settings may be removed;
leaving them in an existing YAML cannot enable classification or block enrichment.
