"""Compact person requests and pre-search plan handoff, without live APIs."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from finmy.runner.person_storyline_pipeline import person_config, main
from finmy.runner.search_pipeline_runner import run_search_pipeline


class PersonStorylinePipelineTests(unittest.TestCase):
    def config(self):
        return {"search_config": {"mode": "agent", "enhancement": {
            "providers": ["exa"], "lm_name": "deepseek/deepseek-chat", "allow_network": False}},
            "event_followup": {"enabled": True}, "builder_config": {"lm_name": "deepseek/deepseek-chat"}}

    def test_compact_request_sets_person_years_and_disables_old_followup_setting(self):
        original = self.config()
        before = copy.deepcopy(original)
        for request in ("Buffett 2022-2023", "Buffett 2022–2023", "巴菲特2022至2023"):
            c = person_config(request, original)
            subject = c["builder_config"]["reconstruction"]["subject"]
            self.assertEqual((subject["coverage_start"], subject["coverage_end"]), ("2022", "2023"))
            self.assertIn(subject["name"], ("Buffett", "巴菲特"))
            self.assertFalse(c["event_followup"]["enabled"])
            self.assertTrue(c["search_config"]["storyline_discovery"]["enabled"])
        self.assertEqual(original, before)

    def test_compact_request_overrides_stale_person_identity(self):
        c = person_config("Other Person 2010-2011", person_config("Buffett 2022-2023", self.config()))
        self.assertEqual(c["builder_config"]["reconstruction"]["subject"]["name"], "Other Person")
        self.assertEqual(c["builder_config"]["reconstruction"]["subject"]["coverage_start"], "2010")

    def test_invalid_scope_rejected_before_calls(self):
        for value in ("Buffett 2023-2022", "Buffett", "2022-2023", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                person_config(value, self.config())

    def test_cli_threads_plan_into_builder_and_uses_initial_event_budget(self):
        config = person_config("Buffett 2022-2023", self.config())
        plan = {"version": "person-storylines-v1", "domains": [{"domain_id": "D1", "label": "Investments"}],
                "events": [{"event_id": "E1", "domain_id": "D1", "label": "A purchase"}]}
        sources = [{"raw_text": "Original evidence of a purchase. " * 100,
                    "url": "https://example.test/purchase", "source_id": "S1", "source_version": "v1",
                    "event_ids": ["E1"], "event_terms": ["purchase"]}]
        with tempfile.TemporaryDirectory() as tmp, \
             patch("finmy.runner.enhanced_subject_search.collect_enhanced_sources", return_value={
                 "status": "finished", "documents": sources, "storyline_plan": plan}) as acquire, \
             patch("finmy.subject_graph.runner.build_from_contents", return_value=(types.SimpleNamespace(), tmp)) as build, \
             patch("finmy.runner.event_refinement.build_with_draft_event_followup", side_effect=AssertionError("Default followup used")):
            result = run_search_pipeline(config, "Buffett 2022-2023", [], tmp)
            self.assertIsNotNone(result["pipeline_result"])
            self.assertEqual(acquire.call_count, 1)
            self.assertEqual(build.call_count, 1)
            contents, _, _, received = build.call_args.args
            self.assertEqual(received["storyline_plan"], plan)
            self.assertEqual(received["all_content_config"]["allocation_strategy"], "event")
            self.assertLessEqual(sum(map(len, contents)), 60000)
            self.assertNotIn('"domains"', ''.join(contents))
            self.assertEqual(received["source_registry"]["saved_0"]["source_id"], "S1")
            self.assertEqual(json.loads((Path(tmp)/"context_budget_report.json").read_text())["allocation_strategy"], "event")

    def test_command_followup_requires_flag_even_with_old_enabled_yaml(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp)/"config.yml"; file.write_text(yaml.safe_dump(self.config()))
            for enable in (False, True):
                with patch("finmy.runner.search_pipeline_runner.run_search_pipeline", return_value={"pipeline_result": object()}) as run:
                    args = ["--request", "Buffett 2022-2023", "--config", str(file), "--output-dir", tmp]
                    if enable: args.append("--event-followup")
                    self.assertEqual(main(args), 0)
                    self.assertEqual(run.call_args.args[0]["event_followup"]["enabled"], enable)

    def test_command_builds_partial_sources_and_reports_unresolved_events(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "config.yml"
            file.write_text(yaml.safe_dump(self.config()))
            report_path = str(Path(tmp) / "initial_event_search" / "phase_report.json")
            acquired = {
                "status": "partial", "complete": False,
                "documents": [{"raw_text": "A retained source from one event."}],
                "reports": [{"event_id": "E1", "status": "finished"},
                            {"event_id": "E2", "status": "limit"}],
                "report_path": report_path,
            }
            output = io.StringIO()
            with patch("finmy.runner.enhanced_subject_search.collect_enhanced_sources", return_value=acquired), \
                 patch("finmy.subject_graph.runner.build_from_contents",
                       return_value=(types.SimpleNamespace(extras={"person_epg": {}}), str(Path(tmp) / "native"))) as build, \
                 redirect_stdout(output):
                code = main(["--request", "Buffett 2022-2023", "--config", str(file),
                             "--output-dir", tmp])
            summary = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(summary["status"], "partial")
            self.assertFalse(summary["complete"])
            self.assertEqual(summary["retained_document_count"], 1)
            self.assertEqual(summary["unresolved_events"], ["E2"])
            self.assertEqual(summary["search_report_path"], report_path)
            self.assertEqual(summary["resume_directory"], tmp)
            self.assertEqual(summary["builder_directory"], str(Path(tmp) / "native"))
            self.assertEqual(summary["search_status"], "partial")
            self.assertFalse(summary["search_complete"])
            self.assertTrue(Path(summary["search_coverage_report_path"]).exists())
            self.assertFalse(summary["postbuild_followup_enabled"])
            self.assertTrue(Path(summary["status_path"]).exists())
            build.assert_called_once()

    def test_explicit_search_resume_is_prepared_before_pipeline_with_matching_scope(self):
        import yaml
        calls = []
        def prepare(*args):
            calls.append(("prepare", args))
        def pipeline(*args):
            calls.append(("pipeline", args))
            return {"status": "partial", "pipeline_result": None}
        resume = types.ModuleType("finmy.runner.storyline_search_resume")
        resume.prepare_storyline_resume = prepare
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "config.yml"
            file.write_text(yaml.safe_dump(self.config()))
            target = Path(tmp) / "new-run"
            source = Path(tmp) / "old-run"
            with patch.dict("sys.modules", {resume.__name__: resume}), \
                 patch("finmy.runner.search_pipeline_runner.run_search_pipeline", pipeline), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--request", "Buffett 2022-2023", "--config", str(file),
                    "--output-dir", str(target), "--resume-search-from", str(source)]), 1)
        self.assertEqual([item[0] for item in calls], ["prepare", "pipeline"])
        prepared = calls[0][1]
        self.assertEqual(prepared[:4], (str(source), target, "Buffett 2022-2023", []))
        self.assertEqual(prepared[4]["name"], "Buffett")
        self.assertEqual(prepared[4]["coverage_start"], "2022")
        self.assertEqual(prepared[4]["coverage_end"], "2023")
        self.assertTrue(prepared[4]["scope"])
        self.assertIs(prepared[5], calls[1][1][0])
        self.assertFalse(prepared[5]["event_followup"]["enabled"])

    def test_search_resume_validation_error_stops_before_pipeline(self):
        import yaml
        resume = types.ModuleType("finmy.runner.storyline_search_resume")
        resume.prepare_storyline_resume = Mock(side_effect=ValueError("Resume target must be empty"))
        errors = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "config.yml"
            file.write_text(yaml.safe_dump(self.config()))
            with patch.dict("sys.modules", {resume.__name__: resume}), \
                 patch("finmy.runner.search_pipeline_runner.run_search_pipeline") as pipeline, \
                 redirect_stderr(errors):
                with self.assertRaises(SystemExit) as raised:
                    main(["--request", "Buffett 2022-2023", "--config", str(file),
                          "--output-dir", tmp, "--resume-search-from", "saved-run"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("Resume target must be empty", errors.getvalue())
        pipeline.assert_not_called()


if __name__ == "__main__":
    unittest.main()
