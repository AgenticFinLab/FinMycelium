"""
Base entities and containers for financial event reconstruction.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List

from finmy.generic import UserQueryInput
from finmy.generic import MetaSample
from finmy.builder.structure import EventCascade, EventStage, ParticipantStateSnapshot


def build_participant_snapshots_map(
    stages: List[EventStage],
) -> Dict[str, List[ParticipantStateSnapshot]]:
    """Merge stage-level and episode-level snapshots into a global map keyed by participant_id.

    Returns a mapping `participant_id -> List[ParticipantStateSnapshot]` sorted by timestamp.
    """

    snapshots_by_participant: Dict[str, List[ParticipantStateSnapshot]] = {}
    for stage in stages or []:
        for pid, snaps in (stage.participant_snapshots or {}).items():
            snapshots_by_participant.setdefault(pid, []).extend(snaps or [])
        for episode in stage.episodes or []:
            for pid, snaps in (episode.participant_snapshots or {}).items():
                snapshots_by_participant.setdefault(pid, []).extend(snaps or [])

    for pid, snaps in snapshots_by_participant.items():
        snaps.sort(key=lambda s: s.timestamp)

    return snapshots_by_participant


def build_participant_snapshots_map_from_event(
    event: EventCascade,
) -> Dict[str, List[ParticipantStateSnapshot]]:
    """Convenience wrapper to derive participant snapshots map from an EventCascade."""

    return build_participant_snapshots_map(event.stages or [])


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
