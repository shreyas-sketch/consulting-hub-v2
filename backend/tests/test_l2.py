"""L2: switched on by the team, pauses L1, L1 restarts after 6 months. L1 payments don't count towards L2."""
from datetime import timedelta

from conftest import login, qa_login, run

from billing import l2
from growth.clock import utcnow


def _member_with_l1(client):
    u = login(client, phone="9876511111", name="Ravi")["user"]
    co = client.post("/api/billing/checkout", json={"plan": "l1"}).json()
    client.post("/api/billing/verify", json={"subscription_id": co["subscription_id"]})
    client.post("/api/auth/logout")
    return u["id"], co["subscription_id"]


def test_start_l2_pauses_l1_and_resumes_after(client, mdb):
    uid, sid = _member_with_l1(client)
    qa_login(client, role="admin")
    d = client.post(f"/api/admin/users/{uid}/start-l2").json()
    assert d["result"]["l1_paused"] == 1 and d["result"]["restart_l1_in_app"] is False
    assert d["plan"]["plan"] == "l2" and d["plan"]["paused_for_l2"] is True and d["l2"]["active"]
    sub = run(mdb.subscriptions.find_one({"_id": sid}))
    assert sub["status"] == "paused" and sub["paused_for_l2"]
    assert client.post(f"/api/admin/users/{uid}/start-l2").status_code == 409      # already on L2

    # nothing resumes early
    assert run(l2.resume_due(mdb, utcnow() + timedelta(days=100)))["resumed"] == 0
    # after L2 ends: L1 resumes, the grant is over, member is back on L1
    later = utcnow() + timedelta(days=l2.L2_DAYS + 1)
    assert run(l2.resume_due(mdb, later))["resumed"] == 1
    sub = run(mdb.subscriptions.find_one({"_id": sid}))
    assert sub["status"] == "active" and sub["paused_for_l2"] is False
    import plans
    user = run(mdb.users.find_one({"phone": "+919876511111"}))
    assert run(plans.effective_plan(mdb, user, later))["plan"] == "l1"


def test_pause_refused_falls_back_to_cancel_and_restart_in_app(client, mdb):
    uid, sid = _member_with_l1(client)
    from billing.razorpay_client import FakeRazorpay
    FakeRazorpay.fail_pause = True
    qa_login(client, role="admin")
    d = client.post(f"/api/admin/users/{uid}/start-l2").json()
    assert d["result"]["l1_paused"] == 0 and d["result"]["restart_l1_in_app"] is True
    sub = run(mdb.subscriptions.find_one({"_id": sid}))
    assert sub["cancel_at_cycle_end"] and sub["ended_for_l2"]


def test_member_plan_ends_when_l2_starts(client, mdb):
    u = login(client, phone="9876522222")["user"]
    co = client.post("/api/billing/checkout", json={"plan": "member"}).json()
    client.post("/api/billing/verify", json={"subscription_id": co["subscription_id"]})
    client.post("/api/auth/logout")
    qa_login(client, role="admin")
    d = client.post(f"/api/admin/users/{u['id']}/start-l2").json()
    assert d["plan"]["plan"] == "l2" and d["result"]["restart_l1_in_app"] is True
    assert run(mdb.subscriptions.find_one({"_id": co["subscription_id"]}))["cancel_at_cycle_end"]


def test_on_l2_cannot_buy_l1(client):
    qa_login(client, plan="l2")
    r = client.post("/api/billing/checkout", json={"plan": "l1"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "on_l2"


def test_late_charge_event_does_not_wake_paused_l1(client, mdb):
    uid, sid = _member_with_l1(client)
    qa_login(client, role="admin")
    client.post(f"/api/admin/users/{uid}/start-l2")
    import json
    import hashlib
    import hmac
    from billing.razorpay_client import FakeRazorpay
    body = json.dumps(FakeRazorpay().charge_event(sid, 590000)).encode()
    sig = hmac.new(b"fake_webhook_secret", body, hashlib.sha256).hexdigest()
    client.post("/api/billing/razorpay/webhook", content=body, headers={"X-Razorpay-Signature": sig})
    assert run(mdb.subscriptions.find_one({"_id": sid}))["status"] == "paused"


def test_resume_job_registered(client):
    qa_login(client, role="admin")
    items = client.get("/api/admin/jobs").json()["items"]
    assert [j["name"] for j in items] == ["l2_resume"]
    assert client.post("/api/admin/jobs/l2_resume/run").json()["ok"]
