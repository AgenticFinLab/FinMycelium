from typing import Dict, Callable

from .summarizer import BaseSummarizer, KWLMSummarizer, KWRuleSummarizer


# Summarizer factory dictionary
summarizer_factory: Dict[str, Callable] = {
    "kw_lm": KWLMSummarizer,
    "kw_rule": KWRuleSummarizer,
}


def get(config: dict) -> BaseSummarizer:
    """Get a summarizer"""
    return summarizer_factory[config["summarizer_type"]](config)
