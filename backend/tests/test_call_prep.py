"""Discovery Call Prep: agenda, opening, questions mapped to the six steps, problems, objections, what not to say,
next step; optional news with links only from search. Metered per prep. L2 only."""
from conftest import qa_login, run

import llm
from growth.clock import ist_month_key

BODY = {"company": "Desai Pumps", "person": "Rahul Desai", "role": "Managing Director", "how_met": "Ex-colleague",
        "known": "Sales flat for two years; opened a Gujarat plant.", "search": True}


def l2(c):
    return qa_login(c, plan="l2")["user"]["id"]


def used(c):
    return c.get("/api/me/plan").json()["limits"]["call_prep"]["used"]


def test_prep_with_news(client):
    l2(client)
    r = client.post("/api/call-prep", json=BODY)
    assert r.status_code == 200, r.text
    p = r.json()
    assert len(p["agenda"]) >= 3 and p["opening"] and p["next_step"]
    steps = [q["step"] for q in p["questions"]]
    assert len(p["questions"]) >= 6 and set(steps) == {1, 2, 3, 4, 5, 6} and steps == sorted(steps)
    assert len(p["problems"]) == 3 and len(p["objections"]) == 3 and all(o["answer"] for o in p["objections"]) and p["avoid"]
    assert p["live_news"] and p["test"] and all(n["url"].startswith("https://example.com/test-mode/") for n in p["news"])
    assert p["steps"]["1"] == "Understand Scope"
    assert used(client) == 1
    assert client.get("/api/call-prep").json()["items"][0]["company"] == "Desai Pumps"
    assert client.get(f"/api/call-prep/{p['id']}").json()["opening"] == p["opening"]


def test_prep_without_news_and_made_up_news_numbers(client, monkeypatch):
    l2(client)
    p = client.post("/api/call-prep", json={**BODY, "search": False}).json()
    assert p["news"] == [] and p["live_news"] is False
    real = llm.complete_json

    async def liar(**kw):
        out = await real(**kw)
        out["news"] = [{"i": 7, "why": "x"}, {"i": 0, "why": "y"}, {"i": 1, "why": "ok"}]
        return out
    monkeypatch.setattr(llm, "complete_json", liar)
    p = client.post("/api/call-prep", json=BODY).json()
    assert [n["why"] for n in p["news"]] == ["ok"]


def test_l1_locked_and_limit(client, mdb):
    uid = l2(client)
    run(mdb.usage.update_one({"_id": f"{uid}:{ist_month_key()}"}, {"$set": {"call_prep": 20, "user_id": uid}}, upsert=True))
    r = client.post("/api/call-prep", json=BODY)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"
    client.post("/api/auth/logout")
    qa_login(client, plan="l1")
    r = client.post("/api/call-prep", json=BODY)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"


def test_ai_failure_refunds(client, monkeypatch):
    l2(client)

    async def thin(**kw):
        return {"agenda": [], "questions": [], "opening": ""}
    monkeypatch.setattr(llm, "complete_json", thin)
    r = client.post("/api/call-prep", json=BODY)
    assert r.status_code == 503 and used(client) == 0
