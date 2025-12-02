"""
Generic converters between matcher outputs, raw data records and meta samples.

This module centralizes all conversion utilities so that:
- matcher logic stays in `finmy.matcher.*`
- data model definitions stay in `finmy.generic`
- conversion logic is decoupled and reusable.

The generally data flow of this framework is:

source_data -> collector -> parsed_data
--> converter --> raw_data in the database (RawData)
--> converter --> MatchInput -> matcher -> MatchOutput
--> converter --> meta sample in the database (MetaSample)
--> converter --> BuildInput -> builder -> BuildOutput
--> converter --> EventCascade in the database (EventCascade)

"""

from __future__ import annotations

import uuid
from typing import Optional, List

from finmy.generic import RawData, MetaSample
from finmy.matcher.base import MatchOutput


def match_to_samples(
    match_output: MatchOutput,
    raw_data: RawData,
    category: Optional[str] = None,
    knowledge_field: Optional[str] = None,
) -> List[MetaSample]:
    """
    Convert a `MatchOutput` to a `MetaSample`.

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
    meta_samples: List[MetaSample] = []

    for matched_item in match_output.items:
        meta_samples.append(
            MetaSample(
                sample_id=str(uuid.uuid4()),
                raw_data_id=raw_data.raw_data_id,
                location=raw_data.location,
                content=matched_item.paragraph,
                time=raw_data.time,
                category=category,
                knowledge_field=knowledge_field,
                tag=raw_data.tag,
                method=raw_data.method or match_output.method,
                reviews=[],
            )
        )

    return meta_samples
