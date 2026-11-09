"""Search coverage survives a failed native build in CLI and UI entry points."""
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from finmy.runner.search_status import record_search_coverage
from finmy.runner.search_pipeline_runner import run_search_pipeline
from finmy.subject_graph.runner import build_from_contents
import test_enhanced_subject_pipeline as cli_tests
import test_enhanced_subject_ui as ui_tests
from test_sparse_person_routing import scoped


class BuildStatusCliTests(unittest.TestCase):
    setUp = cli_tests.EnhancedSubjectPipelineTests.setUp
    config = cli_tests.EnhancedSubjectPipelineTests.config
    acquired = cli_tests.EnhancedSubjectPipelineTests.acquired
    forbid_legacy = cli_tests.EnhancedSubjectPipelineTests.forbid_legacy

    def test_failed_builder_retains_partial_inputs_directory_and_original_exception(self):
        self.forbid_legacy()
        builder_dir = self.root / "builder"
        builder_dir.mkdir()
        error = ValueError("PersonOrganization returned invalid output after 3 attempt(s): unknown activity detail")
        error.builder_directory = str(builder_dir)
        acquisition = {"status": "partial", "complete": False, "documents": self.documents,
                       "reports": [{"event_id": "E1", "status": "insufficient", "gaps": ["Closing date"]}]}
        contents = []

        def fail_build(received, *args):
            running = json.loads((self.root / "search_pipeline_status.json").read_text())
            self.assertEqual(running["builder_status"], "running")
            contents.extend(received)
            raise error

        with patch("finmy.runner.enhanced_subject_search.collect_enhanced_sources", return_value=acquisition), \
             patch("finmy.subject_graph.runner.build_from_contents", fail_build):
            with self.assertRaises(ValueError) as raised:
                run_search_pipeline(self.config(), self.query, self.keywords, self.root)
        self.assertIs(raised.exception, error)
        coverage = json.loads((self.root / "search_pipeline_status.json").read_text())
        self.assertEqual(coverage["builder_status"], "failed")
        self.assertEqual(coverage["builder_directory"], str(builder_dir))
        self.assertEqual(coverage["builder_error"]["stage"], "person_organization")
        self.assertEqual(coverage["unresolved_events"], ["E1"])
        self.assertEqual(coverage["retained_document_count"], 1)
        self.assertFalse(coverage["search_complete"])
        self.assertEqual(json.loads((self.root / "builder_input_contents.json").read_text()), contents)
        self.assertEqual(json.loads((builder_dir / "search_coverage_report.json").read_text()), coverage)

    def test_empty_result_is_failed_not_not_started_and_retry_clears_error(self):
        self.forbid_legacy()
        with patch("finmy.runner.enhanced_subject_search.collect_enhanced_sources", self.acquired), \
             patch("finmy.subject_graph.runner.build_from_contents", return_value=(None, str(self.root))):
            result = run_search_pipeline(self.config(), self.query, self.keywords, self.root)
        self.assertEqual(result["builder_status"], "failed")
        self.assertEqual(result["builder_error"]["type"], "MissingBuildResult")
        with patch("finmy.runner.enhanced_subject_search.collect_enhanced_sources", self.acquired), \
             patch("finmy.subject_graph.runner.build_from_contents", return_value=(SimpleNamespace(), str(self.root))):
            result = run_search_pipeline(self.config(), self.query, self.keywords, self.root)
        self.assertEqual(result["builder_status"], "completed")
        self.assertNotIn("builder_error", result)

    def test_saved_failure_omits_provider_credentials_and_raw_response(self):
        error = RuntimeError("Authorization: Bearer secret-token; request: private source body")
        result = record_search_coverage({"status": "finished", "documents": self.documents}, self.root,
                                       builder_status="failed", builder_error=error)
        self.assertEqual(result["builder_error"]["type"], "RuntimeError")
        self.assertNotIn("secret-token", json.dumps(result))
        self.assertNotIn("private source body", json.dumps(result))


class BuildStatusUiTests(unittest.TestCase):
    setUp = ui_tests.EnhancedSubjectUI.setUp
    config = ui_tests.EnhancedSubjectUI.config
    search = ui_tests.EnhancedSubjectUI.search
    forbid_legacy = ui_tests.EnhancedSubjectUI.forbid_legacy

    def test_failed_builder_updates_sidecar_and_session_without_losing_evidence(self):
        self.forbid_legacy()
        self.search_result.update(status="partial", complete=False,
                                  reports=[{"event_id": "E1", "status": "insufficient"}])
        service = self.service.ReconstructionService(self.config())
        builder_dir = self.path / "failed-builder"
        builder_dir.mkdir()
        error = ValueError("PersonOrganization returned invalid output after 3 attempt(s): unknown activity detail")
        error.builder_directory = str(builder_dir)
        inputs = []

        def fail_build(contents, *args):
            self.assertEqual(self.service.st.session_state.search_coverage["builder_status"], "running")
            inputs.extend(contents)
            raise error

        with patch("finmy.subject_graph.runner.build_from_contents", fail_build), \
             patch.object(self.service.traceback, "print_exc"):
            result = service.run_reconstruction("Subject 2022-2023", [], None)
        self.assertIsNone(result)
        coverage = self.service.st.session_state.search_coverage
        self.assertEqual(coverage["builder_status"], "failed")
        self.assertEqual(coverage["builder_error"]["stage"], "person_organization")
        self.assertEqual(coverage["retained_document_count"], 3)
        self.assertEqual(coverage["unresolved_events"], ["E1"])
        self.assertEqual(self.service.st.session_state.save_builder_dir_path, str(builder_dir))
        self.assertEqual(json.loads(Path(coverage["status_path"]).read_text()), coverage)
        self.assertEqual(json.loads((Path(coverage["save_dir"]) / "builder_input_contents.json").read_text()), inputs)
        self.assertNotIn("source_registry", service.config)
        self.assertTrue(self.errors)


    def test_none_result_keeps_failed_search_coverage_in_session(self):
        service = self.service.ReconstructionService(self.config())
        with patch("finmy.subject_graph.runner.build_from_contents", return_value=(None, str(self.path))):
            self.assertIsNone(service.run_reconstruction("Subject", [], None))
        coverage = self.service.st.session_state.search_coverage
        self.assertEqual(coverage["builder_status"], "failed")
        self.assertEqual(coverage["builder_error"]["type"], "MissingBuildResult")
        self.assertEqual(coverage["retained_document_count"], 3)

    def test_post_build_result_error_does_not_relabel_builder_as_failed(self):
        class Result:
            @property
            def extras(self):
                raise RuntimeError("Result presentation failed")

        service = self.service.ReconstructionService(self.config())
        with patch("finmy.subject_graph.runner.build_from_contents", return_value=(Result(), str(self.path))), \
             patch.object(self.service.traceback, "print_exc"):
            self.assertIsNone(service.run_reconstruction("Subject", [], None))
        coverage = self.service.st.session_state.search_coverage
        self.assertEqual(coverage["builder_status"], "completed")
        self.assertNotIn("builder_error", coverage)


class BuildExceptionDirectoryTests(unittest.TestCase):
    def test_builder_exception_keeps_type_instance_and_saved_directory(self):
        error = ValueError("Failed during organization")

        class Builder:
            def __init__(self, build_config):
                self.save_dir = "output/saved-build"

            def run(self, inputs):
                raise error

        base = ModuleType("finmy.builder.base")
        base.BuildInput = SimpleNamespace
        sparse = ModuleType("finmy.builder.sparse_build.main_build")
        sparse.SparseRagBuilder = Builder
        with patch.dict("sys.modules", {base.__name__: base, sparse.__name__: sparse}):
            with self.assertRaises(ValueError) as raised:
                build_from_contents(["Saved original evidence"], "Subject", [], scoped())
        self.assertIs(raised.exception, error)
        self.assertEqual(raised.exception.builder_directory, "output/saved-build")


if __name__ == "__main__":
    unittest.main()
