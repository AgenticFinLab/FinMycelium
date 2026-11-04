"""Offline HTML extraction and bounded fetching checks."""
import types
import unittest
from unittest.mock import Mock, patch

from finmy.runner.scoped_page import parse, parse_html, _public_url, MAX_BYTES


class ScopedPageTests(unittest.TestCase):
    def test_article_body_and_own_date_links(self):
        html = '''<html><head><meta property="article:published_time" content="2023-05-06T09:00:00Z"></head>
        <body><nav>navigation noise</nav><main><article><h1>Meeting transcript</h1>
        <p>Buffett: We discussed investment decisions in detail.</p>
        <p>Question: How do you assess risk?</p><a href="/full#speech">Full transcript</a>
        <script>tracking_noise()</script></article></main><footer>footer noise</footer></body></html>'''
        result = parse_html(html, "https://example.test/meeting")
        self.assertIn("Buffett: We discussed", result["text"])
        self.assertNotIn("noise", result["text"])
        self.assertEqual(result["published_at"], "2023-05-06T09:00:00+00:00")
        self.assertEqual(result["links"], [{"url": "https://example.test/full", "text": "Full transcript"}])

    def test_event_dates_and_modified_dates_do_not_become_publication_dates(self):
        html = '<meta property="article:modified_time" content="2024-01-01"><p>Meeting held on 2023-05-06.</p><script type="application/ld+json">{"@type":"Article","dateModified":"2024-01-01"}</script>'
        self.assertIsNone(parse_html(html, "https://example.test/a")["published_at"])
        html = '<script type="application/ld+json">{"@graph":[{"@type":"NewsArticle","url":"/a","datePublished":"2023-05-07"}]}</script><main>Actual article</main>'
        self.assertEqual(parse_html(html, "https://example.test/a")["published_at"], "2023-05-07")

    def test_private_targets_rejected(self):
        with self.assertRaises(ValueError):
            _public_url("http://localhost/path")
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 80))]), self.assertRaises(ValueError):
            _public_url("https://example.test/")

    def test_fetch_is_bounded_and_closes_response(self):
        response = Mock(status_code=200, headers={"Content-Type": "text/html"})
        response.iter_content.return_value = [b"<article>Complete source paragraph</article>"]
        requests = types.SimpleNamespace(get=Mock(return_value=response))
        with patch.dict("sys.modules", {"requests": requests}), patch("finmy.runner.scoped_page._public_url"):
            result = parse("https://example.test/", timeout=9)
        self.assertIn("Complete source", result["text"])
        self.assertFalse(requests.get.call_args.kwargs["allow_redirects"])
        self.assertTrue(requests.get.call_args.kwargs["stream"])
        self.assertLessEqual(requests.get.call_args.kwargs["timeout"][1], 9)
        response.close.assert_called_once()

    def test_non_html_and_oversized_pages_fail(self):
        for headers in [{"Content-Type": "application/pdf"}, {"Content-Type": "text/html", "Content-Length": str(MAX_BYTES+1)}]:
            response = Mock(status_code=200, headers=headers)
            requests = types.SimpleNamespace(get=Mock(return_value=response))
            with patch.dict("sys.modules", {"requests": requests}), patch("finmy.runner.scoped_page._public_url"), self.assertRaises(ValueError):
                parse("https://example.test/")
            response.close.assert_called_once()

    def test_redirect_target_checked_before_request(self):
        response = Mock(status_code=302, headers={"Location": "http://localhost/secret"})
        requests = types.SimpleNamespace(get=Mock(return_value=response))
        with patch.dict("sys.modules", {"requests": requests}), patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("8.8.8.8", 443))]), self.assertRaises(ValueError):
            parse("https://example.test/")
        requests.get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
