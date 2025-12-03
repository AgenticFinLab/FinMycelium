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

from finmy.generic import RawData, MetaSample, UserQueryInput
from finmy.builder.base import BuildInput
from finmy.matcher.base import MatchOutput
import os


def write_data_to_file(text: str) -> str:
    """
    Write the provided text content to a file under the directory specified by the DATA_DIR environment variable.
    A unique filename will be generated for each call (UUID-based), and the function returns the generated filename.

    Args:
        text: The text content to be written to the file.

    Returns:
        The generated filename (not the full path).

    Raises:
        ValueError: If the DATA_DIR environment variable is not set or the directory does not exist.
    """
    data_dir = os.environ.get("DATA_DIR")
    if not data_dir or not os.path.isdir(data_dir):
        raise ValueError(
            "Environment variable 'DATA_DIR' is not set or the directory does not exist"
        )
    # Generate a unique filename using UUID
    filename = f"{uuid.uuid4()}.txt"
    file_path = os.path.join(data_dir, filename)
    # Write the text content to the file with UTF-8 encoding
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)
    # Return only the filename so it can be accessed later if needed
    return filename


def read_data_from_file(filename: str) -> str:
    """
    Read the contents of a text file from the data directory specified by the DATA_DIR environment variable.

    Args:
        filename: The name of the file to read.

    Returns:
        The contents of the file as a string.

    Raises:
        ValueError: If the DATA_DIR environment variable is not set or the directory does not exist, or if the file does not exist.
    """
    import os

    data_dir = os.environ.get("DATA_DIR")
    if not data_dir or not os.path.isdir(data_dir):
        raise ValueError(
            "Environment variable 'DATA_DIR' is not set or the directory does not exist"
        )
    file_path = os.path.join(data_dir, filename)
    if not os.path.isfile(file_path):
        raise ValueError(f"File '{file_path}' does not exist")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return content


def match_to_meta_samples(
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
        filename = write_data_to_file(matched_item.paragraph)
        meta_samples.append(
            MetaSample(
                sample_id=str(uuid.uuid4()),
                raw_data_id=raw_data.raw_data_id,
                location=filename,
                time=raw_data.time,
                category=category,
                knowledge_field=knowledge_field,
                tag=raw_data.tag,
                method=raw_data.method or match_output.method,
                reviews=[],
            )
        )

    return meta_samples


def get_raw_data_content(raw_data: RawData) -> str:
    """
    Retrieve the main content from a RawData object.

    Args:
        raw_data: The RawData instance.

    Returns:
        The content (str) stored in the RawData object.
    """
    return read_data_from_file(raw_data.location)


def convert_to_build_input(
    user_query: UserQueryInput,
    samples: List[MetaSample],
    extras: dict = None,
) -> BuildInput:
    """
    Construct a BuildInput object for use with event reconstruction builders.

    Args:
        user_query: UserQueryInput instance describing the user query.
        samples: List of MetaSample objects to be included.
        extras: Optional dictionary with additional information.

    Returns:
        BuildInput instance populated with provided fields.
    """
    if extras is None:
        extras = {}
    return BuildInput(
        user_query=user_query,
        samples=samples,
        extras=extras,
    )
