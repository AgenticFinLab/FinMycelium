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
        fake = {
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

    def test_name_only_form_drops_hidden_constraints_without_mutating_config(self):
        original = config()
        original["builder_config"]["reconstruction"]["subject"]["scope"] = "OXY only"
        snapshot = copy.deepcopy(original)
        with patch.object(self.st, "selectbox", wraps=self.st.selectbox) as selector, \
             patch.object(self.st, "text_input", wraps=self.st.text_input) as inputs, \
             patch.object(self.st, "text_area", wraps=self.st.text_area) as areas:
            effective = self.form.render_subject_scope(original)
        self.assertEqual(selector.call_args.args[1], ["event", "person"])
        self.assertTrue(selector.call_args.kwargs["key"].startswith("person_input_"))
        self.assertEqual([call.args[0] for call in inputs.call_args_list], ["Person name"])
        areas.assert_not_called()
        subject = effective["builder_config"]["reconstruction"]["subject"]
        self.assertEqual(subject["name"], "Warren Buffett")
        self.assertEqual(subject["subject_id"], "person_buffett")
        self.assertEqual(subject["aliases"], [])
        self.assertIsNone(subject["coverage_start"])
        self.assertIsNone(subject["coverage_end"])
        self.assertNotIn("OXY", subject["scope"])
        self.assertEqual(effective["builder_config"]["lm_name"], "test-model")
        self.assertEqual(original, snapshot)
        self.assertIsNot(effective, original)

    def test_old_company_configuration_opens_in_event_mode_without_person_fields(self):
        original = config()
        original["builder_config"]["reconstruction"]["mode"] = "company"
        with patch.object(self.st, "text_input", wraps=self.st.text_input) as inputs:
            result = self.form.render_subject_scope(original)
        inputs.assert_not_called()
        self.assertEqual(result["builder_config"]["reconstruction"], {"mode": "event"})
        self.assertEqual(result["builder_config"]["lm_name"], "test-model")
        self.assertEqual(original["builder_config"]["reconstruction"]["mode"], "company")

    def test_hidden_malformed_fields_do_not_block_name_only_form(self):
        original = config()
        original["builder_config"]["reconstruction"]["subject"].update(
            aliases=[123], coverage_start="invalid", coverage_end=False, scope=None)
        self.assertIsNotNone(self.form.render_subject_scope(original))
        self.st.error.assert_not_called()

    def test_generated_identity_is_stable_and_changes_with_person(self):
        original = config()
        self.assertEqual(self.form.person_subject(original, " WARREN   BUFFETT ")["subject_id"],
                         "person_buffett")
        self.assertEqual(self.form.person_subject(original, "巴菲特")["subject_id"], "person_buffett")
        new = self.form.person_subject(original, "张三")
        self.assertEqual(new, self.form.person_subject(original, "张三"))
        self.assertNotEqual(new["subject_id"], "person_buffett")
        self.assertNotEqual(new["subject_id"], self.form.person_subject(original, "李四")["subject_id"])
        effective = self.form.apply_subject_scope(original, "person", new)
        self.assertEqual(effective["builder_config"]["reconstruction"]["subject"]["name"], "张三")

    def test_blank_name_keeps_description_keywords_visible_and_cannot_start(self):
        pipeline = load("subject_pipeline_blank_test", "finmy/web_ui/pages/pipeline_page.py")
        uploaded = config()
        self.state.update(config=uploaded, config_file_name="config.yml", main_input="Existing description")
        keywords = Mock()
        controls = Mock()
        controls.render.return_value = True
        uploader = Mock()
        uploader.render.return_value = (True, uploaded)
        with patch.object(pipeline, "ConfigUploader", uploader), \
             patch.object(pipeline, "KeywordInput", keywords), \
             patch.object(pipeline, "AnalysisControls", controls), \
             patch.object(pipeline, "render_subject_scope", self.form.render_subject_scope), \
             patch.object(pipeline, "ReconstructionService") as service, \
             patch.object(self.st, "text_input", return_value=" "), \
             patch.object(self.st, "text_area", wraps=self.st.text_area) as areas, \
             patch.object(self.st, "success", Mock(), create=True), \
             patch.object(self.st, "multiselect", return_value=["Keywords"], create=True):
            pipeline.PipelinePage.render()
            self.assertEqual(areas.call_args.args[0], "Description")
            keywords.render.assert_called_once()
            self.assertEqual(self.state.main_input, "Existing description")
            self.assertIsNone(self.state.reconstruction_run_config)
            pipeline.PipelinePage._run_analysis()
            service.assert_not_called()
        self.assertEqual(self.state.processing_status, "idle")
        self.assertIn("person name", self.st.error.call_args.args[0])

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

    def test_history_prefers_native_graph_and_detects_mode(self):
        (self.path / "FinalSubjectGraph.json").write_text(json.dumps(graph()))
        (self.path / "FinalEventCascade.json").write_text(json.dumps({"stages": []}))
        result = self.history.load_history_result(str(self.path))
        self.assertEqual(result, graph())
        self.assertEqual(self.history.detect_build_mode(result), "subject_graph")
        self.assertEqual(self.history.detect_build_mode({"stages": [{"episodes": []}]}), "agent_build")

    def test_invalid_native_history_does_not_silently_load_projection(self):
        invalid = graph()
        invalid["subject_id"] = "missing_entity"
        (self.path / "FinalSubjectGraph.json").write_text(json.dumps(invalid))
        (self.path / "FinalEventCascade.json").write_text(json.dumps({"stages": []}))
        self.assertIsNone(self.history.load_history_result(str(self.path)))

    def test_native_filename_requires_a_valid_schema_version(self):
        invalid = graph()
        invalid.pop("schema_version")
        (self.path / "FinalSubjectGraph.json").write_text(json.dumps(invalid))
        self.assertIsNone(self.history.load_history_result(str(self.path)))

    def test_native_only_run_is_found_by_history_scanner(self):
        folder = self.path / "build_output_20261103"
        folder.mkdir()
        (folder / "FinalSubjectGraph.json").write_text(json.dumps(graph()))
        self.assertEqual(self.history.scan_history_files(str(self.path))[0]["path"], str(folder))

    def test_pipeline_passes_effective_scope_and_sets_native_result_mode(self):
        pipeline = load("subject_pipeline_test", "finmy/web_ui/pages/pipeline_page.py")
        uploaded = config()
        effective = self.form.apply_subject_scope(uploaded, "person", self.form.person_subject(uploaded, "Warren Buffett"))
        self.state.update(config=uploaded, reconstruction_run_config=effective,
                          main_input="Reconstruct Buffett's activities in 2022–2023", keywords=[], structured_data=None)
        received = []
        class Service:
            def __init__(self, cfg):
                received.append(cfg)
            def run_reconstruction(self, **kwargs):
                return graph()
        with patch.object(pipeline, "ReconstructionService", Service):
            pipeline.PipelinePage._run_analysis()
        self.assertIs(received[0], effective)
        self.assertEqual(self.state.build_mode, "subject_graph")
        self.assertEqual(self.state.processing_status, "completed")
        self.assertEqual(uploaded["builder_config"]["reconstruction"]["mode"], "person")


if __name__ == "__main__":
    unittest.main()
