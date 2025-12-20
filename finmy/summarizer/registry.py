from typing import Dict, Callable
import logging

from .summarizer import BaseSummarizer, KWLMSummarizer, KWRuleSummarizer


# Summarizer factory dictionary
summarizer_factory: Dict[str, Callable] = {
    "kw_lm": KWLMSummarizer,
    "kw_rule": KWRuleSummarizer,
}


def get(config: dict) -> BaseSummarizer:
    """Get a summarizer"""
    logging.info("Creating summarizer with config: %s", config)
    summarizer = summarizer_factory[config["summarizer_type"]](config)
    logging.info("Created summarizer: %s", summarizer)
    return summarizer
