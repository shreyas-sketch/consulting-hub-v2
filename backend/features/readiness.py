"""Readiness Score: six consulting skills rated 1–10 (total /60) plus a gut check on potential (0–10).

readiness {_id, user_id, scores: {skill: n}, potential, total, band, at}

Rule-based (no AI), so hundreds of people on the webinar get their score instantly at no cost.
Free: once. Paid: once a month, with the change since last time.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.deps import user_dep
from growth import events
from growth.clock import utcnow
from state import db
from util import iso

from .common import run_metered

router = APIRouter(prefix="/readiness", tags=["readiness"])

SKILLS = [
    {"key": "diagnosis", "name": "Problem diagnosis", "ask": "Finding the real problem behind what a client says",
     "next": "Answer the weekly case and write the root cause before you write any fix."},
    {"key": "offer", "name": "Offer clarity", "ask": "Saying in one line who you help and what result they get",
     "next": "Write your one-line offer: I help [who] get [result] in [time]."},
    {"key": "acquisition", "name": "Client acquisition", "ask": "Getting conversations with people who could pay you",
     "next": "List 20 people in your network who run or manage a business."},
    {"key": "pricing", "name": "Pricing confidence", "ask": "Quoting a fee without dropping it",
     "next": "Pick a fee for your first project and practise saying it out loud."},
    {"key": "delivery", "name": "Delivery & frameworks", "ask": "Running a client project step by step with a framework",
     "next": "Solve one case a week with a framework, then compare with the model answer."},
    {"key": "visibility", "name": "Visibility & authority", "ask": "Being known for your niche on LinkedIn and elsewhere",
     "next": "Run the LinkedIn Score and fix the top problem first."},
]
KEYS = [s["key"] for s in SKILLS]
BANDS = [(50, "Launch-ready", "You have the base. Now it's about getting in front of clients."),
         (40, "Nearly ready", "A few gaps to close, and you can start conversations with clients."),
         (25, "Building", "Good experience. Work on the two lowest skills first."),
         (0, "Starting out", "Everyone starts here. Pick one skill and work on it this month.")]


class ReadinessIn(BaseModel):
    scores: dict[str, int] = Field(...)
    potential: int = Field(..., ge=0, le=10)


def score(scores: dict[str, int], potential: int) -> dict:
    clean = {k: max(1, min(10, int(scores.get(k, 1)))) for k in KEYS}
    total = sum(clean.values())
    band = next(b for b in BANDS if total >= b[0])
    weakest = sorted(SKILLS, key=lambda s: (clean[s["key"]], KEYS.index(s["key"])))[:2]
    return {"scores": clean, "potential": potential, "total": total, "max": 60, "band": band[1], "band_note": band[2],
            "focus": [{"key": s["key"], "name": s["name"], "score": clean[s["key"]], "next": s["next"]} for s in weakest],
            "gap_to_potential": max(0, potential * 6 - total)}


def _public(doc: dict) -> dict:
    return {"id": doc["_id"], **score(doc["scores"], doc["potential"]), "at": iso(doc["at"])}


@router.get("/skills")
async def skills():
    return {"skills": SKILLS, "bands": [{"from": b[0], "name": b[1]} for b in BANDS]}


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    rows = [_public(d) async for d in db().readiness.find({"user_id": str(user["_id"])}).sort("at", -1).limit(12)]
    return {"latest": rows[0] if rows else None, "history": rows}


@router.post("")
async def save(body: ReadinessIn, user: dict = Depends(user_dep())):
    uid = str(user["_id"])

    async def work(plan: str):
        prev = await db().readiness.find_one({"user_id": uid}, sort=[("at", -1)])
        res = score(body.scores, body.potential)
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "scores": res["scores"], "potential": body.potential,
               "total": res["total"], "band": res["band"], "at": utcnow()}
        await db().readiness.insert_one(doc)
        await events.track(db(), "readiness_done", user_id=uid, props={"total": res["total"], "potential": body.potential})
        out = _public(doc)
        out["change"] = res["total"] - prev["total"] if prev else None
        return out
    return await run_metered(db(), user, "readiness", work)
