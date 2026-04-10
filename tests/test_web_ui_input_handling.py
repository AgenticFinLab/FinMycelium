import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
STUBBED_MODULE_NAMES = [
    "streamlit",
    "finmy.web_ui.utils.formatters",
    "finmy.url_collector.SearchCollector.bocha_search",
    "finmy.url_collector.SearchCollector.baidu_search",
    "finmy.url_collector.base",
    "finmy.url_collector.url_parser",
    "finmy.url_collector.url_parser_clean",
    "finmy.pdf_collector.base",
    "finmy.pdf_collector.pdf_collector",
]


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _install_data_collector_stubs():
    streamlit_stub = types.SimpleNamespace(write=lambda *a, **k: None)
    sys.modules["streamlit"] = streamlit_stub

    formatters_mod = types.ModuleType("finmy.web_ui.utils.formatters")
    formatters_mod.format_timestamp = lambda: "2026-04-10 00:00:00"
    sys.modules["finmy.web_ui.utils.formatters"] = formatters_mod

    bocha_mod = types.ModuleType("finmy.url_collector.SearchCollector.bocha_search")
    bocha_mod.bochasearch_api = lambda *a, **k: {"data": {"webPages": {"value": []}}}
    sys.modules["finmy.url_collector.SearchCollector.bocha_search"] = bocha_mod

    baidu_mod = types.ModuleType("finmy.url_collector.SearchCollector.baidu_search")
    baidu_mod.baidusearch_api = lambda *a, **k: {"references": []}
    sys.modules["finmy.url_collector.SearchCollector.baidu_search"] = baidu_mod

    base_mod = types.ModuleType("finmy.url_collector.base")

    class URLCollectorInput:
        def __init__(self, urls):
            self.urls = urls

    base_mod.URLCollectorInput = URLCollectorInput
    sys.modules["finmy.url_collector.base"] = base_mod

    parser_mod = types.ModuleType("finmy.url_collector.url_parser")

    class URLParser:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def run(self, _input):
            return types.SimpleNamespace(results=[])

    parser_mod.URLParser = URLParser
    sys.modules["finmy.url_collector.url_parser"] = parser_mod

    parser_clean_mod = types.ModuleType("finmy.url_collector.url_parser_clean")
    parser_clean_mod.extract_content_from_parsed_content = lambda content: ""
    sys.modules["finmy.url_collector.url_parser_clean"] = parser_clean_mod

    pdf_base_mod = types.ModuleType("finmy.pdf_collector.base")

    class PDFCollectorInput:
        def __init__(self, input_pdf_path, keywords):
            self.input_pdf_path = input_pdf_path
            self.keywords = keywords

    pdf_base_mod.PDFCollectorInput = PDFCollectorInput
    sys.modules["finmy.pdf_collector.base"] = pdf_base_mod

    pdf_mod = types.ModuleType("finmy.pdf_collector.pdf_collector")

    class PDFCollector:
        def __init__(self, config):
            self.config = config

        def collect(self, _input):
            return types.SimpleNamespace(records=[])

    pdf_mod.PDFCollector = PDFCollector
    sys.modules["finmy.pdf_collector.pdf_collector"] = pdf_mod


def _make_bocha_results(urls):
    return {
        "data": {
            "webPages": {
                "value": [
                    {
                        "name": f"Bocha result {index}",
                        "url": url,
                        "snippet": f"Snippet for {url}",
                        "summary": f"Summary for {url}",
                        "siteName": url.split("/")[2],
                        "datePublished": "2026-04-10",
                    }
                    for index, url in enumerate(urls, start=1)
                ]
            }
        }
    }


def _make_baidu_results(urls):
    return {
        "references": [
            {
                "title": f"Baidu result {index}",
                "url": url,
                "snippet": f"Snippet for {url}",
                "content": f"Content for {url}",
                "website": url.split("/")[2],
                "date": "2026-04-10",
            }
            for index, url in enumerate(urls, start=1)
        ]
    }


def _parsed_urls_from_run_calls(run_mock):
    return [call.args[0].urls[0] for call in run_mock.call_args_list]


class IsolatedUiModuleTestCase(unittest.TestCase):
    def setUp(self):
        self._original_modules = {
            name: sys.modules.get(name) for name in STUBBED_MODULE_NAMES
        }
        for name in STUBBED_MODULE_NAMES:
            sys.modules.pop(name, None)

        _install_data_collector_stubs()
        self.validators_module = _load_module(
            "ui_validators_module",
            "finmy/web_ui/utils/validators.py",
        )
        self.data_collector_module = _load_module(
            "ui_data_collector_module",
            "finmy/web_ui/services/data_collector_service.py",
        )
        self.parse_keywords = self.validators_module.parse_keywords
        self.DataCollectorService = self.data_collector_module.DataCollectorService

    def tearDown(self):
        for name in STUBBED_MODULE_NAMES:
            sys.modules.pop(name, None)

        for name, original in self._original_modules.items():
            if original is not None:
                sys.modules[name] = original

    def make_temp_dir(self) -> tempfile.TemporaryDirectory:
        return tempfile.TemporaryDirectory(prefix="ui-fixer-test-")


class KeywordParsingTests(IsolatedUiModuleTestCase):
    def test_parse_keywords_preserves_comma_delimited_phrases(self):
        keywords = self.parse_keywords("fraud,money laundering,Qian Zhimin")

        self.assertEqual(
            keywords,
            ["fraud", "money laundering", "Qian Zhimin"],
        )


class DataCollectorConfigTests(IsolatedUiModuleTestCase):
    def test_data_collector_service_uses_url_collector_config(self):
        config = {
            "url_collector_config": {
                "delay": 0.5,
                "use_selenium_fallback": False,
                "selenium_wait_time": 2,
            }
        }

        with patch.object(self.data_collector_module, "URLParser") as parser_cls:
            self.DataCollectorService(config, "/tmp/ui-fixer-test-output")

        parser_cls.assert_called_once()
        _, kwargs = parser_cls.call_args
        self.assertEqual(kwargs["delay"], 0.5)
        self.assertFalse(kwargs["use_selenium_fallback"])
        self.assertEqual(kwargs["selenium_wait_time"], 2)

    def test_collect_bocha_search_results_skips_blocked_domains(self):
        config = {
            "url_collector_config": {
                "blocked_domains": ["blocked.example"],
                "bocha_parse_limit": 10,
            }
        }
        bocha_urls = [
            "https://blocked.example/article-1",
            "https://allowed.example/article-2",
            "https://allowed.example/article-3",
        ]

        with self.make_temp_dir() as save_dir, patch.object(
            self.data_collector_module,
            "bochasearch_api",
            return_value=_make_bocha_results(bocha_urls),
        ), patch.object(self.data_collector_module, "URLParser") as parser_cls:
            parser_instance = parser_cls.return_value
            parser_instance.run.side_effect = lambda collector_input: types.SimpleNamespace(
                results=[{"content": f"parsed:{collector_input.urls[0]}"}]
            )

            service = self.DataCollectorService(config, save_dir)
            service.collect_bocha_search_results("fraud", ["fraud"])

        self.assertEqual(parser_instance.run.call_count, 2)
        self.assertEqual(
            _parsed_urls_from_run_calls(parser_instance.run),
            [
                "https://allowed.example/article-2",
                "https://allowed.example/article-3",
            ],
        )

    def test_collect_baidu_search_results_prefers_configured_domains_before_parsing(self):
        config = {
            "url_collector_config": {
                "preferred_domains": ["preferred.example"],
                "baidu_parse_limit": 10,
            }
        }
        baidu_urls = [
            "https://other.example/article-1",
            "https://preferred.example/article-2",
            "https://other.example/article-3",
        ]

        with self.make_temp_dir() as save_dir, patch.object(
            self.data_collector_module,
            "baidusearch_api",
            return_value=_make_baidu_results(baidu_urls),
        ), patch.object(self.data_collector_module, "URLParser") as parser_cls:
            parser_instance = parser_cls.return_value
            parser_instance.run.side_effect = lambda collector_input: types.SimpleNamespace(
                results=[{"content": f"parsed:{collector_input.urls[0]}"}]
            )

            service = self.DataCollectorService(config, save_dir)
            service.collect_baidu_search_results("fraud", ["fraud"])

        self.assertEqual(
            _parsed_urls_from_run_calls(parser_instance.run),
            [
                "https://preferred.example/article-2",
                "https://other.example/article-1",
                "https://other.example/article-3",
            ],
        )

    def test_collect_baidu_search_results_respects_parse_limit_after_filtering(self):
        config = {
            "url_collector_config": {
                "blocked_domains": ["blocked.example"],
                "baidu_parse_limit": 2,
            }
        }
        baidu_urls = [
            "https://blocked.example/article-1",
            "https://allowed.example/article-2",
            "https://blocked.example/article-3",
            "https://allowed.example/article-4",
            "https://allowed.example/article-5",
        ]

        with self.make_temp_dir() as save_dir, patch.object(
            self.data_collector_module,
            "baidusearch_api",
            return_value=_make_baidu_results(baidu_urls),
        ), patch.object(self.data_collector_module, "URLParser") as parser_cls:
            parser_instance = parser_cls.return_value
            parser_instance.run.side_effect = lambda collector_input: types.SimpleNamespace(
                results=[{"content": f"parsed:{collector_input.urls[0]}"}]
            )

            service = self.DataCollectorService(config, save_dir)
            service.collect_baidu_search_results("fraud", ["fraud"])

        self.assertEqual(parser_instance.run.call_count, 2)
        self.assertEqual(
            _parsed_urls_from_run_calls(parser_instance.run),
            [
                "https://allowed.example/article-2",
                "https://allowed.example/article-4",
            ],
        )

    def test_phrase_keywords_work_with_filtered_ui_search_selection(self):
        keywords = self.parse_keywords("fraud,money laundering,Qian Zhimin")
        config = {
            "url_collector_config": {
                "preferred_domains": ["preferred.example"],
                "blocked_domains": ["blocked.example"],
                "baidu_parse_limit": 3,
            }
        }
        baidu_urls = [
            "https://blocked.example/article-1",
            "https://other.example/article-2",
            "https://preferred.example/article-3",
            "https://other.example/article-4",
        ]

        with self.make_temp_dir() as save_dir, patch.object(
            self.data_collector_module,
            "baidusearch_api",
            return_value=_make_baidu_results(baidu_urls),
        ), patch.object(self.data_collector_module, "URLParser") as parser_cls:
            parser_instance = parser_cls.return_value
            parser_instance.run.side_effect = lambda collector_input: types.SimpleNamespace(
                results=[{"content": f"parsed:{collector_input.urls[0]}"}]
            )

            service = self.DataCollectorService(config, save_dir)
            service.collect_baidu_search_results("fraud", keywords)

        self.assertEqual(
            keywords,
            ["fraud", "money laundering", "Qian Zhimin"],
        )
        self.assertEqual(
            _parsed_urls_from_run_calls(parser_instance.run),
            [
                "https://preferred.example/article-3",
                "https://other.example/article-2",
                "https://other.example/article-4",
            ],
        )


if __name__ == "__main__":
    unittest.main()
