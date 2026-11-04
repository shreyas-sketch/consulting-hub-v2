"""Support: member opens a ticket, the team answers from Admin (alert), member replies (reopens), close."""
from conftest import qa_login, run


def test_support_full_loop(seeded_client, mdb):
    c = seeded_client
    qa_login(c, plan="free")
    r = c.post("/api/support/tickets", json={"subject": "Help", "category": "tools", "text": "The deck tool is stuck."})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"

    me = qa_login(c, plan="member")
    assert c.post("/api/support/tickets", json={"subject": "Hi", "category": "tools", "text": "x"}).status_code == 422
    assert c.post("/api/support/tickets", json={"subject": "Help me", "category": "nope", "text": "Something"}).status_code == 422
    r = c.post("/api/support/tickets", json={"subject": "Payment taken twice", "category": "billing",
                                             "text": "I was charged ₹2,359 twice this month."})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["status"] == "open" and t["messages"][0]["from"] == "member" and "by_name" not in t["messages"][0]
    assert [x["id"] for x in c.get("/api/support/tickets").json()["items"]] == [t["id"]]

    assert c.get("/api/admin/support").status_code == 403
    qa_login(c, role="admin")
    inbox = c.get("/api/admin/support", params={"status": "open"}).json()
    assert inbox["open"] == 1 and inbox["counts"] == {"open": 1, "answered": 0, "closed": 0}
    row = inbox["items"][0]
    assert row["member"]["name"] == "Demo Member" and row["member"]["plan"] == "member" and row["member"]["phone"]
    assert c.get("/api/admin/support", params={"q": "twice"}).json()["items"][0]["id"] == t["id"]
    assert c.get("/api/admin/support", params={"q": "nothing-like-this"}).json()["items"] == []
    r = c.post(f"/api/admin/support/{t['id']}/reply", json={"text": "Sorry about that. The second charge is refunded."})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "answered" and r.json()["messages"][-1]["from"] == "team"
    assert r.json()["messages"][-1]["by_name"]
    alert = run(mdb.inbox.find_one({"user_id": me["user"]["id"], "kind": "support"}))
    assert alert and alert["link"] == f"/app/support/{t['id']}" and "Payment taken twice" in alert["title"]
    assert c.get("/api/admin/support").json()["open"] == 0

    qa_login(c, plan="member")
    mine = c.get(f"/api/support/tickets/{t['id']}").json()
    assert mine["status"] == "answered" and "by_name" not in mine["messages"][-1]
    r = c.post(f"/api/support/tickets/{t['id']}/reply", json={"text": "Thanks. When will it reach my account?"}).json()
    assert r["status"] == "open" and len(r["messages"]) == 3
    assert c.post(f"/api/support/tickets/{t['id']}/close").json()["status"] == "closed"
    assert c.post(f"/api/support/tickets/{t['id']}/reply", json={"text": "One more thing"}).json()["status"] == "open"

    qa_login(c, role="admin")
    assert c.post(f"/api/admin/support/{t['id']}/close").json()["status"] == "closed"
    one = c.get(f"/api/admin/support/{t['id']}").json()
    assert one["member"]["plan_label"] == "₹1,999 plan" and len(one["messages"]) == 4
    assert c.get("/api/admin/support/nope").status_code == 404


def test_members_only_see_their_own_tickets(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    t = c.post("/api/support/tickets", json={"subject": "Website question", "category": "tools", "text": "How do I add a page?"}).json()
    qa_login(c, plan="l1")
    assert c.get(f"/api/support/tickets/{t['id']}").status_code == 404
    assert c.post(f"/api/support/tickets/{t['id']}/reply", json={"text": "hi"}).status_code == 404
    assert c.get("/api/support/tickets").json()["items"] == []


def test_open_ticket_cap(seeded_client):
    c = seeded_client
    qa_login(c, plan="l1")
    for i in range(10):
        assert c.post("/api/support/tickets", json={"subject": f"Question {i}", "text": "Something here"}).status_code == 200
    r = c.post("/api/support/tickets", json={"subject": "One more", "text": "Something here"})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many"
