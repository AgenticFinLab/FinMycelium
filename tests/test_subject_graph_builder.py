"""Native builder contracts with fake model responses and real validation/export."""
import copy
import json
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import test_epg_validation_integration as integration
from finmy.subject_graph.build import run_subject_build
from finmy.subject_graph.schema import JSON_SCHEMA

SOURCE = "In May 2023 Warren Buffett said he liked the company. In June 2023 Berkshire Hathaway bought shares."


def vf(value, quote=SOURCE):
    return {"value": value, "evidence_source_contents": [quote] if quote else [], "reasons": []}


def config(mode="person", **options):
    return {"reconstruction": {"mode": mode, "subject": {
        "subject_id": "buffett" if mode == "person" else "berkshire",
        "name": "Warren Buffett" if mode == "person" else "Berkshire Hathaway",
        "aliases": [], "coverage_start": "2023", "coverage_end": "2023"}},
        "subject_graph": {"repair_attempts": 0, **options}}


def fixture():
    entities = [{"entity_id": eid, "name": vf(name), "aliases": [], "entity_type": kind, "attributes": {}}
                for eid, name, kind in (("buffett", "Warren Buffett", "individual"),
                                        ("berkshire", "Berkshire Hathaway", "organization"))]
    events = []
    for eid, actor, month, title, action in (("E1", "buffett", "2023-05", "Statement", "speak"),
                                           ("E2", "berkshire", "2023-06", "Share purchase", "buy shares")):
        events.append({"event_id": eid, "title": vf(title), "subject_relevance": vf("Documented subject activity or related company context"),
                       "start_time": vf(month), "end_time": vf(month),
                       "descriptions": [vf(title)],
                       "participations": [{"participation_id": eid+"_P1", "entity_id": actor,
                           "role": vf("speaker" if actor == "buffett" else "buyer"),
                           "start_time": vf(month), "end_time": vf(month)}],
                       "actions": [{"action_id": eid+"_A1", "actor_id": actor, "action_type": vf(action),
                                   "timestamp": vf(month), "details": [vf(title)]}], "transactions": []})
    plan = {"title": vf("Selected history", None), "descriptions": [], "entities": entities,
            "events": [{**copy.deepcopy(e), "participations": [], "actions": []} for e in events], "relations": []}
    return plan, events


def input_():
    return types.SimpleNamespace(user_query=types.SimpleNamespace(query_text="Documented activities", key_words=[]),
                                 samples=[types.SimpleNamespace(sample_id="S1", content=SOURCE)])


class NativeBuildTests(unittest.TestCase):
    def setUp(self):
        self.saved, self.calls = {}, []
        self.plan, self.events = fixture()

    def save(self, value, name):
        self.saved[name] = copy.deepcopy(value)

    def complete(self, name, system, payload):
        self.calls.append((name, system, copy.deepcopy(payload)))
        if name == "SubjectPlanner":
            return copy.deepcopy(self.plan)
        if name in ("SubjectCoverageReviewer", "SubjectEventReviewer"):
            return {"event_additions": [], "missing_events": []}
        return {"event": copy.deepcopy(next(e for e in self.events if e["event_id"] == payload["TargetEvent"]["event_id"])),
                "relations": []}

    def test_native_plan_uses_one_registry_and_independent_events(self):
        graph, state, report = run_subject_build(input_(), config(), self.complete, self.save)
        self.assertTrue(report["valid"], report)
        self.assertNotIn("stages", graph)
        self.assertEqual(graph["subject_id"], "buffett")
        self.assertEqual(len(graph["entities"]), 2)
        self.assertEqual([e["actions"][0]["actor_id"] for e in graph["events"]], ["buffett", "berkshire"])
        self.assertEqual([e["start_time"]["value"] for e in graph["events"]], ["2023-05", "2023-06"])
        self.assertEqual(state["agent_executed"], ["SubjectPlanner", "SubjectEventReconstructor", "SubjectEventReconstructor",
                                                  "SubjectEventReviewer", "SubjectEventReviewer", "SubjectCoverageReviewer"])
        self.assertEqual(self.saved["subject_build_input"]["Sources"][0]["content"], SOURCE)
        self.assertNotIn("Sources", graph)
        self.assertEqual(self.calls[1][2]["EntityRegistry"], self.calls[2][2]["EntityRegistry"])


    def test_dangling_actor_fails_without_final_export(self):
        self.events[0]["actions"][0]["actor_id"] = "invented"
        with self.assertRaisesRegex(ValueError, "failed validation"):
            run_subject_build(input_(), config(), self.complete, self.save)
        self.assertIn("RawSubjectGraph", self.saved)
        self.assertFalse(self.saved["subject_graph_validation"]["valid"])
        self.assertNotIn("FinalSubjectGraph", self.saved)

    def test_unsupported_quotes_are_marked_after_one_bounded_repair(self):
        self.events[0]["descriptions"][0]["evidence_source_contents"] = ["A fabricated quote"]
        def complete(name, system, payload):
            if name == "SubjectGraphRepair":
                self.calls.append((name, system, payload))
                return {"patches": []}
            return self.complete(name, system, payload)
        graph, _, report = run_subject_build(input_(), config(repair_attempts=1), complete, self.save)
        self.assertEqual(sum(name == "SubjectGraphRepair" for name, _, _ in self.calls), 1)
        self.assertTrue(report["valid"])
        self.assertTrue(report["warnings"])
        field = graph["events"][0]["descriptions"][0]
        self.assertEqual(field["evidence_status"], "needs_review")
        self.assertEqual(field["evidence_source_contents"], ["A fabricated quote"])
        self.assertIsNone(field["confidence"])
        self.assertNotIn("evidence_status", graph["events"][1]["descriptions"][0])
        self.assertTrue(self.saved["subject_evidence_review"])


    def test_bounded_repair_can_fix_reference_and_preserve_correct_content(self):
        self.events[0]["actions"][0]["actor_id"] = "wrong"
        def complete(name, system, payload):
            if name == "SubjectGraphRepair":
                self.assertIn('"patches"', system)
                self.assertNotIn("returning ONE complete", system)
                return {"patches": [{"op": "replace", "path": "/events/0/actions/0/actor_id", "value": "buffett"}]}
            return self.complete(name, system, payload)
        graph, state, report = run_subject_build(input_(), config(repair_attempts=1), complete, self.save)
        self.assertTrue(report["valid"])
        self.assertEqual(state["agent_executed"][-4:], ["SubjectGraphRepair", "SubjectEventReviewer",
                                                       "SubjectEventReviewer", "SubjectCoverageReviewer"])
        self.assertEqual(graph["events"][1], self.events[1])
        self.assertEqual(self.saved["RawSubjectGraph"]["events"][0]["actions"][0]["actor_id"], "wrong")


    def test_configured_identity_does_not_invent_personal_participation(self):
        self.plan["entities"] = [self.plan["entities"][1]]
        self.plan["events"] = [self.plan["events"][1]]
        graph, _, report = run_subject_build(input_(), config(), self.complete, self.save)
        self.assertTrue(report["valid"], report)
        subject = next(e for e in graph["entities"] if e["entity_id"] == "buffett")
        self.assertEqual(subject["name"]["reasons"], ["configured_identity"])
        self.assertEqual([p["entity_id"] for p in graph["events"][0]["participations"]], ["berkshire"])


class NativeBuilderIntegrationTests(unittest.TestCase):
    setUp = integration.IntegrationTest.setUp


    def test_run_dispatches_native_and_exports_primary_and_legacy_artifacts(self):
        self.builder.build_config = config()
        self.builder.agents_lm = object()
        self.builder.graph = lambda: self.fail("Native mode must not invoke the legacy stage graph")
        plan, events = fixture()
        calls = []
        def infer(engine, request, **kwargs):
            # The production adapter formats each template once. Literal braces
            # in either the schema or an inserted source must survive that pass.
            formatted_system = request.system_msg.format(**kwargs)
            schema_text = formatted_system.split("Native SubjectGraph schema:\n", 1)[1]
            self.assertEqual(json.loads(schema_text), JSON_SCHEMA)
            payload = json.loads(request.user_msg.format(**kwargs))
            calls.append(payload)
            answer = plan if "TargetEvent" not in payload else {
                "event": next(e for e in events if e["event_id"] == payload["TargetEvent"]["event_id"]), "relations": []}
            if "ConstructedGraph" in payload or "Review ONLY TargetEvent" in formatted_system:
                answer = {"event_additions": [], "missing_events": []}
            return types.SimpleNamespace(response=json.dumps(answer), to_dict=lambda: {"response": json.dumps(answer)})
        source_input = input_()
        source_input.samples[0].content += ' Literal source syntax: {payload}, {other}, {"key": "value"}.'
        with patch.dict(self.builder._run_subject.__globals__, {
            "InferInput": types.SimpleNamespace, "run_single_inference": infer,
            "extract_json_response": json.loads,
        }), patch("finmy.subject_graph.visualizer.to_event_cascade") as render_conversion:
            result = self.builder.run(source_input)
        render_conversion.assert_not_called()
        self.assertEqual(len(calls), 6)
        self.assertTrue(all(call["Sources"][0]["content"] == source_input.samples[0].content for call in calls))
        archived = json.loads((self.path / "subject_build_input.json").read_text())
        self.assertEqual(archived["Sources"][0]["content"], source_input.samples[0].content)
        self.assertTrue(result.extras["event_cascade_is_projection"])
        self.assertEqual(result.subject_graph["schema_version"], "subject-graph-1.0")
        self.assertEqual(json.loads((self.path/"FinalSubjectGraph.json").read_text()), result.subject_graph)
        from finmy.person_epg.adapter import to_subject_graph
        person_epg = json.loads((self.path/"FinalPersonEPG.json").read_text())
        self.assertEqual(person_epg, result.extras["person_epg"])
        self.assertEqual(person_epg["schema_version"], "person-epg-3.0")
        self.assertEqual(to_subject_graph(person_epg), result.subject_graph)
        self.assertEqual(person_epg["occurrence"][0]["occurrence_id"], result.subject_graph["events"][0]["event_id"])
        for table in ("domain", "event", "stage", "event_activity"):
            self.assertEqual(person_epg[table], [])
        self.assertEqual(json.loads((self.path/"FinalEventCascade.json").read_text()), result.event_cascades)
        self.assertEqual(len(result.event_cascades["stages"]), 2)
        self.assertTrue((self.path/"FinalSubjectGraph.html").is_file())
        self.assertFalse((self.path/"person_index.json").exists())


if __name__ == "__main__":
    unittest.main()
