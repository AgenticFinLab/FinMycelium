"""Native graph display contracts, independent of models and plotting libraries."""
import copy
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from finmy.subject_graph.visualizer import render_subject_graph, SubjectGraphVisualizer


def vf(value, quote=None):
    return {"value": value, "evidence_source_contents": [quote] if quote else [], "reasons": []}


def fixture():
    return {
        "schema_version": "subject-graph-1.0", "graph_id": "G1",
        "subject_id": "person_buffett", "subject_type": "individual",
        "coverage_start": "2022", "coverage_end": "2023",
        "title": vf("Buffett selected activities"), "descriptions": [],
        "entities": [
            {"entity_id": "person_buffett", "name": vf("Warren Buffett"),
             "aliases": ["巴菲特"], "entity_type": "individual", "attributes": {}},
            {"entity_id": "company_berkshire", "name": vf("Berkshire Hathaway"),
             "aliases": [], "entity_type": "organization", "attributes": {}},
        ],
        "events": [
            {"event_id": "E2", "title": vf("Company purchase"), "start_time": vf("2023-10-23"),
             "end_time": vf("2023-10-25"), "descriptions": [],
             "subject_relevance": vf("Related company activity, without personal trading attribution", "Buffett discussed this company investment."),
             "participations": [{"participation_id": "P2", "entity_id": "company_berkshire",
                                 "role": vf("buyer"), "start_time": vf("2023-10"), "end_time": vf("2023-10")}],
             "actions": [{"action_id": "A2", "actor_id": "company_berkshire", "action_type": vf("purchase shares"),
                          "timestamp": vf("2023-10"), "details": [vf("Purchase recorded", "Company bought shares.")]}],
             "transactions": [{"transaction_id": "T1", "name": vf("Stock purchase"),
                               "from_entity_id": vf("company_berkshire"), "to_entity_id": vf("unknown"),
                               "timestamp": vf("2023-10"), "instruments": [], "details": []}]},
            {"event_id": "E1", "title": vf("Public statement"), "start_time": vf("2023-05"),
             "end_time": vf("2023-05"), "descriptions": [],
             "subject_relevance": vf("Buffett spoke as an individual", "Buffett spoke."),
             "participations": [{"participation_id": "P1", "entity_id": "person_buffett",
                                 "role": vf("speaker"), "start_time": vf("2023-05"), "end_time": vf("2023-05")}],
             "actions": [{"action_id": "A1", "actor_id": "person_buffett", "action_type": vf("public statement"),
                          "timestamp": vf("2023-05"), "details": [vf("Statement recorded", "Buffett spoke.")]}],
             "transactions": []},
        ],
        "relations": [{"relation_id": "R1", "from_entity_id": "person_buffett",
                       "to_entity_id": "company_berkshire", "relation_type": vf("executive leadership"),
                       "valid_from": vf("unknown"), "valid_to": vf("unknown"), "event_ids": ["E1"]}],
    }


class SubjectGraphVisualizerTests(unittest.TestCase):
    def test_existing_gantt_is_used_with_controls_and_no_cards(self):
        graph = fixture()
        original = copy.deepcopy(graph)
        page = render_subject_graph(graph)
        self.assertEqual(graph, original)
        self.assertIn("Plotly.newPlot", page)
        self.assertIn("initControls", page)
        self.assertIn("plotly_clickannotation", page)
        self.assertIn("Warren Buffett", page)
        self.assertIn("Berkshire Hathaway", page)
        self.assertIn("Activities (Staggered)", page)
        self.assertNotIn("class=timeline", page)
        self.assertNotIn("class=subject-header", page)
        self.assertNotIn("背景关系未画为事件内连线", page)
        self.assertNotIn("人物经历 Gantt：", page)


    def test_unknown_dates_render(self):
        graph = fixture()
        for event in graph["events"]:
            event["start_time"] = vf("unknown")
            event["end_time"] = vf("unknown")
        self.assertIn("Plotly.newPlot", render_subject_graph(graph))


    def test_event_default_labels_unchanged(self):
        from finmy.subject_graph.compat import to_event_cascade
        from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
        fig = EventCascadeGanttVisualizer().plot_cascade(to_event_cascade(fixture()))
        self.assertEqual(fig.layout.yaxis.title.text, "Episodes (Staggered)")
        self.assertEqual(fig.layout.legend.title.text, "Participants")


    def test_actions_are_distinct_activities_with_the_actual_actor(self):
        from finmy.subject_graph.compat import to_event_cascade
        graph = fixture()
        event = graph["events"][1]
        event["actions"][0]["action_type"] = vf("Explained cash reserve policy")
        second = copy.deepcopy(event["actions"][0])
        second.update(action_id="A3", action_type=vf("Discussed investment risks"))
        event["actions"].append(second)
        original = copy.deepcopy(graph)
        stage = to_event_cascade(graph)["stages"][1]
        context, first, second = stage["episodes"]
        self.assertEqual(context["name"]["value"], "Event participation")
        self.assertNotEqual(context["descriptions"], event["descriptions"])
        self.assertEqual([first["name"]["value"], second["name"]["value"]],
                         ["Explained cash reserve policy", "Discussed investment risks"])
        for episode, action in zip((first, second), event["actions"]):
            self.assertEqual(episode["descriptions"], action["details"])
            self.assertEqual(episode["start_time"], action["timestamp"])
            self.assertEqual([p["name"]["value"] for p in episode["participants"]], ["Warren Buffett"])
            self.assertEqual(len(episode["participants"][0]["actions"]), 1)
            self.assertEqual(episode["participant_relations"], [])
        company_action = to_event_cascade(graph)["stages"][0]["episodes"][1]
        self.assertEqual(company_action["participants"][0]["name"]["value"], "Berkshire Hathaway")
        self.assertEqual(graph, original)


    def test_collapsed_events_expand_below_their_header_and_restore_exactly(self):
        from finmy.subject_graph.compat import to_event_cascade
        from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
        from finmy.subject_graph.gantt_collapse import set_expanded_events, figure_items
        graph = fixture()
        original = copy.deepcopy(graph)
        fig = EventCascadeGanttVisualizer().plot_cascade(
            to_event_cascade(graph), subject_name="Warren Buffett", subject_participant_id="P_1")
        model = fig.layout.meta["subject_collapse"]
        collapsed = fig.to_json()
        items = figure_items(fig)
        self.assertEqual([block["activity_count"] for block in model["blocks"]], [1, 1])
        for block in model["blocks"]:
            for kind, indices in block["header"].items():
                self.assertTrue(all(items[kind][i].visible for i in indices))
            for kind, indices in block["body"].items():
                self.assertTrue(all(items[kind][i].visible is False for i in indices))
        x_before = [trace.x for trace in fig.data]
        x_window = fig.layout.xaxis.range
        target = model["blocks"][0]
        set_expanded_events(fig, [target["id"]])
        self.assertEqual([trace.x for trace in fig.data], x_before)
        self.assertEqual(fig.layout.xaxis.range, x_window)
        header_y = fig.data[target["header"]["traces"][0]].y[0]
        for i in target["body"]["traces"]:
            self.assertTrue(fig.data[i].visible)
            self.assertTrue(all(y < header_y for y in fig.data[i].y if y is not None))
        self.assertTrue(fig.layout.annotations[target["header"]["annotations"][0]].text.startswith("▾ "))
        for other in model["blocks"][1:]:
            self.assertTrue(all(fig.data[i].visible is False for i in other["body"]["traces"]))
        set_expanded_events(fig, [])
        self.assertEqual(fig.to_json(), collapsed)
        self.assertEqual(graph, original)

    def test_subject_relations_remain_visible_when_events_are_collapsed(self):
        from test_subject_graph_schema import graph_fixture
        from finmy.subject_graph.compat import to_event_cascade
        from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
        from finmy.subject_graph.gantt_collapse import set_expanded_events
        graph = graph_fixture()
        duplicate = copy.deepcopy(graph["relations"][0])
        duplicate["relation_id"] = "REL_repeat"
        graph["relations"].append(duplicate)
        original = copy.deepcopy(graph)
        fig = EventCascadeGanttVisualizer().plot_cascade(
            to_event_cascade(graph), subject_name="Warren Buffett", subject_participant_id="P_1")
        blocks = {b["id"]: b for b in fig.layout.meta["subject_collapse"]["blocks"]}
        meeting, purchase = blocks["S1"], blocks["S2"]
        label = fig.layout.annotations[meeting["header"]["annotations"][0]]
        text = label.text.replace("<br>", " ")
        self.assertTrue(label.visible)
        self.assertIn("Warren Buffett — chairman of → Berkshire Hathaway", text)
        self.assertEqual(text.count("chairman of"), 1)
        self.assertEqual(meeting["activity_count"], 1)
        self.assertNotIn("chairman of", fig.layout.annotations[purchase["header"]["annotations"][0]].text)
        relations = [fig.data[i] for i in meeting["body"]["traces"]
                     if fig.data[i].legendgroup == "Relations"]
        self.assertTrue(relations)
        self.assertTrue(all(t.visible is False for t in relations))
        set_expanded_events(fig, ["S1"])
        self.assertTrue(all(t.visible for t in relations))
        self.assertIn("chairman of", label.text)
        set_expanded_events(fig, [])
        self.assertTrue(label.visible)
        self.assertEqual(label.text.replace("<br>", " "), text)
        self.assertEqual(graph, original)


if __name__ == "__main__":
    unittest.main()
