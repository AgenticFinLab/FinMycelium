"""
Base entities and containers for financial event reconstruction.
"""

import os
import json
import pickle
import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List

from langgraph.graph import MessagesState
from langgraph.graph.state import CompiledStateGraph

from lmbase.inference.api_call import LangChainAPIInference

# from lmbase.inference.model_call import LLMInference
from lmbase.utils.tools import BaseContainer

from finmy.generic import UserQueryInput, DataSample
from finmy.builder.agent_build.structure import EventCascade


@dataclass
class BuildInput(BaseContainer):
    """Input format of the event reconstruction builder."""

    user_query: UserQueryInput
    samples: List[DataSample]


@dataclass
class BuildOutput(BaseContainer):
    """Output format of the pipeline builder."""

    event_cascades: List[EventCascade] = field(default_factory=list)
    result: Optional[Any] = None
    logs: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


class AgentState(MessagesState):
    """State container used during a multi-agent LangGraph run.

    Purpose:
    - Carry immutable pipeline inputs (user query and matched samples).
    - Hold per-agent prompts and collect structured outputs for each agent execution.
    - Track execution order and basic cost metrics for auditability.

    Lifecycle:
    - Initialize once at graph start with `build_input` and agent prompt maps.
    - Each agent node reads its prompts from `agent_system_msgs`/`agent_user_msgs`,
      produces an output, appends it to `agent_results`, and records its name in `agent_executed`.
    - Costs (e.g., tokens, latency) may be appended to `cost` after each execution.

    Notes:
    - Fields are designed to be simple serializable structures (dicts/lists) to ease persistence.
    - `messages` is reserved for LangGraph internal message passing and may be unused by some nodes.
    """

    # Immutable pipeline input: user query and matched data samples
    build_input: BuildInput

    # Aggregated outputs: one entry per agent execution (keep agent_name in each entry)
    agent_results: List[Dict[str, Any]]
    # Logical execution order: list of agent names in the order they ran
    agent_executed: List[str]

    # Optional execution cost items: e.g., {"agent": "...", "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 0}
    cost: List[Dict[str, Any]]

    # Per-agent system prompts (agent_name -> system_prompt)
    agent_system_msgs: Dict[str, str]
    # Per-agent user prompts (agent_name -> user_prompt)
    agent_user_msgs: Dict[str, str]

    # LangGraph runtime messages envelope (optional; may be unused depending on node implementations)
    messages: List[Any] = None


class BaseBuilder(ABC):
    """Base class for event cascade builders."""

    def __init__(
        self,
        method_name: Optional[str] = None,
        build_config: Optional[dict] = None,
    ):
        self.build_config = build_config
        self.agents_config = build_config["agents"]

        self.method_name = method_name

        # By default, we set only one lm for agents
        # for any agent with a different generation config, we only
        # change the generation config.
        self.agents_lm = None

        self.define_agent_models()

        build_output = (
            f"build_output_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        )
        self.save_dir = os.path.join(build_config["save_folder"], build_output)

        os.makedirs(self.save_dir, exist_ok=True)

    def define_agent_models(self):
        """Define the models for the agent."""
        lm_type = self.build_config["lm_type"]
        model_name = self.build_config["lm_name"]

        if "api" in lm_type.lower():
            self.agents_lm = LangChainAPIInference(
                lm_name=model_name,
                generation_config=self.build_config["generation_config"],
            )
        # else:
        #     self.agents_lm = LLMInference(
        #         lm_path=model_name,
        #         inference_config=self.build_config["inference_config"],
        #         generation_config=self.build_config["generation_config"],
        #     )

    def get_save_name(
        self,
        agent_name: str,
        execution_idx: int,
        **kwargs,
    ) -> str:
        """Return the filename (or full path) used to persist stage outputs.

        Parameters
        - agent_name: The logical name of the agent/stage.
        - execution_idx: The per-agent execution count used for disambiguation.
        - **kwargs: Optional naming options (e.g., dir, ext, prefix, suffix, timestamp).

        Returns
        - A deterministic string suitable for saving artifacts like pickled outputs.
        """
        return f"{agent_name}-{execution_idx}"

    def save_traces(
        self,
        traces: Any,
        save_name: str,
        file_format: str,
        **kwargs,
    ) -> None:
        """Save the traces of the agent to the state.

        Parameters
        - state: The current state of the agent.
        """

        save_path = os.path.join(self.save_dir, f"{save_name}.{file_format}")
        # Save the traces
        if file_format == "json":
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(traces, f, ensure_ascii=False, indent=4)
        else:
            with open(save_path, "wb", encoding="utf-8") as f:
                pickle.dump(traces, f, ensure_ascii=False, indent=4)

    @abstractmethod
    def execute_agent(self, state: AgentState, agent_name: str) -> AgentState:
        """Execute exactly one stage using prompts from the provided state.

        Due to that the langgraph does not support the additional argument, i.e. agent_name, here, one need to use the partial to bind the agent_name to the function during the node creation of the graph.

        Requirements
        - Read system/user prompts from AgentState for the current agent.
        - Produce a model output and write it to state.agent_results[agent_name].
        - Update state.execute_count[agent_name] (increment by 1).
        - Optionally persist artifacts using get_save_name.

        Returns
        - The updated AgentState after this stage completes.
        """

    @abstractmethod
    def graph(self) -> CompiledStateGraph:
        """Construct and compile the LangGraph for this agent or pipeline.

        Note that the `execute_agent` function should be bound with the 'agent_name' using partial.

        Returns
        - A CompiledStateGraph with entry point and edges defined.
        """

    @abstractmethod
    def run(self, build_input: BuildInput):
        """Run the builder pipeline.

        This abstract method defines the interface for executing the complete event reconstruction process.
        Concrete implementations should:
        1. Initialize necessary resources (e.g., prompts, models).
        2. Construct the execution graph via `self.graph()`.
        3. Prepare the initial state with `build_input`.
        4. Invoke the graph to process the input.
        5. Integrate and format the results into a `BuildOutput` object.

        Args:
            build_input (BuildInput): The structured input containing user query and data samples.

        Returns:
            BuildOutput: The final output containing the reconstructed event cascades and execution logs.
        """
