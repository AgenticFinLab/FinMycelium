from typing import Dict, Callable

from .summarizer import BaseSummarizer, KWLMSummarizer, KWRuleSummarizer


# Summarizer factory dictionary
summarizer_factory: Dict[str, Callable] = {
    "kw_lm": lambda config: KWLMSummarizer(config=config),
    "kw_rule": lambda config: KWRuleSummarizer(config=config),
}


def get(config: dict) -> BaseSummarizer:
    """Get a summarizer"""
    summarizer_type = config["summarizer_type"]
    if summarizer_type not in summarizer_factory:
        available = ", ".join(summarizer_factory.keys())
        raise ValueError(
            f"Summarizer '{summarizer_type}' not found. Available options: {available}"
        )
    return summarizer_factory[summarizer_type](config)
