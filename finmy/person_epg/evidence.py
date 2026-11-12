"""Source-bound evidence support reused from Hu's native Person EPG pipeline."""
import copy
import math
import re
from types import SimpleNamespace
from finmy.builder.sparse_build.grounding import SourceIndex

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
