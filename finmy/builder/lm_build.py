"""
Implementation of reconstructing a Financial Event Pipeline Using Large Models (LMs).

This method is to reconstruction the financial event purely by prompting a single large models in one inference:

    prompt  ->  LM -> EventCascade
    samples ->
"""

import time
from pathlib import Path
from functools import partial

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from lmbase.inference.base import InferInput, InferOutput

from finmy.builder.base import BaseBuilder, BuildInput, AgentState
from finmy.builder.utils import (
    load_python_text,
    extract_dataclass_blocks,
    extract_json_response,
)


SYSTEM_PROMPT = """
You are a senior financial event analysis expert and structured extractor, excel at reconstructing specific financial events from large amounts of information. Your task is to, within the scope defined by `Query` and `Keywords`, strictly based on facts in `Content`, extract, summarize, refine, and reconstruct a specific financial event, and output strict JSON that truthfully represents the event. Do not invent or expand beyond the source, and do not alter any information that contradicts `Content`.

Output a single raw JSON object for `EventCascade` containing the reconstructed event fields defined in the Schema.

Compliance and consistency:
- Use ONLY fields and types from the schema block in the system prompt; exact names and types.
- ISO 8601 timestamps; ISO currency codes.
- Participant IDs MUST be "P_" + integer (e.g., P_1, P_2).
- Stage IDs MUST be "S" + integer (e.g., S1, S2). Start from 1.
- Episode IDs MUST be "E" + integer (e.g., E1, E2). Start from 1.
- Attach at least one source_content to critical records.
- Ensure logical consistency across stages and episodes.
- `transactions` within stages/episodes MUST reference valid `participant_id` values.
- Each JSON MUST strictly conform to the dataclass schema from the reference block.
- If information is not present in `Content`, set fields to null or omit; do not fabricate.
- Use `VerifiableField` as defined in the Schema for applicable fields.

Schema:
=== BEGIN Schema ===
{STRUCTURE_SPEC}
=== END Schema ===
"""

USER_PROMPT = """
Based on Query, Keywords, and Content, reconstruct the specific financial event strictly from the input Content below. Base all details on Content and follow the requirement in the Description and Keywords; do not invent, alter, or extend beyond what it explicitly supports. Produce a clear, layered, professional JSON output.

Instructions:
- Output a single raw JSON object for EventCascade that follows the Schema definition exactly.
- Do not include explanations or code fences.

=== Query BEGIN ===
{Query}
=== Query END ===

=== KEYWORDS BEGIN ===
{Keywords}
=== KEYWORDS END ===

=== CONTENT BEGIN ===
{Content}
=== CONTENT END ===
"""


# Load structure spec from agent_build/structure.py
_STRUCTURE_SPEC_FULL = load_python_text(
    path=Path(__file__).resolve().parent / "agent_build" / "structure.py"
)
_STRUCTURE_SPEC = (
    extract_dataclass_blocks(_STRUCTURE_SPEC_FULL, mode="all")
    if _STRUCTURE_SPEC_FULL
    else ""
)


class LMBuilder(BaseBuilder):
    """
    Build the financial event cascade from the input content using the LM model (Single Inference).
    """

    def execute_agent(self, state: AgentState, agent_name: str) -> AgentState:
        """
        Execute the single LM inference to generate the EventCascade.
        """
        t0 = time.time()

        build_ipt: BuildInput = state["build_input"]

        # Prepare prompt kwargs
        # Common prompt arguments
        prompt_kwargs = {
            "Query": build_ipt.user_query.query_text,
            "Keywords": build_ipt.user_query.key_words,
            "Content": "\n".join([sample.content for sample in build_ipt.samples]),
        }

        # 2. Prepare Messages
        # Retrieve templates
        # For LMBuilder, we use the locally defined global prompts as defaults
        # But we still check state if they are provided (though typically we use the globals)
        sys_msg_template = state["agent_system_msgs"][agent_name]
        user_msg_template = state["agent_user_msgs"][agent_name]

        # Escape braces for format if needed, similar to main_build logic
        # We replace { with {{ and } with }} to prevent format() from breaking on schema JSON
        sys_msg = sys_msg_template.format(STRUCTURE_SPEC=_STRUCTURE_SPEC)
        sys_msg = sys_msg.replace("{", "{{").replace("}", "}}")
        user_msg = user_msg_template

        # 3. Call LM
        # Use self.agents_lm which is initialized in BaseBuilder
        out: InferOutput = self.agents_lm.run(
            infer_input=InferInput(system_msg=sys_msg, user_msg=user_msg),
            **prompt_kwargs,
        )

        result = out.response

        # 4. Persist traces
        savename = self.get_save_name(agent_name, len(state["agent_executed"]) + 1)
        self.save_traces({agent_name: out.to_dict()}, savename, "json")
        parsed_result = extract_json_response(result)
        self.save_traces(parsed_result, f"{savename}-Result", "json")

        # 5. Update state
        state["agent_results"].append({agent_name: parsed_result})
        state["cost"].append({agent_name: {"latency": time.time() - t0}})
        state["agent_executed"].append(agent_name)

        return state

    def graph(self) -> CompiledStateGraph:
        """
        Define the simple graph for single-shot LM generation.
        """
        workflow = StateGraph(AgentState)

        # Add single node using partial to bind agent_name
        workflow.add_node(
            "EventReconstructor",
            partial(self.execute_agent, agent_name="EventReconstructor"),
        )

        # Define edges
        workflow.add_edge(START, "EventReconstructor")
        workflow.add_edge("EventReconstructor", END)

        return workflow.compile()
