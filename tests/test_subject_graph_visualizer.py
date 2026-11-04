"""Native graph display contracts, independent of models and plotting libraries."""
import copy
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

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

    def test_legacy_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "SubjectGraph"):
            render_subject_graph({"stages": []})


if __name__ == "__main__":
    unittest.main()
