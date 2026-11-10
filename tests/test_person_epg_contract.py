"""Generated-contract consistency and relational execution of the example.

SQLite exercises relational semantics offline. It does not establish that the
MySQL-specific DDL has run successfully on a MySQL server.
"""

import json
from pathlib import Path
import sqlite3
import unittest

from finmy.person_epg.generate import render_json_schema, render_sql
from finmy.person_epg.schema import DIRECTORY, JSON_SCHEMA, MODEL
from finmy.person_epg.validation import validate_person_epg

EXAMPLE = (
    Path(__file__).resolve().parents[1] / "tests/fixtures/buffett_person_epg_preview.json"
)


def relational_mirror():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    for table in MODEL["tables"]:
        definitions = []
        for column in table["columns"]:
            sql_type = (
                "INTEGER"
                if "INT" in column["type"] or column["type"] == "BOOLEAN"
                else "TEXT"
            )
            definition = f'"{column["name"]}" {sql_type}'
            if not column["nullable"]:
                definition += " NOT NULL"
            if "default" in column:
                definition += " DEFAULT " + column["default"]
            if "UNSIGNED" in column["type"]:
                definition += f' CHECK ("{column["name"]}" >= 0)'
            definitions.append(definition)
        primary_key = ", ".join(
            column["name"] for column in table["columns"] if column["pk"]
        )
        definitions.append(f"PRIMARY KEY ({primary_key})")
        definitions.extend(table.get("constraints", []))
        for relation in MODEL["relationships"]:
            if relation["child"] == table["name"]:
                definitions.append(
                    f"FOREIGN KEY ({', '.join(relation['child_columns'])}) "
                    f"REFERENCES {relation['parent']} ({', '.join(relation['parent_columns'])}) "
                    "DEFERRABLE INITIALLY DEFERRED"
                )
        connection.execute(f"CREATE TABLE {table['name']} ({', '.join(definitions)})")
    for view in MODEL["views"]:
        connection.execute(f"CREATE VIEW {view['name']} AS {view['sql']}")
    return connection


def insert_row(connection, table, row):
    columns = list(row)
    values = [
        (
            json.dumps(value, ensure_ascii=False)
            if isinstance(value, (dict, list))
            else value
        )
        for value in row.values()
    ]
    connection.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        values,
    )


class PersonEPGContractTest(unittest.TestCase):
    def test_committed_contracts_match_their_source_model(self):
        self.assertEqual(JSON_SCHEMA, render_json_schema(MODEL))
        self.assertEqual(
            (DIRECTORY / "mysql.sql").read_text(encoding="utf-8"), render_sql(MODEL)
        )
        self.assertEqual(len(MODEL["tables"]), 25)
        self.assertEqual(len(MODEL["relationships"]), 59)
        self.assertEqual(len(MODEL["views"]), 6)

    def test_example_loads_and_all_views_execute(self):
        package = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        report = validate_person_epg(package)
        self.assertTrue(report["valid"], report)
        connection = relational_mirror()
        self.addCleanup(connection.close)
        connection.execute("BEGIN")
        for table in MODEL["tables"]:
            rows = (
                [package["graph"]]
                if table["name"] == "subject_graph"
                else package[table["name"]]
            )
            for row in rows:
                insert_row(
                    connection,
                    table["name"],
                    {"graph_id": package["graph"]["graph_id"], **row},
                )
        connection.commit()
        self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        for table in MODEL["tables"]:
            expected = (
                1 if table["name"] == "subject_graph" else len(package[table["name"]])
            )
            self.assertEqual(
                connection.execute(f"SELECT COUNT(*) FROM {table['name']}").fetchone()[
                    0
                ],
                expected,
            )
        for view in MODEL["views"]:
            connection.execute(f"SELECT * FROM {view['name']}").fetchall()
        timeline = connection.execute("SELECT * FROM v_person_timeline").fetchall()
        self.assertEqual(len(timeline), len(package["event_activity"]))
        self.assertTrue(package["stage"], "The example must exercise organized stages.")

        # A real FK must reject a stage belonging to another event, even if the
        # caller bypasses the Python validator and writes directly to storage.
        member = package["event_activity"][0]
        event = next(
            row for row in package["event"] if row["event_id"] == member["event_id"]
        )
        graph_id = package["graph"]["graph_id"]
        connection.execute("BEGIN")
        insert_row(
            connection,
            "event",
            {
                "graph_id": graph_id,
                "event_id": "constraint_other_event",
                "domain_id": event["domain_id"],
                "label": "Constraint fixture",
                "sort_order": 0,
            },
        )
        insert_row(
            connection,
            "stage",
            {
                "graph_id": graph_id,
                "event_id": "constraint_other_event",
                "stage_id": "constraint_foreign_stage",
                "label": "Constraint fixture",
                "sort_order": 0,
            },
        )
        connection.execute(
            "UPDATE event_activity SET stage_id=? WHERE graph_id=? AND event_id=? AND activity_id=?",
            (
                "constraint_foreign_stage",
                graph_id,
                member["event_id"],
                member["activity_id"],
            ),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            connection.commit()
        connection.rollback()


if __name__ == "__main__":
    unittest.main()
