"""Small overview context and deterministic fallback; detailed facts stay in stages."""

import copy

from .contracts import compact_values


def overview_context(cascade, samples):
    """Use completed stage summaries, with their actual source spans, not the whole graph."""
    texts = [sample.content for sample in samples]
    quotes, seen = [], set()
    stages = []
    for stage in cascade.get("stages", []):
        descriptions = copy.deepcopy(stage.get("descriptions", []))
        for field in descriptions:
            for quote in field.get("evidence_source_contents", []):
                if quote and quote not in seen and any(quote in text for text in texts):
                    seen.add(quote)
                    quotes.append(quote)
        stages.append({"stage_id": stage.get("stage_id"),
                       "name": compact_values(stage.get("name")),
                       "descriptions": descriptions})
    return {"title": compact_values(cascade.get("title")), "stages": stages}, quotes


def stage_summary_fallback(cascade):
    """Copy one existing overview per stage, without promoting incomplete model text."""
    descriptions, origins, seen = [], [], set()
    for index, stage in enumerate(cascade.get("stages", [])):
        for position, field in enumerate(stage.get("descriptions", [])):
            value = field.get("value")
            if not isinstance(value, str) or not value.strip():
                continue
            if value not in seen:
                seen.add(value)
                descriptions.append(copy.deepcopy(field))
                origins.append({"stage_index": index, "description_index": position})
            break
    return {"descriptions": descriptions}, origins
