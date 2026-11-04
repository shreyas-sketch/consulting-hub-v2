"""Proposal Follow-through: proposal Markdown with the six framework stages and three ₹ options near the fee range,
follow-ups on day 2, 5 and 10, status flow, and the daily reminder job. L2 only."""
from datetime import timedelta

from conftest import qa_login, run

import llm
from features import proposals
from growth.clock import IST, ist_month_key, utcnow
from jobs.registry import JOBS, Ctx

BODY = {"company": "Desai Pumps", "person": "Rahul Desai", "role": "MD", "fee_low_inr": 150000, "fee_high_inr": 400000,
        "notes": "Sales flat for two years at ₹40 crore. Dealers in Gujarat complain about delivery times. Rahul wants "
                 "a plan before the new financial year."}


def l2(c):
    return qa_login(c, plan="l2")["user"]["id"]


def used(c):
    return c.get("/api/me/plan").json()["limits"]["proposal"]["used"]


def test_proposal_markdown_stages_and_options(client):
    l2(client)
    r = client.post("/api/proposals", json=BODY)
    assert r.status_code == 200, r.text
    p = r.json()
    md = p["markdown"]
    order = [md.index(s) for s in ("Scope Note", "Objective Statement", "Diagnostic Report", "Options Paper",
                                   "Prioritisation & Recommendation", "Implementation Charter")]
    assert order == sorted(order)
    for h in ("## Context", "## Objective", "## Approach", "## Deliverables", "## Timeline", "## Investment", "## Next steps"):
        assert h in md
    prices = [o["price_inr"] for o in p["data"]["options"]]
    assert len(prices) == 3 and prices == sorted(prices) and all(75000 <= x <= 600000 for x in prices)
    assert "₹1,50,000" in md and "₹4,00,000" in md
    assert [f["day"] for f in p["followups"]] == [2, 5, 10] and p["status"] == "draft" and p["next"] is None
    assert used(client) == 1
    assert client.get("/api/proposals").json()["items"][0]["top_option_inr"] == 400000


def test_prices_clamped_and_fee_range_swapped(client, monkeypatch):
    l2(client)
    real = llm.complete_json

    async def wild(**kw):
        out = await real(**kw)
        out["options"] = [{"name": "Huge", "price_inr": 99_00_00_000, "includes": "x"},
                          {"name": "Tiny", "price_inr": 10, "includes": "y"}, {"name": "Mid", "price_inr": "2,50,000", "includes": "z"}]
        return out
    monkeypatch.setattr(llm, "complete_json", wild)
    p = client.post("/api/proposals", json={**BODY, "fee_low_inr": 400000, "fee_high_inr": 150000}).json()
    assert [o["price_inr"] for o in p["data"]["options"]] == [75000, 275000, 600000]
    assert p["input"]["fee_low_inr"] == 150000


def test_status_flow_and_daily_reminders(client, mdb):
    uid = l2(client)
    p = client.post("/api/proposals", json=BODY).json()
    s = client.patch(f"/api/proposals/{p['id']}", json={"status": "sent"}).json()
    today = utcnow().astimezone(IST).date()
    assert [f["due"] for f in s["followups"]] == [(today + timedelta(days=d)).isoformat() for d in (2, 5, 10)]
    assert s["next"]["n"] == 1 and s["next"]["is_due"] is False and s["sent_at"]
    e = client.patch(f"/api/proposals/{p['id']}", json={"followup": {"n": 1, "text": "Hi Rahul, did it reach you?"}}).json()
    assert e["followups"][0]["text"] == "Hi Rahul, did it reach you?"

    assert "proposal_followups" in JOBS and JOBS["proposal_followups"][1] == ("daily", 9, 30)
    assert run(proposals.job_followups(Ctx(mdb, utcnow())))["alerts"] == 0                 # nothing due yet
    day2 = utcnow() + timedelta(days=2)
    assert run(proposals.job_followups(Ctx(mdb, day2)))["alerts"] == 1
    assert run(proposals.job_followups(Ctx(mdb, day2)))["alerts"] == 0                     # deduped
    rows = run(mdb.inbox.find({"user_id": uid, "kind": "proposal"}).to_list(10))
    assert len(rows) == 1 and rows[0]["link"] == f"/app/proposals/{p['id']}" and "Rahul Desai" in rows[0]["title"]

    f1 = client.patch(f"/api/proposals/{p['id']}", json={"status": "fu1"}).json()
    assert f1["followups"][0]["done"] and not f1["followups"][1]["done"] and f1["next"]["n"] == 2
    assert run(proposals.job_followups(Ctx(mdb, utcnow() + timedelta(days=5))))["alerts"] == 1
    w = client.patch(f"/api/proposals/{p['id']}", json={"status": "won"}).json()
    assert w["status"] == "won" and w["next"] is None and [h["status"] for h in w["history"]] == ["draft", "sent", "fu1", "won"]
    assert run(proposals.job_followups(Ctx(mdb, utcnow() + timedelta(days=10))))["alerts"] == 0
    assert client.get("/api/proposals").json()["counts"]["won"] == 1
    md = client.patch(f"/api/proposals/{p['id']}", json={"markdown": "# My own proposal\n\nEdited by hand."}).json()
    assert md["markdown"].startswith("# My own proposal")


def test_l1_locked_limit_and_refund(client, mdb, monkeypatch):
    uid = l2(client)

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    assert client.post("/api/proposals", json=BODY).status_code == 503 and used(client) == 0
    run(mdb.usage.update_one({"_id": f"{uid}:{ist_month_key()}"}, {"$set": {"proposal": 20, "user_id": uid}}, upsert=True))
    r = client.post("/api/proposals", json=BODY)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"
    client.post("/api/auth/logout")
    qa_login(client, plan="l1")
    r = client.post("/api/proposals", json=BODY)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    assert client.get("/api/proposals").status_code == 403
