"""
Standardized query input data structure for matching/extraction flows.

- Ensures consistent field names and semantics across modules
- Defines required field `content` and optional guidance parameters
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
