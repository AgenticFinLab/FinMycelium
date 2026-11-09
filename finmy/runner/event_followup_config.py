"""Finite budgets for supplementing events already produced by the builder."""
import copy

from finmy.reconstruction_scope import read_reconstruction
from finmy.runner.subject_search import validate_subject_search_options


def followup_enabled(config):
    scope = read_reconstruction(config)
    settings = config.get("event_followup")
    settings = {} if settings is None else settings
    if not isinstance(settings, dict) or type(settings.get("enabled", True)) is not bool:
        raise ValueError("event_followup.enabled must be a boolean")
    builder = config.get("builder_config", config)
    search = config.get("subject_search")
    search = {} if search is None else search
    if not isinstance(search, dict) or type(search.get("enabled", True)) is not bool:
        raise ValueError("subject_search.enabled must be a boolean")
    return (scope["mode"] == "person" and settings.get("enabled", True)
            and builder.get("builder_type", "SparseRagBuilder") == "SparseRagBuilder"
            and search.get("enabled", True))


def normalize_followup_config(config):
    result = copy.deepcopy(config)
    if not followup_enabled(result):
        return result
    from finmy.runner.draft_event_search import draft_event_options
    result["event_followup"] = draft_event_options(result)[0]
    result.get("builder_config", result).setdefault("builder_type", "SparseRagBuilder")
    from finmy.runner.enhanced_subject_search import enhanced_search_enabled
    if not enhanced_search_enabled(result):
        options = result.get("subject_search") or {}
        search = result.get("search_config", {}) or {}
        for provider, default in (("bocha", 10), ("baidu", 20)):
            options.setdefault(provider + "_count", search.get(provider + "_count", default))
        result["subject_search"] = validate_subject_search_options(options)
    content = result.setdefault("all_content_config", {})
    if not isinstance(content, dict):
        raise ValueError("all_content_config must be a mapping")
    for key, default, minimum in (("max_content_length", 60000, 1),
                                   ("max_document_chars", 12000, 1)):
        value = content.setdefault(key, default)
        if type(value) is not int or value < minimum:
            raise ValueError("all_content_config." + key + " must be finite and positive")
    return result


def initial_search_options(config):
    """Keep the original acquisition budget; supplementation has its own ledger."""
    options = dict(config.get("subject_search", {}) or {})
    return validate_subject_search_options(options) if followup_enabled(config) else options
