"""
Implementation of the financial event reconstruction using a step-by-step multi-agent approach.

The pipeline follows a specific sequence to reconstruct a financial event cascade from unstructured text:

1. **Skeleton Reconstruction**:
   - Generates the overall `EventCascade` structure (Stages -> Episodes) based on the user query and data samples.
   - Provides a high-level roadmap without detailed fields.

2. **Episode Loop (Sequential Reconstruction)**:
   For each episode defined in the skeleton, the following agents execute in order:

   a. **ParticipantReconstructor**:
      - Identifies participants involved in the specific episode.
      - Inputs: Skeleton context, previous participants (for ID reuse).
      - Outputs: List of `Participant` objects (with "P_{int}" IDs).

   b. **TransactionReconstructor**:
      - Identifies financial transactions within the episode.
      - Inputs: Episode context, participants from step (a).
      - Outputs: List of `Transaction` objects linking the identified participants.

   c. **EpisodeReconstructor**:
      - Fills in detailed episode attributes (description, time, relations).
      - Inputs: Episode context, participants from (a), transactions from (b).
      - Outputs: A fully populated `Episode` object.

3. **Integration**:
   - Merges the outputs of all agents into a final, complete `EventCascade`.
   - Supports resuming or integrating from saved intermediate result files.

The architecture uses a `LangGraph` state machine to manage the flow and `AgentState` to pass data between steps.
"""

import time
import copy
import os
import json
from functools import partial
from pathlib import Path

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from lmbase.inference.base import InferInput, InferOutput
from finmy.builder.base import BaseBuilder
from finmy.builder.utils import (
    load_python_text,
    filter_dataclass_fields,
    extract_json_response,
)
from finmy.builder.base import AgentState
from finmy.builder.agent_build.structure import Episode

# Obtain all text content under the structure.py
_STRUCTURE_SPEC_FULL = load_python_text(
    path=Path(__file__).resolve().parent / "structure.py"
)
# Read dataclass definitions from structure.py to embed schema text in prompts
# Skeleton for guiding layout extraction
_SKELETON_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "VerifiableField": [],
        "EventCascade": [],
        "EventStage": [],
        "Episode": ["episode_id", "name", "index_in_stage", "start_time", "end_time"],
    },
)


_PARTICIPANT_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "Participant": [],
        "Action": [],
        "VerifiableField": [],
    },
)

_EPISODE_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "ParticipantRelation": [],
        "Action": [],
        "Transaction": [],
        "VerifiableField": [],
        "Episode": [],
    },
)


_TRANSACTION_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "Transaction": [],
        "VerifiableField": [],
    },
)


class AgentEventBuilder(BaseBuilder):
    """Integrated builder that performs the full event reconstruction pipeline:
    1. SkeletonReconstruction: Generates the overall event structure (EventCascade).
    2. Loop over Episodes:
        a. ParticipantReconstruction: Identifies participants for the current episode.
        b. TransactionReconstructor: Reconstructs transactions for the current episode.
        c. EpisodeReconstruction: Reconstructs the full episode using the skeleton, participants, and transactions.
    """

    def extract_latest_episode(
        self,
        event_skeleton: dict,
        num_episodes: int,
    ):
        """
        Extract the latest episode from the event skeleton based on the num_episodes.
        """
        idx = 0
        for stage in event_skeleton["stages"]:
            for episode in stage["episodes"]:
                if idx == num_episodes:
                    return stage, episode
                idx += 1
        return None, None

    def _collect_reconstructed_participants_structure(self, state: AgentState):
        """Build a full EventCascade-shaped structure from the Skeleton result,
        and inject already reconstructed participants into the corresponding episodes
        in sequence order.

        Returns a deep-copied EventCascade object with participants filled.
        """
        event_skeleton = state["agent_results"][0]["SkeletonReconstructor"]
        skeleton_copy = copy.deepcopy(event_skeleton)

        pr_results = [
            e["ParticipantReconstructor"]
            for e in state["agent_results"]
            if "ParticipantReconstructor" in e
        ]
        idx = 0
        for st in skeleton_copy["stages"]:
            for ep in st["episodes"]:
                if idx < len(pr_results):
                    ep["participants"] = pr_results[idx]["participants"]
                else:
                    ep["participants"] = []
                idx += 1
        return skeleton_copy

    def execute_agent(self, state: AgentState, agent_name: str) -> AgentState:
        """
        Executes a single step (Agent) in the reconstruction pipeline.

        This function handles the prompt construction, context retrieval, and state management
        for all agents: Skeleton, Participant, Transaction, and Episode Reconstructors.

        Key Logic:
        - **SkeletonReconstructor**: Runs once at the start to define the roadmap.
        - **ParticipantReconstructor**:
            - Runs for each episode.
            - Uses `_collect_reconstructed_participants_structure` to provide context of
              previously identified participants across stages for ID consistency.
        - **TransactionReconstructor**:
            - Runs for each episode *after* ParticipantReconstructor.
            - Retrieves the *just-generated* participants from `state["agent_results"][-1]`
              to ensure transactions link valid IDs.
        - **EpisodeReconstructor**:
            - Runs for each episode *after* TransactionReconstructor.
            - Retrieves transactions from `state["agent_results"][-1]` and
              participants from `state["agent_results"][-2]` to fully populate the episode.

        Args:
            state (AgentState): The current accumulation of build inputs and results.
            agent_name (str): The name of the agent to execute (bound via `partial` in the graph).

        Returns:
            AgentState: Updated state with the new agent result appended.
        """
        t0 = time.time()
        build_ipt = state["build_input"]

        # Common prompt arguments
        prompt_kwargs = {
            "Query": build_ipt.user_query.query_text,
            "Keywords": build_ipt.user_query.key_words,
            "Content": "\n".join([sample.content for sample in build_ipt.samples]),
        }

        # Retrieve templates
        sys_msg_template = state["agent_system_msgs"][agent_name]
        user_msg_template = state["agent_user_msgs"][agent_name]

        savename_suffix = ""
        sys_msg = ""

        # Logic branching based on agent_name
        if agent_name == "SkeletonReconstructor":
            sys_msg = sys_msg_template.format(STRUCTURE_SPEC=_SKELETON_SPEC)

        elif agent_name in [
            "ParticipantReconstructor",
            "TransactionReconstructor",
            "EpisodeReconstructor",
        ]:
            # Retrieve skeleton (always the first result)
            event_skeleton = state["agent_results"][0]["SkeletonReconstructor"]

            # Determine which episode we are on
            current_count = state["agent_executed"].count(agent_name)
            belong_state, latest_episode = self.extract_latest_episode(
                event_skeleton, current_count
            )

            if not latest_episode:
                # Should not happen if logic is correct, but good to handle
                raise ValueError(f"Could not find episode for count {current_count}")

            target_episode = Episode(**latest_episode)

            savename_suffix = f"-Stage{belong_state['index_in_event']}-Episode{target_episode.index_in_stage}"

            if agent_name == "ParticipantReconstructor":
                sys_msg = sys_msg_template.format(STRUCTURE_SPEC=_PARTICIPANT_SPEC)
                prompt_kwargs["TargetEpisode"] = target_episode
                prompt_kwargs["ReconstructedParticipants"] = (
                    self._collect_reconstructed_participants_structure(state)
                )

            elif agent_name == "TransactionReconstructor":
                # Get participants from the immediately preceding step (ParticipantReconstructor)
                last_result = state["agent_results"][-1]
                if "ParticipantReconstructor" in last_result:
                    participants_data = last_result["ParticipantReconstructor"]
                    target_episode.participants = participants_data.get(
                        "participants", []
                    )

                sys_msg = sys_msg_template.format(STRUCTURE_SPEC=_TRANSACTION_SPEC)
                prompt_kwargs["TargetEpisode"] = target_episode

            elif agent_name == "EpisodeReconstructor":
                # Get transactions from the immediately preceding step (TransactionReconstructor)
                last_result = state["agent_results"][-1]
                if "TransactionReconstructor" in last_result:
                    transactions_data = last_result["TransactionReconstructor"]
                    target_episode.transactions = transactions_data.get(
                        "transactions", []
                    )

                # Get participants from the step before that (ParticipantReconstructor)
                second_last_result = state["agent_results"][-2]
                if "ParticipantReconstructor" in second_last_result:
                    participants_data = second_last_result["ParticipantReconstructor"]
                    target_episode.participants = participants_data.get(
                        "participants", []
                    )

                sys_msg = sys_msg_template.format(STRUCTURE_SPEC=_EPISODE_SPEC)
                prompt_kwargs["StageSkeleton"] = belong_state
                prompt_kwargs["TargetEpisode"] = target_episode

        # Escape braces for format if needed.
        # We escape them because the downstream inference engine (LangChain)
        # treats the system message as a template and will try to substitute variables.
        # Since we just injected a JSON schema containing braces, we must escape them.
        sys_msg = sys_msg.replace("{", "{{").replace("}", "}}")

        out: InferOutput = self.agents_lm.run(
            infer_input=InferInput(system_msg=sys_msg, user_msg=user_msg_template),
            **prompt_kwargs,
        )
        result = out.response

        # Persist traces
        savename = (
            self.get_save_name(agent_name, len(state["agent_executed"]) + 1)
            + savename_suffix
        )
        self.save_traces({agent_name: out.to_dict()}, savename, "json")

        parsed_result = extract_json_response(result)
        self.save_traces(parsed_result, f"{savename}-Result", "json")

        # Update state
        state["agent_results"].append({agent_name: parsed_result})
        state["cost"].append({agent_name: {"latency": time.time() - t0}})
        state["agent_executed"].append(agent_name)
        return state

    def graph(self) -> CompiledStateGraph[AgentState]:
        """
        Constructs and compiles the LangGraph state machine for the reconstruction pipeline.

        Flow:
        1. **START** -> **SkeletonReconstructor**:
           - Initial step to generate the event structure.

        2. **SkeletonReconstructor** -> **ParticipantReconstructor**:
           - Enters the sequential reconstruction loop.

        3. **The Loop** (Repeated for each episode):
           - **ParticipantReconstructor** -> **TransactionReconstructor**:
             - Participants are identified first.
           - **TransactionReconstructor** -> **EpisodeReconstructor**:
             - Transactions are identified using the participants.
           - **EpisodeReconstructor** -> **(Conditional Edge)**:
             - Checks if all episodes in the skeleton are processed.
             - If **not done**: Loops back to **ParticipantReconstructor** for the next episode.
             - If **done**: Goes to **END**.

        Returns:
            CompiledStateGraph[AgentState]: The compiled graph ready for execution.
        """
        g = StateGraph(AgentState)

        # Use partial to bind agent_name to execute_agent
        g.add_node(
            "SkeletonReconstructor",
            partial(self.execute_agent, agent_name="SkeletonReconstructor"),
        )
        g.add_node(
            "ParticipantReconstructor",
            partial(self.execute_agent, agent_name="ParticipantReconstructor"),
        )
        g.add_node(
            "TransactionReconstructor",
            partial(self.execute_agent, agent_name="TransactionReconstructor"),
        )
        g.add_node(
            "EpisodeReconstructor",
            partial(self.execute_agent, agent_name="EpisodeReconstructor"),
        )

        g.add_edge(START, "SkeletonReconstructor")
        g.add_edge("SkeletonReconstructor", "ParticipantReconstructor")
        g.add_edge("ParticipantReconstructor", "TransactionReconstructor")
        g.add_edge("TransactionReconstructor", "EpisodeReconstructor")

        def _route(state: AgentState) -> str:
            skeleton = state["agent_results"][0]["SkeletonReconstructor"]
            total = sum([len(stage["episodes"]) for stage in skeleton["stages"]])

            # Count how many episodes have been fully processed (EpisodeReconstructor runs)
            num_processed = state["agent_executed"].count("EpisodeReconstructor")

            return "end" if num_processed >= total else "continue"

        g.add_conditional_edges(
            "EpisodeReconstructor",
            _route,
            {
                "continue": "ParticipantReconstructor",
                "end": END,
            },
        )

        return g.compile()

    def integrate_results(self, state: AgentState) -> dict:
        """
        Integrate all reconstruction results into a single EventCascade JSON structure.

        Logic:
        1. Starts with the `Skeleton` as the base structure.
        2. Iterates through the sequential results of Participant, Transaction, and Episode agents.
        3. Since the graph execution guarantees a strict order (P->T->E per episode),
           we can align results by index.
        4. Populates each episode in the skeleton with the fully reconstructed details.

        Args:
            state (AgentState): State containing `agent_results` list.

        Returns:
            dict: The final EventCascade structure.
        """
        # 1. Base is the skeleton
        event_skeleton = state["agent_results"][0]["SkeletonReconstructor"]
        final_cascade = copy.deepcopy(event_skeleton)

        # 2. Collect sequential results
        # The graph execution guarantees P -> T -> E order per episode.
        p_results = [
            r["ParticipantReconstructor"]
            for r in state["agent_results"]
            if "ParticipantReconstructor" in r
        ]
        t_results = [
            r["TransactionReconstructor"]
            for r in state["agent_results"]
            if "TransactionReconstructor" in r
        ]
        e_results = [
            r["EpisodeReconstructor"]
            for r in state["agent_results"]
            if "EpisodeReconstructor" in r
        ]

        # 3. Fill in the cascade
        idx = 0
        for stage in final_cascade["stages"]:
            new_episodes = []
            # Iterate over the original skeleton episodes to maintain structure/count
            for _ in stage["episodes"]:
                # Ensure we have results for this index if execution reached this point
                if (
                    idx < len(e_results)
                    and idx < len(p_results)
                    and idx < len(t_results)
                ):
                    # Start with the rich episode details (descriptions, relations, times)
                    # This dict currently has placeholders for participants/transactions
                    rich_episode = copy.deepcopy(e_results[idx])

                    # Inject Participants
                    rich_episode["participants"] = p_results[idx].get(
                        "participants", []
                    )

                    # Inject Transactions
                    rich_episode["transactions"] = t_results[idx].get(
                        "transactions", []
                    )

                    new_episodes.append(rich_episode)
                else:
                    raise RuntimeError(
                        f"Missing reconstruction results for episode index {idx} in stage '{stage.get('name', 'unknown')}'. "
                        f"Expected results for all episodes. "
                        f"Current counts: Episodes={len(e_results)}, Participants={len(p_results)}, Transactions={len(t_results)}."
                    )

                idx += 1

            # Replace the skeleton episodes with the fully constructed ones
            stage["episodes"] = new_episodes

        return final_cascade

    def integrate_from_files(self) -> dict:
        """
        Reconstructs the EventCascade from saved result files in the save directory.
        Scans for files ending with '-Result.json'.
        """
        # Scan directory
        files_map = {}
        if not os.path.exists(self.save_dir):
            raise FileNotFoundError(f"Save directory {self.save_dir} does not exist.")

        for filename in os.listdir(self.save_dir):
            if filename.endswith("-Result.json"):
                # Split by '-' to get metadata
                # Format: AgentName-Index[-Suffix...]-Result.json
                parts = filename.split("-")

                # We expect at least AgentName and Index
                if len(parts) >= 2:
                    agent_name = parts[0]
                    try:
                        idx = int(parts[1])
                        files_map[idx] = (agent_name, filename)
                    except ValueError:
                        # Skip files where the second part is not an integer index
                        continue

        # Sort by index to maintain execution order
        sorted_indices = sorted(files_map.keys())

        # Check if we have results
        if not sorted_indices:
            raise FileNotFoundError(f"No result files found in {self.save_dir}")

        # Read files and reconstruct agent_results
        agent_results = []

        for idx in sorted_indices:
            agent_name, filename = files_map[idx]
            filepath = os.path.join(self.save_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            agent_results.append({agent_name: data})

        # Create a dummy state
        # integrate_results only needs state["agent_results"]
        dummy_state = {"agent_results": agent_results}

        return self.integrate_results(dummy_state)
