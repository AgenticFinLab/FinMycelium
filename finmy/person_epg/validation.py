"""Validate the Person EPG interchange without a running database.

JSON Schema checks row shapes; the shared relational model supplies keys and
foreign keys. The remaining checks concern final graph identity and evidence
references. This validator never repairs data or judges source entailment.
"""

from datetime import date, datetime, timezone
import re

from jsonschema import Draft202012Validator

from .schema import JSON_SCHEMA, MODEL


def _pointer(parts):
    return "".join(
        "/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts
    )


def _table_rows(package, table):
    if table == "subject_graph":
        return [("/graph", package["graph"])]
    return [
        (f"/{table}/{index}", {"graph_id": package["graph"]["graph_id"], **row})
        for index, row in enumerate(package[table])
    ]


def _keys(table):
    yield "primary key", [column["name"] for column in table["columns"] if column["pk"]]
    for constraint in table.get("constraints", []):
        match = re.search(r"\bUNIQUE\s*\(([^)]+)\)", constraint)
        if match:
            yield "unique key", [
                name.strip().strip("`") for name in match[1].split(",")
            ]


def _check_relations(rows, add_error):
    """Check every declared PK/UNIQUE/FK, with MySQL nullable-key semantics."""
    for table in MODEL["tables"]:
        for kind, columns in _keys(table):
            seen = set()
            for path, row in rows[table["name"]]:
                key = tuple(row.get(column) for column in columns)
                if kind == "unique key" and None in key:
                    continue
                if key in seen:
                    add_error(path, f"Duplicate {kind} ({', '.join(columns)}): {key!r}")
                seen.add(key)

    for relation in MODEL["relationships"]:
        parent_columns = relation["parent_columns"]
        targets = {
            tuple(row.get(column) for column in parent_columns)
            for _, row in rows[relation["parent"]]
        }
        columns = relation["child_columns"]
        for path, row in rows[relation["child"]]:
            key = tuple(row.get(column) for column in columns)
            # MATCH SIMPLE: any NULL component makes the composite FK optional.
            if None not in key and key not in targets:
                add_error(
                    path + "/" + columns[-1],
                    f"Foreign key ({', '.join(columns)}) must reference "
                    f"{relation['parent']} ({', '.join(parent_columns)}): {key!r}",
                )


def _check_evidence(package, add_error):
    documents = {row["document_id"]: row for row in package["source_document"]}
    supported_sets = {row["evidence_set_id"] for row in package["evidence_link"]}
    for index, span in enumerate(package["evidence_span"]):
        if span.get("document_id") is None:
            continue
        start, end = span["char_start"], span["char_end"]
        path = f"/evidence_span/{index}"
        if end <= start:
            add_error(
                path + "/char_end", "Quote offsets must satisfy char_start < char_end."
            )
        document = documents.get(span["document_id"])
        if document and (
            end > len(document["content"])
            or document["content"][start:end] != span["quote"]
        ):
            add_error(
                path + "/quote",
                "Quote differs from the source's Unicode character span.",
            )
    for index, link in enumerate(package["activity_relation"]):
        path = f"/activity_relation/{index}"
        if link["from_activity_id"] == link["to_activity_id"]:
            add_error(path, "An activity relation must have distinct endpoints.")
        if (
            link["relation_type"] not in ("precedes", "overlaps")
            and link.get("evidence_set_id") not in supported_sets
        ):
            add_error(
                path + "/evidence_set_id",
                "A semantic activity relation requires an evidence set containing quotes.",
            )


def _check_semantics(package, add_error):
    for index, document in enumerate(package["source_document"]):
        published_at = document.get("published_at")
        if published_at is None:
            continue
        try:
            instant = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            if instant.astimezone(timezone.utc).year < 1000:
                raise ValueError("Outside MySQL DATETIME range")
        except (ValueError, OverflowError):
            add_error(
                f"/source_document/{index}/published_at",
                "Publication datetime must be valid and fit MySQL DATETIME(6) after UTC conversion.",
            )

    entities = {row["entity_id"]: row for row in package["entity"]}
    focal = entities.get(package["graph"].get("subject_entity_id"))
    if focal is None or focal["entity_type"] != "individual":
        add_error(
            "/graph/subject_entity_id",
            "The completed graph must reference an existing individual.",
        )

    selections = {
        (row["event_id"], row["activity_id"])
        for row in package["event_activity_detail"]
    }
    for index, member in enumerate(package["event_activity"]):
        if (
            member["detail_mode"] == "all"
            and (member["event_id"], member["activity_id"]) in selections
        ):
            add_error(
                f"/event_activity/{index}/detail_mode",
                "Explicit detail selections require detail_mode='selected'.",
            )

    for index, value in enumerate(package["time_value"]):
        if value.get("window_start") is None:
            continue
        try:
            start, end = (
                date.fromisoformat(value[key]) for key in ("window_start", "window_end")
            )
            if any(
                parsed.isoformat() != value[key]
                for parsed, key in ((start, "window_start"), (end, "window_end"))
            ):
                raise ValueError("Noncanonical DATE")
        except ValueError:
            add_error(
                f"/time_value/{index}",
                "Time window endpoints must be valid YYYY-MM-DD dates.",
            )
            continue
        if start > end:
            add_error(
                f"/time_value/{index}/window_end", "Time window end precedes its start."
            )


def validate_person_epg(package, *, require_normalized_times=False):
    """Return ``{valid, errors}``; paths use JSON Pointer and input is unchanged.

    Shape errors are returned before relational checks, so malformed JSON values
    cannot leak Python indexing/type errors through the public interface.
    """
    if isinstance(package, dict) and package.get('schema_version') == 'person-event-1.0':
        from .event.validation import check_graph
        return check_graph(package)
    errors = [
        {"path": _pointer(error.absolute_path), "message": error.message}
        for error in Draft202012Validator(JSON_SCHEMA).iter_errors(package)
    ]
    if errors:
        return {"valid": False, "errors": errors}

    def add_error(path, message):
        errors.append({"path": path, "message": message})

    rows = {
        table["name"]: _table_rows(package, table["name"]) for table in MODEL["tables"]
    }
    _check_relations(rows, add_error)
    _check_evidence(package, add_error)
    _check_semantics(package, add_error)
    if require_normalized_times:
        from .time_utils import date_interval
        for index, time in enumerate(package["time_value"]):
            if time["value"] != "unknown" and date_interval(time["value"]) is None:
                add_error(f"/time_value/{index}/value",
                          "Normalize this expression under subject_graph/temporal_policy.py before writing canonical facts.")
    return {"valid": not errors, "errors": errors}
