"""Web search for Meeting Briefs (and, in stage 2, the weekly case from real news).

    await news(query, max_results=6) -> [{title, url, source, published, snippet, test}]

Vendor: Tavily (SEARCH_PROVIDER=tavily, SEARCH_API_KEY). Docs: docs.tavily.com — POST /search with a Bearer key.
Fake mode returns clearly marked sample results (test=True) so QA never shows a made-up link as real.
Off mode returns [] and the brief says it was made without live news.

    await extract(urls) -> [{url, title, text, test}]       (Research Notebook: readable text of web pages)

Tavily Extract (docs.tavily.com/api-reference/endpoint/extract): POST /extract with the same Bearer key,
{urls: [1-20], extract_depth: basic, format: markdown}; the reply has results[{url, raw_content}] and
failed_results[{url, error}] (both can be filled on a 200). Pages that could not be read are left out.
Fake mode returns a clearly marked sample text per URL (test=True). Off mode returns []; callers check mode() first.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional
from urllib.parse import urlparse

import httpx

from core.vendors import vendor_mode

log = logging.getLogger("search")
TAVILY = "https://api.tavily.com/search"
TAVILY_EXTRACT = "https://api.tavily.com/extract"
EXTRACT_MAX_CHARS = 400_000


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


def fake_extract(url: str) -> dict:
    host = _source(url) or "the page"
    body = (f"Test mode sample text for {host}. This is not the real page; in live mode the page's own words appear here. "
            "The company grew revenue by 18% in 2024 and opened 12 new stores in western India. "
            "Its leaders say rising costs and staff hiring are the two biggest risks for the next year. "
            "In March 2025 the board agreed to focus on smaller cities and on online orders. "
            "Customers said delivery speed and fair prices matter most to them.")
    return {"url": url, "title": f"Sample page from {host} (test mode)", "text": body, "test": True}


_MD_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def _readable(md: str) -> tuple[str, str]:
    """Markdown from Extract → (title from the first heading or line, plain text)."""
    md = _MD_IMG.sub(" ", md or "")
    md = _MD_LINK.sub(r"\1", md)
    title = ""
    for line in md.splitlines():
        s = line.strip().lstrip("#").strip()
        if len(s.split()) >= 2:
            title = s
            break
    body = re.sub(r"(^|\s)#{1,6}\s+|[*_`>|]{1,3}", " ", md)
    return " ".join(title.split())[:160], " ".join(body.split())[:EXTRACT_MAX_CHARS]


async def extract(urls: list[str], *, client: Optional[httpx.AsyncClient] = None) -> list[dict]:
    urls = [u.strip() for u in urls if str(u or "").strip().startswith(("https://", "http://"))][:20]
    m = mode()
    if m == "fake":
        return [fake_extract(u) for u in urls]
    if m == "off" or not urls:
        return []
    provider = (os.environ.get("SEARCH_PROVIDER") or "tavily").lower()
    if provider != "tavily":
        log.warning("unknown SEARCH_PROVIDER %s", provider)
        return []
    body = {"urls": urls, "extract_depth": "basic", "format": "markdown", "include_images": False}
    c = client or httpx.AsyncClient(timeout=40)
    try:
        r = await c.post(TAVILY_EXTRACT, json=body, headers={"Authorization": f"Bearer {os.environ['SEARCH_API_KEY']}"})
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:  # noqa: BLE001 — the caller explains that the page couldn't be read
        log.warning("extract failed: %s", e)
        return []
    finally:
        if client is None:
            await c.aclose()
    for f in data.get("failed_results") or []:
        log.info("extract: could not read %s: %s", str(f.get("url"))[:200], str(f.get("error"))[:200])
    out = []
    for x in data.get("results") or []:
        url = str(x.get("url") or "")
        title, text = _readable(str(x.get("raw_content") or ""))
        if not url.startswith(("https://", "http://")) or len(text.split()) < 20:
            continue
        out.append({"url": url[:500], "title": title or _source(url), "text": text, "test": False})
    return out
