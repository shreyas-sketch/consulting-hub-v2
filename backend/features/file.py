"""My Consulting File: everything the member has made, on one page they can print or save as PDF.

Reads only; nothing is metered. Free accounts keep their file after the webinar (view-only).
GET /file is also what Home reads for its progress, so it records nothing; the File page itself calls
POST /file/viewed once when it opens (the "file_viewed" event behind the admin webinar report).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from core.deps import user_dep
from growth import events
from state import db

from . import brief, linkedin, readiness, start
from .knowledge import knowledge
from .case_bank import CRITERIA

router = APIRouter(prefix="/file", tags=["consulting-file"])


@router.get("")
async def my_file(user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    r = await d.readiness.find_one({"user_id": uid}, sort=[("at", -1)])
    sp = await start.mine(user)
    li = await d.linkedin_checks.find_one({"user_id": uid}, sort=[("at", -1)])
    briefs = [brief._public(b) async for b in d.briefs.find({"user_id": uid}).sort("at", -1).limit(5)]
    titles = {c["_id"]: c["title"] async for c in d.cases.find({}, {"title": 1})}
    answers = [{"case_id": a["case_id"], "title": titles.get(a["case_id"], a["case_id"]), "overall": a["overall"],
                "scores": a["scores"], "at": a["at"].isoformat() if hasattr(a["at"], "isoformat") else a["at"]}
               async for a in d.case_answers.find({"user_id": uid}).sort("at", -1).limit(10)]
    snap = sp["snapshot"]
    niche = snap["options"][snap.get("chosen") or 0] if snap and snap.get("options") else None
    return {"name": user.get("name"), "readiness": readiness._public(r) if r else None, "niche": niche,
            "snapshot": snap, "goal": sp["goal"], "linkedin": linkedin._public(li) if li else None,
            "cases": answers, "criteria": [{"key": k, "label": lbl} for k, lbl in CRITERIA], "briefs": briefs,
            "knowledge": await knowledge(d, user)}


@router.post("/viewed")
async def viewed(user: dict = Depends(user_dep())):
    """The File page was opened (once per visit, from the page itself, not from Home's progress read)."""
    await events.track(db(), "file_viewed", user_id=str(user["_id"]))
    return {"ok": True}
