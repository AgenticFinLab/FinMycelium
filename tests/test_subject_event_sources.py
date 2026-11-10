"""Offline regression for two annual meetings with conflicting evidence dates."""
import copy
import types
import unittest

from finmy.subject_graph.build import run_subject_build
from finmy.subject_graph.event_sources import select_event_sources, restrict_event_evidence
from test_subject_graph_builder import config, fixture, vf


MEETING_22 = "2022年4月30日，Warren Buffett 在年度股东大会发言。"
MEETING_23 = "2023年5月6日，Warren Buffett 在年度股东大会发言。"
CASH = "我们是绝对相信现金的。在3月31日的时候，我们的现金就像我们的氧气一样。"
PROFIT = "我们在今年第一季度营业利润略超80亿美元。"
FLOAT = "我们现在的浮存金已经有1650亿美元之多。"


class EventSourceTests(unittest.TestCase):
    def setUp(self):
        self.sources = [{"source_id": "DOC_2022", "content": MEETING_22 + CASH},
                        {"source_id": "DOC_2023", "content": MEETING_23 + PROFIT + FLOAT}]
        self.plan, self.events = fixture()
        self.plan["entities"] = [self.plan["entities"][0]]
        self.plan["entities"][0]["name"] = vf("Warren Buffett", "Warren Buffett")
        for i, (event, date, quote) in enumerate(zip(
                self.events, ("2022-04-30", "2023-05-06"), (MEETING_22, MEETING_23))):
            event["title"] = vf(f"Annual meeting {date[:4]}", quote)
            event["start_time"] = vf(date, quote)
            event["end_time"] = vf(date, quote)
            event["subject_relevance"] = vf("Buffett spoke at the meeting", quote)
            event["descriptions"] = [vf("Annual meeting", quote)]
            part = event["participations"][0]
            part.update(entity_id="buffett", role=vf("speaker", quote),
                        start_time=vf(date, quote), end_time=vf(date, quote))
            action = event["actions"][0]
            action.update(actor_id="buffett", timestamp=vf(date, quote),
                          action_type=vf("Explained cash policy" if i == 0 else "Reviewed profits",
                                         CASH if i == 0 else PROFIT),
                          details=[vf("Cash is like oxygen" if i == 0 else "Profit exceeded $8 billion",
                                      CASH if i == 0 else PROFIT)])
        self.plan["events"] = [{**copy.deepcopy(e), "participations": [], "actions": []}
                               for e in self.events]
        self.plan["event_sources"] = {"E1": ["DOC_2022"], "E2": ["DOC_2023"]}
        self.cfg = config()
        self.cfg["reconstruction"]["subject"]["coverage_start"] = "2022"
        self.inp = types.SimpleNamespace(
            user_query=types.SimpleNamespace(query_text="Buffett 2022-2023", key_words=[]),
            samples=[types.SimpleNamespace(sample_id=s["source_id"], content=s["content"])
                     for s in self.sources])
        self.saved, self.calls = {}, []

    def save(self, value, name):
        self.saved[name] = copy.deepcopy(value)

    def complete(self, name, system, payload):
        self.calls.append((name, payload))
        if name == "SubjectPlanner":
            return copy.deepcopy(self.plan)
        if name == "SubjectGraphRepair":
            return {"patches": []}
        if name in ("SubjectCoverageReviewer", "SubjectEventReviewer"):
            return {"event_additions": [], "missing_events": []}
        return {"event": copy.deepcopy(next(e for e in self.events
                                            if e["event_id"] == payload["TargetEvent"]["event_id"])),
                "relations": []}

    def test_routes_sources_per_occurrence_with_one_coverage_review(self):
        original = copy.deepcopy(self.events)
        graph, state, report = run_subject_build(self.inp, self.cfg, self.complete, self.save)
        self.assertTrue(report["valid"], report)
        self.assertEqual(graph["events"], original)
        self.assertEqual(len(self.calls), 6)
        self.assertEqual([s["source_id"] for s in self.calls[1][1]["Sources"]], ["DOC_2022"])
        self.assertEqual([s["source_id"] for s in self.calls[2][1]["Sources"]], ["DOC_2023"])
        self.assertEqual([s["source_id"] for s in self.calls[3][1]["Sources"]], ["DOC_2022"])
        self.assertEqual([s["source_id"] for s in self.calls[4][1]["Sources"]], ["DOC_2023"])
        self.assertEqual([name for name, _ in self.calls].count("SubjectEventReviewer"), 2)
        self.assertEqual(self.saved["subject_event_sources"], {"E1": ["DOC_2022"], "E2": ["DOC_2023"]})
        self.assertEqual(self.saved["subject_event_evidence_review"], [])

    def test_replayed_wrong_year_and_compound_action_are_quarantined(self):
        wrong = copy.deepcopy(self.events[0]["actions"][0])
        wrong.update(action_id="E1_A2", action_type=vf("Reviewed profits", PROFIT),
                     details=[vf("Profit exceeded $8 billion", PROFIT)])
        mixed = copy.deepcopy(wrong)
        mixed.update(action_id="E1_A3", action_type=vf("Discussed float and cash", FLOAT),
                     details=[{"value": "Float was $165 billion and cash is like oxygen",
                               "evidence_source_contents": [FLOAT, CASH], "reasons": []}])
        self.events[0]["actions"].extend([wrong, mixed])
        graph, _, report = run_subject_build(self.inp, self.cfg, self.complete, self.save)
        self.assertTrue(report["valid"], report)
        self.assertEqual([a["action_id"] for a in graph["events"][0]["actions"]], ["E1_A1"])
        self.assertEqual(graph["events"][1], self.events[1])
        self.assertEqual(len(self.saved["RawSubjectGraph"]["events"][0]["actions"]), 3)
        review = self.saved["subject_event_evidence_review"]
        self.assertEqual(len(review), 2)
        self.assertEqual(review[0]["record"], wrong)
        self.assertEqual(review[1]["conflicting_quotes"], [FLOAT])
        self.assertEqual(review[0]["source_ids"], ["DOC_2023"])
        self.assertTrue(report["warnings"])
        self.assertEqual(len(self.calls), 6)


    def test_shared_multi_event_source_remains_available_for_both(self):
        shared = {"source_id": "BOTH", "content": self.sources[0]["content"] + self.sources[1]["content"]}
        for target in self.plan["events"]:
            self.assertEqual(select_event_sources(target, [shared]), [shared])


    def test_missing_anchor_skips_details_without_global_fallback(self):
        self.plan["event_sources"]["E1"] = []
        graph, _, report = run_subject_build(self.inp, self.cfg, self.complete, self.save)
        self.assertTrue(report["valid"], report)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(graph["events"], [self.events[1]])
        self.assertEqual(self.saved["subject_event_sources"], {"E1": [], "E2": ["DOC_2023"]})
        self.assertTrue(any("skipped" in w["message"] for w in report["warnings"]))


    def test_legacy_plan_uses_identifying_evidence_with_warning(self):
        self.plan.pop("event_sources")
        graph, _, report = run_subject_build(self.inp, self.cfg, self.complete, self.save)
        self.assertTrue(report["valid"], report)
        self.assertEqual(graph["events"], self.events)
        self.assertTrue(any("Planner omitted event_sources" in w["message"] for w in report["warnings"]))


    def test_out_of_event_action_dates_are_archived_without_failing_the_build(self):
        for date in ("2020", "2022-05-01", "2023-05-06"):
            with self.subTest(date=date):
                self.setUp()
                # The wording exists in an allowed document: source matching alone
                # does not establish that this date belongs to the current event.
                self.events[0]["actions"][0]["timestamp"]["value"] = date
                original = copy.deepcopy(self.events[0]["actions"][0])
                graph, state, report = run_subject_build(self.inp, self.cfg, self.complete, self.save)
                self.assertTrue(report["valid"], report)
                self.assertEqual(graph["events"][0]["actions"], [])
                self.assertEqual(graph["events"][1], self.events[1])
                self.assertEqual(graph["events"][0]["start_time"], self.plan["events"][0]["start_time"])
                review = self.saved["subject_event_evidence_review"]
                self.assertEqual(review[0]["record"], original)
                self.assertIn("date is outside", review[0]["message"])
                self.assertEqual(self.saved["RawSubjectGraph"]["events"][0]["actions"][0], original)
                self.assertTrue(any("event attribution needs review" in w["message"] for w in report["warnings"]))
                self.assertNotIn("SubjectGraphRepair", state["agent_executed"])


if __name__ == "__main__":
    unittest.main()
