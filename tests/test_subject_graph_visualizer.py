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

    def test_subject_time_notes_do_not_leak_into_event_rendering(self):
        from finmy.subject_graph.compat import to_event_cascade
        from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
        cascade = to_event_cascade(fixture())
        original = EventCascadeGanttVisualizer().plot_cascade(cascade).to_json()
        window = {"start": "2023-10-21", "end": "2023-10-31",
                  "original": "2023年10月下旬", "approximate": True}
        for stage in cascade["stages"]:
            stage["start_time"]["time_window"] = window
            for episode in stage["episodes"]:
                episode["start_time"]["time_window"] = window
        event = EventCascadeGanttVisualizer().plot_cascade(cascade)
        self.assertEqual(event.to_json(), original)
        person = EventCascadeGanttVisualizer().plot_cascade(cascade, subject_name="Warren Buffett")
        self.assertTrue(any("2023年10月下旬" in hover
                            for trace in person.data for hover in (trace.hovertext or [])))

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

    def test_subject_focus_survives_expansion_without_company_attribution(self):
        from finmy.subject_graph.compat import to_event_cascade
        from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
        graph = fixture()
        extra = copy.deepcopy(graph["events"][1])
        extra["event_id"] = "E3"
        extra["participations"][0]["participation_id"] = "P3"
        extra["actions"][0]["action_id"] = "A3"
        extra["actions"][0]["action_type"] = vf("Discussed investment risks")
        graph["events"].append(extra)
        original = copy.deepcopy(graph)
        fig = EventCascadeGanttVisualizer().plot_cascade(
            to_event_cascade(graph), subject_name="Warren Buffett", subject_participant_id="P_1")
        from finmy.subject_graph.gantt_collapse import set_expanded_events
        set_expanded_events(fig, [block["id"] for block in fig.layout.meta["subject_collapse"]["blocks"]])
        self.assertLessEqual(fig.layout.xaxis.range[0].date().isoformat(), "2023-05-01")
        self.assertGreaterEqual(fig.layout.xaxis.range[1].date().isoformat(), "2023-10-25")
        points = [(hover, y, size) for trace in fig.data
                  if trace.name.startswith("Participants (")
                  for hover, y, size in zip(trace.hovertext, trace.y, trace.marker.size)]
        actions = [(hover, y, size) for hover, y, size in points
                   if "Name: Warren Buffett" in hover and "Role: speaker" in hover]
        # Two simultaneous actions from different events occupy separate lanes.
        subject_labels = [a for a in fig.layout.annotations if a.text in
                          ("<b>public statement</b>", "<b>Discussed investment risks</b>")]
        self.assertEqual(len(subject_labels), 2)
        self.assertNotEqual(subject_labels[0].y, subject_labels[1].y)
        company_y = [y for hover, y, size in points if "Name: Berkshire Hathaway" in hover]
        self.assertGreater(min(a.y for a in subject_labels), max(company_y))
        self.assertTrue(all(size >= 9 for _, _, size in actions))
        self.assertTrue(all(hover.startswith("Actions:") for hover, _, _ in actions))
        self.assertTrue(all(hover.index("Event context:") < hover.index("Role:")
                            for hover, _, _ in actions))
        legends = [t for t in fig.data if t.showlegend and t.legendgroup == "Participants"]
        self.assertEqual(legends[0].name, "Warren Buffett (individual)")
        self.assertFalse(any(a.text == "<b>purchase shares</b>" for a in fig.layout.annotations))
        self.assertEqual(graph, original)

    def test_subject_focus_uses_id_even_when_entity_names_match(self):
        from finmy.subject_graph.compat import to_event_cascade
        from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
        graph = fixture()
        graph["entities"][1]["name"] = vf("Warren Buffett")
        fig = EventCascadeGanttVisualizer().plot_cascade(
            to_event_cascade(graph), subject_name="Warren Buffett", subject_participant_id="P_1")
        self.assertTrue(any(a.text == "<b>public statement</b>" for a in fig.layout.annotations))
        self.assertFalse(any(a.text == "<b>purchase shares</b>" for a in fig.layout.annotations))

    def test_person_event_titles_and_dates_do_not_pile_up_on_the_axis(self):
        from finmy.subject_graph.compat import to_event_cascade
        from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
        graph = fixture()
        extra = copy.deepcopy(graph["events"][1])
        extra["event_id"] = "E3"
        extra["title"] = vf("Another public statement at the same time with a long descriptive title")
        extra["participations"][0]["participation_id"] = "P3"
        extra["actions"][0]["action_id"] = "A3"
        graph["events"].append(extra)
        fig = EventCascadeGanttVisualizer().plot_cascade(
            to_event_cascade(graph), subject_name="Warren Buffett", subject_participant_id="P_1")
        events = [t for t in fig.data if t.name.startswith("Event:")]
        self.assertNotEqual(events[1].y[0], events[2].y[0])
        self.assertTrue(all(t.text is None for t in events))  # No rotated/shrunken bar text.
        titles = [a for a in fig.layout.annotations if " · " in a.text]
        self.assertEqual(len(titles), 3)
        self.assertTrue(all(a.font.size >= 12 and a.yanchor == "bottom" for a in titles))
        self.assertTrue(any("long descriptive title" in a.text.replace("<br>", " ") for a in titles))
        self.assertFalse(any(a.text.startswith("2023-") or a.text == "●" for a in fig.layout.annotations))
        self.assertTrue(any("Time: 2023-05" in text for t in fig.data for text in (t.hovertext or [])))

    def test_subject_lane_spacing_reserves_the_full_label_height(self):
        import pandas as pd
        from finmy.subject_graph.gantt_layout import arrange_subject_events, LABEL_LINE_HEIGHT, PIXELS_PER_UNIT
        rows = [{"Type": "Episode", "Group": "S1", "ID": f"E{i}", "IndexInStage": i + 1,
                 "Participants": [{"id": "P_1"}], "Title": "Discussed risk &amp; return " * (i + 1)}
                for i in range(5)]
        event = {"Type": "Stage", "Group": "S1", "ID": "S1", "StageName": "Meeting",
                 "StartRaw": "2023-05-06", "FinishRaw": "2023-05-06"}
        positions, _, upper = arrange_subject_events(
            rows, "P_1", lambda row: (pd.Timestamp("2023-05-06"), 0, False), events=[event])
        ordered = sorted(rows, key=lambda row: positions[(row["Group"], row["ID"])])
        for lower, higher in zip(ordered, ordered[1:]):
            bottom = positions[(lower["Group"], lower["ID"])]
            top = bottom + 0.46 + (5 + (lower["LabelText"].count("<br>") + 1) * LABEL_LINE_HEIGHT) / PIXELS_PER_UNIT
            next_bottom = positions[(higher["Group"], higher["ID"])] - 0.46 - 20 / PIXELS_PER_UNIT
            self.assertLess(top, next_bottom)
            self.assertIn("&amp;", lower["LabelText"])
        self.assertGreater(upper, positions[(rows[-1]["Group"], rows[-1]["ID"])])

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

    def test_relation_summary_preserves_all_edges_and_prioritizes_subject(self):
        from finmy.subject_graph.gantt_layout import event_relation_summaries
        rows = [{"Relations": [
            {"src": "P2", "dst": "P3", "name": "owns"},
            {"src": "P2", "dst": "P1", "name": "advises"},
            {"src": "P2", "dst": "P1", "name": "advises"},
            {"src": "P1", "dst": "P2", "name": "advises"},
            {"src": "P2", "dst": "P3", "name": "owns"},
        ]}]
        summaries = event_relation_summaries(rows, "P1", {"P1": "Subject", "P2": "Other", "P3": "Company"})
        self.assertEqual(summaries, ["Other — advises → Subject", "Subject — advises → Other",
                                     "Other — owns → Company"])

    def test_person_and_company_relations_survive_folding(self):
        from test_subject_graph_schema import graph_fixture, entity, participation
        from finmy.subject_graph.compat import to_event_cascade
        from finmy.subject_graph.gantt_collapse import set_expanded_events
        from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
        graph = graph_fixture()
        graph["entities"].append(entity("person_munger", "Charlie Munger", "individual"))
        graph["events"][0]["participations"].append(
            participation("PAR_munger", "person_munger", "speaker"))
        for identifier, source, target, label in [
            ("R_partner", graph["subject_id"], "person_munger", "Colleague and partner at Berkshire Hathaway"),
            ("R_vice", "person_munger", "org_berkshire", "Vice Chairman"),
        ]:
            relation = copy.deepcopy(graph["relations"][0])
            relation.update(relation_id=identifier, from_entity_id=source,
                            to_entity_id=target, relation_type=vf(label))
            graph["relations"].append(relation)
        original = copy.deepcopy(graph)
        fig = EventCascadeGanttVisualizer().plot_cascade(
            to_event_cascade(graph), subject_name="Warren Buffett", subject_participant_id="P_1")
        block = next(b for b in fig.layout.meta["subject_collapse"]["blocks"] if b["id"] == "S1")
        label = fig.layout.annotations[block["header"]["annotations"][0]]
        text = label.text.replace("<br>", " ")
        self.assertIn("Warren Buffett — Colleague and partner at Berkshire Hathaway → Charlie Munger", text)
        self.assertIn("Charlie Munger — Vice Chairman → Berkshire Hathaway", text)
        legends = [t.name for t in fig.data if t.showlegend and t.legendgroup == "Relations"]
        self.assertIn("Colleague and partner at<br>Berkshire Hathaway", legends)
        relations = [fig.data[i] for i in block["body"]["traces"]
                     if fig.data[i].legendgroup == "Relations"]
        self.assertEqual(len(relations), 3)
        self.assertTrue(all(t.visible is False for t in relations))
        set_expanded_events(fig, ["S1"])
        self.assertTrue(all(t.visible for t in relations))
        set_expanded_events(fig, [])
        self.assertEqual(label.text.replace("<br>", " "), text)
        self.assertEqual(graph, original)

    def test_legacy_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "SubjectGraph"):
            render_subject_graph({"stages": []})


if __name__ == "__main__":
    unittest.main()
