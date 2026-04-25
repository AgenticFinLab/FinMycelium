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

    def test_collect_search_contents_passes_configured_bocha_count(self):
        from finmy.runner.search_pipeline_runner import collect_search_contents

        with tempfile.TemporaryDirectory() as tmpdir:
            save_dir = Path(tmpdir)
            parser = Mock()

            def fake_bocha_search(query, *, summary, count):
                self.assertEqual(query, "Event query")
                self.assertTrue(summary)
                self.assertEqual(count, 20)
                return {"data": {"webPages": {"value": []}}}

            with patch(
                "finmy.runner.search_pipeline_runner._bocha_search",
                side_effect=fake_bocha_search,
            ), patch(
                "finmy.runner.search_pipeline_runner._baidu_search",
                return_value={"references": []},
            ):
                result = collect_search_contents(
                    search_query="Event query",
                    keywords=["alpha"],
                    save_dir=save_dir,
                    parser=parser,
                    bocha_count=20,
                )

        self.assertEqual(result["bocha_result_count"], 0)
        self.assertEqual(result["baidu_result_count"], 0)

    def test_collect_search_contents_limits_baidu_results_by_configured_count(self):
        from finmy.runner.search_pipeline_runner import collect_search_contents

        with tempfile.TemporaryDirectory() as tmpdir:
            save_dir = Path(tmpdir)
            parser = Mock()
            parser.run.side_effect = [
                SimpleNamespace(results=[{"content": [{"text": "baidu parsed one"}]}]),
            ]

            baidu_response = {
                "references": [
                    {
                        "title": "Baidu title one",
                        "url": "https://example.com/baidu-one",
                        "snippet": "baidu snippet one",
                        "content": "baidu content one",
                        "website": "Baidu Site",
                        "date": "2026-04-14",
                    },
                    {
                        "title": "Baidu title two",
                        "url": "https://example.com/baidu-two",
                        "snippet": "baidu snippet two",
                        "content": "baidu content two",
                        "website": "Baidu Site",
                        "date": "2026-04-14",
                    },
                ]
            }

            with patch(
                "finmy.runner.search_pipeline_runner._bocha_search",
                return_value={"data": {"webPages": {"value": []}}},
            ), patch(
                "finmy.runner.search_pipeline_runner._baidu_search",
                return_value=baidu_response,
            ), patch(
                "finmy.runner.search_pipeline_runner._render_parsed_content",
                side_effect=lambda parsed: parsed[0]["text"],
            ):
                result = collect_search_contents(
                    search_query="Event query",
                    keywords=["alpha"],
                    save_dir=save_dir,
                    parser=parser,
                    baidu_count=1,
                )

        self.assertEqual(result["baidu_result_count"], 1)
        self.assertEqual(len(result["all_text_content"]), 1)
        self.assertIn("Baidu title one", result["all_text_content"][0])

    def test_collect_search_contents_filters_and_interleaves_search_results(self):
        from finmy.runner.search_pipeline_runner import collect_search_contents

        with tempfile.TemporaryDirectory() as tmpdir:
            save_dir = Path(tmpdir)
            parser = Mock()
            parser.run.side_effect = [
                SimpleNamespace(results=[{"content": [{"text": "bocha parsed alpha " * 20}]}]),
                SimpleNamespace(results=[{"content": []}]),
                SimpleNamespace(results=[{"content": [{"text": "bocha parsed gamma " * 20}]}]),
                SimpleNamespace(results=[{"content": [{"text": "baidu parsed beta " * 20}]}]),
                SimpleNamespace(results=[{"content": [{"text": "baidu duplicate alpha " * 20}]}]),
                SimpleNamespace(results=[{"content": [{"text": "baidu parsed delta " * 20}]}]),
            ]

            bocha_response = {
                "data": {
                    "webPages": {
                        "value": [
                            {
                                "name": "Bocha Alpha",
                                "url": "https://example.com/alpha",
                                "snippet": "alpha snippet",
                                "summary": "alpha summary",
                                "siteName": "Bocha Site",
                                "datePublished": "2026-04-14",
                            },
                            {
                                "name": "Short Navigation",
                                "url": "https://example.com/nav",
                                "snippet": "tiny",
                                "summary": "",
                                "siteName": "Example",
                                "datePublished": "2026-04-14",
                            },
                            {
                                "name": "Bocha Gamma",
                                "url": "https://example.com/gamma",
                                "snippet": "gamma snippet",
                                "summary": "gamma summary",
                                "siteName": "Bocha Site",
                                "datePublished": "2026-04-14",
                            },
                        ]
                    }
                }
            }
            baidu_response = {
                "references": [
                    {
                        "title": "Baidu Beta",
                        "url": "https://example.com/beta",
                        "snippet": "beta snippet",
                        "content": "beta content",
                        "website": "Baidu Site",
                        "date": "2026-04-14",
                    },
                    {
                        "title": "Baidu Alpha Duplicate",
                        "url": "https://example.com/alpha/",
                        "snippet": "duplicate alpha snippet",
                        "content": "duplicate alpha content",
                        "website": "Baidu Site",
                        "date": "2026-04-14",
                    },
                    {
                        "title": "Baidu Delta",
                        "url": "https://example.com/delta",
                        "snippet": "delta snippet",
                        "content": "delta content",
                        "website": "Baidu Site",
                        "date": "2026-04-14",
                    },
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
                side_effect=lambda parsed: parsed[0]["text"] if parsed else "",
            ):
                result = collect_search_contents(
                    search_query="Event query",
                    keywords=["alpha", "beta"],
                    save_dir=save_dir,
                    parser=parser,
                    merge_strategy="interleave",
                    quality_filter={
                        "enabled": True,
                        "min_text_chars": 300,
                        "dedupe_url": True,
                    },
                )
            filtered_bocha_exists = Path(result["filtered_bocha_results_path"]).exists()
            filtered_baidu_exists = Path(result["filtered_baidu_results_path"]).exists()

        titles = [
            line
            for content in result["all_text_content"]
            for line in content.splitlines()
            if line in {"Bocha Alpha", "Bocha Gamma", "Baidu Beta", "Baidu Delta"}
        ]
        self.assertEqual(titles, ["Bocha Alpha", "Baidu Beta", "Bocha Gamma", "Baidu Delta"])
        self.assertEqual(result["bocha_result_count"], 3)
        self.assertEqual(result["baidu_result_count"], 3)
        self.assertEqual(result["filtered_bocha_result_count"], 2)
        self.assertEqual(result["filtered_baidu_result_count"], 2)
        self.assertEqual(len(result["all_text_content"]), 4)
        self.assertTrue(filtered_bocha_exists)
        self.assertTrue(filtered_baidu_exists)

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

    def test_limit_content_length_keeps_legacy_greedy_behavior_by_default(self):
        from finmy.runner.search_pipeline_runner import _limit_content_length

        limited = _limit_content_length(
            ["1234567890", "abcdef", "zzz"],
            max_length=15,
        )

        self.assertEqual(limited, ["1234567890"])

    def test_limit_content_length_evidence_aware_keeps_keyword_window_from_long_content(self):
        from finmy.runner.search_pipeline_runner import _limit_content_length

        long_content = "\n".join(
            [
                "Skip to main content",
                "Navigation Search Subscribe Sign in",
                "background " * 80,
                "ordinary filler " * 80,
                "In 2024, Acme Bank entered emergency resolution after a liquidity run.",
                "ordinary tail " * 80,
            ]
        )

        limited = _limit_content_length(
            [long_content, "short follow-up report"],
            max_length=1200,
            query_text="Acme Bank liquidity run",
            keywords=["emergency resolution"],
            trim_config={
                "content_trim_mode": "evidence_aware",
                "per_item_soft_cap": 320,
                "per_item_hard_cap": 700,
                "head_chars": 120,
                "keyword_window_chars": 220,
                "min_item_chars": 80,
            },
        )

        self.assertEqual(len(limited), 2)
        self.assertIn("Acme Bank entered emergency resolution", limited[0])
        self.assertNotIn("Skip to main content", limited[0])
        self.assertLessEqual(len(limited[0]), 700)

    def test_limit_content_length_evidence_aware_respects_total_and_per_item_caps(self):
        from finmy.runner.search_pipeline_runner import _limit_content_length

        contents = [
            "Event Alpha 2024 " + ("dense evidence " * 120),
            "Event Alpha settlement " + ("details " * 120),
            "Event Alpha aftermath " + ("details " * 120),
        ]

        limited = _limit_content_length(
            contents,
            max_length=900,
            query_text="Event Alpha settlement",
            keywords=["Event Alpha", "settlement"],
            trim_config={
                "content_trim_mode": "evidence_aware",
                "per_item_soft_cap": 260,
                "per_item_hard_cap": 360,
                "head_chars": 100,
                "keyword_window_chars": 160,
                "min_item_chars": 80,
            },
        )

        self.assertGreaterEqual(len(limited), 2)
        self.assertLessEqual(sum(len(item) for item in limited), 900)
        self.assertTrue(all(len(item) <= 360 for item in limited))
        self.assertTrue(any("settlement" in item for item in limited))

    def test_run_search_pipeline_passes_configured_bocha_count_to_search(self):
        from finmy.runner.search_pipeline_runner import run_search_pipeline

        config = {
            "output_dir": "/unused/output",
            "search_config": {
                "bocha_count": 15,
                "baidu_count": 15,
                "merge_strategy": "interleave",
                "quality_filter": {"enabled": True, "min_text_chars": 300},
            },
            "all_content_config": {"max_content_length": 1000},
        }
        fake_pipeline = Mock()
        fake_pipeline.lm_build_pipeline_with_contents.return_value = {"status": "ok"}

        with tempfile.TemporaryDirectory() as tmpdir:
            save_dir = Path(tmpdir)

            def fake_collect_search_contents(**kwargs):
                self.assertEqual(kwargs.get("bocha_count"), 15)
                self.assertEqual(kwargs.get("baidu_count"), 15)
                self.assertEqual(kwargs.get("merge_strategy"), "interleave")
                self.assertEqual(
                    kwargs.get("quality_filter"),
                    {"enabled": True, "min_text_chars": 300},
                )
                return {
                    "all_text_content": ["content a"],
                    "bocha_result_count": 1,
                    "baidu_result_count": 0,
                    "all_text_content_path": str(save_dir / "All_Text_Content.json"),
                }

            with patch(
                "finmy.runner.search_pipeline_runner.collect_search_contents",
                side_effect=fake_collect_search_contents,
            ), patch(
                "finmy.runner.search_pipeline_runner._create_pipeline",
                return_value=fake_pipeline,
            ):
                result = run_search_pipeline(
                    config=config,
                    main_input="Main event",
                    keywords=["alpha"],
                    save_dir=save_dir,
                    parser=object(),
                )

        self.assertEqual(result["bocha_result_count"], 1)
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
