"""
Minimal uTEST for AgentEventBuilder (Consolidated Pipeline)

This script validates the integrated multi-agent pipeline for financial event reconstruction.
It uses a synthetic "Ponzi Scheme" (Dutch Tulip Mania) scenario to test the flow.

Workflow:
1. **Setup**: Constructs a `BuildInput` with one `DataSample` and a `UserQueryInput`.
2. **Execution**: Invokes `AgentEventBuilder` via LangGraph.
   - **Skeleton Phase**: Generates the event structure.
   - **Loop Phase** (per episode):
     - ParticipantReconstructor -> TransactionReconstructor -> EpisodeReconstructor
   - **Description Phase**:
     - StageDescriptionReconstructor runs after finishing each stage’s episodes.
     - EventDescriptionReconstructor runs once after all stages are complete.
3. **Verification**:
   - Checks if the final `EventCascade` is correctly assembled.
   - Tests the `integrate_from_files` functionality to ensure resume/recovery capability.
   - Prints status and simple validation metrics (stage/episode counts).

Usage:
    python examples/uTEST/Builder/agent_build.py -c configs/uTEST/builder/agent_build.yml
"""

import uuid
import argparse
import yaml
from dotenv import load_dotenv

from finmy.generic import UserQueryInput, DataSample
from finmy.builder.base import BuildInput
from finmy.builder.agent_build.main_build import (
    AgentEventBuilder,
)
from finmy.builder.agent_build.prompts import *


def _generate_ponzi_content() -> str:
    """Generate fragmented English content about Dutch tulip mania."""
    fragments = [
        "Pamphlet mentions unusual prices paid for rare tulip bulbs in Haarlem.",
        "A merchant letter reports a neighbor pledging his house for a promised resale profit on a Semper Augustus.",
        "Coffeehouse talk: ‘contracts for future delivery’ traded late into the night; terms vary by guilders and ounces.",
        "A handwritten ledger shows entries for bulb notes changing hands three times in a week.",
        "Rumor spreads that a single bulb fetched more than a skilled artisan’s annual wage.",
        "Broadsheet advertises gatherings where buyers and sellers settle accounts with drafts and ale.",
        "A town notice warns citizens about reckless speculation; no official ban declared.",
        "Correspondence claims profits arise mainly from new subscriptions rather than cultivation.",
        "A tavern receipt lists wagers tied to ‘rare striped varieties’ with disputed provenance.",
        "Neighbors report delayed settlements and overturned promises after price swings.",
        "A notary records disputes over delivery quality and missing bulbs post frost.",
        "Travelers retell tales of fortunes made and lost within a fortnight.",
        "An apothecary complains about clients paying in bulb notes instead of coin.",
        "Local clerk copies a list of names owing sums tied to flower contracts.",
        "Printed satire mocks gentlemen measuring status by bulb certificates.",
        "Gossip suggests linked accounts shuttle funds between related traders.",
        "A parish report mentions families selling furniture to meet margin calls.",
        "Market whisper: some payouts are covered by fresh commitments, not harvest proceeds.",
        "Noticeboard states a civic court will hear cases about tulip debts.",
        "A foreign visitor writes that distant buyers never see the gardens they boast of.",
    ]
    text = " ".join(fragments)
    return text


def main():
    """Test the step builder based on the Dutch Tulip Mania."""
    # 1. Load the environment and the configs
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Run sequential multi-agent test with YAML config."
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="",
        help="Path to YAML config file for sequential agents",
    )
    args = parser.parse_args()
    config_path = args.config

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 2. Get all the query and samples to create the
    # build input.
    ponzi_text = _generate_ponzi_content()

    # Prepare DataSample (content-based)
    data_sample = DataSample(
        sample_id=str(uuid.uuid4()),
        raw_data_id=str(uuid.uuid4()),
        content=ponzi_text,
        category="Fraud",
        knowledge_field="Ponzi",
        tag="utest",
        method="synthetic",
    )

    # Prepare UserQueryInput
    uquery = UserQueryInput(
        query_text="I want to know the process of the Dutch Tulip Mania.",
        key_words=["Tulip mania", "speculation", "resale promise", "settlement delay"],
    )

    # BuildInput
    build_input = BuildInput(user_query=uquery, samples=[data_sample])

    # 3. Instantiate builder with real LLM config
    builder = AgentEventBuilder(
        method_name="APILMReconstruct",
        build_config=config,
    )

    # 4. Create the system and user prompts
    agent_names = list(config["agents"].keys())
    agent_system_msgs = {}
    agent_user_msgs = {}

    for name in agent_names:
        if "skeleton" in name.lower():
            agent_system_msgs[name] = EventLayoutReconstructorSys
            agent_user_msgs[name] = EventLayoutReconstructorUser
        if "participant" in name.lower():
            agent_system_msgs[name] = ParticipantReconstructorSys
            agent_user_msgs[name] = ParticipantReconstructorUser
        if "transaction" in name.lower():
            agent_system_msgs[name] = TransactionReconstructorSys
            agent_user_msgs[name] = TransactionReconstructorUser
        if "episode" in name.lower():
            agent_system_msgs[name] = EpisodeReconstructorSys
            agent_user_msgs[name] = EpisodeReconstructorUser
        if "stagedescription" in name.lower():
            agent_system_msgs[name] = StageDescriptionReconstructorSys
            agent_user_msgs[name] = StageDescriptionReconstructorUser
        if "eventdescription" in name.lower():
            agent_system_msgs[name] = EventDescriptionReconstructorSys
            agent_user_msgs[name] = EventDescriptionReconstructorUser

    # Build the state
    state = {
        "build_input": build_input,
        "agent_results": [],
        "agent_executed": [],
        "cost": [],
        "agent_system_msgs": agent_system_msgs,
        "agent_user_msgs": agent_user_msgs,
    }

    # Run build
    print("Starting AgentEventBuilder...")
    graph = builder.graph()

    # Retrieve graph config from the loaded configuration
    graph_config = config["graph_config"]

    final_state = graph.invoke(state, graph_config)
    print("Build completed.")

    # Integrate final result
    final_cascade = builder.integrate_results(final_state)

    build_input = final_state.pop("build_input")

    # Save the final state to the json
    builder.save_traces(
        build_input.to_dict(),
        save_name="BuildInput",
        file_format="json",
    )
    builder.save_traces(
        final_state,
        save_name="FinalState",
        file_format="json",
    )
    builder.save_traces(
        final_cascade,
        save_name="FinalEventCascade",
        file_format="json",
    )
    print("Traces saved.")

    # Test integrate_from_files
    print("\nTesting integrate_from_files...")
    restored_cascade = builder.integrate_from_files()
    builder.save_traces(
        restored_cascade,
        save_name="IntegratedEventCascade",
        file_format="json",
    )
    print("integrate_from_files test completed.")


if __name__ == "__main__":
    main()
