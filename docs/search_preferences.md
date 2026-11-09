# Search preferences

Apply the three patches in order: Bocha only, relaxed stopping, then source languages.
The pipeline configuration belongs at `configs/search_pipeline.yml`, relative to the
FinMycelium repository root. Keep the existing 16384 Builder output limit if already set.

```yaml
search_config:
  enhancement:
    providers: [bocha]
    early_stop_multiplier: 4
    source_languages: [en, zh]
```

These are additions to the complete configuration, not a replacement for it.
The language patch requires `python -m pip install langid==1.1.6` in the environment
that runs the UI/pipeline; the dependency is also in `requirements.txt`. Restart the UI.

Repeated catalog no-progress, unchanged rejected queries and invalid-action thresholds
increase from 3 to 12. Global/event call budgets, context limits, explicit user pauses
and service outages retain their separate meanings. A model can still finish when
it considers research sufficient; this setting does not force twelve wasted calls.

English queries and sources are prioritized; Chinese supplements unresolved gaps.
Titles order candidate leads but never determine eligibility. Full saved body samples
(beginning, middle and end) are classified across all supported detector languages.
Only documents classified as English/Chinese are admitted; originals of excluded
documents remain archived. Cached/shared sources and handoffs use the same check.
Language identification is statistical; it is not a translation step or a guarantee
that every isolated foreign word/quotation is removed. Builder output remains English.

Changed search settings require a new run or explicit `--resume-search-from` revision
to a new output directory; the latter retains cumulative usage. Do not edit saved
`run.json`/phase reservations to bypass configuration identity checks.
