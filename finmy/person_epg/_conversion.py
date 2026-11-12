"""Canonical fact serialization into the unchanged Person EPG 3.0 contract.

Legacy events become occurrences. Higher-level events and stages are left empty;
classification belongs to the organizer, not to this serialization adapter.
"""

from __future__ import annotations

import copy


from .schema import MODEL, SCHEMA_VERSION

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
