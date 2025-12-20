from typing import Dict, Callable

from .summarizer import BaseSummarizer, KWLMSummarizer, KWRuleSummarizer


# Summarizer factory dictionary
summarizer_factory: Dict[str, Callable] = {
    "kw_lm": lambda config: KWLMSummarizer(config=config),
    "kw_rule": lambda config: KWRuleSummarizer(config=config),
}


def get(config: dict) -> BaseSummarizer:
    """Get a summarizer"""
    return summarizer_factory[config["summarizer_type"]](config)
