"""Canonical representation regressions; no claim to test live model reasoning."""
import copy
import unittest

from finmy.subject_graph.compat import to_event_cascade
from finmy.subject_graph.validation import date_interval, validate_subject_graph
from test_subject_graph_schema import graph_fixture, field


class SubjectTemporalRepresentationTests(unittest.TestCase):
    def event_in_window(self, start, end, timestamp, quote, reason):
        graph = graph_fixture()
        graph.update(coverage_start="2022", coverage_end="2022", relations=[])
        graph["events"] = graph["events"][:1]
        event = graph["events"][0]
        for key, value in (("start_time", start), ("end_time", end)):
            event[key] = field(value, quote)
            event[key]["reasons"] = [reason]
            for participation in event["participations"]:
                participation[key] = copy.deepcopy(event[key])
        event["actions"][0]["timestamp"] = field(timestamp, quote)
        event["actions"][0]["timestamp"]["reasons"] = [reason]
        return graph

    def test_derived_spring_window_and_unknown_action_survive_export(self):
        graph = self.event_in_window(
            "2022-03", "2022-05", "unknown", "2022年春天",
            "Northern meteorological spring; occurrence within March-May, exact day unknown.")
        before = copy.deepcopy(graph)
        self.assertTrue(validate_subject_graph(graph)["valid"])
        stage = to_event_cascade(graph)["stages"][0]
        self.assertEqual(stage["start_time"], graph["events"][0]["start_time"])
        self.assertEqual(stage["end_time"], graph["events"][0]["end_time"])
        self.assertEqual(stage["episodes"][1]["start_time"]["value"], "unknown")
        self.assertEqual(graph, before)

    def test_calendar_derived_named_day_needs_no_literal_iso_quote(self):
        graph = self.event_in_window(
            "2022-12-25", "2022-12-25", "2022-12-25", "2022年圣诞节当天",
            "Gregorian Christmas Day is December 25; derived from the named day.")
        self.assertTrue(validate_subject_graph(graph)["valid"])
        stage = to_event_cascade(graph)["stages"][0]
        timestamp = stage["episodes"][1]["start_time"]
        self.assertEqual(timestamp["value"], "2022-12-25")
        self.assertEqual(timestamp["evidence_source_contents"], ["2022年圣诞节当天"])

    def test_quarter_window_keeps_unknown_action_and_rejects_later_date(self):
        graph = self.event_in_window(
            "2022-07", "2022-09", "unknown", "Bought during Q3 2022.",
            "Calendar Q3: July-September; execution day is not given.")
        self.assertTrue(validate_subject_graph(graph)["valid"])
        stage = to_event_cascade(graph)["stages"][0]
        self.assertEqual(stage["episodes"][1]["end_time"]["value"], "unknown")
        graph["events"][0]["actions"][0]["timestamp"] = field("2022-11")
        self.assertTrue(any("outside" in error["message"] for error in
                            validate_subject_graph(graph)["errors"]))

    def test_partial_dates_use_calendar_bounds_without_mutation(self):
        value = field("2024-02", "February 2024")
        before = copy.deepcopy(value)
        start, end, precision = date_interval(value)
        self.assertEqual((start.day, end.day, precision), (1, 29, "month"))
        self.assertEqual(value, before)


if __name__ == "__main__":
    unittest.main()
