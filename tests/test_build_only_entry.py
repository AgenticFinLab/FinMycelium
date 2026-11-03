"""Unified local-text entry, with all provider calls replaced and network blocked."""

import copy
from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import yaml
from lmbase.inference.api_call import LangChainAPIInference
from lmbase.inference.base import InferCost, InferOutput

from finmy.builder.agent_build.main_build import AgentEventBuilder
from finmy.builder.agent_build_adapter import BuildOnlyAgentEventBuilder, validated_config
from finmy.runner.build_only_runner import main, replay, select_builder
from finmy.runner.sparse_build_runner import load_inputs
from test_sparse_inference_accounting import response
from test_sparse_runtime_entry import responses

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "examples/sparse_input.json"


class BuildOnlyEntryTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.inputs, _ = load_inputs(INPUT)
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")))
        self.stack.enter_context(patch.dict(os.environ, {"ARK_API_KEY": "synthetic-test-key"}))
        self.client = Mock()
        self.client.with_options.return_value = self.client
        self.create = self.client.chat.completions.create
        self.set_responses()
        self.openai = self.stack.enter_context(patch("lmbase.inference.api_call.OpenAI", return_value=self.client))
        self.stack.enter_context(patch("sys.stdout", new_callable=io.StringIO))

    def set_responses(self, values=None, usage=True):
        self.create.reset_mock()
        cost = SimpleNamespace(prompt_tokens=100, completion_tokens=50) if usage else None
        self.create.side_effect = [response(content=json.dumps(x), usage=cost)
                                   for x in (responses() if values is None else values)]

    def config(self, kind="agent"):
        config = yaml.safe_load((ROOT / f"configs/build_only_{kind}.yml").read_text())["builder_config"]
        config["save_folder"] = str(self.root / kind)
        return config

    def config_path(self, kind="agent"):
        path = self.root / f"{kind}.yml"
        path.write_text(yaml.safe_dump({"builder_config": self.config(kind)}))
        return str(path)

    def test_default_preflight_both_builders_no_client_or_output(self):
        for kind in ("agent", "sparse"):
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(main(["--config", self.config_path(kind), "--input", str(INPUT)]), 0)
            self.assertFalse((self.root / kind).exists())
        self.openai.assert_not_called()

    def test_both_builders_execute_and_replay(self):
        for kind in ("agent", "sparse"):
            self.set_responses()
            main(["--config", self.config_path(kind), "--input", str(INPUT), "--execute"])
            directory = next((self.root / kind).iterdir())
            self.assertEqual(replay(directory)["status"], "replay_pass")
            self.assertEqual(main(["--replay", str(directory)]), 0)
            self.assertEqual(self.create.call_count, 11)
            manifest = json.loads((directory / "RunManifest.json").read_text())
            self.assertEqual(manifest["usage"]["prompt_tokens"], 1100)
            self.assertEqual(manifest["usage"]["completion_tokens"], 550)
            self.assertGreater(manifest["elapsed_seconds"], 0)
            for call in self.create.call_args_list:
                self.assertEqual(call.kwargs["max_tokens"], 12288)
                self.assertNotIn("max_new_tokens", call.kwargs)
        self.client.with_options.assert_called_with(max_retries=0, timeout=900)

    def test_original_prompts_order_and_graph_match_unmodified_builder(self):
        inputs = copy.deepcopy(self.inputs)
        inputs.samples[0].content += '\n{"field":"{Query}","nested":{"n":1}}'
        messages = []
        values = iter(responses())

        class OriginalSingleCall:
            def run(self, infer_input, **kwargs):
                rendered = LangChainAPIInference._create_messages(self, infer_input, **kwargs)
                messages.append(rendered)
                content = json.dumps(next(values))
                return InferOutput(rendered, content, content, InferCost(None, None, None))

        original = AgentEventBuilder.__new__(AgentEventBuilder)
        original.agents_lm = OriginalSingleCall()
        original.build_config = self.config()
        original.save_dir = str(self.root / "unmodified")
        Path(original.save_dir).mkdir()
        expected = original.run(inputs)
        adapted = BuildOnlyAgentEventBuilder(self.config()).run(inputs)
        actual_messages = [call.kwargs["messages"] for call in self.create.call_args_list]
        self.assertEqual(actual_messages, messages)
        self.assertEqual(adapted.event_cascades, expected.event_cascades)
        self.assertEqual(adapted.logs, expected.logs)
        self.assertIn('{"field":"{Query}","nested":{"n":1}}', actual_messages[0][1]["content"])

    def test_shared_success_metadata_matches_manifest_and_ledger(self):
        for kind in ("agent", "sparse"):
            with self.subTest(kind=kind):
                self.set_responses()
                config = self.config(kind)
                cls, _ = select_builder(config)
                builder = cls(build_config=config)
                output = builder.run(self.inputs)
                directory = Path(builder.save_dir)
                manifest = json.loads((directory / "RunManifest.json").read_text())
                ledger = json.loads((directory / "CallLedger.json").read_text())
                self.assertEqual(manifest["builder_type"], config["builder_type"])
                self.assertEqual(output.extras["builder_type"], config["builder_type"])
                self.assertEqual(output.extras["run_directory"], builder.save_dir)
                self.assertEqual(output.extras["elapsed_seconds"], manifest["elapsed_seconds"])
                self.assertEqual(output.extras["usage"], manifest["usage"])
                self.assertEqual(output.extras["usage"]["calls"], len(ledger))
                self.assertEqual(output.extras["usage"]["prompt_tokens"],
                                 sum(c["prompt_tokens"] for c in ledger))
                self.assertEqual(self.create.call_count, 11)
                self.assertEqual(output.event_cascades,
                                 json.loads((directory / "FinalEventCascade.json").read_text()))
                self.assertEqual(replay(directory)["status"], "replay_pass")
                if kind == "sparse":
                    self.assertEqual(output.extras["calls"], ledger)
                    self.assertEqual(output.extras["acceptance"],
                                     json.loads((directory / "AcceptanceDecision.json").read_text()))
                    self.assertIn("episode_execution_plan", output.extras)
                    self.assertIn("context_asset_summary", output.extras)

    def test_sparse_metadata_preserves_inner_output(self):
        self.set_responses()
        cls, _ = select_builder(self.config("sparse"))
        builder = cls(build_config=self.config("sparse"))
        inner = builder._run_validated
        captured = []

        def capture(inputs):
            output = inner(inputs)
            captured.append(copy.deepcopy(output))
            return output

        with patch.object(builder, "_run_validated", side_effect=capture):
            result = builder.run(self.inputs)
        self.assertEqual(result.event_cascades, captured[0].event_cascades)
        self.assertEqual(result.result, captured[0].result)
        self.assertEqual(result.logs, captured[0].logs)
        for key, value in captured[0].extras.items():
            self.assertEqual(result.extras[key], value)

    def test_historical_sparse_manifest_without_builder_type_replays(self):
        cls, _ = select_builder(self.config("sparse"))
        builder = cls(build_config=self.config("sparse"))
        builder.run(self.inputs)
        path = Path(builder.save_dir, "RunManifest.json")
        manifest = json.loads(path.read_text())
        manifest.pop("builder_type")
        path.write_text(json.dumps(manifest))
        before = path.read_bytes()
        self.assertEqual(replay(builder.save_dir)["status"], "replay_pass")
        self.assertEqual(path.read_bytes(), before)

    def test_missing_credentials_rejected_before_client(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "key is missing"):
            main(["--config", self.config_path(), "--input", str(INPUT), "--execute"])
        self.openai.assert_not_called()

    def test_invalid_configs_rejected_before_client(self):
        changes = [
            lambda c: c.update(builder_type="Other"),
            lambda c: c.update(sparse_builder_config={"enable_context_assets": True}),
            lambda c: c["build_only_config"].update(max_calls=0),
            lambda c: c["build_only_config"].update(max_calls=True),
            lambda c: c["build_only_config"].update(request_timeout_seconds=float("nan")),
            lambda c: c["build_only_config"].update(retries=3),
            lambda c: c["graph_config"].update(recursion_limit=True),
            lambda c: c["generation_config"].update(max_tokens=5),
            lambda c: c["generation_config"].update(tools=[]),
            lambda c: c["agents"]["SkeletonChecker"].update(lm_name="other/model"),
        ]
        for change in changes:
            config = self.config()
            change(config)
            with self.subTest(config=config), self.assertRaises(ValueError):
                select_builder(config)
        self.openai.assert_not_called()

    def test_timeout_is_recorded_once_without_usage_or_final(self):
        self.create.side_effect = TimeoutError("synthetic")
        builder = BuildOnlyAgentEventBuilder(self.config())
        with self.assertRaises(TimeoutError):
            builder.run(self.inputs)
        directory = Path(builder.save_dir)
        manifest = json.loads((directory / "RunManifest.json").read_text())
        self.assertEqual(manifest["status"], "failed")
        self.assertIsNone(manifest["usage"]["prompt_tokens"])
        self.assertEqual(self.create.call_count, 1)
        self.assertFalse((directory / "FinalEventCascade.json").exists())
        self.assertEqual(json.loads((directory / "CallLedger.json").read_text())[0]["status"], "failed")
        with self.assertRaises(ValueError):
            replay(directory)

    def test_length_response_saved_but_not_assembled_or_retried(self):
        result = response(content="partial")
        result.choices[0].finish_reason = "length"
        self.create.side_effect = [result]
        builder = BuildOnlyAgentEventBuilder(self.config())
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            builder.run(self.inputs)
        self.assertTrue(Path(builder.save_dir, "response-001.json").exists())
        self.assertEqual(self.create.call_count, 1)
        self.assertFalse(Path(builder.save_dir, "FinalEventCascade.json").exists())

    def test_call_cap_and_no_implicit_resume(self):
        config = self.config()
        config["build_only_config"]["max_calls"] = 1
        builder = BuildOnlyAgentEventBuilder(config)
        with self.assertRaisesRegex(RuntimeError, "cap reached"):
            builder.run(self.inputs)
        self.assertEqual(self.create.call_count, 1)
        with self.assertRaisesRegex(RuntimeError, "new builder"):
            builder.run(self.inputs)
        self.assertEqual(self.create.call_count, 1)

    def test_unknown_usage_stays_null(self):
        for kind in ("agent", "sparse"):
            with self.subTest(kind=kind):
                self.set_responses(usage=False)
                config = self.config(kind)
                cls, _ = select_builder(config)
                builder = cls(build_config=config)
                output = builder.run(self.inputs)
                manifest = json.loads(Path(builder.save_dir, "RunManifest.json").read_text())
                self.assertIsNone(output.extras["usage"]["prompt_tokens"])
                self.assertEqual(output.extras["usage"], manifest["usage"])
                self.assertEqual(manifest["usage"]["unknown_prompt_tokens_calls"], 11)

    def test_original_replay_rejects_changed_missing_or_extra_results(self):
        builder = BuildOnlyAgentEventBuilder(self.config())
        builder.run(self.inputs)
        directory = Path(builder.save_dir)
        path = directory / "FinalEventCascade.json"
        original = path.read_bytes()
        path.write_text("{}")
        with self.assertRaisesRegex(ValueError, "changed"):
            replay(directory)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            replay(directory)
        path.write_bytes(original)
        (directory / "Unexpected-1-Result.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "changed"):
            replay(directory)

    def test_gantt_failure_does_not_invalidate_original_run(self):
        with patch("finmy.builder.agent_build.visualizer_gantt.EventCascadeGanttVisualizer.plot_cascade",
                   side_effect=ValueError("synthetic")):
            main(["--config", self.config_path(), "--input", str(INPUT), "--execute", "--gantt"])
        directory = next((self.root / "agent").iterdir())
        self.assertEqual(json.loads((directory / "GanttStatus.json").read_text())["status"], "failed")
        self.assertEqual(replay(directory)["status"], "replay_pass")

    def test_replay_incompatible_options(self):
        for flag in ("--execute", "--gantt", "--input", "--env-file"):
            args = ["--replay", str(self.root), flag]
            if flag in ("--input", "--env-file"):
                args.append("unused")
            with self.subTest(flag=flag), patch("sys.stderr", new_callable=io.StringIO), \
                    self.assertRaises(SystemExit) as exc:
                main(args)
            self.assertEqual(exc.exception.code, 2)
        self.openai.assert_not_called()


if __name__ == "__main__":
    unittest.main()
