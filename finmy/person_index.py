"""Non-destructive links between a stable subject ID and graph-local IDs.

Matching is deliberately conservative: an exact configured name/alias AND an
individual participant type are required. It does not prove real-world identity.
"""
import copy
import unicodedata
from collections import Counter

from finmy.reconstruction_scope import read_reconstruction


def _value(field):
    return field.get("value") if isinstance(field, dict) else field


def _normalized(value):
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _valid_participant_id(value):
    """Require a usable graph-local reference without rewriting its spelling."""
    return (
        isinstance(value, str) and bool(value) and value.isprintable()
        and not any(character.isspace() for character in value)
        and _normalized(value) not in {
            "unknown", "unspecified", "none", "null", "n/a", "na", "nan",
            "undefined", "未知", "不详",
        }
    )


def _records(container, key, path, warnings):
    """Yield valid objects with original positions; retain malformed input untouched."""
    values = container.get(key, [])
    if not isinstance(values, list):
        warnings.append({"graph_pointer": f"{path}/{key}", "code": "invalid_collection"})
        return
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            warnings.append({"graph_pointer": f"{path}/{key}/{index}", "code": "invalid_record"})
            continue
        yield index, value


def build_person_index(cascade, config):
    """Create an auditable sidecar without renaming or adding graph entities."""
    reconstruction = read_reconstruction(config)
    if reconstruction["mode"] != "person":
        raise ValueError("A person index requires person reconstruction mode")
    subject = reconstruction["subject"]
    names = {_normalized(subject["name"]): "name"}
    for alias in subject["aliases"]:
        names.setdefault(_normalized(alias), "alias")
    individual_types = {"individual", "person", "natural_person", "natural person",
                        "个人", "人物", "自然人"}
    episodes = []
    links = []
    warnings = []
    if not isinstance(cascade, dict):
        warnings.append({"graph_pointer": "", "code": "invalid_graph"})
        cascade = {}
    for si, stage in _records(cascade, "stages", "", warnings):
        for ei, episode in _records(stage, "episodes", f"/stages/{si}", warnings):
            path = f"/stages/{si}/episodes/{ei}"
            entry = {
                "stage_id": copy.deepcopy(stage.get("stage_id")),
                "episode_id": copy.deepcopy(episode.get("episode_id")),
                "graph_pointer": path,
                "name": copy.deepcopy(episode.get("name")),
                "start_time": copy.deepcopy(episode.get("start_time")),
                "end_time": copy.deepcopy(episode.get("end_time")),
                "subject_presence": "not_identified",
            }
            candidates = []
            name_matches = []
            ambiguous_subject_id = False
            participants = list(_records(episode, "participants", path, warnings))
            id_counts = Counter(p["participant_id"] for _, p in participants
                                if _valid_participant_id(p.get("participant_id")))
            relations = list(_records(episode, "participant_relations", path, warnings))
            for pi, participant in participants:
                identifier = participant.get("participant_id")
                valid_id = _valid_participant_id(identifier)
                duplicate_id = valid_id and id_counts[identifier] > 1
                if not valid_id or duplicate_id:
                    warnings.append({"graph_pointer": f"{path}/participants/{pi}/participant_id",
                                     "code": "duplicate_participant_id" if duplicate_id
                                     else "invalid_participant_id"})
                match = names.get(_normalized(_value(participant.get("name"))))
                if not match:
                    continue
                name_matches.append(participant)
                kind = _normalized(_value(participant.get("participant_type")))
                if duplicate_id:
                    ambiguous_subject_id = True
                    continue
                if kind not in individual_types or not valid_id:
                    warnings.append({"graph_pointer": f"{path}/participants/{pi}",
                                     "code": "unresolved_subject_type_or_id"})
                    continue
                candidates.append({
                    "subject_id": subject["subject_id"],
                    "stage_id": copy.deepcopy(stage.get("stage_id")),
                    "episode_id": copy.deepcopy(episode.get("episode_id")),
                    "participant_id": identifier,
                    "graph_pointer": f"{path}/participants/{pi}",
                    "match_basis": f"configured_{match}_and_individual_type",
                    "name_evidence": copy.deepcopy(participant.get("name")),
                })
            if len(name_matches) > 1 or ambiguous_subject_id:
                entry["subject_presence"] = "ambiguous"
                warnings.append({"graph_pointer": path,
                                 "code": "ambiguous_subject_id" if ambiguous_subject_id
                                 else "multiple_subject_candidates"})
            elif len(candidates) == 1:
                entry["subject_presence"] = "matched"
                link = candidates[0]
                # Relation contents and their original time fields stay in the graph.
                link["relation_pointers"] = [
                    f"{path}/participant_relations/{ri}"
                    for ri, relation in relations
                    if link["participant_id"] in (
                        _value(relation.get("from_participant_id")),
                        _value(relation.get("to_participant_id")),
                    )
                ]
                links.append(link)
            elif name_matches:
                entry["subject_presence"] = "unresolved"
            episodes.append(entry)
    if not links:
        warnings.append({"code": "no_unambiguous_subject_participant",
                         "message": "Do not infer personal participation from company-only episodes."})
    return {
        "schema_version": "1.0", "mode": "person",
        "subject": copy.deepcopy(subject),
        "graph_asset": "FinalEventCascade.json", "event_id": copy.deepcopy(cascade.get("event_id")),
        "identity_policy": "Exact configured name/alias plus individual type; graph-local references only. "
                           "Participant IDs must be valid and unique within their Episode. "
                           "Name matching is not independent verification of identity.",
        "coverage_policy": "Requested dates are scope, not proof of complete biographical coverage. "
                           "Episode dates below are copied from the graph; absence is not evidence of inactivity.",
        "episodes": episodes, "participant_links": links, "warnings": warnings,
    }
