"""Support (₹1,999 plan and up): a member writes to the team; the team answers from Admin › Support inbox.

support_tickets {_id, user_id, subject, category billing|tools|program|other, status open|answered|closed,
                 messages: [{from: member|team, text, at, by, by_name?}], created_at, updated_at, last_from}

A team reply marks the ticket answered and sends an inbox alert. A member reply (also on a closed ticket) opens it
again, unless that would go past MAX_OPEN open tickets. Members never see which team member wrote: replies show as
"Support team".
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import indexes
import plans
from core.deps import admin_dep, user_dep
from growth import events
from growth.clock import utcnow
from notify import service as notify
from state import db
from util import iso

from .common import text

router = APIRouter(tags=["support"])

MAX_OPEN = 10
STATUSES = ("open", "answered", "closed")

indexes.register("support_tickets", [("user_id", 1), ("updated_at", -1)])
indexes.register("support_tickets", [("status", 1), ("updated_at", -1)])
events.register("support_ticket_opened", "Member opened a support ticket (props.category)")
events.register("support_member_reply", "Member replied on a support ticket")
events.register("support_team_reply", "Team replied on a support ticket (props.ticket_id)")
notify.register_kind("support")


class TicketIn(BaseModel):
    subject: str = Field(..., min_length=3, max_length=140)
    category: Literal["billing", "tools", "program", "other"] = "other"
    text: str = Field(..., min_length=5, max_length=4000)


class ReplyIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


def _msg(m: dict, team_view: bool) -> dict:
    out = {"from": m["from"], "text": m["text"], "at": iso(m.get("at"))}
    if team_view:
        out["by_name"] = m.get("by_name")
    return out


def _row(t: dict) -> dict:
    msgs = t.get("messages") or []
    return {"id": t["_id"], "subject": t["subject"], "category": t["category"], "status": t["status"],
            "count": len(msgs), "last_from": msgs[-1]["from"] if msgs else None,
            "preview": text(msgs[-1]["text"], 120) if msgs else "",
            "created_at": iso(t.get("created_at")), "updated_at": iso(t.get("updated_at"))}


def _public(t: dict, team_view: bool = False) -> dict:
    return _row(t) | {"messages": [_msg(m, team_view) for m in t.get("messages") or []]}


async def _mine(ticket_id: str, user: dict) -> dict:
    t = await db().support_tickets.find_one({"_id": ticket_id, "user_id": str(user["_id"])})
    if not t:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Ticket not found."})
    return t


# ------------------------------------------------------------------ member ----
async def _room_to_open(d, uid: str) -> None:
    if await d.support_tickets.count_documents({"user_id": uid, "status": {"$ne": "closed"}}) >= MAX_OPEN:
        raise HTTPException(status_code=429, detail={"code": "too_many", "msg": (
            f"You have {MAX_OPEN} open questions with the team. Close one you no longer need, or add to an open one.")})


@router.post("/support/tickets")
async def open_ticket(body: TicketIn, user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, "support")
    uid = str(user["_id"])
    await _room_to_open(d, uid)
    now = utcnow()
    t = {"_id": uuid.uuid4().hex, "user_id": uid, "subject": " ".join(body.subject.split()), "category": body.category,
         "status": "open", "messages": [{"from": "member", "text": body.text.strip(), "at": now, "by": uid}],
         "created_at": now, "updated_at": now, "last_from": "member"}
    await d.support_tickets.insert_one(t)
    await events.track(d, "support_ticket_opened", user_id=uid, props={"category": body.category})
    return _public(t)


@router.get("/support/tickets")
async def my_tickets(user: dict = Depends(user_dep())):
    cur = db().support_tickets.find({"user_id": str(user["_id"])}).sort("updated_at", -1).limit(100)
    return {"items": [_row(t) async for t in cur]}


@router.get("/support/tickets/{ticket_id}")
async def my_ticket(ticket_id: str, user: dict = Depends(user_dep())):
    return _public(await _mine(ticket_id, user))


@router.post("/support/tickets/{ticket_id}/reply")
async def member_reply(ticket_id: str, body: ReplyIn, user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, "support")
    t = await _mine(ticket_id, user)
    msg = body.text.strip()
    if not msg:
        raise HTTPException(status_code=422, detail={"code": "empty", "msg": "Type your message first."})
    if t.get("status") == "closed":
        await _room_to_open(d, str(user["_id"]))            # replying reopens it: same limit as a new question
    now = utcnow()
    await d.support_tickets.update_one({"_id": t["_id"]}, {
        "$push": {"messages": {"from": "member", "text": msg, "at": now, "by": str(user["_id"])}},
        "$set": {"status": "open", "updated_at": now, "last_from": "member"}})
    await events.track(d, "support_member_reply", user_id=str(user["_id"]))
    return _public(await d.support_tickets.find_one({"_id": t["_id"]}))


@router.post("/support/tickets/{ticket_id}/close")
async def member_close(ticket_id: str, user: dict = Depends(user_dep())):
    t = await _mine(ticket_id, user)
    await db().support_tickets.update_one({"_id": t["_id"]}, {"$set": {"status": "closed", "updated_at": utcnow()}})
    return _public(await db().support_tickets.find_one({"_id": t["_id"]}))


# ------------------------------------------------------------------ admin ----
async def _people(d, uids: list[str]) -> dict[str, dict]:
    oids = [ObjectId(u) for u in set(uids) if ObjectId.is_valid(u)]
    if not oids:
        return {}
    return {str(u["_id"]): u async for u in d.users.find({"_id": {"$in": oids}}, {"name": 1, "phone": 1, "email": 1})}


def _member(u: Optional[dict], plan: str) -> dict:
    u = u or {}
    return {"name": u.get("name"), "phone": u.get("phone"), "email": u.get("email"), "plan": plan,
            "plan_label": plans.LABELS.get(plan, plan)}


async def _ticket(ticket_id: str) -> dict:
    t = await db().support_tickets.find_one({"_id": ticket_id})
    if not t:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Ticket not found."})
    return t


async def _admin_view(d, t: dict) -> dict:
    u = (await _people(d, [t["user_id"]])).get(t["user_id"])
    plan = (await plans.effective_plan(d, u))["plan"] if u else "free"
    return _public(t, team_view=True) | {"user_id": t["user_id"], "member": _member(u, plan)}


@router.get("/admin/support")
async def admin_inbox(status: Optional[str] = Query(None, pattern="^(open|answered|closed)$"),
                      q: Optional[str] = Query(None, max_length=80), _: dict = Depends(admin_dep())):
    d = db()
    flt: dict = {"status": status} if status else {}
    rows = [t async for t in d.support_tickets.find(flt).sort("updated_at", 1 if status == "open" else -1).limit(500)]
    people = await _people(d, [t["user_id"] for t in rows])
    best = await plans.nonfree_plans(d)
    items = []
    for t in rows:
        m = _member(people.get(t["user_id"]), best.get(t["user_id"], "free"))
        if q:
            needle = q.strip().lower()
            hay = " ".join(str(x or "") for x in (t["subject"], m["name"], m["phone"], m["email"])).lower()
            if needle not in hay:
                continue
        items.append(_row(t) | {"user_id": t["user_id"], "member": m})
    counts = {s: await d.support_tickets.count_documents({"status": s}) for s in STATUSES}
    return {"items": items, "counts": counts, "open": counts["open"]}


@router.get("/admin/support/{ticket_id}")
async def admin_ticket(ticket_id: str, _: dict = Depends(admin_dep())):
    d = db()
    return await _admin_view(d, await _ticket(ticket_id))


@router.post("/admin/support/{ticket_id}/reply")
async def admin_reply(ticket_id: str, body: ReplyIn, admin: dict = Depends(admin_dep())):
    d = db()
    t = await _ticket(ticket_id)
    msg = body.text.strip()
    if not msg:
        raise HTTPException(status_code=422, detail={"code": "empty", "msg": "Type the reply first."})
    now = utcnow()
    await d.support_tickets.update_one({"_id": t["_id"]}, {
        "$push": {"messages": {"from": "team", "text": msg, "at": now, "by": str(admin["_id"]),
                               "by_name": admin.get("name") or admin.get("email") or "Team"}},
        "$set": {"status": "answered", "updated_at": now, "last_from": "team"}})
    await notify.alert(d, t["user_id"], "support", f"The team replied: {text(t['subject'], 90)}", text(msg, 400),
                       link=f"/app/support/{t['_id']}")
    await events.track(d, "support_team_reply", user_id=t["user_id"], props={"ticket_id": t["_id"]})
    return await _admin_view(d, await _ticket(ticket_id))


@router.post("/admin/support/{ticket_id}/close")
async def admin_close(ticket_id: str, _: dict = Depends(admin_dep())):
    d = db()
    t = await _ticket(ticket_id)
    await d.support_tickets.update_one({"_id": t["_id"]}, {"$set": {"status": "closed", "updated_at": utcnow()}})
    return await _admin_view(d, await _ticket(ticket_id))
