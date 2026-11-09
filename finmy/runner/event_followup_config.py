"""Finite budgets for supplementing events already produced by the builder."""
import copy

from finmy.reconstruction_scope import read_reconstruction


def followup_enabled(config):
    scope = read_reconstruction(config)
    settings = config.get("event_followup")
    settings = {} if settings is None else settings
    if not isinstance(settings, dict) or type(settings.get("enabled", False)) is not bool:
        raise ValueError("event_followup.enabled must be a boolean")
    builder = config.get("builder_config", config)
    return (scope["mode"] == "person" and settings.get("enabled", False)
            and builder.get("builder_type", "SparseRagBuilder") == "SparseRagBuilder")


def normalize_followup_config(config):
    result = copy.deepcopy(config)
    if not followup_enabled(result):
        return result
    from finmy.runner.draft_event_search import draft_event_options
    result["event_followup"] = draft_event_options(result)
    result.get("builder_config", result).setdefault("builder_type", "SparseRagBuilder")
    content = result.setdefault("all_content_config", {})
    if not isinstance(content, dict):
        raise ValueError("all_content_config must be a mapping")
    for key, default, minimum in (("max_content_length", 120000, 1),
                                   ("max_document_chars", 12000, 1)):
        value = content.setdefault(key, default)
        if type(value) is not int or value < minimum:
            raise ValueError("all_content_config." + key + " must be finite and positive")
    return result
