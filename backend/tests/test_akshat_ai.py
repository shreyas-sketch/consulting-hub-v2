"""Akshat AI: answered from the knowledge base with sources, queued for the next group call, admin answer + alert."""
from conftest import qa_login, run

import llm
from features import kb
from growth.clock import ist_month_key

PRICING = ("Pricing your first consulting project. Akshat says: never price by the hour. Price the outcome. "
           "Start with a diagnostic engagement of four to six weeks, fee between one and two lakh rupees, "
           "then propose the implementation retainer. Discount only by reducing scope, never the fee for the same scope. "
           "Pricing conversations happen after the client agrees the problem is worth solving.")


def _seed_kb(mdb):
    run(kb.ingest(mdb, "Bootcamp Day 2 – Pricing", PRICING))
    kb.reset_kb_cache()


def test_answer_from_sessions_with_sources(seeded_client, mdb):
    c = seeded_client
    _seed_kb(mdb)
    qa_login(c, plan="l1")
    r = c.post("/api/akshat-ai/ask", json={"question": "How should I price my first consulting project?"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "answered" and out["question_id"] is None
    assert out["message"]["sources"] and all(s["title"] for s in out["message"]["sources"])
    assert "Bootcamp Day 2 – Pricing" in {s["title"] for s in out["message"]["sources"]}
    assert c.get("/api/me/plan").json()["limits"]["akshat_ai"]["used"] == 1
    # follow-up in the same thread
    r = c.post("/api/akshat-ai/ask", json={"question": "And what about discount on pricing?", "thread_id": out["thread_id"]}).json()
    assert r["thread_id"] == out["thread_id"]
    t = c.get(f"/api/akshat-ai/threads/{out['thread_id']}").json()
    assert len(t["messages"]) == 4 and t["title"].startswith("How should I price")
    assert [x["id"] for x in c.get("/api/akshat-ai/threads").json()["items"]] == [out["thread_id"]]


def test_not_covered_is_queued_and_admin_answer_alerts(seeded_client, mdb):
    c = seeded_client
    _seed_kb(mdb)
    me = qa_login(c, plan="l1")
    r = c.post("/api/akshat-ai/ask", json={"question": "Xylophone zebra quantum?"}).json()
    assert r["status"] == "queued" and r["question_id"] and "next group call" in r["message"]["text"]
    # the same question again: no duplicate in the queue
    again = c.post("/api/akshat-ai/ask", json={"question": "xylophone zebra quantum?", "thread_id": r["thread_id"]}).json()
    assert again["question_id"] == r["question_id"]
    mine = c.get("/api/akshat-ai/questions").json()["items"]
    assert len(mine) == 1 and mine[0]["status"] == "queued" and mine[0]["answer"] is None
    # the AI can also decide the excerpts don't cover it
    async def not_covered(**kw):
        return {"kind": "not_covered", "answer": "", "sources": []}
    orig = llm.complete_json
    llm.complete_json = not_covered
    try:
        r2 = c.post("/api/akshat-ai/ask", json={"question": "What fee for pricing a board advisory role?"}).json()
    finally:
        llm.complete_json = orig
    assert r2["status"] == "queued"

    assert c.get("/api/admin/akshat-questions").status_code == 403
    qa_login(c, role="admin")
    q = c.get("/api/admin/akshat-questions", params={"status": "queued"}).json()
    assert q["counts"] == {"queued": 2, "answered": 0}
    row = next(x for x in q["items"] if x["id"] == r["question_id"])
    assert row["name"] == "Demo Member" and row["phone"]
    a = c.post(f"/api/admin/akshat-questions/{r['question_id']}/answer", json={"answer": "We covered this on the call: start small."})
    assert a.status_code == 200, a.text
    assert a.json()["status"] == "answered"
    assert c.get("/api/admin/akshat-questions", params={"status": "answered"}).json()["counts"]["answered"] == 1
    inbox = run(mdb.inbox.find_one({"user_id": me["user"]["id"], "kind": "akshat_ai"}))
    assert inbox and inbox["link"] == f"/app/akshat-ai/{r['thread_id']}"
    # editing the answer doesn't send a second alert
    c.post(f"/api/admin/akshat-questions/{r['question_id']}/answer", json={"answer": "Edited: start with one client."})
    assert run(mdb.inbox.count_documents({"user_id": me["user"]["id"], "kind": "akshat_ai"})) == 1

    qa_login(c, plan="l1")
    mine = {x["id"]: x for x in c.get("/api/akshat-ai/questions").json()["items"]}
    assert mine[r["question_id"]]["status"] == "answered" and mine[r["question_id"]]["answer"].startswith("Edited")
    t = c.get(f"/api/akshat-ai/threads/{r['thread_id']}").json()
    assert t["messages"][-1]["from_call"] and t["messages"][-1]["text"].startswith("Edited")
    assert t["messages"][1]["question_status"] == "answered"


def test_declines_personal_financial_advice(seeded_client, mdb):
    c = seeded_client
    _seed_kb(mdb)
    qa_login(c, plan="l1")
    r = c.post("/api/akshat-ai/ask", json={"question": "Which mutual fund should I put my consulting fee in?"}).json()
    assert r["status"] == "declined" and "qualified professional" in r["message"]["text"]
    assert c.get("/api/akshat-ai/questions").json()["items"] == []


def test_locks_limit_and_refund(seeded_client, mdb, monkeypatch):
    c = seeded_client
    _seed_kb(mdb)
    qa_login(c, plan="member")
    r = c.post("/api/akshat-ai/ask", json={"question": "How do I price?"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    me = qa_login(c, plan="l1")

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = c.post("/api/akshat-ai/ask", json={"question": "How should I price my first project?"})
    assert r.status_code == 503 and c.get("/api/me/plan").json()["limits"]["akshat_ai"]["used"] == 0
    assert c.get("/api/akshat-ai/threads").json()["items"] == []
    run(mdb.usage.update_one({"_id": f"{me['user']['id']}:{ist_month_key()}"}, {"$set": {"akshat_ai": 30}}, upsert=True))
    r = c.post("/api/akshat-ai/ask", json={"question": "How should I price my first project?"})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"
    assert c.get("/api/akshat-ai/threads/nope").status_code == 404
