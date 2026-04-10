# UI Collector Quality Optimization Design

**Goal:** Reduce UI search-and-fetch latency and lower low-quality web content entering the builder, without changing the builder architecture or adding case-specific hacks.

**Current Problem**

The UI pipeline currently suffers from two interacting issues:

1. Search collection is slow because Bocha and Baidu results are parsed sequentially with full URL fetching.
2. Low-quality results from dictionary, document-dump, and generic education sites are allowed into the builder, which increases noise and makes `SkeletonChecker` output less stable.

The first-round fix already addressed two upstream correctness bugs:

- keyword phrases are now preserved instead of being split on spaces
- `DataCollectorService` now respects `url_collector_config` from YAML

The second round should improve collection quality itself rather than patch builder behavior.

## Design Principles

- Do not special-case the README sample or Qian Zhimin case.
- Do not change the builder graph, prompts, or sparse-RAG planner.
- Prefer configuration over hardcoded heuristics.
- Preserve a safe fallback path so filtering does not accidentally remove all usable evidence.
- Optimize for stable quality, not just smaller runtime.

## Recommended Approach

Introduce a configurable search-result prefilter layer inside `DataCollectorService` before per-URL parsing.

The prefilter has three responsibilities:

1. Drop obviously low-value domains using a configurable blocklist.
2. Prioritize higher-value domains using a configurable preference list.
3. Enforce configurable parse budgets separately for Bocha and Baidu after filtering/ranking.

This keeps the existing pipeline shape intact:

- search API returns results
- prefilter selects the highest-value subset
- selected results are parsed sequentially with `URLParser`
- structured data and builder execution remain unchanged

## Configuration Additions

Add the following optional keys under `url_collector_config`:

- `bocha_search_count`: number of Bocha results to request
- `bocha_parse_limit`: max Bocha results to parse
- `baidu_parse_limit`: max Baidu results to parse
- `blocked_domains`: domains or domain fragments to skip before parsing
- `preferred_domains`: domains or domain fragments to prefer during ranking

Defaults should be conservative and reversible:

- preserve current behavior when these fields are missing, except for safe quality defaults
- use defaults that reduce obvious noise while still allowing enough evidence through

## Selection Behavior

For each search source:

1. Normalize each candidate URL to a lowercase hostname string.
2. Mark candidates as blocked if their hostname contains any configured blocked domain fragment.
3. Rank remaining candidates so preferred domains come first.
4. Preserve original search order within the same ranking bucket.
5. Parse only the top `*_parse_limit` candidates after ranking.

Fallback rule:

- if filtering removes too many results, the system should still allow non-blocked, non-preferred candidates through up to the configured parse budget
- do not fall back to blocked domains automatically

## Testing Strategy

Add focused unit tests for:

- domain blocking
- preferred-domain ordering
- parse-limit enforcement
- config defaults and config overrides

Keep tests isolated from Streamlit and external collectors using the same stub-driven test style already used in `tests/test_web_ui_input_handling.py`.

## Non-Goals

- no concurrency changes
- no URL parser rewrite
- no prompt or builder modifications
- no domain heuristics tied to one benchmark sample

## Expected Outcome

After this change:

- UI search/fetch time should fall materially for noisy keyword searches
- low-value sites should stop dominating Bocha/Baidu parsing
- builder inputs should become cleaner and less likely to trigger `SkeletonChecker` JSON failures caused by noisy, oversized context
