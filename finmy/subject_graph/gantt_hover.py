"""Format native evidence fields inside existing Person Gantt hover labels."""
from html import escape, unescape
from textwrap import wrap


def hover_text(value):
    """Wrap plain or already escaped text without dropping source characters."""
    lines = wrap(unescape(str(value)), width=85, replace_whitespace=False,
                 drop_whitespace=False, break_on_hyphens=False)
    return "<br>".join(escape(line) for line in lines)


def field_hover(field, label=None, *, provenance=True):
    return fields_hover([field], label, provenance=provenance)


def fields_hover(fields, label=None, *, provenance=True):
    """Keep field values/statuses and share repeated evidence within one group."""
    fields = list(fields)
    if not fields:
        return ""
    lines = [f"<b>{hover_text(label)}</b>"] if label else []
    for field in fields:
        value = str(field["value"])
        if "confidence" in field:
            confidence = field["confidence"]
            value += " · Confidence: " + str("unknown" if confidence is None else confidence)
        value = hover_text(value)
        if field.get("evidence_status") == "needs_review":
            value = "<b>Needs review</b> — " + value
        lines.append(value)
        window = field.get("time_window")
        if window:
            original = window["original"] + ("（约）" if window["approximate"] else "")
            lines.append("Original time: " + hover_text(original))
            period = f"{window['start']} — {window['end']}"
            lines.append("Time window: " + hover_text(period)
                         + (" (approximate)" if window["approximate"] else ""))
            if window["approximate"]:
                lines.append("发生于该范围内，具体日期不详。")
    if provenance:
        lines.extend(_evidence_lines(fields))
    return "<br>".join(lines)


def _evidence_lines(fields):
    reasons, quotes = {}, {}
    for field in fields:
        for reason in field.get("reasons", []):
            reasons.setdefault(unescape(reason), None)
        for quote in field.get("evidence_source_contents", []):
            quotes.setdefault(unescape(quote), None)
    lines = []
    for heading, contents in (("Basis", reasons), ("Evidence", quotes)):
        if contents:
            lines.append(f"<b>{heading}</b>")
            lines.extend(hover_text(text) for text in contents)
    return lines


def provenance_hover(fields, label=None):
    """Show source material on an existing node, without repeating all values."""
    fields = list(fields)
    lines = [f"<b>{hover_text(label)}</b>"] if label else []
    lines.extend("<b>Needs review</b> — " + hover_text(field["value"])
                 for field in fields if field.get("evidence_status") == "needs_review")
    lines.extend(_evidence_lines(fields))
    return "<br>".join(lines)


def _labeled(field, label):
    return {**field, "value": f"{label}: {field['value']}"}


def _action_fields(action):
    return [_labeled(action["action_type"], "Action"),
            _labeled(action["timestamp"], "Time"), *action["details"]]


def _relation_fields(relation, names=None):
    relation_type = relation["relation_type"]
    if names is not None:
        source = names[relation["from_entity_id"]]
        target = names[relation["to_entity_id"]]
        relation_type = {**relation_type,
                         "value": f"{source} — {relation_type['value']} → {target}"}
    return [_labeled(relation_type, "Relation"),
            _labeled(relation["valid_from"], "Valid from"),
            _labeled(relation["valid_to"], "Valid to")]


def _event_fields(event):
    return [_labeled(event["title"], "Event"),
            _labeled(event["start_time"], "Start"),
            _labeled(event["end_time"], "End"),
            *event["descriptions"],
            _labeled(event["subject_relevance"], "Subject relevance")]


def _transaction_fields(transaction, names):
    fields = [_labeled(transaction["name"], "Transaction")]
    for side in ("from", "to"):
        party = transaction[side + "_entity_id"]
        fields.append(_labeled({**party, "value": names.get(party["value"], party["value"])},
                               side.capitalize()))
    fields.append(_labeled(transaction["timestamp"], "Time"))
    fields.extend(_labeled(instrument, "Instrument") for instrument in transaction["instruments"])
    fields.extend(transaction["details"])
    return fields


def event_hover(event):
    return fields_hover(_event_fields(event), provenance=False)


def episode_hover(metadata):
    kind = metadata["kind"]
    if kind == "context":
        return provenance_hover(_event_fields(metadata["event"]), "Event evidence")
    if kind == "action":
        return fields_hover(_action_fields(metadata["action"]), provenance=False)
    return fields_hover(_transaction_fields(metadata["transaction"], metadata["names"]),
                        provenance=not metadata.get("provenance_on_node", False))


def participant_hover(metadata):
    entity = metadata["entity"]
    fields = [_labeled(entity["name"], "Name"), {"value": f"Type: {entity['entity_type']}"}]
    if "actions" in metadata or "transaction" in metadata:
        fields.extend(_labeled(p["role"], "Role") for p in metadata["participations"])
        if "actions" in metadata:
            actions = metadata["actions"]
            fields.extend(_labeled(a["action_type"], "Action") for a in actions)
            evidence = [field for action in actions for field in _action_fields(action)]
        else:
            fields.append(_labeled(metadata["transaction"]["name"], "Transaction"))
            evidence = _transaction_fields(metadata["transaction"], metadata["names"])
        return fields_hover(fields, provenance=False) + "<br>" + provenance_hover(evidence)
    if entity["aliases"]:
        fields.append({"value": "Aliases: " + ", ".join(entity["aliases"])})
    fields.extend(_labeled(value, key) for key, value in entity["attributes"].items())
    fields.extend(metadata.get("overview", []))
    for participation in metadata["participations"]:
        fields.extend([_labeled(participation["role"], "Role"),
                       _labeled(participation["start_time"], "Participation start"),
                       _labeled(participation["end_time"], "Participation end")])
    if not metadata["participations"]:
        fields.append({"value": "Contextual entity"})
    # Context nodes summarize actions; their complete records belong to activity nodes.
    fields.extend({"value": f"Action: {name['value']}"} for name in metadata.get("action_names", []))
    for relation in metadata.get("global_relations", []):
        fields.extend(_relation_fields(relation, metadata["names"]))
    return fields_hover(fields)


def relation_hover(metadata):
    fields = _relation_fields(metadata["relation"])
    if metadata["contextual"]:
        fields.insert(0, {"value": "Contextual relation"})
    return fields_hover(fields)
