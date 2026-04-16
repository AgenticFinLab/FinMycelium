import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import requests


class NonUISearchRunnerTest(unittest.TestCase):
    def test_collect_search_contents_formats_and_saves_results(self):
        from finmy.runner.search_pipeline_runner import collect_search_contents

        with tempfile.TemporaryDirectory() as tmpdir:
            save_dir = Path(tmpdir)
            parser = Mock()
            parser.run.side_effect = [
                SimpleNamespace(results=[{"content": [{"text": "bocha parsed"}]}]),
                SimpleNamespace(results=[{"content": [{"text": "baidu parsed"}]}]),
            ]

            bocha_response = {
                "data": {
                    "webPages": {
                        "value": [
                            {
                                "name": "Bocha title",
                                "url": "https://example.com/bocha",
                                "snippet": "bocha snippet",
                                "summary": "bocha summary",
                                "siteName": "Bocha Site",
                                "datePublished": "2026-04-14",
                            }
                        ]
                    }
                }
            }
            baidu_response = {
                "references": [
                    {
                        "title": "Baidu title",
                        "url": "https://example.com/baidu",
                        "snippet": "baidu snippet",
                        "content": "baidu content",
                        "website": "Baidu Site",
                        "date": "2026-04-14",
                    }
                ]
            }

            with patch(
                "finmy.runner.search_pipeline_runner._bocha_search",
                return_value=bocha_response,
            ), patch(
                "finmy.runner.search_pipeline_runner._baidu_search",
                return_value=baidu_response,
            ), patch(
                "finmy.runner.search_pipeline_runner._render_parsed_content",
                side_effect=lambda parsed: parsed[0]["text"],
            ):
                result = collect_search_contents(
                    search_query="Event query",
                    keywords=["alpha", "beta"],
                    save_dir=save_dir,
                    parser=parser,
                )

            self.assertEqual(len(result["all_text_content"]), 2)
            self.assertIn("Bocha title", result["all_text_content"][0])
            self.assertIn("baidu parsed", result["all_text_content"][1])
            self.assertEqual(result["bocha_result_count"], 1)
            self.assertEqual(result["baidu_result_count"], 1)

            all_text_path = Path(result["all_text_content_path"])
            self.assertTrue(all_text_path.exists())
            payload = json.loads(all_text_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload), 2)

    def test_run_search_pipeline_uses_pipeline_with_limited_contents(self):
        from finmy.runner.search_pipeline_runner import run_search_pipeline

        config = {
            "output_dir": "/unused/output",
            "all_content_config": {"max_content_length": 15},
        }

        fake_pipeline = Mock()
        fake_pipeline.lm_build_pipeline_with_contents.return_value = {"status": "ok"}

        with tempfile.TemporaryDirectory() as tmpdir:
            save_dir = Path(tmpdir)
            search_payload = {
                "all_text_content": ["1234567890", "abcdef", "zzz"],
                "bocha_result_count": 1,
                "baidu_result_count": 2,
                "all_text_content_path": str(save_dir / "All_Text_Content.json"),
            }
            Path(search_payload["all_text_content_path"]).write_text(
                json.dumps(search_payload["all_text_content"], ensure_ascii=False),
                encoding="utf-8",
            )

            with patch(
                "finmy.runner.search_pipeline_runner.collect_search_contents",
                return_value=search_payload,
            ), patch(
                "finmy.runner.search_pipeline_runner._create_pipeline",
                return_value=fake_pipeline,
            ):
                result = run_search_pipeline(
                    config=config,
                    main_input="Main event",
                    keywords=["alpha", "beta"],
                    save_dir=save_dir,
                    parser=object(),
                )

        fake_pipeline.lm_build_pipeline_with_contents.assert_called_once_with(
            contents=["1234567890"],
            query_text="Main event",
            key_words=["alpha", "beta"],
        )
        self.assertEqual(result["search_query"], "Main event \n\nkeywords: alpha beta")
        self.assertEqual(result["bocha_result_count"], 1)
        self.assertEqual(result["baidu_result_count"], 2)
        self.assertEqual(result["pipeline_result"], {"status": "ok"})

    def test_collect_search_contents_tolerates_bocha_invalid_json(self):
        from finmy.runner.search_pipeline_runner import collect_search_contents

        with tempfile.TemporaryDirectory() as tmpdir:
            save_dir = Path(tmpdir)
            parser = Mock()
            parser.run.return_value = SimpleNamespace(
                results=[{"content": [{"text": "baidu parsed"}]}]
            )

            baidu_response = {
                "references": [
                    {
                        "title": "Baidu title",
                        "url": "https://example.com/baidu",
                        "snippet": "baidu snippet",
                        "content": "baidu content",
                        "website": "Baidu Site",
                        "date": "2026-04-15",
                    }
                ]
            }

            with patch(
                "finmy.runner.search_pipeline_runner._bocha_search",
                side_effect=requests.exceptions.JSONDecodeError("Expecting value", "", 0),
            ), patch(
                "finmy.runner.search_pipeline_runner._baidu_search",
                return_value=baidu_response,
            ), patch(
                "finmy.runner.search_pipeline_runner._render_parsed_content",
                side_effect=lambda parsed: parsed[0]["text"],
            ):
                result = collect_search_contents(
                    search_query="Event query",
                    keywords=["alpha", "beta"],
                    save_dir=save_dir,
                    parser=parser,
                )

        self.assertEqual(result["bocha_result_count"], 0)
        self.assertEqual(result["baidu_result_count"], 1)
        self.assertEqual(len(result["all_text_content"]), 1)
        self.assertIn("Baidu title", result["all_text_content"][0])


if __name__ == "__main__":
    unittest.main()
