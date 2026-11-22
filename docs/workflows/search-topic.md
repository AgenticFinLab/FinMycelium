# Task-scoped original-text retrieval

Apply this patch after `person-search-eval-ee60d3be.patch`, on
`person-epg-muhan` at `9c61d4c2b251eb2d0af29816e574fdecccef4588`.
It changes the first three agreed components: task constraints, virtual topic
windows, and entity/attribute lexical selection with bounded context.
The existing task JSON and eval command still work:

    python -m finmy.search.eval --task examples/search_eval/buffett_goldman.json

The eval code fingerprint creates a separate run after this algorithm change.
Existing checkpoints without a retrieval plan keep their existing reading and
handoff policy. Historical complete manifests replay their recorded policy.
No extra model calls, embeddings, judge changes or Builder stages are added.

New tasks derive and save positive entity names, scope facets, exclusions and
activity dates from the supplied task. They appear in search-model context.
The deterministic first version uses supplied names, proper-name patterns and
small general lexical synonym groups; it does not claim general entity linking.
Tasks without a usable positive name keep existing search behavior. Publication
dates are not restricted by the activity period.

Candidate views follow original paragraphs, complete sentences and table rows.
Headers and source-local dates remain located originals. Standalone page numbers
and clear navigation/newsletter text are omitted from candidates. Local entity
and attribute evidence qualifies a candidate; numbers and generic investment
words alone do not. Neighbors require topic continuity, pronoun linkage or a
short uncertainty qualification. A mixed-issuer passage containing target
evidence is allowed. Validated priority spans retain precedence over lexical
selection, and explicit cursor reading remains available for indirect evidence.

Original source files, block IDs, versions, checksums and read accounting are
unchanged. New handoffs record original block/start/end ranges and omitted ranges;
complete source material is still available. Search budgets remain unchanged.

Offline checks:

    python -m pytest -q tests/test_search_topic.py tests/test_search_eval.py

The attached implementation was also replayed against the supplied Buffett run,
using its existing original text, priority marks and fixed Judge labels. This
isolates material selection, not a new end-to-end web search. The existing eval
rubric limitations still apply; no Judge labels are consulted by the algorithm.
