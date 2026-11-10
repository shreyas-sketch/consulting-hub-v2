"""Plans, limits and billing for free / ₹1,999 (monthly + yearly) / L1."""
import hashlib
import hmac
import json

from conftest import login, qa_login, run

import plans


def _sig(body: bytes) -> str:
    return hmac.new(b"fake_webhook_secret", body, hashlib.sha256).hexdigest()


def _buy(client, plan, period="monthly"):
    co = client.post("/api/billing/checkout", json={"plan": plan, "period": period})
    assert co.status_code == 200, co.text
    co = co.json()
    r = client.post("/api/billing/verify", json={"subscription_id": co["subscription_id"], "payment_id": "x", "signature": "y"})
    assert r.status_code == 200, r.text
    return co, r.json()["plan"]


def test_prices_include_gst():
    assert plans.total_inr("member", "monthly") == 2359
    assert plans.total_inr("member", "yearly") == 23600
    assert plans.total_inr("l1", "monthly") == 5900
    assert plans.monthly_value("member", "yearly") == 20000 / 12


def test_new_account_is_free_with_one_go_each(client):
    login(client)
    info = client.get("/api/me/plan").json()
    assert info["plan"] == "free" and info["label"] == "Free account"
    assert info["limits"]["brief"] == {"used": 0, "limit": 1, "once": True}
    assert info["features"]["readiness"] and not info["features"]["presentation"] and not info["features"]["akshat_ai"]


def test_free_uses_once_for_life_then_402(client):
    qa_login(client, plan="free")
    body = {"scores": {k: 5 for k in ("diagnosis", "offer", "acquisition", "pricing", "delivery", "visibility")}, "potential": 7}
    assert client.post("/api/readiness", json=body).status_code == 200
    r = client.post("/api/readiness", json=body)
    assert r.status_code == 402
    d = r.json()["detail"]
    assert d["code"] == "limit" and d["once"] is True and d["plan_needed"] == "member" and "free go" in d["msg"]


def test_webinar_tools_switch_off_locks_free(client):
    qa_login(client, role="admin")
    client.post("/api/admin/flags", json={"key": "WEBINAR_TOOLS", "on": False})
    client.post("/api/auth/logout")
    qa_login(client, plan="free")
    full = {k: 5 for k in ("diagnosis", "offer", "acquisition", "pricing", "delivery", "visibility")}
    r = client.post("/api/readiness", json={"scores": full, "potential": 5})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"


def test_catalog_public(client):
    r = client.get("/api/plans/catalog").json()
    assert [p["id"] for p in r["plans"]] == ["free", "member", "l1", "l2"] and r["gst_pct"] == 18
    member = next(p for p in r["plans"] if p["id"] == "member")
    assert [(x["period"], x["total_inr"]) for x in member["periods"]] == [("monthly", 2359), ("yearly", 23600)]
    assert "trial_days" not in r


def test_member_monthly_and_yearly_checkout(client, mdb):
    qa_login(client, plan="free")
    co, info = _buy(client, "member", "yearly")
    assert co["amount_inr"] == 23600 and co["price_inr"] == 20000 and co["gst_inr"] == 3600
    assert info["plan"] == "member" and info["period"] == "yearly" and info["source"] == "paid"
    assert info["limits"]["brief"] == {"used": 0, "limit": 4, "once": False}
    again = client.post("/api/billing/checkout", json={"plan": "member", "period": "monthly"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_on_plan"


def test_l1_monthly_only(client):
    qa_login(client, plan="free")
    r = client.post("/api/billing/checkout", json={"plan": "l1", "period": "yearly"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_period"
    co, info = _buy(client, "l1")
    assert co["amount_inr"] == 5900 and info["plan"] == "l1" and info["features"]["akshat_ai"]


def test_upgrade_member_to_l1_stops_old_renewal(client, mdb):
    qa_login(client, plan="free")
    co1, _ = _buy(client, "member")
    co2, info = _buy(client, "l1")
    old = run(mdb.subscriptions.find_one({"_id": co1["subscription_id"]}))
    assert info["plan"] == "l1" and old["cancel_at_cycle_end"] is True and old["replaced_by"] == co2["subscription_id"]


def test_cancel_l1_offers_member_plan_once(client, mdb):
    login(client)
    _buy(client, "l1")
    c = client.post("/api/billing/cancel").json()
    assert c["status"] == "cancels_at_period_end" and c["offer"]["plan"] == "member"
    assert [p["total_inr"] for p in c["offer"]["periods"]] == [2359, 23600]
    assert client.get("/api/me/plan").json()["plan"] == "l1"          # access until the paid month ends
    _, info = _buy(client, "member")                                    # takes the offer
    assert info["plan"] == "l1"                                          # still l1 until that month ends
    # buy L1 again later and cancel again: no second offer
    run(mdb.subscriptions.update_many({"plan": "l1"}, {"$set": {"status": "cancelled"}}))
    client.post("/api/billing/cancel")                                   # cancels the member plan
    run(mdb.subscriptions.update_many({}, {"$set": {"status": "cancelled"}}))
    _buy(client, "l1")
    assert client.post("/api/billing/cancel").json()["offer"] is None


def test_cancel_member_has_no_offer(client):
    qa_login(client, plan="free")
    _buy(client, "member")
    assert client.post("/api/billing/cancel").json()["offer"] is None


def test_webhook_signature_and_charge(client, mdb):
    qa_login(client, plan="free")
    co = client.post("/api/billing/checkout", json={"plan": "l1"}).json()
    from billing.razorpay_client import FakeRazorpay
    ev = FakeRazorpay().charge_event(co["subscription_id"], 590000)
    body = json.dumps(ev).encode()
    assert client.post("/api/billing/razorpay/webhook", content=body, headers={"X-Razorpay-Signature": "bad"}).status_code == 400
    assert client.post("/api/billing/razorpay/webhook", content=body, headers={"X-Razorpay-Signature": _sig(body)}).status_code == 200
    info = client.get("/api/me/plan").json()
    assert info["plan"] == "l1" and info["source"] == "paid"
    ev2 = json.dumps({"event": "subscription.halted", "payload": {"subscription": {"entity": {"id": co["subscription_id"]}}}}).encode()
    client.post("/api/billing/razorpay/webhook", content=ev2, headers={"X-Razorpay-Signature": _sig(ev2)})
    assert client.get("/api/me/plan").json()["plan"] == "free"


def test_member_usage_is_monthly(client, mdb):
    qa_login(client, plan="member")
    client.post("/api/briefs", json={"company": "Tata Motors"})
    info = client.get("/api/me/plan").json()
    assert info["limits"]["brief"] == {"used": 1, "limit": 4, "once": False}
    u = run(mdb.usage.find_one({"brief": 1}))
    assert u["_id"].endswith(u["month"])
