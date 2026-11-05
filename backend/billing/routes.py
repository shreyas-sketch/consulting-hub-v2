"""Billing: Razorpay Subscriptions.

subscriptions {_id: sub_id, user_id, plan member|l1, period monthly|yearly,
               status created|authenticated|active|pending|paused|cancelled|halted|completed,
               current_end, cancel_at_cycle_end, starts_at?, payment_id?, last_event_at?,
               paused_for_l2?, resume_at?, cancel_failed?, created_at, updated_at}

POST /api/billing/checkout {plan, period}  → open Razorpay Checkout with subscription_id (fake mode: confirm with /verify)
                                             Not an upgrade (the ₹1,999 offer after cancelling L1, monthly ↔ yearly, the
                                             same plan again after cancelling): the new subscription starts when the
                                             current paid period ends (Razorpay start_at), so no day is paid twice.
POST /api/billing/verify {...}             → once per subscription, only while it is still "created": provisional access
                                             until the webhook confirms (Razorpay's own status/end when it answers,
                                             else 2 days). A plan that starts later becomes "authenticated" instead.
POST /api/billing/cancel                   → cancels at the end of the paid period. Also cancels a plan that hasn't
                                             started yet, or an L1 paused for L2 (both at once: nothing is running).
                                             Cancelling L1 shows the ₹1,999 plan once (users.downsell_offered_at).
POST /api/billing/razorpay/webhook         → subscription.authenticated / activated / charged / resumed / paused /
                                             cancelled / halted / completed. De-duplicated by X-Razorpay-Event-Id;
                                             an event older than the last one applied to that subscription is ignored.

L2 is not bought here: the team sells it and switches it on in Admin (see billing/l2.py).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

import indexes
import plans
from core.deps import user_dep
from core.errors import (
    BadRequest,
    Conflict,
    NotFound,
    ServiceUnavailable,
    UpstreamError,
)
from core.settings import settings
from growth import events
from growth.clock import IST, as_utc, utcnow
from state import db

from .l2 import l2_status, stop_renewal
from .razorpay_client import RazorpayError, build_client

log = logging.getLogger("billing")
router = APIRouter(prefix="/billing", tags=["billing"])
PROVISIONAL_DAYS = 2
PERIOD_DAYS = {"monthly": 31, "yearly": 366}
MIN_DEFER = timedelta(minutes=15)       # the current plan ends sooner than this: start the new one now
ENDED = ("cancelled", "halted", "completed", "expired")

indexes.register("billing_events", [("at", 1)], {"expireAfterSeconds": 60 * 86400})     # webhook ids kept 60 days
indexes.register("subscriptions", [("payment_id", 1)], {"sparse": True})


class CheckoutIn(BaseModel):
    plan: Literal["member", "l1"]
    period: Literal["monthly", "yearly"] = "monthly"


class VerifyIn(BaseModel):
    subscription_id: str = Field(..., max_length=64)
    payment_id: str = Field("", max_length=64)
    signature: str = Field("", max_length=200)


def _client():
    c = build_client()
    if c is None:
        raise ServiceUnavailable("Payments aren't set up yet.", code="billing_off")
    return c


def day(dt: datetime) -> str:
    """4 Dec 2026, in IST."""
    d = as_utc(dt).astimezone(IST)
    return f"{d.day} {d.strftime('%b %Y')}"


def _ts(v) -> Optional[datetime]:
    return datetime.fromtimestamp(v, tz=timezone.utc) if isinstance(v, (int, float)) and v > 0 else None


async def _paid_end(c, s: dict) -> datetime:
    """When this running subscription's paid period really ends. An unconfirmed one (provisional 2 days) asks
    Razorpay, so a plan bought to follow it doesn't start too early."""
    end = as_utc(s["current_end"])
    if not s.get("confirmed"):
        try:
            real = _ts((await c.fetch_subscription(s["_id"])).get("current_end"))
            if real and real > end:
                end = real
        except RazorpayError:
            pass
    return end


@router.post("/checkout")
async def checkout(body: CheckoutIn, user: dict = Depends(user_dep())):
    if (body.plan, body.period) not in plans.PRICES_INR:
        raise BadRequest("L1 is billed monthly.", code="bad_period")
    uid = str(user["_id"])
    now = utcnow()
    ep = await plans.effective_plan(db(), user, now)
    paused = await db().subscriptions.find_one({"user_id": uid, "status": "paused", "paused_for_l2": True})
    if ep["plan"] == "l2":
        st = l2_status(user)
        when = f" on {day(datetime.fromisoformat(st['ends_at']))}" if st else ""
        msg = ("You're on L2. Your L1 is paused and restarts by itself when L2 ends." if paused else
               f"You're on L2, which includes everything. When L2 ends{when}, you can start L1 again here.")
        raise Conflict(msg, code="on_l2")
    if paused:
        raise Conflict("Your L1 is paused for L2 and restarts by itself. To change plans, cancel it from Account first.", code="l1_paused")
    same = await db().subscriptions.find_one({"user_id": uid, "plan": body.plan, "status": {"$in": plans.LIVE_SUB},
                                              "cancel_at_cycle_end": {"$ne": True}, "current_end": {"$gt": utcnow()}})
    if same:
        raise Conflict(f"You're already on {plans.LABELS[body.plan]}.", code="already_on_plan")
    later = await db().subscriptions.find_one({"user_id": uid, "plan": body.plan, "status": "authenticated",
                                               "starts_at": {"$gt": now}, "cancel_at_cycle_end": {"$ne": True}})
    if later:
        raise Conflict(f"Your {plans.LABELS[body.plan]} already starts on {day(later['starts_at'])}.", code="already_on_plan")
    c = _client()
    # Not an upgrade: start when the current paid period ends, so the member never pays twice for the same days.
    running = [s async for s in db().subscriptions.find({"user_id": uid, "status": {"$in": plans.LIVE_SUB},
                                                         "current_end": {"$gt": now}, "plan": {"$in": list(plans.PAID)}})]
    start_at: Optional[datetime] = None
    if running and plans.RANK[body.plan] <= max(plans.RANK[s["plan"]] for s in running):
        end = max([await _paid_end(c, s) for s in running])
        if end - now > MIN_DEFER:
            start_at = end
    try:
        sub = await c.create_subscription(body.plan, body.period, {"user_id": uid, "plan": body.plan, "period": body.period},
                                          start_at=int(start_at.timestamp()) if start_at else None)
    except RazorpayError as e:
        log.warning("checkout failed: %s", e)
        raise UpstreamError("Couldn't start the payment. Try again.", code="checkout_failed")
    await db().subscriptions.insert_one({"_id": sub["id"], "user_id": uid, "plan": body.plan, "period": body.period,
                                         "status": "created", "current_end": None, "cancel_at_cycle_end": False,
                                         "starts_at": start_at, "created_at": now, "updated_at": now})
    await events.track(db(), "checkout_started", user_id=uid, props={"plan": body.plan, "period": body.period,
                                                                     "deferred": bool(start_at)})
    price = plans.PRICES_INR[(body.plan, body.period)]
    total = plans.total_inr(body.plan, body.period)
    desc = f"{plans.LABELS[body.plan]} ({body.period})" + (f", starts {day(start_at)}" if start_at else "")
    return {"mode": c.mode, "subscription_id": sub["id"], "key_id": getattr(c, "key_id", None),
            "amount_inr": total, "price_inr": price, "gst_inr": total - price, "plan": body.plan, "period": body.period,
            "starts_at": start_at.isoformat() if start_at else None,
            "name": settings.brand_name, "description": desc,
            "prefill": {"contact": user.get("phone"), "email": user.get("email")}}


async def _activate(sub_id: str, current_end: datetime, *, paid: bool, amount_inr=None) -> None:
    s = await db().subscriptions.find_one({"_id": sub_id})
    if not s:
        return
    if s.get("paused_for_l2") and s.get("status") == "paused":
        return                                   # a late charge event can't wake an L1 that L2 paused
    prev_end = s.get("current_end")
    end = max(as_utc(prev_end), current_end) if prev_end else current_end
    await db().subscriptions.update_one({"_id": sub_id}, {"$set": {"status": "active", "current_end": end,
                                                                    "updated_at": utcnow(), "confirmed": paid or s.get("confirmed", False)}})
    if paid:
        await events.track(db(), "payment_captured", user_id=s["user_id"], props={"plan": s["plan"], "amount_inr": amount_inr})
    if not s.get("activated_event"):
        await db().subscriptions.update_one({"_id": sub_id}, {"$set": {"activated_event": True}})
        await events.track(db(), "subscription_activated", user_id=s["user_id"],
                           props={"plan": s["plan"], "period": s.get("period") or "monthly"})
        await _end_older_subscriptions(s)


async def _schedule(s: dict, start: datetime) -> None:
    """A plan bought to start later has been authorised: nothing is charged until `start`. The plans it follows
    stop renewing now, so they end exactly when it starts."""
    res = await db().subscriptions.update_one({"_id": s["_id"], "status": "created"}, {"$set": {
        "status": "authenticated", "starts_at": start, "updated_at": utcnow()}})
    if res.modified_count:
        await events.track(db(), "subscription_scheduled", user_id=s["user_id"],
                           props={"plan": s["plan"], "period": s.get("period") or "monthly", "starts_at": start.isoformat()})
        await _end_older_subscriptions(s)


async def _end_older_subscriptions(new: dict) -> None:
    """An upgrade (₹1,999 → L1) or a plan bought to follow the current one starts a second Razorpay subscription.
    Stop the old one renewing, or the member is charged for both. The old one still runs to the end of the
    period already paid. A cancel Razorpay doesn't take is flagged and retried by the hourly job."""
    c = build_client()
    async for old in db().subscriptions.find({"user_id": new["user_id"], "_id": {"$ne": new["_id"]},
                                              "status": {"$in": plans.LIVE_SUB},
                                              "cancel_at_cycle_end": {"$ne": True}}):
        await stop_renewal(c, db(), old, replaced_by=new["_id"])


@router.post("/verify")
async def verify(body: VerifyIn, user: dict = Depends(user_dep())):
    c = _client()
    s = await db().subscriptions.find_one({"_id": body.subscription_id, "user_id": str(user["_id"])})
    if not s:
        raise NotFound("Payment not found.")
    live = c.mode != "fake"
    if live and not c.verify_payment(body.payment_id, body.subscription_id, body.signature):
        raise BadRequest("Payment couldn't be verified.", code="bad_signature")
    used = Conflict("This payment was already used.", code="payment_used")
    pay = (body.payment_id or "").strip() or "none"
    if live and await db().subscriptions.find_one({"payment_id": pay, "_id": {"$ne": s["_id"]}}, {"_id": 1}):
        raise used
    # One verify per subscription: the payment id is stored in the same write that checks none is stored yet,
    # so an old checkout answer can't be sent again to switch a lapsed or cancelled plan back on.
    now = utcnow()
    claim = await db().subscriptions.update_one({"_id": s["_id"], "payment_id": {"$exists": False}},
                                                {"$set": {"payment_id": pay, "verified_at": now}})
    if claim.modified_count != 1:
        raise used
    s = await db().subscriptions.find_one({"_id": s["_id"]})
    if s.get("status") != "created":
        return {"plan": await plans.plan_info(db(), user)}       # the webhook got here first: nothing to change
    period = s.get("period") or "monthly"
    start = as_utc(s["starts_at"]) if s.get("starts_at") else None
    if not live:
        if start and start > now:
            if hasattr(c, "authenticate"):
                c.authenticate(s["_id"])
            await _schedule(s, start)
        else:
            await _activate(s["_id"], now + timedelta(days=PERIOD_DAYS[period]), paid=True,
                            amount_inr=plans.total_inr(s["plan"], period))
        return {"plan": await plans.plan_info(db(), user)}
    try:
        rs = await c.fetch_subscription(s["_id"])                # what Razorpay itself says, when it answers
    except RazorpayError:
        log.warning("verify: could not fetch %s", s["_id"], exc_info=True)
        rs = {}
    st = rs.get("status")
    if st in ENDED:
        await db().subscriptions.update_one({"_id": s["_id"]}, {"$set": {"status": st, "updated_at": now}})
        raise Conflict("This payment didn't start a plan. If money was taken, write to us from Support.", code="not_active")
    rs_start = _ts(rs.get("start_at"))
    if rs_start and rs_start > now and st in ("authenticated", "created", None):
        await _schedule(s, rs_start)
    elif start and start > now and st in ("authenticated", "created", None):
        await _schedule(s, start)
    elif st == "active" and _ts(rs.get("current_end")):
        await _activate(s["_id"], _ts(rs["current_end"]), paid=False)
    else:
        await _activate(s["_id"], now + timedelta(days=PROVISIONAL_DAYS), paid=False)
    return {"plan": await plans.plan_info(db(), user)}


def _downsell_offer(l1_end: Optional[datetime]) -> dict:
    starts = f" It starts on {day(l1_end)}, when your L1 ends." if l1_end else " It starts when your L1 ends."
    return {"plan": "member", "name": plans.LABELS["member"],
            "periods": [{"period": p, "price_inr": plans.PRICES_INR[("member", p)], "total_inr": plans.total_inr("member", p)}
                        for p in ("monthly", "yearly")],
            "starts_at": as_utc(l1_end).isoformat() if l1_end else None,
            "msg": "Keep the tools for ₹1,999 + GST a month, or ₹20,000 + GST a year." + starts +
                   " This offer is shown once."}


@router.post("/cancel")
async def cancel(user: dict = Depends(user_dep())):
    """Cancels, in this order: the running plan (at the end of its paid period), else a plan that starts later,
    else an L1 paused for L2 (the last two at once, since nothing is running)."""
    uid = str(user["_id"])
    d = db()
    kind = "running"
    s = await d.subscriptions.find_one({"user_id": uid, "status": {"$in": ["active", "pending"]},
                                        "cancel_at_cycle_end": {"$ne": True}}, sort=[("current_end", -1)])
    if not s:
        kind = "scheduled"
        s = await d.subscriptions.find_one({"user_id": uid, "status": "authenticated", "starts_at": {"$ne": None},
                                            "current_end": None, "cancel_at_cycle_end": {"$ne": True}})
    if not s:
        kind = "paused"
        s = await d.subscriptions.find_one({"user_id": uid, "status": "paused", "paused_for_l2": True})
    if not s:
        raise NotFound("No active subscription.", code="no_subscription")
    now = utcnow()
    try:
        await _client().cancel_subscription(s["_id"], at_cycle_end=kind == "running")
    except RazorpayError as e:
        log.warning("cancel failed: %s", e)
        raise UpstreamError("Couldn't cancel right now. Try again.", code="cancel_failed")
    await events.track(d, "subscription_cancelled", user_id=uid, props={"plan": s["plan"], "kind": kind})
    if kind != "running":
        await d.subscriptions.update_one({"_id": s["_id"]}, {"$set": {
            "status": "cancelled", "cancel_at_cycle_end": True, "paused_for_l2": False, "updated_at": now},
            "$unset": {"resume_at": ""}})
        return {"status": "cancelled", "kind": kind, "plan": s["plan"], "access_until": None, "offer": None}
    await d.subscriptions.update_one({"_id": s["_id"]}, {"$set": {"cancel_at_cycle_end": True, "updated_at": now}})
    end = s.get("current_end")
    out = {"status": "cancels_at_period_end", "kind": kind, "plan": s["plan"],
           "access_until": as_utc(end).isoformat() if end else None, "offer": None}
    if s["plan"] == "l1":
        # Offered once per account, ever. The atomic update makes a double tap show it only once.
        res = await d.users.update_one({"_id": user["_id"], "downsell_offered_at": None},
                                       {"$set": {"downsell_offered_at": now}})
        if res.modified_count:
            out["offer"] = _downsell_offer(as_utc(end) if end else None)
            await events.track(d, "downsell_offered", user_id=uid)
    return out


async def _in_order(sid: str, ev: dict) -> bool:
    """Razorpay doesn't promise the order of webhooks. Keep the newest `created_at` applied per subscription and
    ignore anything older (a late 'charged' can't undo a 'cancelled' that came after it)."""
    ts = ev.get("created_at")
    if not isinstance(ts, (int, float)) or ts <= 0:
        return True
    res = await db().subscriptions.update_one(
        {"_id": sid, "$or": [{"last_event_at": {"$exists": False}}, {"last_event_at": None}, {"last_event_at": {"$lte": int(ts)}}]},
        {"$set": {"last_event_at": int(ts)}})
    if res.matched_count:
        return True
    return not await db().subscriptions.find_one({"_id": sid}, {"_id": 1})     # unknown subscription: nothing to order


async def _apply(name: str, sid: str, sub: dict, ev: dict) -> None:
    if name == "subscription.authenticated":
        s = await db().subscriptions.find_one({"_id": sid})
        start = _ts(sub.get("start_at"))
        if s and s.get("status") == "created" and start and start > utcnow():
            await _schedule(s, start)
    elif name in ("subscription.activated", "subscription.charged", "subscription.resumed"):
        end_dt = _ts(sub.get("current_end")) or utcnow() + timedelta(days=31)
        pay = ((ev.get("payload") or {}).get("payment") or {}).get("entity") or {}
        if name == "subscription.resumed":
            await db().subscriptions.update_one({"_id": sid, "status": "paused"},
                                                {"$set": {"status": "active", "paused_for_l2": False, "updated_at": utcnow()}})
        await _activate(sid, end_dt, paid=name == "subscription.charged",
                        amount_inr=(pay.get("amount") or 0) / 100 if pay else None)
    elif name in ("subscription.cancelled", "subscription.halted", "subscription.completed", "subscription.paused"):
        await db().subscriptions.update_one({"_id": sid}, {"$set": {"status": name.split(".")[1], "updated_at": utcnow()}})


@router.post("/razorpay/webhook")
async def webhook(request: Request):
    c = build_client()
    raw = await request.body()
    if c is None or not c.verify_webhook(raw, request.headers.get("X-Razorpay-Signature", "")):
        raise BadRequest("bad signature", code="bad_signature")
    ev = json.loads(raw or b"{}")
    name = ev.get("event", "")
    sub = ((ev.get("payload") or {}).get("subscription") or {}).get("entity") or {}
    sid = sub.get("id")
    if not sid:
        return {"ok": True}
    # Razorpay retries a webhook until it gets a 2xx, so the same event can arrive twice: keep each id once.
    event_id = (request.headers.get("X-Razorpay-Event-Id") or "").strip()[:100]
    if event_id:
        try:
            await db().billing_events.insert_one({"_id": event_id, "event": name, "sid": sid, "at": utcnow()})
        except DuplicateKeyError:
            return {"ok": True, "duplicate": True}
    try:
        if not await _in_order(sid, ev):
            log.info("ignored out-of-order %s for %s", name, sid)
            return {"ok": True, "stale": True}
        await _apply(name, sid, sub, ev)
    except Exception:
        if event_id:                              # let Razorpay's retry run it again
            await db().billing_events.delete_one({"_id": event_id})
        raise
    return {"ok": True}
