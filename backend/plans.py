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

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

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
    "readiness": {"min": "free", "name": "Readiness Score"},
    "start": {"min": "free", "name": "Starting Point"},
    "case": {"min": "free", "name": "Weekly Case"},
    "brief": {"min": "free", "name": "Meeting Brief"},
    "linkedin": {"min": "free", "name": "LinkedIn Score"},
    "file": {"min": "free", "name": "My Consulting File"},
    # ₹1,999 plan
    "linkedin_improve": {"min": "member", "name": "LinkedIn rewrites"},
    "presentation": {"min": "member", "name": "Presentation Builder"},
    "visuals": {"min": "member", "name": "Visual Builder"},
    "website": {"min": "member", "name": "Website Builder"},
    "listen": {"min": "member", "name": "Listen mode"},
    "doc_reader": {"min": "member", "name": "Doc Reader"},
    "progress": {"min": "member", "name": "Progress Report"},
    "support": {"min": "member", "name": "Support"},
    # L1
    "program": {"min": "l1", "name": "4-3-2-1 action program"},
    "action_tools": {"min": "l1", "name": "Action Hub tools"},
    "calls": {"min": "l1", "name": "Group calls with Akshat"},
    "recordings": {"min": "l1", "name": "Recordings and workbooks"},
    "offer_card": {"min": "l1", "name": "Offer Card"},
    "story_bank": {"min": "l1", "name": "Career Story Bank"},
    "insight_pack": {"min": "l1", "name": "Industry Insight Pack"},
    "portfolio": {"min": "l1", "name": "Portfolio Project"},
    "akshat_ai": {"min": "l1", "name": "Akshat AI"},
    "pitch": {"min": "l1", "name": "Pitch Practice"},
    "research": {"min": "l1", "name": "Research Notebook"},
    "recaps": {"min": "l1", "name": "Session Recap Pack"},
    # L2
    "mentorship_tools": {"min": "l2", "name": "Mentorship tools"},
    "network_finder": {"min": "l2", "name": "Warm Network Finder"},
    "outreach": {"min": "l2", "name": "Outreach Drafter"},
    "radar": {"min": "l2", "name": "Opportunity Radar"},
    "call_prep": {"min": "l2", "name": "Discovery Call Prep"},
    "proposal": {"min": "l2", "name": "Proposal Follow-through"},
    "client_diagnostic": {"min": "l2", "name": "Client Diagnostic"},
    "social_builder": {"min": "l2", "name": "Social Media Builder"},
    "bootcamps": {"min": "l2", "name": "Bootcamps"},
    "events": {"min": "l2", "name": "L2 events"},
}
FEATURE_MIN = {k: v["min"] for k, v in FEATURES.items()}
FEATURE_NAMES = {k: v["name"] for k, v in FEATURES.items()}

# Monthly limits (None = no limit, fair use applies). Free = once for life (the webinar go).
def _lim(member: Optional[int], l1: Optional[int], l2: Optional[int], free: Optional[int] = 0) -> dict:
    return {"free": free, "member": member, "l1": l1, "l2": l2}


# Monthly limits (None = no limit, fair use applies). Free = once for life (the webinar go); 0 = not on the plan.
LIMITS: dict[str, dict[str, Optional[int]]] = {
    # webinar tools
    "readiness": _lim(1, 1, 1, free=1),
    "start": _lim(5, 10, 10, free=1),
    "goal": _lim(None, None, None, free=1),
    "case": _lim(8, 12, 12, free=1),
    "brief": _lim(4, 8, 8, free=1),
    "linkedin": _lim(2, 4, 4, free=1),
    # ₹1,999 plan
    "presentation": _lim(2, 6, 6),
    "visuals": _lim(10, 30, 30),
    "audio": _lim(5, 10, 10),            # Listen mode and Insight Pack audio
    "doc_q": _lim(60, 150, 300),         # questions to Doc Reader and Research Notebook
    "progress": _lim(1, 1, 1),
    "site_ai": _lim(20, 60, 100),        # Website Builder AI writes and edits
    # L1
    "gpt": _lim(0, 300, 600),            # messages to the Action Hub (L1) and Mentorship (L2) tools
    "akshat_ai": _lim(0, 30, 60),
    "pitch": _lim(0, 4, 4),
    "offer_card": _lim(0, 10, 10),
    "story": _lim(0, 6, 6),              # Career Story Bank: one story a week
    "insight": _lim(0, 2, 2),
    "portfolio": _lim(0, 2, 2),
    # L2
    "contacts": _lim(0, 0, 50),          # Warm Network Finder: contacts scored
    "outreach": _lim(0, 0, 100),
    "radar": _lim(0, 0, 10),             # Opportunity Radar: companies found
    "call_prep": _lim(0, 0, 20),
    "proposal": _lim(0, 0, 20),
    "diagnostic": _lim(0, 0, 20),
    "posts": _lim(0, 0, 30),
}
LIMIT_UNITS = {"readiness": "Readiness Scores", "start": "Niche Snapshots", "goal": "Goal Map changes",
               "case": "case answers", "brief": "Meeting Briefs", "linkedin": "LinkedIn checks",
               "presentation": "decks", "visuals": "visuals", "audio": "audio versions", "doc_q": "document questions",
               "progress": "Progress Reports", "site_ai": "website AI edits", "gpt": "messages to the tools",
               "akshat_ai": "questions to Akshat AI", "pitch": "pitch practices", "offer_card": "Offer Cards",
               "story": "career stories", "insight": "Insight Packs", "portfolio": "portfolio projects",
               "contacts": "contacts scored", "outreach": "outreach drafts", "radar": "companies",
               "call_prep": "call preps", "proposal": "proposals", "diagnostic": "diagnostics", "posts": "posts"}
FAIR_USE = {"goal": 60}

# Stored-item caps by plan (not monthly): checked by the module that stores them.
CAPS = {
    "docs": {"member": 5, "l1": 20, "l2": 20},             # Doc Reader documents kept at a time
    "research_projects": {"member": 0, "l1": 4, "l2": 8},  # Research Notebook projects
    "site_pages": {"member": 1, "l1": 5, "l2": 5},         # Website Builder pages
    "custom_domain": {"member": 0, "l1": 1, "l2": 1},
}


def cap(name: str, plan: str) -> int:
    return int(CAPS.get(name, {}).get(plan, 0) or 0)


CAP_LOCK_SECONDS = 30


@asynccontextmanager
async def cap_lock(db, user, name: str, wait_s: float = 3.0):
    """Safe pattern for stored-item caps. Counting then inserting in two steps lets two parallel requests both see
    "one slot left". Hold this per-member lock around the count and the insert:

        async with plans.cap_lock(db, user, "docs"):
            if await db.docs.count_documents({"user_id": uid}) >= plans.cap("docs", plan):
                raise HTTPException(409, ...)
            await db.docs.insert_one(...)

    The lock is a short lease in Mongo, so it works across workers; a crashed holder's lease ends after 30 s.
    If another request holds it for longer than `wait_s`, this answers 409 busy."""
    key = f"{_uid(user)}:{name}"
    token = uuid.uuid4().hex
    deadline = asyncio.get_running_loop().time() + wait_s
    while True:
        now = utcnow()
        try:
            await db.cap_locks.find_one_and_update(
                {"_id": key, "until": {"$lt": now}},
                {"$set": {"until": now + timedelta(seconds=CAP_LOCK_SECONDS), "by": token}}, upsert=True)
            break
        except DuplicateKeyError:                    # held by another request
            if asyncio.get_running_loop().time() >= deadline:
                raise HTTPException(status_code=409, detail={"code": "busy", "msg": "Another change is still saving. Try again."})
            await asyncio.sleep(0.05)
    try:
        yield
    finally:
        await db.cap_locks.delete_one({"_id": key, "by": token})


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
# Two short bridges so a member never drops to free between two steps that belong together:
#   - L2 has ended and the hourly job hasn't restarted the paused L1 yet: the L1 counts from resume_at.
#   - A plan bought to start later (subscription "authenticated" with starts_at): it counts from its start date
#     until Razorpay's first charge webhook arrives.
# Each bridge lasts BRIDGE_DAYS at most (the same 2 days a verified-but-unconfirmed payment gets).
BRIDGE_DAYS = 2


def _bridge(s: dict, now: datetime) -> Optional[datetime]:
    """End of the bridge access this subscription gives right now, or None."""
    st = s.get("status")
    if st == "paused" and s.get("paused_for_l2") and s.get("resume_at"):
        start = as_utc(s["resume_at"])
    elif st == "authenticated" and s.get("starts_at") and not s.get("current_end") and not s.get("cancel_at_cycle_end"):
        start = as_utc(s["starts_at"])
    else:
        return None
    end = start + timedelta(days=BRIDGE_DAYS)
    return end if start <= now < end else None


async def effective_plan(db, user: dict, now: Optional[datetime] = None) -> dict:
    """{plan, source, period, until, paid_until, cancelling, paused_for_l2, scheduled}

    scheduled = a plan bought to start later (the ₹1,999 offer after cancelling L1, or a period switch):
    {plan, label, period, starts_at}, or None."""
    now = now or utcnow()
    uid = _uid(user)
    cands: list[tuple[str, str, Optional[datetime], Optional[str]]] = []   # (plan, source, until, period)
    if (user.get("role") or "user") == "admin":
        cands.append(("l2", "grant", None, None))
    renewing = False
    paused = False
    scheduled: Optional[dict] = None
    sched_at: Optional[datetime] = None
    async for s in db.subscriptions.find({"user_id": uid}):
        if s.get("plan") not in PLANS:
            continue
        if s.get("status") == "paused" and s.get("paused_for_l2"):
            paused = True
        end = s.get("current_end")
        bridge = _bridge(s, now)
        if s.get("status") in LIVE_SUB and end and as_utc(end) > now:
            cands.append((s["plan"], "paid", as_utc(end), s.get("period") or "monthly"))
            renewing = renewing or not s.get("cancel_at_cycle_end")
        elif bridge:
            cands.append((s["plan"], "paid", bridge, s.get("period") or "monthly"))
            renewing = True
        elif (s.get("status") == "authenticated" and s.get("starts_at") and not s.get("current_end")
              and not s.get("cancel_at_cycle_end") and as_utc(s["starts_at"]) > now):
            st = as_utc(s["starts_at"])
            if sched_at is None or st < sched_at:
                sched_at = st
                scheduled = {"plan": s["plan"], "label": LABELS[s["plan"]], "period": s.get("period") or "monthly",
                             "starts_at": st.isoformat()}
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
            "cancelling": bool(paid) and not renewing, "paused_for_l2": paused, "scheduled": scheduled}


async def nonfree_plans(db, now: Optional[datetime] = None) -> dict[str, str]:
    """user_id → effective plan for everyone NOT on free, in a few queries. Same precedence as effective_plan."""
    now = now or utcnow()
    best: dict[str, str] = {}

    def up(uid: str, p: Optional[str]) -> None:
        if p in PLANS and RANK[p] > RANK[best.get(uid, "free")]:
            best[uid] = p
    async for s in db.subscriptions.find({"status": {"$in": LIVE_SUB}, "current_end": {"$gt": now}}, {"user_id": 1, "plan": 1}):
        up(s["user_id"], s.get("plan"))
    since = now - timedelta(days=BRIDGE_DAYS)
    async for s in db.subscriptions.find({"$or": [
            {"status": "paused", "paused_for_l2": True, "resume_at": {"$lte": now, "$gt": since}},
            {"status": "authenticated", "starts_at": {"$lte": now, "$gt": since}}]}):
        if _bridge(s, now):
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


def _allowance(feature: str, plan: str) -> Optional[int]:
    """How many uses `plan` gets of `feature` in a month (None = no cap at all)."""
    lim = LIMITS.get(feature, {}).get(plan)
    return lim if lim is not None else FAIR_USE.get(feature)


def _next_plan(plan: str, feature: Optional[str] = None, cap: Optional[int] = None) -> Optional[str]:
    """The plan to point a member to at a limit: the next plan they can buy in the app that really gives more of
    `feature`. None when there is none (L1 and L2 members, or a plan above with the same limit): the screen then
    says the limit resets on the 1st and shows no upgrade button."""
    if plan == "free":
        return "member"
    for p in ("member", "l1"):                      # L2 isn't bought in the app
        if RANK[p] <= RANK[plan]:
            continue
        if feature is None:
            return p
        more = _allowance(feature, p)
        if more is None or (cap is not None and more > cap):
            return p
    return None


async def consume(db, user: dict, feature: str, plan: Optional[str] = None) -> dict:
    """Meter one use. Returns {used, limit}. Raises 402 limit (or 403 locked when the limit is 0).

    The check and the count are ONE conditional write: the counter goes up only if it is still below the limit.
    Two taps at the same moment can't both get the last go (a free account really gets one go)."""
    uid = _uid(user)
    plan = plan or (await effective_plan(db, user))["plan"]
    limit = limit_for(feature, plan)
    key = usage_key(uid, plan)
    if limit == 0:
        await events.track(db, "locked_hit", user_id=uid, props={"feature": feature, "plan": plan})
        need = next((p for p in PLANS if RANK[p] > RANK[plan] and LIMITS[feature][p] != 0), "member")
        raise locked_error(feature, need)
    cap = limit if limit is not None else FAIR_USE.get(feature)
    setoi = {"user_id": uid} if plan == "free" else {"user_id": uid, "month": ist_month_key()}
    flt: dict = {"_id": key}
    if cap is not None:
        flt[feature] = {"$not": {"$gte": cap}}       # missing (never used) or still below the limit
    doc = None
    for _ in range(2):
        try:
            doc = await db.usage.find_one_and_update(flt, {"$inc": {feature: 1}, "$setOnInsert": setoi},
                                                     upsert=True, return_document=ReturnDocument.AFTER)
            break
        except DuplicateKeyError:
            # The row exists but didn't match: it is at the limit. (On the first try this can also be two
            # first-ever uses racing to create the row, so try once more now that it exists.)
            doc = None
    if doc is None:
        await events.track(db, "limit_hit", user_id=uid, props={"feature": feature, "plan": plan})
        used = int(((await db.usage.find_one({"_id": key})) or {}).get(feature, cap or 0))
        nxt = _next_plan(plan, feature, cap)
        unit = LIMIT_UNITS.get(feature, FEATURE_NAMES.get(feature, feature) + " uses")
        if plan == "free":
            msg = f"You've used your free go on the webinar. The {LABELS['member']} gives you {LIMITS[feature]['member'] or 'more'} {unit} a month."
        else:
            msg = f"You've used all {cap} {unit} this month." + (f" {LABELS[nxt]} gives you more." if nxt else " It resets on the 1st.")
        raise HTTPException(status_code=402, detail={"code": "limit", "feature": feature, "used": used, "limit": cap,
                                                     "plan_needed": nxt, "once": plan == "free", "msg": msg})
    return {"used": int(doc.get(feature, 1)), "limit": limit}


async def refund(db, user: dict, feature: str, plan: Optional[str] = None) -> None:
    plan = plan or (await effective_plan(db, user))["plan"]
    await db.usage.update_one({"_id": usage_key(_uid(user), plan), feature: {"$gt": 0}}, {"$inc": {feature: -1}})
