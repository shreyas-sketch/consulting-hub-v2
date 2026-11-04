"""Client Diagnostic: AI draft (8-12 questions, 1-5 scales + short answers, scoring rule), member edits, publish,
public form and answers without login (rate-limited per IP), report for the member + thank-you for the prospect,
inbox alert. Metered per diagnostic created. L2 only."""
from conftest import qa_login, run

import llm
from features import diagnostic
from growth.clock import ist_month_key


def l2(c):
    return qa_login(c, plan="l2")["user"]["id"]


def used(c):
    return c.get("/api/me/plan").json()["limits"]["diagnostic"]["used"]


def published(c):
    x = c.post("/api/diagnostic", json={"topic": "Sales engine", "audience": "Owners of engineering MSMEs"}).json()
    return c.post(f"/api/diagnostic/{x['id']}/publish").json()


def answers_for(form, scale=4):
    return {q["id"]: (scale if q["kind"] == "scale" else "Dealers keep asking for credit.") for q in form["questions"]}


def test_draft_edit_publish(client):
    l2(client)
    r = client.post("/api/diagnostic", json={"topic": "Sales engine"})
    assert r.status_code == 200, r.text
    x = r.json()
    assert 8 <= len(x["questions"]) <= 12 and sum(q["kind"] == "scale" for q in x["questions"]) >= 5
    assert [b["min"] for b in x["bands"]] == [0, 40, 70] and "average" in x["rule"]
    assert x["status"] == "draft" and x["public_path"] is None and used(client) == 1
    qs = x["questions"][:5] + [{"text": "How many dealers do you have?", "kind": "short", "dimension": "Sales"}]
    e = client.put(f"/api/diagnostic/{x['id']}", json={"title": "Dealer health check", "intro": "Five minutes.",
                                                       "questions": qs, "cta": "Book a call", "cta_link": "https://cal.com/me"})
    assert e.status_code == 200, e.text
    e = e.json()
    assert e["title"] == "Dealer health check" and len(e["questions"]) == 6 and e["questions"][0]["id"] == x["questions"][0]["id"]
    two_scale = qs[:2] + qs[5:] + [{"text": "What would you fix first?", "kind": "short"}]
    bad = client.put(f"/api/diagnostic/{x['id']}", json={"title": "x" * 5, "questions": two_scale})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "questions"
    assert client.put(f"/api/diagnostic/{x['id']}", json={"title": "Dealer check", "questions": qs,
                                                          "cta_link": "javascript:alert(1)"}).status_code == 422
    p = client.post(f"/api/diagnostic/{x['id']}/publish").json()
    assert p["status"] == "published" and p["public_path"] == f"/d/{p['public_id']}"
    again = client.post(f"/api/diagnostic/{x['id']}/publish").json()
    assert again["public_id"] == p["public_id"]                            # the link never changes


def test_public_flow_without_login(client, mdb):
    uid = l2(client)
    p = published(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    form = client.get(f"/api/diagnostic/public/{p['public_id']}")
    assert form.status_code == 200, form.text
    form = form.json()
    assert form["title"] and "user_id" not in form and all("dimension" not in q for q in form["questions"])
    url = f"/api/diagnostic/public/{p['public_id']}/responses"
    r = client.post(url, json={"name": "Anil Shah", "answers": answers_for(form)})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "contact"
    some = answers_for(form)
    some.pop(next(q["id"] for q in form["questions"] if q["kind"] == "scale"))
    assert client.post(url, json={"name": "Anil Shah", "phone": "98765 43210", "answers": some}).json()["detail"]["code"] == "answers"
    r = client.post(url, json={"name": "Anil Shah", "company": "Shah Castings", "email": "anil@shahcastings.in",
                               "answers": answers_for(form, 4)})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["pct"] == 75 and t["band"] and t["thank_you"]

    inbox = run(mdb.inbox.find({"user_id": uid, "kind": "diagnostic"}).to_list(5))
    assert len(inbox) == 1 and "Anil Shah" in inbox[0]["title"] and inbox[0]["link"].startswith(f"/app/diagnostic/{p['id']}")

    l2(client)
    full = client.get(f"/api/diagnostic/{p['id']}").json()
    assert full["diagnostic"]["responses"] == 1 and full["responses"][0]["company"] == "Shah Castings"
    rep = client.get(f"/api/diagnostic/{p['id']}/responses/{full['responses'][0]['id']}").json()
    assert rep["email"] == "anil@shahcastings.in" and len(rep["report"]["recommendations"]) == 3
    assert rep["report"]["strengths"] and rep["report"]["gaps"] and rep["report"]["next_conversation"]
    assert len(rep["qa"]) == len(form["questions"]) and used(client) == 1    # answers don't use the member's limit


def test_public_rate_limit_per_ip(client, monkeypatch):
    l2(client)
    p = published(client)
    client.post("/api/auth/logout")
    url = f"/api/diagnostic/public/{p['public_id']}/responses"
    for _ in range(10):
        assert client.post(url, json={"name": "Spam Bot", "answers": {}}).status_code == 422
    r = client.post(url, json={"name": "Spam Bot", "answers": {}})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many"
    assert client.post(url, json={"name": "Spam Bot", "answers": {}}, headers={"x-forwarded-for": "10.0.0.9"}).status_code == 422
    monkeypatch.setattr(diagnostic, "VIEWS_PER_HOUR", 2)
    form_url = f"/api/diagnostic/public/{p['public_id']}"
    assert [client.get(form_url).status_code for _ in range(3)] == [200, 200, 429]


def test_closed_when_unpublished_or_plan_ends(client, mdb):
    uid = l2(client)
    p = published(client)
    client.post(f"/api/diagnostic/{p['id']}/unpublish")
    assert client.get(f"/api/diagnostic/public/{p['public_id']}").json()["detail"]["code"] == "closed"
    client.post(f"/api/diagnostic/{p['id']}/publish")
    assert client.get(f"/api/diagnostic/public/{p['public_id']}").status_code == 200
    run(mdb.plan_grants.delete_many({"user_id": uid}))
    assert client.get(f"/api/diagnostic/public/{p['public_id']}").status_code == 404
    assert client.get("/api/diagnostic/public/nope").status_code == 404


def test_ai_busy_on_answer_still_thanks_the_prospect(client, monkeypatch):
    l2(client)
    p = published(client)
    form = client.get(f"/api/diagnostic/public/{p['public_id']}").json()

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = client.post(f"/api/diagnostic/public/{p['public_id']}/responses",
                    json={"name": "Neha Rao", "phone": "+91 98200 11111", "answers": answers_for(form, 2)})
    assert r.status_code == 200 and r.json()["pct"] == 25 and "Neha" in r.json()["thank_you"]
    rid = client.get(f"/api/diagnostic/{p['id']}").json()["responses"][0]["id"]
    assert client.get(f"/api/diagnostic/{p['id']}/responses/{rid}").json()["report"]["auto"] is True


def test_draft_refund_limit_and_lock(client, mdb, monkeypatch):
    uid = l2(client)

    async def few(**kw):
        return {"title": "Check", "questions": [{"text": "Is it good?", "kind": "scale"}]}
    monkeypatch.setattr(llm, "complete_json", few)
    r = client.post("/api/diagnostic", json={})
    assert r.status_code == 503 and used(client) == 0
    run(mdb.usage.update_one({"_id": f"{uid}:{ist_month_key()}"}, {"$set": {"diagnostic": 20, "user_id": uid}}, upsert=True))
    r = client.post("/api/diagnostic", json={})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"
    client.post("/api/auth/logout")
    qa_login(client, plan="l1")
    r = client.post("/api/diagnostic", json={})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    assert client.get("/api/diagnostic").status_code == 403
