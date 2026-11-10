"""Offline checks that live and saved results retain the stored person hierarchy."""

import ast
import copy
import importlib.util
import json
import logging
from pathlib import Path
import tempfile
import traceback
from types import SimpleNamespace
from typing import Any, Dict, List
import unittest
from unittest.mock import Mock, patch

from finmy.person_epg.compat_projection import project_person_epg
from finmy.person_epg.visualizer import render_person_epg
from finmy.reconstruction_scope import read_reconstruction


ROOT = Path(__file__).resolve().parents[1]


def load_history():
    path = ROOT / "finmy/web_ui/utils/history_loader.py"
    spec = importlib.util.spec_from_file_location("person_render_history", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_pipeline_method(namespace):
    """Execute the production method without importing search/model/UI providers."""
    path = ROOT / "finmy/web_ui/services/reconstruction_service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    service = next(node for node in tree.body
                   if isinstance(node, ast.ClassDef) and node.name == "ReconstructionService")
    method = next(node for node in service.body
                  if isinstance(node, ast.FunctionDef) and node.name == "_run_pipeline")
    module = ast.Module(body=[method], type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)
    return namespace["_run_pipeline"]


class PersonRenderRoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = json.loads((ROOT / "tests/fixtures/buffett_person_epg_preview.json").read_text())
        cls.projection = project_person_epg(cls.package)

    def setUp(self):
        self.history = load_history()
        self.st = SimpleNamespace(session_state=SimpleNamespace(), write=Mock(), error=Mock())
        self.pipeline = Mock()
        self.namespace = {
            "logging": logging, "traceback": traceback, "st": self.st,
            "format_timestamp": lambda: "offline", "estimate_complete_time": lambda **kwargs: 1,
            "read_reconstruction": read_reconstruction, "FinmyPipeline": Mock(return_value=self.pipeline),
            "List": List, "Dict": Dict, "Any": Any,
        }
        self.run_pipeline = load_pipeline_method(self.namespace)

    def run_result(self, output, mode="person"):
        config = {"builder_config": {"builder_type": "AgentEventBuilder",
                  "reconstruction": {"mode": mode}}}
        if mode != "event":
            config["builder_config"]["reconstruction"]["subject"] = {
                "subject_id": "test_subject", "name": "Test Subject"}
        service = SimpleNamespace(config=config)
        self.pipeline.lm_build_pipeline_with_contents.return_value = output
        self.pipeline.save_builder_dir_path = "offline/run"
        with patch("finmy.subject_graph.runner.build_from_contents", return_value=(output, "offline/run")):
            result = self.run_pipeline(service, ["Unchanged source"], "Request", [], "offline")
        self.st.error.assert_not_called()
        return result

    def test_live_person_result_reaches_existing_person_renderer_without_projection(self):
        original = copy.deepcopy(self.package)
        output = SimpleNamespace(extras={"person_epg": self.package},
                                 subject_graph=self.projection, event_cascades={"stages": []})
        result = self.run_result(output)
        self.assertIs(result, self.package)
        self.assertEqual(self.history.detect_build_mode(result), "person_epg")
        self.assertEqual(result, original)
        self.assertIn('id="epg-data"', render_person_epg(result))
        self.assertEqual(self.st.session_state.save_builder_dir_path, "offline/run")


    def test_legacy_event_object_and_dictionary_results_remain_unchanged(self):
        event = {"event_id": "EV1", "stages": [{"episodes": []}]}
        for output in (SimpleNamespace(extras={}, subject_graph=None, event_cascades=event), event):
            with self.subTest(output_type=type(output).__name__):
                self.assertIs(self.run_result(output, "event"), event)
        self.assertEqual(self.namespace["FinmyPipeline"].call_count, 2)

    def test_invalid_canonical_person_result_is_not_hidden_by_valid_projection(self):
        invalid = {"schema_version": "person-epg-3.0"}
        output = SimpleNamespace(extras={"person_epg": invalid}, subject_graph=self.projection)
        result = self.run_result(output)
        self.assertIs(result, invalid)
        with self.assertRaisesRegex(ValueError, "Invalid Person EPG"):
            render_person_epg(result)


    def test_history_retains_legacy_subject_and_event_fallbacks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subject_path = root / "FinalSubjectGraph.json"
            subject_path.write_text(json.dumps(self.projection))
            event = {"event_id": "EV1", "stages": [{"episodes": []}]}
            (root / "FinalEventCascade.json").write_text(json.dumps(event))
            self.assertEqual(self.history.load_history_result(str(root)), self.projection)
            subject_path.unlink()
            self.assertEqual(self.history.load_history_result(str(root)), event)


if __name__ == "__main__":
    unittest.main()
