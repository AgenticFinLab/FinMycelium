"""Read-only replay of pre-canonical PersonFactRepair artifacts.

The live Person builder does not execute a second fact repair pass. These
operations exist only to reproduce already paid-for legacy checkpoint changes
before importing them into canonical fact construction.
"""
import copy

from finmy.person_epg.sparse_adapter import add_evidence
from finmy.person_epg.validation import validate_person_epg
from .runtime import digest

def activity_fact(package, aid):
    a = next(r for r in package["activity"] if r["activity_id"] == aid)
    if a.get("action_id"):
        return "action", next(r for r in package["action"] if r["action_id"] == a["action_id"])
    if a.get("transaction_id"):
        return "financial_transaction", next(r for r in package["financial_transaction"]
                                             if r["transaction_id"] == a["transaction_id"])
    raise ValueError("Context is not an action or transaction")


def evidence_fields(package, set_id):
    spans = {s["span_id"]: s["quote"] for s in package["evidence_span"]}
    result = {}
    for link in package["evidence_link"]:
        if link["evidence_set_id"] == set_id:
            result.setdefault(link["field_path"], []).append(spans[link["span_id"]])
    return result


def merge_evidence(package, target, source, remap=None):
    fields = evidence_fields(package, target)
    for path, quotes in evidence_fields(package, source).items():
        path = (remap or {}).get(path, path)
        fields.setdefault(path, []).extend(quotes)
    add_evidence(package, {path: {"value": "merged evidence",
        "evidence_source_contents": list(dict.fromkeys(quotes)),
        "reasons": ["Evidence retained from canonicalized duplicate fact."]}
        for path, quotes in fields.items()}, evidence_set_id=target)


def _edit(package, row, table, op):
    field, value = op["field"], op["value"]
    if not isinstance(field, str):
        raise ValueError("Edit field must be a string")
    vf = {"value": value if value is not None else "unknown",
          "evidence_source_contents": op["quotes"], "reasons": [op["reason"]]}
    if field == "timestamp":
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Time must preserve a textual value")
        used = {t["time_id"] for t in package["time_value"]}
        n = len(used) + 1
        while f"REPAIR_TIME_{n}" in used:
            n += 1
        tid = f"REPAIR_TIME_{n}"
        package["time_value"].append({"time_id": tid, "value": value})
        row["timestamp_time_id"] = tid
        add_evidence(package, {"/timestamp": vf}, evidence_set_id=row["evidence_set_id"])
    elif field.startswith("detail:"):
        index = int(field.split(":")[1])
        if not isinstance(value, str) or not value.strip() or index < 0:
            raise ValueError("Invalid detail edit")
        if table == "action":
            detail = next(d for d in package["activity_detail"]
                          if d["activity_id"] == op["activity_id"] and d["detail_index"] == index)
            detail["value"] = value
            add_evidence(package, {"/value": vf}, evidence_set_id=detail["evidence_set_id"])
        else:
            row["details"][index] = value
            add_evidence(package, {f"/details/{index}": vf}, evidence_set_id=row["evidence_set_id"])
    else:
        allowed = {"actor_id", "action_type"} if table == "action" else {"from_entity_id", "to_entity_id", "name"}
        if field not in allowed:
            raise ValueError("Unsupported fact field")
        if field.endswith("_id"):
            if value not in {e["entity_id"] for e in package["entity"]} and not (
                table == "financial_transaction" and value is None):
                raise ValueError("Unknown actor")
        elif not isinstance(value, str) or not value.strip():
            raise ValueError("Invalid fact text")
        row[field] = value
        add_evidence(package, {"/" + field: vf}, evidence_set_id=row["evidence_set_id"])


def _remove(package, aid, table, row):
    package["activity"] = [a for a in package["activity"] if a["activity_id"] != aid]
    key = "action_id" if table == "action" else "transaction_id"
    package[table] = [r for r in package[table] if r[key] != row[key]]
    package["activity_detail"] = [d for d in package["activity_detail"] if d["activity_id"] != aid]
    if table == "financial_transaction":
        package["transaction_instrument"] = [r for r in package["transaction_instrument"]
                                            if r["transaction_id"] != row["transaction_id"]]


def apply_operation(package, op, assigned):
    """One transactional operation; old values remain in the saved input/audit."""
    if not isinstance(op, dict):
        raise ValueError("Repair operation must be an object")
    if op.get("activity_id") not in assigned:
        raise ValueError("Operation is outside assigned activities")
    quotes = op.get("quotes")
    if not isinstance(quotes, list) or not quotes or not isinstance(op.get("reason"), str) or not op["reason"].strip():
        raise ValueError("Operation needs support and reason")
    sources = [s["content"] for s in package["source_document"]]
    if any(not isinstance(q, str) or not q.strip() or not any(q in s for s in sources) for q in quotes):
        raise ValueError("Quote not found in original sources")
    candidate = copy.deepcopy(package)
    table, row = activity_fact(candidate, op["activity_id"])
    if op["op"] == "edit":
        _edit(candidate, row, table, op)
    elif op["op"] == "merge":
        if op["keep_id"] == op["activity_id"]:
            raise ValueError("Cannot merge into self")
        other_table, target = activity_fact(candidate, op["keep_id"])
        if other_table != table:
            raise ValueError("Cannot merge an action and a transaction")
        # Do not silently choose between conflicting actors; explicit edits can
        # fix misattribution first. Dates may differ in precision or be unknown.
        keys = ("actor_id",) if table == "action" else ("from_entity_id", "to_entity_id")
        if any(row.get(k) != target.get(k) for k in keys):
            raise ValueError("Correct conflicting actors before merging")
        remap = {}
        if table == "financial_transaction":
            details = target.setdefault("details", [])
            for i, value in enumerate(row.get("details", [])):
                if value not in details:
                    details.append(value)
                remap[f"/details/{i}"] = f"/details/{details.index(value)}"
            existing = [r for r in candidate["transaction_instrument"] if r["transaction_id"] == target["transaction_id"]]
            for inst in list(candidate["transaction_instrument"]):
                if inst["transaction_id"] == row["transaction_id"]:
                    same = next((r for r in existing if r["description"] == inst["description"]), None)
                    if same:
                        merge_evidence(candidate, same["evidence_set_id"], inst["evidence_set_id"])
                    else:
                        new = copy.deepcopy(inst)
                        new.update(transaction_id=target["transaction_id"], ordinal=max(
                            [r["ordinal"] for r in existing], default=-1) + 1)
                        existing.append(new)
                        candidate["transaction_instrument"].append(new)
        else:
            existing = [d for d in candidate["activity_detail"] if d["activity_id"] == op["keep_id"]]
            for detail in list(candidate["activity_detail"]):
                if detail["activity_id"] != op["activity_id"]:
                    continue
                same = next((d for d in existing if d["value"] == detail["value"]), None)
                if same:
                    merge_evidence(candidate, same["evidence_set_id"], detail["evidence_set_id"])
                else:
                    new = copy.deepcopy(detail)
                    new.update(activity_id=op["keep_id"], detail_index=max(
                        [d["detail_index"] for d in existing], default=-1) + 1)
                    existing.append(new)
                    candidate["activity_detail"].append(new)
        merge_evidence(candidate, target["evidence_set_id"], row["evidence_set_id"], remap)
        _remove(candidate, op["activity_id"], table, row)
    elif op["op"] == "covered_by":
        ids = op["keep_ids"]
        if table != "financial_transaction" or not ids or op["activity_id"] in ids:
            raise ValueError("Invalid aggregate replacement")
        for aid in ids:
            kind, component = activity_fact(candidate, aid)
            if kind != table or component["from_entity_id"] != row["from_entity_id"]:
                raise ValueError("Invalid aggregate component")
        _remove(candidate, op["activity_id"], table, row)
    else:
        raise ValueError("Unknown repair operation")
    valid = validate_person_epg(candidate)
    if not valid["valid"]:
        raise ValueError("Repair violates person schema: " + str(valid["errors"][:2]))
    return candidate


def replay_facts(package, artifact):
    if artifact.get("input_sha256") != digest(package):
        raise ValueError("Fact repair input differs from replayed facts")
    result = copy.deepcopy(package)
    for row in artifact["audit"]:
        if row.get("status") == "applied":
            op = row["operation"]
            result = apply_operation(result, op, [op["activity_id"]])
    if result != artifact["package"]:
        raise ValueError("Fact repair replay differs from saved package")
    return result
