import csv
import json
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest


SKILL = Path(__file__).resolve().parents[1] / "skills/curate-event-dataset"
CHECKS = runpy.run_path(str(SKILL / "scripts/check_input.py"))
PLAN = (SKILL / "assets/research-plan.template.md").read_text(encoding="utf-8")
ISSUES = (SKILL / "assets/issues.template.md").read_text(encoding="utf-8")


def plan_with(rows):
    lines = PLAN.splitlines()
    insert_at = next(i for i, line in enumerate(lines) if line.startswith("| ---")) + 1
    lines[insert_at:insert_at] = rows
    return "\n".join(lines)


def issues_with(*rows):
    return ISSUES.replace("\n## Other issues", "\n".join(rows) + "\n\n## Other issues")


class EventDeliveryTests(unittest.TestCase):
    def test_indexed_source_still_requires_a_support_note_in_the_master(self):
        url = "https://example.org/filing"
        sources = {"SRC-0001": (url, {"event1"}, "Docket 1")}
        check = CHECKS["check_source_hints"]
        for placeholder in ("SRC-0001 — TBD", "SRC-0001: N/A"):
            with self.subTest(placeholder=placeholder), self.assertRaises(ValueError):
                check("event1", [url, placeholder], sources)
        check("event1", [url, "SRC-0001 — The page 1 filing stamp dates the petition."], sources)

    def test_master_field_boundaries(self):
        with (SKILL / "assets/events.example.csv").open(encoding="utf-8-sig", newline="") as f:
            row = next(csv.DictReader(f))
        relation = [{"event_id": "event1", "relation_type": "related", "note": "..."}]
        with TemporaryDirectory() as tmp:
            master = Path(tmp) / "events.csv"

            def check_row(**updates):
                with master.open("w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(row))
                    writer.writeheader()
                    writer.writerow({**row, **updates})
                return CHECKS["check"](master, batch=True, sources_path=SKILL / "assets/sources.example.csv")

            for field, value in (("domain", '["Finance", "Trade & Logistics"]'),
                                 ("category", "Bankruptcy|Payment Disruptions"),
                                 ("aliases", json.dumps([row["event_name_en"]])),
                                 ("related_events", json.dumps(relation))):
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                    check_row(**{field: value})
            self.assertEqual(check_row(category="Corporate Governance, IPOs & M&A", aliases="[]",
                                       coverage_start="2022", coverage_end=""), 1)

    def test_both_reviews_cover_each_id_at_each_milestone(self):
        rows = ["| baseline | Historical records | event1-event2999 | event1-event3000 | | |",
                "| baseline | Recheck | event2999-event3000 | | | |"]
        check = CHECKS["check_progress"]
        with self.assertRaisesRegex(ValueError, "Research completed.*event1"):
            check(PLAN, "baseline")
        check(plan_with(rows), "baseline")
        rows.append("| expansion | New records | event3001-event10000 | event3002-event10000 | | |")
        with self.assertRaisesRegex(ValueError, "Duplicate review coverage.*event3001"):
            check(plan_with(rows), "final")
        rows.append("| expansion | Recheck | | event3001 | | |")
        check(plan_with(rows), "final")
        with self.assertRaisesRegex(ValueError, "baseline|阶段"):
            check(plan_with(rows), "baseline")

    def test_decision_sources_identify_both_events(self):
        issue = ("| event1 and event2 | event2 -> event1 | Same action | Same docket | "
                 "SRC-0001 and SRC-0002, docket entries for the same filing. | 2024-02-29 |")
        sources = {"SRC-0001": ("", {"event1"}, "Case A"),
                   "SRC-0002": ("", {"event3"}, "Case B")}
        check = CHECKS["check_duplicate_decisions"]
        with self.assertRaisesRegex(ValueError, "双方"):
            check(issues_with(issue), {"event2": {"event1"}}, sources, {"event1", "event2"})
        sources["SRC-0002"] = ("", {"event2"}, "Case A")
        check(issues_with(issue), {"event2": {"event1"}}, sources, {"event1", "event2"})

    def test_current_pair_decisions_across_batches(self):
        check = CHECKS["check_duplicate_decisions"]
        members = {"event1", "event2"}
        sources = {"SRC-1": ("", members, "Docket 7")}
        row = "| event1 A / event2 B | distinct | Same docket | Different orders | SRC-1, orders 1 and 2. | 2024-02-29 |"
        reverse = row.replace("event1 A / event2 B", "event2 B / event1 A")
        check(issues_with(row) + "\n" + reverse.replace("distinct", "pending"), {}, sources, members)
        check(issues_with(), {}, {}, members)
        for outcome in ("overlap", "distinct", "pending"):
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                check(issues_with(row, reverse.replace("distinct", outcome)), {}, sources, members)
        with self.assertRaisesRegex(ValueError, "待核"):
            check(issues_with(row.replace("distinct", "pending")), {}, sources, members)
        with self.assertRaisesRegex(ValueError, "已登记"):
            check(issues_with(row.replace("event2", "event9")), {}, sources, members)

    def test_registered_graph_is_readable_by_workbench(self):
        with (SKILL / "assets/events.example.csv").open(encoding="utf-8-sig", newline="") as f:
            row = next(csv.DictReader(f))
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            row["epg_path"] = "events/event2/epg/epg.json"
            artifact = root / row["epg_path"]
            artifact.parent.mkdir(parents=True)
            master = root / "events.csv"
            with master.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            options = dict(batch=True, sources_path=SKILL / "assets/sources.example.csv")
            for content in ("broken JSON", "{}", '{"event_id": "internal-id", "stages": []}'):
                artifact.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "epg_path"):
                    CHECKS["check"](master, **options)
            graph = {"event_id": "internal-id", "title": "Test event",
                     "stages": [{"stage_id": "S1", "episodes": []}]}
            artifact.write_text(json.dumps([graph]), encoding="utf-8")
            self.assertEqual(CHECKS["check"](master, **options), 1)
