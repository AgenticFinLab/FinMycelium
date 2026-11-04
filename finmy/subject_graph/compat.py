"""A derived EventCascade view for existing consumers; SubjectGraph is canonical.

Each independent event receives its own stage and episode. Global relationships
without event references are not invented as episode relationships. Entity IDs
are mapped consistently to P_ IDs inside this view only.
"""
import copy

from finmy.subject_graph.evidence import review_fields
from finmy.subject_graph.validation import date_interval, validate_subject_graph


def _metadata(value, reason):
    return {"value": value, "evidence_source_contents": [], "reasons": [reason]}


def _combine(fields):
    if len(fields) == 1:
        return copy.deepcopy(fields[0])
    return {"value": "; ".join(dict.fromkeys(f["value"] for f in fields)),
            "evidence_source_contents": list(dict.fromkeys(q for f in fields for q in f["evidence_source_contents"])),
            "reasons": list(dict.fromkeys(r for f in fields for r in f["reasons"]))}


def to_event_cascade(graph):
    """Create a fresh compatibility projection; reject broken references."""
    report = validate_subject_graph(graph)
    if not report["valid"]:
        first = report["errors"][0]
        raise ValueError(f"Invalid SubjectGraph at {first['path']}: {first['message']}")
    pending = review_fields(graph)
    graph = copy.deepcopy(graph)
    def legacy_fields(value):
        if isinstance(value, dict):
            if value.pop("evidence_status", None) == "needs_review":
                value["confidence"] = None
                value["reasons"] = ["待核实：引用尚未全部匹配到输入原文", *value["reasons"]]
            for child in value.values():
                legacy_fields(child)
        elif isinstance(value, list):
            for child in value:
                legacy_fields(child)
    legacy_fields(graph)
    if pending:
        graph["descriptions"].insert(0, _metadata(f"待核实：{len(pending)} 处内容的引用未完全匹配原文；请查看原生主体图标记。", "Evidence review notice"))
    entities = {entity["entity_id"]: entity for entity in graph["entities"]}
    ids = [graph["subject_id"]] + sorted(set(entities) - {graph["subject_id"]})
    mapping = {identifier: f"P_{i + 1}" for i, identifier in enumerate(ids)}
    stages = []
    for index, event in enumerate(graph["events"]):
        roles = {}
        for participation in event["participations"]:
            roles.setdefault(participation["entity_id"], []).append(participation["role"])
        participants = []
        for entity_id in roles:
            entity = entities[entity_id]
            participants.append({
                "participant_id": mapping[entity_id], "name": copy.deepcopy(entity["name"]),
                "participant_type": _metadata(entity["entity_type"], "Projected entity category"),
                "base_role": _combine(roles[entity_id]), "attributes": copy.deepcopy(entity["attributes"]),
                "actions": [{"name": copy.deepcopy(action["action_type"]),
                             "timestamp": copy.deepcopy(action["timestamp"]),
                             "details": copy.deepcopy(action["details"])}
                            for action in event["actions"] if action["actor_id"] == entity_id],
            })
        relations = []
        for relation in graph["relations"]:
            if (event["event_id"] not in relation["event_ids"]
                    or relation["from_entity_id"] not in roles
                    or relation["to_entity_id"] not in roles):
                # Contextual relations remain in the native graph; legacy episode
                # relations require real participants at both endpoints.
                continue
            relations.append({
                "from_participant_id": mapping[relation["from_entity_id"]],
                "to_participant_id": mapping[relation["to_entity_id"]],
                "relation_name": copy.deepcopy(relation["relation_type"]),
                "relation_type": copy.deepcopy(relation["relation_type"]),
                "descriptions": [],
                "start_time": copy.deepcopy(relation["valid_from"]),
                "end_time": copy.deepcopy(relation["valid_to"]),
            })
        transactions = []
        for transaction in event["transactions"]:
            item = {key: copy.deepcopy(transaction[key]) for key in ("name", "timestamp", "instruments", "details")}
            item["transaction_type"] = _metadata("unknown", "Transaction type not separately represented in SubjectGraph")
            for side in ("from", "to"):
                party = copy.deepcopy(transaction[side + "_entity_id"])
                party["value"] = mapping.get(party["value"], "unknown")
                item[side + "_participant_id"] = party
            transactions.append(item)
        episode = {
            "episode_id": f"E{index + 1}", "name": copy.deepcopy(event["title"]), "index_in_stage": 0,
            "start_time": copy.deepcopy(event["start_time"]), "end_time": copy.deepcopy(event["end_time"]),
            "descriptions": copy.deepcopy(event["descriptions"] + [event["subject_relevance"]]),
            "participants": participants,
            "participant_relations": relations, "transactions": transactions,
        }
        stages.append({
            "stage_id": f"S{index + 1}", "name": copy.deepcopy(event["title"]), "index_in_event": index,
            "start_time": copy.deepcopy(event["start_time"]), "end_time": copy.deepcopy(event["end_time"]),
            "descriptions": copy.deepcopy(event["descriptions"]), "episodes": [episode],
        })
    def extreme(key, minimum):
        candidates = [(date_interval(e[key]), e[key]) for e in graph["events"]]
        candidates = [(interval[0 if minimum else 1], field) for interval, field in candidates if interval]
        if not candidates:
            return _metadata("unknown", "No known event dates")
        return copy.deepcopy((min if minimum else max)(candidates, key=lambda x: x[0])[1])
    return {
        "event_id": graph["graph_id"], "title": copy.deepcopy(graph["title"]),
        "event_type": _metadata("subject history", "Compatibility projection from SubjectGraph"),
        "descriptions": copy.deepcopy(graph["descriptions"]),
        "start_time": extreme("start_time", True), "end_time": extreme("end_time", False),
        "stages": stages,
    }
