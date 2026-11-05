"""Webinar tools: Readiness Score, Starting Point, cases, Meeting Brief, LinkedIn Score, My Consulting File."""
from conftest import qa_login

import llm

SKILLS = ("diagnosis", "offer", "acquisition", "pricing", "delivery", "visibility")
ANSWER = ("The real problem is margin leakage because discounts and wastage grew with the new stores. In grocery this "
          "is common. First split profit by store, then cut slow products, then fix fresh ordering. Measure wastage % weekly.")


def test_readiness_score_bands_and_focus(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    scores = dict(zip(SKILLS, [8, 3, 2, 6, 7, 9]))
    r = c.post("/api/readiness", json={"scores": scores, "potential": 9}).json()
    assert r["total"] == 35 and r["band"] == "Building" and r["max"] == 60
    assert [f["key"] for f in r["focus"]] == ["acquisition", "offer"] and r["change"] is None
    assert c.get("/api/readiness").json()["latest"]["total"] == 35
    assert c.post("/api/readiness", json={"scores": scores, "potential": 9}).status_code == 402   # 1 a month


def test_readiness_clamps_values(seeded_client):
    c = seeded_client
    qa_login(c, plan="free")
    r = c.post("/api/readiness", json={"scores": {"diagnosis": 50, "offer": -3}, "potential": 5}).json()
    assert r["scores"]["diagnosis"] == 10 and r["scores"]["offer"] == 1 and r["total"] == 10 + 1 + 4


def test_snapshot_and_goal(seeded_client):
    c = seeded_client
    qa_login(c, plan="free")
    s = c.post("/api/start/snapshot", json={"experiences": ["Supply chain", "Team leadership", " "], "enjoy": [1, 9],
                                             "industry": "FMCG", "years": 18})
    assert s.status_code == 200, s.text
    s = s.json()
    assert len(s["options"]) == 3 and all(o["total"] == o["experience"] + o["demand"] + o["enjoyment"] for o in s["options"])
    assert s["options"][0]["total"] >= s["options"][-1]["total"] and s["input"]["enjoy"] == [1]
    assert c.post(f"/api/start/snapshot/{s['id']}/choose", json={"index": 2}).json()["chosen"] == 2
    g = c.put("/api/start/goal", json={"monthly_goal_inr": 300000, "fee_inr": 75000}).json()
    assert g["clients_per_month"] == 4 and g["discovery_calls_per_month"] == 16 and g["conversations_per_month"] == 48
    assert "not a promise" in g["label"]
    assert c.put("/api/start/goal", json={"monthly_goal_inr": 400000, "fee_inr": 75000}).status_code == 402   # free: once
    assert c.post("/api/start/goal/preview", json={"monthly_goal_inr": 400000, "fee_inr": 75000}).json()["clients_per_month"] == 6
    mine = c.get("/api/start").json()
    assert mine["snapshot"]["chosen"] == 2 and mine["goal"]["clients_per_month"] == 4


def test_ai_failure_refunds_the_go(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="free")

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = c.post("/api/start/snapshot", json={"experiences": ["Sales"]})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy"
    assert c.get("/api/me/plan").json()["limits"]["start"]["used"] == 0


def test_cases_free_sees_live_only(seeded_client):
    c = seeded_client
    qa_login(c, plan="free")
    items = c.get("/api/cases").json()["items"]
    assert len(items) == 8 and items[0]["live"] and items[0]["id"] == "retail-chain-margins" and not items[0]["locked"]
    assert all(i["locked"] for i in items[1:])
    assert c.get("/api/cases/d2c-skincare-cac").status_code == 403
    assert c.post("/api/cases/d2c-skincare-cac/answer", json={"answer": ANSWER}).status_code == 403
    one = c.get("/api/cases/retail-chain-margins").json()
    assert one["case"]["model_answer"] is None and one["case"]["live"]
    assert c.post("/api/cases/retail-chain-margins/answer", json={"answer": "too short"}).status_code == 422
    r = c.post("/api/cases/retail-chain-margins/answer", json={"answer": ANSWER}).json()
    assert set(r["answer"]["scores"]) == {"scope", "objective", "strategy", "execution"}
    assert 0 <= r["answer"]["overall"] <= 10 and len(r["model_answer"]["options"]) == 5 and r["model_answer"]["charter"]["leading"]
    assert c.get("/api/cases/retail-chain-margins").json()["case"]["model_answer"]     # unlocked after answering
    assert c.post("/api/cases/retail-chain-margins/answer", json={"answer": ANSWER}).status_code == 402


def test_admin_changes_live_case(seeded_client):
    c = seeded_client
    qa_login(c, role="admin")
    assert c.post("/api/admin/settings", json={"live_case_id": "nope"}).status_code == 400
    assert c.post("/api/admin/settings", json={"live_case_id": "hospital-claims"}).json()["live_case_id"] == "hospital-claims"
    assert next(x for x in c.get("/api/admin/cases").json()["items"] if x["live"])["id"] == "hospital-claims"
    c.post("/api/auth/logout")
    qa_login(c, plan="free")
    assert c.get("/api/cases").json()["items"][0]["id"] == "hospital-claims"


def test_member_answers_any_case(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    assert all(not i["locked"] for i in c.get("/api/cases").json()["items"])
    assert c.post("/api/cases/exporter-concentration/answer", json={"answer": ANSWER}).status_code == 200
    row = next(i for i in c.get("/api/cases").json()["items"] if i["id"] == "exporter-concentration")
    assert row["my_score"] is not None


def test_meeting_brief_links_only_from_search(seeded_client, mdb):
    c = seeded_client
    qa_login(c, plan="free")
    b = c.post("/api/briefs", json={"company": "Haldiram's", "meeting_with": "Head of Ops"}).json()
    assert b["live_news"] and b["test"] and len(b["questions"]) == 5 and len(b["problems"]) == 3
    assert all(n["url"].startswith("https://example.com/test-mode/") for n in b["news"])
    assert c.get(f"/api/briefs/{b['id']}").json()["about"]
    assert c.get("/api/briefs").json()["items"][0]["company"] == "Haldiram's"


def test_meeting_brief_without_search(seeded_client):
    c = seeded_client
    qa_login(c, role="admin")
    c.post("/api/admin/flags", json={"key": "BRIEF_WEB_SEARCH", "on": False})
    c.post("/api/auth/logout")
    qa_login(c, plan="member")
    b = c.post("/api/briefs", json={"company": "Acme Pumps"}).json()
    assert b["live_news"] is False and b["news"] == []


def test_brief_drops_made_up_news_numbers(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="member")
    real = llm.complete_json

    async def liar(**kw):
        out = await real(**kw)
        out["news"] = [{"i": 99, "why": "x"}, {"i": "two", "why": "y"}, {"i": 1, "why": "ok"}, {"i": 1, "why": "dup"}]
        return out
    monkeypatch.setattr(llm, "complete_json", liar)
    b = c.post("/api/briefs", json={"company": "Acme"}).json()
    assert len(b["news"]) == 1 and b["news"][0]["why"] == "ok"


def test_linkedin_score_rules():
    from features.linkedin import score_profile
    weak = score_profile("Senior Manager at XYZ Ltd | Open to work", "I am a professional.", "")
    strong = score_profile("I help family-run manufacturers grow profit 20% in 90 days | Operations consultant",
                           "Most manufacturers grow sales but lose margin. I help owners find the leaks and fix them. "
                           "In 22 years I cut costs by ₹14 crore, improved on-time delivery from 70% to 96% and "
                           "led 3 plant turnarounds. My clients are owner-led firms with ₹50–500 crore revenue. "
                           "I use a simple framework to diagnose the problem first. " * 2 + "Message me to talk.",
                           "")
    assert weak["score"] < 30 and strong["score"] >= 85 and strong["experience_checked"] is False
    assert weak["problems"][0]["key"] in {"headline", "about", "positioning"}


def test_linkedin_rewrites_paid_only(seeded_client):
    c = seeded_client
    qa_login(c, plan="free")
    r = c.post("/api/linkedin/check", json={"headline": "Plant head at ABC", "rewrite": True}).json()
    assert r["rewrites"] is None and r["rewrites_locked"] is True and 0 <= r["score"] <= 100
    c.post("/api/auth/logout")
    qa_login(c, plan="member")
    r = c.post("/api/linkedin/check", json={"headline": "Plant head at ABC", "about": "x" * 50, "rewrite": True}).json()
    assert [h["angle"] for h in r["rewrites"]["headlines"]] == ["Authority", "Outcome", "Niche"] and len(r["rewrites"]["posts"]) == 3
    assert r["rewrites"]["about"] and not r["rewrites_locked"]
    assert c.get("/api/linkedin").json()["latest"]["id"] == r["id"]


def test_consulting_file_collects_everything(seeded_client):
    c = seeded_client
    qa_login(c, plan="free")
    c.post("/api/readiness", json={"scores": {k: 6 for k in SKILLS}, "potential": 8})
    c.post("/api/start/snapshot", json={"experiences": ["Finance", "Audit"], "enjoy": [0]})
    c.put("/api/start/goal", json={"monthly_goal_inr": 200000, "fee_inr": 50000})
    c.post("/api/cases/retail-chain-margins/answer", json={"answer": ANSWER})
    c.post("/api/briefs", json={"company": "Zydus"})
    c.post("/api/linkedin/check", json={"headline": "CFO at a pharma company"})
    f = c.get("/api/file").json()
    assert f["readiness"]["total"] == 36 and f["niche"]["niche"] and f["goal"]["clients_per_month"] == 4
    assert f["cases"][0]["title"] == "Selling more, earning less" and f["briefs"][0]["input"]["company"] == "Zydus"
    assert f["linkedin"]["score"] >= 0


def test_snapshot_is_a_full_niche_package_and_feeds_knowledge(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    s = c.post("/api/start/snapshot", json={"experiences": ["Plant operations", "Lean"], "enjoy": [0], "industry": "auto parts",
                                             "proof": "Cut downtime 30% at a 600-person plant"}).json()
    o = s["options"][0]
    assert o["title"] and o["value_prop"].startswith("I help") and o["fee_low"] <= o["fee_high"]
    assert o["yearly_low"] == o["fee_low"] * 48 and "Actual income depends" in s["income_note"]
    c.put("/api/start/goal", json={"monthly_goal_inr": 300000, "fee_inr": 50000})
    k = c.get("/api/file").json()["knowledge"]
    assert k["niche"] == o["niche"] and k["target_industry"] == "auto parts" and k["consulting_goal"] == "₹3,00,000 a month at ₹50,000 per client"
    assert k["blueprint"].startswith("FINALIZED NICHE") and "CONSULTANT IDENTITY" in k["blueprint"] and "VALUE PROPOSITION" in k["blueprint"]
    from features.knowledge import system_block
    assert "Value proposition: I help" in system_block(k)


def test_gpt_catalogue_complete():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "gpts"
    cat = json.loads((root / "catalog.json").read_text())
    assert len(cat) == 52 and sum(1 for g in cat if g["program"] == "action") == 18
    for g in cat:
        assert (root / "prompts" / f"{g['slug']}.md").read_text().strip(), g["slug"]
