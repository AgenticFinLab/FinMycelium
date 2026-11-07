"""Bounded provider calls with native publication-date filters.

Provider references (the legacy wrappers do not expose these parameters):
https://github.com/bocha-ai/dsh-web-search-bocha/blob/main/README.md
https://ai.baidu.com/ai-doc/AppBuilder/pmaxd1hvy
"""
import datetime as dt
import math
import os


def search(provider, query, count, start, end, timeout=25):
    """Return search metadata; snippets are discovery hints, not source evidence.

    Never retry without the requested date filters. Callers still validate the
    returned publication metadata before fetching pages, since engines can
    return noisy dates even with native filters.
    """
    if provider not in ("bocha", "baidu"):
        raise ValueError("Search provider must be bocha or baidu")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query must be nonempty")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 50:
        raise ValueError("Search count must be an integer from 1 through 50")
    try:
        first, last = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    except (TypeError, ValueError):
        raise ValueError("Publication bounds must be YYYY-MM-DD") from None
    if first.isoformat() != start or last.isoformat() != end or first > last:
        raise ValueError("Publication bounds must be ordered YYYY-MM-DD dates")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Search timeout must be a positive finite number")

    # Keep this module importable in offline tooling without runtime packages.
    import requests
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv()

    key_name = "BOCHA_API_KEY" if provider == "bocha" else "BAIDUSEARCH_API_KEY"
    key = os.getenv(key_name, "").strip()
    if not key:
        raise ValueError(f"Missing {key_name}")
    if provider == "bocha":
        url = "https://api.bocha.cn/v1/web-search"
        payload = {"query": query, "summary": False, "count": count,
                   "freshness": f"{start}..{end}"}
    else:
        url = "https://qianfan.baidubce.com/v2/ai_search/web_search"
        payload = {
            "messages": [{"role": "user", "content": query}],
            "edition": "standard", "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": count}],
            "search_filter": {"range": {"page_time": {"gte": start, "lte": end}}},
        }
    response = requests.post(
        url, json=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        timeout=(min(10, timeout), timeout),
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"Invalid {provider} search response")
    if data.get("code") not in (None, 0, "0", 200, "200"):
        # Do not reflect provider text that might contain request credentials.
        raise ValueError(f"{provider} search returned a provider error")
    if provider == "bocha":
        try:
            rows = data["data"]["webPages"]["value"]
        except (KeyError, TypeError):
            raise ValueError("Invalid bocha search response: missing webPages") from None
    else:
        rows = data.get("references")
    if not isinstance(rows, list):
        raise ValueError(f"Invalid {provider} search response: missing results")

    output = []
    for row in rows[:count]:
        if not isinstance(row, dict):
            continue
        url = row.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        title = row.get("name" if provider == "bocha" else "title", "")
        date = row.get("datePublished" if provider == "bocha" else "date")
        snippet = row.get("snippet") or row.get("content") or ""
        output.append({"title": title if isinstance(title, str) else "",
                       "url": url.strip(),
                       "published_at": date if isinstance(date, str) else None,
                       "snippet": snippet if isinstance(snippet, str) else ""})
    return output
