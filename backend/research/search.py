"""Web search for Meeting Briefs (and, in stage 2, the weekly case from real news).

    await news(query, max_results=6) -> [{title, url, source, published, snippet, test}]

Vendor: Tavily (SEARCH_PROVIDER=tavily, SEARCH_API_KEY). Docs: docs.tavily.com — POST /search with a Bearer key.
Fake mode returns clearly marked sample results (test=True) so QA never shows a made-up link as real.
Off mode returns [] and the brief says it was made without live news.
"""
from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlparse

import httpx

from core.vendors import vendor_mode

log = logging.getLogger("search")
TAVILY = "https://api.tavily.com/search"


def mode() -> str:
    return vendor_mode("search")


def _source(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def fake_results(query: str, n: int) -> list[dict]:
    base = query.strip() or "the company"
    items = [("announces expansion plans for next year", "2 days ago"),
             ("reports quarterly results; margins under pressure", "1 week ago"),
             ("hires new leadership for growth", "3 weeks ago"),
             ("faces rising costs and new competition", "1 month ago")]
    out = []
    for i, (what, when) in enumerate(items[:n]):
        out.append({"title": f"{base} {what}", "url": f"https://example.com/test-mode/{i + 1}",
                    "source": "example.com (test mode)", "published": when,
                    "snippet": f"Sample result for {base}, shown in test mode only.", "test": True})
    return out


async def news(query: str, max_results: int = 6, *, client: Optional[httpx.AsyncClient] = None) -> list[dict]:
    m = mode()
    if m == "fake":
        return fake_results(query, min(max_results, 4))
    if m == "off" or not query.strip():
        return []
    provider = (os.environ.get("SEARCH_PROVIDER") or "tavily").lower()
    if provider != "tavily":
        log.warning("unknown SEARCH_PROVIDER %s", provider)
        return []
    body = {"query": query[:300], "topic": "news", "days": 120, "max_results": max(1, min(10, max_results)),
            "include_answer": False, "search_depth": "basic"}
    c = client or httpx.AsyncClient(timeout=15)
    try:
        r = await c.post(TAVILY, json=body, headers={"Authorization": f"Bearer {os.environ['SEARCH_API_KEY']}"})
        r.raise_for_status()
        rows = (r.json() or {}).get("results") or []
    except Exception as e:  # noqa: BLE001 — a brief without news beats no brief
        log.warning("search failed: %s", e)
        return []
    finally:
        if client is None:
            await c.aclose()
    out = []
    for x in rows:
        url = str(x.get("url") or "")
        if not url.startswith(("https://", "http://")):
            continue
        out.append({"title": " ".join(str(x.get("title") or "").split())[:200], "url": url[:500],
                    "source": _source(url), "published": str(x.get("published_date") or "")[:40],
                    "snippet": " ".join(str(x.get("content") or "").split())[:600], "test": False})
    return out
