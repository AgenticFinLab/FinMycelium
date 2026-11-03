"""Person-scoped prompts using the existing EPG field contract.

Mode selection lives in the builder. These prompts do not alter event-mode templates.
Only declared dataclass fields enter person schemas; event-specific examples and
comments from the historical financial schema are intentionally omitted.
"""
import ast

from finmy.builder.agent_build.prompts import _TEMPORAL_NORMALIZATION_POLICY


_FIELDS = {
    "SkeletonReconstructor": {
        "VerifiableField": None,
        "EventCascade": ["event_id", "title", "event_type", "start_time", "end_time", "stages"],
        "EventStage": ["stage_id", "name", "index_in_event", "start_time", "end_time", "episodes"],
        "Episode": ["episode_id", "name", "index_in_stage", "start_time", "end_time"],
    },
    "ParticipantReconstructor": {"VerifiableField": None, "Participant": None, "Action": None},
    "TransactionReconstructor": {"VerifiableField": None, "Transaction": None},
    "EpisodeReconstructor": {"VerifiableField": None, "ParticipantRelation": None,
                               "Action": None, "Transaction": None, "Episode": None},
    "StageDescriptionReconstructor": {"VerifiableField": None, "EventStage": None},
    "EventDescriptionReconstructor": {"VerifiableField": None, "EventCascade": None},
}
_FIELDS["SkeletonChecker"] = _FIELDS["SkeletonReconstructor"]


def schema_for_agent(source, agent_name):
    """Return exact field definitions, without legacy domain descriptions/examples."""
    included = _FIELDS[agent_name]
    classes = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.ClassDef) or node.name not in included:
            continue
        allowed = included[node.name]
        node.body = [field for field in node.body if isinstance(field, ast.AnnAssign)
                     and (allowed is None or field.target.id in allowed)]
        classes.append(ast.unparse(node))
    return "\n\n".join(classes)


_COMMON = _TEMPORAL_NORMALIZATION_POLICY + """
Reconstruct a person-centered EPG from supplied evidence. SubjectScope declares the
person's stable identity, requested period, and topical scope. Query and Keywords
may narrow that scope; they cannot silently expand it to the person's whole life.
SubjectScope and Query define the task, not factual evidence. Use only Content as
evidence. Previous agent output is a reconstruction aid, not independent evidence.

The existing EventCascade is a compatibility container for the person's selected
history. EventStage groups supported periods or coherent activities; Episode is a
concrete experience, appointment, decision, statement, relationship change, or other
material activity within the requested scope. Capital-market impact, a financial
shock, a transaction, and a causal chain are not prerequisites. Independent activities
may coexist or overlap. Do not invent continuity, intent, causality, dates, or missing
life phases. A narrowly requested investment period must remain that limited scope.

Every factual VerifiableField must include verbatim evidence_source_contents and
concise reasons with supported uncertainty. Use unknown for unsupported values.
Distinguish the individual, companies, employers, affiliates, and counterparties.
An organization's acts or assets are not the person's own acts or assets. Do not
include the subject in every Episode unless Content supports their material role.
Outside-period context may explain an in-scope activity but must not become a new
out-of-scope Episode. Configuration dates are requested bounds, not evidence that
an activity occurred throughout them. For an activity crossing a requested bound,
represent only its supported in-scope part and explain this restriction in reasons;
do not misstate the actual appointment or relationship start/end dates.

Output raw JSON only using the specified schema fields and types, without code fences
or extra explanatory keys. Empty lists are valid where no supported item exists.
Schema:
{STRUCTURE_SPEC}
"""

_INPUT = """
=== SUBJECT SCOPE BEGIN ===
{SubjectScope}
=== SUBJECT SCOPE END ===
=== QUERY BEGIN ===
{Query}
=== QUERY END ===
=== KEYWORDS BEGIN ===
{Keywords}
=== KEYWORDS END ===
=== CONTENT BEGIN ===
{Content}
=== CONTENT END ===
"""

_SKELETON = """
Build one EventCascade skeleton for this person's selected history. Return only the
fields in the provided skeleton schema. Review every supplied source for distinct,
material in-scope activities; deduplicate repeated reports of the same occurrence.
Represent evidenced education, career, appointments, decisions, statements,
relationships, and investments only when they fall in the declared topical scope.
Do not introduce standard birth/education/retirement phases without source support.
Each supported material activity must be identifiable in an Episode's name, timing,
and evidence; a broad stage title or date span alone is not coverage. Group closely
related occurrences coherently, preserving distinct activities without forcing any
stage/episode count. Activities without transactions or precise dates still qualify.
Stages may represent periods or coherent themes, with evidence-supported overlap and
gaps. Order stages and episodes by supported temporal/logical order, indices from 0.
Stage IDs S1, S2, ... are unique; Episode IDs E1, E2, ... are unique across all stages.
Event bounds encompass stages and stage bounds encompass episodes at supported
precision; do not stretch an occurrence to fill an empty period. Use unknown for
unsupported temporal boundaries. Set event_type from Content or unknown; this field
must not force classification as a financial incident. The title describes the
person and selected scope, not a fictional single event. Return stages=[] if there
is no supported in-scope activity; do not manufacture a stage or episode.
"""

_CHECKER = """
Audit ProposedSkeleton against EVERY supplied source and SubjectScope, returning one
complete corrected EventCascade skeleton. Preserve correct objects, IDs, and coherent
groupings. Add genuinely omitted material in-scope activities; remove unsupported or
out-of-scope entries. Check subject identity, topic boundaries, actual actors, source
coverage, timing precision, and unique IDs. A broad stage title is not evidence that
an activity is covered. Deduplicate repeated accounts without collapsing distinct
statements, decisions, appointments, or trades into a generic episode.
Accept supported gaps, parallel appointments, overlapping activities, and episodes
with no trades. Do not require a single causal storyline or predefined life phases.
Keep parent bounds consistent with evidenced children without expanding the requested
scope. Check start <= end at supported precision, using unknown where unresolved.
Update indices from 0 after corrections; never restart Episode IDs within a stage.
Remove empty stages. If no supported in-scope activity remains, return stages=[]
instead of inventing activities. Output only fields from the skeleton schema.
"""

_PARTICIPANT = """
Return exactly one object with key participants, a list of Participant records for
TargetEpisode. Identify the evidenced actors and material rights/obligations holders,
including a represented organization when its material role is explicit. Mere mention
or affiliation elsewhere is insufficient. The subject can be absent from an Episode;
do not invent their participation in a company's activity. Include other materially
relevant people and organizations with separate IDs. Resolve aliases from Content;
SubjectScope aliases assist identity matching but do not prove involvement.
Use ReconstructedParticipants to reuse IDs for the SAME entity across episodes, never
to import prior actions or involvement. New participant IDs must be unused P_ integers.
The stable subject_id is a cross-graph identity key, NOT a replacement for P_ IDs; an
external person index maps supported matches. Do not fabricate that mapping in JSON.
Populate actions only for acts the entity performed in this episode, at supported
occurrence times. Keep speech attributed to its speaker and company purchases to the
company. Include participants with actions=[] where their material role is evidenced.
Use participant_type with a VerifiableField value such as individual or organization.
Preserve factual source-backed roles and attributes; missing information is unknown.
"""

_TRANSACTION = """
Return exactly one object with key transactions, a list of Transaction records for
TargetEpisode. Return transactions=[] when no supported transfer occurred here.
Appointments, education, speeches, approvals, and disclosures do not themselves create
transactions. Require evidence of both the episode's activity and timing; shared
people/assets or a possibly overlapping date do not establish membership. Omit
background or later transactions and any whose episode assignment is unsupported.
Use occurrence time, not publication, filing, or disclosure time unless Content equates
them. Explain occurrence-time evidence and episode membership in timestamp.reasons.
Choose each known party ID only from TargetEpisode.participants, matching the actual
entity in Content. A company purchase is not the chair's personal purchase. Do not
substitute an issuer or regulator as a counterparty. If an otherwise supported in-scope
transaction has an unknown/missing party, use the existing VerifiableField value
unknown, explaining the missing identity (and source-backed name, if known) in reasons.
Do not invent participants, transfer parties, placeholder trades, or reporting keys.
"""

_EPISODE = """
Return one complete Episode for TargetEpisode. Preserve episode_id, name, index_in_stage
and valid skeleton dates. The pre-reconstructed participants and transactions are fixed.
Output the exact placeholders participants="Results of ParticipantReconstructor" and
transactions="Results of TransactionReconstructor"; integration inserts the records.
Reconstruct descriptions and participant_relations from Content. For each relationship,
verify the actual parties, predicate, direction, and temporal applicability. Endpoint
IDs must both exist in TargetEpisode.participants. Omit a relation if either endpoint
is missing/ambiguous; never substitute an affiliate, invent an ID, or use unknown as an
endpoint. Return participant_relations=[] if no supported relation can be represented.
Leadership, employment, ownership, investment, representation, and collaboration are
different relations. A person speaking about an asset does not establish ownership;
a company holding that asset does not establish the person's personal investment.
Preserve supported relationship start_time and end_time at source precision; a single
observation does not prove its entire duration. Do not copy a current affiliation into
all historical episodes. Unknown relationship boundaries stay unknown. If a named
party is missing, an existing description's reasons may note it without inventing edges.
Keep descriptions bounded by the episode; do not import other life phases, unsupported
motivations, financial impacts, or causal explanations. Retain evidence and uncertainty.
"""

_STAGE = """
Return exactly one object with key descriptions, a list of VerifiableField records
summarizing TargetStage. Its completed episodes organize the facts, but Content must
support every statement. Explain the evidenced activities in this period/theme and
any documented changes in role or relationships. Preserve overlapping or independent
experiences without forcing a causal sequence. Do not imply continuous activity across
unsupported gaps or invent financial impact or personal motivation.
"""

_HISTORY = """
Return exactly one object with key descriptions, a list of VerifiableField records
summarizing the person's SELECTED history from EventCascade and Content. Stay within
SubjectScope and the actually supported coverage. A narrow topic/window is not a full
biography. State only evidenced experiences and changes, preserving actual actors and
uncertainty; do not turn company acts into personal acts or claim causal continuity.
Do not claim complete life coverage from limited evidence. No invented biography or
unsubstantiated praise, intentions, financial outcomes, or missing phases.
"""


def get_person_prompts():
    """Build fresh prompt dictionaries with the existing agent names and IO contracts."""
    tasks = {
        "SkeletonReconstructor": _SKELETON,
        "SkeletonChecker": _CHECKER,
        "ParticipantReconstructor": _PARTICIPANT,
        "TransactionReconstructor": _TRANSACTION,
        "EpisodeReconstructor": _EPISODE,
        "StageDescriptionReconstructor": _STAGE,
        "EventDescriptionReconstructor": _HISTORY,
    }
    context = {
        "SkeletonReconstructor": "",
        "SkeletonChecker": "\nProposedSkeleton:\n{ProposedSkeleton}\n",
        "ParticipantReconstructor": "\nTargetEpisode:\n{TargetEpisode}\nReconstructedParticipants:\n{ReconstructedParticipants}\n",
        "TransactionReconstructor": "\nTargetEpisode:\n{TargetEpisode}\n",
        "EpisodeReconstructor": "\nStageSkeleton:\n{StageSkeleton}\nTargetEpisode:\n{TargetEpisode}\n",
        "StageDescriptionReconstructor": "\nTargetStage:\n{TargetStage}\n",
        "EventDescriptionReconstructor": "\nEventCascade:\n{EventCascade}\n",
    }
    return ({name: _COMMON + task for name, task in tasks.items()},
            {name: "Perform the task in the system instructions.\n" + context[name] + _INPUT
             for name in tasks})
