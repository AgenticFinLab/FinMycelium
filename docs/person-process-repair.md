# Person process construction and repair

This change applies on top of the English/Chinese-source and relaxed-stopping
patches (local base c88d51b). Apply the single diff with git apply; it is not a
mailbox patch. Search settings and the public Person EPG schema are unchanged.

## Execution

1. The discovery plan (event IDs, scopes and questions) reaches SkeletonReconstructor
   and SkeletonChecker as metadata. It is never quoted as factual evidence.
2. Before extracting participants/transactions, review each supplied document in
   overlapping 16,000-character windows against the original checked skeleton.
   Collect proposed occurrences without modifying that skeleton. Reconcile all
   candidates globally before extraction, with output decisions batched by 16.
   Every batch sees all candidates, their quoted evidence and the original skeleton.
   Classify findings as existing-scene details, corroborating evidence, aliases of
   another candidate, genuinely new occurrences, or deferred ambiguities. Resolve
   forward aliases before assigning final IDs. Preserve notes/quotes from every
   merged candidate. Names alone do not establish identity; genuinely separate
   transactions can have identical names. There is no episode-count cutoff.
   Failed/invalid reconciliation decisions stay in the audit as deferred; good
   independent decisions and original scenes remain usable.
3. After extraction, review activities in batches of 16 with all facts and original
   sources available. Apply local actor, action/status, time and detail corrections.
   Dates may remain fuzzy or unknown; a normalized date need not literally occur
   in the quotation. The quotation must exist in a source.
4. Canonicalize duplicate actions/transactions before organization. Preserve unique
   details and union evidence when merging. Explicitly evidenced aggregate transfers
   may be replaced by their retained components. Do not merge action and transaction
   types, distinct transfers, or just similarly named themes. Old facts remain in
   extraction artifacts; the operation log records every accepted/rejected change.
5. Organize the canonical facts. Multiple event memberships reuse one activity ID.
   Relation review can reverse a supported non-temporal edge; the original edge
   and review decision remain in the audit. responds_to runs from response to request.

## Failure and budget behavior

New coverage and fact repair are best-effort within the existing model call budget.
Core downstream calls are reserved before optional repair calls; this is an estimate,
not a promise that every provider retry will fit. An unavailable repair call is
recorded as unreviewed. Invalid operations are isolated and leave their original
facts intact; accepted neighboring operations survive. Failed relation generation
or review batches do not discard activities or successfully reviewed links.
Unreviewed relation candidates are withheld with an explicit audit reason.

No new search or supplemental acquisition is performed by these repairs.
They incur model calls: typically one coverage call per document/window, one
reconciliation call per 16 proposed occurrences, and one fact-review call per
16 activities, plus normal JSON retries. They do not assert
that LLM semantic judgments are infallible, or that a draft is fully reviewed.

Under builder_config.sparse_builder_config (normally configs/search_pipeline.yml),
the optional switches are:

    person_coverage_repair: true
    person_fact_repair: true

Both default to true for person mode, so existing configuration needs no edit.
Event mode retains its original extraction path. Turning these off preserves the
old extraction/organization sequence, while the storyline checklist still reaches
the skeleton. No dependency changes are required.

## Saved results and replay

- PersonSkeletonBeforeCoverage-Result.json: checked skeleton before additions.
- PersonCoverage-Result.json: source assessments, accepted additions and notes,
  rejected proposals and unreviewed chunks.
- PersonCoverageReconciliation-Result.json: all candidates, matching decisions,
  applied scene IDs and deferred findings.
- SkeletonChecker-1-Result.json: exact repaired skeleton used for extraction.
- PersonFactRepair-Result.json: input hash, operation audit and canonical package.
- PersonOrganization-RelationCandidates-Result.json: original candidates,
  accept/reject/reverse decisions and unavailable batches.

Raw EventCascade artifacts are the extraction record. The corrected canonical
facts feed FinalPersonEPG, its projection and HTML. Strict person replay reconstructs
raw facts, checks their hash, reapplies accepted repairs and verifies the saved
canonical package before applying organization. No model calls occur in replay.
Older artifacts without a repair record keep their original replay path.
The original PersonMappingReport describes extraction-to-package mapping before
canonicalization; follow the fact-repair audit for merged IDs.

## Verification

Offline tests cover source coverage additions, extraction notes, early checklist
delivery, fuzzy dates, actor correction, cross-scene duplicate merging, redundant
aggregates, invalid-operation isolation, service failure, reversed relations,
full person construction, saved HTML data and strict replay. Provider output
quality still requires a fresh real-model run; the supplied old run is not
retroactively claimed to have been regenerated.


## Unknown dates and inherited scene fields

Omitted boundaries, null, empty strings and unknown/null/n/a strings have the same
unknown-time meaning. Equivalent recognized dates with the same precision are
also compatible; a month and a specific day are not automatically equivalent.
EpisodeReconstructor inherits episode_id, name and index_in_stage from the
requested skeleton scene. Harmless temporal representation differences normalize
to that scene; descriptions, relations, actions and source facts are not rewritten.
Raw model responses remain saved, with binding changes recorded separately.

A genuinely different proposed boundary enters the existing local temporal review
instead of being treated as malformed JSON. A keep_scope decision retains the
checked boundary, while an evidenced revise_scope decision updates the scope and
is validated against accepted activities. Uncertain reviews remain unresolved.
The regression fixture includes the exact missing-boundary target and all three
unknown-time responses from build_output_20261109193817987198, plus the actual
E5 coverage proposal that should enrich E3 rather than create a duplicate scene.

The follow-up patch applies AFTER FinMycelium_PR18_person_process_repair.patch.
Use the same build_only_runner command to reconstruct from saved BuildInput.json;
no configuration, search, public schema or HTML renderer change is required.
