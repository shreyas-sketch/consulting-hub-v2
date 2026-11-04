"""Group calls with Akshat (L1: two a month, group only) and events (an L2 event uses plan_min "l2").

calls {_id, title, kind call|event, plan_min l1|l2, when (UTC datetime), duration_min, link, recording_url, notes,
       reminded: ["<stage>:<start epoch>"], created_at, updated_at}

Members see the calls their plan opens: feature `calls` (L1+); a call with plan_min "l2" needs feature `events`.
GET /calls/{id}.ics adds a call to the phone's calendar.
Job `call_reminders` (every 30 min): inbox alert 24 h and 1 h before the start, once per stage and start time
(editing the time sends fresh reminders), to members whose plan opens the call.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

import indexes
import plans
from core.deps import admin_dep, user_dep
from core.settings import settings
from growth.clock import IST, as_utc, utcnow
from jobs import registry
from notify import service as notify
from state import db
from util import iso

router = APIRouter(tags=["calls"])
member = APIRouter(prefix="/calls")
admin = APIRouter(prefix="/admin/calls")
Admin = Depends(admin_dep())

URL_RX = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.I)
ONE_HOUR_WINDOW = timedelta(minutes=70)     # the job runs every 30 min: "1 h before" lands 40–70 min before
DAY_WINDOW = timedelta(hours=24, minutes=10)

indexes.register("calls", [("when", 1)])
notify.register_kind("call")
registry.register("call_reminders", "Remind members of group calls and events (24 h and 1 h before)", ("every", 30),
                  "features.calls:job_reminders")


def _err(status: int, code: str, msg: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "msg": msg})


def parse_when(v: str) -> datetime:
    s = (v or "").strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(timezone.utc)


def _ist(dt: datetime) -> str:
    return as_utc(dt).astimezone(IST).isoformat()


def ist_label(dt: datetime) -> str:
    """'Sat 8 Nov, 7:00 pm IST'"""
    t = as_utc(dt).astimezone(IST)
    h = t.strftime("%I").lstrip("0")
    return f"{t.strftime('%a')} {t.day} {t.strftime('%b')}, {h}:{t.strftime('%M')} {t.strftime('%p').lower()} IST"


def _url(v: str, label: str) -> str:
    v = (v or "").strip()
    if v and not URL_RX.match(v):
        raise _err(400, "bad_link", f"{label} must start with https://")
    return v[:500]


def _feature(c: dict) -> str:
    return "events" if c.get("plan_min") == "l2" else "calls"


def _end(c: dict) -> datetime:
    return as_utc(c["when"]) + timedelta(minutes=int(c.get("duration_min") or 60))


def _out(c: dict, now: datetime, recap_id: Optional[str] = None) -> dict:
    start, end = as_utc(c["when"]), _end(c)
    over = end <= now
    return {"id": c["_id"], "title": c["title"], "kind": c.get("kind", "call"), "plan_min": c.get("plan_min", "l1"),
            "when": _ist(start), "ends_at": _ist(end), "when_label": ist_label(start),
            "duration_min": int(c.get("duration_min") or 60), "link": "" if over else (c.get("link") or ""),
            "recording_url": c.get("recording_url") or "", "notes": c.get("notes") or "",
            "live": start <= now < end, "over": over, "ics_url": f"/api/calls/{c['_id']}.ics", "recap_id": recap_id}


# ------------------------------------------------------------------ member ----
@member.get("")
async def listing(user: dict = Depends(user_dep())):
    d = db()
    plan = await plans.require(d, user, "calls")
    l2 = plans.plan_allows(plan, "events")
    flt: dict = {} if l2 else {"plan_min": {"$ne": "l2"}}
    now = utcnow()
    upcoming, past = [], []
    async for c in d.calls.find({**flt, "when": {"$gte": now - timedelta(hours=12)}}).sort("when", 1).limit(40):
        (upcoming if _end(c) > now else past).append(c)
    async for c in d.calls.find({**flt, "when": {"$lt": now - timedelta(hours=12)}}).sort("when", -1).limit(60):
        past.append(c)
    past.sort(key=lambda c: as_utc(c["when"]), reverse=True)
    recaps = {}
    if past:
        async for r in d.recaps.find({"call_id": {"$in": [c["_id"] for c in past]}, "status": "published"},
                                     {"call_id": 1}):
            recaps[r["call_id"]] = r["_id"]
    up = [_out(c, now) for c in upcoming[:20]]
    hidden = 0 if l2 else await d.calls.count_documents({"plan_min": "l2", "when": {"$gte": now}})
    return {"next": up[0] if up else None, "upcoming": up, "past": [_out(c, now, recaps.get(c["_id"])) for c in past],
            "l2_events_hidden": hidden}


async def _member_call(call_id: str, user: dict) -> dict:
    d = db()
    await plans.require(d, user, "calls")
    c = await d.calls.find_one({"_id": call_id})
    if not c:
        raise _err(404, "not_found", "Call not found.")
    if _feature(c) == "events":
        await plans.require(d, user, "events")
    return c


def _ics_text(v: str) -> str:
    return v.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: lines longer than 75 octets continue on the next line after a space."""
    if len(line.encode()) <= 75:
        return line
    parts, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > (75 if not parts else 74):
            parts.append(cur)
            cur = ch
        else:
            cur += ch
    parts.append(cur)
    return "\r\n ".join(parts)


def ics(c: dict, now: Optional[datetime] = None) -> str:
    fmt = "%Y%m%dT%H%M%SZ"
    now = now or utcnow()
    link = c.get("link") or ""
    desc = "\n\n".join(x for x in [f"Join: {link}" if link else "", c.get("notes") or ""] if x)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{_ics_text(settings.brand_name)}//Calls//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "BEGIN:VEVENT", f"UID:{c['_id']}@consultation-hub",
             f"DTSTAMP:{as_utc(now).strftime(fmt)}", f"DTSTART:{as_utc(c['when']).strftime(fmt)}",
             f"DTEND:{_end(c).strftime(fmt)}", f"SUMMARY:{_ics_text(c['title'])}"]
    if desc:
        lines.append(f"DESCRIPTION:{_ics_text(desc)}")
    if link:
        lines += [f"LOCATION:{_ics_text(link)}", f"URL:{link}"]
    lines += ["BEGIN:VALARM", "TRIGGER:-PT30M", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_text(c['title'])}", "END:VALARM",
              "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


@member.get("/{call_id}.ics")
async def calendar_file(call_id: str, user: dict = Depends(user_dep())):
    c = await _member_call(call_id, user)
    slug = re.sub(r"[^a-z0-9]+", "-", c["title"].lower()).strip("-")[:40] or "call"
    return Response(ics(c), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{slug}.ics"'})


@member.get("/{call_id}")
async def one(call_id: str, user: dict = Depends(user_dep())):
    c = await _member_call(call_id, user)
    r = await db().recaps.find_one({"call_id": c["_id"], "status": "published"}, {"_id": 1})
    return _out(c, utcnow(), r["_id"] if r else None)


# ------------------------------------------------------------------ reminders job ----
async def job_reminders(ctx) -> dict:
    d, now = ctx.db, as_utc(ctx.now)
    calls_n, sent = 0, 0
    async for c in d.calls.find({"when": {"$gt": now, "$lte": now + DAY_WINDOW}}).sort("when", 1):
        start = as_utc(c["when"])
        stage = "1h" if start - now <= ONE_HOUR_WINDOW else "24h"
        key = f"{stage}:{int(start.timestamp())}"
        if key in (c.get("reminded") or []):
            continue
        what = "Event" if c.get("kind") == "event" else "Group call"
        if stage == "1h":
            title, body = f"{what} in 1 hour: {c['title']}", f"Starts at {ist_label(start)}. Open Calls to join."
        else:
            title, body = f"{what} coming up: {c['title']}", f"{ist_label(start)}. Add it to your calendar from Calls."
        users = await plans.users_with(d, _feature(c), now)
        n = await notify.alert_many(d, users, "call", title, body, link="/app/calls", dedupe=f"call:{c['_id']}:{key}")
        await d.calls.update_one({"_id": c["_id"]}, {"$addToSet": {"reminded": key}})
        calls_n += 1
        sent += n
    return {"calls": calls_n, "sent": sent}


# ------------------------------------------------------------------ admin ----
class CallIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=140)
    kind: Literal["call", "event"] = "call"
    plan_min: Literal["l1", "l2"] = "l1"
    when: str = Field(..., min_length=10, max_length=40)
    duration_min: int = Field(60, ge=15, le=720)
    link: str = Field("", max_length=500)
    recording_url: str = Field("", max_length=500)
    notes: str = Field("", max_length=2000)


def _fields(body: CallIn) -> dict:
    try:
        when = parse_when(body.when)
    except ValueError:
        raise _err(400, "bad_date", "Date and time must look like 2026-11-08T19:00 (IST).")
    return {"title": " ".join(body.title.split()), "kind": body.kind, "plan_min": body.plan_min, "when": when,
            "duration_min": body.duration_min, "link": _url(body.link, "Join link"),
            "recording_url": _url(body.recording_url, "Recording link"), "notes": body.notes.strip()}


def _admin_row(c: dict, now: datetime) -> dict:
    return {**_out(c, now), "link": c.get("link") or "", "reminded": c.get("reminded") or [],
            "created_at": iso(c.get("created_at"))}


@admin.get("")
async def admin_list(_: dict = Admin):
    now = utcnow()
    return {"items": [_admin_row(c, now) async for c in db().calls.find({}).sort("when", -1).limit(300)]}


@admin.post("")
async def admin_add(body: CallIn, _: dict = Admin):
    now = utcnow()
    doc = {"_id": uuid.uuid4().hex, **_fields(body), "reminded": [], "created_at": now, "updated_at": now}
    await db().calls.insert_one(doc)
    return _admin_row(doc, now)


@admin.put("/{call_id}")
async def admin_edit(call_id: str, body: CallIn, _: dict = Admin):
    d = db()
    if not await d.calls.find_one({"_id": call_id}, {"_id": 1}):
        raise _err(404, "not_found", "Call not found.")
    await d.calls.update_one({"_id": call_id}, {"$set": {**_fields(body), "updated_at": utcnow()}})
    return _admin_row(await d.calls.find_one({"_id": call_id}), utcnow())


@admin.delete("/{call_id}")
async def admin_delete(call_id: str, _: dict = Admin):
    r = await db().calls.delete_one({"_id": call_id})
    if not r.deleted_count:
        raise _err(404, "not_found", "Call not found.")
    return {"ok": True}


router.include_router(member)
router.include_router(admin)
