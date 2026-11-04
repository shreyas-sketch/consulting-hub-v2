"""Outreach Drafter: three variants (short, warm, direct) per draft, metered per draft; drafts only, the member
sends; marking sent marks the network contact as contacted. L2 only."""
from conftest import qa_login, run

import llm
from growth.clock import ist_month_key

TYPED = {"name": "Meera Kapoor", "role": "COO", "company": "Sunrise Textiles", "relationship": "worked together at Arvind 2010-14",
         "context": "They opened a new unit in Surat last month.", "channel": "email", "goal": "diagnostic_call"}


def l2(c):
    return qa_login(c, plan="l2")["user"]["id"]


def used(c):
    return c.get("/api/me/plan").json()["limits"]["outreach"]["used"]


def test_typed_contact_three_variants_and_mark_sent(client):
    l2(client)
    r = client.post("/api/outreach", json=TYPED)
    assert r.status_code == 200, r.text
    o = r.json()
    assert [v["style"] for v in o["variants"]] == ["short", "warm", "direct"]
    assert all(v["subject"] and "Meera" in v["text"] for v in o["variants"])        # email: subject line
    assert o["status"] == "draft" and used(client) == 1
    w = client.post("/api/outreach", json={**TYPED, "channel": "whatsapp", "goal": "intro"}).json()
    assert all(v["subject"] == "" for v in w["variants"])                             # WhatsApp: no subject
    e = client.patch(f"/api/outreach/{o['id']}", json={"variants": [{"style": "short", "text": "Hi Meera, edited."}],
                                                      "chosen": "short"}).json()
    assert e["variants"][0]["text"] == "Hi Meera, edited." and e["variants"][1]["text"] == o["variants"][1]["text"]
    s = client.patch(f"/api/outreach/{o['id']}", json={"status": "sent"}).json()
    assert s["status"] == "sent" and s["sent_at"]
    assert [x["status"] for x in client.get("/api/outreach").json()["items"]] == ["draft", "sent"]
    assert client.get("/api/outreach?status=sent").json()["items"][0]["id"] == o["id"]
    assert client.delete(f"/api/outreach/{w['id']}").json()["ok"]


def test_from_network_contact_marks_contacted(client, mdb):
    l2(client)
    client.post("/api/network/paste", json={"text": "Rahul Desai, Managing Director, Desai Pumps Pvt Ltd"})
    cid = client.get("/api/network").json()["items"][0]["id"]
    client.patch(f"/api/network/{cid}", json={"notes": "Met at the CII summit"})
    o = client.post("/api/outreach", json={"contact_id": cid, "channel": "linkedin", "goal": "reconnect"}).json()
    assert o["contact"]["name"] == "Rahul Desai" and o["contact"]["company"] == "Desai Pumps Pvt Ltd"
    assert "CII summit" in o["contact"]["context"] and o["contact_id"] == cid
    client.patch(f"/api/outreach/{o['id']}", json={"status": "sent"})
    assert client.get(f"/api/network/{cid}").json()["status"] == "contacted"
    assert client.get(f"/api/outreach?contact_id={cid}").json()["items"][0]["id"] == o["id"]
    assert client.post("/api/outreach", json={"contact_id": "nope"}).status_code == 404


def test_needs_a_name(client):
    l2(client)
    r = client.post("/api/outreach", json={"channel": "linkedin"})
    assert r.status_code == 422 and used(client) == 0


def test_l1_locked(client):
    qa_login(client, plan="l1")
    r = client.post("/api/outreach", json=TYPED)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    assert client.get("/api/outreach").status_code == 403


def test_limit(client, mdb):
    uid = l2(client)
    run(mdb.usage.update_one({"_id": f"{uid}:{ist_month_key()}"}, {"$set": {"outreach": 100, "user_id": uid}}, upsert=True))
    r = client.post("/api/outreach", json=TYPED)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_incomplete_ai_answer_refunds(client, monkeypatch):
    l2(client)

    async def two(**kw):
        return {"variants": [{"style": "short", "text": "Hi Meera, long time. How are you doing?"},
                             {"style": "warm", "text": "Hi Meera, I was thinking of our Arvind days."}]}
    monkeypatch.setattr(llm, "complete_json", two)
    r = client.post("/api/outreach", json=TYPED)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy" and used(client) == 0
