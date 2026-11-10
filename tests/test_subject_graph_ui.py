"""Offline UI routing, scope preservation, and historical SubjectGraph loading."""
import copy
import importlib.util
import json
import tempfile
import types
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    return result


class State(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def field(value, reasons=None):
    return {"value": value, "evidence_source_contents": [] if value == "unknown" else [value],
            "reasons": reasons or [], "confidence": None}


def graph():
    return {"schema_version": "subject-graph-1.0", "graph_id": "G1",
            "subject_id": "person_buffett", "subject_type": "individual",
            "coverage_start": "2022", "coverage_end": "2023", "title": field("Selected history"),
            "descriptions": [], "entities": [{"entity_id": "person_buffett",
                "name": field("Warren Buffett"), "aliases": [], "entity_type": "individual", "attributes": {}}],
            "events": [], "relations": []}


def config():
    return {"builder_config": {"builder_type": "AgentEventBuilder", "lm_name": "test-model",
        "reconstruction": {"mode": "person", "subject": {
            "subject_id": "person_buffett", "name": "Warren Buffett", "aliases": ["巴菲特"],
            "coverage_start": "2022", "coverage_end": "2023", "scope": "Documented activities"}}}}


class SubjectUITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.state = State(analysis_results=graph(), build_mode="agent_build", processing_status="idle")
        self.html = Mock()
        v1 = module("streamlit.components.v1", html=self.html)
        components = module("streamlit.components", v1=v1)
        self.st = module("streamlit", session_state=self.state, components=components,
            selectbox=lambda label, options, index, **kwargs: options[index],
            text_input=lambda label, value="", **kwargs: value,
            text_area=lambda label, value="", **kwargs: value,
            error=Mock(), caption=Mock(), info=Mock(), warning=Mock(), write=Mock(), json=Mock(),
            subheader=Mock(), markdown=Mock(), button=lambda *a, **k: False,
            download_button=Mock(), rerun=Mock(), spinner=lambda *a, **k: nullcontext())
        self.agent_renderer = Mock()
        self.class_renderer = Mock()
        self.history = load("subject_history_test", "finmy/web_ui/utils/history_loader.py")
        fake = {
            "finmy.web_ui": module("web_ui", __path__=[]),
            "finmy.web_ui.utils": module("utils", __path__=[]),
            "finmy.web_ui.components": module("components", __path__=[str(ROOT / "finmy/web_ui/components")]),
            "finmy.web_ui.utils.history_loader": self.history,
            "streamlit": self.st, "streamlit.components": components, "streamlit.components.v1": v1,
            "finmy.web_ui.styles": module("styles", BASE_STYLES="", CLASS_BUILD_STYLES=""),
            "finmy.web_ui.pages.results.agent_results": module("agent", AgentResultsRenderer=self.agent_renderer),
            "finmy.web_ui.pages.results.class_results": module("class", ClassResultsRenderer=self.class_renderer),
            "finmy.web_ui.components.config_uploader": module("config", ConfigUploader=object),
            "finmy.web_ui.components.input_forms": module("forms", KeywordInput=object,
                                                          StructuredDataUpload=object, AnalysisControls=object),
            "finmy.web_ui.utils.validators": module("validators", validate_analysis_inputs=lambda: True),
            "finmy.web_ui.services.reconstruction_service": module("service", ReconstructionService=object),
            "finmy.web_ui.state": module("state", SessionStateManager=object),
            "finmy.web_ui.utils.formatters": module("formatters", format_timestamp=lambda: "now"),
        }
        self.patcher = patch.dict("sys.modules", fake)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.history = load("subject_history_test", "finmy/web_ui/utils/history_loader.py")
        self.form = load("subject_form_test", "finmy/web_ui/components/subject_scope_form.py")
        self.results = load("subject_results_test", "finmy/web_ui/pages/results_page.py")

    def test_name_and_period_form_drops_hidden_constraints_without_mutating_config(self):
        original = config()
        original["builder_config"]["reconstruction"]["subject"]["scope"] = "OXY only"
        snapshot = copy.deepcopy(original)
        with patch.object(self.st, "selectbox", wraps=self.st.selectbox) as selector, \
             patch.object(self.st, "text_input", wraps=self.st.text_input) as inputs, \
             patch.object(self.st, "text_area", wraps=self.st.text_area) as areas:
            effective = self.form.render_subject_scope(original)
        self.assertEqual(selector.call_args.args[1], ["event", "person"])
        self.assertTrue(selector.call_args.kwargs["key"].startswith("person_input_"))
        self.assertEqual([call.args[0] for call in inputs.call_args_list], ["Person name", "Period"])
        areas.assert_not_called()
        subject = effective["builder_config"]["reconstruction"]["subject"]
        self.assertEqual(subject["name"], "Warren Buffett")
        self.assertEqual(subject["subject_id"], "person_buffett")
        self.assertEqual(subject["aliases"], [])
        self.assertEqual(subject["coverage_start"], "2022")
        self.assertEqual(subject["coverage_end"], "2023")
        self.assertNotIn("OXY", subject["scope"])
        self.assertEqual(effective["builder_config"]["lm_name"], "test-model")
        self.assertEqual(effective["search_config"]["mode"], "agent")
        self.assertTrue(effective["search_config"]["storyline_discovery"]["enabled"])
        self.assertFalse(effective["event_followup"]["enabled"])
        self.assertEqual(effective["all_content_config"]["max_content_length"], 120000)
        self.assertEqual(original, snapshot)
        self.assertIsNot(effective, original)


    def test_native_result_routes_by_shape_even_with_stale_agent_mode(self):
        page = self.results.ResultsPage
        with patch.object(page, "_render_history_file_selector"):
            page.render()
        self.html.assert_not_called()
        self.agent_renderer.render.assert_not_called()
        self.class_renderer.render.assert_not_called()
        downloads = self.st.download_button.call_args_list
        self.assertEqual([c.kwargs["file_name"] for c in downloads],
                         ["FinalSubjectGraph.json", "subject_timeline.html"])
        self.assertEqual(json.loads(downloads[0].kwargs["data"]), graph())

    def test_event_result_still_routes_to_existing_renderer(self):
        self.state.analysis_results = {"stages": [{"episodes": []}]}
        page = self.results.ResultsPage
        with patch.object(page, "_render_history_file_selector"):
            page.render()
        self.agent_renderer.render.assert_called_once_with(self.state.analysis_results)
        self.html.assert_not_called()


    def test_invalid_native_history_does_not_silently_load_projection(self):
        invalid = graph()
        invalid["subject_id"] = "missing_entity"
        (self.path / "FinalSubjectGraph.json").write_text(json.dumps(invalid))
        (self.path / "FinalEventCascade.json").write_text(json.dumps({"stages": []}))
        self.assertIsNone(self.history.load_history_result(str(self.path)))


    def test_pipeline_passes_effective_scope_and_sets_native_result_mode(self):
        pipeline = load("subject_pipeline_test", "finmy/web_ui/pages/pipeline_page.py")
        uploaded = config()
        effective = self.form.apply_subject_scope(uploaded, "person", self.form.person_subject(uploaded, "Warren Buffett", "2022–2023"))
        self.state.update(config=uploaded, reconstruction_run_config=effective,
                          main_input="A stale event request", keywords=["stale keyword"], structured_data=[{"old": "data"}])
        received = []
        class Service:
            def __init__(self, cfg):
                received.append(cfg)
            def run_reconstruction(self, **kwargs):
                received.append(kwargs)
                return graph()
        with patch.object(pipeline, "ReconstructionService", Service):
            pipeline.PipelinePage._run_analysis()
        self.assertIs(received[0], effective)
        self.assertEqual(received[1], {"main_input": "Warren Buffett 2022 – 2023", "keywords": [], "structured_data": None})
        self.assertEqual(self.state.build_mode, "subject_graph")
        self.assertEqual(self.state.processing_status, "completed")
        self.assertEqual(uploaded["builder_config"]["reconstruction"]["mode"], "person")


if __name__ == "__main__":
    unittest.main()
