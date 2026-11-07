"""Regenerate schema.json and mysql.sql from schema_model.json. No database access."""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def render_sql(model):
    tables = {table["name"]: table for table in model["tables"]}

    def names(columns):
        return ", ".join("`" + name + "`" for name in columns)

    lines = [
        "-- Person EPG 3.0. Fresh schema only; existing databases require a separate migration.",
        "-- MySQL 8.0.17+; InnoDB; generated from schema_model.json.",
        "-- Apply to an empty, already-selected schema. No DROP statements.",
        "-- Foreign keys are added after table creation to permit declared reference cycles.",
        "",
    ]
    for table in model["tables"]:
        rows = []
        for column in table["columns"]:
            row = "`" + column["name"] + "` " + column["type"]
            row += " NULL" if column["nullable"] else " NOT NULL"
            if column.get("auto_increment"):
                row += " AUTO_INCREMENT"
            if "default" in column:
                row += " DEFAULT " + column["default"]
            rows.append(row)
        pk = [column["name"] for column in table["columns"] if column["pk"]]
        rows.append("PRIMARY KEY (" + names(pk) + ")")
        rows.extend(table["constraints"])
        lines.append("-- " + table["description"])
        lines.append(
            "CREATE TABLE `"
            + table["name"]
            + "` (\n  "
            + ",\n  ".join(rows)
            + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;\n"
        )

    for index, relation in enumerate(model["relationships"], 1):
        child, parent = relation["child"], relation["parent"]
        for name in relation["child_columns"]:
            assert name in {col["name"] for col in tables[child]["columns"]}
        for name in relation["parent_columns"]:
            assert name in {col["name"] for col in tables[parent]["columns"]}
        assert len(relation["child_columns"]) == len(relation["parent_columns"])
        lines.append(
            "ALTER TABLE `"
            + child
            + "` ADD CONSTRAINT `fk_"
            + str(index).zfill(2)
            + "_"
            + child
            + "`"
        )
        lines.append(
            "  FOREIGN KEY ("
            + names(relation["child_columns"])
            + ") REFERENCES `"
            + parent
            + "` ("
            + names(relation["parent_columns"])
            + ")"
        )
        lines.append(";")
    for view in model.get("views", []):
        lines.append("")
        lines.append("-- " + view["description"])
        lines.append("CREATE VIEW `" + view["name"] + "` AS\n" + view["sql"] + ";")
    lines.append("")
    return "\n".join(lines)


def render_json_schema(m):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:finmycelium:person-epg:3.0",
        "title": "Person EPG 3.0 relational interchange",
        "type": "object",
        "additionalProperties": False,
        "properties": {"schema_version": {"const": "person-epg-3.0"}},
        "$defs": {},
    }
    for t in m["tables"]:
        props = {}
        required = []
        for c in t["columns"]:
            n = c["name"]
            if n == "graph_id" and t["name"] != "subject_graph":
                continue
            typ = c["type"]
            if typ == "JSON":
                p = {}
            elif typ == "BOOLEAN":
                p = {"type": "boolean"}
            elif "INT" in typ:
                p = {"type": "integer", **({"minimum": 0} if "UNSIGNED" in typ else {})}
            elif typ == "DATETIME(6)":
                p = {
                    "type": "string",
                    "pattern": (
                        r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                        r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$"
                    ),
                    "description": "ISO datetime with timezone and at most six fractional digits; stored as UTC DATETIME(6).",
                }
            else:
                p = {"type": "string"}
            mm = re.match(r"VARCHAR\((\d+)\)", typ)
            if mm:
                p["maxLength"] = int(mm[1])
            if not c["nullable"]:
                required.append(n)
            if c["nullable"] and p:
                p = {"anyOf": [p, {"type": "null"}]}
            props[n] = p
        d = {
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": False,
        }
        schema["$defs"][t["name"]] = d
        if t["name"] == "subject_graph":
            schema["properties"]["graph"] = {"$ref": "#/$defs/subject_graph"}
        else:
            schema["properties"][t["name"]] = {
                "type": "array",
                "items": {"$ref": "#/$defs/" + t["name"]},
            }
    schema["required"] = list(schema["properties"])
    schema["$defs"]["subject_graph"]["properties"]["subject_type"] = {
        "const": "individual"
    }
    schema["$defs"]["event_activity"]["properties"]["detail_mode"] = {
        "enum": ["all", "selected"]
    }
    schema["$defs"]["activity"]["oneOf"] = []
    for n in ["action_id", "transaction_id", "context_occurrence_id"]:
        schema["$defs"]["activity"]["oneOf"].append(
            {
                "required": [n],
                "properties": {
                    f: (
                        {"type": "string", "minLength": 1}
                        if f == n
                        else {"type": "null"}
                    )
                    for f in ["action_id", "transaction_id", "context_occurrence_id"]
                },
            }
        )
    schema["$defs"]["activity_relation"]["properties"]["relation_type"] = {
        "enum": [
            "precedes",
            "overlaps",
            "executed_by",
            "explains",
            "responds_to",
            "context_for",
        ]
    }
    schema["$defs"]["activity_relation"]["properties"]["basis"] = {
        "enum": ["source", "inferred", "temporal"]
    }
    schema["$defs"]["time_value"]["properties"]["window_semantics"] = {
        "enum": ["uncertainty", "duration", None]
    }

    def nullable_group(names):
        return {
            "oneOf": [
                {"properties": {n: {"type": "null"} for n in names}},
                {
                    "required": names,
                    "properties": {n: {"not": {"type": "null"}} for n in names},
                },
            ]
        }

    schema["$defs"]["time_value"]["allOf"] = [
        nullable_group(
            ["window_start", "window_end", "original_text", "is_approximate"]
        ),
        {
            "if": {
                "required": ["window_semantics"],
                "properties": {"window_semantics": {"type": "string"}},
            },
            "then": {
                "required": ["window_start"],
                "properties": {"window_start": {"type": "string"}},
            },
        },
    ]
    schema["$defs"]["evidence_span"]["allOf"] = [
        nullable_group(["document_id", "char_start", "char_end"])
    ]
    schema["$defs"]["activity_relation"]["allOf"] = [
        {
            "if": {
                "properties": {
                    "relation_type": {"not": {"enum": ["precedes", "overlaps"]}}
                }
            },
            "then": {
                "required": ["evidence_set_id"],
                "properties": {"evidence_set_id": {"type": "string", "minLength": 1}},
            },
        },
        {
            "if": {"properties": {"basis": {"const": "temporal"}}},
            "then": {
                "properties": {"relation_type": {"enum": ["precedes", "overlaps"]}}
            },
        },
    ]
    return schema


def main():
    model = json.loads((HERE / "schema_model.json").read_text(encoding="utf-8"))
    (HERE / "mysql.sql").write_text(render_sql(model), encoding="utf-8")
    (HERE / "schema.json").write_text(
        json.dumps(render_json_schema(model), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
