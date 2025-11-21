"""
Standardized query input data structure for matching/extraction flows.

- Ensures consistent field names and semantics across modules
- Defines required field `content` and optional guidance parameters
"""

from typing import Optional, List
from dataclasses import dataclass, field


@dataclass
class QueryInput:
    """Unified query input structure.

    Fields:
    - content: original text content (required), used for semantic matching/extraction
    - intention_text: semantic intent (optional) that guides selection
    - key_words: keyword hints (optional), guidance signals not strict filters
    """

    content: str
    query_text: Optional[str] = None
    key_words: List[str] = field(default_factory=list)
