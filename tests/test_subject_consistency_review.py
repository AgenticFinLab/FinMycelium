"""Offline source-bound local corrections and occurrence merge regressions."""
import copy
import unittest
import test_subject_graph_builder as fixtures
from test_subject_graph_builder import config, input_, vf, SOURCE
from finmy.subject_graph.build import run_subject_build
from finmy.subject_graph.consistency_review import apply_event_corrections, apply_event_merges, correction_exclusions

class ConsistencyReviewTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.NativeBuildTests(); fixture.setUp()
        self.graph, _, _ = run_subject_build(input_(), config(), fixture.complete, fixture.save)
        self.sources = [{"source_id": "S1", "content": SOURCE}]
        self.allocation = {"E1": self.sources, "E2": self.sources}

    def correct(self, patches):
        return apply_event_corrections(self.graph, "E1", [{"reason": "Use supported context", "patches": patches}], self.allocation, self.sources)

    def test_replaces_existing_detail_preserving_other_records(self):
        original = copy.deepcopy(self.graph)
        result, report = self.correct([{"op": "replace", "path": "/event/actions/0/details/0", "value": vf("Later explanation, not contemporaneous information")}])
        self.assertEqual(self.graph, original)
        self.assertEqual(len(report["accepted"]), 1)
        self.assertEqual(result["events"][1], original["events"][1])
        self.assertNotEqual(result["events"][0]["actions"][0]["details"], original["events"][0]["actions"][0]["details"])

    def test_rejects_fragments_ids_flags_unknown_quotes_and_bad_time(self):
        for path, value in (("/event/event_id", "E3"), ("/event/actions", []),
                ("/event/title/value", "Changed"),
                ("/event/title", {**vf("Changed"), "evidence_status": "needs_review"}),
                ("/event/title", vf("Changed", "not supplied")),
                ("/event/actions/0/timestamp", vf("2024"))):
            result, report = self.correct([{"op": "replace", "path": path, "value": value}])
            self.assertEqual(result, self.graph)
            self.assertTrue(report["rejected"])

    def test_rejects_source_outside_event(self):
        source = {"source_id": "S2", "content": "Only a different occurrence supports this statement."}
        self.sources = [*self.sources, source]
        result, report = self.correct([{"op": "replace", "path": "/event/title", "value": vf("Changed", source["content"])}])
        self.assertEqual(result, self.graph)
        self.assertTrue(report["rejected"])

    def test_removals_across_groups_use_original_indices(self):
        self.graph["events"][0]["descriptions"] = [vf("first"), vf("second"), vf("third")]
        result, report = apply_event_corrections(self.graph, "E1", [
            {"reason": "Unsupported context", "patches": [{"op": "remove", "path": "/event/descriptions/0"}]},
            {"reason": "Later information", "patches": [{"op": "remove", "path": "/event/descriptions/2"}]}], self.allocation, self.sources)
        self.assertEqual(result["events"][0]["descriptions"], [vf("second")])
        self.assertEqual(len(report["accepted"]), 2)

    def test_actor_requires_evidenced_companion_change(self):
        result, report = self.correct([{"op": "replace", "path": "/event/actions/0/actor_id", "value": "buffett"}])
        self.assertTrue(report["rejected"])
        self.assertEqual(result, self.graph)

    def test_quarter_end_can_be_replaced_with_honest_unknown(self):
        event = self.graph["events"][0]
        event["start_time"] = vf("2023-04-01")
        event["end_time"] = vf("2023-06-30")
        event["actions"][0]["timestamp"] = vf("2023-06-30")
        field = vf("unknown", None)
        field["reasons"] = ["Only Q2 2023 is supported; the quarter end is not the trade date."]
        result, report = self.correct([{"op": "replace", "path": "/event/actions/0/timestamp", "value": field}])
        self.assertTrue(report["accepted"])
        self.assertEqual(result["events"][0]["actions"][0]["timestamp"], field)

    def test_speculative_attribution_stays_qualified(self):
        quote = "Observers inferred Buffett may have made the decision from the position size."
        self.sources[0]["content"] += " " + quote
        result, report = self.correct([{"op": "replace", "path": "/event/actions/0/action_type",
            "value": vf("Reported possible involvement in the investment, unconfirmed", quote)}])
        self.assertTrue(report["accepted"])
        self.assertIn("unconfirmed", result["events"][0]["actions"][0]["action_type"]["value"])

    def test_failed_group_does_not_discard_independent_corrections(self):
        result, report = apply_event_corrections(self.graph, "E1", [
            {"reason": "Unsupported context", "patches": [{"op": "remove", "path": "/event/descriptions/0"}]},
            {"reason": "Invalid precision", "patches": [{"op": "replace", "path": "/event/actions/0/timestamp", "value": vf("2024")}]},
            {"reason": "Add supported explanation", "patches": [{"op": "add", "path": "/event/actions/0/details/-", "value": vf("The person expressed a view")}]}], self.allocation, self.sources)
        self.assertEqual(result["events"][0]["descriptions"], [])
        self.assertEqual(result["events"][0]["actions"][0]["timestamp"], self.graph["events"][0]["actions"][0]["timestamp"])
        self.assertEqual(len(result["events"][0]["actions"][0]["details"]), 2)
        self.assertEqual(len(report["accepted"]), 2)
        self.assertEqual(len(report["rejected"]), 1)

    def test_one_group_remains_atomic(self):
        result, report = self.correct([
            {"op": "remove", "path": "/event/descriptions/0"},
            {"op": "replace", "path": "/event/actions/0/timestamp", "value": vf("2024")}])
        self.assertEqual(result, self.graph)
        self.assertEqual(len(report["rejected"]), 1)

    def test_stale_remove_rejects_only_its_group(self):
        self.graph["events"][0]["actions"] = []
        result, report = apply_event_corrections(self.graph, "E1", [
            {"reason": "Already removed action", "patches": [{"op": "remove", "path": "/event/actions/0"}]},
            {"reason": "Documented context", "patches": [{"op": "replace", "path": "/event/descriptions/0", "value": vf("Documented explanation")}]}], self.allocation, self.sources)
        self.assertEqual(len(report["accepted"]), 1)
        self.assertIn("does not exist", report["rejected"][0]["reason"])
        self.assertEqual(result["events"][0]["descriptions"], [vf("Documented explanation")])

    def test_stable_ids_and_exclusions_keep_original_targets_after_removal(self):
        event = self.graph["events"][0]
        action = copy.deepcopy(event["actions"][0])
        action["action_id"] = "E1_A2"
        action["details"] = [vf("Original second action")]
        event["actions"].append(action)
        result, report = apply_event_corrections(self.graph, "E1", [
            {"reason": "Remove unsupported action", "patches": [{"op": "remove", "path": "/event/actions/E1_A1"}]},
            {"reason": "Qualify second action", "patches": [{"op": "replace", "path": "/event/actions/E1_A2/details/0", "value": vf("Qualified second action")}]},
            {"reason": "Add context", "patches": [{"op": "add", "path": "/event/actions/E1_A2/details/-", "value": vf("Context")}]}], self.allocation, self.sources)
        self.assertEqual(len(report["accepted"]), 3, report)
        self.assertEqual(result["events"][0]["actions"][0]["action_id"], "E1_A2")
        exclusions = correction_exclusions("E1", report)
        self.assertEqual([r["record"]["action_id"] for r in exclusions if "action_id" in r["record"]], ["E1_A1", "E1_A2"])
        self.assertEqual(exclusions[-1]["record"], vf("Original second action"))

    def test_appends_full_action_with_same_source_and_schema_guards(self):
        action = copy.deepcopy(self.graph["events"][0]["actions"][0])
        action["action_id"] = "E1_A2"
        result, report = self.correct([
            {"op": "add", "path": "/event/actions/-", "value": action},
            {"op": "add", "path": "/event/descriptions/-", "value": vf("Context")},
            {"op": "add", "path": "/event/descriptions/-", "value": vf("Further context")}])
        self.assertTrue(report["accepted"], report)
        self.assertEqual(len(result["events"][0]["actions"]), 2)
        self.assertEqual(correction_exclusions("E1", report), [])
        for invalid in ({**action, "actor_id": "missing"},
                        {**action, "details": [vf("Unsupported", "Fabricated source")]},
                        {**action, "action_id": "E1_A1"}):
            result, report = self.correct([{"op": "add", "path": "/event/actions/-", "value": invalid}])
            self.assertEqual(result, self.graph)
            self.assertTrue(report["rejected"])

    def test_conflicting_groups_do_not_overwrite_accepted_change(self):
        result, report = apply_event_corrections(self.graph, "E1", [
            {"reason": "First correction", "patches": [{"op": "replace", "path": "/event/actions/0/details/0", "value": vf("First")}]},
            {"reason": "Conflicting correction", "patches": [{"op": "remove", "path": "/event/actions/E1_A1"}]}], self.allocation, self.sources)
        self.assertEqual(result["events"][0]["actions"][0]["details"], [vf("First")])
        self.assertEqual(len(report["accepted"]), 1)
        self.assertEqual(len(report["rejected"]), 1)

    def letters(self):
        quote = "The annual shareholder letter was published on February 25, 2023."
        self.sources = [{"source_id": "S1", "content": SOURCE + " " + quote}]
        self.allocation = {"E1": self.sources, "E2": self.sources}
        for index, event in enumerate(self.graph["events"]):
            event["title"] = vf(f"{2022+index} Annual Shareholder Letter", quote)
            event["start_time"] = event["end_time"] = vf("2023-02-25", quote)
            for part in event["participations"]:
                part["start_time"] = part["end_time"] = vf("2023-02-25", quote)
            for action in event["actions"]:
                action["timestamp"] = vf("2023-02-25", quote)
        return {"keep_event_id": "E1", "remove_event_id": "E2", "reason": "Same letter, reporting and publication year labels", "evidence_source_contents": [quote]}

    def test_merge_preserves_content_and_remaps_relations(self):
        proposal = self.letters()
        self.graph["relations"] = [{"relation_id": "R1", "from_entity_id": "buffett", "to_entity_id": "berkshire", "relation_type": vf("Chairman"), "valid_from": vf("unknown", None), "valid_to": vf("unknown", None), "event_ids": ["E1", "E2"]}]
        original = copy.deepcopy(self.graph)
        result, allocation, report = apply_event_merges(self.graph, [proposal], self.allocation, self.sources)
        self.assertEqual(len(report["accepted"]), 1, report)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(len(result["events"][0]["actions"]), 2)
        self.assertEqual(result["relations"][0]["event_ids"], ["E1"])
        self.assertNotIn("E2", allocation)
        self.assertEqual(self.graph, original)

    def test_same_date_alone_different_type_or_coarse_time_cannot_merge(self):
        proposal = self.letters()
        for change in ("different_type", "different_day", "coarse", "unshared_quote"):
            graph = copy.deepcopy(self.graph)
            if change == "different_type": graph["events"][1]["title"] = vf("Share purchase")
            if change == "different_day": graph["events"][1]["end_time"] = vf("2023-02-26")
            if change == "coarse": graph["events"][1]["start_time"] = graph["events"][1]["end_time"] = vf("2023-02")
            if change == "unshared_quote": graph["events"][1]["title"] = vf("Another annual shareholder letter")
            result, _, report = apply_event_merges(graph, [proposal], self.allocation, self.sources)
            self.assertEqual(result, graph)
            self.assertTrue(report["rejected"], change)

    def test_builder_final_merge_preserves_raw_proposal_and_saved_sources(self):
        proposal = self.letters()
        saved = {}
        graph = copy.deepcopy(self.graph)
        source = input_()
        source.samples[0].content = self.sources[0]["content"]
        def complete(name, system, payload):
            if name == "SubjectPlanner":
                return {"title": graph["title"], "descriptions": [], "entities": graph["entities"],
                        "events": [{**e, "participations": [], "actions": [], "transactions": []}
                                   for e in graph["events"]], "relations": [],
                        "event_sources": {"E1": ["S1"], "E2": ["S1"]}}
            if name == "SubjectEventReconstructor":
                return {"event": next(e for e in graph["events"]
                                      if e["event_id"] == payload["TargetEvent"]["event_id"]), "relations": []}
            return {"event_additions": [], "missing_events": [], **(
                {"event_merges": [proposal]} if name == "SubjectCoverageReviewer" else {})}
        result, state, report = run_subject_build(source, config(), complete,
                                                  lambda value, name: saved.update({name: copy.deepcopy(value)}))
        self.assertTrue(report["valid"], report)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(saved["subject_event_sources"], {"E1": ["S1"]})
        self.assertEqual(state["agent_results"][-1]["SubjectCoverageReviewer"]["event_merges"], [proposal])
        self.assertEqual(len(state["agent_executed"]), 6)

if __name__ == "__main__": unittest.main()
