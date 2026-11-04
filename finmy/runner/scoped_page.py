"""Small bounded HTML reader for scoped retrieval; no browser fallback."""
import datetime as dt
import ipaddress
import json
import math
import re
import socket
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

MAX_BYTES = 4 * 1024 * 1024


def _publication(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    # Accept dates only when supplied by explicit publication metadata.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?", value):
        return None
    try:
        if len(value) == 10:
            return dt.date.fromisoformat(value).isoformat()
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def parse_html(html, url):
    """Extract page body, explicit publication metadata, and discovery links."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    published_at = None
    publication_keys = {"article:published_time", "datepublished", "pubdate", "publishdate", "publication_date"}
    for tag in soup.find_all("meta"):
        key = str(tag.get("property") or tag.get("name") or tag.get("itemprop") or "").lower()
        if key in publication_keys:
            published_at = _publication(tag.get("content"))
            if published_at:
                break
    if published_at is None:
        def dates(value):
            if isinstance(value, list):
                for item in value:
                    yield from dates(item)
            elif isinstance(value, dict):
                # Nested recommended articles must not date the current page.
                kind = value.get("@type", "")
                kinds = kind if isinstance(kind, list) else [kind]
                if any(k in ("Article", "NewsArticle", "BlogPosting", "WebPage", "Report", "ScholarlyArticle") for k in kinds):
                    page_url = value.get("url")
                    if not page_url or (isinstance(page_url, str) and (urlsplit(urljoin(url, page_url)).netloc, urlsplit(urljoin(url, page_url)).path.rstrip("/")) == (urlsplit(url).netloc, urlsplit(url).path.rstrip("/"))):
                        yield _publication(value.get("datePublished"))
                if "@graph" in value:
                    yield from dates(value["@graph"])
                if "mainEntity" in value:
                    yield from dates(value["mainEntity"])
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                published_at = next((value for value in dates(json.loads(tag.get_text())) if value), None)
            except (ValueError, TypeError):
                continue
            if published_at:
                break

    links, seen = [], set()
    for anchor in soup.find_all("a", href=True):
        linked = urljoin(url, anchor["href"])
        parts = urlsplit(linked)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            continue
        linked = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
        if linked in seen:
            continue
        seen.add(linked)
        links.append({"url": linked, "text": anchor.get_text(" ", strip=True)})
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    body = soup.find("article") or soup.find("main") or soup.body or soup
    text = body.get_text("\n", strip=True)
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return {"text": text, "links": links, "published_at": published_at}


def _public_url(url):
    """Reject local targets before every request, including redirect targets."""
    parts = urlsplit(url)
    if (parts.scheme not in ("http", "https") or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.hostname.rstrip(".").lower() == "localhost"
            or parts.hostname.rstrip(".").lower().endswith(".localhost")):
        raise ValueError("Only public HTTP(S) page URLs are allowed")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in (80, 443):
        raise ValueError("Only standard web ports are allowed")
    addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError("Page URL resolves to a non-public address")


def parse(url, timeout=25):
    """Fetch at most 4 MiB of HTML; follow at most three checked redirects."""
    if isinstance(timeout, bool) or not isinstance(timeout, (float, int)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Page timeout must be a positive finite number")
    import requests
    started = time.monotonic()
    for hop in range(4):
        _public_url(url)
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("Page fetch exceeded its time budget")
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
                                timeout=(min(10, remaining), remaining), stream=True, allow_redirects=False)
        try:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location or hop == 3:
                    raise ValueError("Page redirect limit or invalid redirect")
                url = urljoin(url, location)
                continue
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type not in ("text/html", "application/xhtml+xml"):
                raise ValueError("Page reader only accepts HTML")
            try:
                declared = int(response.headers.get("Content-Length", "0"))
            except ValueError:
                declared = 0
            if declared > MAX_BYTES:
                raise ValueError("Page exceeds 4 MiB limit")
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=65536):
                if time.monotonic() - started > timeout:
                    raise TimeoutError("Page fetch exceeded its time budget")
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("Page exceeds 4 MiB limit")
                chunks.append(chunk)
            # Let BeautifulSoup inspect the byte encoding declaration.
            return parse_html(b"".join(chunks), url)
        finally:
            response.close()
    raise ValueError("Page redirect limit")
