# Dev150 Issue-to-Fix Mapping

## Scope

This note records how the `design/finmy-runtime-acceleration-sparse-rag` branch and its current uncommitted changes relate to the `dev150` experiment run (`2026-04-15-dev-candidate-v2`).

The goal is not to restate all branch history. It is to answer a narrower question:

- which `dev150` problems were already absorbed by this branch,
- which problems are addressed by the current uncommitted changes,
- and what evidence exists for each fix.

## Experiment Snapshot

- Stage: `dev`
- Run: `2026-04-15-dev-candidate-v2`
- Final outcome: `150` events completed end-to-end
- Final success events: `144`
- Final failed events: `6`

Known failed events from the final summary:

- `FIN-076`
- `MIL-006`
- `FIN-045`
- `FIN-046`
- `FIN-048`
- `FIN-101`

Observed failure patterns during the run:

1. search-source fragility could interrupt data collection for a case
2. invalid or truncated builder JSON could abort progress inside a shard
3. replay-style nested agent payloads could destabilize downstream episode reconstruction
4. true low-signal retrieval failures still existed for some hard cases and should be recorded explicitly rather than silently inferred

## Branch-Level Fixes Already Present Before the Current Working Tree

This branch already contains a substantial set of committed changes related to the run:

- `feat: add non-ui search pipeline runner`
- `fix: harden skeleton checker json parsing`
- `fix: retry invalid json across builder agents`
- a long sequence of sparse-rag routing, execution-budget, prompt compaction, and replay-compatibility hardening commits

These committed changes explain why the `dev150` run was able to complete after reruns instead of failing at the first routing or replay inconsistency.

## Current Uncommitted Fixes

### 1. Search-source failure isolation

**Problem observed in `dev150`:**

- external search providers could fail independently
- a single provider-side exception should not force the whole search collection step to crash

**Current code change:**

- `finmy/runner/search_pipeline_runner.py`

**Fix summary:**

- adds `_safe_search_call(...)`
- wraps both Bocha and Baidu calls
- converts provider exceptions into structured `_error` payloads and warning logs
- allows the pipeline to continue with whatever source still succeeded

**Verification anchor:**

- `tests/test_non_ui_search_runner.py::test_collect_search_contents_tolerates_bocha_invalid_json`

**Why it matters for `dev150`:**

- this directly addresses the run-time fragility pattern where a malformed or invalid upstream response could otherwise collapse the case before builder execution even began

### 2. Builder JSON recovery after repeated malformed responses

**Problem observed in `dev150`:**

- some builder agents returned invalid or truncated JSON
- a single malformed retry was not always enough to recover the case

**Current code change:**

- `finmy/builder/agent_build/main_build.py`

**Fix summary:**

- raises retry budget for JSON-parse-retry agents from `2` attempts to `3`
- keeps the stricter retry prompt path
- preserves per-attempt trace output through `-RetryN` save names

**Verification anchor:**

- `tests/test_skeleton_validation.py::test_participant_reconstructor_recovers_after_empty_retry_response`

**Why it matters for `dev150`:**

- this addresses the exact class of instability seen in shard reruns where builder agents could fail on malformed intermediate output even though a later retry would have succeeded

### 3. Replay-style nested agent payload unwrapping

**Problem observed in `dev150`:**

- some replay-style agent outputs nested the agent payload under the agent name
- downstream steps expected flat `participants` or `transactions` lists
- that mismatch could break episode reconstruction even when upstream data existed

**Current code change:**

- `finmy/builder/agent_build/main_build.py`

**Fix summary:**

- adds `_unwrap_agent_payload(...)`
- adds `_agent_result_items(...)`
- uses those helpers when reading participant and transaction outputs for
  - `TransactionReconstructor`
  - `EpisodeReconstructor`

**Verification anchor:**

- `tests/test_sparse_rag_routing.py::test_episode_reconstructor_unwraps_replay_style_transaction_payload`

**Why it matters for `dev150`:**

- this reduces replay/rerun brittleness and makes later-stage reconstruction consume the same logical data even when serialization shape differs

## What These Fixes Do Not Claim

These changes do **not** solve the hardest residual `dev150` failures by themselves.

They do not guarantee recovery for:

- true retrieval misses
- low-signal skeleton-empty cases
- entity-only hits with no usable timeline or stage structure

Those failure families remain real benchmark outcomes and should continue to be recorded explicitly.

## Practical Assessment

Relative to `dev150`, the current working-tree changes should be understood as:

- **stability hardening**, not benchmark inflation
- fixes for infrastructure and replay robustness around search and builder integration
- changes that reduce avoidable shard aborts without masking genuinely hard low-signal cases

## Files Covered by This Review

- `finmy/runner/search_pipeline_runner.py`
- `finmy/builder/agent_build/main_build.py`
- `tests/test_non_ui_search_runner.py`
- `tests/test_skeleton_validation.py`
- `tests/test_sparse_rag_routing.py`
