"""Progress Report: numbers from the data, AI words only, one a month, and the day-1 nudge."""
from datetime import datetime, timedelta, timezone

from conftest import qa_login, run

import llm
from growth.clock import utcnow

SKILLS = ("diagnosis", "offer", "acquisition", "pricing", "delivery", "visibility")
ANSWER = ("The real problem is margin leakage because discounts and wastage grew with the new stores. In grocery this "
          "is common. First split profit by store, then cut slow products, then fix fresh ordering. Measure wastage % weekly.")


def _used(c):
    return c.get("/api/me/plan").json()["limits"]["progress"]["used"]


def _activity(c, mdb, uid):
    old = utcnow() - timedelta(days=40)
    run(mdb.readiness.insert_one({"_id": "old-r", "user_id": uid, "scores": {k: 4 for k in SKILLS}, "potential": 8,
                                  "total": 24, "band": "Starting out", "at": old}))
    run(mdb.linkedin_checks.insert_one({"_id": "old-li", "user_id": uid, "score": 40, "parts": [], "problems": [],
                                        "input": {}, "at": old}))
    run(mdb.case_answers.insert_one({"_id": "old-a", "user_id": uid, "case_id": "it-attrition", "answer": "x",
                                     "scores": {}, "overall": 4.0, "at": old}))
    c.post("/api/readiness", json={"scores": dict(zip(SKILLS, [8, 3, 5, 6, 7, 9])), "potential": 9})
    for cid in ("retail-chain-margins", "hospital-claims"):
        assert c.post(f"/api/cases/{cid}/answer", json={"answer": ANSWER}).status_code == 200
    c.post("/api/briefs", json={"company": "Zydus"})
    c.post("/api/linkedin/check", json={"headline": "I help family-run manufacturers grow profit | Operations consultant"})
    c.put("/api/start/goal", json={"monthly_goal_inr": 300000, "fee_inr": 75000})
    c.post("/api/visuals", json={"kind": "process", "prompt": "My five-step diagnosis process"})


def test_report_numbers_come_from_data(seeded_client, mdb):
    c = seeded_client
    uid = qa_login(c, plan="member")["user"]["id"]
    _activity(c, mdb, uid)
    r = c.post("/api/progress")
    assert r.status_code == 200, r.text
    p = r.json()
    s = p["stats"]
    assert s["readiness"]["now"] == 38 and s["readiness"]["last"] == 24 and s["readiness"]["change"] == 14
    assert s["readiness"]["weakest"] == "Offer clarity"
    assert s["cases"]["solved"] == 2 and s["cases"]["prev_solved"] == 1 and s["cases"]["prev_avg"] == 4.0
    assert s["cases"]["avg_change"] == round(s["cases"]["avg"] - 4.0, 1)
    assert s["briefs"] == {"made": 1, "prev": 0}
    assert s["linkedin"]["before"] == 40 and s["linkedin"]["change"] == s["linkedin"]["now"] - 40
    assert s["made"]["visuals"] == 1 and s["made"]["decks"] == 0
    assert {t["label"] for t in s["tools"]} >= {"Cases", "Meeting Brief", "LinkedIn Score", "Readiness Score", "Visual Builder"}
    assert next(t for t in s["tools"] if t["key"] == "case_answered")["uses"] == 2
    assert s["goal"]["clients_per_month"] == 4 and "not a promise" in s["goal"]["label"]
    assert p["summary"] and len(p["focus"]) == 3 and all(f["title"] for f in p["focus"])
    # one a month
    assert c.post("/api/progress").status_code == 402
    lst = c.get("/api/progress").json()
    assert lst["made_this_month"] and lst["items"][0]["id"] == p["id"] and lst["items"][0]["readiness"] == 38
    assert c.get(f"/api/progress/{p['id']}").json()["stats"]["cases"]["solved"] == 2


def test_ai_numbers_that_are_not_in_the_data_are_dropped(seeded_client, mdb, monkeypatch):
    async def liar(**kw):
        return {"summary": "You solved 17 cases this month. You kept going, which matters most.",
                "focus": [{"title": "Solve 9 cases a week", "why": "More practice."},
                          {"title": "Talk to two owners a week", "why": "Conversations bring clients."},
                          {"title": "Post on LinkedIn every week", "why": "Owners need to see you."}]}
    monkeypatch.setattr(llm, "complete_json", liar)
    c = seeded_client
    qa_login(c, plan="member")
    p = c.post("/api/progress").json()
    assert "17" not in p["summary"] and "You kept going" in p["summary"]
    titles = [f["title"] for f in p["focus"]]
    assert len(titles) == 3 and "Solve 9 cases a week" not in titles and "Talk to two owners a week" in titles


def test_locked_and_refund(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="free")
    r = c.post("/api/progress")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    c.post("/api/auth/logout")
    qa_login(c, plan="member")

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = c.post("/api/progress")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy" and _used(c) == 0


def test_nudge_only_on_day_one_ist(seeded_client, mdb):
    from features.progress import job_progress_nudge
    from jobs.registry import Ctx
    c = seeded_client
    member = qa_login(c, plan="member")["user"]["id"]
    c.post("/api/auth/logout")
    free = qa_login(c, plan="free")["user"]["id"]
    day1 = datetime(2026, 11, 30, 19, 0, tzinfo=timezone.utc)          # 1 Dec, 00:30 IST
    assert run(job_progress_nudge(Ctx(mdb, day1 - timedelta(days=1))))["skipped"] == "not_day_1"
    res = run(job_progress_nudge(Ctx(mdb, day1)))
    assert res["month"] == "2026-12" and res["sent"] >= 1
    assert run(mdb.inbox.count_documents({"user_id": member, "kind": "progress"})) == 1
    assert run(mdb.inbox.count_documents({"user_id": free, "kind": "progress"})) == 0
    assert run(job_progress_nudge(Ctx(mdb, day1 + timedelta(hours=2))))["sent"] == 0      # deduped
