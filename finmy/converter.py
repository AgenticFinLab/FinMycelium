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
import time
import random
import os

from lmbase.utils.tools import BlockBasedStoreManager
from finmy.generic import RawData, MetaSample, UserQueryInput, DataSample
from finmy.builder.base import BuildInput
from finmy.matcher.base import MatchOutput, MatchInput
from finmy.matcher.summarizer import SummarizedUserQuery


def write_text_data_to_block(text: str) -> str:
    """
    Store the given text in a block-based persistent store using a unique key.

    Args:
        text: The string content to be stored.

    Returns:
        The unique file key identifying the stored record.

    Raises:
        ValueError: If the DATA_DIR environment variable is not set.
    """

    data_dir = os.environ.get("DATA_DIR")
    if not data_dir:
        raise ValueError("Environment variable 'DATA_DIR' is not set")
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    bbsm = BlockBasedStoreManager(
        folder=os.environ["DATA_DIR"], file_format="json", block_size=1000
    )
    # Generate a unique filename using UUID

    file_key = f"text_{int(time.time()*1e6)}{random.randint(1000, 9999)}"

    bbsm.save(savename=file_key, data={"text": text})
    return file_key


def read_text_data_from_block(filekey: str) -> str:
    """
    Read text content from a file in the directory specified by the DATA_DIR environment variable,
    using the given file key as the record identifier.

    Args:
        filekey: The unique file key representing the stored record.

    Returns:
        The loaded text content associated with the file key.

    Raises:
        ValueError: If the DATA_DIR environment variable is not set or the directory does not exist.
    """

    bbsm = BlockBasedStoreManager(
        folder=os.environ["DATA_DIR"], file_format="json", block_size=1000
    )
    try:
        return bbsm.load(filekey)["text"]
    except Exception as e:
        raise RuntimeError(
            f"Error loading text data from block for filekey '{filekey}': {e}"
        )


def match_output_to_meta_samples(
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
        file_key = write_text_data_to_block(matched_item.paragraph)
        meta_samples.append(
            MetaSample(
                sample_id=str(uuid.uuid4()),
                raw_data_id=raw_data.raw_data_id,
                location=file_key,
                time=raw_data.time,
                category=category,
                knowledge_field=knowledge_field,
                tag=raw_data.tag,
                method=raw_data.method or match_output.method,
                reviews=[],
            )
        )

    return meta_samples


def raw_data_and_summarized_query_to_match_input(
    raw_data: RawData, summarized_query: SummarizedUserQuery
) -> MatchInput:
    """
    Convert a RawData object into a MatchInput for content matching.

    Args:
        raw_data: RawData instance containing content to be matched.
        summarized_query: A summarized query string or object to guide the matching.

    Returns:
        MatchInput populated with `match_data`, `db_item` from RawData, and `summarized_query`.
    """
    return MatchInput(
        match_data=read_text_data_from_block(raw_data.location),
        db_item=raw_data,
        summarized_query=summarized_query,
    )


def convert_to_build_input(
    user_query: UserQueryInput,
    meta_samples: List[MetaSample],
    extras: dict = None,
) -> BuildInput:
    """
    Construct a BuildInput object for use with event reconstruction builders.

    Args:
        user_query: UserQueryInput instance describing the user query.
        meta_samples: List of MetaSample objects to be included.
        extras: Optional dictionary with additional information.

    Returns:
        BuildInput instance populated with provided fields.
    """
    if extras is None:
        extras = {}
    data_samples: List[DataSample] = []
    for meta_sample in meta_samples:
        data_samples.append(
            DataSample(
                sample_id=meta_sample.sample_id,
                raw_data_id=meta_sample.raw_data_id,
                content=read_text_data_from_block(meta_sample.location),
                category=meta_sample.category,
                knowledge_field=meta_sample.knowledge_field,
                tag=meta_sample.tag,
                method=meta_sample.method,
            )
        )
    return BuildInput(
        user_query=user_query,
        samples=meta_samples,
        extras=extras,
    )
