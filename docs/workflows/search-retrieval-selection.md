# Passage retrieval and evidence selection

Evidence delivery combines validated original spans with coverage-aware selection.
The material budget is an upper limit; unused budget may remain.

## Review decisions and working context

For scoped research, each decision context includes `evidence_review` with the
exact `required_passage_ids` being shown and a JSON response schema. The agent
submits useful evidence through `fact_checks.evidence` or `priority_passages`,
and records remaining text in `passage_exclusions`, together with its next action.
When every shown passage is fully selected, return `passage_exclusions: {}`.
This contract is shown on the first
presentation, before a missing-decision error can occur. JSON mode supplies the
object; existing application validators verify IDs, original ranges and coverage.
The schema is part of the prompt, not a provider-specific structured-output setting.
Preparing the context does not mark evidence read. Only a completed response can
commit a presentation; interrupted streams cannot change evidence state.

Working context uses the original source-ledger view for every source, without
selecting expanded metadata by the current question. Existing passage marks,
question details and provider query histories remain visible under the original
context rules. There is no additional 240-character truncation of supported checks
or metadata paging action. Original excerpts and pending evidence retain their
shared budget, and the overall context limit and finalization rules still apply.

## Defaults and separate comparisons

The workbench, Python API and repository profile in `configs/search.yml` use
Ark DeepSeek V4.1 Flash (`ark/deepseek-v4-1-flash-261017`), high reasoning,
JSON output and `retrieval: {mode: bm25}` for new agent searches.
The evaluation CLI uses the same search profile. BM25 ranks passages within saved sources and offers
located cached excerpts before the next research decision. The research agent
decides which originals to mark and which sources need further reading.

`retrieval: {}` or `{mode: topic}` selects the existing topic reader, including
its lexical ranking. New workbench tasks inherit saved profile overrides.
Runs saved before the reader setting existed resume with the topic reader.
Both readers run locally. A Baidu or Bocha result with a missing body can
trigger an original-page fetch. The body becomes eligible for selection after
the agent has inspected an original passage from that version.

Optional BM25 settings, passed to the existing `--config` argument:

```json
{
  "retrieval": {
    "mode": "bm25",
    "top_k": 24,
    "window_chars": 1600
  }
}
```

`top_k` limits passage candidates, not final material length. The accepted options
are `mode`, `top_k` and `window_chars`. Removed retrieval modes and model options
are rejected explicitly. Existing `topic`, `bm25` and empty-config checkpoints
remain resumable with their saved configuration.

Feature-level results and the decision to retain default BM25 are recorded in
[搜索功能演进与效果对比](../experiments/search-feature-comparison.md).

## Baidu and Bocha original bodies

Baidu `content` is stored as a partial original. Bocha `summary` and provider
snippets remain leads. For Baidu/Bocha results without a saved body, search now
fetches the original URL once and caches its parsed text before source selection.
Up to three URLs download concurrently, using the existing 20-second acquisition
timeout (or a shorter configured timeout); saved bodies and failed discovery downloads are reused across searches
and resume. Downloads add HTTP work, not model or search-provider calls.

Search feedback returns source IDs and provider results. Fetching alone does not
mark a body read. In BM25 mode, `cached_evidence` offers up to three selected original
excerpts during research, sharing the existing context allowance with `read_evidence`.
The serialized offer is capped at 3,200 characters, including locations and metadata;
whole bodies and provider summaries are not added to the decision context.

Before the first cached presentation, unread partial sources in that offer get
their existing one-time original-fetch attempt. The agent rebuilds the context
after acquisition so versions and offsets match. Failed expansion keeps the
partial cache; already inspected versions remain frozen. Context inspection alone
does not fetch, and newly ranked candidates wait rather than expanding the pool.

All decision excerpts share one serialized allowance of `max_read_chars` (with a
3,200-character floor for small read limits), also bounded by the remaining model
context. Outstanding shown passages get priority; otherwise the latest requested
read precedes older previews. Previews omit selected or explicitly excluded ranges. Mark coordinates and saved checks remain available without repeating their
original bodies or copying them into recent actions. Task and source-catalog fields
precede changing state in the model request, keeping the request prefix stable
between discoveries. Explicit reads can still revisit marked wording.

Candidates do not need an English full name in their paragraph or title. The
current query and its existing `provider_queries` variants rank saved originals,
including source-language passages and numerical matches beside abbreviations.
Long prose is split into bounded windows at available sentence boundaries,
including Chinese punctuation, without changing original offsets. A pronoun
beside a person's name in the page title does not establish personal attribution.
The agent verifies entities and marks useful support; ranking never selects delivery.

Only ranges actually presented in a successful model call become inspected. Their
source version and offsets are checked against the cached original before the
returned action is processed, so useful excerpts can be marked in that same action.
Calling the context builder or a failed model request does not establish a read.
`read_source` expands an excerpt or reads another location. Failed downloads retain
their leads and acquisition errors. Search summaries never become original evidence.

## Metadata and time

Optional `task.retrieval_constraints` and original document/block
`evidence_scope` metadata can specify `entity_id`, `event_id`, `activity_start`
and `activity_end`. IDs are compared only when both sides are explicitly supplied.
Activity intervals filter only when both endpoints are known and non-overlapping.
These fields are never inferred from names, URLs or publication years. An absent
or ambiguous value does not reject a candidate.

Publication is separate: only the user's explicit `publication_start` and
`publication_end` settings filter known publication dates. An activity window of
2008–2013 permits a 2025 retrospective. Existing publication conflicts remain
unknown rather than selecting an arbitrary provider's date.

## Final evidence selection

The model judges relevance against the entire confirmed event/person scope, rather
than only the active question or retrieval facets. Funding and enabling actions,
constraints applied to the commitment, and dated continued ownership/participation
can establish distinct facts even after transaction terms are supported. Shared
paragraphs must explicitly connect the target to those actions; group totals and
other entities' actions cannot be attributed to the target alone. Unconnected
general policy remains background. A later holding supports its dated state, not
an unreported acquisition or exact receipt.

For mixed passages, the model selects useful complete sentences with their
referents before excluding the remainder. Pending remainders can include
`selected_context_before`: up to 800 characters of an adjacent already-selected
prefix in the same source/version/block. This preserves the antecedent of phrases
such as "these commitments" when the prefix has left the ordinary preview. It uses
the existing serialized excerpt allowance, is omitted if it would displace the
remainder, and never exposes non-whitespace gaps or creates another delivery mark.
Distinct scoped facts go into atomic fact checks; an answered broader question,
absence of new terms, or mention of other entities alone does not justify exclusion.

Delivery still starts exclusively from validated, previously read priority spans.
Optional mark annotations support coverage-aware choice:

```json
{
  "source_id": "runtime-id",
  "block": 3,
  "start": 0,
  "end": 220,
  "reason": "Original completion statement and its condition",
  "fact_ids": ["settlement-completion"],
  "claim_id": "delivered-on-confirmed-date",
  "evidence_role": "outcome"
}
```

Allowed roles: `terms`, `personal`, `condition`, `outcome`, `corroboration`,
`contradiction`, `context`. Equivalent claims share a `claim_id`; planned versus
completed actions, different conditions, dates or opposing statements do not.
An independently verified corroboration may include `independence_key` naming the
original evidence origin. Reprints share one key; different URLs alone do not
establish independence. These annotations remain model advice, not source facts.

Selection recalculates marginal value after every retained mark. New fact coverage
has weight 4, new claims and evidence roles 2, new independent corroboration and
numerical/negation qualifications 1. Cost only decides whether a span fits and
breaks equal-value ties. There is no target length, source quota or filler phase.
The selector stops when nothing with positive value fits. Equivalent descriptions
lose priority; personal statements, conditions, opposing claims and independent
origins can still add value for an already-covered fact. Numeric/date/negation
changes survive even if a model reuses a claim ID incorrectly.

Every `fact_checks.evidence` location explicitly selects useful original text, even
when its question remains `planned`, `missing` or `conflicting`. The ordinary action
saves it through the existing mark validator; this does not promote the fact to
`supported`. The model need not submit duplicate `priority_passages`. Unread or
invalid locations cannot become marks. Existing marked annotations are preserved.
New handoffs prioritize validated ranges cited by supported `fact_checks`. Shared fact/claim labels cannot let a shorter question displace its
cited answer. The citations add coverage value only inside validated marks;
they never establish a read or bypass version, coordinate or budget validation. Exact-copy deduplication and the
material ceiling still apply, and any undelivered citation remains a gap.

Necessary attribution, dates and qualifications must be included inside the marked
support span, or marked as a specific condition. A `context` mark can earn value
for `fact_ids` not yet covered by selected evidence. Pure background and context
whose facts are already covered add no value; existing duplicate checks still apply.
Marks without semantic annotations remain supported: unique original text is
retained without inventing semantic equivalence. Exact
reposts are deduplicated unless an explicit independent corroboration adds value.

All original files, versions, hashes, marks and omitted ranges remain intact.
`selection.json` records marginal gains, new facts, and `retained`, `redundant` or
`material_limit` decisions. Retained text always comes from original coordinates.

## Read coverage and sentence boundaries

For evidence-selected tasks (`entity_attribute_windows_v2`), `inspection.py`
maintains one location ledger for originals actually included in a successful
model request. Each excerpt carries a stable `passage_id` tied to its source,
version, block and offsets. Context construction, failed requests, cached bodies
and read ranges omitted from the context do not create pending decisions.

The agent selects useful ranges using `fact_checks.evidence` or `priority_passages`
and excludes other shown text with `passage_exclusions: {"passage_id": "reason"}`
in the same ordinary action. A partial mark leaves the remaining text pending;
an exclusion covers only the unselected remainder of that shown excerpt. It
cannot exclude an entire source. Old decisions never apply to a new version.

Kept ranges come from validated marks, so there is no second saved/support status
to maintain. Pending originals return under the same shared excerpt allowance,
before new candidates. Search, read and finish wait for their decisions. Deferred
actions are not counted as attempted searches or reads. Legacy document-selection
tasks retain their source-level contract.

`commit_evidence` saves independently valid updates before validating the next
tool action. One bad fact, rename, annotation or tool field cannot roll back a
valid selection. `evidence_feedback` identifies rejected items. The ledger and
marks survive checkpoints; resumed tasks need no duplicate fetch or model review.

New annotations may expand clipped prose to closed sentence boundaries inside
the same source block. Each extension must be fully covered by existing reads in
that version. Blank lines delimit paragraphs; tables and unfinished source
tails are not completed by this rule. Saved marks and frozen handoffs keep their
exact coordinates. A repeated mark is matched against its original and aligned
coordinates to avoid retaining both copies.

Alignment preserves the source wording. It does not correct a relevance mistake:
an endpoint already inside company boilerplate may include the rest of that
sentence. The agent still chooses the supporting passage. These checks are local
and introduce no model calls or additional search requests.

## Research questions and finishing

The pipeline has one research loop: acquire originals, navigate with local BM25,
select useful support and update `fact_checks`, then choose the next action from
those checks. Final selection and citation validation use the same evidence.
There is no separate LLM review or reranking stage.

Establish important questions from the confirmed task scope during ordinary
research, including task-derived questions whose sources have not yet been found.
Each question names one verifiable fact. A supported answer to one condition or
reason does not close an entire direction about conditions or reasons. Narrow the
answered check and keep important unresolved parts as separate checks.
New originals may add a distinct
reason, condition, response or outcome even when a broader check is supported.
An announcement can support what was announced while actual completion remains a
separate `planned` or `missing` question. These are model judgments about originals;
no evaluation fact list or event-specific rules are injected.

`fact_checks` updates accompany `search`, `read_source` or `finish`. Omitted checks
persist. Supported updates cite exact inspected locations; new source-only support
cannot establish delivery. Use `replaces: ["exact old question"]` to rename or merge
checks, preserving unresolved obligations as separate questions. Citation locations
and historical attempts follow the replacement.

Both search and read actions use `question` to identify the saved question while
`query` contains the search keywords. The first discovery search can omit it.
Accepted actions provide the attempt history; rewording keywords does not reset a
question. A new question explicitly named by an action is retained as missing until
support is recorded. The existing source/version/range and no-gain guards still control reads.

| Component | Responsibility |
|---|---|
| Sources | Acquire and version original bodies; acquisition alone is not inspection. |
| BM25 and previews | Offer bounded original passages for discovery or a named question; ranking does not establish support. |
| Agent and fact checks | Select useful originals and update atomic questions in the same action. |
| `inspection.py` | Track shown ranges, commit independent selections/exclusions, and defer the next action while decisions remain pending. |
| `research_steps` | Suggest review of inspected text, a cached location, or a previously unattempted targeted search. |
| Selection and delivery checks | Deduplicate, retain marginal evidence within the ceiling, and validate actual delivered support. |

`next_steps` suggests work during ordinary research.
A named question restricts navigation to that question, without broad personal or
background fallback groups. If no useful cached match remains and no targeted
search for the question is recorded, it can suggest a search within the existing
budget. Previously attempted questions may remain explicit gaps. Suggestions are
navigation, not assertions that a candidate answers the question.

Every first read, including a nonzero cursor, attempts eligible partial-body
completion before recording inspected text. If completion changes the version,
a nonzero cursor returns `source_version_changed` with a fresh `next_location`;
it records no inspected ranges or query attempt. Acquisition progress prevents a
stagnation stop while the next read is pending. Failed completion keeps the old
body and cursor. Already inspected versions and their saved marks stay fixed.

Finish uses the same pending-range check as ordinary actions. Voluntary finish
also requires explicitly supplied seed sources to be inspected or skipped with
concrete reasons. Deferred finish returns ordinary read actions; it never marks
cached bodies inspected. Skip decisions persist across deferred actions and
resume. Failed acquisition, exhausted source slots and forced finalization leave
explicit source gaps and cannot claim supported completion. Both source-based
and legacy span-based finish use this gate. Other candidates remain optional.
Before voluntary finish, the agent submits `scope_review` with a substantive
`summary` comparing the original task with the actual saved answers, and
`followups: [{"question": "one unresolved fact", "reason": "task requirement or source lead"}]`.
This reviews unexplored parts of the task as well as already listed questions;
all current checks being `supported` is not itself a coverage assessment.
Followups enter the existing `fact_checks` ledger as missing. Reopening a supported
question preserves its citations and selected originals. Omitting an unresolved
question from a later scope review does not remove it from the ledger.
New unattempted followups receive a bounded navigation opportunity through the same
`next_steps`, source inspection and search budgets. Prior attempts and question
renames are retained. A missing or malformed assessment receives at most one
correction turn; if still absent, it remains an explicit coverage gap. Forced
finalization does not spend extra calls and cannot claim assessed scope without
a valid review. The review is saved in `run.json` under `scope_review` and can be
reused after its followups have been resolved. No event-specific fact list is used.

Finish then performs one located citation repair if necessary. Once finalization
is imposed, undecided originals become
explicit source/version/offset gaps and cannot support a completeness claim.

Free-form gap notes with matching saved support receive at most one ordinary
finish-review turn within the existing model budget. `saved_gap_evidence` brings
whole selected ranges back under the shared excerpt allowance, including at
forced finalization, without marking new text. The model reconciles gap wording
and fact checks together, preserving announced quantities and dates while keeping
unconfirmed completion separate. Canonical ledger gaps need no extra review turn.

No model, reranker or provider stage is added. Decisions accompany existing model
calls. Ignored passages may consume existing retry turns; the current no-progress,
model, source, context and material budgets still bound the run.

Factual `gaps` derive from the checks after delivery validation. Other notes retain
acquisition failures and operational limits. `person_evidence.questions` links to
the same delivered checks, including renamed questions; status and detail are
recomputed rather than preserving an independent narrative. Invalid or omitted
support remains a gap even if a model described the fact as supported.

New manifests use `question_flow_v3`. Frozen older manifests retain their previous
selection and assessment behavior and exact original coordinates. The configured
model, search, context and final material limits are unchanged.

Changing the handoff budget in the workbench preserves the scoped manifest's
selection policy. A larger limit can admit additional marked evidence that
previously did not fit. The previous revision remains available.

## Frozen-source comparison

Use independently reviewed case labels against fixed source versions:

```json
[
  {
    "source_id": "saved-source-id",
    "version": "saved-source-version",
    "query": "What confirms completed delivery?",
    "expected_ranges": [{"block": 12, "start": 0, "end": 240}]
  }
]
```

Run the zero-extra-model baseline first:

```bash
python -m finmy.search.retrieval_eval \
  --run-dir output/search-eval/TASK/runs/initial \
  --cases cases.json --modes topic bm25 --output baseline.json
```

The comparison does not rerun web searches or alter the original run. Each mode
has its own checkpoint next to the report. Reports include original returned
ranges, labeled-evidence character recall and delivered characters. This is recall
against supplied range labels, not whole-web recall or overall precision. Keep the
source versions, labels and read limit fixed across modes.

Offline tests:

```bash
python -m pytest -q tests/test_search_retrieval.py tests/test_search_coverage.py \
  tests/test_search_passage_boundaries.py tests/test_search_evidence_selection.py \
  tests/test_search_evidence_routing.py tests/test_search_cache_selection.py \
  tests/test_search_question_flow.py tests/test_search_inspection.py \
  tests/test_search_acquisition.py tests/test_search_flow_transitions.py
```
