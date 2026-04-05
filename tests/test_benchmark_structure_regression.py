import unittest

from finmy.builder.agent_build.prompts import (
    StageDescriptionReconstructorSys,
    StageDescriptionReconstructorUser,
)


class BenchmarkStructureRegressionTest(unittest.TestCase):
    def test_stage_description_prompt_retains_expected_benchmark_shape(self):
        combined_prompt = "\n".join(
            [StageDescriptionReconstructorSys, StageDescriptionReconstructorUser]
        )

        self.assertIn("TargetStage", combined_prompt)
        self.assertIn("Content", combined_prompt)
        self.assertIn("RetrievedContext", combined_prompt)
        self.assertIn("RetrievedContextSummary", combined_prompt)
        self.assertIn("additive evidence only", combined_prompt)
        self.assertIn("=== RETRIEVED CONTEXT BEGIN ===", combined_prompt)
        self.assertIn("=== RETRIEVED CONTEXT SUMMARY BEGIN ===", combined_prompt)
        self.assertNotIn("TargetEpisode", combined_prompt)


if __name__ == "__main__":
    unittest.main()
