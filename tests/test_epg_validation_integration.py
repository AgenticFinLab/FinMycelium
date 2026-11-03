"""Exercise actual builder integration/persistence with model dependencies stubbed."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


def field(value, evidence=None):
    return {"value": value, "evidence_source_contents": evidence or [],
            "reasons": [], "confidence": 0.9}


def state_fixture():
    participants = [{"participant_id": "P1", "name": field("Buyer"),
                     "participant_type": "organization"},
                    {"participant_id": "P2", "name": field("Seller"),
                     "participant_type": "organization"}]
    trade = {"name": field("share purchase"),
             "transaction_type": field("share purchase"),
             "timestamp": field("2022-07-13"),
             "from_participant_id": field("P1"), "to_participant_id": field("P2"),
             "instruments": [field("Example common stock")],
             "details": [field("Bought 100 shares for USD 1000",
                               ["Buyer bought 100 shares of Example common stock for USD 1000."])]}
    episodes = [{"episode_id": "E1", "start_time": field("2022-01-01"),
                 "end_time": field("2022-07-31")},
                {"episode_id": "E2", "start_time": field("2022-07-01"),
                 "end_time": field("2022-07-31")}]
    skeleton = {"event_id": "EV", "start_time": field("2022"), "end_time": field("2022"),
                "stages": [{"stage_id": "S1", "start_time": field("2022-01-01"),
                            "end_time": field("2022-12-31"), "episodes": episodes}]}
    results = [{"SkeletonChecker": skeleton}]
    for episode in episodes:
        results.extend([
            {"ParticipantReconstructor": {"participants": copy.deepcopy(participants)}},
            {"TransactionReconstructor": {"transactions": [copy.deepcopy(trade)]}},
            {"EpisodeReconstructor": {**copy.deepcopy(episode), "participants": "placeholder",
                                      "transactions": "placeholder", "participant_relations": []}},
        ])
    results.append({"StageDescriptionReconstructor": {"descriptions": [field("Stage text")]}})
    results.append({"EventDescriptionReconstructor": {"descriptions": [field("Event text")]}})
    return {"agent_results": results, "agent_executed": []}


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

        class BaseBuilder:
            def save_traces(self, traces, save_name, file_format):
                (Path(self.save_dir) / (save_name + ".json")).write_text(
                    json.dumps(traces), encoding="utf-8")

        fake = {
            "langgraph": module("langgraph"),
            "langgraph.graph": module("graph", StateGraph=object, END="END"),
            "langgraph.graph.state": module("state", CompiledStateGraph=object),
            "lmbase": module("lmbase"), "lmbase.inference": module("inference"),
            "lmbase.inference.base": module("base", InferInput=object, InferOutput=object),
            "finmy.builder.base": module("base", BaseBuilder=BaseBuilder, BuildInput=object,
                BuildOutput=types.SimpleNamespace, AgentState=dict),
            "finmy.builder.utils": module("utils", load_python_text=lambda path: "",
                filter_dataclass_fields=lambda *a: "", extract_json_response=lambda x: x,
                run_single_inference=lambda *a, **kw: self.fail("Unexpected model call")),
        }
        with patch.dict(sys.modules, fake):
            spec = importlib.util.spec_from_file_location("epg_builder_test",
                ROOT / "finmy/builder/agent_build/main_build.py")
            loaded = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(loaded)
        self.builder = loaded.AgentEventBuilder()
        self.builder.build_config = {"graph_config": {}}
        self.builder.save_dir = str(self.path)

    def write_results(self, state):
        for i, entry in enumerate(state["agent_results"]):
            name, value = next(iter(entry.items()))
            (self.path / f"{name}-{i}-Result.json").write_text(json.dumps(value), encoding="utf-8")

    def run_builder(self):
        state = state_fixture()
        self.write_results(state)
        self.builder._get_agent_prompts = lambda: ({}, {})
        self.builder.graph = lambda: types.SimpleNamespace(invoke=lambda *a, **kw: state)
        return self.builder.run(None)

    def test_final_return_and_file_reintegration_are_both_validated(self):
        result = self.run_builder()
        final = result.event_cascades
        episodes = final["stages"][0]["episodes"]
        self.assertEqual([len(e["transactions"]) for e in episodes], [0, 1])
        for filename in ("FinalEventCascade.json", "IntegratedEventCascade.json"):
            self.assertEqual(json.loads((self.path / filename).read_text()), final)
        raw = json.loads((self.path / "RawEventCascade.json").read_text())
        self.assertEqual(sum(len(e["transactions"]) for e in raw["stages"][0]["episodes"]), 2)
        report = json.loads((self.path / "epg_validation_report.json").read_text())
        self.assertEqual(result.extras["epg_validation"], report)
        self.assertEqual(final["descriptions"], raw["descriptions"])
        self.assertEqual(final["stages"][0]["descriptions"], raw["stages"][0]["descriptions"])

    def test_integration_does_not_mutate_agent_results(self):
        state = state_fixture()
        original = copy.deepcopy(state)
        self.builder.integrate_results(state)
        self.assertEqual(state, original)

    def test_disable_switch_preserves_legacy_result(self):
        self.builder.build_config["epg_validation"] = {"enabled": False}
        output = self.run_builder()
        self.assertEqual([len(e["transactions"]) for e in output.event_cascades["stages"][0]["episodes"]], [1, 1])
        self.assertFalse((self.path / "epg_validation_report.json").exists())

    def test_check_only_preserves_transactions_and_produces_report(self):
        self.builder.build_config["epg_validation"] = {"deduplicate": False}
        output = self.run_builder()
        self.assertEqual([len(e["transactions"]) for e in output.event_cascades["stages"][0]["episodes"]], [1, 1])
        self.assertTrue((self.path / "epg_validation_report.json").exists())

    def test_invalid_config_fails_explicitly(self):
        for options in (False, {"enabled": "false"}, {"deduplicate": "true"}):
            with self.subTest(options=options):
                self.builder.build_config["epg_validation"] = options
                with self.assertRaises(ValueError):
                    self.builder.integrate_results(state_fixture())

    def test_cli_keeps_input_bytes_and_refuses_overwrite(self):
        self.builder.build_config["epg_validation"] = {"enabled": False}
        original = self.builder.integrate_results(state_fixture())
        source = self.path / "source.json"
        source.write_text(json.dumps(original), encoding="utf-8")
        before = source.read_bytes()
        cmd = [sys.executable, str(ROOT / "scripts/validate_epg.py"), str(source),
               "--output-dir", str(self.path / "validated")]
        run = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(source.read_bytes(), before)
        self.assertNotEqual(json.loads((self.path / "validated/FinalEventCascade.json").read_text()), original)
        repeat = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(repeat.returncode, 0)
        self.assertIn("Refusing to overwrite", repeat.stderr)


if __name__ == "__main__":
    unittest.main()
