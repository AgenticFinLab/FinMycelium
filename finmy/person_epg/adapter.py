"""Lossless fact conversion between SubjectGraph 1.0 and Person EPG 3.0.

Legacy events become occurrences. Higher-level events and stages are left empty;
classification belongs to the organizer, not to this serialization adapter.
"""

from __future__ import annotations

import copy

from finmy.subject_graph.validation import validate_subject_graph

from .schema import MODEL, SCHEMA_VERSION
from .validation import validate_person_epg

TIME_FIELDS = {
    "start_time": "start_time_id",
    "end_time": "end_time_id",
    "timestamp": "timestamp_time_id",
    "valid_from": "valid_from_time_id",
    "valid_to": "valid_to_time_id",
}
GRAPH_FIELDS = [
    "graph_id",
    "schema_version",
    "subject_id",
    "subject_type",
    "coverage_start",
    "coverage_end",
    "title",
    "descriptions",
]
OCCURRENCE_FIELDS = [
    "event_id",
    "title",
    "subject_relevance",
    "start_time",
    "end_time",
    "descriptions",
]
PARTICIPATION_FIELDS = [
    "participation_id",
    "entity_id",
    "role",
    "start_time",
    "end_time",
]
ACTION_FIELDS = ["action_id", "actor_id", "action_type", "timestamp"]
TRANSACTION_FIELDS = [
    "transaction_id",
    "name",
    "from_entity_id",
    "to_entity_id",
    "timestamp",
    "details",
]
RELATION_FIELDS = [
    "relation_id",
    "from_entity_id",
    "to_entity_id",
    "relation_type",
    "valid_from",
    "valid_to",
]


def _pointer(key):
    return str(key).replace("~", "~0").replace("/", "~1")


def _require_valid(report, label):
    if not report["valid"]:
        first = report["errors"][0]
        raise ValueError(
            f"Invalid {label}: {first.get('path', '/')}: {first['message']}"
        )


class _Converter:
    def __init__(self):
        self.package = {"schema_version": SCHEMA_VERSION, "graph": {}}
        self.package.update(
            {t["name"]: [] for t in MODEL["tables"] if t["name"] != "subject_graph"}
        )
        self.metadata = {}
        self.participants = set()

    def pack(self, value, path, evidence_set_id, *, temporal=False):
        if isinstance(value, dict) and "value" in value:
            # Lift only quotations and temporal windows; preserve optional VF metadata.
            self.metadata[evidence_set_id][path] = {
                key: copy.deepcopy(item)
                for key, item in value.items()
                if key not in {"value", "evidence_source_contents"}
                and not (temporal and key == "time_window")
            }
            for index, quote in enumerate(value["evidence_source_contents"]):
                span_id = f"SPAN_{len(self.package['evidence_span']) + 1:05d}"
                self.package["evidence_span"].append(
                    {
                        "span_id": span_id,
                        "document_id": None,
                        "char_start": None,
                        "char_end": None,
                        "quote": quote,
                    }
                )
                self.package["evidence_link"].append(
                    {
                        "evidence_set_id": evidence_set_id,
                        "span_id": span_id,
                        "field_path": path,
                        "quote_order": index,
                    }
                )
            return copy.deepcopy(value["value"])
        if isinstance(value, dict):
            return {
                key: self.pack(item, path + "/" + _pointer(key), evidence_set_id)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self.pack(item, path + "/" + str(index), evidence_set_id)
                for index, item in enumerate(value)
            ]
        return copy.deepcopy(value)

    def record(self, table, native, fields, *, extra=None, renames=None):
        evidence_set_id = f"ES_{len(self.metadata) + 1:05d}"
        self.metadata[evidence_set_id] = {}
        row = {}
        for field in fields:
            value = native[field]
            scalar = self.pack(
                value,
                "/" + _pointer(field),
                evidence_set_id,
                temporal=field in TIME_FIELDS,
            )
            if field in TIME_FIELDS:
                time_id = f"TIME_{len(self.package['time_value']) + 1:05d}"
                time = {"time_id": time_id, "value": scalar}
                if "time_window" in value:
                    window = value["time_window"]
                    time.update(
                        window_start=window["start"],
                        window_end=window["end"],
                        original_text=window["original"],
                        is_approximate=window["approximate"],
                    )
                self.package["time_value"].append(time)
                row[TIME_FIELDS[field]] = time_id
            else:
                row[(renames or {}).get(field, field)] = scalar
        row.update(extra or {})
        row["evidence_set_id"] = evidence_set_id
        self.package["evidence_set"].append(
            {
                "evidence_set_id": evidence_set_id,
                "field_metadata": self.metadata[evidence_set_id],
            }
        )
        if table == "subject_graph":
            self.package["graph"] = row
        else:
            self.package[table].append(row)
        return row

    def participant(self, occurrence_id, entity_id):
        key = (occurrence_id, entity_id)
        if entity_id is not None and key not in self.participants:
            self.participants.add(key)
            self.package["occurrence_participant"].append(
                {
                    "occurrence_id": occurrence_id,
                    "entity_id": entity_id,
                }
            )

    def activity(self, fact_type, fact_id):
        activity_id = ("A:" if fact_type == "action" else "T:") + fact_id
        self.package["activity"].append(
            {
                "activity_id": activity_id,
                "action_id": None,
                "transaction_id": None,
                "context_occurrence_id": None,
                fact_type + "_id": fact_id,
            }
        )
        return activity_id

    def convert(self, graph):
        self.record(
            "subject_graph",
            graph,
            GRAPH_FIELDS,
            renames={"subject_id": "subject_entity_id"},
        )
        for index, entity in enumerate(graph["entities"]):
            self.record(
                "entity",
                entity,
                ["entity_id", "name", "entity_type", "attributes"],
                extra={"sort_order": index},
            )
            self.package["entity_alias"].extend(
                {
                    "entity_id": entity["entity_id"],
                    "alias": alias,
                    "sort_order": order,
                }
                for order, alias in enumerate(entity["aliases"])
            )
        for index, occurrence in enumerate(graph["events"]):
            oid = occurrence["event_id"]
            self.record(
                "occurrence",
                occurrence,
                OCCURRENCE_FIELDS,
                renames={"event_id": "occurrence_id"},
                extra={"sort_order": index},
            )
            for order, part in enumerate(occurrence["participations"]):
                self.record(
                    "participation",
                    part,
                    PARTICIPATION_FIELDS,
                    extra={"occurrence_id": oid, "sort_order": order},
                )
                self.participant(oid, part["entity_id"])
            for order, action in enumerate(occurrence["actions"]):
                self.record(
                    "action",
                    action,
                    ACTION_FIELDS,
                    extra={"occurrence_id": oid, "sort_order": order},
                )
                self.participant(oid, action["actor_id"])
                aid = self.activity("action", action["action_id"])
                for detail_index, detail in enumerate(action["details"]):
                    self.record(
                        "activity_detail",
                        {"value": detail},
                        ["value"],
                        extra={"activity_id": aid, "detail_index": detail_index},
                    )
            for order, transaction in enumerate(occurrence["transactions"]):
                row = self.record(
                    "financial_transaction",
                    transaction,
                    TRANSACTION_FIELDS,
                    extra={"occurrence_id": oid, "sort_order": order},
                )
                for side in ("from_entity_id", "to_entity_id"):
                    if row[side] == "unknown":
                        row[side] = None
                    self.participant(oid, row[side])
                self.activity("transaction", transaction["transaction_id"])
                for ordinal, instrument in enumerate(transaction["instruments"]):
                    self.record(
                        "transaction_instrument",
                        {"description": instrument},
                        ["description"],
                        extra={
                            "transaction_id": transaction["transaction_id"],
                            "ordinal": ordinal,
                        },
                    )
        for index, relation in enumerate(graph["relations"]):
            self.record(
                "entity_relation",
                relation,
                RELATION_FIELDS,
                extra={"sort_order": index},
            )
            self.package["relation_occurrence"].extend(
                {
                    "relation_id": relation["relation_id"],
                    "occurrence_id": oid,
                    "sort_order": order,
                }
                for order, oid in enumerate(relation["event_ids"])
            )
        return self.package


def from_subject_graph(graph):
    """Convert legacy person facts without inferring domains, events, or stages.

    The package version is 3.0; graph.schema_version retains the source format for
    roundtrip export. Source documents remain empty because SubjectGraph embeds
    quotes without document identities or offsets.
    """
    _require_valid(validate_subject_graph(graph), "SubjectGraph")
    if graph["subject_type"] != "individual":
        raise ValueError("Person EPG conversion requires an individual subject")
    package = _Converter().convert(graph)
    _require_valid(validate_person_epg(package), "Person EPG")
    return package


def to_subject_graph(package):
    """Restore the legacy factual graph; organization remains in the EPG package.

    For packages produced by from_subject_graph this is an exact, non-mutating
    roundtrip. Higher-level event/stage memberships have no legacy representation.
    """
    _require_valid(validate_person_epg(package), "Person EPG")
    sets = {
        row["evidence_set_id"]: row.get("field_metadata") or {}
        for row in package["evidence_set"]
    }
    spans = {row["span_id"]: row["quote"] for row in package["evidence_span"]}
    times = {row["time_id"]: row for row in package["time_value"]}
    links = {}
    for row in package["evidence_link"]:
        links.setdefault((row["evidence_set_id"], row["field_path"]), []).append(row)

    def ordered(table, key="sort_order"):
        return sorted(package[table], key=lambda row: row.get(key, 0))

    def restore(value, path, sid):
        if path in sets.get(sid, {}):
            quotes = sorted(
                links.get((sid, path), []), key=lambda row: row["quote_order"]
            )
            return {
                "value": copy.deepcopy(value),
                "evidence_source_contents": [spans[row["span_id"]] for row in quotes],
                **copy.deepcopy(sets[sid][path]),
            }
        if isinstance(value, dict):
            return {
                key: restore(item, path + "/" + _pointer(key), sid)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                restore(item, path + "/" + str(index), sid)
                for index, item in enumerate(value)
            ]
        return copy.deepcopy(value)

    def record(row, fields, renames=None):
        sid = row.get("evidence_set_id")
        result = {}
        for field in fields:
            if field in TIME_FIELDS:
                tid = row.get(TIME_FIELDS[field])
                if tid is None:
                    raise ValueError(
                        f"Cannot restore SubjectGraph: missing {TIME_FIELDS[field]}"
                    )
                time = times[tid]
                value = restore(time["value"], "/" + field, sid)
                if time.get("window_start") is not None:
                    if not isinstance(value, dict):
                        raise ValueError(
                            f"Cannot restore SubjectGraph: missing value-field metadata for {field}"
                        )
                    value["time_window"] = {
                        "start": time["window_start"],
                        "end": time["window_end"],
                        "original": time["original_text"],
                        "approximate": time["is_approximate"],
                    }
            else:
                column = (renames or {}).get(field, field)
                if column not in row:
                    raise ValueError(
                        f"Cannot restore SubjectGraph: missing source column {column}"
                    )
                raw = row[column]
                if field in ("from_entity_id", "to_entity_id") and raw is None:
                    raw = "unknown"
                value = restore(raw, "/" + _pointer(field), sid)
            result[field] = value
        return result

    out = record(package["graph"], GRAPH_FIELDS, {"subject_id": "subject_entity_id"})
    out["entities"] = []
    for row in ordered("entity"):
        entity = record(row, ["entity_id", "name", "entity_type", "attributes"])
        entity["aliases"] = [
            a["alias"]
            for a in ordered("entity_alias")
            if a["entity_id"] == row["entity_id"]
        ]
        out["entities"].append(entity)
    action_activities = {
        row["action_id"]: row["activity_id"]
        for row in package["activity"]
        if row.get("action_id") is not None
    }
    out["events"] = []
    for row in ordered("occurrence"):
        occurrence = record(row, OCCURRENCE_FIELDS, {"event_id": "occurrence_id"})
        oid = row["occurrence_id"]
        occurrence["participations"] = [
            record(part, PARTICIPATION_FIELDS)
            for part in ordered("participation")
            if part["occurrence_id"] == oid
        ]
        occurrence["actions"] = []
        for action_row in ordered("action"):
            if action_row["occurrence_id"] != oid:
                continue
            action = record(action_row, ACTION_FIELDS)
            aid = action_activities.get(action_row["action_id"])
            action["details"] = [
                record(detail, ["value"])["value"]
                for detail in ordered("activity_detail", "detail_index")
                if detail["activity_id"] == aid
            ]
            occurrence["actions"].append(action)
        occurrence["transactions"] = []
        for transaction_row in ordered("financial_transaction"):
            if transaction_row["occurrence_id"] != oid:
                continue
            transaction = record(transaction_row, TRANSACTION_FIELDS)
            transaction["instruments"] = [
                record(item, ["description"])["description"]
                for item in ordered("transaction_instrument", "ordinal")
                if item["transaction_id"] == transaction_row["transaction_id"]
            ]
            occurrence["transactions"].append(transaction)
        out["events"].append(occurrence)
    out["relations"] = []
    for row in ordered("entity_relation"):
        relation = record(row, RELATION_FIELDS)
        relation["event_ids"] = [
            item["occurrence_id"]
            for item in ordered("relation_occurrence")
            if item["relation_id"] == row["relation_id"]
        ]
        out["relations"].append(relation)
    _require_valid(validate_subject_graph(out), "restored SubjectGraph")
    return out
