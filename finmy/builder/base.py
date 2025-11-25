"""
Implementation of the base builder to be used by all subsequent builders.
"""

from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Optional, Any, Dict, List
import time


@dataclass
class BuildInput:
    """Input format of the pipeline builder."""

    samples: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BuildOutput:
    """Input format of the pipeline builder."""

    success: bool = False
    result: Optional[Any] = None
    logs: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Pipeline:
    """Pipeline Structure created by the builder."""

    name: Optional[str] = None
    steps: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)


class BaseBuilder(ABC):
    def __init__(
        self,
        config: Optional[dict] = None,
        method_name: Optional[str] = None,
        pipeline: Optional[Pipeline] = None,
    ):
        self.config = config
        self.method_name = method_name
        self.pipeline = pipeline

    def set_pipeline(self, pipeline: Pipeline):
        self.pipeline = pipeline
        return self

    @abstractmethod
    def build(self, build_input: BuildInput) -> BuildOutput:
        pass

    def run(self, build_input: BuildInput) -> BuildOutput:
        start = time.time()
        output = self.build(build_input)
        output.extras["time_cost"] = time.time() - start
        return output
