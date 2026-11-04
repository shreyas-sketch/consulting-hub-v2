"""L2 Mentorship: switched on by the team, pauses L1, and L1 restarts after 6 months.

start_l2(db, user_id, by)
  1. Writes a plan grant for L2 that ends in L2_DAYS (≈ 6 months).
  2. Pauses every live L1 subscription (Razorpay pause). Each is marked paused_for_l2 with resume_at = grant end.
     If Razorpay refuses the pause (some payment methods can't be paused), the L1 is cancelled at the end
     of its current month instead and the member is marked to restart L1 in the app after L2.
  3. A live ₹1,999 plan is cancelled at the end of its period (L2 includes it; after L2 the member moves to L1).
  4. users.l2 = {started_at, ends_at, by, restart_l1}

job_resume (daily): resumes every L1 whose resume_at has passed. Access stays on for PROVISIONAL days until
Razorpay's charge webhook arrives, so there's no gap between L2 ending and L1 starting.

L1 payments never count towards L2.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from bson import ObjectId

import plans
from growth import events
from growth.clock import as_utc, utcnow

from .razorpay_client import build_client

log = logging.getLogger("billing.l2")
L2_DAYS = 183
PROVISIONAL_DAYS = 2


async def start_l2(db, user_id: str, by: str, now=None) -> dict:
    now = now or utcnow()
    u = await db.users.find_one({"_id": ObjectId(user_id)})
    if not u:
        raise LookupError(user_id)
    ends = now + timedelta(days=L2_DAYS)
    await db.plan_grants.insert_one({"user_id": user_id, "plan": "l2", "ends_at": ends, "by": by, "at": now, "kind": "l2"})
    c = build_client()
    paused, pause_failed = 0, False
    async for s in db.subscriptions.find({"user_id": user_id, "status": {"$in": plans.LIVE_SUB},
                                          "cancel_at_cycle_end": {"$ne": True}}):
        if s.get("plan") == "l1":
            try:
                if c is None:
                    raise RuntimeError("billing off")
                await c.pause_subscription(s["_id"])
                await db.subscriptions.update_one({"_id": s["_id"]}, {"$set": {
                    "status": "paused", "paused_for_l2": True, "resume_at": ends, "updated_at": now}})
                paused += 1
            except Exception:  # noqa: BLE001
                log.warning("pause failed for %s; cancelling at cycle end instead", s["_id"], exc_info=True)
                await _cancel_at_end(c, db, s, now)
                pause_failed = True
        else:                                       # ₹1,999 plan: L2 includes it; L1 follows L2
            await _cancel_at_end(c, db, s, now)
    restart = pause_failed or paused == 0           # nothing to resume: the app offers L1 checkout when L2 ends
    await db.users.update_one({"_id": u["_id"]}, {"$set": {"l2": {"started_at": now, "ends_at": ends, "by": by,
                                                                    "restart_l1": restart}}})
    await events.track(db, "l2_started", user_id=user_id, props={"l1_paused": paused})
    return {"ends_at": ends.isoformat(), "l1_paused": paused, "restart_l1_in_app": restart}


async def _cancel_at_end(c, db, s: dict, now) -> None:
    try:
        if c is not None:
            await c.cancel_subscription(s["_id"], at_cycle_end=True)
    except Exception:  # noqa: BLE001
        log.warning("could not cancel %s", s["_id"], exc_info=True)
    await db.subscriptions.update_one({"_id": s["_id"]}, {"$set": {"cancel_at_cycle_end": True, "ended_for_l2": True,
                                                                    "updated_at": now}})


async def resume_due(db, now=None) -> dict:
    now = now or utcnow()
    c = build_client()
    resumed, failed = 0, 0
    async for s in db.subscriptions.find({"paused_for_l2": True, "status": "paused", "resume_at": {"$lte": now}}):
        try:
            if c is None:
                raise RuntimeError("billing off")
            await c.resume_subscription(s["_id"])
        except Exception:  # noqa: BLE001
            log.warning("resume failed for %s", s["_id"], exc_info=True)
            failed += 1
            continue
        end = now + timedelta(days=31 if getattr(c, "mode", "") == "fake" else PROVISIONAL_DAYS)
        prev = s.get("current_end")
        await db.subscriptions.update_one({"_id": s["_id"]}, {"$set": {
            "status": "active", "paused_for_l2": False, "resumed_at": now,
            "current_end": max(as_utc(prev), end) if prev else end, "updated_at": now}})
        await events.track(db, "l1_resumed", user_id=s["user_id"], props={"subscription_id": s["_id"]})
        resumed += 1
    return {"resumed": resumed, "failed": failed}


async def job_resume(ctx) -> dict:
    return await resume_due(ctx.db, ctx.now)


def l2_status(user: dict, now: Optional[object] = None) -> Optional[dict]:
    l2 = user.get("l2")
    if not l2:
        return None
    now = now or utcnow()
    ends = as_utc(l2["ends_at"])
    return {"started_at": as_utc(l2["started_at"]).isoformat(), "ends_at": ends.isoformat(),
            "active": ends > now, "restart_l1": bool(l2.get("restart_l1"))}
