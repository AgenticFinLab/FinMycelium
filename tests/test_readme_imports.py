import importlib
import unittest


class ReadmeImportRegressionTest(unittest.TestCase):
    def test_class_build_prompts_exports_legacy_crypto_prompt_name(self):
        prompts = importlib.import_module("finmy.builder.class_build.prompts")

        self.assertEqual(prompts.__name__, "finmy.builder.class_build.prompts")
        self.assertTrue(hasattr(prompts, "cryptocurrency_ico_scam"))
        self.assertTrue(
            hasattr(prompts.cryptocurrency_ico_scam, "cryptocurrency_ico_scam_prompt")
        )


if __name__ == "__main__":
    unittest.main()
