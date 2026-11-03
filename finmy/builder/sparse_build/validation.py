"""Structural checks derived from the shared event dataclasses."""

from dataclasses import MISSING, fields, is_dataclass
from types import UnionType
from typing import Union, get_args, get_origin, get_type_hints

from finmy.builder.agent_build.structure import (
    Episode, EventCascade, Participant, Transaction, VerifiableField,
)


def validate_shape(value, annotation, path="result", *, skeleton=False):
    """Reject invalid shapes without filling missing facts or mutating results."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, UnionType):
        for choice in args:
            try:
                validate_shape(value, choice, path, skeleton=skeleton)
                return
            except ValueError:
                pass
        raise ValueError(f"{path}: unexpected value type")
    if annotation is type(None):
        if value is not None:
            raise ValueError(f"{path}: expected null")
    elif is_dataclass(annotation):
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected object")
        definitions = {f.name: f for f in fields(annotation)}
        hints = get_type_hints(annotation)
        unknown = value.keys() - definitions.keys()
        if unknown:
            raise ValueError(f"{path}: unsupported fields {sorted(unknown)}")
        for name, field in definitions.items():
            if skeleton and name in {"descriptions", "participants", "participant_relations", "transactions"}:
                if name not in value:
                    continue
            if name not in value:
                if field.default is MISSING and field.default_factory is MISSING:
                    raise ValueError(f"{path}.{name}: missing field")
                continue
            validate_shape(value[name], hints[name], f"{path}.{name}", skeleton=skeleton)
        if annotation is VerifiableField:
            confidence = value.get("confidence")
            if confidence is not None and not 0 <= confidence <= 1:
                raise ValueError(f"{path}.confidence: expected value in [0, 1]")
    elif origin is list:
        if not isinstance(value, list):
            raise ValueError(f"{path}: expected array")
        for index, item in enumerate(value):
            validate_shape(item, args[0], f"{path}[{index}]", skeleton=skeleton)
    elif origin is dict:
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected object")
        for key, item in value.items():
            validate_shape(key, args[0], f"{path} key", skeleton=skeleton)
            validate_shape(item, args[1], f"{path}.{key}", skeleton=skeleton)
    elif annotation is float:
        if type(value) not in (float, int):
            raise ValueError(f"{path}: expected number")
    elif type(value) is not annotation:
        raise ValueError(f"{path}: expected {annotation.__name__}")


def scalar(value):
    return value.get("value") if isinstance(value, dict) else value


def validate_ids(items, field, path):
    seen = set()
    for item in items:
        identifier = item.get(field)
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError(f"{path}.{field}: expected nonempty ID")
        if identifier in seen:
            raise ValueError(f"{path}.{field}: duplicate ID {identifier}")
        seen.add(identifier)
    return seen


def validate_skeleton(payload):
    validate_shape(payload, EventCascade, skeleton=True)
    if not payload.get("event_id", "").strip():
        raise ValueError("event_id: expected nonempty ID")
    def meaningful(value):
        return isinstance(value, str) and value.strip().lower() not in {"", "unknown", "unspecified", "null", "none", "n/a"}

    if not meaningful(scalar(payload["title"])):
        raise ValueError("title: expected a meaningful title")
    stages = payload.get("stages", [])
    if not stages:
        raise ValueError("stages: expected at least one stage")
    validate_ids(stages, "stage_id", "stages")
    for si, stage in enumerate(stages):
        if not meaningful(scalar(stage["name"])):
            raise ValueError("stage.name: expected a meaningful name")
        if stage["index_in_event"] != si:
            raise ValueError("index_in_event: must match zero-based stage order")
        episodes = stage.get("episodes", [])
        if not episodes:
            raise ValueError(f"stages[{si}].episodes: expected at least one episode")
        validate_ids(episodes, "episode_id", f"stages[{si}].episodes")
        for ei, episode in enumerate(episodes):
            if not meaningful(scalar(episode["name"])):
                raise ValueError("episode.name: expected a meaningful name")
            if episode["index_in_stage"] != ei:
                raise ValueError("index_in_stage: must match zero-based episode order")


def validate_endpoints(items, participant_ids, path):
    for index, item in enumerate(items):
        for key in ("from_participant_id", "to_participant_id"):
            identifier = scalar(item.get(key))
            # Unknown endpoints are permitted for transactions by the shared schema.
            if path == "transactions" and identifier in (None, "", "unknown"):
                continue
            if identifier not in participant_ids:
                raise ValueError(f"{path}[{index}].{key}: dangling participant reference")


def validate_episode(payload):
    validate_shape(payload, Episode)
    for key in ("participants", "transactions", "participant_relations", "descriptions"):
        if not isinstance(payload.get(key), list):
            raise ValueError(f"episode.{key}: expected array")
    ids = validate_ids(payload["participants"], "participant_id", "participants")
    validate_endpoints(payload["participant_relations"], ids, "participant_relations")
    validate_endpoints(payload["transactions"], ids, "transactions")


def validate_role(agent_name, payload):
    if not isinstance(payload, dict):
        raise ValueError(f"{agent_name}: expected object")
    if agent_name in {"SkeletonReconstructor", "SkeletonChecker"}:
        validate_skeleton(payload)
    elif agent_name == "EpisodeReconstructor":
        # Only these exact placeholders may be resolved during assembly.
        normalized = dict(payload)
        for key, role in (("participants", "ParticipantReconstructor"), ("transactions", "TransactionReconstructor")):
            if normalized.get(key) == f"Results of {role}":
                normalized[key] = []
        validate_shape(normalized, Episode)
        for key in ("participants", "transactions", "participant_relations", "descriptions"):
            if not isinstance(normalized.get(key), list):
                raise ValueError(f"episode.{key}: expected array or declared placeholder")
    else:
        key, item_type = {
            "ParticipantReconstructor": ("participants", Participant),
            "TransactionReconstructor": ("transactions", Transaction),
            "StageDescriptionReconstructor": ("descriptions", VerifiableField),
            "EventDescriptionReconstructor": ("descriptions", VerifiableField),
        }[agent_name]
        if set(payload) != {key}:
            raise ValueError(f"{agent_name}: expected only {key}")
        validate_shape(payload[key], list[item_type], key)
        if key == "participants":
            validate_ids(payload[key], "participant_id", key)


def validate_cascade(payload):
    validate_skeleton(payload)
    validate_shape(payload, EventCascade)
    for stage in payload["stages"]:
        for episode in stage["episodes"]:
            validate_episode(episode)


def evidence_report(payload, samples):
    """Locate verbatim quotes in supplied sources; this is not entailment checking."""
    links, missing = [], []

    def visit(value, path):
        if isinstance(value, dict):
            if isinstance(value.get("value"), str):
                quotes = value.get("evidence_source_contents", [])
                if not quotes:
                    missing.append(path)
                for quote in quotes:
                    matches = [s.sample_id for s in samples if quote.strip() and quote in s.content]
                    links.append({"field": path, "quote": quote, "sample_ids": matches})
            for key, child in value.items():
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(payload, "event")
    unmatched = sum(not link["sample_ids"] for link in links)
    return {"method": "exact_substring", "semantic_support_checked": False,
            "quote_count": len(links), "unmatched_quote_count": unmatched,
            "fields_without_quotes": missing, "links": links}
