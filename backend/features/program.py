"""4-3-2-1 action program: L1 month 1, day by day, with a coach.

program_cohorts     {_id, name, start_date "YYYY-MM-DD" (IST day), active, default_coach: {name, whatsapp} | None,
                     days: [{n, title, when (UTC datetime) | None, link, recording_url, workbook_url,
                             tasks: [{id, text}]}], created_at, updated_at}
program_enrollments {_id, user_id, cohort_id, enrolled_at, coach: {name, whatsapp} | None, coach_until (UTC datetime),
                     done: [task_id], moved_at?}

GET /program enrols an L1/L2 member the first time they open it: the next active cohort (start ≥ today − 7 days),
else the latest active one. The coach is for month 1 (cohort start + 30 days). L2 members keep the coach while L2 is
on. After that the screen points to Support (/app/support). A member's own coach overrides the cohort's default coach.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import indexes
import plans
from accounts.phone import InvalidPhone, normalise_in_mobile
from core.deps import admin_dep, user_dep
from core.errors import AppError, error
from growth import events
from growth.clock import IST, as_utc, utcnow
from state import db
from util import iso, oid

router = APIRouter(tags=["program"])
member = APIRouter(prefix="/program")
admin = APIRouter(prefix="/admin/program")
Admin = Depends(admin_dep())

COACH_DAYS = 30
JOIN_WINDOW_DAYS = 7
SUPPORT_LINK = "/app/support"
SUPPORT_NOTE = "Your coach was for month 1 — for help use Support."
URL_RX = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.I)
TASK_ID_RX = re.compile(r"^[a-z0-9]{4,40}$")

indexes.register("program_enrollments", [("user_id", 1)], {"unique": True})
indexes.register("program_enrollments", [("cohort_id", 1)])
indexes.register("program_cohorts", [("active", 1), ("start_date", 1)])
events.register("program_enrolled", "Joined a 4-3-2-1 cohort (props.cohort_id)")
events.register("program_task_done", "Ticked a 4-3-2-1 task (props.task_id, props.pct)")


# ------------------------------------------------------------------ helpers ----
def _err(status: int, code: str, msg: str) -> AppError:
    return error(status, code, msg)


def ist_today() -> date:
    return utcnow().astimezone(IST).date()


def start_utc(start_date: str) -> datetime:
    """IST midnight of the cohort's first day, as UTC."""
    d = date.fromisoformat(start_date)
    return datetime(d.year, d.month, d.day, tzinfo=IST).astimezone(timezone.utc)


def parse_when(v: str) -> datetime:
    """ISO date-time; without an offset it is read as IST. Raises ValueError."""
    s = (v or "").strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(timezone.utc)


def ist_iso(dt: Optional[datetime]) -> Optional[str]:
    return as_utc(dt).astimezone(IST).isoformat() if dt else None


def url_or_blank(v: str, label: str) -> str:
    v = (v or "").strip()
    if v and not URL_RX.match(v):
        raise _err(400, "bad_link", f"{label} must start with https://")
    return v[:500]


def _coach_out(c: Optional[dict]) -> Optional[dict]:
    if not c or not c.get("name"):
        return None
    wa = c.get("whatsapp") or ""
    digits = re.sub(r"\D", "", wa)
    return {"name": c["name"], "whatsapp": wa, "whatsapp_link": f"https://wa.me/{digits}" if digits else None}


def _all_tasks(cohort: dict) -> list[str]:
    return [t["id"] for day in cohort.get("days") or [] for t in day.get("tasks") or []]


def _progress(cohort: Optional[dict], done: list[str]) -> dict:
    ids = _all_tasks(cohort or {})
    have = set(done or [])
    n = sum(1 for t in ids if t in have)
    return {"done": n, "total": len(ids), "pct": round(n * 100 / len(ids)) if ids else 0}


# ------------------------------------------------------------------ input models ----
class TaskIn(BaseModel):
    id: Optional[str] = Field(None, max_length=40)
    text: str = Field(..., min_length=1, max_length=300)


class DayIn(BaseModel):
    n: int = Field(..., ge=1, le=60)
    title: str = Field(..., min_length=2, max_length=140)
    when: Optional[str] = Field(None, max_length=40)
    link: str = Field("", max_length=500)
    recording_url: str = Field("", max_length=500)
    workbook_url: str = Field("", max_length=500)
    tasks: list[TaskIn] = Field(default_factory=list, max_length=20)


class CoachIn(BaseModel):
    name: str = Field("", max_length=80)
    whatsapp: str = Field("", max_length=20)
    until: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")     # member coach only: last IST day


class CohortIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    active: bool = True
    days: Optional[list[DayIn]] = Field(None, max_length=60)
    default_coach: Optional[CoachIn] = None


class DoneIn(BaseModel):
    done: bool = True


class MoveIn(BaseModel):
    cohort_id: str = Field(..., min_length=1, max_length=64)


def _coach_in(c: Optional[CoachIn]) -> Optional[dict]:
    if c is None:
        return None
    name = " ".join(c.name.split())
    if not name:
        return None
    wa = ""
    if c.whatsapp.strip():
        try:
            wa = normalise_in_mobile(c.whatsapp)
        except InvalidPhone as e:
            raise _err(400, "bad_phone", f"Coach WhatsApp: {e}")
    return {"name": name, "whatsapp": wa}


def _day_in(d: DayIn, used: set[str]) -> dict:
    when = None
    if d.when and d.when.strip():
        try:
            when = parse_when(d.when)
        except ValueError:
            raise _err(400, "bad_date", f"Day {d.n}: the date and time must look like 2026-11-10T19:00.")
    tasks = []
    for t in d.tasks:
        txt = " ".join(t.text.split())
        if not txt:
            continue
        tid = (t.id or "").strip().lower()
        if not TASK_ID_RX.match(tid) or tid in used:
            tid = uuid.uuid4().hex[:10]
        used.add(tid)
        tasks.append({"id": tid, "text": txt})
    return {"n": d.n, "title": " ".join(d.title.split()), "when": when,
            "link": url_or_blank(d.link, f"Day {d.n} join link"),
            "recording_url": url_or_blank(d.recording_url, f"Day {d.n} recording link"),
            "workbook_url": url_or_blank(d.workbook_url, f"Day {d.n} workbook link"), "tasks": tasks}


def _days_in(days: list[DayIn]) -> list[dict]:
    if len({d.n for d in days}) != len(days):
        raise _err(400, "dup_day", "Two days have the same number.")
    used: set[str] = set()
    return sorted((_day_in(d, used) for d in days), key=lambda x: x["n"])


def _check_date(s: str) -> str:
    try:
        date.fromisoformat(s)
    except ValueError:
        raise _err(400, "bad_date", "Start date must be a real date (YYYY-MM-DD).")
    return s


# ------------------------------------------------------------------ outputs ----
def _day_out(day: dict, done: Optional[set] = None) -> dict:
    out = {"n": day["n"], "title": day["title"], "when": ist_iso(day.get("when")), "link": day.get("link") or "",
           "recording_url": day.get("recording_url") or "", "workbook_url": day.get("workbook_url") or ""}
    if done is None:
        out["tasks"] = [{"id": t["id"], "text": t["text"]} for t in day.get("tasks") or []]
    else:
        out["tasks"] = [{"id": t["id"], "text": t["text"], "done": t["id"] in done} for t in day.get("tasks") or []]
        out["done"] = sum(1 for t in out["tasks"] if t["done"])
        out["total"] = len(out["tasks"])
    return out


def _cohort_full(c: dict, enrolled: int = 0) -> dict:
    return {"id": c["_id"], "name": c["name"], "start_date": c["start_date"], "active": bool(c.get("active")),
            "default_coach": _coach_out(c.get("default_coach")), "enrolled": enrolled,
            "days": [_day_out(x) for x in c.get("days") or []], "tasks": len(_all_tasks(c)),
            "created_at": iso(c.get("created_at"))}


# ------------------------------------------------------------------ member ----
async def _pick_cohort(d) -> Optional[dict]:
    floor = (ist_today() - timedelta(days=JOIN_WINDOW_DAYS)).isoformat()
    c = await d.program_cohorts.find_one({"active": True, "start_date": {"$gte": floor}}, sort=[("start_date", 1)])
    return c or await d.program_cohorts.find_one({"active": True}, sort=[("start_date", -1)])


async def ensure_enrollment(d, uid: str) -> Optional[dict]:
    e = await d.program_enrollments.find_one({"user_id": uid})
    if e:
        return e
    cohort = await _pick_cohort(d)
    if not cohort:
        return None
    now = utcnow()
    doc = {"_id": uuid.uuid4().hex, "user_id": uid, "cohort_id": cohort["_id"], "enrolled_at": now, "coach": None,
           "coach_until": start_utc(cohort["start_date"]) + timedelta(days=COACH_DAYS), "done": []}
    try:
        await d.program_enrollments.insert_one(doc)
    except Exception:  # noqa: BLE001 — two tabs opened at once: the other one enrolled first
        e = await d.program_enrollments.find_one({"user_id": uid})
        if e:
            return e
        raise
    await events.track(d, "program_enrolled", user_id=uid, props={"cohort_id": cohort["_id"]})
    return doc


def _coach_view(plan: str, e: dict, cohort: dict, now: datetime) -> dict:
    until = as_utc(e["coach_until"]) if e.get("coach_until") else None
    on = plan == "l2" or (until is not None and until > now)
    coach = _coach_out(e.get("coach")) or _coach_out(cohort.get("default_coach"))
    if not on:
        return {"coach": None, "coach_status": "ended", "coach_until": iso(until), "coach_note": SUPPORT_NOTE,
                "support_link": SUPPORT_LINK}
    return {"coach": coach, "coach_status": "active" if coach else "pending",
            "coach_until": None if plan == "l2" else iso(until), "coach_note": None, "support_link": SUPPORT_LINK}


@member.get("")
async def my_program(user: dict = Depends(user_dep())):
    d = db()
    plan = await plans.require(d, user, "program")
    uid = str(user["_id"])
    e = await ensure_enrollment(d, uid)
    cohort = await d.program_cohorts.find_one({"_id": e["cohort_id"]}) if e else None
    if not e or not cohort:
        return {"enrolled": False, "cohort": None, "days": [], "progress": _progress(None, []), "coach": None,
                "coach_status": "pending", "coach_note": None, "support_link": SUPPORT_LINK,
                "msg": "Your cohort is being set up. The team will add you soon."}
    now = utcnow()
    done = set(e.get("done") or [])
    days = [_day_out(x, done) for x in cohort.get("days") or []]
    nxt = next((x["n"] for x in cohort.get("days") or [] if x.get("when") and as_utc(x["when"]) + timedelta(hours=3) > now), None)
    starts = date.fromisoformat(cohort["start_date"])
    return {"enrolled": True, "plan": plan,
            "cohort": {"id": cohort["_id"], "name": cohort["name"], "start_date": cohort["start_date"],
                       "starts_in_days": max(0, (starts - ist_today()).days)},
            "days": days, "next_day": nxt, "progress": _progress(cohort, list(done)),
            "enrolled_at": iso(e.get("enrolled_at")), **_coach_view(plan, e, cohort, now)}


@member.post("/tasks/{task_id}")
async def tick(task_id: str, body: DoneIn, user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, "program")
    uid = str(user["_id"])
    e = await ensure_enrollment(d, uid)
    cohort = await d.program_cohorts.find_one({"_id": e["cohort_id"]}) if e else None
    if not cohort or task_id not in _all_tasks(cohort):
        raise _err(404, "not_found", "Task not found.")
    upd = {"$addToSet": {"done": task_id}} if body.done else {"$pull": {"done": task_id}}
    await d.program_enrollments.update_one({"_id": e["_id"]}, upd)
    e = await d.program_enrollments.find_one({"_id": e["_id"]})
    prog = _progress(cohort, e.get("done") or [])
    if body.done:
        await events.track(d, "program_task_done", user_id=uid, props={"task_id": task_id, "pct": prog["pct"]})
    return {"task_id": task_id, "done": body.done, "progress": prog}


# ------------------------------------------------------------------ admin: cohorts ----
async def _cohort(cid: str) -> dict:
    c = await db().program_cohorts.find_one({"_id": cid})
    if not c:
        raise _err(404, "not_found", "Cohort not found.")
    return c


@admin.get("/cohorts")
async def cohorts(_: dict = Admin):
    d = db()
    counts: dict[str, int] = {}
    async for r in d.program_enrollments.aggregate([{"$group": {"_id": "$cohort_id", "n": {"$sum": 1}}}]):
        counts[r["_id"]] = r["n"]
    rows = []
    async for c in d.program_cohorts.find({}).sort("start_date", -1):
        full = _cohort_full(c, counts.get(c["_id"], 0))
        full["day_count"] = len(full["days"])
        rows.append(full)
    return {"items": rows}


@admin.post("/cohorts")
async def cohort_add(body: CohortIn, _: dict = Admin):
    now = utcnow()
    doc = {"_id": uuid.uuid4().hex, "name": " ".join(body.name.split()), "start_date": _check_date(body.start_date),
           "active": body.active, "days": _days_in(body.days or []), "default_coach": _coach_in(body.default_coach),
           "created_at": now, "updated_at": now}
    await db().program_cohorts.insert_one(doc)
    return _cohort_full(doc)


@admin.get("/cohorts/{cid}")
async def cohort_one(cid: str, _: dict = Admin):
    c = await _cohort(cid)
    return _cohort_full(c, await db().program_enrollments.count_documents({"cohort_id": cid}))


@admin.put("/cohorts/{cid}")
async def cohort_edit(cid: str, body: CohortIn, _: dict = Admin):
    c = await _cohort(cid)
    upd = {"name": " ".join(body.name.split()), "start_date": _check_date(body.start_date), "active": body.active,
           "updated_at": utcnow()}
    if body.days is not None:
        upd["days"] = _days_in(body.days)
    if body.default_coach is not None:
        upd["default_coach"] = _coach_in(body.default_coach)
    await db().program_cohorts.update_one({"_id": cid}, {"$set": upd})
    if upd["start_date"] != c["start_date"]:           # month 1 moves with the start date (own coach dates kept)
        await db().program_enrollments.update_many(
            {"cohort_id": cid, "coach_set_until": {"$ne": True}},
            {"$set": {"coach_until": start_utc(upd["start_date"]) + timedelta(days=COACH_DAYS)}})
    return await cohort_one(cid, _)


@admin.delete("/cohorts/{cid}")
async def cohort_delete(cid: str, _: dict = Admin):
    await _cohort(cid)
    n = await db().program_enrollments.count_documents({"cohort_id": cid})
    if n:
        raise _err(409, "has_members", f"{n} member{'s' if n != 1 else ''} in this cohort. Move them first.")
    await db().program_cohorts.delete_one({"_id": cid})
    return {"ok": True}


@admin.put("/cohorts/{cid}/days/{n}")
async def day_save(cid: str, n: int, body: DayIn, _: dict = Admin):
    """Add day n, or replace it (body.n may renumber it)."""
    c = await _cohort(cid)
    days = [x for x in c.get("days") or [] if x["n"] != n]
    if any(x["n"] == body.n for x in days):
        raise _err(409, "dup_day", f"Day {body.n} already exists.")
    used = {t["id"] for x in days for t in x.get("tasks") or []}
    days = sorted(days + [_day_in(body, used)], key=lambda x: x["n"])
    await db().program_cohorts.update_one({"_id": cid}, {"$set": {"days": days, "updated_at": utcnow()}})
    return await cohort_one(cid, _)


@admin.delete("/cohorts/{cid}/days/{n}")
async def day_delete(cid: str, n: int, _: dict = Admin):
    c = await _cohort(cid)
    days = [x for x in c.get("days") or [] if x["n"] != n]
    await db().program_cohorts.update_one({"_id": cid}, {"$set": {"days": days, "updated_at": utcnow()}})
    return await cohort_one(cid, _)


@admin.put("/cohorts/{cid}/coach")
async def cohort_coach(cid: str, body: CoachIn, _: dict = Admin):
    """Default coach for everyone in the cohort who has no coach of their own. Empty name clears it."""
    await _cohort(cid)
    await db().program_cohorts.update_one({"_id": cid}, {"$set": {"default_coach": _coach_in(body), "updated_at": utcnow()}})
    return await cohort_one(cid, _)


# ------------------------------------------------------------------ admin: enrolments ----
async def _enrollment_rows(d, flt: dict) -> list[dict]:
    rows = [e async for e in d.program_enrollments.find(flt).sort("enrolled_at", -1).limit(2000)]
    oids = [o for o in (oid(e["user_id"]) for e in rows) if o]
    users = {str(u["_id"]): u async for u in d.users.find({"_id": {"$in": oids}}, {"name": 1, "phone": 1})}
    cohorts = {c["_id"]: c async for c in d.program_cohorts.find({"_id": {"$in": list({e["cohort_id"] for e in rows})}})}
    best = await plans.nonfree_plans(d)
    now = utcnow()
    out = []
    for e in rows:
        u = users.get(e["user_id"]) or {}
        c = cohorts.get(e["cohort_id"]) or {}
        p = best.get(e["user_id"], "free")
        own = _coach_out(e.get("coach"))
        until = as_utc(e["coach_until"]) if e.get("coach_until") else None
        out.append({"id": e["_id"], "user_id": e["user_id"], "name": u.get("name") or "", "phone": u.get("phone") or "",
                    "plan": p, "plan_label": plans.LABELS[p], "cohort_id": e["cohort_id"], "cohort_name": c.get("name") or "—",
                    "progress": _progress(c, e.get("done") or []), "coach": own or _coach_out(c.get("default_coach")),
                    "own_coach": bool(own), "coach_until": iso(until),
                    "coach_on": p == "l2" or bool(until and until > now), "enrolled_at": iso(e.get("enrolled_at"))})
    return out


@admin.get("/enrollments")
async def enrollments(cohort_id: Optional[str] = None, _: dict = Admin):
    return {"items": await _enrollment_rows(db(), {"cohort_id": cohort_id} if cohort_id else {})}


async def _enrollment(eid: str) -> dict:
    e = await db().program_enrollments.find_one({"_id": eid})
    if not e:
        raise _err(404, "not_found", "Enrolment not found.")
    return e


@admin.post("/enrollments/{eid}/move")
async def move(eid: str, body: MoveIn, _: dict = Admin):
    """Move a member to another cohort. Month 1 with the coach restarts from the new cohort's start date."""
    await _enrollment(eid)
    c = await _cohort(body.cohort_id)
    await db().program_enrollments.update_one({"_id": eid}, {
        "$set": {"cohort_id": c["_id"], "moved_at": utcnow(), "coach_set_until": False,
                 "coach_until": start_utc(c["start_date"]) + timedelta(days=COACH_DAYS)}})
    return (await _enrollment_rows(db(), {"_id": eid}))[0]


@admin.put("/enrollments/{eid}/coach")
async def member_coach(eid: str, body: CoachIn, _: dict = Admin):
    """The member's own coach (empty name = use the cohort's default). `until` (YYYY-MM-DD) changes the last coach day."""
    await _enrollment(eid)
    upd: dict = {"coach": _coach_in(body)}
    if body.until:
        try:
            last = date.fromisoformat(body.until)
        except ValueError:
            raise _err(400, "bad_date", "Coach until must be a real date (YYYY-MM-DD).")
        upd["coach_until"] = datetime(last.year, last.month, last.day, tzinfo=IST).astimezone(timezone.utc) + timedelta(days=1)
        upd["coach_set_until"] = True
    await db().program_enrollments.update_one({"_id": eid}, {"$set": upd})
    return (await _enrollment_rows(db(), {"_id": eid}))[0]


router.include_router(member)
router.include_router(admin)
