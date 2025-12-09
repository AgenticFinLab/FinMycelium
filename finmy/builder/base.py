"""
Base entities and containers for financial event reconstruction.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List

from finmy.generic import UserQueryInput
from finmy.generic import MetaSample
from finmy.builder.structure import EventCascade


@dataclass
class BuildInput:
    """Input format of the event reconstruction builder."""

    user_query: UserQueryInput

    samples: List[MetaSample]

    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BuildOutput:
    """Output format of the pipeline builder."""

    event_cascades: List[EventCascade] = field(default_factory=list)
    result: Optional[Any] = None
    logs: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


class BaseBuilder(ABC):
    """Base class for event cascade builders."""

    def __init__(
        self,
        method_name: Optional[str] = None,
        config: Optional[dict] = None,
    ):
        self.build_config = config
        self.method_name = method_name

    @abstractmethod
    def build(self, build_input: BuildInput) -> BuildOutput:
        """Build the event cascades from the input samples."""

    @abstractmethod
    def load_samples(self, build_input: BuildInput) -> Any:
        """Load the specific content of samples from the files."""

    def run(self, build_input: BuildInput) -> BuildOutput:
        """Run the builder pipeline."""
        start = time.time()
        output = self.build(build_input)
        output.extras["time_cost"] = time.time() - start
        return output
