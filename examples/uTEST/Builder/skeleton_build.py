"""
Minimal uTEST for StepWiseEventBuilder (LangGraph single-node pipeline)

- Constructs a BuildInput with one DataSample and a UserQueryInput
- Generates ~1000 chars Ponzi scheme test content in English, fragmented (no explicit stages)
- Uses the real LLM API similar to `examples/uTEST/test_flow.py`
- Invokes the builder and prints the saved directory and parsed event JSON

Notes:
- This test calls the actual LLM; ensure environment variables/API keys are set
- The builder's `load_samples` is monkeypatched to read `DataSample.content`

Run:

    python examples/uTEST/Builder/step_build.py -c configs/uTEST/builder/step_build.yml

"""

import uuid
import argparse

import yaml

from dotenv import load_dotenv

from finmy.generic import UserQueryInput, DataSample
from finmy.builder.base import BuildInput
from finmy.builder.step_build.main_build import (
    EventSkeletonBuilder,
    EpisodeReconstructionBuilder,
)
from finmy.builder.step_build.prompts import *


def _generate_ponzi_content() -> str:
    """Generate fragmented English content about Dutch tulip mania covering start → peak → crash → aftermath.

    The text avoids explicit stage labels and uses mixed sources: pamphlets, gossip,
    ledgers, auctions, notices, diaries, court clerks, and broadside commentary.
    Length is unrestricted to better simulate real-world noisy information.
    """
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
        "Broadsheet editors compile letters from multiple towns on rising prices and missed deliveries.",
        "Printer issues a cautionary pamphlet citing examples of broken promises and disputed quality.",
        "Municipal clerks draft advice to moderate speculation; language shifts from polite guidance to stern warning.",
        "A guild rumor: brokers coordinate informal auctions across inns, expanding into neighboring cities.",
        "Ship manifests note confusion over consignments labeled only by fancy names and stripes.",
        "Court scribes log appeals over forfeited bonds when settlements fail after a cold snap.",
        "A moneylender ledger shows chains of IOUs linked to bulb certificates across several families.",
        "Foreign pamphlets praise quick fortunes; local satire counters with tales of sudden ruin.",
        "A church bulletin describes alms requests spiking after speculative losses.",
        "A magistrate remark recorded by a clerk: commerce is burdened by notes unbacked by harvest.",
        "Night gatherings grow noisier; traders citing ‘new subscribers’ as reason to keep accounts open.",
        "Anonymized table posted on a tavern wall lists prices that jump daily without physical exchange.",
        "A narrow column in a broadsheet questions whether contracts reference actual bulbs or mere promises.",
        "Regional couriers deliver notices urging restraint; some readers dismiss them as envious prose.",
        "A gardener’s account book shows few real deliveries compared to traded notes in town.",
        "Several letters mention settlements delayed ‘for want of better banking arrangements’.",
        "Clerks in the civic office report queues of complainants seeking arbitration over unpaid drafts.",
        "Travelers from Leiden tell of coffeehouses packed with new faces discussing bulb names like currency.",
        "An extract from a private diary: neighbors avoid speaking of debts during market days.",
        "A woodcut pamphlet lampoons men measuring status by color charts rather than gardens.",
        "A short municipal circular hints at forthcoming rules if disputes continue to clog the court.",
        # Expansion and peak frenzy
        "Auction scribbles note bidding by strangers who never handle bulbs, only notes and drafts.",
        "Merchants reference ‘guaranteed resale’ arrangements, recorded loosely without seals.",
        "Criers repeat news of a nobleman rumored to pay a princely sum for a striped variety.",
        "Inn ledgers show tabs settled with certificate transfers rather than coin.",
        "Printer adds an appendix listing extraordinary sums paid in nearby towns.",
        "Street talk suggests every craftsman knows someone richer from bulb trading.",
        "House appraisals reportedly include a line item for ‘speculative paper tied to bulbs’.",
        "Scribes describe price boards revised twice daily to keep pace with gossip.",
        # Trigger events and early cracks
        "Reports of frost lead gardeners to caution: physical bulbs may suffer; trading persists regardless.",
        "Some letters mention cancellations when quality cannot be proved upon delivery.",
        "Coffeehouse argument breaks out over whether promises can substitute for garden output.",
        "A local judge informally advises that certain private wagers might be unenforceable.",
        "Anxious notes from families describe sleepless nights over outstanding drafts.",
        # Crash and disputes
        "Price summaries show sudden drops; sellers refuse to honor previous talk without notarized proof.",
        "Clerks record stacks of petitions claiming contracts were mere wagers and thus invalid.",
        "Brokers vanish from usual tables; new buyers fail to appear, leaving papers without takers.",
        "A broadsheet front page headlines ‘Bulb prices falter; debts contested in civic halls’.",
        "Witness statements mention doors closed to collectors seeking repayment.",
        # Aftermath and impacts
        "A town meeting transcript indicates intent to standardize trading forms and discourage informal markets.",
        "Families list sold belongings to cover obligations; some move to relatives to share rent.",
        "Guild commentary urges a return to craft and coin, warning about paper promises.",
        "Regional merchants revise terms to require physical inspection before payment.",
        "A minister’s sermon speaks against vanity and quick fortune, asking for community support.",
        "Clerks circulate a memo that courts may treat many bulb disputes as non-commercial wagers.",
        "Prices on surviving exchanges stabilize at modest levels tied to real cultivation.",
        "Travel notes say conversation has shifted from color charts to winter survival and work.",
        "An epilogue in a pamphlet claims lessons were learned: avoid anonymous notes, respect harvest risk, seek audits.",
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
    builder = EventSkeletonBuilder(
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
    ske_graph = builder.graph()
    final_state = ske_graph.invoke(state)
    build_input = final_state.pop("build_input")

    # Save the final state to the json
    builder.save_traces(
        build_input,
        save_name="BuildInput",
        file_format="json",
    )
    builder.save_traces(
        final_state,
        save_name="FinalState",
        file_format="json",
    )


if __name__ == "__main__":
    main()
