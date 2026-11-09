"""Evidence-first Person facts, independent of the legacy EventCascade builder.

Only this phase changes factual identity, transaction granularity and occurrence
boundaries. Organization consumes its stable activity IDs. Model proposals are
applied one item at a time; rejected items never discard accepted neighbours.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from finmy.person_epg.adapter import _Converter, TIME_FIELDS
from finmy.person_epg.schema import SCHEMA_VERSION
from finmy.person_epg.validation import validate_person_epg
from finmy.person_epg.sparse_adapter import ground_person_evidence
from finmy.subject_graph.validation import date_interval
from .runtime import digest
from .completion_errors import IncompleteCompletionError

VERSION = "canonical-person-v1"
UNKNOWN = {"", "unknown", "unspecified", "none", "null", "n/a"}

EXTRACTION_SYSTEM = """Extract evidence-bound facts for a Person EPG. Return JSON
{"entities":[],"occurrences":[]}. You are extracting real occurrences, not a
biography outline or stages. The search event plan is routing context, not a
limit on supported facts. Inspect the entire supplied source excerpt. Reuse
known entity IDs. Do not duplicate an action for each storyline.

Every text/time field VF is {"value":"English text","citations":[{"document_id":
"DOC_00001","quote":"exact original excerpt"}]}. Translate values, NEVER quotes.
Unknown dates are {"value":"unknown","citations":[]}; do not invent precision.
A normalized/fuzzy time may use time_window {start,end,original,approximate}.
Dates need supporting context, not literal equality with the normalized value.

Entity: {entity_id,name:VF,entity_type:"individual|organization|unknown",aliases:[],
attributes:{}}. Occurrence: {occurrence_id,title:VF,subject_relevance:VF,
start_time:VF,end_time:VF,descriptions:[VF],actions:[],transactions:[]}.
Action: {action_id,actor_id,action_type:VF,timestamp:VF,details:[VF],
time_role:"occurrence|disclosure|as_of|historical"}.
Transaction: {transaction_id,name:VF,from_entity_id:null|ID,to_entity_id:null|ID,
timestamp:VF,details:[VF],instruments:[VF],time_role:"occurrence|historical"}.

Separate an action from a later statement ABOUT that action. A report's date,
financial reporting period and holdings-as-of date are not interchangeable.
Historical purchases mentioned at a later meeting belong to their own occurrence.
One actual transfer per sender/recipient/asset/time: use separate transactions
for different recipients. Put the aggregate total in a descriptive action;
do not attach a many-recipient total to a single recipient. Unknown market
counterparty is null; the security issuer is not automatically the seller.
Preserve distinct facts and numeric units; do not infer changes between quantities
with unexplained denominators. Attribute reporter background to the reporter,
not to a quoted person. Relevance may be indirect, but state the evidenced link.
The returned list may be empty when the excerpt supplies no relevant facts.
For an already catalogued fact, reuse its occurrence/fact ID and existing scalar
identity fields, adding supported details. Otherwise give new globally unique
IDs, preferably prefixed by document_id; reconciliation will compare candidates.
When retry_items are supplied, return corrected items with their IDs. If a pending
candidate is unsupported, explicitly return rejected_candidates:[{pending_id,reason}].
An empty response does not resolve earlier pending candidates.
"""

RECONCILE_SYSTEM = """Resolve the supplied Person fact candidates BEFORE any event
or stage organization. Return JSON {"operations":[],"reviewed_occurrence_ids":[]}.
Use only the supplied source evidence and existing identifiers. All text/time
edits use VF {value,citations:[{document_id,quote}]}; quotes stay verbatim.
No operation is required for an already correct fact. Do not re-extract the graph.
Allowed operations (each has a reason):
merge_occurrences {keep_id,occurrence_ids}: SAME real scene, not just same theme/date.
merge_facts {keep_id,fact_ids}: SAME action or transfer; all unique details and
citations are retained automatically. Different recipients cannot be merged.
edit_fact {fact_id,changes:{actor_id|action_type|name|timestamp|from_entity_id|to_entity_id}}.
split_transaction {transaction_id,legs:[complete transaction records]}: one leg
per actual recipient. An aggregate action automatically retains ALL old details.
create_occurrence {occurrence:{occurrence_id,title:VF,subject_relevance:VF,
start_time:VF,end_time:VF,descriptions:[VF]}} then move_fact {fact_id,occurrence_id}.
edit_occurrence {occurrence_id,changes:{title|subject_relevance|start_time|end_time}}.
merge_entities {keep_id,entity_ids}: same real entity supported by evidence,
not employer/employee or related foundations.

Prioritize duplicate annual letters/meetings and repeated purchases; distinguish
one action from separate statements about it. Split a multi-recipient donation
before organization. Split historical activity from later speech/report scenes:
the action's occurrence date, disclosure date and reporting-as-of date differ.
Do not widen a meeting to include a historical purchase just because mentioned
there. Fuzzy dates and unknown dates are legitimate. Scene ranges are subsequently
derived from contained factual times. Repeated themes are not duplicate facts.
Use existing facts outside the assigned group as merge targets when they are
the same real action. An operation must touch an assigned occurrence or fact.
Do not delete supported facts merely because the person link is indirect.
"""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def canonical_input_hash(build_input, subject, storyline_plan=None):
    return _hash({"version": VERSION, "semantic_sha256": _hash([EXTRACTION_SYSTEM, RECONCILE_SYSTEM]),
                  "subject": subject, "storyline_plan": storyline_plan,
                  "source_registry": (getattr(build_input.user_query, "extras", None) or {}).get("source_registry", {}),
                  "samples": [{"sample_id": getattr(s, "sample_id", None),
                               "raw_data_id": getattr(s, "raw_data_id", None),
                               "content": s.content} for s in build_input.samples]})


def _value(value):
    return value.get("value") if isinstance(value, dict) else value


def _unknown(value):
    return str(_value(value) or "").strip().casefold() in UNKNOWN


def _metadata(value, reason="Derived workflow metadata; not a source assertion."):
    return {"value": value, "evidence_source_contents": [], "reasons": [reason]}


def _citations(field):
    return field.get("_citations", []) if isinstance(field, dict) else []


def _field(value, documents, *, allow_unknown=False):
    if not isinstance(value, dict) or not isinstance(value.get("value"), str):
        raise ValueError("Fact fields must be objects with a string value")
    refs = value.get("citations", value.get("_citations", []))
    if not isinstance(refs, list):
        raise ValueError("Citations must be a list")
    checked = []
    for ref in refs:
        if not isinstance(ref, dict):
            raise ValueError("Citation must name a document and quote")
        doc_id, quote = ref.get("document_id"), ref.get("quote")
        if doc_id not in documents or not isinstance(quote, str) or not quote.strip():
            raise ValueError("Unknown document or empty quote")
        text = documents[doc_id]["content"]
        start = ref.get("char_start")
        if type(start) is not int or text[start:start + len(quote)] != quote:
            start = text.find(quote)
        if start < 0:
            raise ValueError("Quote is absent from its declared source document")
        checked.append({"document_id": doc_id, "quote": quote,
                        "char_start": start, "char_end": start + len(quote)})
    if not checked and not (allow_unknown and _unknown(value)):
        raise ValueError("A new factual assertion requires source-bound evidence")
    out = {"value": value["value"], "evidence_source_contents": [r["quote"] for r in checked],
           "reasons": list(value.get("reasons", [])), "_citations": checked}
    if "time_window" in value:
        if date_interval(value) is None:
            raise ValueError("Invalid normalized time window")
        out["time_window"] = copy.deepcopy(value["time_window"])
    return out


def _merge_fields(left, right):
    out = copy.deepcopy(left)
    if not isinstance(out, dict):
        if not isinstance(right, dict):
            return out
        out = _metadata(str(left))
    for key in ("evidence_source_contents", "reasons", "_citations"):
        values = out.setdefault(key, [])
        for value in (right.get(key, []) if isinstance(right, dict) else []):
            if value not in values:
                values.append(copy.deepcopy(value))
    if out.get("_citations"):
        # Equal text in two documents is two pieces of provenance, not one.
        bound_quotes = [r["quote"] for r in out["_citations"]]
        unbound = [q for q in out.get("evidence_source_contents", []) if q not in bound_quotes]
        out["evidence_source_contents"] = bound_quotes + unbound
    return out


def _merge_list(left, right):
    for item in right:
        existing = next((i for i in left if _value(i) == _value(item)), None)
        if existing is None:
            left.append(copy.deepcopy(item))
        elif isinstance(existing, dict):
            existing.update(_merge_fields(existing, item))


def _merge_entity(target, source):
    target["name"] = _merge_fields(target["name"], source["name"])
    target["aliases"] = list(dict.fromkeys(target.get("aliases", []) + source.get("aliases", [])))
    if target.get("entity_type") == "unknown":
        target["entity_type"] = source["entity_type"]
    for key, field in source.get("attributes", {}).items():
        old = target.setdefault("attributes", {}).get(key)
        if old is None:
            target["attributes"][key] = copy.deepcopy(field)
        elif _value(old) == _value(field):
            target["attributes"][key] = _merge_fields(old, field)
        else:
            combined = _merge_fields(old, field)
            if not isinstance(combined, dict):
                combined = _metadata(str(_value(old)))
            combined["value"] = str(_value(old)) + "; " + str(_value(field))
            combined.setdefault("reasons", []).append("Distinct source assertions retained; compatibility is not inferred.")
            combined["evidence_status"] = "needs_review"
            target["attributes"][key] = combined


def _sources(build_input, seed=None):
    if seed is not None:
        return copy.deepcopy(seed["source_document"])
    registry = (getattr(build_input.user_query, "extras", None) or {}).get("source_registry", {})
    result = []
    for index, sample in enumerate(build_input.samples):
        meta = registry.get(getattr(sample, "raw_data_id", None), {}) if isinstance(registry, dict) else {}
        meta = meta if isinstance(meta, dict) else {}
        doc_id = meta.get("document_id") or f"DOC_{index + 1:05d}"
        if not isinstance(doc_id, str) or not doc_id:
            raise ValueError("Source registry document IDs must be nonempty strings")
        if any(d["document_id"] == doc_id for d in result):
            doc_id += "__SAMPLE_" + _hash([getattr(sample, "sample_id", index), index])[:12]
        result.append({"document_id": doc_id, "content": sample.content,
                       "title": meta.get("title"), "source_url": meta.get("source_url", meta.get("url")),
                       "published_at": meta.get("published_at")})
    return result


def _restore_graph(package):
    """Restore facts without invoking legacy temporal containment validation.

    A saved native graph is a valid input even when its old compatibility export
    failed. Preserve source anchors while restoring verifiable fields.
    """
    validation = validate_person_epg(package)
    if not validation["valid"]:
        raise ValueError("Invalid canonical seed: " + str(validation["errors"][:2]))
    metadata = {r["evidence_set_id"]: r.get("field_metadata") or {} for r in package["evidence_set"]}
    spans = {r["span_id"]: r for r in package["evidence_span"]}
    times = {r["time_id"]: r for r in package["time_value"]}
    links = {}
    for link in package["evidence_link"]:
        links.setdefault((link["evidence_set_id"], link["field_path"]), []).append(link)

    def restore(raw, path, sid):
        if path in metadata.get(sid, {}):
            selected = [spans[l["span_id"]] for l in sorted(links.get((sid, path), []),
                                                         key=lambda r: r["quote_order"])]
            return {"value": copy.deepcopy(raw), "evidence_source_contents": [s["quote"] for s in selected],
                    **copy.deepcopy(metadata[sid][path]),
                    "_citations": [{k: s.get(k) for k in ("document_id", "quote", "char_start", "char_end")}
                                   for s in selected if s.get("document_id")]}
        if isinstance(raw, list):
            return [restore(v, path + "/" + str(i), sid) for i, v in enumerate(raw)]
        if isinstance(raw, dict):
            return {k: restore(v, path + "/" + str(k).replace("~", "~0").replace("/", "~1"), sid)
                    for k, v in raw.items()}
        return copy.deepcopy(raw)

    def record(row, keys, renames=None):
        out = {}
        for key in keys:
            if key in TIME_FIELDS:
                tid = row.get(TIME_FIELDS[key])
                if tid is None:
                    out[key] = _metadata("unknown", "Time was not supplied in the saved facts.")
                    continue
                time = times[tid]
                out[key] = restore(time["value"], "/" + key, row.get("evidence_set_id"))
                if time.get("window_start") is not None:
                    if not isinstance(out[key], dict):
                        out[key] = _metadata(out[key])
                    out[key]["time_window"] = {"start": time["window_start"], "end": time["window_end"],
                        "original": time["original_text"], "approximate": time["is_approximate"]}
            else:
                raw = row.get((renames or {}).get(key, key))
                if raw is None and key in {"descriptions", "details", "instruments"}:
                    raw = []
                if raw is None and key == "attributes":
                    raw = {}
                if key in {"from_entity_id", "to_entity_id"} and raw is None:
                    raw = "unknown"
                out[key] = restore(raw, "/" + key, row.get("evidence_set_id"))
        return out

    graph = record(package["graph"], ["graph_id", "schema_version", "subject_id", "subject_type",
        "coverage_start", "coverage_end", "title", "descriptions"], {"subject_id": "subject_entity_id"})
    graph["entities"] = []
    for row in package["entity"]:
        entity = record(row, ["entity_id", "name", "entity_type", "attributes"])
        entity["aliases"] = [a["alias"] for a in package["entity_alias"] if a["entity_id"] == row["entity_id"]]
        graph["entities"].append(entity)
    activities = {a.get("action_id"): a["activity_id"] for a in package["activity"] if a.get("action_id")}
    graph["events"] = []
    for row in package["occurrence"]:
        occurrence = record(row, ["event_id", "title", "subject_relevance", "start_time", "end_time", "descriptions"],
                            {"event_id": "occurrence_id"})
        oid = occurrence["event_id"]
        occurrence["participations"] = [record(r, ["participation_id", "entity_id", "role", "start_time", "end_time"])
                                       for r in package["participation"] if r["occurrence_id"] == oid]
        occurrence["actions"], occurrence["transactions"] = [], []
        for row in package["action"]:
            if row["occurrence_id"] == oid:
                action = record(row, ["action_id", "actor_id", "action_type", "timestamp"])
                action["details"] = [record(r, ["value"])["value"] for r in sorted(package["activity_detail"],
                    key=lambda r: r["detail_index"]) if r["activity_id"] == activities[row["action_id"]]]
                occurrence["actions"].append(action)
        for row in package["financial_transaction"]:
            if row["occurrence_id"] == oid:
                transaction = record(row, ["transaction_id", "name", "from_entity_id", "to_entity_id", "timestamp", "details"])
                transaction["instruments"] = [record(r, ["description"])["description"]
                    for r in package["transaction_instrument"] if r["transaction_id"] == row["transaction_id"]]
                occurrence["transactions"].append(transaction)
        graph["events"].append(occurrence)
    graph["relations"] = []
    for row in package["entity_relation"]:
        relation = record(row, ["relation_id", "from_entity_id", "to_entity_id", "relation_type", "valid_from", "valid_to"])
        relation["event_ids"] = [r["occurrence_id"] for r in package["relation_occurrence"]
                                 if r["relation_id"] == row["relation_id"]]
        graph["relations"].append(relation)
    graph["_context_activities"] = [{"row": copy.deepcopy(row), "details": [
        {"detail_index": r["detail_index"], "value": record(r, ["value"])["value"]}
        for r in package["activity_detail"] if r["activity_id"] == row["activity_id"]]}
        for row in package["activity"] if row.get("context_occurrence_id")]
    # get(key, default) does not substitute an explicit null action_id.
    graph["_activity_ids"] = {(r.get("action_id") or r.get("transaction_id")): r["activity_id"]
        for r in package["activity"] if r.get("action_id") or r.get("transaction_id")}
    graph["_extra_participants"] = copy.deepcopy(package["occurrence_participant"])
    return graph


def _package(graph, documents):
    class Converter(_Converter):
        def participant(self, occurrence_id, entity_id):
            # Old attribution repairs may have attached field evidence to the
            # actor ID. Keep that evidence while indexing its scalar identity.
            return super().participant(occurrence_id, _value(entity_id))
    converter = Converter()
    package = converter.convert(graph)
    aid_map = {}
    for row in package["activity"]:
        fid = row.get("action_id") or row.get("transaction_id")
        new_id = graph.get("_activity_ids", {}).get(fid, row["activity_id"])
        aid_map[row["activity_id"]] = new_id
        row["activity_id"] = new_id
    for row in package["activity_detail"]:
        row["activity_id"] = aid_map.get(row["activity_id"], row["activity_id"])
    occurrence_ids = {o["occurrence_id"] for o in package["occurrence"]}
    entity_ids = {e["entity_id"] for e in package["entity"]}
    for row in graph.get("_extra_participants", []):
        if row["occurrence_id"] in occurrence_ids and row["entity_id"] in entity_ids and row not in package["occurrence_participant"]:
            package["occurrence_participant"].append(copy.deepcopy(row))
    for context in graph.get("_context_activities", []):
        package["activity"].append(copy.deepcopy(context["row"]))
        for row in context["details"]:
            converter.record("activity_detail", {"value": row["value"]}, ["value"],
                extra={"activity_id": context["row"]["activity_id"], "detail_index": row["detail_index"]})
    package["source_document"] = copy.deepcopy(list(documents.values()))
    sets = {s["evidence_set_id"]: s for s in package["evidence_set"]}
    spans = {s["span_id"]: s for s in package["evidence_span"]}
    consumed = {}
    for link in package["evidence_link"]:
        meta = (sets[link["evidence_set_id"]].get("field_metadata") or {}).get(link["field_path"], {})
        quote = spans[link["span_id"]]["quote"]
        refs = [r for r in meta.get("_citations", []) if r.get("quote") == quote and r.get("document_id") in documents]
        if refs:
            key = (link["evidence_set_id"], link["field_path"], quote)
            position = consumed.get(key, 0)
            ref = refs[min(position, len(refs) - 1)]
            consumed[key] = position + 1
            spans[link["span_id"]].update({k: ref[k] for k in ("document_id", "char_start", "char_end")})
    for row in package["evidence_set"]:
        for meta in (row.get("field_metadata") or {}).values():
            meta.pop("_citations", None)
    ground_person_evidence(package)
    check = validate_person_epg(package)
    if not check["valid"]:
        raise ValueError("Invalid canonical facts: " + str(check["errors"][:2]))
    return package


def _fact_index(graph):
    return {r[key]: (occurrence, kind, r) for occurrence in graph["events"]
            for kind, key in (("actions", "action_id"), ("transactions", "transaction_id"))
            for r in occurrence[kind]}


def _validate_id(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A stable nonempty ID is required")
    return value


def _entity_ref(value, entities, *, unknown=False):
    value = _value(value)
    if unknown and (value is None or _unknown(value)):
        return "unknown"
    if value not in entities:
        raise ValueError("Unknown entity: " + str(value))
    return value


def _fact(row, kind, entities, documents):
    if not isinstance(row, dict):
        raise ValueError("Fact must be an object")
    key = "action_id" if kind == "actions" else "transaction_id"
    out = {key: _validate_id(row.get(key)), "timestamp": _field(row.get("timestamp", {"value": "unknown"}),
                                                                                documents, allow_unknown=True),
           "details": [_field(v, documents) for v in row.get("details", [])]}
    if kind == "actions":
        out.update(actor_id=_entity_ref(row.get("actor_id"), entities),
                   action_type=_field(row.get("action_type"), documents))
    else:
        out.update(name=_field(row.get("name"), documents),
                   from_entity_id=_entity_ref(row.get("from_entity_id"), entities, unknown=True),
                   to_entity_id=_entity_ref(row.get("to_entity_id"), entities, unknown=True),
                   instruments=[_field(v, documents) for v in row.get("instruments", [])])
    if row.get("time_role") in {"occurrence", "disclosure", "as_of", "historical"}:
        out["timestamp"]["time_role"] = row["time_role"]
    return out


def _scene(row, documents):
    if not isinstance(row, dict):
        raise ValueError("Occurrence must be an object")
    return {"event_id": _validate_id(row.get("occurrence_id", row.get("event_id"))),
            "title": _field(row.get("title"), documents),
            "subject_relevance": _field(row.get("subject_relevance"), documents),
            "start_time": _field(row.get("start_time", {"value": "unknown"}), documents, allow_unknown=True),
            "end_time": _field(row.get("end_time", {"value": "unknown"}), documents, allow_unknown=True),
            "descriptions": [_field(v, documents) for v in row.get("descriptions", [])],
            "participations": [], "actions": [], "transactions": []}


def _scope(graph, audit):
    """Derive containment from facts, retaining unknown/fuzzy values verbatim.

    Dates alone never split a scene. Semantic moves/merges are model proposals;
    unresolved containment changes are visible review items, not silent repairs.
    """
    for occurrence in list(graph["events"]):
        bounds = [date_interval(occurrence.get(k)) for k in ("start_time", "end_time")]
        boundary = (bounds[0][0], bounds[1][1]) if all(bounds) else None
        for kind in ("actions", "transactions"):
            for fact in list(occurrence[kind]):
                interval = date_interval(fact.get("timestamp"))
                outside = boundary and interval and (interval[1] < boundary[0] or interval[0] > boundary[1])
                if outside:
                    fid = fact.get("action_id", fact.get("transaction_id"))
                    audit.append({"status": "needs_review", "op": "temporal_membership",
                        "fact_id": fid, "occurrence_id": occurrence["event_id"],
                        "previous_start": copy.deepcopy(occurrence["start_time"]),
                        "previous_end": copy.deepcopy(occurrence["end_time"]),
                        "reason": "Fact falls outside prior scene bounds. Date alone does not decide scene identity; derived containment is updated and semantic membership remains flagged."})
    for occurrence in graph["events"]:
        facts = occurrence["actions"] + occurrence["transactions"]
        dated = [(date_interval(f["timestamp"]), f["timestamp"]) for f in facts]
        dated = [(interval, value) for interval, value in dated if interval is not None]
        if dated:
            occurrence["start_time"] = copy.deepcopy(min(dated, key=lambda p: p[0][0])[1])
            occurrence["end_time"] = copy.deepcopy(max(dated, key=lambda p: p[0][1])[1])


def _apply_operation(graph, op, documents, assigned=None):
    if not isinstance(op, dict) or not isinstance(op.get("reason"), str) or not op["reason"].strip():
        raise ValueError("Operation needs a reason")
    kind = op.get("op")
    scenes = {o["event_id"]: o for o in graph["events"]}
    facts = _fact_index(graph)
    entities = {e["entity_id"] for e in graph["entities"]}
    touched = {op.get("occurrence_id"), op.get("keep_id"), *op.get("occurrence_ids", [])}
    for fid in [op.get("fact_id"), op.get("transaction_id"), op.get("keep_id"), *op.get("fact_ids", [])]:
        if fid in facts:
            touched.add(facts[fid][0]["event_id"])
    if assigned is not None and kind not in {"create_occurrence", "merge_entities"} and not touched.intersection(assigned):
        raise ValueError("Operation does not touch its assigned occurrences")
    if kind == "merge_facts":
        keep = op["keep_id"]
        target_scene, target_kind, target = facts[keep]
        for fid in op["fact_ids"]:
            if fid == keep:
                continue
            scene, source_kind, source = facts[fid]
            if source_kind != target_kind:
                raise ValueError("Cannot merge an action with a transaction")
            keys = ["actor_id"] if source_kind == "actions" else ["from_entity_id", "to_entity_id"]
            if any(_value(source[k]) != _value(target[k]) for k in keys):
                raise ValueError("Distinct actors or recipients cannot be merged")
            _merge_list(target["details"], source["details"])
            if source_kind == "transactions":
                _merge_list(target["instruments"], source["instruments"])
            for key in ("action_type", "name", "timestamp"):
                if key in target and key in source:
                    target[key] = _merge_fields(target[key], source[key])
            scene[source_kind].remove(source)
    elif kind == "merge_occurrences":
        target = scenes[op["keep_id"]]
        for oid in op["occurrence_ids"]:
            if oid == op["keep_id"]:
                continue
            source = scenes[oid]
            for key in ("descriptions",):
                _merge_list(target[key], source[key])
            for key in ("actions", "transactions", "participations"):
                target[key].extend(source[key])
            for key in ("title", "subject_relevance", "start_time", "end_time"):
                target[key] = _merge_fields(target[key], source[key])
            for relation in graph["relations"]:
                relation["event_ids"] = list(dict.fromkeys(op["keep_id"] if v == oid else v for v in relation["event_ids"]))
            for row in graph.get("_extra_participants", []):
                if row["occurrence_id"] == oid:
                    row["occurrence_id"] = op["keep_id"]
            contexts = graph.get("_context_activities", [])
            for context in list(contexts):
                if context["row"]["context_occurrence_id"] == oid:
                    canonical = next((c for c in contexts if c["row"]["context_occurrence_id"] == op["keep_id"]), None)
                    if canonical is None:
                        context["row"]["context_occurrence_id"] = op["keep_id"]
                    else:
                        known = {_value(r["value"]) for r in canonical["details"]}
                        for detail in context["details"]:
                            if _value(detail["value"]) not in known:
                                canonical["details"].append({"detail_index": len(canonical["details"]),
                                                             "value": copy.deepcopy(detail["value"])})
                        contexts.remove(context)
            graph["events"].remove(source)
        # This is an explicit semantic scene merge, not automatic date-based merging.
        target["start_time"], target["end_time"] = _metadata("unknown"), _metadata("unknown")
    elif kind == "edit_fact":
        _, fact_kind, target = facts[op["fact_id"]]
        allowed = {"timestamp", "actor_id", "action_type"} if fact_kind == "actions" else {
            "timestamp", "name", "from_entity_id", "to_entity_id"}
        for key, value in op["changes"].items():
            if key not in allowed:
                raise ValueError("Unsupported fact field: " + key)
            target[key] = (_entity_ref(value, entities, unknown=key != "actor_id") if key.endswith("_id")
                           else _field(value, documents, allow_unknown=key == "timestamp"))
    elif kind == "split_transaction":
        scene, fact_kind, original = facts[op["transaction_id"]]
        if fact_kind != "transactions" or len(op.get("legs", [])) < 2:
            raise ValueError("Splitting requires at least two evidence-bound transfer legs")
        legs = [_fact(r, "transactions", entities, documents) for r in op["legs"]]
        ids = [r["transaction_id"] for r in legs]
        if len(ids) != len(set(ids)) or any(fid in facts and fid != op["transaction_id"] for fid in ids):
            raise ValueError("Duplicate split transaction IDs")
        signatures = [(_value(r["from_entity_id"]), _value(r["to_entity_id"]), _value(r["timestamp"]),
                       tuple(_value(v) for v in r["instruments"])) for r in legs]
        if len(set(signatures)) != len(signatures):
            raise ValueError("Duplicate transfer legs")
        actor = _value(original["from_entity_id"])
        if actor not in entities:
            raise ValueError("Cannot represent an aggregate action without its supported sender")
        aggregate_id = "AGG_" + original["transaction_id"]
        if aggregate_id in facts:
            raise ValueError("Aggregate action ID already exists")
        scene["actions"].append({"action_id": aggregate_id, "actor_id": actor,
            "action_type": copy.deepcopy(original["name"]), "timestamp": copy.deepcopy(original["timestamp"]),
            "details": copy.deepcopy(original["details"] + original["instruments"])})
        scene["transactions"].remove(original)
        scene["transactions"].extend(legs)
    elif kind == "create_occurrence":
        scene = _scene(op["occurrence"], documents)
        if scene["event_id"] in scenes:
            raise ValueError("Occurrence ID already exists")
        graph["events"].append(scene)
    elif kind == "move_fact":
        source, fact_kind, fact = facts[op["fact_id"]]
        target = scenes[op["occurrence_id"]]
        if source is not target:
            source[fact_kind].remove(fact)
            target[fact_kind].append(fact)
    elif kind == "edit_occurrence":
        target = scenes[op["occurrence_id"]]
        for key, value in op["changes"].items():
            if key not in {"title", "subject_relevance", "start_time", "end_time"}:
                raise ValueError("Unsupported occurrence field")
            target[key] = _field(value, documents, allow_unknown=key in {"start_time", "end_time"})
    elif kind == "merge_entities":
        keep = op["keep_id"]
        if keep not in entities:
            raise ValueError("Unknown canonical entity")
        drops = set(op["entity_ids"]) - {keep}
        if not drops <= entities or graph["subject_id"] in drops:
            raise ValueError("Unknown entity or attempted subject replacement")
        target = next(e for e in graph["entities"] if e["entity_id"] == keep)
        for source in list(graph["entities"]):
            if source["entity_id"] in drops:
                target["name"] = _merge_fields(target["name"], source["name"])
                target["aliases"] = list(dict.fromkeys(target["aliases"] + [_value(source["name"])] + source["aliases"]))
                _merge_entity(target, source)
                graph["entities"].remove(source)
        for scene in graph["events"]:
            for row in scene["actions"] + scene["transactions"] + scene["participations"]:
                for key in ("actor_id", "from_entity_id", "to_entity_id", "entity_id"):
                    if _value(row.get(key)) in drops:
                        row[key] = keep
        for relation in graph["relations"]:
            for key in ("from_entity_id", "to_entity_id"):
                if relation[key] in drops:
                    relation[key] = keep
        for row in graph.get("_extra_participants", []):
            if row["entity_id"] in drops:
                row["entity_id"] = keep
    else:
        raise ValueError("Unknown canonical operation: " + str(kind))


def apply_canonical_proposal(package, proposal, *, assigned_occurrence_ids=None):
    """Apply independently reviewable operations; preserve unaffected facts."""
    graph = _restore_graph(package)
    documents = {d["document_id"]: d for d in package["source_document"]}
    audit = {"version": VERSION, "items": []}
    operations = proposal.get("operations") if isinstance(proposal, dict) else None
    if not isinstance(operations, list):
        raise ValueError("Canonical proposal requires operations array")
    for index, op in enumerate(operations):
        candidate = copy.deepcopy(graph)
        try:
            _apply_operation(candidate, op, documents,
                             set(assigned_occurrence_ids) if assigned_occurrence_ids is not None else None)
            _package(candidate, documents)
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            audit["items"].append({"index": index, "status": "rejected", "operation": copy.deepcopy(op),
                                   "error": str(exc)})
        else:
            graph = candidate
            audit["items"].append({"index": index, "status": "applied", "operation": copy.deepcopy(op)})
    _scope(graph, audit["items"])
    return _package(graph, documents), audit


def _compact(graph):
    return [{"occurrence_id": o["event_id"], "title": _value(o["title"]),
             "start_time": _value(o["start_time"]), "end_time": _value(o["end_time"]),
             "facts": [{"fact_id": r.get("action_id", r.get("transaction_id")),
                        "actor_id": r.get("actor_id", _value(r.get("from_entity_id"))),
                        "recipient": _value(r.get("to_entity_id")),
                        "name": _value(r.get("action_type", r.get("name"))),
                        "timestamp": _value(r["timestamp"])} for r in o["actions"] + o["transactions"]]}
            for o in graph["events"]]


def _model_value(value):
    if isinstance(value, list):
        return [_model_value(v) for v in value]
    if isinstance(value, dict):
        if "value" in value:
            return {"value": value["value"], "citations": copy.deepcopy(_citations(value)),
                    **({"time_role": value["time_role"]} if "time_role" in value else {}),
                    **({"time_window": value["time_window"]} if "time_window" in value else {})}
        return {k: _model_value(v) for k, v in value.items() if not k.startswith("_")}
    return value


def _excerpts(scenes, documents):
    refs = []
    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for ref in _citations(value):
                if ref not in refs:
                    refs.append(ref)
            for key, item in value.items():
                if key != "_citations":
                    walk(item)
    walk(scenes)
    by_doc = {}
    for ref in refs:
        if ref["document_id"] not in documents:
            continue
        text = documents[ref["document_id"]]["content"]
        start = max(0, ref["char_start"] - 500)
        end = min(len(text), ref["char_end"] + 500)
        intervals = by_doc.setdefault(ref["document_id"], [])
        if intervals and start <= intervals[-1][1] and end >= intervals[-1][0]:
            intervals[-1] = (min(start, intervals[-1][0]), max(end, intervals[-1][1]))
        else:
            intervals.append((start, end))
    return [{"document_id": did, "char_start": start, "text": documents[did]["content"][start:end]}
            for did, intervals in by_doc.items() for start, end in intervals]


def _response_shape(value, key):
    if not isinstance(value, dict) or not isinstance(value.get(key), list):
        raise ValueError("Expected JSON object with " + key + " array")


def _operation_owners(graph, op):
    if not isinstance(op, dict):
        return set()
    scenes = {o["event_id"] for o in graph["events"]}
    facts = _fact_index(graph)
    ids = [op.get("occurrence_id"), op.get("keep_id"), *op.get("occurrence_ids", [])]
    owners = {oid for oid in ids if isinstance(oid, str) and oid in scenes}
    for fid in [op.get("fact_id"), op.get("transaction_id"), op.get("keep_id"), *op.get("fact_ids", [])]:
        if isinstance(fid, str) and fid in facts:
            owners.add(facts[fid][0]["event_id"])
    return owners


def _adaptive_infer(infer, system, task, name, key, audit, persist):
    """Split only truncated work; cache each complete child response immediately."""
    relevant = ({"source": task["source"], "retry_items": task.get("retry_items", [])} if key == "occurrences"
                else {"occurrences": task["occurrences"], "assigned_fact_ids": task.get("assigned_fact_ids"),
                      "assigned_occurrence_ids": task["assigned_occurrence_ids"], "pending_issues": task.get("pending_issues", []),
                      "known_entities": task.get("known_entities"), "global_fact_catalog": task.get("global_fact_catalog")})
    cache_key = _hash({"version": VERSION, "system": system, "kind": key, "task": relevant})
    cache = audit.setdefault("response_cache", {})
    if cache_key in cache:
        return copy.deepcopy(cache[cache_key])
    try:
        response = infer(system, _json(task), name, lambda value: _response_shape(value, key))
        cache[cache_key] = copy.deepcopy(response)
        audit.setdefault("response_cache_scopes", {})[cache_key] = task.get("assigned_occurrence_ids", [])
        persist()
        return response
    except IncompleteCompletionError as exc:
        if exc.finish_reason != "length" or exc.refusal or exc.tool_calls:
            raise
        left, right = copy.deepcopy(task), copy.deepcopy(task)
        if key == "occurrences":
            text = task["source"]["text"]
            if len(text) < 512:
                raise
            midpoint = len(text) // 2
            boundary = text.rfind("\n", midpoint // 2, midpoint)
            midpoint = boundary + 1 if boundary >= 0 else midpoint
            left["source"]["text"] = text[:midpoint]
            right["source"]["text"] = text[midpoint:]
            right["source"]["char_start"] += midpoint
        elif len(task["assigned_occurrence_ids"]) > 1:
            ids = task["assigned_occurrence_ids"]
            midpoint = len(ids) // 2
            for child, selected in ((left, ids[:midpoint]), (right, ids[midpoint:])):
                child["assigned_occurrence_ids"] = selected
                child["occurrences"] = [o for o in task["occurrences"] if o["event_id"] in selected]
        else:
            occurrence = task["occurrences"][0]
            facts = [(kind, fact) for kind in ("actions", "transactions") for fact in occurrence[kind]]
            if len(facts) < 2:
                raise
            midpoint = len(facts) // 2
            for child, selected in ((left, facts[:midpoint]), (right, facts[midpoint:])):
                child["occurrences"][0]["actions"] = [f for kind, f in selected if kind == "actions"]
                child["occurrences"][0]["transactions"] = [f for kind, f in selected if kind == "transactions"]
                child["assigned_fact_ids"] = [f.get("action_id", f.get("transaction_id")) for _, f in selected]
                child["batch_instruction"] = "Only change assigned_fact_ids. Other catalog facts are merge targets/context. Review this subset only."
        audit.setdefault("subdivisions", []).append({"name": name, "reason": "output_length", "children": [name + "-L", name + "-R"]})
        persist()
        results, failures = [], []
        for suffix, child in (("-L", left), ("-R", right)):
            try:
                result = _adaptive_infer(infer, system, child, name + suffix, key, audit, persist)
                results.append(result)
                failures.extend(result.get("_failed_subtasks", []))
            except (ValueError, RuntimeError, TimeoutError, ConnectionError) as error:
                failures.append({"name": name + suffix, "error_type": type(error).__name__, "error": str(error),
                    "assigned_occurrence_ids": child.get("assigned_occurrence_ids", []),
                    "source": child.get("source")})
        combined = {key: [item for result in results for item in result[key]], "_failed_subtasks": failures}
        if key == "occurrences":
            combined["entities"] = [row for result in results for row in result.get("entities", [])]
            combined["rejected_candidates"] = [row for result in results for row in result.get("rejected_candidates", [])]
        else:
            confirmed = {oid for result in results for oid in result.get("reviewed_occurrence_ids", [])}
            failed_ids = {oid for fail in failures for oid in fail.get("assigned_occurrence_ids", [])}
            combined["reviewed_occurrence_ids"] = sorted(confirmed - failed_ids)
        if not failures:
            cache[cache_key] = copy.deepcopy(combined)
            audit.setdefault("response_cache_scopes", {})[cache_key] = task.get("assigned_occurrence_ids", [])
        persist()
        return combined


def build_canonical_facts(build_input, subject, *, infer, save, seed=None, checkpoint=None,
                          storyline_plan=None, output_language="English"):
    """Build/reuse grounded facts, then resolve their identity before organizing."""
    previous = None
    if checkpoint is not None:
        previous = copy.deepcopy(checkpoint.get("audit"))
        restored = checkpoint.get("package")
        if not isinstance(previous, dict) or not isinstance(restored, dict):
            raise ValueError("Canonical checkpoint requires package and audit")
        if previous.get("version") != VERSION or previous.get("input_sha256") != canonical_input_hash(
                build_input, subject, storyline_plan):
            raise ValueError("Canonical checkpoint belongs to a different input or pipeline version")
        if previous.get("package_sha256") != digest(restored):
            raise ValueError("Canonical checkpoint package hash mismatch")
        seed = copy.deepcopy(restored)
    source_list = _sources(build_input, seed)
    documents = {d["document_id"]: d for d in source_list}
    registry = (getattr(build_input.user_query, "extras", None) or {}).get("source_registry", {})
    source_routes = {}
    for index, sample in enumerate(build_input.samples):
        meta = registry.get(getattr(sample, "raw_data_id", None), {}) if isinstance(registry, dict) else {}
        if isinstance(meta, dict):
            doc_id = source_list[index]["document_id"] if index < len(source_list) else meta.get("document_id")
            source_routes[doc_id] = {k: copy.deepcopy(v) for k, v in meta.items() if k != "content"}
    audit = {"version": VERSION, "status": "completed",
             "input_sha256": canonical_input_hash(build_input, subject, storyline_plan),
             "seed_sha256": _hash(seed) if seed is not None else None,
             "sources": [{"document_id": d["document_id"], "source_sha256": _hash(d["content"])} for d in source_list],
             "extraction": [], "reconciliation": [], "items": [], "phase": "extraction"}
    if previous is not None:
        audit = previous
        audit["status"] = "completed"
    def persist(graph):
        package = _package(graph, documents)
        audit["package_sha256"] = digest(package)
        save(package, "PersonCanonicalFacts")
        snapshot = copy.deepcopy(audit)
        if snapshot.get("phase") != "completed":
            snapshot["status"] = "partial"
        save(snapshot, "PersonCanonicalAudit")
        return package
    if seed is not None:
        seed = copy.deepcopy(seed)
        ground_person_evidence(seed)
        graph = _restore_graph(seed)
        graph["descriptions"] = []  # summaries are derived after canonical organization
    else:
        graph = {"schema_version": "subject-graph-1.0", "graph_id": "SG_CANON_" + audit["input_sha256"][:20],
                 "subject_id": subject["subject_id"], "subject_type": "individual",
                 "coverage_start": subject.get("coverage_start"), "coverage_end": subject.get("coverage_end"),
                 "title": _metadata(subject["name"]), "descriptions": [], "relations": [], "events": [],
                 "entities": [{"entity_id": subject["subject_id"], "name": _metadata(subject["name"]),
                               "entity_type": "individual", "aliases": subject.get("aliases", []), "attributes": {}}]}
    # A resumed fresh extraction must finish missing source chunks even though
    # its already accepted partial facts are now supplied as a seed package.
    extract_sources = seed is None or (previous is not None and previous.get("seed_sha256") is None)
    if extract_sources:
        done_chunks = {(r.get("document_id"), r.get("char_start")) for r in audit["extraction"]
                       if r.get("status") == "processed"}
        batch = 0
        for document in source_list:
            text = document["content"]
            for offset in range(0, len(text), 15600):
                batch += 1
                if (document["document_id"], offset) in done_chunks:
                    continue
                name = f"PersonFacts-Extract-{batch:03d}"
                previous_failures = [r for r in audit["items"] if r.get("phase") == name
                                     and r.get("status") == "rejected" and not r.get("resolved")]
                def pending_id(item):
                    for kind, keys in (("fact", ("action_id", "transaction_id")),
                                       ("occurrence", ("occurrence_id", "event_id")), ("entity", ("entity_id",))):
                        row = item.get(kind)
                        if isinstance(row, dict):
                            for key in keys:
                                if isinstance(row.get(key), str):
                                    return kind + ":" + row[key]
                    return "item:" + _hash(item)[:16]
                for row in previous_failures:
                    row.setdefault("pending_id", pending_id(row))
                accepted_item_ids = set()
                item_start = len(audit["items"])
                task = {"subject": subject, "event_plan": storyline_plan, "output_language": output_language,
                        "source": {"document_id": document["document_id"], "char_start": offset,
                                   "text": text[offset:offset + 16000], "routing": source_routes.get(document["document_id"], {})},
                        "retry_items": previous_failures,
                        "retry_instruction": "Preserve accepted existing facts. Return missing/corrected candidates only; do not re-emit accepted rows." if previous_failures else None,
                        "known_entities": _model_value(graph["entities"]), "existing_facts": _compact(graph)}
                try:
                    response = _adaptive_infer(infer, EXTRACTION_SYSTEM, task, name, "occurrences", audit,
                                               lambda: persist(graph))
                except (ValueError, RuntimeError, TimeoutError, ConnectionError) as exc:
                    audit["extraction"].append({"name": name, "document_id": document["document_id"],
                        "char_start": offset, "status": "unavailable", "error_type": type(exc).__name__, "error": str(exc)})
                    audit["status"] = "partial"
                    persist(graph)
                    continue
                entities = {e["entity_id"]: e for e in graph["entities"]}
                for row in response.get("entities", []):
                    try:
                        if not isinstance(row, dict):
                            raise ValueError("Entity must be an object")
                        eid = _validate_id(row.get("entity_id"))
                        entity = {"entity_id": eid, "name": _field(row.get("name"), documents),
                                  "entity_type": row.get("entity_type", "unknown"),
                                  "aliases": row.get("aliases", []),
                                  "attributes": {k: _field(v, documents) for k, v in row.get("attributes", {}).items()}}
                        if not isinstance(entity["aliases"], list) or any(not isinstance(a, str) or not a.strip() for a in entity["aliases"]):
                            raise ValueError("Entity aliases must be nonempty strings")
                        if eid in entities:
                            if str(_value(entities[eid]["name"])).casefold() != str(_value(entity["name"])).casefold() and \
                                    _value(entity["name"]) not in entities[eid]["aliases"]:
                                raise ValueError("Entity ID reused for a different name")
                            candidate = copy.deepcopy(graph)
                            target = next(e for e in candidate["entities"] if e["entity_id"] == eid)
                            _merge_entity(target, entity)
                            _package(candidate, documents)
                            graph = candidate
                            entities = {e["entity_id"]: e for e in graph["entities"]}
                        else:
                            candidate = copy.deepcopy(graph)
                            candidate["entities"].append(entity)
                            _package(candidate, documents)
                            graph = candidate
                            entities = {e["entity_id"]: e for e in graph["entities"]}
                        accepted_item_ids.add("entity:" + eid)
                    except (ValueError, TypeError, KeyError) as exc:
                        audit["items"].append({"phase": name, "status": "rejected", "entity": row, "error": str(exc)})
                accepted = 0
                for row in response["occurrences"]:
                    try:
                        scene = _scene(row, documents)
                        existing_scene = next((o for o in graph["events"] if o["event_id"] == scene["event_id"]), None)
                        if existing_scene is not None and _value(existing_scene["title"]) != _value(scene["title"]):
                            raise ValueError("Occurrence ID already belongs to a different scene title")
                    except (ValueError, TypeError, KeyError) as exc:
                        audit["items"].append({"phase": name, "status": "rejected", "occurrence": row, "error": str(exc)})
                        continue
                    for kind in ("actions", "transactions"):
                        for raw in row.get(kind, []):
                            try:
                                fact = _fact(raw, kind, set(entities), documents)
                                fid = fact.get("action_id", fact.get("transaction_id"))
                                existing_fact = _fact_index(graph).get(fid)
                                if existing_fact is not None:
                                    existing_owner, existing_kind, existing_row = existing_fact
                                    compare = ("actor_id", "action_type", "timestamp") if kind == "actions" else (
                                        "from_entity_id", "to_entity_id", "name", "timestamp")
                                    if existing_owner["event_id"] != scene["event_id"] or existing_kind != kind or any(
                                            _value(existing_row[k]) != _value(fact[k]) for k in compare):
                                        raise ValueError("Existing fact ID refers to a different accepted fact")
                                    _merge_list(existing_row["details"], fact["details"])
                                    if kind == "transactions":
                                        _merge_list(existing_row["instruments"], fact["instruments"])
                                    accepted_item_ids.add("fact:" + fid)
                                    continue
                                if fid in {f.get("action_id", f.get("transaction_id"))
                                                                    for f in scene["actions"] + scene["transactions"]}:
                                    raise ValueError("Fact ID already exists")
                                scene[kind].append(fact)
                                accepted_item_ids.add("fact:" + fid)
                            except (ValueError, TypeError, KeyError) as exc:
                                audit["items"].append({"phase": name, "status": "rejected", "fact": raw, "error": str(exc)})
                    background = not scene["actions"] and not scene["transactions"]
                    if background and not scene["descriptions"]:
                        if existing_scene is not None:
                            continue  # accepted rows re-emitted by a resumed subtask
                        audit["items"].append({"phase": name, "status": "deferred", "occurrence": row,
                                               "reason": "No accepted factual activities or supported background descriptions"})
                        continue
                    candidate = copy.deepcopy(graph)
                    if existing_scene is not None:
                        target = next(o for o in candidate["events"] if o["event_id"] == scene["event_id"])
                        target["actions"].extend(scene["actions"])
                        target["transactions"].extend(scene["transactions"])
                        _merge_list(target["descriptions"], scene["descriptions"])
                    else:
                        candidate["events"].append(scene)
                    if background:
                        contexts = candidate.setdefault("_context_activities", [])
                        if not any(c["row"]["context_occurrence_id"] == scene["event_id"] for c in contexts):
                            contexts.append({"row": {"activity_id": "C:" + scene["event_id"], "action_id": None,
                                "transaction_id": None, "context_occurrence_id": scene["event_id"]}, "details": []})
                    try:
                        _package(candidate, documents)
                    except (ValueError, TypeError, KeyError) as exc:
                        audit["items"].append({"phase": name, "status": "rejected", "occurrence": row, "error": str(exc)})
                    else:
                        graph = candidate
                        accepted += 1
                        accepted_item_ids.add("occurrence:" + scene["event_id"])
                audit["extraction"] = [r for r in audit["extraction"] if
                    (r.get("document_id"), r.get("char_start")) != (document["document_id"], offset)]
                rejected = [r for r in audit["items"][item_start:] if r.get("status") == "rejected"]
                declines = {r.get("pending_id"): r["reason"] for r in response.get("rejected_candidates", [])
                            if isinstance(r, dict) and isinstance(r.get("reason"), str) and r["reason"].strip()}
                present_ids = ({"fact:" + fid for fid in _fact_index(graph)} |
                               {"occurrence:" + o["event_id"] for o in graph["events"]} |
                               {"entity:" + e["entity_id"] for e in graph["entities"]})
                accepted_item_ids.intersection_update(present_ids)
                for row in previous_failures:
                    pid = row["pending_id"]
                    if pid in accepted_item_ids:
                        row.update(resolved=True, resolution="corrected_candidate_accepted")
                    elif pid in declines:
                        row.update(resolved=True, resolution="candidate_explicitly_unsupported", resolution_reason=declines[pid])
                unresolved = [r for r in previous_failures if not r.get("resolved")]
                subtask_failures = response.get("_failed_subtasks", [])
                audit["extraction"].append({"name": name, "document_id": document["document_id"],
                    "char_start": offset, "status": "partial" if rejected or unresolved or subtask_failures else "processed",
                    "accepted_occurrences": accepted, "pending_item_count": len(rejected) + len(unresolved), "failed_subtasks": subtask_failures})
                persist(graph)
    # Reconciliation sees one shared identity catalog, with local originals rather
    # than repeatedly injecting the full 120,000-character corpus into every call.
    audit["phase"] = "reconciliation"
    reviewed = {oid for row in audit["reconciliation"] for oid in row.get("reviewed_occurrence_ids", [])}
    initial_ids = [o["event_id"] for o in graph["events"] if o["event_id"] not in reviewed]
    for index, offset in enumerate(range(0, len(initial_ids), 6), 1):
        assigned = [oid for oid in initial_ids[offset:offset + 6] if oid in {o["event_id"] for o in graph["events"]}]
        if not assigned:
            continue
        scenes = [o for o in graph["events"] if o["event_id"] in assigned]
        task = {"subject": subject, "event_plan": storyline_plan, "output_language": output_language,
                "assigned_occurrence_ids": assigned, "occurrences": _model_value(scenes),
                "known_entities": _model_value(graph["entities"]), "global_fact_catalog": _compact(graph),
                "original_excerpts": _excerpts(scenes, documents),
                "pending_issues": [r for r in audit["items"] if not r.get("resolved") and
                                   (r.get("occurrence_id") in assigned or r.get("phase", "").startswith("PersonFacts-Reconcile"))]}
        name = f"PersonFacts-Reconcile-{index:03d}"
        try:
            response = _adaptive_infer(infer, RECONCILE_SYSTEM, task, name, "operations", audit,
                                       lambda: persist(graph))
            confirmed = response.get("reviewed_occurrence_ids", [])
            if not isinstance(confirmed, list) or any(not isinstance(v, str) for v in confirmed) or \
                    len(set(confirmed)) != len(confirmed) or not set(confirmed) <= set(assigned):
                raise ValueError("Reviewed occurrence IDs must be a unique subset of the assigned IDs")
            before = graph
            package, result = apply_canonical_proposal(_package(graph, documents), response,
                                                       assigned_occurrence_ids=assigned)
            graph = _restore_graph(package)
            failed_owners = set()
            for row in result["items"]:
                if row.get("status") == "rejected":
                    owners = _operation_owners(before, row.get("operation")) & set(assigned)
                    failed_owners.update(owners or assigned)
                elif row.get("status") == "needs_review":
                    failed_owners.add(row["occurrence_id"])
            confirmed = set(confirmed) - failed_owners
            # A structurally complete model response is not a reusable accepted
            # decision when its operations or coverage failed validation.
            invalidate = set(assigned) - confirmed
            for cache_key, owners in list(audit.get("response_cache_scopes", {}).items()):
                if set(owners) & invalidate:
                    audit["response_cache"].pop(cache_key, None)
            for row in audit["items"]:
                owners = _operation_owners(before, row.get("operation"))
                if row.get("occurrence_id"):
                    owners.add(row["occurrence_id"])
                if owners and owners <= confirmed:
                    row["resolved"] = True
            audit["items"].extend({"phase": name, **r} for r in result["items"])
            audit["reconciliation"] = [r for r in audit["reconciliation"] if not
                (r.get("status") == "unavailable" and set(r.get("assigned_occurrence_ids", [])) <= set(assigned))]
            audit["reconciliation"].append({"name": name, "status": "processed" if set(assigned) <= confirmed else "partial",
                "assigned_occurrence_ids": assigned, "reviewed_occurrence_ids": sorted(confirmed),
                "pending_occurrence_ids": sorted(set(assigned) - confirmed)})
        except (ValueError, RuntimeError, TimeoutError, ConnectionError) as exc:
            audit["status"] = "partial"
            audit["reconciliation"].append({"name": name, "status": "unavailable", "assigned_occurrence_ids": assigned,
                                              "error_type": type(exc).__name__, "error": str(exc)})
        persist(graph)
    _scope(graph, audit["items"])
    package = _package(graph, documents)
    audit["status"] = "completed"
    reviewed = {oid for row in audit["reconciliation"] for oid in row.get("reviewed_occurrence_ids", [])}
    pending_ids = sorted({o["event_id"] for o in graph["events"]} - reviewed)
    audit["pending_occurrence_ids"] = pending_ids
    audit["pending_source_chunks"] = [{"document_id": r["document_id"], "char_start": r["char_start"]}
                                       for r in audit["extraction"] if r["status"] != "processed"]
    if pending_ids or audit["pending_source_chunks"] or any(
            r.get("status") == "needs_review" and not r.get("resolved") for r in audit["items"]):
        audit["status"] = "partial"
    if not package["activity"]:
        audit["status"] = "no_usable_facts"
    audit["phase"] = "completed"
    audit["package_sha256"] = digest(package)
    audit["relevance_confirmed_occurrence_ids"] = [o["event_id"] for o in graph["events"]
        if _citations(o["subject_relevance"]) and "pending" not in str(_value(o["subject_relevance"])).casefold()
        and o["subject_relevance"].get("evidence_status") != "needs_review"]
    save(package, "PersonCanonicalFacts")
    save(audit, "PersonCanonicalAudit")
    return package, audit
