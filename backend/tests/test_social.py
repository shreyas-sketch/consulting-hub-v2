"""Social Media Builder: 1-10 posts a run on posting days, pillars and formats, Career Story Bank used when present
(read defensively), calendar listing, edit / mark posted. Metered per post. L2 only."""
from datetime import date, timedelta

from conftest import qa_login, run

import llm
from features import social
from growth.clock import IST, ist_month_key, utcnow


def l2(c):
    return qa_login(c, plan="l2")["user"]["id"]


def used(c):
    return c.get("/api/me/plan").json()["limits"]["posts"]["used"]


def next_monday() -> date:
    t = utcnow().astimezone(IST).date()
    return t + timedelta(days=(7 - t.weekday()) % 7 or 7)


def test_generate_schedule_edit_and_post(client):
    l2(client)
    mon = next_monday()
    r = client.post("/api/social/generate", json={"count": 4, "pillars": ["expertise", "opinion"], "formats": ["insight", "myth_fact"],
                                                  "per_week": 3, "start_date": mon.isoformat()})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [p["date"] for p in items] == [(mon + timedelta(days=d)).isoformat() for d in (0, 2, 4, 7)]
    assert [p["pillar"] for p in items] == ["expertise", "opinion", "expertise", "opinion"]
    assert [p["format"] for p in items] == ["insight", "myth_fact", "insight", "myth_fact"]
    assert all(len(p["text"]) >= 150 and p["hook"] and p["status"] == "draft" for p in items)
    assert used(client) == 4
    # a second run fills the next free posting days
    more = client.post("/api/social/generate", json={"count": 1, "per_week": 3, "start_date": mon.isoformat()}).json()["items"]
    assert more[0]["date"] == (mon + timedelta(days=9)).isoformat()
    cal = client.get(f"/api/social?month={mon.strftime('%Y-%m')}").json()
    assert {p["id"] for p in items if p["date"][:7] == mon.strftime("%Y-%m")} <= {p["id"] for p in cal["items"]}
    assert cal["upcoming"] == 5 and cal["formats"]["myth_fact"] == "Myth vs fact"
    pid = items[0]["id"]
    e = client.patch(f"/api/social/{pid}", json={"text": "A new first line.\n\nAnd a much better second paragraph."}).json()
    assert e["hook"] == "A new first line."
    e = client.patch(f"/api/social/{pid}", json={"date": (mon + timedelta(days=1)).isoformat(), "status": "posted"}).json()
    assert e["status"] == "posted" and e["posted_at"] and e["date"] == (mon + timedelta(days=1)).isoformat()
    assert client.patch(f"/api/social/{pid}", json={"date": "2026-02-31"}).status_code == 422
    assert client.delete(f"/api/social/{pid}").json()["ok"]


def test_uses_career_stories_and_survives_odd_story_docs(client, mdb):
    uid = l2(client)
    run(mdb.stories.insert_many([
        {"_id": "s1", "user_id": uid, "title": "The warehouse that ate our margin", "situation": "Stock losses of 4% a year.",
         "what_i_did": "Counted every bin for a month.", "result": "Losses fell to 1%.", "at": utcnow()},
        {"_id": "s2", "user_id": uid, "title": None, "situation": None},          # half-written story: ignored
        {"_id": "s3", "user_id": uid, "transcript": ["not", "the", "shape", "we", "know"]}]))
    items = client.post("/api/social/generate", json={"count": 2, "pillars": ["story"], "formats": ["story", "mini_case"]}).json()["items"]
    assert all(p["story_title"] == "The warehouse that ate our margin" for p in items)
    assert "Counted every bin" in items[0]["text"]
    assert client.get("/api/social").json()["stories"] == 1
    no = client.post("/api/social/generate", json={"count": 1, "formats": ["story"], "use_stories": False}).json()["items"]
    assert no[0]["story_title"] == "" and "[" in no[0]["text"]


def test_limit_and_partial_ai_answer(client, mdb, monkeypatch):
    uid = l2(client)
    run(mdb.usage.update_one({"_id": f"{uid}:{ist_month_key()}"}, {"$set": {"posts": 28, "user_id": uid}}, upsert=True))
    r = client.post("/api/social/generate", json={"count": 5})
    assert r.status_code == 402 and "2 posts left" in r.json()["detail"]["msg"]
    run(mdb.usage.update_one({"_id": f"{uid}:{ist_month_key()}"}, {"$set": {"posts": 20}}))

    async def half(**kw):
        body = "A line that stops the scroll.\n\n" + "Short paragraph with a real point. " * 8
        return {"posts": [{"n": 1, "text": body}, {"n": 3, "text": body}, {"n": 3, "text": body}, {"n": 77, "text": body},
                          {"n": 2, "text": "too short"}]}
    monkeypatch.setattr(llm, "complete_json", half)
    items = client.post("/api/social/generate", json={"count": 4}).json()["items"]
    assert len(items) == 2 and used(client) == 22                 # 4 reserved, 2 written, 2 given back


def test_refund_lock_and_bad_dates(client, monkeypatch):
    l2(client)
    assert client.post("/api/social/generate", json={"count": 2, "start_date": "2020-01-01"}).status_code == 422
    assert client.post("/api/social/generate", json={"count": 11}).status_code == 422

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = client.post("/api/social/generate", json={"count": 3})
    assert r.status_code == 503 and used(client) == 0
    client.post("/api/auth/logout")
    qa_login(client, plan="l1")
    r = client.post("/api/social/generate", json={"count": 1})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    assert client.get("/api/social").status_code == 403


def test_schedule_patterns():
    mon = date(2026, 11, 9)
    assert social.schedule(mon, 5, 5, set()) == [(mon + timedelta(days=d)).isoformat() for d in range(5)]
    assert social.schedule(mon, 3, 4, {mon.isoformat()}) == [(mon + timedelta(days=d)).isoformat() for d in (1, 3, 4)]
