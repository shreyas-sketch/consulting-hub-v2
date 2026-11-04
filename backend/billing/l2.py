"""L2 Mentorship: switched on by the team, pauses L1, and L1 restarts after 6 months.

start_l2(db, user_id, by)
  1. Claims L2 for the member in one write (users.l2), so a double click or two admins can't start it twice.
     Raises L2AlreadyActive when an L2 still runs.
  2. Writes a plan grant for L2 that ends in L2_DAYS (≈ 6 months).
  3. Pauses every live L1 subscription (Razorpay pause). Each is marked paused_for_l2 with resume_at = grant end.
     An L1 still paused from an earlier L2 (the restart job hadn't run yet) stays paused: its resume_at moves to
     the new end, so it can't restart and charge in the middle of the new L2.
     If Razorpay refuses the pause (some payment methods can't be paused), the L1 is cancelled at the end
     of its current month instead and the member is marked to restart L1 in the app after L2.
  4. A live ₹1,999 plan is cancelled at the end of its period (L2 includes it; after L2 the member moves to L1).
  5. users.l2 = {started_at, ends_at, by, restart_l1}

stop_renewal(): every "stop this subscription renewing" goes through here. It is marked cancelling only after
Razorpay agrees. If Razorpay can't be reached it is flagged cancel_failed (Admin › Users shows it) and
job_resume tries again every hour.

job_resume (hourly): resumes every L1 whose resume_at has passed (never for a disabled or deleted account),
then retries failed cancels. Until it runs, plans.effective_plan already counts that L1 (see plans.BRIDGE_DAYS),
so there's no gap between L2 ending and L1 starting. After a resume, access stays on for PROVISIONAL days until
Razorpay's charge webhook arrives.

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


class L2AlreadyActive(Exception):
    def __init__(self, ends_at=None):
        super().__init__("L2 already active")
        self.ends_at = as_utc(ends_at) if ends_at else None


async def start_l2(db, user_id: str, by: str, now=None) -> dict:
    now = now or utcnow()
    u = await db.users.find_one({"_id": ObjectId(user_id)})
    if not u:
        raise LookupError(user_id)
    ends = now + timedelta(days=L2_DAYS)
    claim = await db.users.update_one(
        {"_id": u["_id"], "$or": [{"l2.ends_at": {"$exists": False}}, {"l2.ends_at": {"$lte": now}}]},
        {"$set": {"l2": {"started_at": now, "ends_at": ends, "by": by, "restart_l1": False}}})
    if claim.modified_count != 1:
        cur = ((await db.users.find_one({"_id": u["_id"]}, {"l2": 1})) or {}).get("l2") or {}
        raise L2AlreadyActive(cur.get("ends_at"))
    await db.plan_grants.insert_one({"user_id": user_id, "plan": "l2", "ends_at": ends, "by": by, "at": now, "kind": "l2"})
    c = build_client()
    paused, pause_failed = 0, False
    async for s in db.subscriptions.find({"user_id": user_id, "status": "paused", "paused_for_l2": True}):
        await db.subscriptions.update_one({"_id": s["_id"]}, {"$set": {"resume_at": ends, "updated_at": now}})
        paused += 1
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
                await stop_renewal(c, db, s, now, ended_for_l2=True)
                pause_failed = True
        else:                                       # ₹1,999 plan: L2 includes it; L1 follows L2
            await stop_renewal(c, db, s, now, ended_for_l2=True)
    restart = pause_failed or paused == 0           # nothing to resume: the app offers L1 checkout when L2 ends
    await db.users.update_one({"_id": u["_id"]}, {"$set": {"l2.restart_l1": restart}})
    await events.track(db, "l2_started", user_id=user_id, props={"l1_paused": paused})
    return {"ends_at": ends.isoformat(), "l1_paused": paused, "restart_l1_in_app": restart}


def _not_started(s: dict) -> bool:
    return s.get("status") in ("created", "authenticated") and not s.get("current_end")


async def stop_renewal(c, db, s: dict, now=None, **marks) -> bool:
    """Stop `s` renewing. Running plans are cancelled at the end of the period already paid; a paused plan or one
    that hasn't started yet is cancelled at once (nothing is running). Returns True when Razorpay agreed.
    `marks` (e.g. ended_for_l2=True, replaced_by=...) are saved either way, so a retry knows why."""
    now = now or utcnow()
    immediate = s.get("status") == "paused" or _not_started(s)
    try:
        if c is None:
            raise RuntimeError("billing off")
        await c.cancel_subscription(s["_id"], at_cycle_end=not immediate)
    except Exception as e:  # noqa: BLE001
        log.warning("could not cancel %s; flagged for retry", s["_id"], exc_info=True)
        await db.subscriptions.update_one({"_id": s["_id"]}, {"$set": {
            "cancel_failed": True, "cancel_error": f"{type(e).__name__}: {e}"[:200], "cancel_tries": int(s.get("cancel_tries") or 0) + 1,
            "updated_at": now, **marks}})
        return False
    upd = {"cancel_at_cycle_end": True, "cancel_failed": False, "updated_at": now, **marks}
    unset = {"cancel_error": ""}
    if immediate:
        upd.update(status="cancelled", paused_for_l2=False)
        unset["resume_at"] = ""
    await db.subscriptions.update_one({"_id": s["_id"]}, {"$set": upd, "$unset": unset})
    return True


async def retry_failed_cancels(db, c=None, now=None) -> dict:
    """Hourly: try again every cancel Razorpay didn't take. One that has ended meanwhile just loses the flag."""
    now = now or utcnow()
    c = c if c is not None else build_client()
    done, still = 0, 0
    async for s in db.subscriptions.find({"cancel_failed": True}):
        if s.get("status") not in (*plans.LIVE_SUB, "paused") or s.get("cancel_at_cycle_end"):
            await db.subscriptions.update_one({"_id": s["_id"]}, {"$set": {"cancel_failed": False}, "$unset": {"cancel_error": ""}})
            continue
        if await stop_renewal(c, db, s, now):
            done += 1
        else:
            still += 1
    return {"cancels_retried": done, "cancels_failing": still}


async def _account_ok(db, user_id: str) -> Optional[dict]:
    try:
        u = await db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:  # noqa: BLE001 — bad id
        return None
    if not u or (u.get("status") or "active") == "revoked":
        return None
    return u


async def resume_due(db, now=None) -> dict:
    now = now or utcnow()
    c = build_client()
    resumed, failed, skipped = 0, 0, 0
    async for s in db.subscriptions.find({"paused_for_l2": True, "status": "paused", "resume_at": {"$lte": now}}):
        u = await _account_ok(db, s["user_id"])
        if u is None:                                # disabled or deleted: never restart their billing
            skipped += 1
            continue
        l2 = u.get("l2") or {}
        if l2.get("ends_at") and as_utc(l2["ends_at"]) > now:
            # A newer L2 runs: keep L1 paused until that one ends.
            await db.subscriptions.update_one({"_id": s["_id"]}, {"$set": {"resume_at": as_utc(l2["ends_at"]), "updated_at": now}})
            skipped += 1
            continue
        try:
            if c is None:
                raise RuntimeError("billing off")
            await c.resume_subscription(s["_id"])
        except Exception as e:  # noqa: BLE001
            log.warning("resume failed for %s", s["_id"], exc_info=True)
            await db.subscriptions.update_one({"_id": s["_id"]}, {"$set": {
                "resume_failed": True, "resume_error": f"{type(e).__name__}: {e}"[:200], "updated_at": now}})
            failed += 1
            continue
        end = now + timedelta(days=31 if getattr(c, "mode", "") == "fake" else PROVISIONAL_DAYS)
        prev = s.get("current_end")
        await db.subscriptions.update_one({"_id": s["_id"]}, {"$set": {
            "status": "active", "paused_for_l2": False, "resumed_at": now, "resume_failed": False,
            "confirmed": getattr(c, "mode", "") == "fake",          # the end is a guess until the charge webhook
            "current_end": max(as_utc(prev), end) if prev else end, "updated_at": now}, "$unset": {"resume_error": ""}})
        await events.track(db, "l1_resumed", user_id=s["user_id"], props={"subscription_id": s["_id"]})
        resumed += 1
    retried = await retry_failed_cancels(db, c, now)
    return {"resumed": resumed, "failed": failed, "skipped": skipped, **retried}


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
