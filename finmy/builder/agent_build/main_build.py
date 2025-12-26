"""
Step-wise financial event reconstruction using a multi-agent pipeline with explicit
state management and schema-constrained prompts.

Overview:
- Input: `BuildInput` containing `UserQueryInput` and a list of `DataSample`s (source text).
- Output: Fully assembled `EventCascade` with stages, episodes, participants, transactions,
  relations, and grounded descriptions at stage and event levels.

Execution Flow:
1) Skeleton Reconstruction
   - Agent: `SkeletonReconstructor`
   - Goal: Produce an `EventCascade` skeleton (Stages -> Episodes) strictly from `Content`
     using `VerifiableField` for applicable fields.
   - Note: Only structure fields are generated (no descriptions at this step).

2) Skeleton Verification
   - Agent: `SkeletonChecker`
   - Goal: Audit and correct the initial skeleton.
   - Input: `ProposedSkeleton` from step 1, plus `Content`, `Query`, `Keywords`.
   - Action: Validates time hierarchy, consistency, and completeness. Corrects errors while strictly maintaining JSON structure.
   - Critical: The output of this agent becomes the definitive skeleton for all subsequent steps.

3) Episode Loop (per episode in CORRECTED skeleton order)
   a) `ParticipantReconstructor`
      - Identifies and reconstructs episode participants (including `Action`s).
      - Reuses participant IDs across episodes via already reconstructed participants.
   b) `TransactionReconstructor`
      - Reconstructs financial transactions among the episode’s participants.
      - Ensures `from_participant_id`/`to_participant_id` refer to valid participants.
   c) `EpisodeReconstructor`
      - Produces a complete `Episode` (relations, descriptions, timestamps).
      - Emits placeholders for `participants` and `transactions` to avoid duplication,
        which are later replaced during integration.

4) Description Reconstruction
   - `StageDescriptionReconstructor`: Runs once after finishing all episodes within a stage.
     Produces grounded stage `descriptions` based on reconstructed episodes plus source content.
   - `EventDescriptionReconstructor`: Runs once after all stages are completed.
     Produces grounded event `descriptions` based on the full cascade plus source content.

5) Integration
   - `integrate_results`: Consolidates all agent outputs into a complete `EventCascade`.
     Replaces episode placeholders with actual participants/transactions, attaches stage
     and event descriptions, and preserves the skeleton’s ordering.
   - `integrate_from_files`: Reads saved `*-Result.json` artifacts, reconstructs
     `agent_results` sequence, and delegates to `integrate_results` to assemble the final cascade.

Architecture:
- Orchestration: `LangGraph` (`StateGraph`) with conditional routing:
  Skeleton -> SkeletonChecker -> (Participant -> Transaction -> Episode)* -> StageDescription (per-stage) -> EventDescription -> END.
- Schema text: Derived from `structure.py`, filtered per-agent scope via `filter_dataclass_fields`.
- State: `AgentState` carries prompts, inputs, and incremental results throughout the pipeline.
"""

import time
import copy
import os
import json
from functools import partial
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from lmbase.inference.base import InferInput, InferOutput
from finmy.builder.base import BaseBuilder, BuildInput, BuildOutput
from finmy.builder.utils import (
    load_python_text,
    filter_dataclass_fields,
    extract_json_response,
)
from finmy.builder.base import AgentState
from finmy.builder.agent_build.structure import Episode
from finmy.builder.agent_build.prompts import *

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
        "EventCascade": [
            "event_id",
            "title",
            "event_type",
            "start_time",
            "end_time",
            "stages",
        ],
        "EventStage": [
            "stage_id",
            "name",
            "index_in_event",
            "start_time",
            "end_time",
            "episodes",
        ],
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

_TRANSACTION_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "Transaction": [],
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


_STAGE_DESCRIPTION_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "EventStage": [],
        "VerifiableField": [],
    },
)


_EVENT_DESCRIPTION_SPEC = filter_dataclass_fields(
    _STRUCTURE_SPEC_FULL,
    {
        "EventCascade": [],
        "VerifiableField": [],
    },
)


class AgentEventBuilder(BaseBuilder):
    """Integrated builder that performs the full event reconstruction pipeline:
    1. SkeletonReconstruction: Generates the overall event structure (EventCascade).
    2. SkeletonChecker: Validates and corrects the skeleton structure and timeline.
    3. Loop over Episodes (based on Checked Skeleton):
        a. ParticipantReconstruction: Identifies participants for the current episode.
        b. TransactionReconstructor: Reconstructs transactions for the current episode.
        c. EpisodeReconstruction: Reconstructs the full episode using the skeleton, participants, and transactions.
    4. StageDescriptionReconstructor:
        - Runs after completing all episodes within a stage.
        - Produces grounded `descriptions` for the stage using reconstructed episodes plus source content.
    5. EventDescriptionReconstructor:
        - Runs after all stages are complete.
        - Produces grounded `descriptions` for the entire event using the full cascade plus source content.
    """

    def _get_agent_prompts(self):
        """Initialize system and user prompts for all agents."""
        agent_system_msgs = {}
        agent_user_msgs = {}

        # Skeleton
        agent_system_msgs["SkeletonReconstructor"] = EventLayoutReconstructorSys
        agent_user_msgs["SkeletonReconstructor"] = EventLayoutReconstructorUser

        agent_system_msgs["SkeletonChecker"] = SkeletonCheckerSys
        agent_user_msgs["SkeletonChecker"] = SkeletonCheckerUser

        # Participant
        agent_system_msgs["ParticipantReconstructor"] = ParticipantReconstructorSys
        agent_user_msgs["ParticipantReconstructor"] = ParticipantReconstructorUser

        # Transaction
        agent_system_msgs["TransactionReconstructor"] = TransactionReconstructorSys
        agent_user_msgs["TransactionReconstructor"] = TransactionReconstructorUser

        # Episode
        agent_system_msgs["EpisodeReconstructor"] = EpisodeReconstructorSys
        agent_user_msgs["EpisodeReconstructor"] = EpisodeReconstructorUser

        # Stage Description
        agent_system_msgs["StageDescriptionReconstructor"] = (
            StageDescriptionReconstructorSys
        )
        agent_user_msgs["StageDescriptionReconstructor"] = (
            StageDescriptionReconstructorUser
        )

        # Event Description
        agent_system_msgs["EventDescriptionReconstructor"] = (
            EventDescriptionReconstructorSys
        )
        agent_user_msgs["EventDescriptionReconstructor"] = (
            EventDescriptionReconstructorUser
        )

        return agent_system_msgs, agent_user_msgs

    def _get_event_skeleton(self, state: AgentState) -> dict:
        """
        Retrieves the definitive event skeleton.
        Prioritizes SkeletonChecker result if available, otherwise SkeletonReconstructor.
        """
        # Search for SkeletonChecker result in agent_results
        for res in state["agent_results"]:
            if "SkeletonChecker" in res:
                return res["SkeletonChecker"]

        # Fallback to SkeletonReconstructor (should be at index 0)
        return state["agent_results"][0]["SkeletonReconstructor"]

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

    def get_completed_stage_index(self, state: AgentState) -> int:
        """
        Determines if a stage has just been completed based on the number of executed episodes.
        Returns the index of the completed stage, or -1 if no stage boundary was just crossed.
        """
        event_skeleton = self._get_event_skeleton(state)
        # Count total episodes completed so far (assuming EpisodeReconstructor is the last step per episode loop)
        episodes_completed = state["agent_executed"].count("EpisodeReconstructor")

        cumulative_episodes = 0
        for i, stage in enumerate(event_skeleton["stages"]):
            num_episodes_in_stage = len(stage["episodes"])
            cumulative_episodes += num_episodes_in_stage

            # If the total completed equals the cumulative count at the end of this stage,
            # we just finished this stage.
            # NOTE: We need to ensure we don't return True if we've already processed this stage's description.
            # But the graph logic will handle that by routing.
            # Here we just want to know "Are we at a boundary?"
            if episodes_completed == cumulative_episodes:
                return i

        return -1

    def _collect_reconstructed_participants_structure(self, state: AgentState):
        """Build a full EventCascade-shaped structure from the Skeleton result,
        and inject already reconstructed participants into the corresponding episodes
        in sequence order.

        Returns a deep-copied EventCascade object with participants filled.
        Note: This creates a fresh copy of the skeleton. For episodes not yet processed,
        participants will be empty (as initialized in the skeleton), ensuring safety.
        """
        event_skeleton = self._get_event_skeleton(state)
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

        elif agent_name == "SkeletonChecker":
            # Pass the previous Skeleton as context
            # It should be the first result
            skeleton_result = state["agent_results"][0]["SkeletonReconstructor"]
            prompt_kwargs["ProposedSkeleton"] = json.dumps(
                skeleton_result, default=str, indent=2
            )
            sys_msg = sys_msg_template.format(STRUCTURE_SPEC=_SKELETON_SPEC)

        elif agent_name == "StageDescriptionReconstructor":
            # Identify which stage we just finished
            # We can rely on the number of times StageDescriptionReconstructor has run?
            # Or recalculate using get_completed_stage_index logic, but we need the exact stage index.
            # Since the graph routes here only when a stage is done, and we process stages sequentially:
            # The index of the stage to process is equal to the number of times this agent has already run.

            stage_idx = state["agent_executed"].count("StageDescriptionReconstructor")
            savename_suffix = f"-Stage{stage_idx}"
            event_skeleton = self._get_event_skeleton(state)

            # We need to construct the "TargetStage" with all episodes filled in.
            # First, get the skeleton of the target stage
            if stage_idx < len(event_skeleton["stages"]):
                target_stage_skeleton = copy.deepcopy(
                    event_skeleton["stages"][stage_idx]
                )

                # Now populate it with the actual reconstructed episodes
                # We need to find the global episode indices for this stage
                start_ep_idx = 0
                for i in range(stage_idx):
                    start_ep_idx += len(event_skeleton["stages"][i]["episodes"])

                # Collect reconstructed episodes
                reconstructed_episodes = []
                for j in range(len(target_stage_skeleton["episodes"])):
                    global_ep_idx = start_ep_idx + j
                    # Find the result for this episode.
                    # EpisodeReconstructor results are in state["agent_results"]
                    # We need to filter for EpisodeReconstructor outputs
                    ep_results = [
                        r["EpisodeReconstructor"]
                        for r in state["agent_results"]
                        if "EpisodeReconstructor" in r
                    ]

                    if global_ep_idx < len(ep_results):
                        reconstructed_episodes.append(ep_results[global_ep_idx])

                # Replace episodes in skeleton with fully reconstructed ones
                target_stage_skeleton["episodes"] = reconstructed_episodes

                prompt_kwargs["TargetStage"] = json.dumps(
                    target_stage_skeleton, default=str, indent=2
                )

            sys_msg = sys_msg_template.format(
                STRUCTURE_SPEC=_STAGE_DESCRIPTION_SPEC,
            )

        elif agent_name == "EventDescriptionReconstructor":
            # Construct the full EventCascade with all reconstructed data
            # similar to integrate_results but without the final descriptions yet

            # Start with skeleton
            event_skeleton = self._get_event_skeleton(state)
            full_cascade = copy.deepcopy(event_skeleton)

            # Collect all episodes
            ep_results = [
                r["EpisodeReconstructor"]
                for r in state["agent_results"]
                if "EpisodeReconstructor" in r
            ]

            # Fill them into the cascade
            ep_cursor = 0
            for stage in full_cascade["stages"]:
                num_eps = len(stage["episodes"])
                stage["episodes"] = ep_results[ep_cursor : ep_cursor + num_eps]
                ep_cursor += num_eps

                # Also potentially inject the stage descriptions if we want the event summarizer to see them?
                # The user didn't explicitly ask for this, but it helps.
                # Let's find StageDescriptionReconstructor results
                sd_results = [
                    r["StageDescriptionReconstructor"]
                    for r in state["agent_results"]
                    if "StageDescriptionReconstructor" in r
                ]

                # Match stage descriptions to stages
                # Assuming sequential execution matches order
                current_stage_idx = full_cascade["stages"].index(stage)
                if current_stage_idx < len(sd_results):
                    sd_res = sd_results[current_stage_idx]
                    stage["descriptions"] = sd_res["descriptions"]

            prompt_kwargs["EventCascade"] = json.dumps(
                full_cascade, default=str, indent=2
            )

            sys_msg = sys_msg_template.format(
                STRUCTURE_SPEC=_EVENT_DESCRIPTION_SPEC,
            )

        elif agent_name in [
            "ParticipantReconstructor",
            "TransactionReconstructor",
            "EpisodeReconstructor",
        ]:
            # Retrieve definitive skeleton (prioritizing Checker result)
            event_skeleton = self._get_event_skeleton(state)

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
                participants_data = last_result["ParticipantReconstructor"]
                target_episode.participants = participants_data["participants"]

                sys_msg = sys_msg_template.format(STRUCTURE_SPEC=_TRANSACTION_SPEC)
                prompt_kwargs["TargetEpisode"] = target_episode

            elif agent_name == "EpisodeReconstructor":
                # Get transactions from the immediately preceding step (TransactionReconstructor)
                last_result = state["agent_results"][-1]
                transactions_data = last_result["TransactionReconstructor"]
                target_episode.transactions = transactions_data["transactions"]

                # Get participants from the step before that (ParticipantReconstructor)
                second_last_result = state["agent_results"][-2]
                participants_data = second_last_result["ParticipantReconstructor"]
                target_episode.participants = participants_data["participants"]

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

    def graph(self) -> CompiledStateGraph:
        """
        Constructs and compiles the LangGraph state machine for the reconstruction pipeline.

        Workflow Overview:
        The pipeline reconstructs a financial event cascade in a hierarchical and sequential manner:

        1. **SkeletonReconstructor**:
           - **Start Node**.
           - Generates the high-level `EventCascade` structure (Stages -> Episodes) based on user query and content.
           - Defines the roadmap for the entire reconstruction.

        2. **SkeletonChecker**:
           - Runs immediately after SkeletonReconstructor.
           - Audits the proposed skeleton against Content and Schema.
           - Corrects time inconsistencies, hierarchy issues, and completeness.
           - **Crucial**: Its output serves as the authoritative ground truth for all downstream agents.

        3. **Episode Loop (Participant -> Transaction -> Episode)**:
           - Iterates through each episode defined in the **verified** skeleton.
           - **ParticipantReconstructor**: Identifies participants for the current episode.
           - **TransactionReconstructor**: Identifies transactions, linking the participants.
           - **EpisodeReconstructor**: Synthesizes full episode details (time, description, relations).

        4. **StageDescription Loop**:
           - **Trigger Condition**: After an episode is completed (`EpisodeReconstructor`), the system checks if a stage boundary is reached.
           - **StageDescriptionReconstructor**:
             - Runs *only* when all episodes in a specific stage are fully reconstructed.
             - Synthesizes a high-level description for that stage based on its completed episodes.
             - **Routing**:
               - If more stages exist: Loops back to `ParticipantReconstructor` to start the next stage's first episode.
               - If all stages are done: Proceeds to `EventDescriptionReconstructor`.

        5. **EventDescriptionReconstructor**:
           - **Final Node** (before END).
           - Runs after all stages and episodes are fully reconstructed.
           - Synthesizes the global event description based on the complete cascade.

        Returns:
            CompiledStateGraph[AgentState]: The compiled LangGraph ready for execution.
        """
        g = StateGraph(AgentState)

        # ============================================================================
        # 1. Add Nodes
        # ============================================================================

        # Skeleton: Generates the initial structure
        g.add_node(
            "SkeletonReconstructor",
            partial(self.execute_agent, agent_name="SkeletonReconstructor"),
        )
        g.add_node(
            "SkeletonChecker",
            partial(self.execute_agent, agent_name="SkeletonChecker"),
        )

        # Episode Level Agents
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

        # Summarization Agents
        g.add_node(
            "StageDescriptionReconstructor",
            partial(self.execute_agent, agent_name="StageDescriptionReconstructor"),
        )
        g.add_node(
            "EventDescriptionReconstructor",
            partial(self.execute_agent, agent_name="EventDescriptionReconstructor"),
        )

        # ============================================================================
        # 2. Set Entry Point and Basic Linear Edges
        # ============================================================================

        # Start with Skeleton
        g.set_entry_point("SkeletonReconstructor")

        # Basic Flow: Skeleton -> SkeletonChecker -> First Episode (Participant)
        g.add_edge("SkeletonReconstructor", "SkeletonChecker")
        g.add_edge("SkeletonChecker", "ParticipantReconstructor")

        # Intra-Episode Flow: Participant -> Transaction -> Episode
        g.add_edge("ParticipantReconstructor", "TransactionReconstructor")
        g.add_edge("TransactionReconstructor", "EpisodeReconstructor")

        # ============================================================================
        # 3. Conditional Logic (Routing)
        # ============================================================================

        def _route(state: AgentState):
            """
            Determines the next step after an Episode is reconstructed.

            Logic:
            1. Check if the just-completed episode marks the end of a stage.
            2. If yes, and we haven't generated the description for that stage yet -> Go to `StageDescriptionReconstructor`.
            3. If no (mid-stage), or stage description already done (unlikely path but safe) -> Check if there are more episodes.
            4. If more episodes exist -> Go to `ParticipantReconstructor` (next episode).
            5. If all episodes done -> (Fallback) END.
               (Note: Usually routed via StageDescriptionReconstructor -> EventDescriptionReconstructor).
            """
            # Check total episodes in the plan
            event_skeleton = self._get_event_skeleton(state)
            total_episodes = sum(
                len(stage["episodes"]) for stage in event_skeleton["stages"]
            )
            executed_episodes = state["agent_executed"].count("EpisodeReconstructor")

            # Check if a stage was just completed
            completed_stage_idx = self.get_completed_stage_index(state)

            # Count how many stage descriptions we have already generated
            executed_stage_descs = state["agent_executed"].count(
                "StageDescriptionReconstructor"
            )

            # Condition 1: End of a Stage -> Generate Stage Description
            # We check `completed_stage_idx != -1` (a stage just finished)
            # AND `completed_stage_idx == executed_stage_descs` (we haven't done this stage's desc yet)
            # Example: Finished Stage 0 (idx=0). executed_stage_descs=0. 0==0 -> True.
            if (
                completed_stage_idx != -1
                and completed_stage_idx == executed_stage_descs
            ):
                return "StageDescriptionReconstructor"

            # Condition 2: Not a stage boundary (or already handled), check for next episode
            if executed_episodes < total_episodes:
                return "ParticipantReconstructor"

            # Fallback (should ideally reach EventDescription via _route_from_stage_desc)
            return END

        def _route_from_stage_desc(state: AgentState):
            """
            Determines the next step after a Stage Description is generated.

            Logic:
            1. Check if there are more stages remaining.
            2. If yes -> Go to `ParticipantReconstructor` (Start first episode of next stage).
            3. If no (all stages done) -> Go to `EventDescriptionReconstructor` (Final Summary).
            """
            event_skeleton = self._get_event_skeleton(state)
            total_stages = len(event_skeleton["stages"])
            executed_stages = state["agent_executed"].count(
                "StageDescriptionReconstructor"
            )

            if executed_stages < total_stages:
                # Start next stage's first episode
                return "ParticipantReconstructor"
            else:
                # All stages done, generate global event description
                return "EventDescriptionReconstructor"

        # Route from EpisodeReconstructor
        g.add_conditional_edges(
            "EpisodeReconstructor",
            _route,
            {
                "ParticipantReconstructor": "ParticipantReconstructor",
                "StageDescriptionReconstructor": "StageDescriptionReconstructor",
                END: END,
            },
        )

        # Route from StageDescriptionReconstructor
        g.add_conditional_edges(
            "StageDescriptionReconstructor",
            _route_from_stage_desc,
            {
                "ParticipantReconstructor": "ParticipantReconstructor",
                "EventDescriptionReconstructor": "EventDescriptionReconstructor",
            },
        )

        # Final Step: Event Description -> END
        g.add_edge("EventDescriptionReconstructor", END)

        return g.compile()

    def integrate_results(self, state: AgentState) -> dict:
        """
        Integrates all agent results into the final EventCascade structure.
        """
        # 1. Start with the skeleton
        final_cascade = self._collect_reconstructed_participants_structure(state)

        # 2. Collect Transaction results
        tr_results = [
            r["TransactionReconstructor"]
            for r in state["agent_results"]
            if "TransactionReconstructor" in r
        ]

        # Also collect Participant results to reattach after Episode update
        p_results = [
            r["ParticipantReconstructor"]
            for r in state["agent_results"]
            if "ParticipantReconstructor" in r
        ]

        # 3. Collect Episode results
        er_results = [
            r["EpisodeReconstructor"]
            for r in state["agent_results"]
            if "EpisodeReconstructor" in r
        ]

        # Populate episodes in order
        ep_idx = 0
        for stage in final_cascade["stages"]:
            for episode in stage["episodes"]:
                if ep_idx < len(er_results):
                    # Replace with the fully reconstructed episode
                    episode.update(er_results[ep_idx])

                    # Ensure transactions are attached
                    if (
                        "transactions" not in episode
                        or not episode["transactions"]
                        or isinstance(episode["transactions"], str)
                    ):
                        if ep_idx < len(tr_results):
                            episode["transactions"] = tr_results[ep_idx]["transactions"]
                    # Ensure participants are attached (EpisodeReconstructor uses placeholders)
                    if "participants" not in episode or isinstance(
                        episode["participants"], str
                    ):
                        if ep_idx < len(p_results):
                            episode["participants"] = p_results[ep_idx]["participants"]
                ep_idx += 1

        # 4. Integrate StageDescriptionReconstructor results
        sd_results = [
            r["StageDescriptionReconstructor"]
            for r in state["agent_results"]
            if "StageDescriptionReconstructor" in r
        ]

        # Map results to stages sequentially
        for i, stage in enumerate(final_cascade["stages"]):
            if i < len(sd_results):
                res = sd_results[i]
                stage["descriptions"] = res["descriptions"]

        # 5. Integrate EventDescriptionReconstructor results
        ed_results = [
            r["EventDescriptionReconstructor"]
            for r in state["agent_results"]
            if "EventDescriptionReconstructor" in r
        ]

        if ed_results:
            # Should be only one
            res = ed_results[-1]
            final_cascade["descriptions"] = res["descriptions"]

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

    def run(self, build_input: BuildInput) -> BuildOutput:
        """Run the builder pipeline."""
        # 1. Get prompts
        agent_system_msgs, agent_user_msgs = self._get_agent_prompts()

        # 2. Build initial state
        state = {
            "build_input": build_input,
            "agent_results": [],
            "agent_executed": [],
            "cost": [],
            "agent_system_msgs": agent_system_msgs,
            "agent_user_msgs": agent_user_msgs,
        }

        # 3. Compile graph
        app = self.graph()

        # 4. Run graph
        # Increase recursion limit if needed, though default is usually 25
        # For long events, we might need more.
        config = self.build_config["graph_config"]
        final_state = app.invoke(state, config=config)

        # 5. Integrate results
        cascade_dict = self.integrate_results(final_state)
        self.save_traces(
            cascade_dict,
            save_name="FinalEventCascade",
            file_format="json",
        )
        restored_cascade = self.integrate_from_files()
        self.save_traces(
            restored_cascade,
            save_name="IntegratedEventCascade",
            file_format="json",
        )
        # 6. Construct BuildOutput
        # We wrap the result in BuildOutput.
        # Note: cascade_dict is a dictionary matching EventCascade structure.
        return BuildOutput(
            event_cascades=[cascade_dict],
            result=cascade_dict,
            logs=final_state["agent_executed"],
            extras=None,
        )
