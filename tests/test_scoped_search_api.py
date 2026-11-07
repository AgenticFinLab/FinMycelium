"""Offline checks for native provider date filters and bounded requests."""
import types
import unittest
from unittest.mock import Mock, patch

from finmy.runner.scoped_search_api import search


class ScopedSearchApiTests(unittest.TestCase):
    def setUp(self):
        self.response = Mock()
        self.requests = types.SimpleNamespace(post=Mock(return_value=self.response))
        self.dotenv = types.SimpleNamespace(load_dotenv=Mock())
        self.modules = patch.dict("sys.modules", {"requests": self.requests, "dotenv": self.dotenv})
        self.env = patch.dict("os.environ", {"BOCHA_API_KEY": "fake", "BAIDUSEARCH_API_KEY": "fake"})
        self.modules.start()
        self.env.start()
        self.addCleanup(self.modules.stop)
        self.addCleanup(self.env.stop)

    def test_bocha_native_range_and_normalized_metadata(self):
        self.response.json.return_value = {"code": 200, "data": {"webPages": {"value": [
            {"name": "Letter", "url": "https://example.test/letter", "datePublished": "2023-02-25", "snippet": "hint"}
        ]}}}
        rows = search("bocha", '"Warren Buffett" 2023 shareholder letter', 3, "2023-01-01", "2023-12-31")
        args, kwargs = self.requests.post.call_args
        self.assertEqual(args[0], "https://api.bocha.cn/v1/web-search")
        self.assertEqual(kwargs["json"]["freshness"], "2023-01-01..2023-12-31")
        self.assertFalse(kwargs["json"]["summary"])
        self.assertEqual(kwargs["timeout"], (10, 25))
        self.assertEqual(rows[0], {"title": "Letter", "url": "https://example.test/letter", "published_at": "2023-02-25", "snippet": "hint"})
        self.response.raise_for_status.assert_called_once()

    def test_baidu_uses_publication_range_web_only_and_timeout(self):
        self.response.json.return_value = {"references": [
            {"title": "Meeting", "url": "https://example.test/meeting", "date": "2022-05-01", "content": "discovery hint"}
        ]}
        rows = search("baidu", "meeting", 5, "2022-03-01", "2022-12-31", timeout=7)
        args, kwargs = self.requests.post.call_args
        self.assertEqual(args[0], "https://qianfan.baidubce.com/v2/ai_search/web_search")
        self.assertEqual(kwargs["json"]["search_filter"], {"range": {"page_time": {"gte": "2022-03-01", "lte": "2022-12-31"}}})
        self.assertEqual(kwargs["json"]["resource_type_filter"], [{"type": "web", "top_k": 5}])
        self.assertEqual(kwargs["timeout"], (7, 7))
        self.assertEqual(rows[0]["published_at"], "2022-05-01")
        self.assertEqual(rows[0]["snippet"], "discovery hint")

    def test_errors_never_retry_without_bounds(self):
        self.response.raise_for_status.side_effect = RuntimeError("HTTP failure")
        with self.assertRaises(RuntimeError):
            search("bocha", "query", 5, "2022-01-01", "2022-12-31")
        self.requests.post.assert_called_once()

    def test_invalid_bounds_and_missing_credentials_fail_before_request(self):
        for start, end in [("2022", "2023"), ("2023-01-01", "2022-01-01"), (None, "2022-12-31")]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                search("baidu", "query", 5, start, end)
        with patch.dict("os.environ", {"BOCHA_API_KEY": ""}), self.assertRaisesRegex(ValueError, "Missing BOCHA_API_KEY"):
            search("bocha", "query", 5, "2022-01-01", "2022-12-31")
        self.requests.post.assert_not_called()

    def test_provider_errors_and_malformed_results_are_not_empty_success(self):
        for data in [{"code": 403}, {}, {"data": {"webPages": {"value": None}}}]:
            self.response.json.return_value = data
            with self.subTest(data=data), self.assertRaises(ValueError):
                search("bocha", "query", 5, "2022-01-01", "2022-12-31")


if __name__ == "__main__":
    unittest.main()
