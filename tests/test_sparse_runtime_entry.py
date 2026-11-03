"""Documented entry, real adapter and SQLite integration without network calls."""

import copy
from contextlib import ExitStack
import io
import json
import logging
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import yaml

from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.builder.sparse_build.runtime import summarize_calls, validate_config
from finmy.runner.sparse_build_runner import load_inputs, main, preflight
from test_sparse_inference_accounting import response
from test_sparse_role_contracts import cascade, vf

ROOT = Path(__file__).resolve().parents[1]


def responses():
    graph = cascade()
    graph["title"]["evidence_source_contents"] = ["Baytown Council warned residents about a storm."]
    outputs = [graph, copy.deepcopy(graph)]
    for stage in graph["stages"]:
        episode = copy.deepcopy(stage["episodes"][0])
        episode["participants"].append({"participant_id": "P_2", "name": vf("Rescue"), "actions": []})
        episode["participant_relations"] = [{
            "from_participant_id": "P_1", "to_participant_id": "P_2", "relation_name": vf("cooperation")
        }]
        outputs.extend([{"participants": episode["participants"]}, {"transactions": []}, episode,
                        {"descriptions": [vf("Completed stage description")]}])
    outputs.append({"descriptions": [vf("Completed event description")]})
    return outputs


class SparseRuntimeEntryTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.config = yaml.safe_load((ROOT / "configs/sparse_pipeline.yml").read_text())
        self.builder_config = self.config["builder_config"]
        self.builder_config["save_folder"] = str(self.root / "runs")
        self.builder_config["sparse_builder_config"]["enable_sparse_routing"] = False
        self.inputs, _ = load_inputs(ROOT / "examples/sparse_input.json")
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")))
        self.stack.enter_context(patch.dict(os.environ, {"DEEPSEEK_API_KEY": "synthetic-test-key"}))
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50)
        self.create = Mock(side_effect=[response(content=json.dumps(x), usage=usage) for x in responses()])
        self.client = Mock()
        self.client.with_options.return_value = self.client
        self.client.chat.completions.create = self.create
        self.stack.enter_context(patch("lmbase.inference.api_call.OpenAI", return_value=self.client))

    def builder(self):
        return SparseRagBuilder(build_config=self.builder_config)

    def test_two_stage_real_adapter_run_and_repeat_replay(self):
        builder = self.builder()
        result = builder.run(self.inputs)
        self.assertEqual(self.create.call_count, 11)
        self.client.with_options.assert_called_once_with(max_retries=0, timeout=900)
        for call in self.create.call_args_list:
            messages = call.kwargs["messages"]
            self.assertIn("class VerifiableField", messages[0]["content"])
            for sample in self.inputs.samples:
                self.assertIn(sample.content, messages[1]["content"])
                self.assertIn(sample.sample_id, messages[1]["content"])
        self.assertEqual(builder.integrate_from_files(strict=True), result.event_cascades)
        self.assertEqual(builder.integrate_from_files(strict=True), result.event_cascades)
        manifest = json.loads(Path(builder.save_dir, "RunManifest.json").read_text())
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["usage"]["prompt_tokens"], 1100)
        self.assertEqual(manifest["usage"]["completion_tokens"], 550)
        self.assertIn("finmy/builder/agent_build/structure.py", manifest["code"]["source_sha256"])
        evidence = json.loads(Path(builder.save_dir, "EvidenceCheck.json").read_text())
        self.assertEqual(evidence["unmatched_quote_count"], 0)
        self.assertEqual(evidence["links"][0]["sample_ids"], ["sample-1"])
        self.assertGreater(len(evidence["fields_without_quotes"]), 0)
        self.assertFalse(evidence["semantic_support_checked"])
        with self.assertRaisesRegex(RuntimeError, "new builder"):
            builder.run(self.inputs)

    def test_replay_rejects_missing_or_mislocated_outputs(self):
        builder = self.builder()
        builder.run(self.inputs)
        path = next(Path(builder.save_dir).glob("ParticipantReconstructor-1-*-Result.json"))
        original = path.read_text()
        path.unlink()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            builder.integrate_from_files(strict=True)
        payload = json.loads(original)
        payload["_meta"]["episode_locator"]["episode_index"] = 4
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, "changed"):
            builder.integrate_from_files(strict=True)
        with self.assertRaisesRegex(ValueError, "locator"):
            builder.integrate_from_files()

    def test_transport_failure_records_failed_run_and_no_final(self):
        self.create.side_effect = TimeoutError("synthetic transport failure")
        builder = self.builder()
        with self.assertRaises(TimeoutError):
            builder.run(self.inputs)
        manifest = json.loads(Path(builder.save_dir, "RunManifest.json").read_text())
        self.assertEqual(manifest["status"], "failed")
        self.assertIsNone(manifest["usage"]["prompt_tokens"])
        self.assertFalse(Path(builder.save_dir, "FinalEventCascade.json").exists())
        self.assertEqual(self.create.call_count, 1)

    def test_strict_quote_failure_does_not_publish_final(self):
        values = responses()
        values[1]["title"]["evidence_source_contents"] = ["Never present in either source."]
        self.create.side_effect = [response(content=json.dumps(x)) for x in values]
        builder = self.builder()
        with self.assertRaisesRegex(ValueError, "quotes absent"):
            builder.run(self.inputs)
        self.assertFalse(Path(builder.save_dir, "FinalEventCascade.json").exists())
        evidence = json.loads(Path(builder.save_dir, "EvidenceCheck.json").read_text())
        self.assertEqual(evidence["unmatched_quote_count"], 1)

    def test_context_assets_opt_out_preserves_full_input(self):
        self.builder_config["sparse_builder_config"]["enable_context_assets"] = False
        builder = self.builder()
        self.assertEqual(builder._build_private_context_assets(self.inputs).evidence_cards, [])
        builder.run(self.inputs)
        self.assertIn(self.inputs.samples[0].content, self.create.call_args.kwargs["messages"][1]["content"])

    def test_compiled_graph_keeps_sparse_plan_and_context(self):
        builder = self.builder()
        result = builder.graph().invoke({
            "build_input": self.inputs, "context_assets": builder._build_private_context_assets(self.inputs),
            "agent_results": [], "agent_executed": [], "cost": [], "stage_sparse_cache": {},
            "episode_execution_plan": {"episodes": []},
        }, config={"recursion_limit": 30})
        self.assertEqual(len(result["episode_execution_plan"]["episodes"]), 2)
        self.assertEqual(len(result["agent_executed"]), 11)
        self.assertEqual(result["context_assets"].index.sample_ids, ["sample-1", "sample-2"])

    def test_preflight_needs_no_credentials_and_makes_no_calls(self):
        with patch.dict(os.environ, {}, clear=True):
            report = preflight(self.builder_config, self.inputs)
        self.assertFalse(report["credential_present"])
        self.assertFalse(report["online_compatibility_verified"])
        self.assertFalse((self.root / "runs").exists())
        self.create.assert_not_called()

    def test_documented_cli_executes_and_replays_without_network(self):
        config_path = self.root / "config.yml"
        config_path.write_text(yaml.safe_dump(self.config))
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(["--config", str(config_path), "--input", str(ROOT / "examples/sparse_input.json")]), 0)
            self.create.assert_not_called()
            self.assertEqual(main(["--config", str(config_path), "--input", str(ROOT / "examples/sparse_input.json"), "--execute"]), 0)
            run_dir = next((self.root / "runs").iterdir())
            self.assertEqual(main(["--replay", str(run_dir)]), 0)
        self.assertEqual(self.create.call_count, 11)

    def test_gantt_failure_preserves_completed_graph(self):
        config_path = self.root / "config.yml"
        config_path.write_text(yaml.safe_dump(self.config))
        with patch("sys.stdout", new_callable=io.StringIO), \
             patch("finmy.builder.agent_build.visualizer_gantt.EventCascadeGanttVisualizer.plot_cascade",
                   side_effect=ValueError("synthetic render failure")):
            main(["--config", str(config_path), "--input", str(ROOT / "examples/sparse_input.json"),
                  "--execute", "--gantt"])
        run_dir = next((self.root / "runs").iterdir())
        self.assertEqual(json.loads((run_dir / "GanttStatus.json").read_text())["status"], "failed")
        self.assertEqual(json.loads((run_dir / "RunManifest.json").read_text())["status"], "completed")
        with patch("sys.stdout", new_callable=io.StringIO):
            main(["--replay", str(run_dir)])

    def test_invalid_input_is_rejected_without_submission(self):
        bad = copy.deepcopy(self.inputs)
        bad.samples.append(copy.deepcopy(bad.samples[0]))
        builder = self.builder()
        with self.assertRaisesRegex(ValueError, "unique"):
            builder.run(bad)
        self.create.assert_not_called()

    def test_unknown_skeleton_names_rejected_during_run(self):
        values = responses()
        values[0]["title"] = vf("unknown")
        self.create.side_effect = [response(content=json.dumps(values[0]))] * 3
        builder = self.builder()
        with self.assertRaisesRegex(ValueError, "3 attempt"):
            builder.run(self.inputs)
        self.assertFalse(Path(builder.save_dir, "FinalEventCascade.json").exists())

    def test_dangling_episode_reference_rejected_during_run(self):
        values = responses()
        values[4]["participant_relations"][0]["to_participant_id"] = "absent"
        self.create.side_effect = [response(content=json.dumps(x)) for x in values[:4] + [values[4]] * 3]
        builder = self.builder()
        with self.assertRaisesRegex(ValueError, "dangling"):
            builder.run(self.inputs)
        self.assertEqual(self.create.call_count, 7)
        self.assertFalse(Path(builder.save_dir, "FinalEventCascade.json").exists())

    def test_missing_usage_does_not_become_zero(self):
        summary = summarize_calls([{"agent": "A", "attempt": 1, "prompt_tokens": None},
                                   {"agent": "A", "attempt": 2, "prompt_tokens": 20}])
        self.assertIsNone(summary["prompt_tokens"])
        self.assertEqual(summary["known_prompt_tokens"], 20)
        self.assertEqual(summary["unknown_prompt_tokens_calls"], 1)

    def test_invalid_configuration_is_rejected_before_client_creation(self):
        changes = [
            lambda c: c["agents"]["SkeletonChecker"].update(lm_name="other/model"),
            lambda c: c["generation_config"].update(max_tokens=2),
            lambda c: c["generation_config"].update(tools=[]),
            lambda c: c["generation_config"].update(extra_body={"messages": []}),
            lambda c: c["sparse_builder_config"].update(enable_sparse_routing="false"),
            lambda c: c["sparse_builder_config"].update(max_json_attempts=4),
        ]
        for change in changes:
            config = copy.deepcopy(self.builder_config)
            change(config)
            with self.assertRaises(ValueError):
                validate_config(config)
        self.create.assert_not_called()

    def test_pipeline_sqlite_text_path_needs_no_pdf_key(self):
        from finmy.pipeline import FinmyPipeline

        self.config["db_config"] = {"url": f"sqlite:///{self.root / 'metadata.sqlite3'}"}
        with patch.dict(os.environ, {"DATA_DIR": str(self.root / "blocks"), "MINERU_API_KEY": ""}), \
             patch.object(FinmyPipeline, "setup_logging", return_value=logging.getLogger("sparse-test")), \
             patch("finmy.pipeline.PDFCollector", side_effect=AssertionError("PDF not requested")), \
             patch("finmy.summarizer.summarizer.BaseSummarizer.invoke_llm", return_value=json.dumps({"summarization": "Storm", "key_words": ["storm"]})):
            pipeline = FinmyPipeline(self.config)
            self.assertIsNone(pipeline.pdf_collector)
            try:
                output = pipeline.lm_build_pipeline_with_contents(
                    [s.content for s in self.inputs.samples], "Storm response", ["storm"])
                self.assertEqual(output.event_cascades["event_id"], "synthetic-storm")
                manager = pipeline.data_manager
                self.assertEqual(len(manager.read_sql_table(manager.TABLE_RAW_DATA)), 2)
                self.assertEqual(len(manager.read_sql_table(manager.TABLE_MEAT_SAMPLE)), 2)
                self.assertEqual(len(manager.read_sql_table(manager.TABLE_USER_QUERY)), 1)
            finally:
                pipeline.data_manager.engine.dispose()


if __name__ == "__main__":
    unittest.main()
