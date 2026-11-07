"""Scope decisions preserve dated background without moving it into the timeline."""
import copy
import unittest

from finmy.subject_graph.event_sources import exclude_outside_coverage
from finmy.subject_graph.validation import outside_coverage, validate_subject_graph
from test_subject_graph_schema import SOURCE, field, graph_fixture


HISTORY = "The company bought shares between October and November 2021."


def historical_event():
    event = copy.deepcopy(graph_fixture()["events"][1])
    event.update(event_id="EV_history", title=field("Earlier company purchase", HISTORY),
                 start_time=field("2021-10", HISTORY), end_time=field("2021-11", HISTORY),
                 descriptions=[field("The purchase preceded the covered period.", HISTORY)])
    for participation in event["participations"]:
        participation.update(start_time=field("2021-10", HISTORY),
                             end_time=field("2021-11", HISTORY))
    for row in event["actions"] + event["transactions"]:
        row["timestamp"] = field("2021-11", HISTORY)
    return event


class SubjectScopeReviewTest(unittest.TestCase):
    def test_only_wholly_outside_known_intervals_are_excluded(self):
        for start, end, expected in [
                ("2021-10", "2021-11", True), ("2024", "2024", True),
                ("2021", "2022", False), ("2023-12-31", "2023-12-31", False),
                ("2022", "2024", False), ("unknown", "2021", False),
                ("2024", "unknown", False), ("invalid", "2021", False),
                ("2024", "2021", False)]:
            with self.subTest(start=start, end=end):
                event = {"start_time": field(start), "end_time": field(end)}
                self.assertEqual(outside_coverage(event, "2022", "2023"), expected)

    def test_open_coverage_uses_only_its_configured_bound(self):
        event = historical_event()
        self.assertFalse(outside_coverage(event, None, None))
        self.assertFalse(outside_coverage(event, None, "2023"))
        self.assertTrue(outside_coverage(event, "2022", None))

    def test_outside_event_becomes_dated_background_and_links_are_cleaned(self):
        graph = graph_fixture()
        old = historical_event()
        graph["events"][1] = old
        graph["relations"][0]["event_ids"] += [old["event_id"]]
        historical_relation = copy.deepcopy(graph["relations"][0])
        historical_relation.update(relation_id="REL_old", event_ids=[old["event_id"]])
        graph["relations"].append(historical_relation)
        before = copy.deepcopy(graph)

        result, excluded = exclude_outside_coverage(graph)

        self.assertEqual(graph, before)
        self.assertEqual([e["event_id"] for e in result["events"]], ["EV_meeting"])
        self.assertEqual(result["relations"][0]["event_ids"], ["EV_meeting"])
        self.assertEqual(len(result["relations"]), 1)
        self.assertEqual(excluded[0]["record"], old)
        context = result["descriptions"][-1]
        self.assertIn("2021-10 to 2021-11", context["value"])
        self.assertNotIn("2021-10-01", context["value"])
        self.assertIn(old["descriptions"][0]["value"], context["value"])
        self.assertEqual(context["evidence_source_contents"], [HISTORY])
        self.assertEqual(context["reasons"], ["fixture source"])
        self.assertTrue(validate_subject_graph(result, [SOURCE, HISTORY])["valid"])
        again, second_excluded = exclude_outside_coverage(result)
        self.assertEqual(again, result)
        self.assertEqual(second_excluded, [])

    def test_planned_event_can_be_filtered_before_detail_reconstruction(self):
        event = historical_event()
        event = {key: event[key] for key in (
            "event_id", "title", "start_time", "end_time", "descriptions")}
        graph = {"coverage_start": "2022", "coverage_end": "2023", "events": [event]}
        result, excluded = exclude_outside_coverage(graph)
        self.assertEqual(result["events"], [])
        self.assertEqual(len(excluded), 1)
        self.assertEqual(len(result["descriptions"]), 1)

    def test_preserving_background_does_not_upgrade_pending_evidence(self):
        graph = graph_fixture()
        graph["events"][1] = historical_event()
        graph["events"][1]["title"]["evidence_status"] = "needs_review"
        result, _ = exclude_outside_coverage(graph)
        self.assertEqual(result["descriptions"][-1]["evidence_status"], "needs_review")

    def test_validation_rejects_outside_event_without_erasing_its_dates(self):
        graph = graph_fixture()
        graph["events"][1] = historical_event()
        before = copy.deepcopy(graph)
        report = validate_subject_graph(graph, [SOURCE, HISTORY])
        self.assertFalse(report["valid"])
        self.assertTrue(any(item["path"] == "/events/1" and
                            "outside configured coverage" in item["message"]
                            for item in report["errors"]))
        self.assertEqual(graph, before)


if __name__ == "__main__":
    unittest.main()
