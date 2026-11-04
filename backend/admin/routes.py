"""Admin panel API (role admin). Everything under /api/admin.

pulse            KPIs: accounts, plan mix (free / ₹1,999 / L1 / L2), MRR, signups by day and source, tool use
live             During the webinar: accounts made and tools used in the last 15 minutes and today
webinar          Report for a date window; group-session.csv = accounts from that window who didn't buy
users            Search, detail, grant a plan, start L2, disable
flags, settings, vendors, jobs, cases (live case picker), kb (knowledge base for Akshat AI, stage 3)
"""
from __future__ import annotations

import asyncio
import csv
import io
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

import appsettings
import plans
from auth import public_user
from billing import l2 as l2_billing
from billing.razorpay_client import build_client
from core import flags
from core.deps import admin_dep
from core.vendors import REQUIRED_KEYS, vendor_mode
from features import kb as kb_f
from growth import events
from growth.clock import IST, as_utc, utcnow
from jobs import registry
from state import db
from util import iso, oid

router = APIRouter(prefix="/admin", tags=["admin"])
Admin = Depends(admin_dep())

TOOL_EVENTS = {"readiness_done": "Readiness Score", "snapshot_run": "Niche Snapshot", "goal_saved": "Goal Map",
               "case_answered": "Case answers", "brief_made": "Meeting Brief", "linkedin_checked": "LinkedIn Score",
               "file_viewed": "My Consulting File"}


def ist_day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=IST).astimezone(timezone.utc)


async def paid_subs(d, now: Optional[datetime] = None) -> dict[str, tuple[str, str]]:
    """user_id → (best paid plan, period) from live subscriptions (same statuses as plans.effective_plan)."""
    now = now or utcnow()
    out: dict[str, tuple[str, str]] = {}
    async for s in d.subscriptions.find({"status": {"$in": plans.LIVE_SUB}, "current_end": {"$gt": now}},
                                        {"user_id": 1, "plan": 1, "period": 1}):
        p = s.get("plan")
        if p in plans.PLANS and plans.RANK[p] > plans.RANK[out.get(s["user_id"], ("free", ""))[0]]:
            out[s["user_id"]] = (p, s.get("period") or "monthly")
    return out


async def _admin_ids(d) -> set[str]:
    return {str(u["_id"]) async for u in d.users.find({"role": "admin"}, {"_id": 1})}


async def _granted(d, now: datetime) -> dict[str, str]:
    out: dict[str, str] = {}
    async for g in d.plan_grants.find({"ends_at": {"$gt": now}}, {"user_id": 1, "plan": 1}):
        if g.get("plan") in plans.PLANS and plans.RANK[g["plan"]] > plans.RANK[out.get(g["user_id"], "free")]:
            out[g["user_id"]] = g["plan"]
    return out


async def _tool_counts(d, since: datetime, until: Optional[datetime] = None, skip: set[str] = frozenset()) -> list[dict]:
    """Uses and distinct people per tool in one aggregate."""
    ts = {"$gte": since, **({"$lt": until} if until else {})}
    feat: dict[str, dict] = {}
    async for r in d.events.aggregate([
            {"$match": {"name": {"$in": list(TOOL_EVENTS)}, "ts": ts}},
            {"$project": {"_id": 0, "name": 1, "who": "$user_id"}},
            {"$match": {"who": {"$nin": [None, *skip]}}},
            {"$group": {"_id": {"n": "$name", "w": "$who"}, "uses": {"$sum": 1}}},
            {"$group": {"_id": "$_id.n", "users": {"$sum": 1}, "uses": {"$sum": "$uses"}}}], allowDiskUse=True):
        feat[TOOL_EVENTS[r["_id"]]] = {"users": r["users"], "uses": r["uses"]}
    return sorted([{"tool": k, **v} for k, v in feat.items()], key=lambda x: -x["users"])


# ------------------------------------------------------------------ pulse ----
@router.get("/pulse")
async def pulse(_: dict = Admin):
    d = db()
    now = utcnow()
    today = now.astimezone(IST).date()
    members = {"role": {"$ne": "admin"}, "phone": {"$exists": True}}
    skip = await _admin_ids(d)
    total = await d.users.count_documents(members)
    t0 = ist_day_start(today)
    signups_today = await d.users.count_documents({**members, "created_at": {"$gte": t0}})
    signups_7d = await d.users.count_documents({**members, "created_at": {"$gte": t0 - timedelta(days=6)}})
    paid = {u: p for u, p in (await paid_subs(d, now)).items() if u not in skip}
    granted = {u: p for u, p in (await _granted(d, now)).items() if u not in skip}
    best: dict[str, str] = {u: p for u, (p, _) in paid.items()}
    for u, p in granted.items():
        if plans.RANK[p] > plans.RANK[best.get(u, "free")]:
            best[u] = p
    mix = {p: sum(1 for x in best.values() if x == p) for p in ("member", "l1", "l2")}
    mix["free"] = max(0, total - sum(mix.values()))
    mrr = round(sum(plans.monthly_value(p, per) for p, per in paid.values()))
    member_yearly = sum(1 for p, per in paid.values() if p == "member" and per == "yearly")
    l1_paused = await d.subscriptions.count_documents({"status": "paused", "paused_for_l2": True})
    counts: dict[str, int] = {}
    async for u in d.users.find({**members, "created_at": {"$gte": t0 - timedelta(days=13)}}, {"_id": 0, "created_at": 1}):
        k = as_utc(u["created_at"]).astimezone(IST).date().isoformat()
        counts[k] = counts.get(k, 0) + 1
    by_day = [{"date": (today - timedelta(days=i)).isoformat(), "count": counts.get((today - timedelta(days=i)).isoformat(), 0)}
              for i in range(13, -1, -1)]
    src: dict[str, int] = {}
    async for r in d.users.aggregate([{"$match": members}, {"$group": {"_id": "$acquisition.source", "n": {"$sum": 1}}}]):
        k = r["_id"] or "unknown"
        src[k] = src.get(k, 0) + r["n"]
    paying = sum(1 for p, _ in paid.values())
    return {"kpis": {"users_total": total, "signups_today": signups_today, "signups_7d": signups_7d,
                     "member_active": mix["member"], "member_yearly": member_yearly, "l1_active": mix["l1"],
                     "l2_active": mix["l2"], "l1_paused_for_l2": l1_paused, "mrr_inr": mrr,
                     "granted_active": sum(1 for u in granted if u not in paid),
                     "paid_conversion_pct": round(paying / total * 100, 1) if total else 0.0},
            "mrr_note": "Before GST. Yearly ₹1,999 plans count as a twelfth a month. L2 is sold outside the app.",
            "signups_by_day": by_day,
            "by_source": sorted([{"source": k, "count": v} for k, v in src.items()], key=lambda x: -x["count"]),
            "tool_usage_7d": await _tool_counts(d, now - timedelta(days=7), skip=skip),
            "plan_mix": [{"plan": p, "label": plans.LABELS[p], "count": mix[p]} for p in ("l2", "l1", "member", "free")]}


@router.get("/live")
async def live(_: dict = Admin):
    """For the team during the webinar: refresh every 30 s."""
    d = db()
    now = utcnow()
    skip = await _admin_ids(d)
    t0 = ist_day_start(now.astimezone(IST).date())
    q15 = now - timedelta(minutes=15)
    members = {"role": {"$ne": "admin"}}
    return {"at": now.isoformat(),
            "accounts_today": await d.users.count_documents({**members, "created_at": {"$gte": t0}}),
            "accounts_15m": await d.users.count_documents({**members, "created_at": {"$gte": q15}}),
            "tools_15m": await _tool_counts(d, q15, skip=skip), "tools_today": await _tool_counts(d, t0, skip=skip)}


# ------------------------------------------------------------------ webinar ----
def _window(start: str, end: str) -> tuple[datetime, datetime]:
    try:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": "bad_date", "msg": "Dates must be YYYY-MM-DD."})
    if e < s:
        s, e = e, s
    if (e - s).days > 92:
        raise HTTPException(status_code=400, detail={"code": "range_too_long", "msg": "Pick at most 3 months."})
    return ist_day_start(s), ist_day_start(e + timedelta(days=1))


async def _window_users(d, a: datetime, b: datetime) -> list[dict]:
    return [u async for u in d.users.find({"created_at": {"$gte": a, "$lt": b}, "role": {"$ne": "admin"},
                                           "status": {"$ne": "revoked"}},
                                          {"name": 1, "phone": 1, "created_at": 1, "acquisition.source": 1,
                                           "last_login_at": 1}).sort("created_at", 1)]


@router.get("/webinar")
async def webinar(start: str, end: str, _: dict = Admin):
    d = db()
    a, b = _window(start, end)
    now = utcnow()
    skip = await _admin_ids(d)
    rows = await _window_users(d, a, b)
    ids = {str(u["_id"]) for u in rows}
    paid = await paid_subs(d, now)
    granted = await _granted(d, now)
    used = set()
    async for r in d.events.aggregate([{"$match": {"name": {"$in": list(TOOL_EVENTS)}, "ts": {"$gte": a},
                                                   "user_id": {"$in": list(ids)}}}, {"$group": {"_id": "$user_id"}}]):
        used.add(r["_id"])
    bought = {p: sum(1 for u in ids if paid.get(u, ("", ""))[0] == p) for p in ("member", "l1")}
    return {"accounts": len(ids), "used_a_tool": len(used), "tool_usage": await _tool_counts(d, a, b, skip=skip),
            "bought": bought, "l2_from_window": sum(1 for u in ids if granted.get(u) == "l2"),
            "group_session_list": sum(1 for u in ids if u not in paid and u not in granted)}


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_PLAIN_NUMBER = re.compile(r"^[+-]?\d+(\.\d+)?$")


def csv_safe(v):
    """Excel and Sheets run a cell that starts with = + - @ (or a tab / CR before one) as a formula. Member names are
    typed by members, so prefix such cells with ' (OWASP CSV injection). Plain numbers (+919876543210) stay as they are."""
    if not isinstance(v, str) or not v or _PLAIN_NUMBER.match(v):
        return v
    return "'" + v if v.startswith(_FORMULA_START) else v


@router.get("/webinar/group-session.csv")
async def group_session_csv(start: str, end: str, _: dict = Admin):
    """Accounts from the window who haven't bought: invite them to Akshat's group session."""
    d = db()
    a, b = _window(start, end)
    now = utcnow()
    paid = await paid_subs(d, now)
    granted = await _granted(d, now)
    rows = [u for u in await _window_users(d, a, b) if str(u["_id"]) not in paid and str(u["_id"]) not in granted]
    used_by: dict[str, int] = {}
    ids = [str(u["_id"]) for u in rows]
    for k in range(0, len(ids), 5000):
        async for r in d.events.aggregate([
                {"$match": {"name": {"$in": list(TOOL_EVENTS)}, "ts": {"$gte": a}, "user_id": {"$in": ids[k:k + 5000]}}},
                {"$project": {"_id": 0, "user_id": 1}}, {"$group": {"_id": "$user_id", "n": {"$sum": 1}}}]):
            used_by[r["_id"]] = r["n"]
    scores: dict[str, int] = {}
    async for r in d.readiness.aggregate([{"$match": {"user_id": {"$in": ids}}}, {"$sort": {"at": -1}},
                                          {"$group": {"_id": "$user_id", "total": {"$first": "$total"}}}]):
        scores[r["_id"]] = r["total"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "phone", "signed_up_ist", "source", "tools_used", "readiness_score", "last_login_ist"])
    for u in rows:
        uid = str(u["_id"])
        ll = u.get("last_login_at") or u.get("created_at")
        w.writerow([csv_safe(x) for x in (
            u.get("name") or "", u.get("phone") or "", as_utc(u["created_at"]).astimezone(IST).strftime("%Y-%m-%d %H:%M"),
            (u.get("acquisition") or {}).get("source", ""), used_by.get(uid, 0), scores.get(uid, ""),
            as_utc(ll).astimezone(IST).strftime("%Y-%m-%d %H:%M") if ll else "")])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="group-session-{start}-to-{end}.csv"'})


# ------------------------------------------------------------------ users ----
async def _row(d, u: dict) -> dict:
    ep = await plans.effective_plan(d, u)
    return {"id": str(u["_id"]), "phone": u.get("phone"), "name": u.get("name"), "email": u.get("email"),
            "role": u.get("role") or "user", "plan": ep["plan"], "plan_label": plans.LABELS[ep["plan"]],
            "plan_source": ep["source"], "period": ep["period"],
            "source": (u.get("acquisition") or {}).get("source"), "created_at": iso(u.get("created_at")),
            "last_login_at": iso(u.get("last_login_at")), "paid_until": ep["paid_until"],
            "paused_for_l2": ep["paused_for_l2"], "status": u.get("status") or "active"}


@router.get("/users")
async def users(q: Optional[str] = None, plan: Optional[str] = None, page: int = Query(1, ge=1, le=10000),
                _: dict = Admin):
    d = db()
    flt: dict = {}
    if q:
        rx = {"$regex": re.escape(q.strip().lstrip("+").replace(" ", "")), "$options": "i"}
        flt = {"$or": [{"phone": rx}, {"name": {"$regex": re.escape(q.strip()), "$options": "i"}}, {"email": rx}]}
    size = 50
    if plan in plans.PLANS:
        best = await plans.nonfree_plans(d)
        if plan == "free":
            flt = {**flt, "_id": {"$nin": [o for o in (oid(u) for u in best) if o]}}
        else:
            flt = {**flt, "_id": {"$in": [o for o in (oid(u) for u, p in best.items() if p == plan) if o]}}
    total = await d.users.count_documents(flt)
    cur = d.users.find(flt).sort("created_at", -1).skip((page - 1) * size).limit(size)
    return {"total": total, "items": [await _row(d, u) async for u in cur]}


async def _user(user_id: str) -> dict:
    o = oid(user_id)
    u = await db().users.find_one({"_id": o}) if o else None
    if not u:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "User not found."})
    return u


@router.get("/users/{user_id}")
async def user_detail(user_id: str, _: dict = Admin):
    u = await _user(user_id)
    d = db()
    info = await plans.plan_info(d, u)
    evs = [{"name": e["name"], "ts": iso(e["ts"]), "props": e.get("props") or {}}
           async for e in d.events.find({"user_id": user_id}).sort("ts", -1).limit(60)]
    subs = [{"id": s["_id"], "plan": s["plan"], "period": s.get("period") or "monthly", "status": s["status"],
             "current_end": iso(s.get("current_end")), "cancel_at_cycle_end": s.get("cancel_at_cycle_end"),
             "paused_for_l2": s.get("paused_for_l2", False), "resume_at": iso(s.get("resume_at")),
             "starts_at": iso(s.get("starts_at")), "cancel_failed": bool(s.get("cancel_failed")),
             "resume_failed": bool(s.get("resume_failed")), "error": s.get("cancel_error") or s.get("resume_error")}
            async for s in d.subscriptions.find({"user_id": user_id}).sort("created_at", -1)]
    grants = [{"plan": g["plan"], "ends_at": iso(g["ends_at"]), "by": g.get("by"), "kind": g.get("kind")}
              async for g in d.plan_grants.find({"user_id": user_id}).sort("at", -1)]
    return {"user": {**public_user(u), "status": u.get("status") or "active",
                     "source": (u.get("acquisition") or {}).get("source"), "last_login_at": iso(u.get("last_login_at")),
                     "downsell_offered_at": iso(u.get("downsell_offered_at"))},
            "plan": info, "usage": info["limits"], "l2": l2_billing.l2_status(u), "subscriptions": subs,
            "grants": grants, "events": evs}


class GrantIn(BaseModel):
    plan: str = Field(..., pattern="^(free|member|l1)$")
    months: int = Field(1, ge=0, le=36)


@router.post("/users/{user_id}/grant")
async def grant(user_id: str, body: GrantIn, admin: dict = Admin):
    """Give a plan without payment (support cases, team accounts). Free ends every live grant except L2."""
    await _user(user_id)
    now = utcnow()
    await db().plan_grants.update_many({"user_id": user_id, "ends_at": {"$gt": now}, "plan": {"$ne": "l2"}},
                                       {"$set": {"ends_at": now}})
    if body.plan != "free" and body.months > 0:
        await db().plan_grants.insert_one({"user_id": user_id, "plan": body.plan, "ends_at": now + timedelta(days=31 * body.months),
                                           "by": str(admin["_id"]), "at": now})
    await events.track(db(), "plan_granted", user_id=user_id, props={"plan": body.plan, "months": body.months})
    return await user_detail(user_id, admin)


@router.post("/users/{user_id}/start-l2")
async def start_l2(user_id: str, admin: dict = Admin):
    """The member has paid for L2 (₹1.5L, outside the app): switch L2 on for 6 months and pause their L1."""
    await _user(user_id)
    try:
        res = await l2_billing.start_l2(db(), user_id, by=str(admin["_id"]))     # claims L2 atomically
    except l2_billing.L2AlreadyActive as e:
        until = f" until {e.ends_at.astimezone(IST).date().isoformat()}" if e.ends_at else ""
        raise HTTPException(status_code=409, detail={"code": "already_l2", "msg": f"L2 already runs{until}."})
    return {"result": res, **(await user_detail(user_id, admin))}


class StatusIn(BaseModel):
    status: str = Field(..., pattern="^(active|revoked)$")


async def _stop_billing(user_id: str) -> dict:
    """A revoked account must not keep paying: every running, scheduled or paused subscription stops renewing
    (running ones at the end of the period already paid). Ones the payment provider didn't take are flagged and
    retried by the hourly l2_resume job."""
    c = build_client()
    stopped, failed = 0, 0
    async for s in db().subscriptions.find({"user_id": user_id, "status": {"$in": [*plans.LIVE_SUB, "paused"]},
                                            "cancel_at_cycle_end": {"$ne": True}}):
        if await l2_billing.stop_renewal(c, db(), s, ended_for_revoke=True):
            stopped += 1
        else:
            failed += 1
    return {"stopped": stopped, "failed": failed}


@router.post("/users/{user_id}/status")
async def set_status(user_id: str, body: StatusIn, admin: dict = Admin):
    u = await _user(user_id)
    if str(u["_id"]) == str(admin["_id"]):
        raise HTTPException(status_code=400, detail={"code": "self", "msg": "You can't change your own status."})
    await db().users.update_one({"_id": u["_id"]}, {"$set": {"status": body.status}})
    billing = await _stop_billing(user_id) if body.status == "revoked" else None
    return {**(await user_detail(user_id, admin)), "billing": billing}


# ------------------------------------------------------------------ cases ----
@router.get("/cases")
async def cases(_: dict = Admin):
    live_id = (await appsettings.get(db()))["live_case_id"]
    rows = []
    async for c in db().cases.find({"active": {"$ne": False}}).sort("created_at", 1):
        n = await db().case_answers.count_documents({"case_id": c["_id"]})
        rows.append({"id": c["_id"], "title": c["title"], "company": c["company"], "industry": c["industry"],
                     "kind": c.get("kind", "practice"), "live": c["_id"] == live_id, "answers": n})
    return {"items": rows}


# ------------------------------------------------------------------ control ----
@router.get("/flags")
async def get_flags(_: dict = Admin):
    await flags.refresh(db(), force=True)
    return {"items": flags.listing()}


class FlagIn(BaseModel):
    key: str
    on: Optional[bool] = None


@router.post("/flags")
async def set_flag(body: FlagIn, admin: dict = Admin):
    try:
        await flags.set_flag(db(), body.key, body.on, by=str(admin.get("phone") or admin.get("email") or admin["_id"]))
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "unknown_flag", "msg": "Unknown switch."})
    await events.track(db(), "feature_toggled", user_id=str(admin["_id"]), props={"key": body.key, "on": body.on})
    return {"items": flags.listing()}


@router.get("/settings")
async def get_settings(_: dict = Admin):
    return await appsettings.get(db())


@router.post("/settings")
async def set_settings(body: dict, _: dict = Admin):
    return await appsettings.update(db(), body)


@router.get("/vendors")
async def vendors(_: dict = Admin):
    out = []
    for n in REQUIRED_KEYS:
        try:
            m = vendor_mode(n)
        except Exception as e:  # noqa: BLE001
            m = f"error: {e}"
        out.append({"name": n, "mode": m})
    return {"vendors": out}


@router.get("/jobs")
async def jobs(_: dict = Admin):
    return {"items": await registry.listing(db())}


@router.post("/jobs/{name}/run")
async def run_job(name: str, _: dict = Admin):
    """Run now takes the same lock as the scheduler, so a job never runs twice at once."""
    if name not in registry.JOBS:
        raise HTTPException(status_code=404, detail={"code": "unknown_job", "msg": "Unknown job."})
    owner = "admin-" + uuid.uuid4().hex[:12]
    if not await registry.claim_lock(db(), name, owner=owner):
        raise HTTPException(status_code=409, detail={"code": "job_running", "msg": "This job is running now. Try again in a few minutes."})
    try:
        r = await registry.run(db(), name)
    finally:
        await registry.release_lock(db(), name, owner=owner)
    return {"ok": r.get("ok"), "result": r.get("result") or r.get("error"), "ms": r.get("ms")}


# ------------------------------------------------------------------ knowledge base ----
@router.get("/kb")
async def kb(_: dict = Admin):
    return {"items": [{"id": k["_id"], "title": k["title"], "chunks": k["chunks"], "words": k["words"],
                       "uploaded_at": iso(k["uploaded_at"])} async for k in db().kb_docs.find({}).sort("uploaded_at", -1)]}


@router.post("/kb")
async def kb_upload(file: UploadFile = File(...), title: Optional[str] = Form(None), _: dict = Admin):
    name = (file.filename or "").lower()
    if not name.endswith((".txt", ".vtt", ".md", ".srt")):
        raise HTTPException(status_code=400, detail={"code": "bad_type", "msg": "Upload a .txt, .vtt, .srt or .md file."})
    raw = await file.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail={"code": "too_large", "msg": "Files up to 8 MB."})
    text = raw.decode("utf-8", errors="ignore")
    out = await kb_f.ingest(db(), (title or file.filename or "Session").strip()[:120], text)
    if not out["chunks"]:
        raise HTTPException(status_code=400, detail={"code": "empty", "msg": "No text found in that file."})
    return out


@router.delete("/kb/{doc_id}")
async def kb_delete(doc_id: str, _: dict = Admin):
    await db().kb_docs.delete_one({"_id": doc_id})
    await db().kb_chunks.delete_many({"doc_id": doc_id})
    kb_f.reset_kb_cache()
    return {"ok": True}




# ------------------------------------------------------------------ WhatsApp templates ----
@router.get("/whatsapp-templates")
async def whatsapp_templates(_: dict = Admin):
    from notify import templates
    return templates.catalogue()


class TemplateTestIn(BaseModel):
    kind: str = Field(..., max_length=40)


@router.post("/whatsapp-templates/test")
async def whatsapp_template_test(body: TemplateTestIn, user: dict = Admin):
    """Send one sample of an alert template to the admin's own mobile, to check the AiSensy campaign works."""
    from notify import templates
    from notify.channels import build_whatsapp
    row = next((t for t in templates.ALERTS if t[0] == body.kind), None)
    if not row:
        raise HTTPException(404, {"code": "not_found", "msg": "No such message type."})
    if not user.get("phone"):
        raise HTTPException(400, {"code": "no_phone", "msg": "Your admin account has no mobile number. Log in with OTP."})
    wa = build_whatsapp()
    if wa is None:
        raise HTTPException(409, {"code": "off", "msg": "WhatsApp isn't set up yet (AiSensy key missing)."})
    kind, _t, _w, _o, sample, path, _c = row
    title, _, text_ = sample.partition(" — ")
    res = await wa.send(user, {"kind": kind, "title": title, "body": text_ or title, "link": "/" + path})
    return {"ok": res.ok, "error": res.error, "campaign": templates.campaign_for(kind)}
