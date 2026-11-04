"""Session Recap Pack (L1): after every session, a written recap and a short audio.

recaps {_id, title, date "YYYY-MM-DD", call_id?, transcript (clean words), words, summary, key_ideas: [str],
        frameworks: [{name, how_to_use}], action_points: [str], questions_answered: [{q, a}],
        audio_id?, audio_type?, audio_error?, kb_doc_id?, status draft|published, published_at?, by, created_at, updated_at}

The team uploads a transcript (.txt/.vtt/.srt/.md, ≤ 8 MB) → the AI writes the recap (validated) → the summary and
action points are read aloud (audio.tts) and stored with media.save_blob (not public; served by
GET /recaps/{id}/audio after a plan check) → the team checks it and publishes. Publishing adds the transcript to
Akshat AI's knowledge base (features.kb.ingest) and sends an inbox alert to every member whose plan has `recaps`.
"""
from __future__ import annotations

import inspect
import logging
import re
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

import indexes
import llm
import media
import plans
from audio import tts
from core.deps import admin_dep, user_dep
from growth import events
from growth.clock import IST, utcnow
from notify import service as notify
from state import db
from util import iso

from . import kb
from .common import text, text_list

log = logging.getLogger("recaps")
router = APIRouter(tags=["recaps"])
member = APIRouter(prefix="/recaps")
admin = APIRouter(prefix="/admin/recaps")
Admin = Depends(admin_dep())

MAX_UPLOAD = 8 * 1024 * 1024
MAX_PROMPT_CHARS = 120_000
MIN_WORDS = 40
TYPES = (".txt", ".vtt", ".srt", ".md")

indexes.register("recaps", [("status", 1), ("date", -1)])
indexes.register("recaps", [("call_id", 1)], {"sparse": True})
notify.register_kind("recap")
events.register("recap_published", "Session recap published (props.recap_id, props.alerted)")
events.register("recap_opened", "Member opened a session recap (props.recap_id)")

SYSTEM = (
    "You write the Session Recap Pack for members of Akshat Dani's consulting program. Members are senior Indian "
    "professionals (mostly 40+, 15-35 years in jobs) getting ready to work as consultants. You get the transcript of "
    "one live session. Use only what was said in the session: no outside facts, no made-up numbers, names or links. "
    "If something was unclear in the transcript, leave it out. Plain, spoken English, short sentences, one idea per "
    "sentence, written to the member as 'you'. No buzzwords, no hype, no emojis, never promise income. Never name or "
    "describe any AI provider or model; if you need to refer to yourself, say 'the hub'."
)


def _err(status: int, code: str, msg: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "msg": msg})


def _sentences(t: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if len(s.strip().split()) >= 4]


def fake_recap(title: str, transcript: str) -> dict:
    """Deterministic recap built from the transcript, for tests and QA."""
    sents = _sentences(transcript) or [" ".join(transcript.split()[:30])]
    pick = (sents * 6)[:6]
    return {"summary": f"In {title} we covered: " + " ".join(sents[:3]),
            "key_ideas": pick[:4],
            "frameworks": [{"name": "Strategic Thinking Framework",
                            "how_to_use": "Define the problem, craft the strategy, then plan who does what first."}],
            "action_points": ["Write down the one idea from this session you will use this week.",
                              "Apply it to one real conversation before the next call.",
                              "Bring your result and one question to the next group call."],
            "questions_answered": [{"q": "What should I do first?", "a": pick[0]}]}


def _prompt(title: str, day: str, transcript: str) -> str:
    t = transcript if len(transcript) <= MAX_PROMPT_CHARS else transcript[:MAX_PROMPT_CHARS] + " [transcript cut here]"
    return (f"Session: {title}\nDate: {day}\n\nTRANSCRIPT:\n{t}\n\n"
            "Write the recap:\n"
            "- summary: 4-6 sentences on what the session was about and the main point.\n"
            "- key_ideas: 4-8 ideas from the session, one sentence each.\n"
            "- frameworks: each framework or method that was taught (0-6), with its name as said in the session and "
            "how_to_use (2-3 sentences, step by step).\n"
            "- action_points: 3-8 things to do this week, each starting with a verb.\n"
            "- questions_answered: questions members asked and the answers given (0-10), short.\n"
            'JSON only: {"summary": "", "key_ideas": [""], "frameworks": [{"name": "", "how_to_use": ""}], '
            '"action_points": [""], "questions_answered": [{"q": "", "a": ""}]}')


def validate(raw) -> dict:
    """AI recap → clean fields. Raises llm.LLMError when the shape is wrong."""
    if not isinstance(raw, dict):
        raise llm.LLMError("recap: not an object")
    summary = text(raw.get("summary"), 1600)
    key_ideas = text_list(raw.get("key_ideas"), 8, 300)
    actions = text_list(raw.get("action_points"), 8, 300)
    frameworks = [{"name": text(f.get("name"), 100), "how_to_use": text(f.get("how_to_use"), 600)}
                  for f in (raw.get("frameworks") or [])[:6] if isinstance(f, dict) and text(f.get("name"), 100)]
    qa = [{"q": text(x.get("q"), 300), "a": text(x.get("a"), 800)}
          for x in (raw.get("questions_answered") or [])[:10]
          if isinstance(x, dict) and text(x.get("q"), 300) and text(x.get("a"), 800)]
    if len(summary) < 40 or len(key_ideas) < 2 or len(actions) < 2:
        raise llm.LLMError("recap: incomplete")
    return {"summary": summary, "key_ideas": key_ideas, "frameworks": frameworks, "action_points": actions,
            "questions_answered": qa}


def audio_script(r: dict) -> str:
    acts = " ".join(f"{i + 1}. {a.rstrip('.')}." for i, a in enumerate(r.get("action_points") or []))
    return f"Session recap: {r['title']}. {r['summary']} Your action points. {acts}"


async def _make_audio(d, r: dict) -> dict:
    """Read the summary and action points aloud. A failure keeps the recap and records the error (retry later)."""
    try:
        data, ctype = await tts.speak(audio_script(r))
        ext = "mp3" if "mpeg" in ctype else "wav"
        bid = await media.save_blob(d, user_id=None, kind="recap_audio", content_type=ctype, data=data,
                                    name=f"recap-{r['_id']}.{ext}", public=False)
        return {"audio_id": bid, "audio_type": ctype, "audio_error": None}
    except (tts.TTSError, media.TooLarge) as e:
        log.warning("recap audio failed: %s", e)
        return {"audio_id": None, "audio_type": None, "audio_error": "Audio could not be made. Try again in a minute."}


async def _write(title: str, day: str, transcript: str) -> dict:
    kw = {"timeout": 120} if "timeout" in inspect.signature(llm.complete_json).parameters else {}
    raw = await llm.complete_json(task="session_recap", system=SYSTEM, prompt=_prompt(title, day, transcript),
                                  fake=lambda: fake_recap(title, transcript), model="strong", max_tokens=3000, **kw)
    return validate(raw)


# ------------------------------------------------------------------ outputs ----
def _card(r: dict) -> dict:
    return {"id": r["_id"], "title": r["title"], "date": r.get("date"), "call_id": r.get("call_id"),
            "summary": r.get("summary") or "", "has_audio": bool(r.get("audio_id")), "status": r.get("status", "draft"),
            "published_at": iso(r.get("published_at"))}


def _full(r: dict) -> dict:
    return {**_card(r), "key_ideas": r.get("key_ideas") or [], "frameworks": r.get("frameworks") or [],
            "action_points": r.get("action_points") or [], "questions_answered": r.get("questions_answered") or [],
            "audio_url": f"/api/recaps/{r['_id']}/audio" if r.get("audio_id") else None, "words": r.get("words", 0)}


def _admin_full(r: dict) -> dict:
    return {**_full(r), "audio_error": r.get("audio_error"), "kb_doc_id": r.get("kb_doc_id"),
            "created_at": iso(r.get("created_at")), "updated_at": iso(r.get("updated_at"))}


def serve_bytes(data: bytes, ctype: str, request: Request, name: str) -> Response:
    """Bytes with Range support (phone audio players ask for byte ranges before they play)."""
    size = len(data)
    head = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{name}"'}
    m = re.match(r"^bytes=(\d*)-(\d*)$", (request.headers.get("range") or "").strip())
    if m and size and (m.group(1) or m.group(2)):
        if m.group(1):
            a = int(m.group(1))
            b = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
        else:
            a, b = max(0, size - int(m.group(2))), size - 1
        if a >= size or a > b:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        return Response(data[a:b + 1], status_code=206, media_type=ctype,
                        headers={**head, "Content-Range": f"bytes {a}-{b}/{size}"})
    return Response(data, media_type=ctype, headers=head)


# ------------------------------------------------------------------ member ----
async def _published(recap_id: str, user: dict) -> dict:
    await plans.require(db(), user, "recaps")
    r = await db().recaps.find_one({"_id": recap_id})
    if not r or (r.get("status") != "published" and user.get("role") != "admin"):
        raise _err(404, "not_found", "Recap not found.")
    return r


@member.get("")
async def listing(user: dict = Depends(user_dep())):
    await plans.require(db(), user, "recaps")
    cur = db().recaps.find({"status": "published"}, {"transcript": 0}).sort([("date", -1), ("published_at", -1)]).limit(100)
    return {"items": [_card(r) async for r in cur]}


@member.get("/{recap_id}/audio")
async def audio(recap_id: str, request: Request, user: dict = Depends(user_dep())):
    r = await _published(recap_id, user)
    b = await media.get_blob(db(), r["audio_id"]) if r.get("audio_id") else None
    if not b:
        raise _err(404, "not_found", "This recap has no audio yet.")
    ctype = b.get("content_type") or "audio/mpeg"
    return serve_bytes(bytes(b["data"]), ctype, request, f"recap.{'mp3' if 'mpeg' in ctype else 'wav'}")


@member.get("/{recap_id}")
async def one(recap_id: str, user: dict = Depends(user_dep())):
    r = await _published(recap_id, user)
    out = _full(r)
    out["call"] = None
    if r.get("call_id"):
        c = await db().calls.find_one({"_id": r["call_id"]}, {"title": 1, "recording_url": 1})
        if c:
            out["call"] = {"id": c["_id"], "title": c["title"], "recording_url": c.get("recording_url") or ""}
    await events.track(db(), "recap_opened", user_id=str(user["_id"]), props={"recap_id": recap_id})
    return out


# ------------------------------------------------------------------ admin ----
def _day(v: Optional[str]) -> str:
    v = (v or "").strip()
    if not v:
        return utcnow().astimezone(IST).date().isoformat()
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise _err(400, "bad_date", "Date must look like 2026-11-08.")


async def _call_id(v: Optional[str]) -> Optional[str]:
    v = (v or "").strip()
    if not v:
        return None
    if not await db().calls.find_one({"_id": v}, {"_id": 1}):
        raise _err(400, "bad_call", "That call was not found.")
    return v


async def _recap(recap_id: str) -> dict:
    r = await db().recaps.find_one({"_id": recap_id})
    if not r:
        raise _err(404, "not_found", "Recap not found.")
    return r


@admin.get("")
async def admin_list(_: dict = Admin):
    cur = db().recaps.find({}, {"transcript": 0}).sort([("date", -1), ("created_at", -1)]).limit(300)
    return {"items": [{**_card(r), "audio_error": r.get("audio_error"), "created_at": iso(r.get("created_at"))}
                      async for r in cur]}


@admin.post("")
async def admin_create(file: UploadFile = File(...), title: str = Form(..., min_length=2, max_length=140),
                       date: Optional[str] = Form(None), call_id: Optional[str] = Form(None), admin_user: dict = Admin):
    name = (file.filename or "").lower()
    if not name.endswith(TYPES):
        raise _err(400, "bad_type", "Upload a .txt, .vtt, .srt or .md transcript.")
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise _err(400, "too_large", "Transcripts up to 8 MB.")
    transcript = kb.clean_transcript(raw.decode("utf-8", errors="ignore"))
    words = len(transcript.split())
    if words < MIN_WORDS:
        raise _err(400, "empty", "There isn't enough text in that file to make a recap.")
    title = " ".join(title.split())
    day = _day(date)
    cid = await _call_id(call_id)
    try:
        rec = await _write(title, day, transcript)
    except llm.LLMError:
        raise _err(503, "ai_busy", "The AI is busy right now. Try again in a minute.")
    now = utcnow()
    doc = {"_id": uuid.uuid4().hex, "title": title, "date": day, "call_id": cid, "transcript": transcript, "words": words,
           **rec, "status": "draft", "by": str(admin_user["_id"]), "created_at": now, "updated_at": now}
    doc.update(await _make_audio(db(), doc))
    await db().recaps.insert_one(doc)
    return _admin_full(doc)


@admin.get("/{recap_id}")
async def admin_one(recap_id: str, _: dict = Admin):
    return _admin_full(await _recap(recap_id))


class FrameworkIn(BaseModel):
    name: str = Field(..., max_length=100)
    how_to_use: str = Field("", max_length=600)


class QaIn(BaseModel):
    q: str = Field(..., max_length=300)
    a: str = Field(..., max_length=800)


class RecapEditIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=140)
    date: Optional[str] = Field(None, max_length=10)
    call_id: Optional[str] = Field(None, max_length=64)
    summary: str = Field(..., min_length=40, max_length=1600)
    key_ideas: list[str] = Field(default_factory=list, max_length=8)
    frameworks: list[FrameworkIn] = Field(default_factory=list, max_length=6)
    action_points: list[str] = Field(default_factory=list, max_length=8)
    questions_answered: list[QaIn] = Field(default_factory=list, max_length=10)


@admin.put("/{recap_id}")
async def admin_edit(recap_id: str, body: RecapEditIn, _: dict = Admin):
    """Fix the AI's wording before (or after) publishing. Audio is remade when the summary or action points change."""
    r = await _recap(recap_id)
    try:
        fields = validate({**body.model_dump(), "frameworks": [f.model_dump() for f in body.frameworks],
                           "questions_answered": [x.model_dump() for x in body.questions_answered]})
    except llm.LLMError:
        raise _err(400, "incomplete", "Keep a summary, at least 2 key ideas and at least 2 action points.")
    same_call = (body.call_id or None) == r.get("call_id")          # an already-linked call that was deleted stays as is
    upd = {"title": " ".join(body.title.split()), "date": _day(body.date),
           "call_id": r.get("call_id") if same_call else await _call_id(body.call_id), **fields, "updated_at": utcnow()}
    if fields["summary"] != r.get("summary") or fields["action_points"] != r.get("action_points") or upd["title"] != r["title"]:
        old = r.get("audio_id")
        upd.update(await _make_audio(db(), {**r, **upd}))
        if old and upd.get("audio_id"):
            await media.delete_blob(db(), old)
        elif old:
            upd["audio_id"], upd["audio_type"] = old, r.get("audio_type")
    await db().recaps.update_one({"_id": recap_id}, {"$set": upd})
    return _admin_full(await _recap(recap_id))


@admin.post("/{recap_id}/audio")
async def admin_audio(recap_id: str, _: dict = Admin):
    """Make the audio again (after a failure)."""
    r = await _recap(recap_id)
    res = await _make_audio(db(), r)
    if not res["audio_id"]:
        raise _err(503, "audio_busy", res["audio_error"])
    await db().recaps.update_one({"_id": recap_id}, {"$set": {**res, "updated_at": utcnow()}})
    await media.delete_blob(db(), r.get("audio_id"))
    return _admin_full(await _recap(recap_id))


@admin.post("/{recap_id}/publish")
async def admin_publish(recap_id: str, _: dict = Admin):
    """Publish: the transcript joins Akshat AI's knowledge base (once) and every member with Session Recaps gets an
    inbox alert (once per recap)."""
    d = db()
    r = await _recap(recap_id)
    now = utcnow()
    upd: dict = {"status": "published", "updated_at": now}
    if not r.get("published_at"):
        upd["published_at"] = now
    kb_chunks = 0
    if not r.get("kb_doc_id") and r.get("transcript"):
        res = await kb.ingest(d, f"Session: {r['title']} ({r.get('date')})", r["transcript"])
        upd["kb_doc_id"], kb_chunks = res["id"], res["chunks"]
    await d.recaps.update_one({"_id": recap_id}, {"$set": upd})
    users = await plans.users_with(d, "recaps", now)
    alerted = await notify.alert_many(d, users, "recap", f"Session recap: {r['title']}",
                                      "The summary, action points and a short audio are ready.",
                                      link=f"/app/recaps/{recap_id}", dedupe=f"recap:{recap_id}")
    await events.track(d, "recap_published", props={"recap_id": recap_id, "alerted": alerted})
    return {**_admin_full(await _recap(recap_id)), "alerted": alerted, "kb_chunks": kb_chunks}


@admin.post("/{recap_id}/unpublish")
async def admin_unpublish(recap_id: str, _: dict = Admin):
    await _recap(recap_id)
    await db().recaps.update_one({"_id": recap_id}, {"$set": {"status": "draft", "updated_at": utcnow()}})
    return _admin_full(await _recap(recap_id))


@admin.delete("/{recap_id}")
async def admin_delete(recap_id: str, _: dict = Admin):
    """Deletes the recap, its audio and its transcript in the knowledge base."""
    d = db()
    r = await _recap(recap_id)
    await d.recaps.delete_one({"_id": recap_id})
    await media.delete_blob(d, r.get("audio_id"))
    if r.get("kb_doc_id"):
        await d.kb_docs.delete_one({"_id": r["kb_doc_id"]})
        await d.kb_chunks.delete_many({"doc_id": r["kb_doc_id"]})
        kb.reset_kb_cache()
    return {"ok": True}


router.include_router(member)
router.include_router(admin)
