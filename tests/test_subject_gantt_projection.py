"""Person Gantt projection preserves native facts without changing graph semantics."""
import copy
import json
import unittest

from finmy.subject_graph.compat import to_event_cascade
from finmy.subject_graph.gantt_projection import prepare_gantt_cascade
from test_subject_graph_schema import entity, field, graph_fixture


class SubjectGanttProjectionTests(unittest.TestCase):
    def test_contextual_relation_has_display_endpoints_without_fabricated_participation(self):
        graph = graph_fixture()
        graph["relations"][0]["event_ids"].append("EV_purchase")
        cascade = to_event_cascade(graph)
        before_graph, before_cascade = copy.deepcopy(graph), copy.deepcopy(cascade)

        displayed = prepare_gantt_cascade(graph, cascade)
        context = displayed["stages"][1]["episodes"][0]
        self.assertEqual(len(context["participant_relations"]), 1)
        relation = context["participant_relations"][0]
        self.assertEqual(relation["_subject"]["relation"], graph["relations"][0])
        self.assertTrue(relation["_subject"]["contextual"])
        node_ids = {p["participant_id"] for p in context["participants"]}
        self.assertIn(relation["from_participant_id"], node_ids)
        self.assertIn(relation["to_participant_id"], node_ids)
        buffett = next(p for p in context["participants"]
                       if p["_subject"]["entity"]["entity_id"] == graph["subject_id"])
        self.assertEqual(buffett["base_role"]["value"], "Related entity")
        self.assertEqual(buffett["actions"], [])
        self.assertEqual(buffett["_subject"]["participations"], [])
        self.assertEqual(graph, before_graph)
        self.assertEqual(cascade, before_cascade)
        self.assertEqual(cascade["stages"][1]["episodes"][0]["participant_relations"], [])

    def test_native_metadata_retains_aliases_participation_times_and_review_state(self):
        graph = graph_fixture()
        graph["entities"][0]["aliases"] = ["Warren E. Buffett", "巴菲特"]
        graph["descriptions"] = [field("Subject overview")]
        participation = graph["events"][0]["participations"][0]
        participation["start_time"] = field("2023-05-02")
        participation["end_time"] = field("2023-05-03")
        action_type = graph["events"][0]["actions"][0]["action_type"]
        action_type["evidence_status"] = "needs_review"
        action_type["confidence"] = None
        cascade = to_event_cascade(graph)

        displayed = prepare_gantt_cascade(graph, cascade)
        node = next(p for p in displayed["stages"][0]["episodes"][0]["participants"]
                    if p["_subject"]["entity"]["entity_id"] == graph["subject_id"])
        self.assertEqual(node["_subject"]["entity"]["aliases"], ["Warren E. Buffett", "巴菲特"])
        self.assertEqual(node["_subject"]["participations"], [participation])
        self.assertIn("Subject overview", json.dumps(displayed))
        self.assertIn('"evidence_status": "needs_review"', json.dumps(displayed))
        self.assertNotIn('"evidence_status": "needs_review"', json.dumps(cascade))
        self.assertEqual(node["actions"][0]["name"]["value"], action_type["value"])

    def test_transaction_row_preserves_window_parties_and_unique_instrument_reference(self):
        graph = graph_fixture()
        graph["entities"].append(entity("org_byd", "BYD Co", "organization"))
        transaction = graph["events"][1]["transactions"][0]
        transaction["instruments"] = [field("BYD H shares")]
        transaction["timestamp"] = field("unknown", None)
        transaction["timestamp"]["time_window"] = {
            "start": "2023-05-01", "end": "2023-05-14",
            "original": "the first two weeks of May 2023", "approximate": True,
        }
        cascade = to_event_cascade(graph)
        before_graph, before_cascade = copy.deepcopy(graph), copy.deepcopy(cascade)

        displayed = prepare_gantt_cascade(graph, cascade)
        episodes = displayed["stages"][1]["episodes"]
        transactions = [ep for ep in episodes if ep.get("_subject", {}).get("kind") == "transaction"]
        self.assertEqual(len(transactions), 1)
        row = transactions[0]
        self.assertIs(row, episodes[-1])
        self.assertEqual(row["episode_id"], "E2_T1")
        self.assertEqual(row["_subject"]["transaction"], transaction)
        self.assertEqual(row["start_time"]["value"], "2023-05-01")
        self.assertEqual(row["end_time"]["value"], "2023-05-14")
        self.assertEqual(row["start_time"]["time_window"], transaction["timestamp"]["time_window"])
        self.assertEqual({p["name"]["value"] for p in row["participants"]},
                         {"Berkshire Hathaway", "BYD Co"})
        instrument = next(p for p in row["participants"] if p["name"]["value"] == "BYD Co")
        self.assertEqual(instrument["_subject"]["participations"], [])
        self.assertEqual(instrument["actions"], [])
        self.assertEqual(row["_subject"]["transaction"]["to_entity_id"]["value"], "unknown")
        self.assertEqual(graph, before_graph)
        self.assertEqual(cascade, before_cascade)

    def test_ambiguous_instrument_reference_does_not_create_a_display_party(self):
        graph = graph_fixture()
        graph["entities"].append(entity("org_byd", "BYD Co", "organization"))
        other = entity("org_other", "Other Corporation", "organization")
        other["aliases"] = ["BYD"]
        graph["entities"].append(other)
        graph["events"][1]["transactions"][0]["instruments"] = [field("BYD H shares")]

        displayed = prepare_gantt_cascade(graph, to_event_cascade(graph))
        row = next(ep for ep in displayed["stages"][1]["episodes"]
                   if ep.get("_subject", {}).get("kind") == "transaction")
        self.assertEqual([p["name"]["value"] for p in row["participants"]], ["Berkshire Hathaway"])
        self.assertEqual(row["_subject"]["transaction"]["to_entity_id"]["value"], "unknown")

    def test_unknown_transaction_time_is_not_replaced_by_event_dates(self):
        graph = graph_fixture()
        graph["events"][1]["transactions"][0]["timestamp"] = field("unknown", None)
        displayed = prepare_gantt_cascade(graph, to_event_cascade(graph))
        row = next(ep for ep in displayed["stages"][1]["episodes"]
                   if ep.get("_subject", {}).get("kind") == "transaction")
        self.assertEqual(row["start_time"]["value"], "unknown")
        self.assertEqual(row["end_time"]["value"], "unknown")

    def test_global_relations_do_not_acquire_event_membership(self):
        graph = graph_fixture()
        graph["relations"][0]["event_ids"] = []
        before = copy.deepcopy(graph)
        displayed = prepare_gantt_cascade(graph, to_event_cascade(graph))
        self.assertTrue(all(not stage["episodes"][0]["participant_relations"]
                            for stage in displayed["stages"]))
        self.assertEqual(graph, before)


if __name__ == "__main__":
    unittest.main()
