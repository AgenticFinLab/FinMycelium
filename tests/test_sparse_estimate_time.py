"""Offline checks for the time estimate used before reconstruction starts."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from finmy.builder.constant import BuildType


class SparseEstimateTimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The estimator is pure; load it without requiring model providers.
        inference = types.ModuleType("lmbase.inference")
        inference.InferInput = type("InferInput", (), {})
        inference.InferOutput = type("InferOutput", (), {})
        source = Path(__file__).resolve().parents[1] / "finmy/builder/utils.py"
        spec = importlib.util.spec_from_file_location("estimate_utils_test", source)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {
            "lmbase": types.ModuleType("lmbase"),
            "lmbase.inference": inference,
        }):
            spec.loader.exec_module(module)
        cls.estimate = staticmethod(module.estimate_complete_time)

    def test_sparse_string_and_enum_use_agent_estimate(self):
        contents = ["甲" * 1000]
        agent_minutes = self.estimate(contents, "AgentEventBuilder")
        for mode in ("SparseRagBuilder", BuildType.SPARSE_BUILD):
            with self.subTest(mode=mode):
                self.assertEqual(agent_minutes, self.estimate(contents, mode))

    def test_legacy_builder_estimates_remain_unchanged(self):
        contents = ["甲" * 1000]
        for mode, expected in (
            ("ClassEventBuilder", 1), (BuildType.CLASS_BUILD, 1),
            ("AgentEventBuilder", 2), (BuildType.AGENT_BUILD, 2),
        ):
            with self.subTest(mode=mode):
                self.assertEqual(expected, self.estimate(contents, mode))

    def test_invalid_builder_modes_remain_rejected(self):
        for mode in ("UnsupportedBuilder", "", None):
            with self.subTest(mode=mode):
                with self.assertRaises(ValueError):
                    self.estimate(["source"], mode)


if __name__ == "__main__":
    unittest.main()
