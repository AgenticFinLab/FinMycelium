import copy
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from finmy.reconstruction_scope import read_reconstruction, search_query
from finmy.runner.source_documents import make_document
from source_test_support import source_batch
from finmy.subject_graph.runner import build_from_contents
import test_source_integration as web


def config(mode="person"):
    return {"builder_config": {"builder_type": "AgentEventBuilder", "reconstruction": {
        "mode": mode, "subject": {"subject_id": "subject_example", "name": "Example",
                                    "coverage_start": "2022", "coverage_end": "2023"}}}}


class SubjectScopeTest(unittest.TestCase):
    def test_broad_scope_is_default_and_explicit_scope_still_respected(self):
        for mode in ("person", "company"):
            c = config(mode)
            normalized = read_reconstruction(c)
            self.assertIn("Discover relevant events", normalized["subject"]["scope"])
            self.assertNotIn("OXY", search_query("history", [], c))
            c["builder_config"]["reconstruction"]["subject"]["scope"] = "Selected project only"
            self.assertEqual(read_reconstruction(c)["subject"]["scope"], "Selected project only")


    def test_saved_runner_rejects_empty_input_before_loading_runtime(self):
        for contents in ([], "text", [None], [" "]):
            with self.subTest(contents=contents), self.assertRaises(ValueError):
                build_from_contents(contents, "history", [], config())

    def test_render_cli_works_without_model_runtime_and_preserves_existing_output(self):
        from test_subject_graph_schema import graph_fixture
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "FinalSubjectGraph.json"
            source.write_text(json.dumps(graph_fixture()), encoding="utf-8")
            original = source.read_bytes()
            command = [sys.executable, "-m", "finmy.subject_graph.runner", "--render-only", str(source)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            output = source.with_suffix(".html")
            self.assertIn("Warren Buffett", output.read_text(encoding="utf-8"))
            output.write_text("existing output", encoding="utf-8")
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("Output exists", second.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "existing output")
            self.assertEqual(source.read_bytes(), original)


class NativeServiceTest(unittest.TestCase):
    setUp = web.WebSourceIntegrationTest.setUp

    def test_service_prefers_native_subject_and_bypasses_legacy_pipeline(self):
        c = config()
        graph = {"schema_version": "subject-graph-1.0", "events": []}
        output = types.SimpleNamespace(subject_graph=graph, event_cascades={"stages": []})
        self.service.st.session_state = types.SimpleNamespace()
        service = self.service.ReconstructionService(c)
        with patch("finmy.subject_graph.runner.build_from_contents", return_value=(output, str(self.path))) as build, \
             patch.object(self.service, "FinmyPipeline", side_effect=AssertionError("Legacy pipeline used")):
            result = service._run_pipeline(["Evidence"], "History", [], str(self.path))
        self.assertIs(result, graph)
        build.assert_called_once_with(["Evidence"], "History", [], c)
        self.assertEqual(self.service.st.session_state.save_builder_dir_path, str(self.path))


if __name__ == "__main__":
    unittest.main()
