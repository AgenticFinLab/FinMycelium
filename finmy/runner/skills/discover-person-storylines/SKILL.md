---
name: discover-person-storylines
description: Discover domains and researchable storylines for a person in a requested period, then research each event with FinMycelium's shared search before EPG construction. Use a short request such as "Buffett 2022-2023"; no user-supplied event list is required.
---

# Discover and research person storylines

1. Resolve the request into a person and coverage period. Preserve explicit scope and date precision. Ask only if identity cannot be resolved. Treat publication dates separately from activity dates.
2. Propose concrete continuing matters involving that person: investments, projects, roles, relationships or sustained issues. Use model knowledge as search hypotheses only. Do not manufacture citations, actions, dates or source support.
3. Group candidate storylines into domains after identifying the matters. Infer labels from the person and period; do not require fixed categories or a fixed number of events. Use the configured event cap to prioritize useful research targets.
4. Merge the same matter across reports, meetings and years. Keep unrelated matters separate. Do not treat every annual report or shareholder meeting as a container for unrelated storylines. Identify the person's relationship to each matter without equating an organization's actions with its leader's actions.
5. Give each candidate a boundary, search terms and concrete process questions. Preserve uncertainty. Include earlier background only when needed to explain in-period activities.
6. Research each candidate through the shared search Agent. Let that Agent choose queries, inspect sources and retain useful original material. Do not run a second relevance classifier.
7. Pass retained originals, provenance and the candidate organization plan to the builder. Use the plan only as grouping hints; require actual source evidence for activities and relationships. Do not fill unsupported candidates into the final graph.
8. Keep discovery under its own model-call ceiling. Reserve each event's allowance within the shared initial search/read/model budget; use smaller remaining allowances when useful and retain unfunded candidates as pending. Share downloaded originals across events, but require each event to inspect and select its own evidence. Share one initial source-character allowance across all events. Persist progress before external calls, resume from the cumulative ledger, and report partial completion explicitly. Build from validated nonempty partial material while preserving coverage gaps separately. Leave post-build enrichment disabled unless explicitly enabled.

The executable prompt lives in `finmy.runner.storyline_discovery.DISCOVERY_PROMPT`;
`discover_storylines` validates and archives the candidate plan. The shared-search
runner executes the event research and owns the total initial budget. The skill file
is repository documentation, not a separate runtime dependency or a ChatGPT installation.
