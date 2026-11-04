"""Opportunity Radar: news search → companies picked by result number (links only from search), deduped across
runs, metered per company found (reserve, then give back what wasn't found). L2 only."""
from conftest import qa_login, run

import llm
from growth.clock import ist_month_key
from research import search


def l2(c):
    return qa_login(c, plan="l2")["user"]["id"]


def used(c):
    return c.get("/api/me/plan").json()["limits"]["radar"]["used"]


def set_used(mdb, uid, n):
    run(mdb.usage.update_one({"_id": f"{uid}:{ist_month_key()}"}, {"$set": {"radar": n, "user_id": uid}}, upsert=True))


REAL = [{"title": "Zenith Pharma to build new plant in Pune", "url": "https://news.example.in/zenith-plant", "source": "news.example.in",
         "published": "2 days ago", "snippet": "Zenith Pharma Ltd will invest ₹200 crore in a new plant.", "test": False},
        {"title": "Orbit Labs names new CEO", "url": "https://news.example.in/orbit-ceo", "source": "news.example.in",
         "published": "1 week ago", "snippet": "Orbit Labs appointed a new chief executive.", "test": False}]


def test_run_counts_companies_found_and_dedupes(client):
    l2(client)
    r = client.post("/api/radar/run", json={"industry": "Pharma", "city": "Pune"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert 1 <= len(d["found"]) <= 5 and d["test"]
    assert all(c["news"]["url"].startswith("https://example.com/test-mode/") for c in d["found"])
    assert all(c["signal"] in ("expansion", "new_plant", "funding", "leadership", "losses", "layoffs", "new_rules", "other")
               for c in d["found"])
    n = len(d["found"])
    assert used(client) == n
    again = client.post("/api/radar/run", json={"industry": "Pharma", "city": "Pune"}).json()
    assert again["found"] == [] and used(client) == n                 # same companies: nothing new, nothing charged
    lst = client.get("/api/radar").json()
    assert len(lst["items"]) == n and lst["runs"][0]["found"] == 0
    cid = lst["items"][0]["id"]
    assert client.patch(f"/api/radar/{cid}", json={"status": "dismissed"}).json()["status"] == "dismissed"
    assert len(client.get("/api/radar").json()["items"]) == n - 1
    assert len(client.get("/api/radar?status=dismissed").json()["items"]) == 1


def test_links_only_from_search(client, monkeypatch):
    l2(client)

    async def news(q, max_results=6, **kw):
        return REAL

    async def liar(**kw):
        return {"companies": [
            {"i": 99, "company": "Ghost Corp", "signal": "funding", "why": "Made up.", "url": "https://evil.example/x"},
            {"i": 1, "company": "Imaginary Pharma Holdings", "signal": "expansion", "why": "Not in that result."},
            {"i": 1, "company": "Zenith Pharma", "signal": "new_plant", "summary": "New plant.", "why": "Plants need supply chains.",
             "angle": "Ask about hiring.", "url": "https://evil.example/y"},
            {"i": 1, "company": "Zenith Pharma Ltd", "signal": "expansion", "why": "Duplicate company."},
            {"i": "2", "company": "Orbit Labs", "signal": "made_up_signal", "why": "New CEO, new priorities."}]}
    monkeypatch.setattr(search, "news", news)
    monkeypatch.setattr(llm, "complete_json", liar)
    d = client.post("/api/radar/run", json={"industry": "Pharma"}).json()
    assert [c["company"] for c in d["found"]] == ["Zenith Pharma", "Orbit Labs"]
    assert [c["news"]["url"] for c in d["found"]] == [r["url"] for r in REAL]
    assert d["found"][1]["signal"] == "other" and not d["test"]
    assert used(client) == 2


def test_no_news_gives_everything_back(client, monkeypatch):
    l2(client)

    async def nothing(q, max_results=6, **kw):
        return []
    monkeypatch.setattr(search, "news", nothing)
    r = client.post("/api/radar/run", json={"industry": "Pharma"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_news" and used(client) == 0


def test_limit_and_partial(client, mdb):
    uid = l2(client)
    set_used(mdb, uid, 8)
    d = client.post("/api/radar/run", json={"industry": "Auto parts", "city": "Chennai"}).json()
    assert len(d["found"]) == 2 and used(client) == 10              # only what was left
    r = client.post("/api/radar/run", json={"industry": "Steel"})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_ai_failure_refunds(client, monkeypatch):
    l2(client)

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = client.post("/api/radar/run", json={"industry": "Pharma"})
    assert r.status_code == 503 and used(client) == 0


def test_needs_an_industry_and_l2(client):
    l2(client)
    assert client.post("/api/radar/run", json={}).json()["detail"]["code"] == "industry"   # no niche chosen yet
    client.post("/api/auth/logout")
    qa_login(client, plan="l1")
    r = client.post("/api/radar/run", json={"industry": "Pharma"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
