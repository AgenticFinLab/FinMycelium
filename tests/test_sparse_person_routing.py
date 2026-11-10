"""Offline coverage for the default sparse person entry and config boundaries."""

import copy
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from finmy.reconstruction_scope import read_reconstruction
from finmy.subject_graph.runner import SPARSE_ROLES, build_from_contents, subject_builder_config


ROOT = Path(__file__).resolve().parents[1]


def scoped(mode="person", builder=None):
    config = {"reconstruction": {"mode": mode, "subject": {
        "subject_id": "person_test", "name": "Test Person",
        "coverage_start": "2022", "coverage_end": "2023",
    }}}
    if builder is not None:
        config["builder_type"] = builder
    return config


class SparsePersonRoutingTests(unittest.TestCase):
    def test_missing_builder_defaults_to_sparse_without_mutation(self):
        source = {"builder_config": scoped()}
        original = copy.deepcopy(source)
        result = subject_builder_config(source)
        self.assertEqual(result["builder_type"], "SparseRagBuilder")
        self.assertEqual(set(result["agents"]), set(SPARSE_ROLES))
        self.assertEqual(read_reconstruction(result)["mode"], "person")
        self.assertEqual(source, original)

    def test_explicit_legacy_builder_is_preserved(self):
        source = scoped(builder="AgentEventBuilder")
        self.assertEqual(subject_builder_config(source), source)


        # Conflicting settings are intentionally retained for runtime validation.


    def test_saved_text_dispatches_to_selected_builder(self):
        calls = []

        class Sparse:
            def __init__(self, build_config):
                self.config = build_config
                self.save_dir = "output/synthetic-sparse"

            def run(self, inputs):
                calls.append((type(self).__name__, self.config, inputs))
                return SimpleNamespace(subject_graph={"synthetic": True})

        class Legacy(Sparse):
            pass

        base = ModuleType("finmy.builder.base")
        base.BuildInput = SimpleNamespace
        sparse = ModuleType("finmy.builder.sparse_build.main_build")
        sparse.SparseRagBuilder = Sparse
        legacy = ModuleType("finmy.builder.agent_build.main_build")
        legacy.AgentEventBuilder = Legacy
        with patch.dict("sys.modules", {
            base.__name__: base, sparse.__name__: sparse, legacy.__name__: legacy,
        }):
            output, directory = build_from_contents(["Unchanged source text"], "Request", ["key"], scoped())
            self.assertEqual(calls[-1][0], "Sparse")
            self.assertEqual(calls[-1][2].samples[0].content, "Unchanged source text")
            self.assertEqual(calls[-1][2].user_query.query_text, "Request")
            self.assertEqual(directory, "output/synthetic-sparse")
            self.assertEqual(output.subject_graph, {"synthetic": True})
            build_from_contents(["Evidence"], "Request", [], scoped(builder="AgentEventBuilder"))
            self.assertEqual(calls[-1][0], "Legacy")

    def test_standard_and_person_configs_default_to_valid_seven_role_shape(self):
        for name in ("search_pipeline.yml", "sparse_pipeline.yml", "person_sparse.yml"):
            with self.subTest(config=name):
                config = yaml.safe_load((ROOT / "configs" / name).read_text())
                builder = config["builder_config"]
                self.assertEqual(builder["builder_type"], "SparseRagBuilder")
                self.assertEqual(set(builder["agents"]), set(SPARSE_ROLES))
                self.assertTrue(builder["sparse_builder_config"]["enable_sparse_routing"])
                for role in builder["agents"].values():
                    for key in ("lm_type", "lm_name", "generation_config"):
                        if key in role:
                            self.assertEqual(role[key], builder[key])
        self.assertEqual(read_reconstruction(yaml.safe_load(
            (ROOT / "configs/person_sparse.yml").read_text()))["mode"], "person")


if __name__ == "__main__":
    unittest.main()
