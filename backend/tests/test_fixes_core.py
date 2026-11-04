"""Regression tests for the pre-launch review (billing, L2, plans, auth, jobs, admin).

Each test is the reviewer's confirming test turned around: it now checks the fixed behaviour.
"""
import asyncio
import hashlib
import hmac
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from conftest import login, qa_login, run

import plans
from billing import l2
from billing.razorpay_client import FakeRazorpay, RazorpayError, hmac_hex
from growth.clock import utcnow


def _sig(body: bytes) -> str:
    return hmac.new(b"fake_webhook_secret", body, hashlib.sha256).hexdigest()


def _hook(client, ev: dict, event_id: str = None):
    body = json.dumps(ev).encode()
    h = {"X-Razorpay-Signature": _sig(body)}
    if event_id:
        h["X-Razorpay-Event-Id"] = event_id
    return client.post("/api/billing/razorpay/webhook", content=body, headers=h)


def _l1(client, phone):
    u = login(client, phone=phone)["user"]
    co = client.post("/api/billing/checkout", json={"plan": "l1"}).json()
    assert client.post("/api/billing/verify", json={"subscription_id": co["subscription_id"]}).status_code == 200
    return u, co["subscription_id"]


def _as_admin(client):
    client.post("/api/auth/logout")
    qa_login(client, role="admin")


class LiveishRazorpay(FakeRazorpay):
    """The fake, but /verify treats it as live (signature required, status fetched)."""
    mode = "live"


# ---------------------------------------------------------------- 1. /verify replay ----
def test_verify_replay_cannot_reactivate_cancelled_subscription(client, mdb, monkeypatch):
    import billing.routes as br
    monkeypatch.setattr(br, "build_client", lambda: LiveishRazorpay())
    login(client, phone="9876500001")
    sid = client.post("/api/billing/checkout", json={"plan": "l1"}).json()["subscription_id"]
    pay = "pay_abc123"
    sig = hmac_hex("fake_secret", f"{pay}|{sid}".encode())
    body = {"subscription_id": sid, "payment_id": pay, "signature": sig}
    r = client.post("/api/billing/verify", json=body)
    assert r.status_code == 200 and r.json()["plan"]["plan"] == "l1"
    assert run(mdb.subscriptions.find_one({"_id": sid}))["payment_id"] == pay
    # the paid period ends and the subscription is cancelled
    assert _hook(client, {"event": "subscription.cancelled", "payload": {"subscription": {"entity": {"id": sid}}}}).status_code == 200
    run(mdb.subscriptions.update_one({"_id": sid}, {"$set": {"current_end": utcnow() - timedelta(days=1)}}))
    assert client.get("/api/me/plan").json()["plan"] == "free"
    # replaying the old checkout answer is refused and changes nothing
    r = client.post("/api/billing/verify", json=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "payment_used"
    assert client.get("/api/me/plan").json()["plan"] == "free"
    assert run(mdb.subscriptions.find_one({"_id": sid}))["status"] == "cancelled"


def test_verify_only_acts_on_created_and_uses_real_end(client, mdb, monkeypatch):
    import billing.routes as br
    monkeypatch.setattr(br, "build_client", lambda: LiveishRazorpay())
    login(client, phone="9876500011")
    # Razorpay already says active with its own period end: that end is used, not a 2-day guess.
    sid = client.post("/api/billing/checkout", json={"plan": "l1"}).json()["subscription_id"]
    real_end = int((utcnow() + timedelta(days=30)).timestamp())
    FakeRazorpay.subs[sid].update(status="active", current_end=real_end)
    pay = "pay_real1"
    r = client.post("/api/billing/verify", json={"subscription_id": sid, "payment_id": pay,
                                                  "signature": hmac_hex("fake_secret", f"{pay}|{sid}".encode())})
    assert r.status_code == 200
    s = run(mdb.subscriptions.find_one({"_id": sid}))
    assert s["status"] == "active" and int(s["current_end"].replace(tzinfo=timezone.utc).timestamp()) == real_end
    # A first verify on a subscription the webhooks already ended does not switch it back on.
    run(mdb.subscriptions.update_many({}, {"$set": {"status": "cancelled", "current_end": utcnow() - timedelta(days=1)}}))
    sid2 = client.post("/api/billing/checkout", json={"plan": "l1"}).json()["subscription_id"]
    run(mdb.subscriptions.update_one({"_id": sid2}, {"$set": {"status": "halted"}}))
    pay2 = "pay_real2"
    r = client.post("/api/billing/verify", json={"subscription_id": sid2, "payment_id": pay2,
                                                  "signature": hmac_hex("fake_secret", f"{pay2}|{sid2}".encode())})
    assert r.status_code == 200 and r.json()["plan"]["plan"] == "free"
    assert run(mdb.subscriptions.find_one({"_id": sid2}))["status"] == "halted"


# ---------------------------------------------------------------- 2. second L2 / double click ----
def test_second_start_l2_is_refused_atomically(client, mdb):
    u, _ = _l1(client, "9876500006")
    r1 = run(l2.start_l2(mdb, u["id"], by="a"))
    with pytest.raises(l2.L2AlreadyActive):
        run(l2.start_l2(mdb, u["id"], by="a", now=utcnow() + timedelta(seconds=5)))   # double click past the 409 check
    assert r1["restart_l1_in_app"] is False
    user = run(mdb.users.find_one({"phone": "+919876500006"}))
    assert user["l2"]["restart_l1"] is False
    assert run(mdb.plan_grants.count_documents({"user_id": u["id"], "plan": "l2"})) == 1
    _as_admin(client)
    r = client.post(f"/api/admin/users/{u['id']}/start-l2")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "already_l2"


def test_l2_renewed_before_resume_job_keeps_l1_paused(client, mdb):
    u, sid = _l1(client, "9876500007")
    t0 = utcnow() - timedelta(days=l2.L2_DAYS + 1)
    run(l2.start_l2(mdb, u["id"], by="a", now=t0))                 # first L2, ended yesterday
    assert run(mdb.subscriptions.find_one({"_id": sid}))["status"] == "paused"
    _as_admin(client)
    r = client.post(f"/api/admin/users/{u['id']}/start-l2")        # second L2 before the restart job ran
    assert r.status_code == 200
    res = r.json()["result"]
    assert res["l1_paused"] == 1 and res["restart_l1_in_app"] is False
    s = run(mdb.subscriptions.find_one({"_id": sid}))
    assert s["status"] == "paused" and abs((s["resume_at"].replace(tzinfo=timezone.utc) - datetime.fromisoformat(res["ends_at"])).total_seconds()) < 1
    out = run(l2.resume_due(mdb))
    assert out["resumed"] == 0
    assert FakeRazorpay.subs[sid]["status"] == "paused"


# ---------------------------------------------------------------- 3. gap after L2 ----
def test_gap_after_l2_keeps_l1_and_blocks_second_l1(client, mdb):
    u, sid = _l1(client, "9876500003")
    _as_admin(client)
    client.post(f"/api/admin/users/{u['id']}/start-l2")
    client.post("/api/auth/logout")
    # L2 ended an hour ago, the restart job hasn't run yet
    hour_ago = utcnow() - timedelta(hours=1)
    run(mdb.plan_grants.update_many({"user_id": u["id"], "plan": "l2"}, {"$set": {"ends_at": hour_ago}}))
    run(mdb.subscriptions.update_one({"_id": sid}, {"$set": {"resume_at": hour_ago}}))
    run(mdb.users.update_one({"phone": "+919876500003"}, {"$set": {"l2.ends_at": hour_ago}}))
    qa_login(client, phone="9876500003")
    assert client.get("/api/me/plan").json()["plan"] == "l1"       # no drop to free
    co2 = client.post("/api/billing/checkout", json={"plan": "l1"})
    assert co2.status_code == 409 and co2.json()["detail"]["code"] == "l1_paused"
    assert run(l2.resume_due(mdb))["resumed"] == 1
    subs = run(mdb.subscriptions.find({"user_id": u["id"], "plan": "l1"}).to_list(10))
    assert len(subs) == 1 and subs[0]["status"] == "active"


def test_l2_resume_runs_hourly():
    from jobs import registry
    assert registry.JOBS["l2_resume"][1] == ("every", 60)


def test_on_l2_message_matches_restart(client, mdb):
    u, _ = _l1(client, "9876500033")
    FakeRazorpay.fail_pause = True                                 # L1 is cancelled, member restarts it in the app
    _as_admin(client)
    client.post(f"/api/admin/users/{u['id']}/start-l2")
    qa_login(client, phone="9876500033")
    d = client.post("/api/billing/checkout", json={"plan": "l1"}).json()["detail"]
    assert d["code"] == "on_l2" and "by itself" not in d["msg"] and "start L1 again here" in d["msg"]
    u2, _ = _l1(client, "9876500034")                              # pause works: L1 really restarts by itself
    _as_admin(client)
    FakeRazorpay.fail_pause = False
    client.post(f"/api/admin/users/{u2['id']}/start-l2")
    qa_login(client, phone="9876500034")
    d = client.post("/api/billing/checkout", json={"plan": "l1"}).json()["detail"]
    assert d["code"] == "on_l2" and "restarts by itself" in d["msg"]


# ---------------------------------------------------------------- 4. failed cancel isn't "cancelling" ----
def test_start_l2_cancel_failure_flagged_and_retried(client, mdb, monkeypatch):
    u, sid = _l1(client, "9876500005")
    FakeRazorpay.fail_pause = True
    real_cancel = FakeRazorpay.cancel_subscription

    async def boom(self, sub_id, at_cycle_end=True):
        raise RazorpayError("timeout")
    monkeypatch.setattr(FakeRazorpay, "cancel_subscription", boom)
    _as_admin(client)
    d = client.post(f"/api/admin/users/{u['id']}/start-l2").json()
    s = run(mdb.subscriptions.find_one({"_id": sid}))
    assert s.get("cancel_at_cycle_end") is not True and s["cancel_failed"] is True and s["ended_for_l2"] is True
    assert any(x["id"] == sid and x["cancel_failed"] for x in d["subscriptions"])     # admin sees it
    monkeypatch.setattr(FakeRazorpay, "cancel_subscription", real_cancel)
    out = run(l2.resume_due(mdb))                                  # the hourly job tries again
    assert out["cancels_retried"] == 1
    s = run(mdb.subscriptions.find_one({"_id": sid}))
    assert s["cancel_at_cycle_end"] is True and s["cancel_failed"] is False
    assert FakeRazorpay.subs[sid]["cancel_at_cycle_end"] is True


# ---------------------------------------------------------------- 5. revoke stops billing ----
def test_revoke_stops_billing_and_resume_skips_revoked(client, mdb):
    u, sid = _l1(client, "9876500002")
    _as_admin(client)
    client.post(f"/api/admin/users/{u['id']}/start-l2")
    r = client.post(f"/api/admin/users/{u['id']}/status", json={"status": "revoked"})
    assert r.status_code == 200 and r.json()["billing"] == {"stopped": 1, "failed": 0}
    assert FakeRazorpay.subs[sid]["status"] == "cancelled"
    out = run(l2.resume_due(mdb, utcnow() + timedelta(days=l2.L2_DAYS + 1)))
    assert out["resumed"] == 0
    assert FakeRazorpay.subs[sid]["status"] == "cancelled"


def test_resume_due_skips_revoked_even_if_cancel_failed(client, mdb, monkeypatch):
    u, sid = _l1(client, "9876500012")
    _as_admin(client)
    client.post(f"/api/admin/users/{u['id']}/start-l2")

    async def boom(self, sub_id, at_cycle_end=True):
        raise RazorpayError("down")
    monkeypatch.setattr(FakeRazorpay, "cancel_subscription", boom)
    r = client.post(f"/api/admin/users/{u['id']}/status", json={"status": "revoked"})
    assert r.json()["billing"] == {"stopped": 0, "failed": 1}
    out = run(l2.resume_due(mdb, utcnow() + timedelta(days=l2.L2_DAYS + 1)))
    assert out["resumed"] == 0 and out["skipped"] == 1
    assert FakeRazorpay.subs[sid]["status"] == "paused"


# ---------------------------------------------------------------- 6. client IP + OTP global cap ----
def _req(headers: dict, host="5.6.7.8"):
    from starlette.requests import Request
    return Request({"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                    "client": (host, 1234)})


def test_client_ip_trusts_only_proxy_added_entries(monkeypatch):
    from accounts.routes import client_ip
    monkeypatch.delenv("BEHIND_CLOUDFLARE", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    assert client_ip(_req({"x-forwarded-for": "9.9.9.9, 1.2.3.4"})) == "1.2.3.4"      # rightmost = added by the edge
    assert client_ip(_req({"cf-connecting-ip": "9.9.9.9"})) == "5.6.7.8"             # ignored without Cloudflare
    assert client_ip(_req({})) == "5.6.7.8"
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
    assert client_ip(_req({"x-forwarded-for": "9.9.9.9, 1.2.3.4, 10.0.0.1"})) == "1.2.3.4"
    assert client_ip(_req({"x-forwarded-for": "1.2.3.4"})) == "1.2.3.4"
    monkeypatch.setenv("BEHIND_CLOUDFLARE", "true")
    assert client_ip(_req({"cf-connecting-ip": "8.8.4.4", "x-forwarded-for": "1.1.1.1"})) == "8.8.4.4"


def test_spoofed_ip_header_does_not_bypass_public_rate_limit(client):
    qa_login(client, plan="l2")
    x = client.post("/api/diagnostic", json={"topic": "Sales engine"}).json()
    p = client.post(f"/api/diagnostic/{x['id']}/publish").json()
    client.post("/api/auth/logout")
    form = client.get(f"/api/diagnostic/public/{p['public_id']}").json()
    ans = {q["id"]: (4 if q["kind"] == "scale" else "x") for q in form["questions"]}
    url = f"/api/diagnostic/public/{p['public_id']}/responses"
    codes = [client.post(url, json={"name": "Bot Bot", "phone": "9876543210", "answers": ans},
                         headers={"cf-connecting-ip": f"1.2.3.{i}", "x-forwarded-for": f"7.7.7.{i}, 4.4.4.4"}).status_code
             for i in range(25)]
    assert codes.count(200) <= 10 and 429 in codes                 # limit is 10/hour per IP


def test_otp_global_cap_per_minute(mdb, monkeypatch):
    from accounts import otp_service
    monkeypatch.setenv("OTP_MAX_PER_MINUTE", "2")
    now = datetime(2026, 11, 5, 10, 0, 20, tzinfo=timezone.utc)

    async def go():
        await otp_service._check_limits(mdb, "+919800000001", "1.1.1.1", now)
        await otp_service._check_limits(mdb, "+919800000002", "1.1.1.2", now)
        with pytest.raises(otp_service.OtpError) as e:
            await otp_service._check_limits(mdb, "+919800000003", "1.1.1.3", now)
        assert e.value.code == "busy" and e.value.status == 429 and e.value.extra["retry_in"] == 40
        await otp_service._check_limits(mdb, "+919800000003", "1.1.1.3", now + timedelta(minutes=1))   # next minute
    run(go())
    assert otp_service.DEFAULT_MAX_PER_MINUTE == 1200


# ---------------------------------------------------------------- 7. metering is atomic ----
class SlowDb:
    """Yields to the loop on every usage call, like a real network round-trip."""
    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        coll = getattr(self._db, name)
        if name != "usage":
            return coll

        class C:
            def __getattr__(self, k):
                fn = getattr(coll, k)

                async def slow(*a, **kw):
                    await asyncio.sleep(0)
                    r = await fn(*a, **kw)
                    await asyncio.sleep(0)
                    return r
                return slow
        return C()

    def __getitem__(self, k):
        return self._db[k]


def test_consume_race_free_gets_one_go(mdb):
    async def go():
        user = {"_id": "u1", "role": "user"}
        res = await asyncio.gather(*(plans.consume(SlowDb(mdb), user, "brief", "free") for _ in range(5)),
                                   return_exceptions=True)
        ok = [r for r in res if not isinstance(r, Exception)]
        assert all(getattr(r, "status_code", None) == 402 for r in res if isinstance(r, Exception))
        doc = await mdb.usage.find_one({"_id": "u1:life"})
        return len(ok), doc["brief"]
    assert run(go()) == (1, 1)


def test_consume_race_paid_limit_holds(mdb):
    async def go():
        user = {"_id": "u2", "role": "user"}
        res = await asyncio.gather(*(plans.consume(SlowDb(mdb), user, "brief", "member") for _ in range(7)),
                                   return_exceptions=True)
        ok = sorted(r["used"] for r in res if not isinstance(r, Exception))
        doc = await mdb.usage.find_one({"_id": plans.usage_key("u2", "member")})
        return ok, doc["brief"]
    assert run(go()) == ([1, 2, 3, 4], 4)


def test_free_double_submit_gets_one_go(mdb):
    from bson import ObjectId
    from features import common
    uid = ObjectId()
    user = {"_id": uid, "role": "user", "name": "X"}
    calls = []

    async def work(plan):
        calls.append(plan)
        return {"ok": True}

    async def go():
        d = SlowDb(mdb)
        res = await asyncio.gather(common.run_metered(d, user, "readiness", work),
                                   common.run_metered(d, user, "readiness", work), return_exceptions=True)
        return res, await mdb.usage.find_one({"_id": f"{uid}:life"})
    res, doc = run(go())
    assert len(calls) == 1 and doc["readiness"] == 1
    assert sum(1 for r in res if getattr(r, "status_code", None) == 402) == 1


def test_refund_still_correct(mdb):
    async def go():
        user = {"_id": "u3", "role": "user"}
        await plans.consume(mdb, user, "brief", "member")
        await plans.refund(mdb, user, "brief", "member")
        await plans.refund(mdb, user, "brief", "member")             # never below zero
        doc = await mdb.usage.find_one({"_id": plans.usage_key("u3", "member")})
        again = await plans.consume(mdb, user, "brief", "member")
        return doc["brief"], again["used"]
    assert run(go()) == (0, 1)


def test_cap_lock_serialises_count_and_insert(mdb):
    async def go():
        user = {"_id": "u4"}

        async def add():
            async with plans.cap_lock(mdb, user, "docs"):
                n = await mdb.docs_t.count_documents({"user_id": "u4"})
                await asyncio.sleep(0.01)
                if n >= 2:
                    return False
                await mdb.docs_t.insert_one({"user_id": "u4"})
                return True
        res = await asyncio.gather(*(add() for _ in range(5)))
        return sum(res), await mdb.docs_t.count_documents({"user_id": "u4"})
    assert run(go()) == (2, 2)


# ---------------------------------------------------------------- 8. cancel a paused L1 ----
def test_paused_l1_can_be_cancelled_during_l2(client, mdb):
    u, sid = _l1(client, "9876500004")
    _as_admin(client)
    client.post(f"/api/admin/users/{u['id']}/start-l2")
    qa_login(client, phone="9876500004")
    assert client.get("/api/me/plan").json()["paused_for_l2"] is True
    r = client.post("/api/billing/cancel")
    assert r.status_code == 200 and r.json()["kind"] == "paused" and r.json()["offer"] is None
    s = run(mdb.subscriptions.find_one({"_id": sid}))
    assert s["status"] == "cancelled" and "resume_at" not in s and s["paused_for_l2"] is False
    assert FakeRazorpay.subs[sid]["status"] == "cancelled"
    info = client.get("/api/me/plan").json()
    assert info["plan"] == "l2" and info["paused_for_l2"] is False
    assert run(l2.resume_due(mdb, utcnow() + timedelta(days=l2.L2_DAYS + 1)))["resumed"] == 0


# ---------------------------------------------------------------- 9. seed_admin ----
def test_member_email_not_promoted_by_seed_admin(client, mdb, monkeypatch):
    from auth import seed_admin
    u = qa_login(client)["user"]
    assert client.patch("/api/auth/profile", json={"email": "founder@akshatdani.com"}).status_code == 200
    monkeypatch.setenv("ADMIN_EMAIL", "founder@akshatdani.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-pass-123")
    run(seed_admin(mdb))
    from bson import ObjectId
    doc = run(mdb.users.find_one({"_id": ObjectId(u["id"])}))
    assert doc["role"] == "user" and "password_hash" not in doc
    assert client.get("/api/admin/pulse").status_code == 403


def test_member_cannot_take_admin_email(client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "founder@akshatdani.com")
    qa_login(client)
    r = client.patch("/api/auth/profile", json={"email": "Founder@akshatdani.com"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "email_taken"


# ---------------------------------------------------------------- 10. plans that follow start later ----
def test_downsell_starts_when_l1_ends(client, mdb):
    login(client, phone="9876500020")
    co = client.post("/api/billing/checkout", json={"plan": "l1"}).json()
    client.post("/api/billing/verify", json={"subscription_id": co["subscription_id"]})
    l1_end = run(mdb.subscriptions.find_one({"_id": co["subscription_id"]}))["current_end"].replace(tzinfo=timezone.utc)
    c = client.post("/api/billing/cancel").json()
    assert c["offer"]["starts_at"] == l1_end.isoformat() and "It starts on" in c["offer"]["msg"]
    m = client.post("/api/billing/checkout", json={"plan": "member", "period": "monthly"}).json()
    assert m["starts_at"] == l1_end.isoformat()
    assert FakeRazorpay.subs[m["subscription_id"]]["start_at"] == int(l1_end.timestamp())
    v = client.post("/api/billing/verify", json={"subscription_id": m["subscription_id"]}).json()["plan"]
    assert v["plan"] == "l1" and v["scheduled"]["plan"] == "member" and v["scheduled"]["starts_at"] == l1_end.isoformat()
    s = run(mdb.subscriptions.find_one({"_id": m["subscription_id"]}))
    assert s["status"] == "authenticated" and s["current_end"] is None
    uid = s["user_id"]
    assert run(mdb.events.count_documents({"name": "payment_captured", "user_id": uid, "props.plan": "member"})) == 0
    user = run(mdb.users.find_one({"phone": "+919876500020"}))
    after = l1_end + timedelta(hours=1)                            # L1 has ended; the first charge is on its way
    assert run(plans.effective_plan(mdb, user, after))["plan"] == "member"
    ev = FakeRazorpay().charge_event(m["subscription_id"], 235900, now=after.timestamp())
    assert _hook(client, ev).status_code == 200
    s = run(mdb.subscriptions.find_one({"_id": m["subscription_id"]}))
    assert s["status"] == "active" and s["current_end"] is not None


def test_period_switch_starts_when_paid_period_ends(client, mdb):
    qa_login(client, plan="free")
    co = client.post("/api/billing/checkout", json={"plan": "member", "period": "monthly"}).json()
    client.post("/api/billing/verify", json={"subscription_id": co["subscription_id"]})
    end = run(mdb.subscriptions.find_one({"_id": co["subscription_id"]}))["current_end"].replace(tzinfo=timezone.utc)
    client.post("/api/billing/cancel")
    y = client.post("/api/billing/checkout", json={"plan": "member", "period": "yearly"}).json()
    assert y["starts_at"] == end.isoformat()
    again = client.post("/api/billing/verify", json={"subscription_id": y["subscription_id"]}).json()["plan"]
    assert again["period"] == "monthly" and again["scheduled"]["period"] == "yearly"
    r = client.post("/api/billing/checkout", json={"plan": "member", "period": "yearly"})
    assert r.status_code == 409 and "starts on" in r.json()["detail"]["msg"]
    # the scheduled plan can be cancelled before it starts
    c = client.post("/api/billing/cancel").json()
    assert c["kind"] == "scheduled" and FakeRazorpay.subs[y["subscription_id"]]["status"] == "cancelled"


def test_upgrade_still_starts_now(client, mdb):
    qa_login(client, plan="free")
    co = client.post("/api/billing/checkout", json={"plan": "member"}).json()
    client.post("/api/billing/verify", json={"subscription_id": co["subscription_id"]})
    up = client.post("/api/billing/checkout", json={"plan": "l1"}).json()
    assert up["starts_at"] is None and FakeRazorpay.subs[up["subscription_id"]]["start_at"] is None


# ---------------------------------------------------------------- 11. failed jobs retry ----
def test_failed_job_retries_with_backoff(mdb, monkeypatch):
    import sys
    import types

    from jobs import registry
    state = {"fail": True}

    async def job(ctx):
        if state["fail"]:
            raise RuntimeError("AI busy")
        return {"ok": 1}
    m = types.ModuleType("tests_fix_x")
    m.job = job
    sys.modules["tests_fix_x"] = m
    monkeypatch.setattr(registry, "JOBS", {"x_weekly": ("x", ("weekly", 2, 6, 30), "tests_fix_x:job")})
    t = datetime(2026, 11, 4, 1, 30, tzinfo=timezone.utc)          # Wed 07:00 IST, slot Wed 06:30 IST
    assert run(registry.due(mdb, t)) == ["x_weekly"]
    run(registry.tick(mdb, t))
    assert run(registry.due(mdb, t + timedelta(minutes=5))) == []         # backing off
    for i in range(1, 4):                                                 # tries 2..4
        assert run(registry.due(mdb, t + timedelta(minutes=16 * i))) == ["x_weekly"]
        run(registry.tick(mdb, t + timedelta(minutes=16 * i)))
    assert run(mdb.job_runs.count_documents({"name": "x_weekly", "ok": False})) == 4
    assert run(registry.due(mdb, t + timedelta(hours=3))) == []           # gave up on this slot
    assert run(registry.due(mdb, t + timedelta(days=7))) == ["x_weekly"]  # next week's slot


def test_ok_run_counts_as_done_after_a_failure(mdb, monkeypatch):
    import sys
    import types

    from jobs import registry
    state = {"fail": True}

    async def job(ctx):
        if state["fail"]:
            raise RuntimeError("x")
        return {"ok": 1}
    m = types.ModuleType("tests_fix_y")
    m.job = job
    sys.modules["tests_fix_y"] = m
    monkeypatch.setattr(registry, "JOBS", {"y_daily": ("y", ("daily", 6, 0), "tests_fix_y:job")})
    t = datetime(2026, 11, 4, 1, 0, tzinfo=timezone.utc)
    run(registry.tick(mdb, t))
    state["fail"] = False
    assert run(registry.tick(mdb, t + timedelta(minutes=20))) == {"y_daily": True}
    assert run(registry.due(mdb, t + timedelta(minutes=40))) == []


# ---------------------------------------------------------------- 13. limit with nothing higher ----
def test_limit_without_higher_plan_has_no_upgrade(mdb):
    async def hit(plan, feature, used):
        user = {"_id": f"lim-{plan}-{feature}"}
        await mdb.usage.insert_one({"_id": plans.usage_key(user["_id"], plan), feature: used})
        try:
            await plans.consume(mdb, user, feature, plan)
        except Exception as e:  # noqa: BLE001
            return e.detail
        raise AssertionError("no limit")
    l1 = run(hit("l1", "akshat_ai", 30))
    assert l1["plan_needed"] is None and "resets on the 1st" in l1["msg"]
    l2d = run(hit("l2", "proposal", 20))
    assert l2d["plan_needed"] is None
    same = run(hit("member", "readiness", 1))                      # L1 gives no more Readiness Scores
    assert same["plan_needed"] is None and "resets on the 1st" in same["msg"]
    more = run(hit("member", "brief", 4))
    assert more["plan_needed"] == "l1" and "L1 gives you more" in more["msg"]
    free = run(hit("free", "brief", 1))
    assert free["plan_needed"] == "member"


# ---------------------------------------------------------------- 14. webhook de-dup + order ----
def test_webhook_deduplicated_by_event_id(client, mdb):
    qa_login(client, plan="free")
    sid = client.post("/api/billing/checkout", json={"plan": "l1"}).json()["subscription_id"]
    ev = FakeRazorpay().charge_event(sid, 590000)
    assert _hook(client, ev, "evt_1").json() == {"ok": True}
    assert _hook(client, ev, "evt_1").json()["duplicate"] is True
    assert run(mdb.events.count_documents({"name": "payment_captured"})) == 1


def test_webhook_older_event_ignored(client, mdb):
    qa_login(client, plan="free")
    sid = client.post("/api/billing/checkout", json={"plan": "l1"}).json()["subscription_id"]
    t = utcnow().timestamp()
    cancel = {"event": "subscription.cancelled", "payload": {"subscription": {"entity": {"id": sid}}}, "created_at": int(t)}
    charge = FakeRazorpay().charge_event(sid, 590000, now=t - 600)  # sent before the cancel, arrives after it
    assert _hook(client, cancel, "evt_a").status_code == 200
    assert _hook(client, charge, "evt_b").json()["stale"] is True
    assert run(mdb.subscriptions.find_one({"_id": sid}))["status"] == "cancelled"
    assert client.get("/api/me/plan").json()["plan"] == "free"


# ---------------------------------------------------------------- 15. Run now takes the job lock ----
def test_run_now_respects_job_lock(client, mdb):
    from jobs.registry import claim_lock, release_lock
    qa_login(client, role="admin")
    assert run(claim_lock(mdb, "l2_resume", owner="worker-1"))
    r = client.post("/api/admin/jobs/l2_resume/run")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "job_running"
    run(release_lock(mdb, "l2_resume", owner="worker-1"))
    assert client.post("/api/admin/jobs/l2_resume/run").json()["ok"] is True
    assert client.post("/api/admin/jobs/l2_resume/run").status_code == 200     # released after each run


# ---------------------------------------------------------------- 16. CSV formula injection ----
def test_group_session_csv_escapes_formulas(client, mdb):
    from admin.routes import csv_safe
    from growth.clock import IST
    assert [csv_safe(v) for v in ("=1+1", "+cmd", "-2+3", "@x", "\t=x", "\r=x", "Asha", "+919876543210", "-2", 5, "")] == \
        ["'=1+1", "'+cmd", "'-2+3", "'@x", "'\t=x", "'\r=x", "Asha", "+919876543210", "-2", 5, ""]
    login(client, phone="9876500040", name='=HYPERLINK("http://x.example","click")')
    _as_admin(client)
    t = utcnow().astimezone(IST).date().isoformat()
    text = client.get(f"/api/admin/webinar/group-session.csv?start={t}&end={t}").text
    assert "'=HYPERLINK" in text and "+919876500040" in text and "'+919876500040" not in text


# ---------------------------------------------------------------- 17. staff lockout + bcrypt off the loop ----
def test_staff_lockout_counts_atomically(mdb):
    import auth
    auth.bind_db(mdb)

    async def go():
        res = await asyncio.gather(*(auth._count_attempt("x@example.com") for _ in range(12)))
        return sum(res)
    assert run(go()) == auth.LOCKOUT_MAX_ATTEMPTS


def test_staff_login_checks_password_off_the_event_loop(mdb, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "staff2@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret-pass")
    import auth
    import server
    from fastapi.testclient import TestClient
    seen = []
    real = auth.verify_password

    def spy(p, h):
        seen.append(threading.current_thread().name)
        return real(p, h)
    monkeypatch.setattr(auth, "verify_password", spy)
    app = server.create_app(mdb, start_jobs=False, seed=False, serve_spa=False)
    with TestClient(app) as c:
        for _ in range(auth.LOCKOUT_MAX_ATTEMPTS):
            assert c.post("/api/auth/staff/login", json={"email": "staff2@example.com", "password": "nope"}).status_code == 401
        r = c.post("/api/auth/staff/login", json={"email": "staff2@example.com", "password": "s3cret-pass"})
        assert r.status_code == 429                                 # 6th try inside the window
    assert seen and all(n != "MainThread" for n in seen)
