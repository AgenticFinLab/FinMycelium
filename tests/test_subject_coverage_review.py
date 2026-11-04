"""Offline omission-review regressions: additions cannot rewrite existing facts."""
import copy
import unittest

import test_subject_graph_builder as fixtures
from test_subject_graph_builder import config, input_, vf, SOURCE
from finmy.subject_graph.build import run_subject_build
from finmy.subject_graph.coverage_review import apply_coverage_additions, find_statement_duplicates


class CoverageReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.NativeBuildTests()
        self.fixture.setUp()
        self.graph, _, _ = run_subject_build(input_(), config(), self.fixture.complete, self.fixture.save)
        self.sources = [{"source_id": "S1", "content": SOURCE}]
        self.allocation = {"E1": self.sources, "E2": self.sources}

    def apply(self, additions=None, missing=None):
        return apply_coverage_additions(self.graph,
            {"event_additions": additions or [], "missing_events": missing or []},
            self.allocation, self.sources, 60)

    def test_existing_action_gets_missing_details_without_rewriting(self):
        detail = vf("Buffett said he liked the company.")
        original = copy.deepcopy(self.graph)
        result, _, report = self.apply([{"event_id": "E1", "action_details": [
            {"action_id": "E1_A1", "details": [detail]}]}])
        expected = copy.deepcopy(original)
        expected["events"][0]["actions"][0]["details"].append(detail)
        self.assertEqual(result, expected)
        self.assertEqual(self.graph, original)
        self.assertEqual(report["status"], "supplemented")

    def test_distinct_statement_can_be_added(self):
        action = copy.deepcopy(self.graph["events"][0]["actions"][0])
        action.update(action_id="E1_A2", action_type=vf("Expressed confidence in the company"))
        result, _, report = self.apply([{"event_id": "E1", "actions": [action]}])
        self.assertEqual(len(result["events"][0]["actions"]), 2)
        self.assertEqual(len(report["accepted"]), 1)

    def test_omitted_event_is_recovered_with_explicit_sources(self):
        missing = self.graph["events"].pop()
        self.allocation.pop("E2")
        result, allocation, report = self.apply(missing=[{"event": missing, "source_ids": ["S1"]}])
        self.assertEqual(result["events"][1], missing)
        self.assertEqual(allocation["E2"], self.sources)
        self.assertTrue(report["accepted"][0]["new_event"])

    def test_date_identity_and_outside_source_edits_are_rejected(self):
        other = "In 2024 a different company reported profits."
        self.sources.append({"source_id": "S2", "content": other})
        self.allocation = {"E1": self.sources[:1], "E2": self.sources[:1]}
        for addition in (
            {"event_id": "E1", "start_time": vf("2024")},
            {"event_id": "E1", "descriptions": [vf("Unrelated profits", other)]},
            {"event_id": "E1", "descriptions": [vf("Invented", "No such passage")]},
            {"event_id": "E1", "descriptions": [{**vf("Invented", None), "evidence_status": "needs_review"}]},
        ):
            result, _, report = self.apply([addition])
            self.assertEqual(result, self.graph)
            self.assertEqual(len(report["rejected"]), 1)

    def test_out_of_event_actions_and_dangling_actors_stay_rejected(self):
        for change in ({"timestamp": vf("2020")}, {"actor_id": "unregistered"}):
            action = copy.deepcopy(self.graph["events"][0]["actions"][0])
            action.update(action_id="E1_A2", action_type=vf("Another statement"), **change)
            result, _, report = self.apply([{"event_id": "E1", "actions": [action]}])
            self.assertEqual(result, self.graph)
            self.assertEqual(len(report["rejected"]), 1)

    def test_duplicate_actions_events_and_details_are_not_readded(self):
        event = copy.deepcopy(self.graph["events"][0])
        for additions, missing in (
            ([{"event_id": "E1", "actions": event["actions"]}], []),
            ([], [{"event": event, "source_ids": ["S1"]}]),
            ([{"event_id": "E1", "action_details": [{"action_id": "E1_A1", "details": event["actions"][0]["details"]}]}], []),
        ):
            result, _, report = self.apply(additions, missing)
            self.assertEqual(result, self.graph)
            self.assertEqual(report["accepted"], [])

    def test_invalid_missing_event_sources_and_event_limit(self):
        missing = self.graph["events"].pop()
        result, _, report = self.apply(missing=[{"event": missing, "source_ids": ["unknown"]}])
        self.assertEqual(result, self.graph)
        self.assertEqual(len(report["rejected"]), 1)
        result, _, report = apply_coverage_additions(self.graph,
            {"event_additions": [], "missing_events": [{"event": missing, "source_ids": ["S1"]}]},
            self.allocation, self.sources, 1)
        self.assertEqual(result, self.graph)
        self.assertIn("limit", report["rejected"][0]["reason"])

    def test_one_failed_group_does_not_discard_a_supported_supplement(self):
        result, _, report = self.apply([
            {"event_id": "E1", "descriptions": [vf("More context")]},
            {"event_id": "E2", "descriptions": [vf("Invented", "not present")]},
        ])
        self.assertEqual(len(result["events"][0]["descriptions"]), 2)
        self.assertEqual(result["events"][1], self.graph["events"][1])
        self.assertEqual(len(report["accepted"]), 1)
        self.assertEqual(len(report["rejected"]), 1)

    def test_optional_review_failure_keeps_valid_graph_and_never_retries(self):
        calls = []
        def complete(name, system, payload):
            if name == "SubjectCoverageReviewer":
                calls.append(payload)
                raise ValueError("Incomplete model JSON")
            return self.fixture.complete(name, system, payload)
        graph, _, report = run_subject_build(input_(), config(), complete, self.fixture.save)
        self.assertEqual(graph, self.graph)
        self.assertTrue(report["valid"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.fixture.saved["subject_coverage_review"]["status"], "failed")

    def test_successful_builder_review_updates_saved_validation_and_sources(self):
        self.fixture.plan["events"] = self.fixture.plan["events"][:1]
        def complete(name, system, payload):
            if name == "SubjectCoverageReviewer":
                self.assertEqual(payload["EventSourceIds"], {"E1": ["S1"]})
                self.assertEqual(payload["Sources"], self.sources)
                return {"event_additions": [], "missing_events": [
                    {"event": self.fixture.events[1], "source_ids": ["S1"]}]}
            return self.fixture.complete(name, system, payload)
        graph, state, report = run_subject_build(input_(), config(), complete, self.fixture.save)
        self.assertEqual(graph, self.graph)
        self.assertTrue(report["valid"])
        self.assertEqual(state["agent_executed"].count("SubjectCoverageReviewer"), 1)
        self.assertEqual(self.fixture.saved["subject_event_sources"]["E2"], ["S1"])
        self.assertEqual(self.fixture.saved["subject_coverage_review"]["status"], "supplemented")

    def test_detail_review_enriches_existing_action_before_global_review(self):
        calls = []
        detail = vf("Buffett liked the company.")
        def complete(name, system, payload):
            if name == "SubjectEventReviewer":
                eid = payload["TargetEvent"]["event_id"]
                calls.append(eid)
                self.assertNotIn("ConstructedGraph", payload)
                self.assertEqual(payload["Sources"], self.sources)
                return {"missing_events": [], "event_additions": ([{
                    "event_id": "E1", "action_details": [{"action_id": "E1_A1", "details": [detail]}]
                }] if eid == "E1" else [])}
            if name == "SubjectCoverageReviewer":
                self.assertIn(detail, payload["ConstructedGraph"]["events"][0]["actions"][0]["details"])
            return self.fixture.complete(name, system, payload)
        graph, _, report = run_subject_build(input_(), config(), complete, self.fixture.save)
        self.assertEqual(calls, ["E1", "E2"])
        self.assertTrue(report["valid"])
        self.assertIn(detail, graph["events"][0]["actions"][0]["details"])
        self.assertEqual([r["status"] for r in self.fixture.saved["subject_event_detail_review"]],
                         ["supplemented", "no_additions"])

    def test_detail_review_cannot_edit_another_event_or_add_events(self):
        for proposal in ({"event_additions": [{"event_id": "E2", "descriptions": [vf("Wrong event")]}], "missing_events": []},
                         {"event_additions": [], "missing_events": [{"event": self.fixture.events[1], "source_ids": ["S1"]}]}):
            calls = []
            def complete(name, system, payload):
                if name == "SubjectEventReviewer":
                    calls.append(payload["TargetEvent"]["event_id"])
                    if calls[-1] == "E1":
                        return proposal
                return self.fixture.complete(name, system, payload)
            graph, _, report = run_subject_build(input_(), config(), complete, self.fixture.save)
            self.assertEqual(graph, self.graph)
            self.assertTrue(report["valid"])
            self.assertEqual(calls, ["E1", "E2"])
            self.assertEqual(self.fixture.saved["subject_event_detail_review"][0]["status"], "failed")

    def test_review_restores_quotes_only_within_assigned_sources(self):
        text = "This original passage describes the intrinsic value of the company in detail."
        supplied = text.replace("the intrinsic", "theintrinsic")
        self.sources[0]["content"] += supplied
        result, _, report = self.apply([{"event_id": "E1", "descriptions": [vf(text, text)]}])
        self.assertEqual(result["events"][0]["descriptions"][-1]["evidence_source_contents"], [supplied])
        self.assertEqual(len(report["quote_restoration"]), 1)
        self.sources[0]["content"] = SOURCE
        self.sources.append({"source_id": "S2", "content": supplied})
        self.allocation = {"E1": self.sources[:1], "E2": self.sources[:1]}
        result, _, report = self.apply([{"event_id": "E1", "descriptions": [vf(text, text)]}])
        self.assertEqual(result, self.graph)
        self.assertEqual(len(report["rejected"]), 1)

    def statement_fixture(self):
        event = self.graph["events"][0]
        event["start_time"] = event["end_time"] = vf("2023-05-06")
        event["participations"][0]["start_time"] = event["participations"][0]["end_time"] = vf("2023-05-06")
        action = event["actions"][0]
        action.update(action_type=vf("Explained investment decision"), timestamp=vf("2023-05-06"))
        return event, action

    def test_reworded_statement_in_new_event_is_flagged_without_mutating_old_graph(self):
        event, _ = self.statement_fixture()
        duplicate = copy.deepcopy(event)
        duplicate.update(event_id="E3", title=vf("Another headline about the same disclosure"))
        duplicate["participations"][0]["participation_id"] = "E3_P1"
        duplicate["actions"][0].update(action_id="E3_A1", action_type=vf("Disclosed rationale"))
        result, _, report = self.apply(missing=[{"event": duplicate, "source_ids": ["S1"]}])
        self.assertEqual(result, self.graph)
        self.assertIn("repeated statement", report["rejected"][0]["reason"])
        self.graph["events"].append(duplicate)
        original = copy.deepcopy(self.graph)
        duplicates = find_statement_duplicates(self.graph)
        self.assertEqual(duplicates[0]["possible_duplicate_of"], {"event_id": "E1", "action_id": "E1_A1"})
        self.assertEqual(self.graph, original)

    def test_similar_statements_at_other_times_by_other_speakers_or_without_common_evidence_are_kept(self):
        _, action = self.statement_fixture()
        from finmy.subject_graph.coverage_review import repeated_statement
        for change in ({"timestamp": vf("2023-05-07")}, {"timestamp": vf("2023-05")},
                       {"timestamp": vf("unknown")}, {"actor_id": "berkshire"},
                       {"action_type": vf("Purchased shares")},
                       {"action_type": vf("Explained investment decision", "Different specific evidence passage entirely."),
                        "details": []}):
            with self.subTest(change=change):
                self.assertIsNone(repeated_statement({**action, **change}, self.graph))


if __name__ == "__main__":
    unittest.main()
