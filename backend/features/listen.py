"""Listen mode: hear a case or a Meeting Brief as audio, on a walk or in the car.

audio_tracks {_id, user_id, source case|brief, ref_id, title, sub, script, words, blob_id, content_type,
              shared, made_by_me, at}

POST /listen {source, id}: the AI writes a spoken script (600 words at most; for a case: situation, facts, question,
a pause, then the model answer) → text to speech → saved as a blob → audio url.
The same member + source + id plays again for free. The weekly case from real news is made once and shared: its
blob is public and every member after the first gets it free (it counts for the member who made it first).
"""
from __future__ import annotations

import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import indexes
import llm
import media
import plans
from audio import tts
from core.deps import user_dep
from growth import events
from growth.clock import utcnow
from state import db
from util import iso

from .case_bank import model_answer_text
from .common import run_metered, text

router = APIRouter(prefix="/listen", tags=["listen"])

events.register("audio_made", "Listen mode audio made (props.source, shared)")
indexes.register("audio_tracks", [("user_id", 1), ("source", 1), ("ref_id", 1)])
indexes.register("audio_tracks", [("source", 1), ("ref_id", 1), ("shared", 1)])

MAX_WORDS = 600
SYSTEM = (
    "You write a script to be read aloud for a senior Indian professional who is becoming a consultant. They listen "
    "on a walk or in the car, so write for the ear: short sentences, natural spoken English, no lists, no headings, no "
    "symbols or abbreviations that read badly aloud. Say rupee amounts in words the way Indians say them (one lakh fifty "
    "thousand rupees, twelve crore rupees). Use only the facts given. At most 550 words. Never mention AI providers, "
    'models, courses or upsells. JSON: {"script": ""}'
)


class ListenIn(BaseModel):
    source: Literal["case", "brief"]
    id: str = Field(..., min_length=1, max_length=64)


def is_shared_case(c: dict) -> bool:
    return c.get("origin") == "news" or c.get("kind") == "weekly"


def _cut(script: str, n: int = MAX_WORDS) -> str:
    words = script.split()
    if len(words) <= n:
        return script
    cut = " ".join(words[:n])
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return cut[:end + 1] if end > len(cut) // 2 else cut + "."


def _case_prompt(c: dict) -> str:
    facts = "\n".join(f"- {f}" for f in c.get("facts", []))
    return (f"Write the audio version of this business case. Order: a one-line welcome and the case title; the "
            f"situation; the facts; the question; then say 'Pause here and think about your answer.'; then the model "
            f"answer walked through the six steps.\n\nCASE: {c['title']} ({c['company']}, {c['industry']}, "
            f"{c.get('city') or 'India'})\nSituation: {c['situation']}\nFacts:\n{facts}\nQuestion: {c['question']}\n\n"
            f"MODEL ANSWER:\n{model_answer_text(c['model_answer'])}")


def _case_fake(c: dict) -> dict:
    m = c["model_answer"]
    o = m["objective"]
    facts = " ".join(f"{f}." if not f.endswith(".") else f for f in c.get("facts", []))
    opts = " ".join(f"From {x['source'].lower()}: {x['option']}." for x in m["options"])
    return {"script": (
        f"Welcome. This case is called {c['title']}. It's about {c['company']}, in {c['industry'].replace('·', ',')}. "
        f"{c['situation']} Here are the facts. {facts} The question is this. {c['question']} "
        "Pause here and think about your answer. Now, the model answer. "
        f"Step one, scope. The client says: {m['scope_before']} The real problem is this: {m['scope_after']} "
        f"Step two, the objective. Go from {o['from']} to {o['to']} in {o['by']}. {m['success']} "
        f"Step three, the framework: {m['framework']}. {m['finding']} Step four, the options. {opts} "
        f"Step five, do first: {m['do_first']} Step six, the charter. The owner is {m['charter']['owner']}. "
        f"Track {m['charter']['leading']}, and {m['charter']['lagging']}. Same six steps, every problem, every time.")}


def _brief_prompt(b: dict) -> str:
    news = "\n".join(f"- {n['title']}: {n.get('why', '')}" for n in b.get("news") or [])
    probs = "\n".join(f"- {p['problem']}: {p.get('why', '')}" for p in b.get("problems") or [])
    qs = "\n".join(f"- {q}" for q in b.get("questions") or [])
    return (f"Write the audio version of this Meeting Brief, so they can prepare on the way to the meeting. Order: who "
            f"they are meeting and why; what the company does; the news that matters; the likely problems; the "
            f"questions to ask; the opening line.\n\nCompany: {b['input']['company']}\nMeeting with: "
            f"{b['input'].get('meeting_with') or 'not given'}\nPurpose: {b['input'].get('purpose') or 'first conversation'}\n"
            f"About: {b.get('about')}\nNews:\n{news or '- none'}\nLikely problems:\n{probs}\nQuestions:\n{qs}\n"
            f"Opening line: {b.get('opening') or ''}")


def _brief_fake(b: dict) -> dict:
    co = b["input"]["company"]
    probs = " ".join(f"{p['problem']}. {p.get('why', '')}" for p in b.get("problems") or [])
    qs = " ".join(f"Question {i + 1}. {q}" for i, q in enumerate(b.get("questions") or []))
    return {"script": (f"Here is your brief for the meeting with {co}. {b.get('about') or ''} "
                       f"Here are the problems they likely have. {probs} Here are the questions to ask. {qs} "
                       f"You could open with this. {b.get('opening') or ''} Good luck with the meeting.")}


def _public(t: dict, cached: bool = False) -> dict:
    return {"id": t["_id"], "source": t["source"], "ref_id": t["ref_id"], "title": t["title"], "sub": t.get("sub"),
            "url": media.blob_url(t["blob_id"]), "script": t.get("script"), "words": t.get("words"),
            "shared": bool(t.get("shared")), "cached": cached, "at": iso(t["at"])}


async def _blob_ok(d, blob_id) -> bool:
    return bool(blob_id) and bool(await d.blobs.find_one({"_id": blob_id}, {"_id": 1}))


@router.post("")
async def listen(body: ListenIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    await plans.require(d, user, "listen")
    if body.source == "case":
        c = await d.cases.find_one({"_id": body.id, "active": {"$ne": False}})
        if not c:
            raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Case not found."})
        shared, title, sub = is_shared_case(c), c["title"], f"{c['company']} · {c['industry']}"
        prompt, fake = _case_prompt(c), (lambda: _case_fake(c))
    else:
        b = await d.briefs.find_one({"_id": body.id, "user_id": uid})
        if not b:
            raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Brief not found."})
        shared, title, sub = False, f"Brief: {b['input']['company']}", b["input"].get("meeting_with") or "Meeting Brief"
        prompt, fake = _brief_prompt(b), (lambda: _brief_fake(b))

    mine = await d.audio_tracks.find_one({"user_id": uid, "source": body.source, "ref_id": body.id}, sort=[("at", -1)])
    if mine and await _blob_ok(d, mine.get("blob_id")):
        return _public(mine, cached=True)
    if shared:
        first = await d.audio_tracks.find_one({"source": "case", "ref_id": body.id, "shared": True, "made_by_me": True},
                                              sort=[("at", 1)])
        if first and await _blob_ok(d, first.get("blob_id")):
            row = {k: first[k] for k in ("source", "ref_id", "title", "sub", "script", "words", "blob_id", "content_type")}
            row.update(_id=uuid.uuid4().hex, user_id=uid, shared=True, made_by_me=False, at=utcnow())
            await d.audio_tracks.insert_one(row)
            return _public(row, cached=True)

    async def work(plan: str):
        raw = await llm.complete_json(task=f"listen_{body.source}", system=SYSTEM, prompt=prompt, fake=fake,
                                      model="fast", max_tokens=1400)
        script = str((raw or {}).get("script") or "").strip() if isinstance(raw, dict) else ""
        script = re.sub(r"[ \t]+", " ", script)[:6000]
        if len(script.split()) < 40:
            raise llm.LLMError("listen: script too short")
        script = _cut(script)
        try:
            data, ctype = await tts.speak(script)
        except tts.TTSError:
            raise HTTPException(status_code=503, detail={
                "code": "audio_busy", "msg": "Audio isn't working right now. Try again in a few minutes. This didn't use up your go."})
        ext = "mp3" if "mpeg" in ctype else "wav"
        try:
            blob_id = await media.save_blob(d, user_id=uid, kind="listen", content_type=ctype, data=data,
                                            name=f"{text(title, 60)}.{ext}", public=shared)
        except media.TooLarge:
            raise HTTPException(status_code=503, detail={"code": "audio_busy", "msg": "This audio came out too long. Try again."})
        row = {"_id": uuid.uuid4().hex, "user_id": uid, "source": body.source, "ref_id": body.id, "title": title,
               "sub": sub, "script": script, "words": len(script.split()), "blob_id": blob_id, "content_type": ctype,
               "shared": shared, "made_by_me": True, "at": utcnow()}
        await d.audio_tracks.insert_one(row)
        await events.track(d, "audio_made", user_id=uid, props={"source": body.source, "shared": shared})
        return _public(row)
    return await run_metered(d, user, "audio", work, access="listen")


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    rows = [_public(t) async for t in db().audio_tracks.find({"user_id": str(user["_id"])}, {"script": 0}).sort("at", -1).limit(50)]
    return {"items": rows}


@router.get("/sources")
async def sources(user: dict = Depends(user_dep())):
    """This week's case, recent cases and the member's briefs, each with its audio if it already exists."""
    d = db()
    uid = str(user["_id"])
    mine_by = {(t["source"], t["ref_id"]): _public(t, cached=True)
               async for t in d.audio_tracks.find({"user_id": uid}, {"script": 0}).sort("at", 1)}
    weekly, cases = [], []
    async for c in d.cases.find({"active": {"$ne": False}}).sort([("week", -1), ("created_at", -1)]).limit(14):
        shared_ready = False
        if is_shared_case(c) and ("case", c["_id"]) not in mine_by:
            shared_ready = bool(await d.audio_tracks.find_one({"source": "case", "ref_id": c["_id"], "shared": True}, {"_id": 1}))
        row = {"source": "case", "id": c["_id"], "title": c["title"], "sub": f"{c['company']} · {c['industry']}",
               "week": c.get("week"), "track": mine_by.get(("case", c["_id"])), "free": shared_ready}
        (weekly if c.get("kind") == "weekly" else cases).append(row)
    briefs = [{"source": "brief", "id": b["_id"], "title": b["input"]["company"], "sub": iso(b["at"]),
               "track": mine_by.get(("brief", b["_id"])), "free": False}
              async for b in d.briefs.find({"user_id": uid}, {"input": 1, "at": 1}).sort("at", -1).limit(12)]
    return {"weekly": weekly, "cases": cases[:10], "briefs": briefs}
