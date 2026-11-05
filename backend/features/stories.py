"""Career Story Bank: one story a week from the member's career, turned into proof for clients.

Each week the hub suggests a "story question of the week" (rotating list below). The member records a voice note in
the browser, uploads a recording, or types the story. A voice note is turned into text (audio.stt) and then the AI
shapes it the way the current hub's Credibility Code GPT shapes proof stories (backend/gpts/prompts/credibility-code.md,
Stage 3): Situation / What I did / Result / What it proves, using only the member's own facts and numbers, plus a
LinkedIn post and one line to use in a pitch.

stories {_id, user_id, question, source: voice|text, transcript, title, situation, what_i_did, result, what_it_proves,
         numbers: [str], linkedin_post, pitch_line, edited: bool, at, updated_at}

We keep the transcript and the story only. The audio is never stored: it is read into memory, transcribed, dropped.
Other tools (Offer Card, Credibility Code) read title, situation, what_i_did and result.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

import indexes
import llm
import plans
from audio import stt
from core.deps import user_dep
from core.errors import (
    InvalidInput,
    NotFound,
    PayloadTooLarge,
    ServiceUnavailable,
    UnsupportedMedia,
)
from growth import events
from growth.clock import IST, as_utc, utcnow
from state import db
from util import iso

from .common import run_metered, text, text_list
from .knowledge import knowledge, system_block

log = logging.getLogger("stories")

router = APIRouter(prefix="/stories", tags=["story-bank"])

events.register("story_saved", "Career story saved (props.source voice|text)")
indexes.register("stories", [("user_id", 1), ("at", -1)])

MAX_AUDIO_BYTES = 24 * 1024 * 1024
MAX_AUDIO_SECONDS = 10 * 60
AUDIO_TYPES = {  # extension → content type sent to speech-to-text
    "webm": "audio/webm", "ogg": "audio/ogg", "oga": "audio/ogg", "m4a": "audio/mp4", "mp4": "audio/mp4",
    "mp3": "audio/mpeg", "mpeg": "audio/mpeg", "wav": "audio/wav"}
CT_EXT = {"audio/webm": "webm", "video/webm": "webm", "audio/ogg": "ogg", "application/ogg": "ogg", "audio/mp4": "m4a",
          "audio/x-m4a": "m4a", "audio/m4a": "m4a", "audio/aac": "m4a", "video/mp4": "m4a", "audio/mpeg": "mp3",
          "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav", "audio/vnd.wave": "wav"}

QUESTIONS = [
    "Tell me about a time you turned around a team, a unit or a project that was failing.",
    "What is the biggest cost you ever saved a business? How did you find it?",
    "Tell me about a hard call you made that people disagreed with at first.",
    "When did you grow sales faster than anyone expected? What did you do differently?",
    "Tell me about a customer who was about to leave, and how you kept them.",
    "Which process did you fix after everyone else had given up on it?",
    "Tell me about the best team you built. How did you pick and grow those people?",
    "When did you spot a problem before anyone else did? What happened next?",
    "Tell me about a launch, or a new market you opened.",
    "What is a mistake you made, and what did you change because of it?",
    "Tell me about a time you got people who didn't report to you to act.",
    "When did you finish a project on time when it looked impossible?",
    "Tell me about a negotiation that went your way. What did you do?",
    "What did you change in a business that is still working today?",
    "Tell me about a time you had to restructure a team or let someone go.",
    "When did the numbers change your mind about a big decision?",
    "Tell me about a crisis you handled: a shutdown, a recall, a big loss.",
    "What is the hardest problem a boss or a client ever handed you?",
    "Tell me about a time you made something simpler and it worked better.",
    "When did you coach someone who went on to do great things?",
    "Tell me about a time you settled a fight between two departments.",
    "What is a result you're proud of that never made it to your CV?",
    "Tell me about a time you raised quality or safety and saved money too.",
    "When did you win back a client, a project or a budget that was lost?",
]

SYSTEM = (
    "You are the Career Story Bank coach inside Akshat Dani's High Value Consulting program. Members are experienced "
    "Indian professionals (mostly 40-60) building consulting practices. They tell you a story from their career, often "
    "as a rough voice note. You turn it into a proof story in four short parts, the way the Credibility Code does: "
    "Situation (what problem existed), What I did (what they personally changed), Result (what improved, with the "
    "numbers they gave), What it proves (how this shows they can solve their clients' problem today, tied to their "
    "niche). Write in the first person, plain and confident. Give it a title of four to six words.\n"
    "RULES: Use only the facts and numbers in the member's words. NEVER invent or round up a number, result, client, "
    "company, award or title. If the result has no number, keep it without one. Voice notes ramble: drop filler, keep "
    "the facts. Indian English spelling and Indian context (₹, lakh, crore). Never use language that lowers their level "
    "('new to consulting', 'just started', 'retired', 'still in my job'). Avoid: delve, unlock, unleash, leverage (as a "
    "verb), game-changer, landscape, navigate, journey, seamless, robust, elevate, empower, transformative, passionate, "
    "results-driven, seasoned. No hype, no emojis, no hashtags. Never mention or describe the AI or who makes it."
)


def week_key(now=None) -> tuple[str, int]:
    d = as_utc(now or utcnow()).astimezone(IST).date()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}", (y * 53 + w) % len(QUESTIONS)


def question_of_week(now=None) -> dict:
    key, i = week_key(now)
    return {"week": key, "n": i + 1, "text": QUESTIONS[i]}


class TextIn(BaseModel):
    text: str = Field(..., min_length=80, max_length=8000)
    question: str = Field("", max_length=300)


class StoryEdit(BaseModel):
    title: str = Field(..., min_length=2, max_length=80)
    situation: str = Field(..., min_length=2, max_length=800)
    what_i_did: str = Field(..., min_length=2, max_length=1000)
    result: str = Field(..., min_length=2, max_length=800)
    what_it_proves: str = Field("", max_length=600)
    numbers: list[str] = Field(default_factory=list, max_length=10)
    linkedin_post: str = Field("", max_length=3000)
    pitch_line: str = Field("", max_length=300)


def _sentences(t: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", " ".join(t.split())) if s]


def _fake(story: str, question: str) -> dict:
    s = _sentences(story) or [story]
    nums = re.findall(r"₹?\d[\d,.]*\s*(?:%|percent|lakh|crore|days|months|weeks|years)?", story)
    title_words = [w for w in re.findall(r"[A-Za-z]+", s[0]) if len(w) > 3][:4] or ["My", "Turnaround", "Story"]
    return {"title": " ".join(w.capitalize() for w in title_words)[:60],
            "situation": s[0], "what_i_did": " ".join(s[1:-1]) or s[0], "result": s[-1],
            "what_it_proves": "I can find the real cause of a problem quickly and get a team to fix it.",
            "numbers": [n.strip() for n in nums][:5],
            "linkedin_post": f"{s[0]}\n\n{' '.join(s[1:-1]) or s[0]}\n\n{s[-1]}\n\nThe lesson: the fix is rarely where people "
                             "first look. What is one problem in your business that everyone has stopped questioning?",
            "pitch_line": f"In one of my roles, {s[-1][0].lower() + s[-1][1:] if s[-1] else ''}",
            "note": "Test mode story. Live mode writes it from your words."}


def _prompt(story: str, question: str, k: dict, source: str) -> str:
    kb = system_block(k) or "Their niche is not known yet: tie 'What it proves' to the kind of problem the story shows."
    return (f"{kb}\n\nSTORY QUESTION: {question or 'their own story'}\n\nTHE MEMBER'S STORY (their words"
            f"{', transcribed from a voice note' if source == 'voice' else ''}):\n\"\"\"\n{story}\n\"\"\"\n\n"
            "Write: title (4-6 words), situation (1-2 sentences), what_i_did (2-3 sentences), result (1-2 sentences, "
            "with their numbers), what_it_proves (1 sentence tied to the problem their niche solves), numbers (each "
            "number from their story with what it measures, e.g. 'On-time delivery 70% to 94% in 3 months'; empty if "
            "none), linkedin_post (120-220 words, first person, short paragraphs, a first line that makes people stop, "
            "the story, one lesson for business owners, end with a question; no hashtags, no emojis), pitch_line (one "
            "sentence they could say in a client conversation).\n"
            'JSON: {"title": "", "situation": "", "what_i_did": "", "result": "", "what_it_proves": "", "numbers": [""], '
            '"linkedin_post": "", "pitch_line": ""}')


def _clean(raw: dict) -> dict:
    out = {"title": text(raw.get("title"), 80), "situation": text(raw.get("situation"), 800),
           "what_i_did": text(raw.get("what_i_did"), 1000), "result": text(raw.get("result"), 800),
           "what_it_proves": text(raw.get("what_it_proves"), 600), "numbers": text_list(raw.get("numbers"), 10, 160),
           "linkedin_post": str(raw.get("linkedin_post") or "").strip()[:3000],
           "pitch_line": text(raw.get("pitch_line"), 300)}
    if not all(out[f] for f in ("title", "situation", "what_i_did", "result", "what_it_proves", "linkedin_post")):
        raise llm.LLMError("story: incomplete")
    return out


def _public(d: dict) -> dict:
    return {"id": d["_id"], "question": d.get("question") or "", "source": d.get("source"),
            "transcript": d.get("transcript") or "", **{f: d.get(f) for f in (
                "title", "situation", "what_i_did", "result", "what_it_proves", "numbers", "linkedin_post", "pitch_line")},
            "edited": bool(d.get("edited")), "at": iso(d["at"]), "updated_at": iso(d.get("updated_at") or d["at"])}


async def _make(user: dict, story: str, question: str, source: str, transcribe=None) -> dict:
    uid = str(user["_id"])

    async def work(plan: str):
        words = story
        if transcribe is not None:
            try:
                words = await transcribe()
            except stt.STTError as e:
                log.warning("voice note transcription failed: %s", e)
                raise ServiceUnavailable("We couldn't turn your voice note into text just now. Try again in a "
                                                 "minute, or type your story. This didn't use up your go.", code="stt_failed")
            if len(words.strip()) < 40:
                raise InvalidInput("We could hear very little in that recording. Try again a little closer "
                                                "to the phone, and speak for at least a minute. This didn't use up your go.", code="too_short")
        k = await knowledge(db(), user)
        raw = await llm.complete_json(task="career_story", system=SYSTEM, prompt=_prompt(words, question, k, source),
                                      fake=lambda: _fake(words, question), model="strong", max_tokens=1400)
        st = _clean(raw)
        now = utcnow()
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "question": question, "source": source,
               "transcript": words.strip()[:20000], **st, "edited": False, "at": now, "updated_at": now}
        await db().stories.insert_one(doc)
        await events.track(db(), "story_saved", user_id=uid, props={"source": source})
        return _public(doc)
    return await run_metered(db(), user, "story", work, access="story_bank")


def _audio_type(f: UploadFile) -> tuple[str, str]:
    """(extension, content type) for an accepted audio file, or a plain 415."""
    name = (f.filename or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    ct = (f.content_type or "").split(";")[0].strip().lower()
    if ext not in AUDIO_TYPES:
        ext = CT_EXT.get(ct, "")
    if ext not in AUDIO_TYPES:
        raise UnsupportedMedia("Use a voice recording: webm, ogg, m4a, mp3 or wav.")
    return ext, AUDIO_TYPES[ext]


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    q = question_of_week()
    items = [_public(d) async for d in db().stories.find({"user_id": uid}).sort("at", -1).limit(100)]
    answered = await db().stories.count_documents({"user_id": uid, "question": q["text"]})
    return {"question": q, "answered_this_week": answered > 0, "items": items,
            "limits": {"max_minutes": MAX_AUDIO_SECONDS // 60, "max_mb": MAX_AUDIO_BYTES // (1024 * 1024)}}


@router.post("/voice")
async def from_voice(file: UploadFile = File(...), question: str = Form(""), duration_s: Optional[float] = Form(None),
                     user: dict = Depends(user_dep())):
    await plans.require(db(), user, "story_bank")
    ext, ctype = _audio_type(file)
    if duration_s is not None and duration_s > MAX_AUDIO_SECONDS + 5:
        raise PayloadTooLarge("Keep your voice note under 10 minutes.", code="too_long")
    data = await file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise PayloadTooLarge("That recording is larger than 24 MB. Keep it under 10 minutes.")
    if len(data) < 1000:
        raise InvalidInput("That recording is empty. Try again.", code="empty")
    q = text(question, 300)

    async def transcribe() -> str:
        return await stt.transcribe(data, filename=f"story.{ext}", content_type=ctype)
    # The audio only lives in this request's memory: it is never saved to Mongo, blobs or disk.
    return await _make(user, "", q, "voice", transcribe=transcribe)


@router.post("/text")
async def from_text(body: TextIn, user: dict = Depends(user_dep())):
    return await _make(user, body.text.strip(), text(body.question, 300), "text")


async def _own(story_id: str, uid: str) -> dict:
    d = await db().stories.find_one({"_id": story_id, "user_id": uid})
    if not d:
        raise NotFound("Story not found.")
    return d


@router.get("/{story_id}")
async def one(story_id: str, user: dict = Depends(user_dep())):
    return _public(await _own(story_id, str(user["_id"])))


@router.put("/{story_id}")
async def edit(story_id: str, body: StoryEdit, user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    await plans.require(db(), user, "story_bank")
    await _own(story_id, uid)
    upd = body.model_dump()
    upd["numbers"] = text_list(upd["numbers"], 10, 160)
    upd["linkedin_post"] = upd["linkedin_post"].strip()
    await db().stories.update_one({"_id": story_id, "user_id": uid}, {"$set": {**upd, "edited": True, "updated_at": utcnow()}})
    return _public(await _own(story_id, uid))


@router.delete("/{story_id}")
async def remove(story_id: str, user: dict = Depends(user_dep())):
    res = await db().stories.delete_one({"_id": story_id, "user_id": str(user["_id"])})
    if not res.deleted_count:
        raise NotFound("Story not found.")
    return {"ok": True}
