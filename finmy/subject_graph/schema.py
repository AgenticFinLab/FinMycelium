"""The public SubjectGraph JSON contract (JSON Schema draft 2020-12).

The graph owns one entity registry. Events reference those identities through
participations and actions; relationships retain their own validity intervals.
The schema intentionally does not impose a stage hierarchy or causal chain.
"""

SCHEMA_VERSION = "subject-graph-1.0"


def _object(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


def _array(items, **kwargs):
    return {"type": "array", "items": items, **kwargs}


def _ref(name):
    return {"$ref": "#/$defs/" + name}


ID = {"type": "string", "minLength": 1, "pattern": r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"}
TEXT = {"type": "string", "minLength": 1}
VF = _ref("VerifiableField")
DEFINITIONS = {
    "VerifiableField": _object({
        "value": {"type": "string"},
        "evidence_source_contents": _array(TEXT),
        "reasons": _array({"type": "string"}),
        "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
        "evidence_status": {"enum": ["needs_review"]},
        "time_window": _object({
            "start": TEXT, "end": TEXT, "original": TEXT,
            "approximate": {"type": "boolean"},
        }),
    }, ["value", "evidence_source_contents", "reasons"]),
    "Entity": _object({
        "entity_id": ID, "name": VF, "aliases": _array(TEXT), "entity_type": TEXT,
        "attributes": {"type": "object", "additionalProperties": VF},
    }),
    "Participation": _object({
        "participation_id": ID, "entity_id": ID, "role": VF,
        "start_time": VF, "end_time": VF,
    }),
    "Action": _object({
        "action_id": ID, "actor_id": ID, "action_type": VF,
        "timestamp": VF, "details": _array(VF),
    }),
    "Transaction": _object({
        "transaction_id": ID, "name": VF, "from_entity_id": VF,
        "to_entity_id": VF, "timestamp": VF,
        "instruments": _array(VF), "details": _array(VF),
    }),
    "Event": _object({
        "event_id": ID, "title": VF, "start_time": VF, "end_time": VF,
        "subject_relevance": VF, "descriptions": _array(VF),
        "participations": _array(_ref("Participation"), minItems=1),
        "actions": _array(_ref("Action")),
        "transactions": _array(_ref("Transaction")),
    }),
    "Relation": _object({
        "relation_id": ID, "from_entity_id": ID, "to_entity_id": ID,
        "relation_type": VF, "valid_from": VF, "valid_to": VF,
        "event_ids": _array(ID, uniqueItems=True),
    }),
}

JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://finmycelium.local/schema/subject-graph-1.0.json",
    "title": "SubjectGraph",
    **_object({
        "schema_version": {"const": SCHEMA_VERSION},
        "graph_id": ID, "subject_id": ID,
        "subject_type": {"enum": ["individual", "organization"]},
        "coverage_start": {"type": ["string", "null"]},
        "coverage_end": {"type": ["string", "null"]},
        "title": VF, "descriptions": _array(VF),
        "entities": _array(_ref("Entity"), minItems=1),
        "events": _array(_ref("Event")),
        "relations": _array(_ref("Relation")),
    }),
    "$defs": DEFINITIONS,
}
