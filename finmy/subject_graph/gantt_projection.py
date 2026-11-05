"""Enrich a disposable Gantt view without changing the canonical event projection."""
import copy
import re

from finmy.subject_graph.time_display import project_time


def instrument_entities(instruments, entities):
    """Resolve unique references to registered names, not transaction parties."""
    aliases = {}
    for identifier, entity in entities.items():
        names = [entity["name"]["value"], *entity["aliases"]]
        aliases[identifier] = [re.sub(
            r"(?:[\s,.]+(?:co|corp|corporation|company|inc|ltd|limited|plc)\.?)+$",
            "", name.casefold()).strip() for name in names]
    found = set()
    for instrument in instruments:
        text = instrument["value"].casefold()
        matches = {identifier for identifier, names in aliases.items()
                   if any(name and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text)
                          for name in names)}
        if len(matches) == 1:
            found.update(matches)
    return found


def prepare_gantt_cascade(graph, cascade):
    """Keep native evidence and contextual nodes in the Person rendering copy."""
    graph, cascade = copy.deepcopy(graph), copy.deepcopy(cascade)
    entities = {e["entity_id"]: e for e in graph["entities"]}
    names = {identifier: e["name"]["value"] for identifier, e in entities.items()}
    identifiers = [graph["subject_id"], *sorted(set(entities) - {graph["subject_id"]})]
    mapping = {identifier: f"P_{i + 1}" for i, identifier in enumerate(identifiers)}

    for event, stage in zip(graph["events"], cascade["stages"]):
        stage["_subject"] = {"event": event}
        context = stage["episodes"][0]
        context["_subject"] = {"kind": "context", "event": event}
        participants = {p["participant_id"]: p for p in context["participants"]}
        roles = {p["entity_id"] for p in event["participations"]}

        def participant(identifier, role="Related entity"):
            pid = mapping[identifier]
            if pid not in participants:
                entity = entities[identifier]
                participants[pid] = {
                    "participant_id": pid, "name": entity["name"],
                    "participant_type": {"value": entity["entity_type"]},
                    "base_role": {"value": role}, "attributes": entity["attributes"],
                    "actions": [],
                }
            node = participants[pid]
            node["_subject"] = {
                "entity": entities[identifier],
                "participations": [p for p in event["participations"] if p["entity_id"] == identifier],
                "overview": [graph["title"], *graph["descriptions"]]
                            if identifier == graph["subject_id"] else [],
                "action_names": [a["action_type"] for a in event["actions"] if a["actor_id"] == identifier],
                "global_relations": [r for r in graph["relations"] if not r["event_ids"]
                                     and identifier in (r["from_entity_id"], r["to_entity_id"])],
                "names": names,
            }
            return node

        for identifier in sorted(roles):
            participant(identifier)
        context["participant_relations"] = []
        for relation in graph["relations"]:
            if event["event_id"] not in relation["event_ids"]:
                continue
            source, target = relation["from_entity_id"], relation["to_entity_id"]
            participant(source)
            participant(target)
            context["participant_relations"].append({
                "from_participant_id": mapping[source], "to_participant_id": mapping[target],
                "relation_name": relation["relation_type"], "relation_type": relation["relation_type"],
                "descriptions": [], "start_time": project_time(relation["valid_from"], "start"),
                "end_time": project_time(relation["valid_to"], "end"),
                "_subject": {"relation": relation, "contextual": not {source, target} <= roles},
            })

        for action, episode in zip(event["actions"], stage["episodes"][1:]):
            episode["_subject"] = {"kind": "action", "action": action}
            actor = copy.deepcopy(participant(action["actor_id"]))
            actor["actions"] = [{"name": action["action_type"], "timestamp": action["timestamp"],
                                 "details": action["details"]}]
            actor["_subject"].update(actions=[action], action_names=[], overview=[])
            episode["participants"] = [actor]

        for i, transaction in enumerate(event["transactions"], 1):
            parties = {transaction[side + "_entity_id"]["value"] for side in ("from", "to")}
            references = instrument_entities(transaction["instruments"], entities)
            nodes = []
            for identifier in sorted((parties & entities.keys()) | references):
                node = copy.deepcopy(participant(
                    identifier, "Referenced by instrument" if identifier in references else "Transaction party"))
                node["actions"] = []
                node["_subject"].update(action_names=[], overview=[], transaction=transaction)
                nodes.append(node)
            stage["episodes"].append({
                "episode_id": f"{context['episode_id']}_T{i}", "name": transaction["name"],
                "index_in_stage": len(event["actions"]) + i,
                "start_time": project_time(transaction["timestamp"], "start"),
                "end_time": project_time(transaction["timestamp"], "end"),
                "descriptions": transaction["details"], "participants": nodes,
                "participant_relations": [], "transactions": [],
                "_subject": {"kind": "transaction", "transaction": transaction, "names": names,
                             "provenance_on_node": bool(nodes)},
            })
        context["participants"] = list(participants.values())
    return cascade
