"""Execution metadata for occurrence relevance pending content review."""

PENDING_RELEVANCE = {
    'value': 'Person relevance review pending.',
    'evidence_source_contents': [],
    'reasons': ['Execution status only; no claim of personal involvement has been accepted.'],
}


def pending_relevance(value):
    return value == PENDING_RELEVANCE
