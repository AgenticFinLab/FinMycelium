"""
Base entities and containers for financial event reconstruction.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List

from finmy.generic import UserQueryInput
from finmy.generic import MetaSample
from finmy.builder.structure import EventCascade, EventStage, ParticipantState


def build_participant_states_map(
    stages: List[EventStage],
) -> Dict[str, List[ParticipantState]]:
    """Merge stage-level and episode-level states into a global map keyed by participant_id.

    Returns a mapping `participant_id -> List[ParticipantState]` sorted by timestamp.
    """

    states_by_participant: Dict[str, List[ParticipantState]] = {}
    for stage in stages or []:
        for pid, states in (stage.participant_states or {}).items():
            states_by_participant.setdefault(pid, []).extend(states or [])
        for episode in stage.episodes or []:
            for pid, states in (episode.participant_states or {}).items():
                states_by_participant.setdefault(pid, []).extend(states or [])

    for pid, arr in states_by_participant.items():
        arr.sort(key=lambda s: s.timestamp)

    return states_by_participant


def build_participant_states_map_from_event(
    event: EventCascade,
) -> Dict[str, List[ParticipantState]]:
    """Convenience wrapper to derive participant states map from an EventCascade."""

    return build_participant_states_map(event.stages or [])


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
