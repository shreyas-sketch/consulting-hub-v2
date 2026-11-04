"""Industry Insight Pack: news links only from search results, audio made once per pack, gates and refunds."""
from conftest import qa_login

import llm
from audio import tts
from features import insights
from research import search

PACK = {"headline": "Costs up, owners cautious",
        "trends": [{"trend": f"Trend {i}", "why_it_matters": "Because."} for i in range(3)],
        "opportunities": ["Op 1", "Op 2", "Op 3"], "talking_points": [f"Point {i}" for i in range(5)],
        "questions_to_ask_clients": ["Q1?", "Q2?", "Q3?"]}


def used(c, meter):
    return c.get("/api/me/plan").json()["limits"][meter]["used"]


def test_pack_happy_path_and_listen(seeded_client):
    c = seeded_client
    qa_login(c, plan="l1")
    r = c.post("/api/insights", json={"industry": "FMCG"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["industry"] == "FMCG" and p["headline"]
    assert len(p["trends"]) == 3 and len(p["opportunities"]) == 3 and len(p["talking_points"]) == 5
    assert len(p["questions_to_ask_clients"]) == 3 and p["test"] and p["live_news"]
    assert p["news"] and all(n["url"].startswith("https://example.com/test-mode/") for n in p["news"])
    assert p["audio_url"] is None and used(c, "insight") == 1
    items = c.get("/api/insights").json()["items"]
    assert items[0]["id"] == p["id"] and not items[0]["has_audio"]

    a = c.post(f"/api/insights/{p['id']}/audio")
    assert a.status_code == 200, a.text
    assert a.json()["cached"] is False and used(c, "audio") == 1
    assert c.get(a.json()["audio_url"]).status_code == 200
    again = c.post(f"/api/insights/{p['id']}/audio").json()
    assert again["cached"] is True and again["audio_url"] == a.json()["audio_url"] and used(c, "audio") == 1
    assert c.get(f"/api/insights/{p['id']}").json()["audio_url"] == a.json()["audio_url"]
    assert "Three trends" in insights.spoken(c.get(f"/api/insights/{p['id']}").json())


def test_links_only_from_search_results(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")
    seen = []

    async def fake_news(query, max_results=6, **kw):
        seen.append(query)
        return [{"title": f"Real story {query[:10]}", "url": f"https://news.example.org/{len(seen)}", "source": "news.example.org",
                 "published": "1 day ago", "snippet": "…", "test": False}]

    async def picky(**kw):
        return {**PACK, "news": [{"i": 1, "why": "first"}, {"i": 99, "why": "made up"}, {"i": 0}, {"i": "x"},
                                 {"i": 1, "why": "duplicate"}, {"i": 2, "url": "https://invented.example.com/story"}]}
    monkeypatch.setattr(search, "news", fake_news)
    monkeypatch.setattr(llm, "complete_json", picky)
    r = c.post("/api/insights", json={"industry": "Pharma"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert 2 <= len(seen) <= 3
    assert [n["url"] for n in p["news"]] == ["https://news.example.org/1", "https://news.example.org/2"]
    assert "invented.example.com" not in r.text and not p["test"]


def test_pack_without_search_and_without_industry(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")

    async def nothing(query, max_results=6, **kw):
        return []
    monkeypatch.setattr(search, "news", nothing)
    r = c.post("/api/insights", json={})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "no_industry"
    p = c.post("/api/insights", json={"industry": "Textiles"}).json()
    assert p["news"] == [] and p["live_news"] is False


def test_pack_locked_and_limit(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    r = c.post("/api/insights", json={"industry": "FMCG"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    qa_login(c, plan="l1")
    for _ in range(2):
        assert c.post("/api/insights", json={"industry": "FMCG"}).status_code == 200
    r = c.post("/api/insights", json={"industry": "FMCG"})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_failures_refund(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")
    p = c.post("/api/insights", json={"industry": "FMCG"}).json()

    async def mute(text, **kw):
        raise tts.TTSError("down")
    monkeypatch.setattr(tts, "speak", mute)
    r = c.post(f"/api/insights/{p['id']}/audio")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "audio_failed"
    assert used(c, "audio") == 0

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    assert c.post("/api/insights", json={"industry": "FMCG"}).status_code == 503
    assert used(c, "insight") == 1

    async def thin(**kw):
        return {**PACK, "talking_points": ["only one"]}
    monkeypatch.setattr(llm, "complete_json", thin)
    assert c.post("/api/insights", json={"industry": "FMCG"}).status_code == 503
    assert used(c, "insight") == 1
