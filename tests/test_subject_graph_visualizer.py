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
        self.assertIn("Warren Buffett", page)
        self.assertIn("Berkshire Hathaway", page)
        self.assertIn("Activities (Staggered)", page)
        self.assertNotIn("class=timeline", page)
        self.assertNotIn("class=subject-header", page)
        self.assertNotIn("背景关系未画为事件内连线", page)
        self.assertNotIn("人物经历 Gantt：", page)

    def test_precomputed_cascade_reuses_identical_render_input(self):
        from finmy.subject_graph.compat import to_event_cascade
        from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
        graph = fixture()
        graph["entities"][0]["name"]["value"] = "Warren <Buffett>"
        cascade = to_event_cascade(graph)
        original = copy.deepcopy(cascade)
        rendered = []

        def plot(value, target, **kwargs):
            rendered.append((copy.deepcopy(value), kwargs))
            Path(target).write_text("<html>same gantt</html>", encoding="utf-8")

        with patch.object(EventCascadeGanttVisualizer, "plot_cascade", side_effect=plot):
            expected = render_subject_graph(graph)
            with patch("finmy.subject_graph.visualizer.to_event_cascade") as convert:
                actual = render_subject_graph(graph, event_cascade=cascade)
                convert.assert_not_called()
        self.assertEqual(actual, expected)
        self.assertEqual(rendered[0], rendered[1])
        self.assertEqual(cascade, original)

    def test_unknown_dates_render(self):
        graph = fixture()
        for event in graph["events"]:
            event["start_time"] = vf("unknown")
            event["end_time"] = vf("unknown")
        self.assertIn("Plotly.newPlot", render_subject_graph(graph))

    def test_empty_graph_and_exact_file_write(self):
        graph = fixture()
        graph["events"] = []
        graph["relations"] = []
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "nested" / "gantt.html"
            page = SubjectGraphVisualizer().plot_graph(graph, target)
            self.assertEqual(target.read_text(), page)
            self.assertIn("没有已记录的经历", page)

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

    def test_single_day_event_is_a_marker_and_duration_event_stays_a_bar(self):
        from finmy.subject_graph.compat import to_event_cascade
        from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
        graph = fixture()
        graph["events"][1]["start_time"] = vf("2023-05-06")
        graph["events"][1]["end_time"] = vf("2023-05-06")
        graph["events"][1]["actions"][0]["timestamp"] = vf("2023-05-06")
        cascade = to_event_cascade(graph)
        fig = EventCascadeGanttVisualizer().plot_cascade(cascade, subject_name="Warren Buffett")
        event_traces = [t for t in fig.data if t.name.startswith("Event:")]
        self.assertEqual([t.name for t in event_traces], ["Event: S1", "Event: S2"])
        self.assertEqual(event_traces[0].type, "bar")
        self.assertEqual(event_traces[0].x[0], 2 * 86400000)
        self.assertEqual(event_traces[1].type, "scatter")
        self.assertEqual(str(event_traces[1].x[0])[:10], "2023-05-06")
        labels = " ".join(t.name or "" for t in fig.data)
        self.assertNotIn("STAGE:", labels)
        self.assertNotIn("Activitys", labels)
        self.assertIn("Activities", labels)
        legacy = EventCascadeGanttVisualizer().plot_cascade(cascade)
        self.assertEqual([t.type for t in legacy.data if t.name.startswith("Stage:")],
                         ["bar", "bar"])

    def test_equivalent_role_labels_share_one_legend_entry(self):
        from finmy.subject_graph.compat import to_event_cascade
        from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
        from test_subject_graph_schema import graph_fixture
        graph = graph_fixture()
        graph["relations"][0]["relation_type"]["value"] = "Chairman and CEO"
        other = copy.deepcopy(graph["relations"][0])
        other["relation_id"] = "R_alias"
        other["relation_type"]["value"] = "Chief Executive Officer and Chairman"
        graph["relations"].append(other)
        original = copy.deepcopy(graph)
        fig = EventCascadeGanttVisualizer().plot_cascade(
            to_event_cascade(graph), subject_name="Warren Buffett")
        names = [t.name for t in fig.data if t.showlegend]
        self.assertEqual(names.count("Chairman and CEO"), 1)
        self.assertFalse(any("Chief Executive" in name for name in names))
        self.assertEqual(graph, original)

    def test_person_hover_includes_action_details_time_and_event_context(self):
        from finmy.subject_graph.compat import to_event_cascade
        from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
        graph = fixture()
        graph["events"][1]["descriptions"] = [vf("The discussion concerned liquidity needs.")]
        graph["events"][1]["actions"][0]["details"] = [vf("Cash was retained to meet obligations.")]
        original = copy.deepcopy(graph)
        fig = EventCascadeGanttVisualizer().plot_cascade(
            to_event_cascade(graph), subject_name="Warren Buffett")
        hovers = [text for trace in fig.data for text in (trace.hovertext or [])]
        person_hover = next(text for text in hovers if "Name: Warren Buffett" in text)
        self.assertIn("Cash was retained to meet obligations.", person_hover)
        self.assertIn("Time: 2023-05", person_hover)
        self.assertIn("Event context:<br>The discussion", person_hover.replace("- ", ""))
        activity = next(text for text in hovers if text.startswith("Activity: public statement"))
        self.assertIn("Cash was retained to meet obligations.", activity)
        self.assertIn("The discussion concerned liquidity needs.", activity)
        self.assertEqual(graph, original)
        graph["events"][1]["actions"][0]["details"] = []
        fig = EventCascadeGanttVisualizer().plot_cascade(
            to_event_cascade(graph), subject_name="Warren Buffett")
        self.assertTrue(any("Details:<br>Not documented in supplied sources." in text
                            for trace in fig.data for text in (trace.hovertext or [])
                            if "Name: Warren Buffett" in text))
        legacy = EventCascadeGanttVisualizer().plot_cascade(to_event_cascade(original))
        self.assertFalse(any("Event context:" in text for trace in legacy.data
                             for text in (trace.hovertext or [])))

    def test_legacy_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "SubjectGraph"):
            render_subject_graph({"stages": []})


if __name__ == "__main__":
    unittest.main()
