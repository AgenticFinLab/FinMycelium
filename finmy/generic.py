"""
Generic variables used across the whole project.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class UserQueryInput:
    """Unified query input structure for Users.

    Fields:
    - `query_text`: semantic intent (optional) that guides selection
    - `key_words`: keyword hints (optional), guidance signals not strict filters
    - `time_range`: time range (optional), used for determine content only within the given time range.
    - `extras`: extra information (optional), set for backup.
    """

    query_text: Optional[str] = None
    key_words: List[str] = field(default_factory=list)
    time_range: Optional[List[str]] = None

    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataQueryInput:
    """Unified query input structure for Data.

    Fields:

    """

    data_content: str = None


@dataclass
class QuerySample:
    """Unified query sample structure for the financial event pipeline building.

    Fields:
    - `query_text`: semantic intent (optional) that guides selection
    - `key_words`: keyword hints (optional), guidance signals not strict filters
    - `time_range`: time range (optional), used for determine content only within the given time range.
    - `extras`: extra information (optional), set for backup.
    """


@dataclass
class RawData:
    """Raw data descriptor

    Fields:
    - `raw_data_id`: UUID string uniquely identifying the raw data record
      Format: 8-4-4-4-12 hex digits, e.g., `550e8400-e29b-41d4-a716-446655440000`
    - `source`: URI pointing to where the data was collected (path or URL)
      Examples: `gulm/data/pdfs/Technical_report.pdf`, `https://ieeexplore.ieee.org/...`
    - `location`: URI of the stored content (local path or URL)
      Examples: `gulm/data/pdfs/Technical_report.pdf`, `https://ieeexplore.ieee.org/...`
    - `time`: ISO 8601 timestamp when data was obtained (YYYY-MM-DD HH:MM:SS TZ)
      Example: `2024-05-20 10:23:45 UTC`
    - `copyright`: copyright statement or license notice
      Example: `© 2023 ACM, Inc., All rights reserved.`
    - `method`: tool/software used to obtain data with version
      Examples: `PyMuPDF (v1.23.0)`, `pdfplumber (v0.9.0)`
    - `tag`: manually defined tag for the sample
      Examples: `AgenticFin`, `HKUST`
    """

    raw_data_id: str
    source: str
    location: str
    time: str
    copyright: str
    method: str
    tag: str


@dataclass
class MetaSample:
    """Sample metadata linked to a raw data entry

    Fields:
    - `sample_id`: identifier of the sample; typically aligned to `raw_data_id`
    - `raw_data_id`: the UUID from `RawData` that this sample originates from
    - `location`: storage URI of the sample content (same as `RawData.location`)
    - `time`: ISO 8601 timestamp of the sample (same as `RawData.time`)
    - `category`: high-level category label of the sample (user-defined)
      Example: `NULL` or a domain grouping
    - `belong_field`: primary knowledge field (second-level category)
      Examples: `AI`, `Finance`, `Medicine`, `History`
    - `tag`: inherited tag from `RawData.tag`
    - `method`: inherited collection method from `RawData.method`
    - `reviews`: list of review records with fields
      `{ "reviewer_name": str, "review_time": ISO8601 str, "comment": str }`
      where `comment` ∈ { `Pending`, `Approved`, `Rejected` } and `review_time`
      follows ISO 8601 (e.g., `2024-05-21 14:30:00 UTC`).
    """

    sample_id: str
    raw_data_id: str
    location: str
    time: str
    category: Optional[str] = None
    knowledge_field: Optional[str] = None
    tag: Optional[str] = None
    method: Optional[str] = None
    reviews: List[Dict[str, str]] = field(default_factory=list)
