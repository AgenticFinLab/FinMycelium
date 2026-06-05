"""Prompt templates for SparseRagBuilder."""

from __future__ import annotations

ADDITIVE_CONTEXT_POLICY = """
Content is the primary evidence. RetrievedContext is additive evidence only:
use it when it supports the same event, but never remove, replace, override,
weaken, or contradict facts from Content.
""".strip()

REQUIRED_PROMPT_VARIABLES = (
    "Query",
    "Keywords",
    "Content",
    "RetrievedContext",
    "RetrievedContextSummary",
    "RetrievedContextQueryBundle",
    "RetrievedContextBudgetSummary",
    "RetrievedContextMemory",
    "EpisodeExecutionMode",
    "TransactionDetailTier",
    "EpisodeDetailTier",
    "ConflictGuard",
    "EpisodeCompactnessHint",
    "TargetStage",
    "TargetEpisode",
)

COMMON_SYSTEM_PROMPT = f"""
You are a senior financial event reconstruction expert.

Evidence policy:
{ADDITIVE_CONTEXT_POLICY}

Output must stay grounded in the provided source text. Prefer compact,
schema-compatible JSON and avoid unsupported elaboration.
""".strip()

COMMON_USER_INPUT_BLOCK = """
=== Query BEGIN ===
{Query}
=== Query END ===

=== KEYWORDS BEGIN ===
{Keywords}
=== KEYWORDS END ===

=== CONTENT BEGIN ===
{Content}
=== CONTENT END ===

=== RETRIEVED CONTEXT BEGIN ===
{RetrievedContext}
=== RETRIEVED CONTEXT END ===

=== RETRIEVED CONTEXT SUMMARY BEGIN ===
{RetrievedContextSummary}
=== RETRIEVED CONTEXT SUMMARY END ===

=== RETRIEVED CONTEXT QUERY BUNDLE BEGIN ===
{RetrievedContextQueryBundle}
=== RETRIEVED CONTEXT QUERY BUNDLE END ===

=== RETRIEVED CONTEXT BUDGET SUMMARY BEGIN ===
{RetrievedContextBudgetSummary}
=== RETRIEVED CONTEXT BUDGET SUMMARY END ===

=== RETRIEVED CONTEXT MEMORY BEGIN ===
{RetrievedContextMemory}
=== RETRIEVED CONTEXT MEMORY END ===

=== TARGET STAGE BEGIN ===
{TargetStage}
=== TARGET STAGE END ===

=== TARGET EPISODE BEGIN ===
{TargetEpisode}
=== TARGET EPISODE END ===

=== EPISODE EXECUTION MODE ===
{EpisodeExecutionMode}

=== TRANSACTION DETAIL TIER ===
{TransactionDetailTier}

=== EPISODE DETAIL TIER ===
{EpisodeDetailTier}

=== CONFLICT GUARD ===
{ConflictGuard}

=== EPISODE COMPACTNESS HINT ===
{EpisodeCompactnessHint}
""".strip()


EventLayoutReconstructorSys = COMMON_SYSTEM_PROMPT
EventLayoutReconstructorUser = (
    "Reconstruct the event skeleton only, then output raw JSON.\n\n"
    + COMMON_USER_INPUT_BLOCK
)

SkeletonCheckerSys = COMMON_SYSTEM_PROMPT
SkeletonCheckerUser = (
    "Audit and correct the proposed event skeleton using Content as primary evidence.\n\n"
    + COMMON_USER_INPUT_BLOCK
    + "\n\n=== PROPOSED SKELETON BEGIN ===\n{ProposedSkeleton}\n=== PROPOSED SKELETON END ==="
)

ParticipantReconstructorSys = COMMON_SYSTEM_PROMPT
ParticipantReconstructorUser = (
    "Reconstruct participants for the target episode only.\n\n"
    + COMMON_USER_INPUT_BLOCK
)

TransactionReconstructorSys = COMMON_SYSTEM_PROMPT
TransactionReconstructorUser = (
    "Reconstruct transactions for the target episode using the requested detail tier.\n\n"
    + COMMON_USER_INPUT_BLOCK
)

EpisodeReconstructorSys = COMMON_SYSTEM_PROMPT
EpisodeReconstructorUser = (
    "Reconstruct the target episode using the execution mode and compactness hint.\n\n"
    + COMMON_USER_INPUT_BLOCK
)

StageDescriptionReconstructorSys = COMMON_SYSTEM_PROMPT
StageDescriptionReconstructorUser = (
    "Write grounded descriptions for the target stage only.\n\n"
    + COMMON_USER_INPUT_BLOCK
)

EventDescriptionReconstructorSys = COMMON_SYSTEM_PROMPT
EventDescriptionReconstructorUser = (
    "Write grounded descriptions for the full event only.\n\n"
    + COMMON_USER_INPUT_BLOCK
)


def required_prompt_variables() -> set[str]:
    """Return the public prompt variables expected from SparseRagBuilder."""

    return set(REQUIRED_PROMPT_VARIABLES)


def get_agent_prompts() -> tuple[dict[str, str], dict[str, str]]:
    """Return system and user templates keyed by agent name."""

    agent_system_msgs = {
        "SkeletonReconstructor": EventLayoutReconstructorSys,
        "SkeletonChecker": SkeletonCheckerSys,
        "ParticipantReconstructor": ParticipantReconstructorSys,
        "TransactionReconstructor": TransactionReconstructorSys,
        "EpisodeReconstructor": EpisodeReconstructorSys,
        "StageDescriptionReconstructor": StageDescriptionReconstructorSys,
        "EventDescriptionReconstructor": EventDescriptionReconstructorSys,
    }
    agent_user_msgs = {
        "SkeletonReconstructor": EventLayoutReconstructorUser,
        "SkeletonChecker": SkeletonCheckerUser,
        "ParticipantReconstructor": ParticipantReconstructorUser,
        "TransactionReconstructor": TransactionReconstructorUser,
        "EpisodeReconstructor": EpisodeReconstructorUser,
        "StageDescriptionReconstructor": StageDescriptionReconstructorUser,
        "EventDescriptionReconstructor": EventDescriptionReconstructorUser,
    }
    return agent_system_msgs, agent_user_msgs
