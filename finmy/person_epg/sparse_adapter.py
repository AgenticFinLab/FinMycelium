"""Deterministic Sparse EventCascade facts and evidence in the unchanged Person EPG.

Organization is deliberately separate. This module never guesses personal roles,
decisions, stage memberships or activity links, and never rewrites source text.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from types import SimpleNamespace

from finmy.builder.sparse_build.grounding import SourceIndex

from .adapter import _Converter
from .validation import validate_person_epg


def _value(field):
    return field.get("value") if isinstance(field, dict) else field


def _vf(value=None, *, reason="Not supplied in the source result."):
    if isinstance(value, dict):
        result = copy.deepcopy(value)
        if not isinstance(result.get("value"), str):
            raise ValueError("A verifiable field must contain a string value")
        result.setdefault("evidence_source_contents", [])
        result.setdefault("reasons", [])
    else:
        if value is not None and not isinstance(value, str):
            raise ValueError("A verifiable field must be a string, object or null")
        result = {"value": value if value is not None else "unknown",
                  "evidence_source_contents": [], "reasons": [reason]}
    for key in ("evidence_source_contents", "reasons"):
        if not isinstance(result[key], list) or any(not isinstance(x, str) for x in result[key]):
            raise ValueError(f"{key} must be a list of strings")
    if any(not quote.strip() for quote in result["evidence_source_contents"]):
        raise ValueError("Evidence quotations must not be empty")
    confidence = result.get("confidence")
    if confidence is not None and (
        type(confidence) not in (int, float) or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        raise ValueError("confidence must be null or a finite number in [0, 1]")
    return result


def _normalized(text):
    return " ".join(str(text or "").split()).casefold()


def _unknown(value):
    return _normalized(_value(value)) in {"", "unknown", "unspecified", "none", "null", "n/a"}


def _merge_same_field(left, right):
    """Merge evidence for identical values; original assertions stay in traces."""
    result = copy.deepcopy(left)
    for key in ("evidence_source_contents", "reasons"):
        result[key] = list(dict.fromkeys(left.get(key, []) + right.get(key, [])))
    confidences = [x.get("confidence") for x in (left, right) if x.get("confidence") is not None]
    if confidences:
        result["confidence"] = min(confidences)
    if any(x.get("evidence_status") == "needs_review" for x in (left, right)):
        result["evidence_status"] = "needs_review"
    return result


def _next_id(rows, key, prefix):
    used = {row[key] for row in rows}
    number = len(used) + 1
    while f"{prefix}{number:05d}" in used:
        number += 1
    return f"{prefix}{number:05d}"


def add_evidence(package, fields, *, evidence_set_id=None):
    """Attach local-pointer VFs, optionally replacing paths in an existing set.

    Only the specified paths are replaced. Unrelated field evidence is retained.
    Source resolution is a separate final assembly step.
    """
    prepared = {}
    for path, value in fields.items():
        if not isinstance(path, str) or not path.startswith("/") or re.search(r"~(?![01])", path):
            raise ValueError("Evidence field paths must be escaped local JSON Pointers")
        prepared[path] = _vf(value)
    if evidence_set_id is None:
        evidence_set_id = _next_id(package["evidence_set"], "evidence_set_id", "PERSON_ES_")
        record = {"evidence_set_id": evidence_set_id, "field_metadata": {}}
        package["evidence_set"].append(record)
    else:
        record = next((r for r in package["evidence_set"] if r["evidence_set_id"] == evidence_set_id), None)
        if record is None:
            raise ValueError(f"Unknown evidence set: {evidence_set_id}")
        record["field_metadata"] = record.get("field_metadata") or {}
    old_spans = {r["span_id"] for r in package["evidence_link"]
                 if r["evidence_set_id"] == evidence_set_id and r["field_path"] in prepared}
    package["evidence_link"] = [r for r in package["evidence_link"]
                                if not (r["evidence_set_id"] == evidence_set_id and r["field_path"] in prepared)]
    linked = {r["span_id"] for r in package["evidence_link"]}
    package["evidence_span"] = [r for r in package["evidence_span"]
                                if r["span_id"] not in old_spans or r["span_id"] in linked]
    for path, field in prepared.items():
        record["field_metadata"][path] = {k: copy.deepcopy(v) for k, v in field.items()
                                          if k not in {"value", "evidence_source_contents"}}
        for index, quote in enumerate(field["evidence_source_contents"]):
            span_id = _next_id(package["evidence_span"], "span_id", "PERSON_SPAN_")
            package["evidence_span"].append({"span_id": span_id, "document_id": None,
                                              "char_start": None, "char_end": None, "quote": quote})
            package["evidence_link"].append({"evidence_set_id": evidence_set_id, "field_path": path,
                                              "quote_order": index, "span_id": span_id})
    return evidence_set_id


def build_person_facts(cascade, build_input, subject):
    """Return a schema-valid, unorganized factual package and mapping diagnostics.

    An Episode is a scene candidate. Its relation to the person remains explicitly
    pending until the organizer supplies evidence. IDs are stable for replay of
    the same saved result, not an automatic cross-run entity matching claim.
    """
    report = {"contract_version": 1, "entity_map": {}, "occurrence_map": [],
              "field_map": [], "retained_in_sparse_result": [], "attribute_conflicts": [],
              "source_map": [], "semantic_support_checked": False}
    source_fields = []

    def mapped(source_path, table, key, pointer):
        source_fields.append({"source_path": source_path, "table": table,
                              "record_key": key, "field_path": pointer})

    subject_id, subject_name = subject["subject_id"], subject["name"]
    aliases = list(dict.fromkeys([subject_name, *subject.get("aliases", [])]))
    subject_names = {_normalized(name) for name in aliases}
    participants = [(si, ei, pi, p) for si, stage in enumerate(cascade.get("stages", []))
                    for ei, ep in enumerate(stage.get("episodes", []))
                    for pi, p in enumerate(ep.get("participants", []))]
    matches = {p["participant_id"] for _, _, _, p in participants
               if _normalized(_value(p.get("name"))) in subject_names}
    if len(matches) > 1:
        raise ValueError("Ambiguous subject identity: multiple participant IDs match the configured person")
    known = {}
    for si, ei, pi, participant in participants:
        pid = participant["participant_id"]
        eid = subject_id if pid in matches else f"entity:{pid}"
        if eid == subject_id and pid not in matches:
            raise ValueError("Subject ID collides with a different entity")
        report["entity_map"][pid] = eid
        name, kind = _vf(participant.get("name")), _value(participant.get("participant_type")) or "unknown"
        if pid in matches:
            if kind not in ("individual", "person", "unknown"):
                raise ValueError("Configured person matches a non-individual participant")
            kind = "individual"
        attrs = {k: _vf(v) for k, v in (participant.get("attributes") or {}).items()}
        if eid not in known:
            known[eid] = {"entity_id": eid, "name": name, "entity_type": kind,
                          "attributes": attrs, "aliases": aliases if pid in matches else []}
        else:
            entity = known[eid]
            if _unknown(entity["name"]):
                entity["name"] = name
            elif not _unknown(name) and _normalized(name["value"]) != _normalized(entity["name"]["value"]):
                raise ValueError(f"Participant identity drift: {pid}.name")
            else:
                entity["name"] = _merge_same_field(entity["name"], name)
            if entity["entity_type"] == "unknown":
                entity["entity_type"] = kind
            elif kind != "unknown" and entity["entity_type"] != kind:
                raise ValueError(f"Participant identity drift: {pid}.participant_type")
            for key, value in attrs.items():
                if key not in entity["attributes"]:
                    entity["attributes"][key] = value
                elif _value(entity["attributes"][key]) == _value(value):
                    entity["attributes"][key] = _merge_same_field(entity["attributes"][key], value)
                else:
                    report["attribute_conflicts"].append({"entity_id": eid, "attribute": key,
                        "previous": copy.deepcopy(entity["attributes"][key]), "candidate": value})
                    entity["attributes"][key] = _vf(None, reason="Conflicting attributes retained in the mapping report.")
        base = f"event.stages[{si}].episodes[{ei}].participants[{pi}]"
        mapped(base + ".name", "entity", {"entity_id": eid}, "/name")
        for key in attrs:
            mapped(base + ".attributes." + key, "entity", {"entity_id": eid},
                   "/attributes/" + key.replace("~", "~0").replace("/", "~1"))
        if isinstance(participant.get("participant_type"), dict):
            report["retained_in_sparse_result"].append({"source_path": base + ".participant_type",
                "reason": "Entity type is structural; original type evidence remains in the Sparse result."})
    if subject_id not in known:
        known = {subject_id: {"entity_id": subject_id,
                 "name": _vf(subject_name, reason="Configured focal person; task metadata, not source evidence."),
                 "entity_type": "individual", "attributes": {}, "aliases": aliases}, **known}
    fingerprint = json.dumps({"subject": subject, "event_id": cascade.get("event_id"),
        "samples": [{"sample_id": s.sample_id, "raw_data_id": s.raw_data_id,
                     "content": s.content} for s in build_input.samples]},
        ensure_ascii=False, sort_keys=True).encode("utf-8")
    graph = {"schema_version": "subject-graph-1.0",
             "graph_id": "SG_SPARSE_" + hashlib.sha256(fingerprint).hexdigest()[:20],
             "subject_id": subject_id, "subject_type": "individual",
             "coverage_start": subject.get("coverage_start"), "coverage_end": subject.get("coverage_end"),
             "title": _vf(cascade.get("title")),
             "descriptions": [_vf(x) for x in cascade.get("descriptions", []) or []],
             "entities": list(known.values()), "events": [], "relations": []}
    mapped("event.title", "subject_graph", {"graph_id": graph["graph_id"]}, "/title")
    for di, _ in enumerate(graph["descriptions"]):
        mapped(f"event.descriptions[{di}]", "subject_graph", {"graph_id": graph["graph_id"]}, f"/descriptions/{di}")
    for si, stage in enumerate(cascade.get("stages", [])):
        for ei, episode in enumerate(stage.get("episodes", [])):
            oid = f"O_S{si + 1}_E{ei + 1}"
            base = f"event.stages[{si}].episodes[{ei}]"
            locator = {"stage_index": si, "episode_index": ei,
                       "stage_id": stage["stage_id"], "episode_id": episode["episode_id"]}
            report["occurrence_map"].append({**locator, "occurrence_id": oid})
            occurrence = {"event_id": oid, "title": _vf(episode.get("name")),
                          "start_time": _vf(episode.get("start_time")), "end_time": _vf(episode.get("end_time")),
                          "subject_relevance": {**_vf("Pending person organization review.",
                            reason="Scene candidate from Sparse reconstruction; relevance is not yet established."),
                            "evidence_status": "needs_review"},
                          "descriptions": [_vf(x) for x in episode.get("descriptions", []) or []],
                          "participations": [], "actions": [], "transactions": []}
            for old, target in (("name", "title"), ("start_time", "start_time"), ("end_time", "end_time")):
                mapped(base + "." + old, "occurrence", {"occurrence_id": oid}, "/" + target)
            for di, _ in enumerate(occurrence["descriptions"]):
                mapped(base + f".descriptions[{di}]", "occurrence", {"occurrence_id": oid}, f"/descriptions/{di}")
            member_ids = {p["participant_id"] for p in episode.get("participants", [])}

            def endpoint(value, *, allow_unknown=False):
                field = _vf(value)
                if allow_unknown and _unknown(field):
                    field["value"] = "unknown"
                else:
                    if field["value"] not in member_ids:
                        raise ValueError(f"{oid}: dangling participant endpoint {field['value']!r}")
                    field["value"] = report["entity_map"][field["value"]]
                return field

            for pi, participant in enumerate(episode.get("participants", [])):
                eid = report["entity_map"][participant["participant_id"]]
                part_id = f"PAR_{oid}_{pi + 1}"
                part = {"participation_id": part_id, "entity_id": eid,
                        "role": _vf(participant.get("base_role")),
                        "start_time": _vf(None), "end_time": _vf(None)}
                occurrence["participations"].append(part)
                pbase = base + f".participants[{pi}]"
                mapped(pbase + ".base_role", "participation", {"participation_id": part_id}, "/role")
                for ai, action in enumerate(participant.get("actions", []) or []):
                    aid = f"ACT_{oid}_P{pi + 1}_{ai + 1}"
                    occurrence["actions"].append({"action_id": aid, "actor_id": eid,
                        "action_type": _vf(action.get("name")), "timestamp": _vf(action.get("timestamp")),
                        "details": [_vf(d) for d in action.get("details", []) or []]})
                    abase = pbase + f".actions[{ai}]"
                    mapped(abase + ".name", "action", {"action_id": aid}, "/action_type")
                    mapped(abase + ".timestamp", "action", {"action_id": aid}, "/timestamp")
                    for di, _ in enumerate(action.get("details", []) or []):
                        mapped(abase + f".details[{di}]", "activity_detail",
                               {"activity_id": "A:" + aid, "detail_index": di}, "/value")
            for ti, transaction in enumerate(episode.get("transactions", []) or []):
                tid, tbase = f"TX_{oid}_{ti + 1}", base + f".transactions[{ti}]"
                occurrence["transactions"].append({"transaction_id": tid, "name": _vf(transaction.get("name")),
                    "from_entity_id": endpoint(transaction.get("from_participant_id"), allow_unknown=True),
                    "to_entity_id": endpoint(transaction.get("to_participant_id"), allow_unknown=True),
                    "timestamp": _vf(transaction.get("timestamp")),
                    "details": [_vf(d) for d in transaction.get("details", []) or []],
                    "instruments": [_vf(d) for d in transaction.get("instruments", []) or []]})
                for old, target in (("name", "name"), ("timestamp", "timestamp"),
                                    ("from_participant_id", "from_entity_id"), ("to_participant_id", "to_entity_id")):
                    mapped(tbase + "." + old, "financial_transaction", {"transaction_id": tid}, "/" + target)
                for di, _ in enumerate(transaction.get("details", []) or []):
                    mapped(tbase + f".details[{di}]", "financial_transaction", {"transaction_id": tid}, f"/details/{di}")
                for di, _ in enumerate(transaction.get("instruments", []) or []):
                    mapped(tbase + f".instruments[{di}]", "transaction_instrument",
                           {"transaction_id": tid, "ordinal": di}, "/description")
                if transaction.get("transaction_type") is not None:
                    report["retained_in_sparse_result"].append({"source_path": tbase + ".transaction_type",
                        "value": copy.deepcopy(transaction["transaction_type"]), "reason": "No equivalent target column."})
            for ri, relation in enumerate(episode.get("participant_relations", []) or []):
                rid, rbase = f"REL_{oid}_{ri + 1}", base + f".participant_relations[{ri}]"
                reltype = relation.get("relation_type")
                relation_source_key = "relation_type"
                if _unknown(reltype):
                    reltype = relation.get("relation_name")
                    relation_source_key = "relation_name"
                graph["relations"].append({"relation_id": rid,
                    "from_entity_id": endpoint(relation.get("from_participant_id"))["value"],
                    "to_entity_id": endpoint(relation.get("to_participant_id"))["value"],
                    "relation_type": _vf(reltype), "valid_from": _vf(relation.get("start_time")),
                    "valid_to": _vf(relation.get("end_time")), "event_ids": [oid]})
                for old, target in ((relation_source_key, "relation_type"), ("start_time", "valid_from"), ("end_time", "valid_to")):
                    mapped(rbase + "." + old, "entity_relation", {"relation_id": rid}, "/" + target)
                for key in ("relation_name", "descriptions"):
                    if relation.get(key) is not None:
                        report["retained_in_sparse_result"].append({"source_path": rbase + "." + key,
                            "value": copy.deepcopy(relation[key]), "reason": "No separate target column; raw relation preserved."})
            graph["events"].append(occurrence)
    # Reuse value/time/evidence and Activity serialization without forcing the
    # candidate graph through a semantic SubjectGraph acceptance decision.
    package = _Converter().convert(graph)
    registry = (getattr(build_input.user_query, "extras", None) or {}).get("source_registry", {})
    for i, sample in enumerate(build_input.samples):
        doc_id = f"DOC_{i + 1:05d}"
        metadata = registry.get(sample.raw_data_id, {}) if isinstance(registry, dict) else {}
        if not isinstance(metadata, dict):
            metadata = {}
        package["source_document"].append({"document_id": doc_id, "content": sample.content,
            "title": metadata.get("title"), "source_url": metadata.get("source_url", metadata.get("url")),
            "published_at": metadata.get("published_at")})
        report["source_map"].append({"document_id": doc_id, "sample_id": sample.sample_id,
            "raw_data_id": sample.raw_data_id, "source_sha256": hashlib.sha256(sample.content.encode("utf-8")).hexdigest(),
            "offset_origin": "sample.content"})
    for mapping in source_fields:
        rows = [package["graph"]] if mapping["table"] == "subject_graph" else package[mapping["table"]]
        row = next(r for r in rows if all(r.get(k) == v for k, v in mapping["record_key"].items()))
        mapping["evidence_set_id"] = row["evidence_set_id"]
        report["field_map"].append(mapping)
    report["retained_in_sparse_result"].extend([
        {"source_path": "event.event_type", "reason": "No equivalent person graph column."},
        {"source_path": "event.start_time", "reason": "Overall reconstruction boundary; factual times remain on occurrences and activities."},
        {"source_path": "event.end_time", "reason": "Overall reconstruction boundary; factual times remain on occurrences and activities."},
        {"source_path": "event.stages", "reason": "Original grouping and boundaries are organization candidates, not copied facts."}])
    validation = validate_person_epg(package)
    if not validation["valid"]:
        first = validation["errors"][0]
        raise ValueError(f"Invalid normalized Person EPG at {first['path']}: {first['message']}")
    return package, report


def ground_person_evidence(package):
    """Resolve quotes against stored source snapshots; preserve ambiguities.

    Mutates only evidence spans/links and review metadata. Existing valid anchors
    are kept, allowing replay and repeated validation without losing provenance.
    """
    docs = {d["document_id"]: d for d in package["source_document"]}
    index = SourceIndex([SimpleNamespace(sample_id=key, content=doc["content"]) for key, doc in docs.items()])
    sets = {r["evidence_set_id"]: r for r in package["evidence_set"]}
    outcomes, kept, remap, locations = {}, [], {}, {}
    for span in package["evidence_span"]:
        original = span["quote"]
        doc_id = span.get("document_id")
        if doc_id is not None:
            doc = docs.get(doc_id)
            start, end = span.get("char_start"), span.get("char_end")
            if (doc is None or type(start) is not int or type(end) is not int or start < 0
                    or end <= start or doc["content"][start:end] != original):
                raise ValueError(f"Invalid existing quote anchor: {span['span_id']}")
            anchors = [{"sample_id": doc_id, "start": start, "end": end,
                        "source_text": original, "method": "exact"}]
        else:
            anchors = index.locate(original)
        status = "ambiguous" if len(anchors) > 1 else "unresolved"
        if len(anchors) == 1:
            anchor = anchors[0]
            span.update(document_id=anchor["sample_id"], char_start=anchor["start"],
                        char_end=anchor["end"], quote=anchor["source_text"])
            status = anchor["method"]
        else:
            span.update(document_id=None, char_start=None, char_end=None)
        outcomes[span["span_id"]] = {"status": status, "original_quote": original, "anchors": anchors}
        location = (span.get("document_id"), span.get("char_start"), span.get("char_end"))
        if location[0] is not None and location in locations:
            remap[span["span_id"]] = locations[location]
        else:
            kept.append(span)
            if location[0] is not None:
                locations[location] = span["span_id"]
    links = []
    for link in package["evidence_link"]:
        old_id = link["span_id"]
        outcome = outcomes[old_id]
        if outcome["status"] in {"ambiguous", "unresolved"}:
            meta = sets[link["evidence_set_id"]].setdefault("field_metadata", {})
            if meta is None:
                meta = sets[link["evidence_set_id"]]["field_metadata"] = {}
            meta.setdefault(link["field_path"], {})["evidence_status"] = "needs_review"
        link["span_id"] = remap.get(old_id, old_id)
        links.append({**copy.deepcopy(link), **outcome})
    package["evidence_span"] = kept
    matched_fields = {(x["evidence_set_id"], x["field_path"]) for x in package["evidence_link"]}
    missing = [{"evidence_set_id": sid, "field_path": path} for sid, record in sets.items()
               for path in (record.get("field_metadata") or {}) if (sid, path) not in matched_fields]
    counts = {status: sum(x["status"] == status for x in links)
              for status in ("exact", "whitespace", "ambiguous", "unresolved")}
    return {"contract_version": 1, "method": "unique_exact_or_whitespace_with_offsets",
            "offset_unit": "unicode_codepoint", "offset_end": "exclusive",
            "semantic_support_checked": False, "quote_count": len(links),
            "unmatched_quote_count": counts["ambiguous"] + counts["unresolved"],
            "match_counts": counts, "fields_without_quotes": missing, "links": links}
