"""Plans, feature access and limits.

    free    — the account opened on the ₹99 webinar. Each webinar tool once, then view-only.
    member  — the ₹1,999 plan (₹1,999 + GST a month, or ₹20,000 + GST a year).
    l1      — ₹5,000 + GST a month, with the 4-3-2-1 action program inside it.
    l2      — the 6-month mentorship (₹1.5L, sold by the team, switched on in Admin). L1 pauses during L2.

Effective plan = the highest of: an active paid subscription, an admin grant, admin role (= l2).
There is no free trial: the webinar is the trial.

Limits reset on the 1st of each IST month:
    usage {_id: "<uid>:<YYYY-MM>", user_id, month, <feature>: n}
Free accounts count once for life instead:
    usage {_id: "<uid>:life", user_id, <feature>: n}

`require()` raises 403 {code: locked}; `consume()` raises 402 {code: limit}.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException

from growth import events
from growth.clock import as_utc, ist_month_key, utcnow

PLANS = ("free", "member", "l1", "l2")
RANK = {"free": 0, "member": 1, "l1": 2, "l2": 3}
LABELS = {"free": "Free account", "member": "₹1,999 plan", "l1": "L1", "l2": "L2 Mentorship"}
GST_PCT = 18

# (plan, period) → list price before GST
PRICES_INR: dict[tuple[str, str], int] = {("member", "monthly"): 1999, ("member", "yearly"): 20000, ("l1", "monthly"): 5000}
PAID = {"member", "l1"}                       # bought in the app; l2 is switched on by the team


def total_inr(plan: str, period: str = "monthly") -> int:
    """What the member is charged each period: list price + 18% GST (₹2,359 / ₹23,600 / ₹5,900)."""
    return round(PRICES_INR.get((plan, period), 0) * (100 + GST_PCT) / 100)


def monthly_value(plan: str, period: str) -> float:
    """List price per month, before GST (what MRR counts). A yearly plan counts as a twelfth."""
    p = PRICES_INR.get((plan, period), 0)
    return p / 12 if period == "yearly" else p


# Lowest plan that opens each feature. `built` = stage it ships in (the menu shows later ones as "being built").
FEATURES: dict[str, dict] = {
    # webinar tools — free accounts get one go each
    "readiness": {"min": "free", "name": "Readiness Score", "stage": 1},
    "start": {"min": "free", "name": "Starting Point", "stage": 1},
    "case": {"min": "free", "name": "Weekly Case", "stage": 1},
    "brief": {"min": "free", "name": "Meeting Brief", "stage": 1},
    "linkedin": {"min": "free", "name": "LinkedIn Score", "stage": 1},
    "file": {"min": "free", "name": "My Consulting File", "stage": 1},
    # ₹1,999 plan
    "linkedin_improve": {"min": "member", "name": "LinkedIn rewrites", "stage": 1},
    "presentation": {"min": "member", "name": "Presentation Builder", "stage": 2},
    "visuals": {"min": "member", "name": "Visual Builder", "stage": 2},
    "website": {"min": "member", "name": "Website Builder", "stage": 2},
    "listen": {"min": "member", "name": "Listen mode", "stage": 2},
    "doc_reader": {"min": "member", "name": "Doc Reader", "stage": 2},
    "progress": {"min": "member", "name": "Progress Report", "stage": 2},
    # L1
    "action_tools": {"min": "l1", "name": "Action Hub tools", "stage": 3},
    "calls": {"min": "l1", "name": "Group calls with Akshat", "stage": 3},
    "recordings": {"min": "l1", "name": "Recordings and workbooks", "stage": 3},
    "offer_card": {"min": "l1", "name": "Offer Card", "stage": 3},
    "story_bank": {"min": "l1", "name": "Career Story Bank", "stage": 3},
    "insight_pack": {"min": "l1", "name": "Industry Insight Pack", "stage": 3},
    "portfolio": {"min": "l1", "name": "Portfolio Project", "stage": 3},
    "akshat_ai": {"min": "l1", "name": "Akshat AI", "stage": 3},
    "pitch": {"min": "l1", "name": "Pitch Practice", "stage": 3},
    "research": {"min": "l1", "name": "Research Notebook", "stage": 3},
    "recaps": {"min": "l1", "name": "Session Recap Pack", "stage": 3},
    # L2
    "mentorship_tools": {"min": "l2", "name": "Mentorship tools", "stage": 4},
    "network_finder": {"min": "l2", "name": "Warm Network Finder", "stage": 4},
    "outreach": {"min": "l2", "name": "Outreach Drafter", "stage": 4},
    "radar": {"min": "l2", "name": "Opportunity Radar", "stage": 4},
    "call_prep": {"min": "l2", "name": "Discovery Call Prep", "stage": 4},
    "proposal": {"min": "l2", "name": "Proposal Follow-through", "stage": 4},
    "client_diagnostic": {"min": "l2", "name": "Client Diagnostic", "stage": 4},
    "social_builder": {"min": "l2", "name": "Social Media Builder", "stage": 4},
}
FEATURE_MIN = {k: v["min"] for k, v in FEATURES.items()}
FEATURE_NAMES = {k: v["name"] for k, v in FEATURES.items()}

# Monthly limits (None = no limit, fair use applies). Free = once for life (the webinar go).
LIMITS: dict[str, dict[str, Optional[int]]] = {
    "readiness": {"free": 1, "member": 1, "l1": 1, "l2": 1},
    "start": {"free": 1, "member": 5, "l1": 10, "l2": 10},
    "goal": {"free": 1, "member": None, "l1": None, "l2": None},
    "case": {"free": 1, "member": 8, "l1": 12, "l2": 12},
    "brief": {"free": 1, "member": 4, "l1": 8, "l2": 8},
    "linkedin": {"free": 1, "member": 2, "l1": 4, "l2": 4},
}
LIMIT_UNITS = {"readiness": "Readiness Scores", "start": "Niche Snapshots", "goal": "Goal Map changes",
               "case": "case answers", "brief": "Meeting Briefs", "linkedin": "LinkedIn checks"}
FAIR_USE = {"goal": 60}

CATALOG = [
    {"id": "free", "name": "Free account", "periods": [], "features": [
        "Made on the webinar: your Readiness Score, Niche Snapshot, Goal Map, one live case and one Meeting Brief",
        "LinkedIn Score, once", "Everything you made stays in My Consulting File"]},
    {"id": "member", "name": "₹1,999 plan", "periods": [
        {"period": "monthly", "price_inr": 1999, "total_inr": total_inr("member", "monthly")},
        {"period": "yearly", "price_inr": 20000, "total_inr": total_inr("member", "yearly")}], "features": [
        "Weekly Case + Meeting Brief: a real company from your industry every Monday, scored", "4 Meeting Briefs of your own a month",
        "LinkedIn Score + rewrites, twice a month", "Readiness Score every month", "Presentation Builder: 2 decks a month",
        "Visual Builder, Chart Builder and Mind Maps: 10 a month", "Website Builder: a one-page consulting site",
        "Listen mode and Doc Reader", "Monthly Progress Report", "My Consulting File"]},
    {"id": "l1", "name": "L1", "periods": [
        {"period": "monthly", "price_inr": 5000, "total_inr": total_inr("l1", "monthly")}], "features": [
        "Everything in the ₹1,999 plan, with higher limits", "The 4-3-2-1 action program in month 1, with coaches",
        "All Action Hub tools", "2 group calls a month with Akshat", "Recordings and workbooks",
        "Offer Card, Career Story Bank and Industry Insight Pack", "Monthly Portfolio Project and video",
        "Akshat AI, Pitch Practice and Research Notebook", "Session Recap Pack after every session"]},
    {"id": "l2", "name": "L2 Mentorship", "periods": [], "features": [
        "The 6-month mentorship, switched on by the team", "Client-getting tools: Warm Network Finder, Outreach Drafter, "
        "Opportunity Radar, Discovery Call Prep, Proposal Follow-through, Client Diagnostic", "Social Media Builder"]},
]


def plan_allows(plan: str, feature: str) -> bool:
    return RANK[plan] >= RANK[FEATURE_MIN.get(feature, "l2")]


def _uid(user) -> str:
    return str(user["_id"]) if isinstance(user, dict) else str(user)


LIVE_SUB = ["active", "authenticated", "pending"]


async def effective_plan(db, user: dict, now: Optional[datetime] = None) -> dict:
    """{plan, source, period, paid_until, cancelling, paused_for_l2}"""
    now = now or utcnow()
    uid = _uid(user)
    cands: list[tuple[str, str, Optional[datetime], Optional[str]]] = []   # (plan, source, until, period)
    if (user.get("role") or "user") == "admin":
        cands.append(("l2", "grant", None, None))
    renewing = False
    paused = False
    async for s in db.subscriptions.find({"user_id": uid}):
        if s.get("status") == "paused" and s.get("paused_for_l2"):
            paused = True
        end = s.get("current_end")
        if s.get("status") in LIVE_SUB and end and as_utc(end) > now and s.get("plan") in PLANS:
            cands.append((s["plan"], "paid", as_utc(end), s.get("period") or "monthly"))
            renewing = renewing or not s.get("cancel_at_cycle_end")
    async for g in db.plan_grants.find({"user_id": uid}):
        if g.get("ends_at") and as_utc(g["ends_at"]) > now and g.get("plan") in PLANS:
            cands.append((g["plan"], "grant", as_utc(g["ends_at"]), None))
    order = {"paid": 2, "grant": 1}
    best = ("free", "free", None, None)
    for c in cands:
        if RANK[c[0]] > RANK[best[0]] or (RANK[c[0]] == RANK[best[0]] and order.get(c[1], 0) > order.get(best[1], 0)):
            best = c
    paid = [c for c in cands if c[1] == "paid"]
    return {"plan": best[0], "source": best[1], "period": best[3], "until": best[2].isoformat() if best[2] else None,
            "paid_until": max(c[2] for c in paid).isoformat() if paid else None,
            "cancelling": bool(paid) and not renewing, "paused_for_l2": paused}


async def nonfree_plans(db, now: Optional[datetime] = None) -> dict[str, str]:
    """user_id → effective plan for everyone NOT on free, in three queries. Same precedence as effective_plan."""
    now = now or utcnow()
    best: dict[str, str] = {}

    def up(uid: str, p: Optional[str]) -> None:
        if p in PLANS and RANK[p] > RANK[best.get(uid, "free")]:
            best[uid] = p
    async for s in db.subscriptions.find({"status": {"$in": LIVE_SUB}, "current_end": {"$gt": now}}, {"user_id": 1, "plan": 1}):
        up(s["user_id"], s.get("plan"))
    async for g in db.plan_grants.find({"ends_at": {"$gt": now}}, {"user_id": 1, "plan": 1}):
        up(g["user_id"], g.get("plan"))
    async for u in db.users.find({"role": "admin"}, {"_id": 1}):
        up(str(u["_id"]), "l2")
    return best


async def users_with(db, feature: str, now: Optional[datetime] = None) -> list[str]:
    """Ids of active (not revoked) members whose plan includes `feature`, resolved in bulk for job fan-outs."""
    now = now or utcnow()
    need = FEATURE_MIN.get(feature, "l2")
    if need == "free":
        return [str(u["_id"]) async for u in db.users.find({"status": {"$ne": "revoked"}}, {"_id": 1})]
    revoked = {str(u["_id"]) async for u in db.users.find({"status": "revoked"}, {"_id": 1})}
    return [uid for uid, p in (await nonfree_plans(db, now)).items() if RANK[p] >= RANK[need] and uid not in revoked]


def usage_key(uid: str, plan: str) -> str:
    return f"{uid}:life" if plan == "free" else f"{uid}:{ist_month_key()}"


def _webinar_tools_on() -> bool:
    from core.flags import is_on
    return is_on("WEBINAR_TOOLS")


def limit_for(feature: str, plan: str) -> Optional[int]:
    lim = LIMITS[feature][plan]
    if plan == "free" and not _webinar_tools_on():
        return 0
    return lim


async def plan_info(db, user: dict) -> dict:
    ep = await effective_plan(db, user)
    plan = ep["plan"]
    u = await db.usage.find_one({"_id": usage_key(_uid(user), plan)}) or {}
    from billing.l2 import l2_status
    return {**ep, "label": LABELS[plan], "l2": l2_status(user),
            "features": {f: plan_allows(plan, f) for f in FEATURE_MIN},
            "limits": {f: {"used": int(u.get(f, 0)), "limit": limit_for(f, plan), "once": plan == "free"} for f in LIMITS}}


def needed_for(feature: str) -> str:
    need = FEATURE_MIN.get(feature, "l2")
    return "member" if need == "free" else need


def locked_error(feature: str, plan_needed: Optional[str] = None) -> HTTPException:
    need = plan_needed or needed_for(feature)
    return HTTPException(status_code=403, detail={
        "code": "locked", "feature": feature, "plan_needed": need,
        "msg": f"{FEATURE_NAMES.get(feature, feature)} is part of the {LABELS[need]}."})


async def require(db, user: dict, feature: str) -> str:
    """Returns the plan; raises 403 locked if the plan doesn't include the feature."""
    plan = (await effective_plan(db, user))["plan"]
    if not plan_allows(plan, feature):
        await events.track(db, "locked_hit", user_id=_uid(user), props={"feature": feature, "plan": plan})
        raise locked_error(feature)
    return plan


def _next_plan(plan: str) -> Optional[str]:
    return {"free": "member", "member": "l1"}.get(plan)


async def consume(db, user: dict, feature: str, plan: Optional[str] = None) -> dict:
    """Meter one use. Returns {used, limit}. Raises 402 limit (or 403 locked when the limit is 0)."""
    uid = _uid(user)
    plan = plan or (await effective_plan(db, user))["plan"]
    limit = limit_for(feature, plan)
    key = usage_key(uid, plan)
    if limit == 0:
        await events.track(db, "locked_hit", user_id=uid, props={"feature": feature, "plan": plan})
        raise locked_error(feature, "member")
    doc = await db.usage.find_one({"_id": key}) or {}
    used = int(doc.get(feature, 0))
    cap = limit if limit is not None else FAIR_USE.get(feature)
    if cap is not None and used >= cap:
        await events.track(db, "limit_hit", user_id=uid, props={"feature": feature, "plan": plan})
        nxt = _next_plan(plan)
        unit = LIMIT_UNITS.get(feature, FEATURE_NAMES.get(feature, feature) + " uses")
        if plan == "free":
            msg = f"You've used your free go on the webinar. The {LABELS['member']} gives you {LIMITS[feature]['member'] or 'more'} {unit} a month."
        else:
            msg = f"You've used all {cap} {unit} this month." + (f" {LABELS[nxt]} gives you more." if nxt else " It resets on the 1st.")
        raise HTTPException(status_code=402, detail={"code": "limit", "feature": feature, "used": used, "limit": cap,
                                                     "plan_needed": nxt, "once": plan == "free", "msg": msg})
    setoi = {"user_id": uid} if plan == "free" else {"user_id": uid, "month": ist_month_key()}
    await db.usage.update_one({"_id": key}, {"$inc": {feature: 1}, "$setOnInsert": setoi}, upsert=True)
    return {"used": used + 1, "limit": limit}


async def refund(db, user: dict, feature: str, plan: Optional[str] = None) -> None:
    plan = plan or (await effective_plan(db, user))["plan"]
    await db.usage.update_one({"_id": usage_key(_uid(user), plan), feature: {"$gt": 0}}, {"$inc": {feature: -1}})
