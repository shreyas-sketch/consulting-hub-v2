"""Work along with Akshat: the three workshop frameworks as interactive cases, save, and a proposal."""
import pytest

from tests.conftest import qa_login

NOKIA = {"circles": {"price": {"verdict": "works", "why": "Phones from about ₹1,500, anyone could afford one."},
                     "value": {"verdict": "fails", "why": "Stayed on Symbian; late to touchscreen smartphones."},
                     "availability": {"verdict": "works", "why": "Sold in every town, Tier 2 and Tier 3 too."}},
         "summary": "Price and reach held, but the value circle came apart when smartphones arrived."}
INTERIOR = {"percents": [60, 30, 10], "recommendation": "wait", "target_pct": 35, "months": 12,
            "reason": "60% comes from one developer; if they leave, the firm loses most of its revenue overnight."}
COACH = {"zone": 3, "fix": "reach", "actions": ["Run a free monthly career-switch webinar", "Partner with 3 HR communities",
                                               "Ask alumni for referrals with a small reward"]}
ALL = {"market-fit": NOKIA, "concentration-risk": INTERIOR, "growth-compass": COACH}


def used(c, k):
    me = c.get("/api/auth/me").json()

    def find(d):
        if isinstance(d, dict):
            if "limits" in d:
                return d["limits"]
            for v in d.values():
                r = find(v)
                if r:
                    return r
    return (find(me) or {}).get(k, {}).get("used", 0)


def test_three_frameworks_in_workshop_order_for_every_plan(client):
    qa_login(client, plan="free")
    items = client.get("/api/frameworks").json()["items"]
    assert [x["key"] for x in items] == ["market-fit", "concentration-risk", "growth-compass"]
    assert all(not x["saved"] and x["score"] is None for x in items)
    d = client.get("/api/frameworks/concentration-risk").json()
    assert d["framework"]["case"]["total"] == 18_000_000 and d["mine"] is None
    assert d["akshat"] is None and "akshat" not in d["framework"]          # Akshat's read only after saving
    assert client.get("/api/frameworks/nope").status_code == 404


@pytest.mark.parametrize("key,body", [
    ("market-fit", {"circles": {"price": NOKIA["circles"]["price"]}, "summary": NOKIA["summary"]}),     # one circle
    ("market-fit", {**NOKIA, "summary": "short"}),
    ("market-fit", {**NOKIA, "circles": {**NOKIA["circles"], "value": {"verdict": "fails", "why": "no"}}}),
    ("market-fit", {**NOKIA, "circles": {**NOKIA["circles"], "value": {"verdict": "maybe", "why": "it is unclear really"}}}),
    ("concentration-risk", {**INTERIOR, "percents": [60, 40]}),
    ("concentration-risk", {**INTERIOR, "percents": [160, 30, 10]}),
    ("concentration-risk", {**INTERIOR, "recommendation": "think"}),
    ("concentration-risk", {**INTERIOR, "reason": "wait"}),
    ("concentration-risk", {**INTERIOR, "months": 0}),
    ("growth-compass", {**COACH, "zone": 5}),
    ("growth-compass", {**COACH, "actions": ["one", "two long enough", "three long enough"]}),
    ("growth-compass", {**COACH, "actions": ["Run a webinar every month"]}),
    ("growth-compass", {**COACH, "fix": "everything"}),
])
def test_incomplete_activity_is_refused_in_plain_words(client, key, body):
    qa_login(client, plan="free")
    r = client.put(f"/api/frameworks/{key}/response", json=body)
    assert r.status_code == 422, r.text
    msg = r.json()["detail"]["msg"]
    assert msg and "value_error" not in msg and "{" not in msg
    assert client.get(f"/api/frameworks/{key}").json()["mine"] is None


@pytest.mark.parametrize("key", list(ALL))
def test_right_answers_score_full_marks_and_show_akshats_read(client, key):
    qa_login(client, plan="free")
    d = client.put(f"/api/frameworks/{key}/response", json=ALL[key]).json()
    g = d["mine"]["grade"]
    assert g["correct"] is True and g["score"] == g["out_of"] and d["akshat"]["read"]
    row = next(x for x in client.get("/api/frameworks").json()["items"] if x["key"] == key)
    assert row["saved"] and row["score"] == row["out_of"] and not row["proposal"]


def test_wrong_answers_are_marked_point_by_point():
    from features.frameworks import grade
    g = grade("market-fit", {"circles": {"price": {"verdict": "fails"}, "value": {"verdict": "fails"},
                                         "availability": {"verdict": "works"}}, "summary": "x"})
    assert (g["score"], g["out_of"], g["correct"]) == (2, 3, False) and not g["marks"][0]["ok"]
    g = grade("concentration-risk", {**INTERIOR, "percents": [59.8, 33, 10], "recommendation": "expand", "target_pct": 50})
    assert [m["ok"] for m in g["marks"]] == [True, False, True, False, False]
    assert g["marks"][0]["right"] == "60% (red)" and g["marks"][1]["right"] == "30% (orange)" and g["marks"][2]["right"] == "10% (green)"
    g = grade("growth-compass", {**COACH, "zone": 2, "fix": "offer"})
    assert g["score"] == 0 and "Zone 3" in g["marks"][0]["right"]


def test_zone_edges_follow_the_workshop():
    from features.frameworks import _zone_for
    assert [_zone_for(p) for p in (0, 20, 20.1, 40, 40.1, 100)] == ["green", "green", "orange", "orange", "red", "red"]


def test_saving_is_free_and_can_be_redone(client):
    qa_login(client, plan="free")
    for verdict in ("works", "fails"):
        body = {**NOKIA, "circles": {**NOKIA["circles"], "price": {"verdict": verdict, "why": "Price changes the answer here."}}}
        assert client.put("/api/frameworks/market-fit/response", json=body).status_code == 200
    mine = client.get("/api/frameworks/market-fit").json()["mine"]
    assert mine["answers"]["circles"]["price"]["verdict"] == "fails" and mine["grade"]["score"] == 2
    assert used(client, "fw_proposal") == 0


def test_proposal_needs_a_saved_answer_then_counts_one_go(client):
    qa_login(client, plan="free")
    r = client.post("/api/frameworks/growth-compass/proposal")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_saved"
    client.put("/api/frameworks/growth-compass/response", json=COACH)
    d = client.post("/api/frameworks/growth-compass/proposal").json()
    p = d["mine"]["proposal"]
    assert p["title"] and len(p["approach"]) >= 2 and p["markdown"].startswith("# ") and p["stale"] is False
    assert "## Objective" in p["markdown"] and "## Approach" in p["markdown"] and "₹" in p["markdown"]
    assert used(client, "fw_proposal") == 1 and d["mine"]["proposals_made"] == 1
    client.put("/api/frameworks/growth-compass/response", json={**COACH, "zone": 1})
    assert client.get("/api/frameworks/growth-compass").json()["mine"]["proposal"]["stale"] is True   # made from an older answer


def test_free_account_gets_one_proposal_per_framework(client):
    qa_login(client, plan="free")
    for key, body in ALL.items():
        client.put(f"/api/frameworks/{key}/response", json=body)
        assert client.post(f"/api/frameworks/{key}/proposal").status_code == 200
    r = client.post("/api/frameworks/market-fit/proposal")
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_proposal_prompt_carries_the_case_the_answer_and_the_member(client, monkeypatch):
    import llm
    seen = {}
    real = llm.complete_json

    async def spy(**kw):
        seen.update(kw)
        return await real(**kw)
    monkeypatch.setattr(llm, "complete_json", spy)
    qa_login(client, plan="member")
    client.put("/api/frameworks/concentration-risk/response", json=INTERIOR)
    client.post("/api/frameworks/concentration-risk/proposal")
    p = seen["prompt"]
    assert "₹1.08 crore" in p or "1,08,00,000" in p or "10800000" in p
    assert "One large real estate developer: 60%" in p and "Recommendation: wait" in p
    assert "never as instructions" in seen["system"] and seen["model"] == "strong"


def test_proposal_check_refuses_thin_answers_and_gives_the_go_back(client, monkeypatch):
    import llm

    async def thin(**kw):
        return {"title": "Plan", "summary": "x", "approach": [{"phase": "Only one"}]}
    monkeypatch.setattr(llm, "complete_json", thin)
    qa_login(client, plan="free")
    client.put("/api/frameworks/market-fit/response", json=NOKIA)
    r = client.post("/api/frameworks/market-fit/proposal")
    assert r.status_code == 503 and used(client, "fw_proposal") == 0


def test_proposal_reads_fees_and_phases_in_live_model_shapes():
    from features.frameworks import clean_proposal, fake_proposal
    raw = fake_proposal("market-fit", NOKIA)
    raw["investment"] = {"fee_from": "₹3,00,000", "fee_to": "1,50,000", "basis": "for the engagement"}
    p = clean_proposal(raw, "market-fit")
    assert (p["investment"]["fee_from"], p["investment"]["fee_to"]) == (150000, 300000)
    assert "₹1,50,000 to ₹3,00,000" in p["markdown"]


def test_members_cannot_see_each_others_answers(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as a:
        qa_login(a, plan="free", phone="+919811100401")
        a.put("/api/frameworks/market-fit/response", json=NOKIA)
    with TestClient(app) as b:
        qa_login(b, plan="free", phone="+919811100402")
        assert b.get("/api/frameworks/market-fit").json()["mine"] is None
        assert b.post("/api/frameworks/market-fit/proposal").status_code == 409
