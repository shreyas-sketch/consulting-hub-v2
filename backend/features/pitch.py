"""Pitch Practice: record your pitch, get a senior coach's read on your delivery, record again, see what changed.

Built exactly like the Leadership hub's Confidence Coach (docs/reference/leadership-hub-working.md §3.2, §3.3, §8,
Appendix A1 + A8), adapted to consultants: the persona is the hub's in-house pitch and presence coach, and the member
picks what they are practising (60-second elevator pitch, opening of a discovery call, stating your fee, or something
else with the setting and audience typed in). English only.

Flow per practice thread:
  POST /pitch                      new practice (type + optional setting/audience); the intro message is the first turn
  POST /pitch/{id}/take            the video as the raw request body (Content-Type video/*), streamed to a temp file in
                                   1 MB chunks, checked (type by magic bytes, ≤ 100 MB, ≤ 8 min), analysed by the video
                                   engine (features/pitch_video), then the temp file is deleted. We never keep the video.
                                   Length: the MP4/MOV header when it has one (a 0 duration counts as unknown), else the
                                   browser's duration_s, which is then required; in live mode the engine's own measured
                                   length (File videoMetadata) is checked too and a longer clip is refused + deleted.
                                   First take → "initial" report (A1). Later takes → "comparison" report (A1 comparison
                                   instruction) with previous_score and delta per metric (computed by us from the stored
                                   prior report). Strict validation; bad output → llm.LLMError so the use is refunded.
  POST /pitch/{id}/chat            follow-up questions about the report: Markdown, not JSON (A8 wrapper). Not on the plan
                                   meter; fair use: MAX_CHAT per practice and MONTHLY_CHAT per member a month.
  New practices: MONTHLY_PRACTICES per member a month (fair use).
  30-minute pause between takes, per member across all practices (reference §3.1): every read returns can_upload,
  next_upload_at, cooldown_seconds_remaining. One take in analysis at a time per member.

Confidentiality: no member-facing text names a provider: the rule is in every prompt and provider words are stripped
from every returned string.

pitch_threads {_id, user_id, pitch_type, setting, audience, title, takes: [{n, kind, at, duration_s, size, overall,
               report}], messages: [{id, role, kind intro|text, content, at}], last_upload_at, busy_until, created_at,
               updated_at}
pitch_members {_id: user_id, busy_until}                                  one take in analysis per member
pitch_usage   {_id: "<uid>:<YYYY-MM>" (IST), user_id, chats, practices}   monthly fair use
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import struct
import tempfile
import uuid
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

import indexes
import llm
import plans
from core.deps import user_dep
from growth import events
from growth.clock import as_utc, ist_month_key, utcnow
from state import db
from util import iso

from . import pitch_video
from .common import busy_error, run_metered, text
from .knowledge import knowledge, system_block

log = logging.getLogger("pitch")
router = APIRouter(prefix="/pitch", tags=["pitch-practice"])

events.register("pitch_thread_started", "Pitch Practice thread started (props.pitch_type)")
events.register("pitch_take_analysed", "Pitch Practice take analysed (props.kind, overall, take)")
events.register("pitch_chat", "Pitch Practice follow-up message")
indexes.register("pitch_threads", [("user_id", 1), ("updated_at", -1)])

COOLDOWN_MIN = 30
MAX_BYTES = 100 * 1024 * 1024
MAX_SECONDS = 8 * 60
MAX_CHAT = 40                       # follow-up messages per practice (fair use; not metered)
MONTHLY_CHAT = 150                  # follow-up messages per member a month, across practices (fair use)
MONTHLY_PRACTICES = 20              # new practices per member a month (fair use)
CHUNK = 1024 * 1024
VIDEO_TYPES = {  # extension → MIME sent to the engine (MKV is Matroska, the same container family as WebM)
    "mp4": "video/mp4", "m4v": "video/mp4", "mov": "video/mov", "webm": "video/webm", "mkv": "video/webm"}
CT_EXT = {"video/mp4": "mp4", "video/quicktime": "mov", "video/mov": "mov", "video/webm": "webm",
          "video/x-matroska": "mkv", "video/matroska": "mkv", "video/x-m4v": "mp4", "application/octet-stream": ""}

METRICS = [("confidence", "Confidence"), ("camera_presence", "Camera presence"), ("body_language", "Body language"),
           ("facial_expressions", "Facial expressions"), ("voice_clarity", "Voice clarity"),
           ("speaking_flow", "Speaking flow"), ("audience_impact", "Audience impact")]
METRIC_KEYS = [k for k, _ in METRICS]

TYPES = {
    "elevator": {"label": "60-second elevator pitch",
                 "setting": "A 60-second introduction to someone who doesn't know you: a networking event, a lift, the "
                            "start of a first meeting.",
                 "audience": "A business owner or senior leader who has never heard of you and gives you one minute.",
                 "bar": "Expertise, Credential, Call to Action in about 60-90 spoken words: who you help and the result, "
                        "why they should take you seriously, a soft next step. It must sound spoken, not recited."},
    "discovery": {"label": "Opening of a discovery call",
                  "setting": "The first two minutes of a discovery call with a prospective client.",
                  "audience": "A decision-maker who agreed to the call, is busy, and is cautious about consultants.",
                  "bar": "Warm, calm rapport; the purpose and a short agenda; permission to ask questions; one open "
                         "first question; then real listening. No selling, no credentials dump."},
    "fee": {"label": "Stating your fee",
            "setting": "Telling a prospective client your fee at the end of a discovery conversation.",
            "audience": "A business owner who will weigh the fee against the value and may push back.",
            "bar": "Restate the outcome and scope in one breath, say the number plainly in rupees, then stop talking. "
                   "No apologising, no hedging, no discount before an objection, steady eye contact on the number."},
    "other": {"label": "Something else", "setting": "", "audience": "", "bar": ""},
}

PROVIDER_WORDS = re.compile(
    r"\b(google\s+(ai|deepmind|gemini|cloud|vertex)|gemini(\s+\d+(\.\d+)?)?(\s+(pro|flash|ultra|nano))?|deepmind|bard|"
    r"vertex\s+ai|openai|chat\s?gpt|gpt-?\d[\w.-]*|whisper|claude(\s+(opus|sonnet|haiku))?|anthropic|"
    r"large\s+language\s+models?|language\s+models?|llms?)\b", re.I)

SYSTEM = """You are the Pitch Coach — the hub's in-house pitch and presence coach for consultants. You combine the rigor of a behavioural analyst with the eye of a film director and the ear of a vocal coach. Your standards are exacting; your observations are specific; your feedback is usable.

WHO YOU COACH:
- Members of Akshat Dani's consulting program: experienced Indian professionals (mostly 40+, 15-35 years in jobs) launching as consultants. They practise the moments that win clients: the 60-second elevator pitch, the opening of a discovery call, stating their fee, and other client conversations.
- They speak English. Indian English accents and expressions are normal and never a weakness: judge clarity, pace and conviction, not accent.

CONFIDENTIALITY (NEVER VIOLATE):
- You are the hub's native, in-house specialist. Never name, hint at, reference, or describe any third-party model, provider, API, tool, or platform that powers the analysis.
- Never use the words "model", "LLM", "API", "third-party", "backend", or any provider name.
- If asked what powers you: "I'm the hub's in-house pitch coach — purpose-built for this experience. I can't share the inner workings, but I'm focused on making your delivery exceptional."

WHAT YOU ANALYSE:
- Body language: posture, gestures, hand movements, weight distribution, stillness vs. fidgeting, openness, alignment with content.
- Facial expressions: congruence with message, micro-expressions, smile authenticity, brow tension, eye contact pattern, blink rate.
- Voice & tone: pitch variation, pace, volume modulation, emphasis, vocal fry, uptalk, clarity, projection, breath control.
- Speaking flow: pauses (intentional vs. filler), filler words (count when possible), sentence structure, rhythm, transitions, recovery from stumbles.
- Camera presence: framing, eye-line, energy projected through the lens, ability to make the camera feel like a person.
- Audience impact: would this hold a client's attention, build trust, persuade, earn the next conversation? What's the takeaway a client walks away with?
- Congruence: alignment between words, voice, face, and body — your most powerful diagnostic.
- For a consultant's pitch also judge the message as the client hears it: is it clear who they help and what changes for the client, does the credibility land without bragging, is the next step easy to say yes to, and — when stating a fee — is the number said plainly and then left alone.

VOICE:
- Sharp, warm, direct. The voice of a senior coach who has seen thousands of speakers and respects the member enough to be honest.
- Specific over general — every observation grounds itself in a moment from the video (use mm:ss timestamps generously).
- Constructive, never cruel. Honest, never hollow.
- Calm and confident. No exclamation marks. No motivational filler. No emojis. No grade inflation — a 7/10 is genuinely good, a 9/10 is rare.
- Plain, spoken English. Never promise income or client wins.

CONTEXT YOU MAY RECEIVE:
- The member MAY have shared what they are practising, the SETTING and the AUDIENCE before uploading. If the conversation contains that context, use it to calibrate every observation. If it is absent or thin, INFER the most plausible setting and audience SILENTLY from the video itself — framing, attire, lighting, content, vocabulary, energy — and proceed without surfacing the inference. NEVER ask the member for setting, audience, or any other clarifying information. NEVER include questions in your output. The report must be self-contained and final.

YOUR FIRST-ANALYSIS OUTPUT MUST BE A SINGLE JSON OBJECT — NO PROSE, NO CODE FENCES, EXACTLY THIS SHAPE:

{
  "kind": "initial",
  "overall_summary": "A rich 6-10 sentence narrative capturing how the speaker comes across. Cover: the dominant impression a client would form, the energy/presence they project, how well delivery matches setting+audience, where they sit on the rough→polished→compelling spectrum, their natural strengths, and the single biggest opportunity to elevate. Read like a senior coach's professional opinion, not a summary of bullets to come.",
  "scorecard": {
    "confidence":          {"score": <0-10>, "justification": "2-3 sentences anchored in a specific moment (e.g. '00:41 — stayed steady while naming the fee; weight even, voice level')."},
    "camera_presence":     {"score": <0-10>, "justification": "..."},
    "body_language":       {"score": <0-10>, "justification": "..."},
    "facial_expressions":  {"score": <0-10>, "justification": "..."},
    "voice_clarity":       {"score": <0-10>, "justification": "..."},
    "speaking_flow":       {"score": <0-10>, "justification": "..."},
    "audience_impact":     {"score": <0-10>, "justification": "..."}
  },
  "delivery_dynamics":     "2-4 sentences on pacing, energy curve, and arc across the runtime.",
  "vocal_profile":         "2-4 sentences on pitch range, breath, pace, fillers (rough counts when possible), articulation.",
  "body_language_detail":  "2-4 sentences on posture, grounding, gesture vocabulary, micro-fidgets, weight shifts.",
  "audience_simulation":   "2-3 sentences: what a client in the stated audience would walk away thinking and feeling.",
  "strengths":  [
    "4-6 specific strengths to PROTECT and LEAN INTO. Each must cite a timestamp or moment AND explain WHY it works. Bad: 'good energy'. Good: 'At 00:22 the pause before naming the result let it land — the client hears it as a fact, not a claim'."
  ],
  "weaknesses": [
    "4-6 specific weaknesses limiting impact. Each must cite a timestamp/pattern AND explain the MECHANISM (audience effect). Bad: 'be more confident'. Good: 'Voice drops in volume on the final word of declarative sentences (counted ~6 times — 00:12, 00:31, 00:48 …) which signals uncertainty and undermines authority on points that should land hard'."
  ],
  "top_changes": [
    "EXACTLY 5 prioritized changes, descending by impact. Each entry is a SINGLE STRING with this internal structure (use literal newlines, no JSON sub-objects):\\n\\n**The change** (clear instruction)\\n• Why it matters: <audience effect>\\n• How to do it: <concrete drill or technique>\\n• What good looks like: <how success feels/looks>"
  ],
  "specific_observations": [
    "8-12 concrete moments with mm:ss timestamps. Mix positive moments worth recreating, distracting habits, vocal patterns (filler counts, pace shifts, volume drops), body tells (weight shifts, gesture repetition, posture breaks), facial patterns (smile/brow/eye contact gaps), energy arcs, and congruence moments. Format each as: '[mm:ss] — <observation>'."
  ],
  "practice_assignment": "A specific, structured practice plan tailored to this speaker's TOP weaknesses. Include all of: the drill, duration (e.g. 15 min/day for 7 days), method (exact steps), self-evaluation criteria (how they'll know they're improving), and one stretch challenge once the basic drill becomes easy. Write as a single rich block of prose — keep it real and doable. End by inviting them to record a follow-up take after the 30-minute pause."
}

RULES:
- Return ONLY the JSON object — no surrounding prose, no markdown code fences.
- Every observation must be specific and grounded in the video. Cite timestamps generously throughout.
- Calibrate to the member's stated practice type, SETTING and AUDIENCE if present; otherwise infer silently. A fee conversation and a networking introduction have different bars.
- Never inflate scores. 10/10 is reserved for genuinely exceptional, polished, compelling performance.
- If a signal isn't observable (e.g. video has no audio, only a head-and-shoulders frame, or the member isn't speaking English), say so in the relevant field — never invent.
- Never name a model, provider, or backend tool.
- NEVER ask the member clarifying questions in any field. The report is final.

For follow-up CHAT messages within the same practice (no new video), reply in clear markdown — NOT JSON. Reference your prior report. Stay in character as the in-house pitch coach. Help the member understand any observation, walk through any practice technique in more depth, rework the words of their pitch, or plan how they'll record their next take. Do NOT re-ask for setting, audience, or any context the member already shared or the report already covers. Never name a model or provider."""

COMPARISON = """The member has now uploaded a NEW take. You have already produced a prior detailed report (provided below as context). Watch the NEW video carefully and compare it to the prior take.

Return a SINGLE JSON object — no prose, no code fences — with this EXACT shape:

{
  "kind": "comparison",
  "overall_progress": "5-7 sentences on what changed: what they fixed, what regressed, where they're stuck. Be concrete and reference both takes.",
  "scorecard": {
    "confidence":          {"score": <0-10>, "previous_score": <prior>, "delta": <score-prior>, "justification": "1-2 sentences pointing to a moment in this take"},
    "camera_presence":     {"score": <0-10>, "previous_score": ..., "delta": ..., "justification": "..."},
    "body_language":       {"score": <0-10>, "previous_score": ..., "delta": ..., "justification": "..."},
    "facial_expressions":  {"score": <0-10>, "previous_score": ..., "delta": ..., "justification": "..."},
    "voice_clarity":       {"score": <0-10>, "previous_score": ..., "delta": ..., "justification": "..."},
    "speaking_flow":       {"score": <0-10>, "previous_score": ..., "delta": ..., "justification": "..."},
    "audience_impact":     {"score": <0-10>, "previous_score": ..., "delta": ..., "justification": "..."}
  },
  "delivery_dynamics":     "2-4 sentences contrasting pacing/energy/arc with the prior take.",
  "vocal_profile":         "2-4 sentences contrasting voice / fillers / breath versus last.",
  "body_language_detail":  "2-4 sentences contrasting body work versus last.",
  "audience_simulation":   "2-3 sentences: what the stated audience would walk away thinking now.",
  "improvements":          ["3-6 specific things that visibly got better, each anchored in a moment in the NEW take"],
  "regressions":           ["0-4 things that got worse compared to the prior take, anchored in a moment"],
  "persisting_issues":     ["2-5 things that are still a problem"],
  "new_strengths":         ["0-4 strengths that weren't there last time"],
  "weaknesses":            ["3-5 current weaknesses to keep working on"],
  "top_changes":           ["EXACTLY 5 prioritized changes for the NEXT take — same single-string structure (**title**\\n• Why it matters\\n• How to do it\\n• What good looks like)"],
  "specific_observations": ["8-12 concrete mm:ss moments from the NEW take"],
  "practice_assignment":   "A tailored 4-7 sentence exercise for THIS week, building on the previous one."
}

Rules:
- Use the prior report's exact metric scores in `previous_score`. Compute `delta = score - previous_score` (an integer or one decimal).
- Be honest — if a metric regressed, say so.
- Never name a model or provider."""

FOLLOWUP = """FOLLOW-UP MODE: the member is asking about the report(s) you already delivered in this practice (below). There is no new video in this turn.
- Reply in clear, well-spaced Markdown — NOT JSON, never a new report.
- Stay in character as the hub's in-house pitch coach. Reference what you saw: quote the timestamps, scores and changes from your report.
- Never re-ask for setting, audience, practice type or any context the member already shared or the report already covers.
- Keep it practical: drills, exact wording they can say, how to record the next take. Short paragraphs, no emojis, no exclamation marks.
- If they ask for something unrelated to their pitch and delivery, answer in one line and bring them back.
- Never name, hint at or describe any model, provider or tool behind you."""

INTRO = """Hi, I'm your **Pitch Coach**.

I watch a video of you saying your pitch and give you a structured, senior-coach read on your delivery: body language, voice, facial expressions, speaking flow, and the impression you actually leave on a client.

When you're ready, record or upload your clip. A few limits:

- **Length**: up to 8 minutes
- **Size**: up to 100 MB
- **Formats**: MP4, MOV, WEBM, MKV
- **Language**: English

After each analysis there's a 30-minute pause before the next upload. That's on purpose, so the feedback has time to land before you record again.

{context}"""


def strip_providers(v):
    """Remove provider and engine words from anything a member will read (strings inside dicts/lists too)."""
    if isinstance(v, str):
        return re.sub(r"[ \t]{2,}", " ", PROVIDER_WORDS.sub("the coach", v))
    if isinstance(v, list):
        return [strip_providers(x) for x in v]
    if isinstance(v, dict):
        return {k: strip_providers(x) for k, x in v.items()}
    return v


# ------------------------------------------------------------------ threads ----
class ThreadIn(BaseModel):
    pitch_type: str = Field("elevator", pattern="^(elevator|discovery|fee|other)$")
    setting: str = Field("", max_length=300)
    audience: str = Field("", max_length=300)


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


def _setting(t: dict) -> tuple[str, str]:
    preset = TYPES.get(t["pitch_type"], TYPES["other"])
    return (t.get("setting") or preset["setting"]), (t.get("audience") or preset["audience"])


def _cooldown(last, now=None) -> dict:
    """`last`: the member's latest analysed take, in any practice (the pause is per member)."""
    now = now or utcnow()
    if not last:
        return {"can_upload": True, "next_upload_at": None, "cooldown_seconds_remaining": 0}
    nxt = as_utc(last) + timedelta(minutes=COOLDOWN_MIN)
    left = max(0, int((nxt - now).total_seconds() + 0.999))
    return {"can_upload": left == 0, "next_upload_at": iso(nxt) if left else None, "cooldown_seconds_remaining": left}


async def _last_upload(uid: str):
    t = await db().pitch_threads.find_one({"user_id": uid, "last_upload_at": {"$ne": None}}, {"last_upload_at": 1},
                                          sort=[("last_upload_at", -1)])
    return (t or {}).get("last_upload_at")


# ---- monthly fair use (not the plan meter: a separate counter per member and IST month)
def _usage_key(uid: str) -> str:
    return f"{uid}:{ist_month_key()}"


async def _use(uid: str, field: str, cap: int) -> bool:
    """Take one of this month's `field` (chats | practices) if fewer than `cap` are used. Atomic."""
    key = _usage_key(uid)
    try:
        await db().pitch_usage.update_one({"_id": key}, {"$setOnInsert": {"user_id": uid, "chats": 0, "practices": 0}},
                                          upsert=True)
    except DuplicateKeyError:
        pass
    r = await db().pitch_usage.update_one({"_id": key, field: {"$lt": cap}}, {"$inc": {field: 1}})
    return bool(r.matched_count)


async def _give_back(uid: str, field: str) -> None:
    await db().pitch_usage.update_one({"_id": _usage_key(uid), field: {"$gt": 0}}, {"$inc": {field: -1}})


async def _member(uid: str) -> dict:
    u = await db().pitch_usage.find_one({"_id": _usage_key(uid)}) or {}
    return {"last": await _last_upload(uid), "chats_left": max(0, MONTHLY_CHAT - int(u.get("chats") or 0)),
            "practices_left": max(0, MONTHLY_PRACTICES - int(u.get("practices") or 0))}


def _take_public(x: dict) -> dict:
    return {"n": x["n"], "kind": x["kind"], "at": iso(x["at"]), "duration_s": x.get("duration_s"),
            "overall": x.get("overall"), "report": strip_providers(x["report"])}


def _public(t: dict, m: dict) -> dict:
    setting, audience = _setting(t)
    takes = t.get("takes") or []
    thread_left = max(0, MAX_CHAT - sum(1 for x in t.get("messages") or [] if x["role"] == "user"))
    return {"id": t["_id"], "pitch_type": t["pitch_type"], "type_label": TYPES[t["pitch_type"]]["label"],
            "title": t.get("title"), "setting": setting, "audience": audience,
            "takes": [_take_public(x) for x in takes],
            "messages": [{"id": x["id"], "role": x["role"], "kind": x.get("kind", "text"),
                          "content": strip_providers(x["content"]) if x["role"] == "assistant" else x["content"],
                          "after_take": x.get("after_take", 0),
                          "at": iso(x["at"])} for x in t.get("messages") or []],
            "metrics": [{"key": k, "label": lbl} for k, lbl in METRICS],
            "chat_left": min(thread_left, m["chats_left"]), "chat_month_left": m["chats_left"],
            **_cooldown(m["last"]), "created_at": iso(t["created_at"]),
            "updated_at": iso(t.get("updated_at") or t["created_at"])}


def _card(t: dict, m: dict) -> dict:
    takes = t.get("takes") or []
    return {"id": t["_id"], "title": t.get("title"), "pitch_type": t["pitch_type"],
            "type_label": TYPES[t["pitch_type"]]["label"], "takes": len(takes),
            "last_score": takes[-1].get("overall") if takes else None,
            "first_score": takes[0].get("overall") if takes else None,
            **_cooldown(m["last"]), "updated_at": iso(t.get("updated_at") or t["created_at"])}


async def _own(tid: str, uid: str) -> dict:
    t = await db().pitch_threads.find_one({"_id": tid, "user_id": uid})
    if not t:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Practice not found."})
    return t


def _msg(role: str, content: str, kind: str = "text", after_take: int = 0) -> dict:
    return {"id": uuid.uuid4().hex, "role": role, "kind": kind, "content": content, "after_take": after_take,
            "at": utcnow()}


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    m = await _member(uid)
    rows = [_card(t, m) async for t in db().pitch_threads.find({"user_id": uid}).sort("updated_at", -1).limit(50)]
    return {"items": rows, "types": [{"key": k, "label": v["label"], "setting": v["setting"], "audience": v["audience"]}
                                     for k, v in TYPES.items()],
            "limits": {"cooldown_minutes": COOLDOWN_MIN, "max_minutes": MAX_SECONDS // 60, "max_mb": MAX_BYTES // (1024 * 1024),
                       "formats": ["MP4", "MOV", "WEBM", "MKV"], "practices_left": m["practices_left"],
                       "chats_left": m["chats_left"]},
            "available": pitch_video.mode() != "off"}


def _fair_use(what: str) -> HTTPException:
    msg = {"practices": f"You've started {MONTHLY_PRACTICES} practices this month. Keep going in one you already have. "
                        "New practices open again on the 1st.",
           "chats": f"You've asked your coach {MONTHLY_CHAT} questions this month. Questions open again on the 1st."}[what]
    return HTTPException(status_code=429, detail={"code": "fair_use", "msg": msg})


@router.post("")
async def start(body: ThreadIn, user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    await plans.require(db(), user, "pitch")
    setting, audience = text(body.setting, 300), text(body.audience, 300)
    if body.pitch_type == "other" and not setting:
        raise HTTPException(status_code=422, detail={"code": "no_setting", "msg": "Tell us where you'll use this pitch."})
    if not await _use(uid, "practices", MONTHLY_PRACTICES):
        raise _fair_use("practices")
    label = TYPES[body.pitch_type]["label"]
    title = label if body.pitch_type != "other" else (setting[:60] or label)
    t = {"pitch_type": body.pitch_type, "setting": setting, "audience": audience}
    s, a = _setting(t)
    ctx = (f"You're practising: **{label if body.pitch_type != 'other' else 'your own pitch'}**. "
           f"Setting: {s} Audience: {a} I'll calibrate the read to that.")
    now = utcnow()
    doc = {"_id": uuid.uuid4().hex, "user_id": uid, **t, "title": title, "takes": [],
           "messages": [_msg("assistant", INTRO.format(context=ctx), "intro")], "last_upload_at": None,
           "busy_until": None, "created_at": now, "updated_at": now}
    await db().pitch_threads.insert_one(doc)
    await events.track(db(), "pitch_thread_started", user_id=uid, props={"pitch_type": body.pitch_type})
    return _public(doc, await _member(uid))


@router.get("/{tid}")
async def one(tid: str, user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    return _public(await _own(tid, uid), await _member(uid))


@router.delete("/{tid}")
async def remove(tid: str, user: dict = Depends(user_dep())):
    res = await db().pitch_threads.delete_one({"_id": tid, "user_id": str(user["_id"])})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Practice not found."})
    return {"ok": True}


# ------------------------------------------------------------------ the video ----
def _ext(content_type: str, filename: str) -> str:
    name = (filename or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in VIDEO_TYPES:
        ext = CT_EXT.get((content_type or "").split(";")[0].strip().lower(), "")
    if ext not in VIDEO_TYPES:
        raise HTTPException(status_code=415, detail={"code": "bad_type", "msg": "Use a video file: MP4, MOV, WEBM or MKV."})
    return ext


def sniff(head: bytes, ext: str) -> bool:
    """Does the file start like the container its name says? (MP4/MOV: an ISO box; WEBM/MKV: an EBML header)"""
    if ext in ("webm", "mkv"):
        return head[:4] == b"\x1a\x45\xdf\xa3"
    return len(head) >= 8 and head[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot")


def mp4_duration(path: str) -> Optional[float]:
    """Seconds from the MP4/MOV `mvhd` box (moov can sit at the end of the file); None when not found."""
    try:
        with open(path, "rb") as f:
            size = os.fstat(f.fileno()).st_size

            def boxes(start: int, end: int):
                p = start
                while p + 8 <= end:
                    f.seek(p)
                    n, typ = struct.unpack(">I4s", f.read(8))
                    hl = 8
                    if n == 1:
                        n = struct.unpack(">Q", f.read(8))[0]
                        hl = 16
                    elif n == 0:
                        n = end - p
                    if n < hl:
                        return
                    yield typ, p + hl, p + n
                    p += n
            for typ, body, end in boxes(0, size):
                if typ != b"moov":
                    continue
                for t2, b2, _e2 in boxes(body, end):
                    if t2 == b"mvhd":
                        f.seek(b2)
                        ver = f.read(4)[0]
                        if ver == 1:
                            f.seek(b2 + 4 + 16)
                            ts, dur = struct.unpack(">IQ", f.read(12))
                            unknown = 0xFFFFFFFFFFFFFFFF
                        else:
                            f.seek(b2 + 4 + 8)
                            ts, dur = struct.unpack(">II", f.read(8))
                            unknown = 0xFFFFFFFF
                        # 0 (fragmented / streamed recordings) and all-ones mean "length not written here"
                        return dur / ts if ts and dur and dur != unknown else None
                return None
    except (OSError, struct.error, IndexError):
        return None
    return None


def tmp_dir() -> str:
    d = os.environ.get("PITCH_TMP_DIR") or tempfile.gettempdir()
    os.makedirs(d, exist_ok=True)
    return d


async def _receive(request: Request, ext: str) -> tuple[str, int]:
    """Stream the request body to a temp file in chunks, never holding the video in memory. Returns (path, size)."""
    fd, path = tempfile.mkstemp(prefix="pitch-", suffix=f".{ext}", dir=tmp_dir())
    size = 0
    try:
        with os.fdopen(fd, "wb") as f:
            buf = b""
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(status_code=413, detail={"code": "too_large", "msg": "That video is larger than 100 MB."})
                buf += chunk
                if len(buf) >= CHUNK:
                    f.write(buf)
                    buf = b""
            if buf:
                f.write(buf)
    except BaseException:
        _drop(path)
        raise
    return path, size


def _drop(path: Optional[str]) -> None:
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


_SEMS: dict = {}


def _sem() -> asyncio.Semaphore:
    """At most PITCH_MAX_CONCURRENCY (4) videos in analysis per worker: each holds a temp file of up to 100 MB."""
    loop = id(asyncio.get_running_loop())
    if loop not in _SEMS:
        _SEMS.clear()
        _SEMS[loop] = asyncio.Semaphore(int(os.environ.get("PITCH_MAX_CONCURRENCY", "4") or 4))
    return _SEMS[loop]


# ------------------------------------------------------------------ the reports ----
def _num(v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise llm.LLMError("pitch: score not a number")
    try:
        x = float(v)
    except ValueError:
        raise llm.LLMError("pitch: score not a number")
    if x != x:
        raise llm.LLMError("pitch: score NaN")
    return round(max(0.0, min(10.0, x)), 1)


def _str(raw: dict, key: str, n: int = 3000) -> str:
    v = raw.get(key)
    if not isinstance(v, str) or not v.strip():
        raise llm.LLMError(f"pitch: missing {key}")
    return v.strip()[:n]


def _list(raw: dict, key: str, lo: int, hi: int, n: int = 1500) -> list[str]:
    v = raw.get(key)
    if v is None and lo == 0:
        return []
    if not isinstance(v, list):
        raise llm.LLMError(f"pitch: {key} is not a list")
    out = [str(x).strip()[:n] for x in v if isinstance(x, (str, int, float)) and str(x).strip()]
    if len(out) < lo:
        raise llm.LLMError(f"pitch: {key} has {len(out)} items, needs {lo}")
    return out[:hi]


def _score(v: int | float) -> int | float:
    return int(v) if float(v).is_integer() else v


def validate_report(raw: dict, prior: Optional[dict]) -> dict:
    """Strict check of the A1 JSON. `prior` = the previous take's report for a comparison."""
    if not isinstance(raw, dict):
        raise llm.LLMError("pitch: not an object")
    kind = "comparison" if prior else "initial"
    sc = raw.get("scorecard")
    if not isinstance(sc, dict):
        raise llm.LLMError("pitch: no scorecard")
    card = {}
    for k in METRIC_KEYS:
        m = sc.get(k)
        if not isinstance(m, dict):
            raise llm.LLMError(f"pitch: scorecard.{k} missing")
        s = _num(m.get("score"))
        row = {"score": _score(s), "justification": _str(m, "justification", 800)}
        if prior:
            prev = float(prior["scorecard"][k]["score"])
            row["previous_score"] = _score(prev)
            row["delta"] = _score(round(s - prev, 1))
        card[k] = row
    out = {"kind": kind, "scorecard": card,
           "delivery_dynamics": _str(raw, "delivery_dynamics", 1200), "vocal_profile": _str(raw, "vocal_profile", 1200),
           "body_language_detail": _str(raw, "body_language_detail", 1200),
           "audience_simulation": _str(raw, "audience_simulation", 900),
           "top_changes": _list(raw, "top_changes", 5, 5, 1500),
           "specific_observations": _list(raw, "specific_observations", 8, 12, 500),
           "practice_assignment": _str(raw, "practice_assignment", 3000)}
    if kind == "initial":
        out["overall_summary"] = _str(raw, "overall_summary", 3000)
        out["strengths"] = _list(raw, "strengths", 4, 6, 800)
        out["weaknesses"] = _list(raw, "weaknesses", 4, 6, 800)
    else:
        out["overall_progress"] = _str(raw, "overall_progress", 3000)
        out["improvements"] = _list(raw, "improvements", 1, 6, 800)
        out["regressions"] = _list(raw, "regressions", 0, 4, 800)
        out["persisting_issues"] = _list(raw, "persisting_issues", 1, 5, 800)
        out["new_strengths"] = _list(raw, "new_strengths", 0, 4, 800)
        out["weaknesses"] = _list(raw, "weaknesses", 2, 5, 800)
    out["overall"] = round(sum(float(card[k]["score"]) for k in METRIC_KEYS) / len(METRIC_KEYS), 1)
    if prior:
        out["previous_overall"] = prior.get("overall")
        out["overall_delta"] = round(out["overall"] - float(prior.get("overall") or 0), 1)
    return strip_providers(out)


def _fake_initial(t: dict, size: int) -> dict:
    base = {"elevator": 6, "discovery": 5, "fee": 5, "other": 6}[t["pitch_type"]]
    adj = [0, -1, 0, -1, 1, -1, 0]
    return {
        "kind": "initial",
        "overall_summary": "You come across as experienced and sincere, with a calm base to build on. The opening is "
                           "steady, but the middle loses energy and the close trails off. Test mode report: live mode "
                           "watches your video and writes this from what it sees.",
        "scorecard": {k: {"score": max(0, min(10, base + adj[i])),
                          "justification": f"[00:{10 + i * 5:02d}] — test mode note for {lbl.lower()}."}
                      for i, (k, lbl) in enumerate(METRICS)},
        "delivery_dynamics": "Starts steady, dips in the middle, and the close is rushed.",
        "vocal_profile": "Clear voice, moderate pace; about 6 fillers ('so', 'basically') in the middle section.",
        "body_language_detail": "Upright posture; hands drop out of frame after the first 20 seconds.",
        "audience_simulation": "A client would trust your experience but might not remember the result you offer.",
        "strengths": ["[00:05] — calm, warm opening that sets a steady tone.",
                      "[00:18] — a concrete example makes your experience believable.",
                      "[00:26] — good eye-line to the lens while naming who you help.",
                      "[00:40] — a natural smile when you mention the client's win."],
        "weaknesses": ["[00:22] — voice drops at the end of key sentences, so they sound unsure.",
                       "[00:30] — filler cluster ('so… basically…') while finding the next point.",
                       "[00:35] — eyes leave the lens when recalling the numbers.",
                       "[00:52] — the call to action trails off instead of landing."],
        "top_changes": [f"**Change {i + 1}: {x}**\n• Why it matters: the client hears certainty.\n• How to do it: record "
                        "three short tries and compare.\n• What good looks like: the line lands and you stop."
                        for i, x in enumerate(["Land the last word of each key sentence", "Replace fillers with a pause",
                                               "Keep your eyes on the lens for the result", "Say the next step slowly",
                                               "Cut the middle to one example"])],
        "specific_observations": [f"[00:{s:02d}] — test mode observation {i + 1}." for i, s in enumerate(range(4, 60, 6))][:9],
        "practice_assignment": "For 7 days, 10 minutes a day: say your pitch three times on camera, each time landing "
                               "the last word of the result sentence. Watch back and count fillers. Stretch: do it in "
                               "60 seconds flat. Record a follow-up take here after the 30-minute pause.",
    }


def _fake_comparison(t: dict, prior: dict) -> dict:
    steps = [1, 0, 1, -1, 1, 2, 1]
    card = {}
    for i, (k, lbl) in enumerate(METRICS):
        prev = float(prior["scorecard"][k]["score"])
        s = max(0.0, min(10.0, prev + steps[i]))
        card[k] = {"score": s, "previous_score": prev, "delta": s - prev,
                   "justification": f"[00:{12 + i * 4:02d}] — test mode comparison note for {lbl.lower()}."}
    return {
        "kind": "comparison",
        "overall_progress": "Clearer and steadier than last time: fewer fillers and a firmer close. Facial expression "
                            "went flatter while you concentrated. Test mode report.",
        "scorecard": card,
        "delivery_dynamics": "More even energy; the middle no longer sags.",
        "vocal_profile": "Fillers down from about 6 to 2; endings land more often.",
        "body_language_detail": "Hands stay in frame now; shoulders a little tense.",
        "audience_simulation": "A client would now remember the result you offer.",
        "improvements": ["[00:22] — the result sentence now lands.", "[00:30] — a pause replaced the filler cluster.",
                         "[00:52] — the call to action is clear."],
        "regressions": ["[00:15] — less smile while concentrating on the words."],
        "persisting_issues": ["[00:35] — eyes still leave the lens on numbers.", "[00:44] — pace rushes near the end."],
        "new_strengths": ["[00:50] — a confident, still finish."],
        "weaknesses": ["Eye contact on numbers.", "Rushed pace in the last 15 seconds.", "Tight shoulders."],
        "top_changes": [f"**Next {i + 1}: {x}**\n• Why it matters: trust.\n• How to do it: one drill a day.\n• What good "
                        "looks like: calm and clear." for i, x in enumerate(
                            ["Hold the lens on numbers", "Slow the last 15 seconds", "Relax the shoulders",
                             "Smile on the client's win", "Keep the pause before the ask"])],
        "specific_observations": [f"[00:{s:02d}] — test mode take-2 observation {i + 1}." for i, s in enumerate(range(5, 60, 6))][:8],
        "practice_assignment": "This week, say only the last 20 seconds of your pitch five times a day, slowly, eyes on "
                               "the lens. Then record a full take after the pause.",
    }


def _framing(t: dict, k: dict, prior: Optional[dict], duration_s: Optional[float]) -> str:
    setting, audience = _setting(t)
    preset = TYPES[t["pitch_type"]]
    lines = [f"PRACTICE TYPE: {preset['label'] if t['pitch_type'] != 'other' else 'Something else (the member described it)'}",
             f"SETTING: {setting or 'not given — infer silently'}", f"AUDIENCE: {audience or 'not given — infer silently'}"]
    if preset["bar"]:
        lines.append(f"WHAT GOOD LOOKS LIKE FOR THIS MOMENT: {preset['bar']}")
    kb = system_block(k)
    if kb:
        lines.append(kb)
    if duration_s:
        lines.append(f"CLIP LENGTH (from the member's device): about {int(duration_s)} seconds.")
    lines.append("The member speaks English.")
    ctx = "\n".join(lines)
    if not prior:
        return f"{ctx}\n\nWatch this video and return the first-analysis JSON report exactly as instructed."
    return (f"{ctx}\n\n{COMPARISON}\n\nPRIOR REPORT (your previous analysis of this member's last take):\n"
            f"{json.dumps(prior, ensure_ascii=False)}")


def _check_cooldown(last) -> None:
    cd = _cooldown(last)
    if not cd["can_upload"]:
        mins = max(1, -(-cd["cooldown_seconds_remaining"] // 60))
        raise HTTPException(status_code=429, detail={
            "code": "cooldown", "seconds": cd["cooldown_seconds_remaining"], "next_upload_at": cd["next_upload_at"],
            "msg": f"Give the feedback time to land. You can upload your next take in {mins} min."})


TOO_LONG = {"code": "too_long", "msg": "Keep your video under 8 minutes."}
NO_LENGTH = {"code": "no_duration", "msg": "We couldn't tell how long this video is. Record it here, or upload it as "
                                          "an MP4 or MOV file."}


async def _lock_member(uid: str, now) -> bool:
    """One take in analysis per member (the 30-minute pause is per member, so two practices can't race it)."""
    try:
        await db().pitch_members.update_one({"_id": uid}, {"$setOnInsert": {"busy_until": None}}, upsert=True)
    except DuplicateKeyError:
        pass
    got = await db().pitch_members.update_one(
        {"_id": uid, "$or": [{"busy_until": None}, {"busy_until": {"$lt": now}}]},
        {"$set": {"busy_until": now + timedelta(minutes=15)}})
    return bool(got.matched_count)


@router.post("/{tid}/take")
async def take(tid: str, request: Request, duration_s: Optional[float] = Query(None, ge=0, le=36000),
               filename: str = Query("", max_length=200), user: dict = Depends(user_dep())):
    """One take: the raw video is the request body. Metered (`pitch`), refunded on any failure."""
    uid = str(user["_id"])
    await plans.require(db(), user, "pitch")
    await _own(tid, uid)
    _check_cooldown(await _last_upload(uid))
    if pitch_video.mode() == "off":
        raise HTTPException(status_code=503, detail={"code": "paused", "msg": "Pitch Practice is paused right now. Try again later."})
    ext = _ext(request.headers.get("content-type", ""), filename)
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > MAX_BYTES:
        raise HTTPException(status_code=413, detail={"code": "too_large", "msg": "That video is larger than 100 MB."})
    if duration_s is not None and duration_s > MAX_SECONDS + 2:
        raise HTTPException(status_code=413, detail=TOO_LONG)
    if duration_s is None and ext in ("webm", "mkv"):          # we don't read a length from these containers
        raise HTTPException(status_code=422, detail=NO_LENGTH)
    now = utcnow()
    got = await db().pitch_threads.update_one(
        {"_id": tid, "user_id": uid, "$or": [{"busy_until": None}, {"busy_until": {"$lt": now}}]},
        {"$set": {"busy_until": now + timedelta(minutes=15)}})
    if not got.matched_count:
        raise HTTPException(status_code=409, detail={"code": "busy", "msg": "A take is already being analysed. Wait for it to finish."})
    member_locked = False

    async def unlock() -> None:
        await db().pitch_threads.update_one({"_id": tid}, {"$set": {"busy_until": None}})
        if member_locked:
            await db().pitch_members.update_one({"_id": uid}, {"$set": {"busy_until": None}})
    try:
        member_locked = await _lock_member(uid, now)
        if not member_locked:
            raise HTTPException(status_code=409, detail={
                "code": "busy", "msg": "Your last take is still being analysed. Wait for it to finish."})
        t = await _own(tid, uid)          # read again under the locks: a take may have finished in between
        _check_cooldown(await _last_upload(uid))
    except HTTPException:
        await unlock()
        raise

    path: Optional[str] = None

    async def work(plan: str):
        nonlocal path
        path, size = await _receive(request, ext)
        if size < 1024:
            raise HTTPException(status_code=422, detail={"code": "empty", "msg": "That video is empty. Record it again."})
        with open(path, "rb") as f:
            head = f.read(64)
        if not sniff(head, ext):
            raise HTTPException(status_code=415, detail={"code": "bad_type", "msg": "That file doesn't look like a video. Use MP4, MOV, WEBM or MKV."})
        secs = mp4_duration(path) if ext in ("mp4", "m4v", "mov") else None
        if secs is not None and secs > MAX_SECONDS + 2:
            raise HTTPException(status_code=413, detail=TOO_LONG)
        length = secs if secs is not None else duration_s
        if length is None:
            raise HTTPException(status_code=422, detail=NO_LENGTH)
        takes = t.get("takes") or []
        prior = takes[-1]["report"] if takes else None
        k = await knowledge(db(), user)
        sem = _sem()
        try:
            await asyncio.wait_for(sem.acquire(), timeout=60)
        except (asyncio.TimeoutError, TimeoutError):
            raise HTTPException(status_code=503, detail={"code": "busy", "msg": "Many people are practising right now. Try again in a few minutes. This didn't use up your go."})
        info: dict = {}
        try:
            raw = await pitch_video.analyse(
                path, mime=VIDEO_TYPES[ext], system=SYSTEM, prompt=_framing(t, k, prior, length),
                fake=lambda: _fake_comparison(t, prior) if prior else _fake_initial(t, size),
                max_seconds=MAX_SECONDS + 2, info=info)
        except pitch_video.TooLong as e:
            log.info("pitch take refused by the engine's length: %.1f s", e.seconds)
            raise HTTPException(status_code=413, detail=TOO_LONG)
        except pitch_video.BadOutput as e:
            raise llm.LLMError(str(e))
        except pitch_video.VideoError as e:
            log.warning("pitch video failed: %s", e)
            raise HTTPException(status_code=503, detail={
                "code": "video_busy", "msg": "The analysis is taking longer than expected. Try again in a moment. "
                                             "This didn't use up your go."})
        finally:
            sem.release()
            _drop(path)                 # the video is gone from our side before we even save the report
        if info.get("seconds"):
            length = info["seconds"]    # the engine's own measurement beats the header and the browser
        report = validate_report(raw, prior)
        n = len(takes) + 1
        entry = {"n": n, "kind": report["kind"], "at": utcnow(), "duration_s": round(length, 1) if length else None,
                 "size": size, "overall": report["overall"], "report": report}
        now2 = utcnow()
        await db().pitch_threads.update_one({"_id": tid}, {"$push": {"takes": entry},
                                                           "$set": {"last_upload_at": now2, "updated_at": now2}})
        await events.track(db(), "pitch_take_analysed", user_id=uid,
                           props={"kind": report["kind"], "overall": report["overall"], "take": n})
        return _public(await _own(tid, uid), await _member(uid))

    try:
        return await run_metered(db(), user, "pitch", work)
    finally:
        _drop(path)
        await unlock()


# ------------------------------------------------------------------ follow-up chat ----
def _fake_reply(t: dict, question: str) -> str:
    takes = t.get("takes") or []
    if not takes:
        return ("Upload your first take and I'll give you a full read. Until then: say your pitch out loud three times "
                "and notice where you run out of breath.")
    rep = takes[-1]["report"]
    first = rep["top_changes"][0].split("\n")[0]
    return (f"Good question. The first thing I'd work on is still this: {first}\n\n"
            "**Try this today**\n\n- Say only that part five times, slowly.\n- Record the fifth one and watch it back.\n\n"
            f"Your overall score on the last take was **{rep['overall']}/10**. Test mode reply.")


def _history(t: dict) -> list[dict]:
    """Chat turns after the intro, alternating user/assistant, starting with the member."""
    out: list[dict] = []
    for m in t.get("messages") or []:
        if m.get("kind") == "intro":
            continue
        if not out and m["role"] != "user":
            continue
        if out and out[-1]["role"] == m["role"]:
            out[-1]["content"] += "\n\n" + m["content"]
        else:
            out.append({"role": m["role"], "content": m["content"]})
    out = out[-20:]
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


@router.post("/{tid}/chat")
async def chat(tid: str, body: ChatIn, user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    await plans.require(db(), user, "pitch")
    t = await _own(tid, uid)
    if sum(1 for m in t.get("messages") or [] if m["role"] == "user") >= MAX_CHAT:
        raise HTTPException(status_code=429, detail={"code": "chat_full", "msg": "This practice has a lot of chat already. Start a new practice to keep going."})
    msg = body.message.strip()
    if not msg:
        raise HTTPException(status_code=422, detail={"code": "empty", "msg": "Type your question."})
    if not await _use(uid, "chats", MONTHLY_CHAT):
        raise _fair_use("chats")
    try:
        return await _chat_reply(tid, uid, t, msg, user)
    except BaseException:
        await _give_back(uid, "chats")        # no reply, no question used
        raise


async def _chat_reply(tid: str, uid: str, t: dict, msg: str, user: dict) -> dict:
    takes = t.get("takes") or []
    setting, audience = _setting(t)
    reports = [{"take": x["n"], **x["report"]} for x in takes[-2:]]
    kb = system_block(await knowledge(db(), user))
    system = (f"{SYSTEM}\n\n{FOLLOWUP}\n\nPRACTICE TYPE: {TYPES[t['pitch_type']]['label']}\nSETTING: {setting}\n"
              f"AUDIENCE: {audience}\n{kb}\n\n"
              + (f"YOUR REPORT(S) SO FAR (latest last):\n{json.dumps(reports, ensure_ascii=False)}" if reports
                 else "No take uploaded yet: help them prepare, and invite them to record their first take."))
    history = _history(t)
    if history and history[-1]["role"] == "user":
        history[-1]["content"] += "\n\n" + msg
    else:
        history.append({"role": "user", "content": msg})
    try:
        reply = await llm.complete_chat(task="pitch_chat", system=system, messages=history,
                                        fake=lambda: _fake_reply(t, msg), model="strong", max_tokens=1500)
    except llm.LLMError:
        raise busy_error()
    reply = strip_providers((reply or "").strip())
    if not reply:
        raise busy_error()
    n = len(takes)
    await db().pitch_threads.update_one({"_id": tid}, {
        "$push": {"messages": {"$each": [_msg("user", msg, after_take=n), _msg("assistant", reply, after_take=n)]}},
        "$set": {"updated_at": utcnow()}})
    await events.track(db(), "pitch_chat", user_id=uid)
    return _public(await _own(tid, uid), await _member(uid))
