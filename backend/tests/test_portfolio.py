"""Portfolio Project: practice client → approach → feedback, case study (projected outcome) and video script."""
from conftest import qa_login

import llm

ANSWER = {"scope": "Profit has fallen since April in the two Pune plants, for the industrial valves line, direct channel.",
          "objective": "From 6% to 10% EBITDA in 9 months. Success: 10% by month 9. Failure: no move by month 3.",
          "framework_options": "Profit tree: price, volume, cost. Options: cut discounts, fix scrap, renegotiate steel, "
                               "drop slow products, a pricing review.",
          "do_first": "Cut discounting first: high benefit, easy, the owner controls it.",
          "owner_metrics": "Owner: sales head. Weekly metric: average discount %. Monthly metric: EBITDA %."}


def used(c):
    return c.get("/api/me/plan").json()["limits"]["portfolio"]["used"]


def test_portfolio_full_flow(seeded_client):
    c = seeded_client
    qa_login(c, plan="l1")
    r = c.post("/api/portfolio")
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["status"] == "brief" and p["review"] is None
    b = p["brief"]
    for f in ("company", "company_type", "size", "city", "decision_maker_name", "decision_maker_title", "client_words"):
        assert b[f], f
    assert used(c) == 1
    a = c.post(f"/api/portfolio/{p['id']}/answer", json=ANSWER)
    assert a.status_code == 200, a.text
    d = a.json()
    assert d["status"] == "done" and d["answer"]["scope"] == ANSWER["scope"]
    rv = d["review"]
    assert set(rv["scores"]) == {"scope", "objective", "strategy", "execution"} and 0 <= rv["overall"] <= 10
    cs = rv["case_study"]
    assert [s["step"] for s in cs["approach"]] == [1, 2, 3, 4, 5, 6] and cs["approach"][5]["name"] == "Implementation charter"
    assert cs["expected_outcome"] and "Projected" in d["outcome_label"] and "fictional" in d["practice_note"]
    assert all(rv["video_script"][k] for k in ("hook", "problem", "approach", "result", "call_to_action"))
    assert rv["script_seconds"] > 0
    assert used(c) == 1                                  # answer + review are part of the project
    again = c.post(f"/api/portfolio/{p['id']}/answer", json=ANSWER)
    assert again.status_code == 409
    items = c.get("/api/portfolio").json()["items"]
    assert items[0]["id"] == p["id"] and items[0]["status"] == "done" and items[0]["overall"] == rv["overall"]
    assert c.post(f"/api/portfolio/{p['id']}/answer", json={**ANSWER, "scope": "short"}).status_code == 422


def test_portfolio_locked_and_limit(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    r = c.post("/api/portfolio")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    qa_login(c, plan="l1")
    for _ in range(2):
        assert c.post("/api/portfolio").status_code == 200
    r = c.post("/api/portfolio")
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_portfolio_ai_failures(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")
    real = llm.complete_json

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = c.post("/api/portfolio")
    assert r.status_code == 503 and used(c) == 0          # refunded

    monkeypatch.setattr(llm, "complete_json", real)
    p = c.post("/api/portfolio").json()
    monkeypatch.setattr(llm, "complete_json", boom)
    r = c.post(f"/api/portfolio/{p['id']}/answer", json=ANSWER)
    assert r.status_code == 503
    assert c.get(f"/api/portfolio/{p['id']}").json()["status"] == "answered"     # answer kept, try again

    async def half(**kw):
        return {"scores": {"scope": 5, "objective": 5, "strategy": 5, "execution": 5}, "case_study": {"approach": ["a"]}}
    monkeypatch.setattr(llm, "complete_json", half)
    assert c.post(f"/api/portfolio/{p['id']}/review").status_code == 503

    monkeypatch.setattr(llm, "complete_json", real)
    ok = c.post(f"/api/portfolio/{p['id']}/review")
    assert ok.status_code == 200 and ok.json()["status"] == "done"
    assert used(c) == 1
