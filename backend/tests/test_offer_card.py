"""Offer Card: AI card from what's known, member edits (free), latest + history, plan and limit gates."""
from conftest import qa_login

import llm


def used(c, meter):
    return c.get("/api/me/plan").json()["limits"][meter]["used"]


def test_offer_card_make_edit_and_history(seeded_client):
    c = seeded_client
    qa_login(c, plan="l1")
    assert c.get("/api/offer-card").json() == {"latest": None, "history": []}
    r = c.post("/api/offer-card", json={"offer_name": "Margin Reset", "fee_from_inr": 30000, "fee_to_inr": 60000,
                                         "what_you_get": "A 2-week diagnosis\nWeekly working session"})
    assert r.status_code == 200, r.text
    card = r.json()
    for f in ("offer_name", "ideal_client", "problem", "outcome", "engagement", "what_you_get", "fee_from_inr",
              "fee_to_inr", "proof", "call_to_action"):
        assert card[f], f
    assert card["offer_name"] == "Margin Reset"
    assert (card["fee_from_inr"], card["fee_to_inr"]) == (30000, 60000)       # the member's own range is kept
    assert card["what_you_get"][:2] == ["A 2-week diagnosis", "Weekly working session"]
    assert used(c, "offer_card") == 1

    edit = {**{k: card[k] for k in ("ideal_client", "problem", "outcome", "engagement", "fee_basis", "proof",
                                    "call_to_action")},
            "offer_name": "The Margin Reset", "what_you_get": ["One", " ", "Two"], "fee_from_inr": 40000, "fee_to_inr": 80000}
    e = c.put(f"/api/offer-card/{card['id']}", json=edit)
    assert e.status_code == 200, e.text
    assert e.json()["offer_name"] == "The Margin Reset" and e.json()["what_you_get"] == ["One", "Two"] and e.json()["edited"]
    assert used(c, "offer_card") == 1                                           # editing is free
    bad = c.put(f"/api/offer-card/{card['id']}", json={**edit, "fee_from_inr": 90000, "fee_to_inr": 50000})
    assert bad.status_code == 422

    c.post("/api/offer-card", json={})
    mine = c.get("/api/offer-card").json()
    assert len(mine["history"]) == 2 and mine["latest"]["id"] != card["id"]
    assert mine["latest"]["fee_from_inr"] <= mine["latest"]["fee_to_inr"]
    assert c.get(f"/api/offer-card/{card['id']}").json()["offer_name"] == "The Margin Reset"
    assert c.get("/api/offer-card/nope").status_code == 404


def test_offer_card_locked_for_member(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    r = c.post("/api/offer-card", json={})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"


def test_offer_card_limit(seeded_client):
    c = seeded_client
    qa_login(c, plan="l1")
    for _ in range(10):
        assert c.post("/api/offer-card", json={}).status_code == 200
    r = c.post("/api/offer-card", json={})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_offer_card_ai_failure_and_bad_shape_refund(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = c.post("/api/offer-card", json={})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy"
    assert used(c, "offer_card") == 0

    async def empty(**kw):
        return {"offer_name": "Only a name"}
    monkeypatch.setattr(llm, "complete_json", empty)
    assert c.post("/api/offer-card", json={}).status_code == 503
    assert used(c, "offer_card") == 0
