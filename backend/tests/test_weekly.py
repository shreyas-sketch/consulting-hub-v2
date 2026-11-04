"""Weekly case from real news: job, strict checks, alerts, admin endpoints."""
from datetime import datetime, timezone

from conftest import qa_login, run

import llm


def _member(c, phone=None, plan="member"):
    return qa_login(c, plan=plan, **({"phone": phone} if phone else {}))["user"]["id"]


def _admin(c):
    c.post("/api/auth/logout")
    qa_login(c, role="admin")


def test_job_publishes_case_with_search_link_and_alerts_paid_members(seeded_client, mdb):
    c = seeded_client
    member = _member(c, plan="member")
    c.post("/api/auth/logout")
    free = _member(c, plan="free")
    _admin(c)
    r = c.post("/api/admin/jobs/weekly_case/run").json()
    assert r["ok"] and r["result"]["published"] and r["result"]["test"] is True
    cid = r["result"]["published"]
    doc = run(mdb.cases.find_one({"_id": cid}))
    assert doc["kind"] == "weekly" and doc["origin"] == "news" and doc["active"] and doc["week"].count("-W") == 1
    assert doc["source"]["url"].startswith("https://example.com/test-mode/") and set(doc["source"]) == {"title", "url"}
    m = doc["model_answer"]
    assert [o["source"] for o in m["options"]] == ["Same industry", "Adjacent industry", "Similar geography",
                                                    "Customer research", "Out of the box"]
    assert m["objective"]["from"] and m["charter"]["leading"] and len(doc["facts"]) >= 3
    # one alert per paid member (admin counts as l2), none for free accounts
    assert run(mdb.inbox.count_documents({"user_id": member, "kind": "weekly_case"})) == 1
    assert run(mdb.inbox.count_documents({"user_id": free})) == 0
    # a second run in the same week does nothing
    again = c.post("/api/admin/jobs/weekly_case/run").json()["result"]
    assert again["skipped"] == "already_published"
    c.post("/api/auth/logout")
    qa_login(c, plan="member")
    items = c.get("/api/cases").json()["items"]
    first = next(i for i in items if not i["live"])
    assert first["id"] == cid and first["kind"] == "weekly" and first["source"]["url"].startswith("https://example.com/")
    one = c.get(f"/api/cases/{cid}").json()["case"]
    assert one["model_answer"] is None and one["question"]


def test_bad_ai_output_is_not_published(seeded_client, mdb, monkeypatch):
    c = seeded_client
    _admin(c)
    real = llm.complete_json
    bad = [
        lambda o: o.update(pick=99),                                          # story number that wasn't found
        lambda o: o.update(company="Imaginary Holdings"),                     # company not in the story
        lambda o: o["model_answer"].update(options=o["model_answer"]["options"][:3]),   # missing option sources
        lambda o: o.update(facts=["one"]),
        lambda o: o["model_answer"]["charter"].update(owner=""),
    ]
    for spoil in bad:
        async def liar(**kw):
            out = await real(**kw)
            spoil(out)
            return out
        monkeypatch.setattr(llm, "complete_json", liar)
        r = c.post("/api/admin/weekly/generate")
        assert r.status_code == 503 and r.json()["detail"]["code"] == "bad_ai_output"

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    assert c.post("/api/admin/weekly/generate").status_code == 503
    assert run(mdb.cases.count_documents({"origin": "news"})) == 0


def test_link_comes_from_search_not_ai(seeded_client, mdb, monkeypatch):
    c = seeded_client
    _admin(c)
    real = llm.complete_json

    async def liar(**kw):
        out = await real(**kw)
        out["source"] = {"title": "made up", "url": "https://made-up.example/news"}
        out["pick"] = 2
        out["company"] = out["company"]
        return out
    monkeypatch.setattr(llm, "complete_json", liar)
    r = c.post("/api/admin/weekly/generate").json()
    doc = run(mdb.cases.find_one({"_id": r["item"]["id"]}))
    assert doc["source"]["url"] == "https://example.com/test-mode/2"


def test_admin_list_generate_toggle_and_older_weeks_become_practice(seeded_client, mdb):
    c = seeded_client
    run(mdb.cases.insert_one({"_id": "old-weekly", "title": "Old", "company": "Old Co", "industry": "Retail", "city": "Pune",
                              "situation": "x", "facts": [], "question": "q", "model_answer": {}, "kind": "weekly",
                              "week": "2020-W01", "origin": "news", "active": True,
                              "created_at": datetime(2020, 1, 1, tzinfo=timezone.utc)}))
    _member(c)
    assert c.get("/api/admin/weekly").status_code == 403
    assert c.post("/api/admin/weekly/generate").status_code == 403
    _admin(c)
    g = c.post("/api/admin/weekly/generate").json()
    assert g["item"]["current"] and g["item"]["test"] and g["item"]["answers"] == 0
    assert run(mdb.cases.find_one({"_id": "old-weekly"}))["kind"] == "practice"
    lst = c.get("/api/admin/weekly").json()
    assert [i["id"] for i in lst["items"]] == [g["item"]["id"], "old-weekly"] and lst["schedule"] == "Mon 06:30 IST"
    off = c.post(f"/api/admin/weekly/{g['item']['id']}/active", json={"active": False}).json()
    assert off["item"]["active"] is False
    assert c.post("/api/admin/weekly/old-weekly/active", json={"active": False}).status_code == 200
    assert c.post("/api/admin/weekly/retail-chain-margins/active", json={"active": False}).status_code == 404
    c.post("/api/auth/logout")
    qa_login(c, plan="member")
    ids = {i["id"] for i in c.get("/api/cases").json()["items"]}
    assert g["item"]["id"] not in ids and "old-weekly" not in ids


def test_job_skips_when_search_finds_nothing(seeded_client, mdb, monkeypatch):
    from research import search

    async def empty(q, max_results=6, **kw):
        return []
    monkeypatch.setattr(search, "news", empty)
    from features.weekly import job_weekly_case
    from jobs.registry import Ctx
    from growth.clock import utcnow
    assert run(job_weekly_case(Ctx(mdb, utcnow())))["skipped"] == "no_news"
    assert run(mdb.cases.count_documents({"origin": "news"})) == 0


def test_week_key_is_ist():
    from features.weekly import week_key
    # Sunday 20:00 UTC = Monday 01:30 IST → already the next ISO week in India
    assert week_key(datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc)) == "2026-W46"
    assert week_key(datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)) == "2026-W45"
