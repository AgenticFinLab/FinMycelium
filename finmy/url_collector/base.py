"""
Base entities and containers for URL collection and parsing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class URLCollectorInput:
    """Input format for URL collection and parsing."""
    
    urls: List[str]
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class URLCollectorOutput:
    """Output format for URL collection and parsing."""
    
    results: List[Dict[str, Any]] = field(default_factory=list)
    parsed_contents: Dict[int, str] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


class BaseURLCollector(ABC):
    """Base class for URL collectors and parsers."""
    
    def __init__(
        self,
        method_name: Optional[str] = None,
        config: Optional[dict] = None,
    ):
        self.config = config
        self.method_name = method_name
    
    @abstractmethod
    def collect(self, input_data: URLCollectorInput) -> URLCollectorOutput:
        """Collect and parse URLs from the input."""
    
    def run(self, input_data: URLCollectorInput) -> URLCollectorOutput:
        """Run the URL collection pipeline."""
        return self.collect(input_data)