import unittest


class BenchmarkStructureRegressionTest(unittest.TestCase):
    def test_benchmark_baseline_structure_and_vocab_remain_locked(self):
        benchmark_contract = {
            "expected_stage_count": 3,
            "expected_episode_count": 8,
            "forbidden_modes": ["late_only", "unknown_empty"],
        }

        self.assertEqual(
            set(benchmark_contract),
            {"expected_stage_count", "expected_episode_count", "forbidden_modes"},
        )
        self.assertEqual(benchmark_contract["expected_stage_count"], 3)
        self.assertEqual(benchmark_contract["expected_episode_count"], 8)
        self.assertEqual(
            benchmark_contract["forbidden_modes"],
            ["late_only", "unknown_empty"],
        )


if __name__ == "__main__":
    unittest.main()
