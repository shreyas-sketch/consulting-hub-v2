"""Bootcamps (L2): build the practice step by step, with tasks the team reviews.

bootcamps            {_id, n, title, description, tasks: [{id, title, detail}], resources: [{title, url}], published,
                      created_at, updated_at}
bootcamp_submissions {_id, user_id, bootcamp_id, task_id, text, link, status submitted|reviewed, feedback, at,
                      reviewed_at?, reviewed_by?}  — one per member per task (updated in place)

No big uploads: members share a link (Google Drive and the like) and/or a written answer. Editing an answer after
review sends it back to "submitted" (the earlier feedback stays visible). A review sends the member an inbox alert.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import indexes
import plans
from core.deps import admin_dep, user_dep
from core.errors import AppError, error
from growth import events
from growth.clock import utcnow
from notify import service as notify
from state import db
from util import iso, oid

router = APIRouter(tags=["bootcamps"])
member = APIRouter(prefix="/bootcamps")
admin = APIRouter(prefix="/admin/bootcamps")
Admin = Depends(admin_dep())

URL_RX = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.I)
TASK_ID_RX = re.compile(r"^[a-z0-9]{4,40}$")

indexes.register("bootcamps", [("published", 1), ("n", 1)])
indexes.register("bootcamp_submissions", [("user_id", 1), ("bootcamp_id", 1), ("task_id", 1)], {"unique": True})
indexes.register("bootcamp_submissions", [("bootcamp_id", 1), ("at", -1)])
notify.register_kind("bootcamp")
events.register("bootcamp_submitted", "Bootcamp task sent for review (props.bootcamp_id, props.task_id)")
events.register("bootcamp_reviewed", "Team reviewed a bootcamp task (props.bootcamp_id, props.task_id)")


def _err(status: int, code: str, msg: str) -> AppError:
    return error(status, code, msg)


def _url(v: str, label: str) -> str:
    v = (v or "").strip()
    if v and not URL_RX.match(v):
        raise _err(400, "bad_link", f"{label} must start with https://")
    return v[:500]


def _progress(b: dict, subs: list[dict]) -> dict:
    ids = {t["id"] for t in b.get("tasks") or []}
    mine = [s for s in subs if s["task_id"] in ids]
    sub = len(mine)
    rev = sum(1 for s in mine if s.get("status") == "reviewed")
    return {"submitted": sub, "reviewed": rev, "total": len(ids), "pct": round(sub * 100 / len(ids)) if ids else 0}


def _sub_out(s: Optional[dict]) -> Optional[dict]:
    if not s:
        return None
    return {"id": s["_id"], "text": s.get("text") or "", "link": s.get("link") or "", "status": s.get("status", "submitted"),
            "feedback": s.get("feedback") or "", "at": iso(s.get("at")), "reviewed_at": iso(s.get("reviewed_at"))}


def _card(b: dict, subs: list[dict]) -> dict:
    return {"id": b["_id"], "n": int(b.get("n") or 0), "title": b["title"], "description": b.get("description") or "",
            "tasks": len(b.get("tasks") or []), "progress": _progress(b, subs)}


# ------------------------------------------------------------------ member ----
async def _mine(uid: str, bootcamp_id: Optional[str] = None) -> list[dict]:
    flt = {"user_id": uid, **({"bootcamp_id": bootcamp_id} if bootcamp_id else {})}
    return [s async for s in db().bootcamp_submissions.find(flt)]


@member.get("")
async def listing(user: dict = Depends(user_dep())):
    await plans.require(db(), user, "bootcamps")
    subs = await _mine(str(user["_id"]))
    out = []
    async for b in db().bootcamps.find({"published": True}).sort("n", 1):
        out.append(_card(b, [s for s in subs if s["bootcamp_id"] == b["_id"]]))
    return {"items": out}


async def _bootcamp_for(user: dict, bootcamp_id: str) -> dict:
    await plans.require(db(), user, "bootcamps")
    b = await db().bootcamps.find_one({"_id": bootcamp_id})
    if not b or (not b.get("published") and user.get("role") != "admin"):
        raise _err(404, "not_found", "Bootcamp not found.")
    return b


def _detail(b: dict, subs: list[dict]) -> dict:
    by_task = {s["task_id"]: s for s in subs}
    return {**_card(b, subs), "resources": b.get("resources") or [],
            "task_list": [{"id": t["id"], "title": t["title"], "detail": t.get("detail") or "",
                           "submission": _sub_out(by_task.get(t["id"]))} for t in b.get("tasks") or []]}


@member.get("/{bootcamp_id}")
async def one(bootcamp_id: str, user: dict = Depends(user_dep())):
    b = await _bootcamp_for(user, bootcamp_id)
    return _detail(b, await _mine(str(user["_id"]), bootcamp_id))


class SubmitIn(BaseModel):
    text: str = Field("", max_length=4000)
    link: str = Field("", max_length=500)


@member.post("/{bootcamp_id}/tasks/{task_id}")
async def submit(bootcamp_id: str, task_id: str, body: SubmitIn, user: dict = Depends(user_dep())):
    """Send a task for review, or update it."""
    b = await _bootcamp_for(user, bootcamp_id)
    if task_id not in {t["id"] for t in b.get("tasks") or []}:
        raise _err(404, "not_found", "Task not found.")
    txt = body.text.strip()
    link = _url(body.link, "The link")
    if not txt and not link:
        raise _err(400, "empty", "Write your answer or add a link to your work.")
    uid = str(user["_id"])
    now = utcnow()
    await db().bootcamp_submissions.update_one(
        {"user_id": uid, "bootcamp_id": bootcamp_id, "task_id": task_id},
        {"$set": {"text": txt, "link": link, "status": "submitted", "at": now},
         "$setOnInsert": {"_id": uuid.uuid4().hex, "feedback": ""}}, upsert=True)
    await events.track(db(), "bootcamp_submitted", user_id=uid, props={"bootcamp_id": bootcamp_id, "task_id": task_id})
    return _detail(b, await _mine(uid, bootcamp_id))


# ------------------------------------------------------------------ admin ----
class TaskIn(BaseModel):
    id: Optional[str] = Field(None, max_length=40)
    title: str = Field(..., min_length=2, max_length=160)
    detail: str = Field("", max_length=2000)


class ResourceIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=140)
    url: str = Field(..., min_length=8, max_length=500)


class BootcampIn(BaseModel):
    n: int = Field(1, ge=1, le=50)
    title: str = Field(..., min_length=2, max_length=140)
    description: str = Field("", max_length=2000)
    tasks: list[TaskIn] = Field(default_factory=list, max_length=30)
    resources: list[ResourceIn] = Field(default_factory=list, max_length=30)
    published: bool = False


def _fields(body: BootcampIn) -> dict:
    used: set[str] = set()
    tasks = []
    for t in body.tasks:
        tid = (t.id or "").strip().lower()
        if not TASK_ID_RX.match(tid) or tid in used:
            tid = uuid.uuid4().hex[:10]
        used.add(tid)
        tasks.append({"id": tid, "title": " ".join(t.title.split()), "detail": t.detail.strip()})
    res = [{"title": " ".join(r.title.split()), "url": _url(r.url, f"Link for \"{r.title[:40]}\"")} for r in body.resources]
    return {"n": body.n, "title": " ".join(body.title.split()), "description": body.description.strip(), "tasks": tasks,
            "resources": res, "published": body.published}


async def _bootcamp(bootcamp_id: str) -> dict:
    b = await db().bootcamps.find_one({"_id": bootcamp_id})
    if not b:
        raise _err(404, "not_found", "Bootcamp not found.")
    return b


async def _admin_row(b: dict) -> dict:
    d = db()
    ids = {t["id"] for t in b.get("tasks") or []}
    subs = [s async for s in d.bootcamp_submissions.find({"bootcamp_id": b["_id"]}, {"user_id": 1, "task_id": 1, "status": 1})]
    subs = [s for s in subs if s["task_id"] in ids]
    return {"id": b["_id"], "n": int(b.get("n") or 0), "title": b["title"], "description": b.get("description") or "",
            "tasks": [{"id": t["id"], "title": t["title"], "detail": t.get("detail") or ""} for t in b.get("tasks") or []],
            "resources": b.get("resources") or [], "published": bool(b.get("published")),
            "members": len({s["user_id"] for s in subs}), "submissions": len(subs),
            "to_review": sum(1 for s in subs if s.get("status") != "reviewed"),
            "created_at": iso(b.get("created_at"))}


@admin.get("")
async def admin_list(_: dict = Admin):
    return {"items": [await _admin_row(b) async for b in db().bootcamps.find({}).sort("n", 1)]}


@admin.post("")
async def admin_add(body: BootcampIn, _: dict = Admin):
    now = utcnow()
    doc = {"_id": uuid.uuid4().hex, **_fields(body), "created_at": now, "updated_at": now}
    await db().bootcamps.insert_one(doc)
    return await _admin_row(doc)


@admin.put("/{bootcamp_id}")
async def admin_edit(bootcamp_id: str, body: BootcampIn, _: dict = Admin):
    await _bootcamp(bootcamp_id)
    await db().bootcamps.update_one({"_id": bootcamp_id}, {"$set": {**_fields(body), "updated_at": utcnow()}})
    return await _admin_row(await _bootcamp(bootcamp_id))


@admin.delete("/{bootcamp_id}")
async def admin_delete(bootcamp_id: str, _: dict = Admin):
    await _bootcamp(bootcamp_id)
    await db().bootcamps.delete_one({"_id": bootcamp_id})
    r = await db().bootcamp_submissions.delete_many({"bootcamp_id": bootcamp_id})
    return {"ok": True, "submissions_deleted": r.deleted_count}


@admin.get("/{bootcamp_id}/submissions")
async def admin_submissions(bootcamp_id: str, status: Optional[str] = None, _: dict = Admin):
    """Every submission for the bootcamp (newest first) and each member's completion %."""
    d = db()
    b = await _bootcamp(bootcamp_id)
    tasks = {t["id"]: t for t in b.get("tasks") or []}
    subs = [s async for s in d.bootcamp_submissions.find({"bootcamp_id": bootcamp_id}).sort("at", -1).limit(3000)
            if s["task_id"] in tasks]
    oids = [o for o in {oid(s["user_id"]) for s in subs} if o]
    users = {str(u["_id"]): u async for u in d.users.find({"_id": {"$in": oids}}, {"name": 1, "phone": 1})}
    members: dict[str, list] = {}
    for s in subs:
        members.setdefault(s["user_id"], []).append(s)
    rows = [{**_sub_out(s), "user_id": s["user_id"], "name": (users.get(s["user_id"]) or {}).get("name") or "",
             "phone": (users.get(s["user_id"]) or {}).get("phone") or "", "task_id": s["task_id"],
             "task_title": tasks[s["task_id"]]["title"]}
            for s in subs if not status or s.get("status") == status]
    people = sorted([{"user_id": u, "name": (users.get(u) or {}).get("name") or "", "phone": (users.get(u) or {}).get("phone") or "",
                      **_progress(b, ss), "last_at": iso(max(x["at"] for x in ss))} for u, ss in members.items()],
                    key=lambda x: (-x["pct"], x["name"]))
    return {"bootcamp": await _admin_row(b), "items": rows, "members": people}


class ReviewIn(BaseModel):
    feedback: str = Field(..., min_length=2, max_length=3000)


@admin.post("/submissions/{sub_id}/review")
async def admin_review(sub_id: str, body: ReviewIn, admin_user: dict = Admin):
    d = db()
    s = await d.bootcamp_submissions.find_one({"_id": sub_id})
    if not s:
        raise _err(404, "not_found", "Submission not found.")
    b = await d.bootcamps.find_one({"_id": s["bootcamp_id"]}) or {"title": "Bootcamp", "tasks": []}
    now = utcnow()
    await d.bootcamp_submissions.update_one({"_id": sub_id}, {"$set": {
        "status": "reviewed", "feedback": body.feedback.strip(), "reviewed_at": now, "reviewed_by": str(admin_user["_id"])}})
    task = next((t for t in b.get("tasks") or [] if t["id"] == s["task_id"]), {"title": "your task"})
    await notify.alert(d, s["user_id"], "bootcamp", "The team reviewed your bootcamp task",
                       f"{b['title']}: {task['title']}. Open it to read the feedback.",
                       link=f"/app/bootcamps/{s['bootcamp_id']}", dedupe=f"bootcamp-review:{sub_id}:{int(now.timestamp())}")
    await events.track(d, "bootcamp_reviewed", user_id=s["user_id"], props={"bootcamp_id": s["bootcamp_id"], "task_id": s["task_id"]})
    return {**_sub_out(await d.bootcamp_submissions.find_one({"_id": sub_id})), "task_id": s["task_id"],
            "user_id": s["user_id"]}


router.include_router(member)
router.include_router(admin)
