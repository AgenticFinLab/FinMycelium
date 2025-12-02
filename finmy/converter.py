"""
Generic converters between matcher outputs, raw data records and meta samples.

This module centralizes all conversion utilities so that:
- matcher logic stays in `finmy.matcher.*`
- data model definitions stay in `finmy.generic`
- conversion logic is decoupled and reusable.
"""

from __future__ import annotations

import uuid
from typing import Optional, List

from finmy.generic import RawData, MetaSample
from finmy.matcher.base import MatchOutput, MatchItem


def match_output_to_meta_sample(
    match_output: MatchOutput,
    category: Optional[str] = None,
    knowledge_field: Optional[str] = None,
    sample_id: Optional[object] = None,
) -> MetaSample:
    """Convert a `MatchOutput` to a `MetaSample`.

    This function extracts metadata from `MatchOutput.raw` (a `RawData` instance)
    and creates a corresponding `MetaSample` record. The `MetaSample` represents
    a processed sample derived from the raw data, typically after matching.

    Args:
        match_output: The `MatchOutput` containing matched items and raw data metadata.
        category: Optional high-level category label for the sample.
        knowledge_field: Optional primary knowledge domain (e.g., "AI", "Finance").
        sample_id: Optional identifier for the sample. If not provided, uses
            `raw_data.raw_data_id` when available, otherwise generates a new UUID.
            Any object with a meaningful string representation is accepted
            (e.g., `uuid.UUID`, `str`).

    Returns:
        A `MetaSample` instance built from the `MatchOutput` and `RawData`.

    Raises:
        ValueError: If `match_output.raw` is None.
    """
    if match_output.raw is None:
        raise ValueError(
            "Cannot convert MatchOutput to MetaSample: raw data is required but is None"
        )

    raw_data = match_output.raw

    # Normalize / generate sample_id
    if sample_id is None:
        # Prefer using raw_data_id when available
        sample_id_str = raw_data.raw_data_id or str(uuid.uuid4())
    else:
        # Accept UUID or any object, but store as string
        if isinstance(sample_id, uuid.UUID):
            sample_id_str = str(sample_id)
        else:
            sample_id_str = str(sample_id)

    return MetaSample(
        sample_id=sample_id_str,
        raw_data_id=raw_data.raw_data_id,
        location=raw_data.location,
        time=raw_data.time,
        category=category,
        knowledge_field=knowledge_field,
        tag=raw_data.tag,
        method=raw_data.method or match_output.method,
        reviews=[],
    )
