"""Coverage stays reviewable while a partial search can produce native results."""
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from finmy.runner.search_status import has_search_material, incomplete_search_result, record_search_coverage
import test_subject_graph_ui as subject_ui


class SearchCoverageTests(unittest.TestCase):
    def test_empty_finished_phase_is_insufficient_and_does_not_claim_completed_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = incomplete_search_result({"status": "finished", "documents": [], "reports": []}, temporary)
            self.assertEqual(result["search_status"], "insufficient")
            self.assertFalse(result["search_complete"])
            self.assertEqual(result["builder_status"], "not_started")
            self.assertIsNone(result["pipeline_result"])
            self.assertEqual(json.loads(Path(result["status_path"]).read_text()), result)

    def test_selection_gaps_and_reason_are_preserved_in_coverage_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            event_dir = directory / "event_search" / "E2"
            event_dir.mkdir(parents=True)
            (event_dir / "selection.json").write_text(json.dumps({
                "gaps": ["No closing announcement"], "reason": "read budget exhausted"}))
            acquired = {"status": "partial", "documents": [{"raw_text": "Inspected transaction original."}],
                        "reports": [{"event_id": "E1", "status": "finished"},
                                    {"event_id": "E2", "status": "insufficient", "run_directory": str(event_dir)}],
                        "storyline_plan": {"events": [{"event_id": "E2", "label": "Acquisition"}]}}
            coverage = record_search_coverage(acquired, directory)
            self.assertEqual(coverage["events"][1]["gaps"], ["No closing announcement"])
            self.assertEqual(coverage["events"][1]["stop_reason"], "read budget exhausted")
            self.assertEqual(coverage["unresolved_events"], ["E2"])
            self.assertEqual(coverage["unresolved_event_labels"], ["Acquisition"])
            self.assertEqual(json.loads(Path(coverage["search_coverage_report_path"]).read_text()), coverage)
            self.assertNotIn("gaps", acquired["reports"][1])

    def test_document_contract_rejects_malformed_partial_text(self):
        for documents in (None, {}, [None], [{}], [{"raw_text": []}], [{"raw_text": "  "}]):
            with self.subTest(documents=documents), self.assertRaises(ValueError):
                has_search_material({"status": "partial", "documents": documents})


class SearchCoverageResultsTests(unittest.TestCase):
    def setUp(self):
        subject_ui.SubjectUITest.setUp(self)

    def test_partial_graph_downloads_remain_native_and_offer_separate_coverage(self):
        coverage = {"search_status": "partial", "search_complete": False,
                    "unresolved_events": ["E2"], "unresolved_event_labels": ["Acquisition"]}
        self.state.search_coverage = coverage
        with patch.object(self.results.ResultsPage, "_render_history_file_selector"):
            self.results.ResultsPage.render()
        self.assertIn("Acquisition", self.st.warning.call_args.args[0])
        downloads = self.st.download_button.call_args_list
        self.assertEqual([call.kwargs["file_name"] for call in downloads],
                         ["search_coverage_report.json", "FinalSubjectGraph.json", "subject_timeline.html"])
        self.assertEqual(json.loads(downloads[0].kwargs["data"]), coverage)
        self.assertEqual(json.loads(downloads[1].kwargs["data"]), subject_ui.graph())

    def test_history_uses_own_sidecar_and_clears_previous_partial_banner(self):
        (self.path / "FinalSubjectGraph.json").write_text(json.dumps(subject_ui.graph()))
        coverage = {"search_status": "partial", "search_complete": False, "unresolved_events": ["E2"]}
        sidecar = self.path / "search_coverage_report.json"
        sidecar.write_text(json.dumps(coverage))
        with patch.object(self.st, "success", Mock(), create=True):
            self.results.ResultsPage._load_history_result(str(self.path))
            self.assertEqual(self.state.search_coverage, coverage)
            sidecar.unlink()
            self.results.ResultsPage._load_history_result(str(self.path / "FinalSubjectGraph.json"))
        self.assertIsNone(self.state.search_coverage)
        self.st.error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
