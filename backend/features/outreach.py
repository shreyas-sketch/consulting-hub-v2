"""Outreach Drafter: three ways to write to someone you know. The member copies one and sends it themselves.

outreach {_id, user_id, contact_id?, contact: {name, role, company, relationship, context}, channel, goal,
          variants: [{style short|warm|direct, subject, text}], chosen?, status draft|sent, sent_at?, at, updated_at}

Follows the current hub's 5:95 Principle GPT (backend/gpts/prompts/5-95-principle.md): warm contacts first, value
before any pitch, never salesy. Nothing is sent from the hub. Marking a draft as sent also marks the contact as
contacted in the Warm Network Finder.
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import indexes
import llm
import plans
from core.deps import user_dep
from growth import events
from growth.clock import utcnow
from state import db
from util import iso

from .common import run_metered, text
from .knowledge import knowledge, system_block
from .network import NO_VENDOR

router = APIRouter(prefix="/outreach", tags=["outreach"])

FEATURE = METER = "outreach"
STYLES = ("short", "warm", "direct")
CHANNELS = {"linkedin": "LinkedIn message", "whatsapp": "WhatsApp message", "email": "email"}
GOALS = {"reconnect": "reconnect and restart the relationship (no ask yet)",
         "intro": "ask for an introduction to someone who might need the consultant's help",
         "diagnostic_call": "offer a short, free 20-30 minute diagnostic call about one problem"}
MAX_CHARS = {"short": 450, "warm": 1100, "direct": 900}

events.register("outreach_drafted", "Outreach Drafter: draft made (props.channel, goal)")
events.register("outreach_sent", "Outreach Drafter: member marked a draft as sent (props.channel)")
indexes.register("outreach", [("user_id", 1), ("at", -1)])

SYSTEM = (
    "You write outreach messages for an experienced Indian professional who is launching as a consultant. They are "
    "writing to people they already know. Follow the 5:95 principle: relationships and value first, almost no "
    "selling. Every message must sound like a real person typing to someone they know: plain, warm, specific, short "
    "sentences, Indian English is fine. Never hard-sell, never pressure, never use phrases like 'synergy', "
    "'leverage', 'I hope this finds you well' or 'quick call to explore'. Never invent shared history, numbers or "
    "facts: use only what you are told; where a personal detail would help but is missing, write it as "
    "[square brackets] for the member to fill. One clear, easy next step at most. WhatsApp: no subject, very short "
    "lines. LinkedIn: no subject. Email: a short, plain subject line. Sign off with the sender's first name. "
    + NO_VENDOR
)


class DraftIn(BaseModel):
    contact_id: Optional[str] = Field(None, max_length=40)
    name: str = Field("", max_length=120)
    role: str = Field("", max_length=160)
    company: str = Field("", max_length=160)
    relationship: str = Field("", max_length=200)        # e.g. "worked together at Tata Steel 2012-16"
    context: str = Field("", max_length=1000)            # what you know, last time you spoke, a news item
    channel: Literal["linkedin", "whatsapp", "email"] = "linkedin"
    goal: Literal["reconnect", "intro", "diagnostic_call"] = "reconnect"


def _first(name: str) -> str:
    return (name or "").split()[0] if (name or "").strip() else "there"


def _fake(c: dict, channel: str, goal: str, me: str, k: dict) -> dict:
    to, sign = _first(c["name"]), _first(me) if me else "[your name]"
    rel = c.get("relationship") or "[how you know each other]"
    niche = k.get("niche") or "[your niche]"
    ask = {"reconnect": "Would love to hear what you're working on these days.",
           "intro": f"Is there someone in your circle dealing with this I could speak to? Happy to return the favour.",
           "diagnostic_call": "If it's useful, I'm happy to do a free 20-minute call to look at one problem with you. No pitch."}[goal]
    subj = lambda s: s if channel == "email" else ""  # noqa: E731
    return {"variants": [
        {"style": "short", "subject": subj(f"Catching up, {to}"), "text": f"Hi {to}, it's been a while since {rel}. {ask}\n\n{sign}"},
        {"style": "warm", "subject": subj("It's been a while"),
         "text": f"Hi {to},\n\nI was thinking about {rel} the other day and it made me smile.\n\nI've recently started "
                 f"working as a consultant in {niche}. {c.get('context') or '[one line on what you know about their work]'}\n\n"
                 f"{ask}\n\nWarmly,\n{sign}"},
        {"style": "direct", "subject": subj(f"A question for you, {to}"),
         "text": f"Hi {to}, I now help businesses with {niche}. {ask}\n\nThanks,\n{sign}"},
    ], "note": "Test mode drafts. Live mode writes these from what you typed."}


def _prompt(c: dict, channel: str, goal: str, me: str, k: dict) -> str:
    return (f"{system_block(k) or 'Niche not chosen yet.'}\nConsultant title: {k.get('consultant_title') or 'not set'}\n"
            f"Sender's name: {me or 'not given'}\n\nWRITING TO:\nName: {c['name']}\nRole: {c.get('role') or 'not given'}\n"
            f"Company: {c.get('company') or 'not given'}\nHow they know each other: {c.get('relationship') or 'not given'}\n"
            f"What the sender knows / context: {c.get('context') or 'nothing more'}\n\n"
            f"Channel: {CHANNELS[channel]}\nGoal: {GOALS[goal]}\n\n"
            "Write exactly 3 variants: short (2-3 lines), warm (personal, refers to how they know each other), direct "
            "(says the reason for writing in the first two lines, still polite). Plain text, line breaks allowed.\n"
            'JSON: {"variants": [{"style": "short", "subject": "", "text": ""}, {"style": "warm", "subject": "", "text": ""}, '
            '{"style": "direct", "subject": "", "text": ""}]}')


def _clean_text(v, n: int) -> str:
    lines = [" ".join(ln.split()) for ln in str(v or "").replace("\r", "").split("\n")]
    out = "\n".join(lines).strip()
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out[:n]


def public(o: dict) -> dict:
    return {"id": o["_id"], "contact_id": o.get("contact_id"), "contact": o["contact"], "channel": o["channel"],
            "goal": o["goal"], "variants": o["variants"], "chosen": o.get("chosen"), "status": o.get("status", "draft"),
            "sent_at": iso(o.get("sent_at")), "at": iso(o["at"]), "updated_at": iso(o.get("updated_at") or o["at"])}


@router.post("")
async def draft(body: DraftIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    c = {"name": body.name.strip(), "role": body.role.strip(), "company": body.company.strip(),
         "relationship": body.relationship.strip(), "context": body.context.strip()}
    await plans.require(d, user, FEATURE)
    if body.contact_id:
        n = await d.contacts.find_one({"_id": body.contact_id, "user_id": uid})
        if not n:
            raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "That contact is no longer in your list."})
        c["name"] = c["name"] or n.get("name", "")
        c["role"] = c["role"] or n.get("position", "")
        c["company"] = c["company"] or n.get("company", "")
        extra = " ".join(x for x in [n.get("notes"), f"Suggested angle: {n['angle']}" if n.get("angle") else ""] if x)
        c["context"] = " ".join(x for x in [c["context"], extra] if x)[:1000]
    if len(c["name"]) < 2:
        raise HTTPException(status_code=422, detail={"code": "name", "msg": "Type the person's name."})

    async def work(plan: str):
        k = await knowledge(d, user)
        me = user.get("name") or ""
        raw = await llm.complete_json(task="outreach_draft", system=SYSTEM, prompt=_prompt(c, body.channel, body.goal, me, k),
                                      fake=lambda: _fake(c, body.channel, body.goal, me, k), model="fast", max_tokens=1400)
        got: dict[str, dict] = {}
        for v in raw.get("variants") or []:
            if not isinstance(v, dict):
                continue
            style = str(v.get("style") or "").lower().strip()
            body_text = _clean_text(v.get("text"), MAX_CHARS.get(style, 900))
            if style in STYLES and style not in got and len(body_text) >= 20:
                got[style] = {"style": style, "subject": text(v.get("subject"), 120) if body.channel == "email" else "",
                              "text": body_text}
        if len(got) < 3:
            raise llm.LLMError("outreach: fewer than 3 variants")
        now = utcnow()
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "contact_id": body.contact_id, "contact": c,
               "channel": body.channel, "goal": body.goal, "variants": [got[s] for s in STYLES], "chosen": None,
               "status": "draft", "at": now, "updated_at": now}
        await d.outreach.insert_one(doc)
        await events.track(d, "outreach_drafted", user_id=uid, props={"channel": body.channel, "goal": body.goal})
        return public(doc)
    return await run_metered(d, user, METER, work, access=FEATURE)


@router.get("")
async def mine(status: Literal["", "draft", "sent"] = "", contact_id: str = Query("", max_length=40),
               user: dict = Depends(user_dep())):
    await plans.require(db(), user, FEATURE)
    f: dict = {"user_id": str(user["_id"])}
    if status:
        f["status"] = status
    if contact_id:
        f["contact_id"] = contact_id
    return {"items": [public(o) async for o in db().outreach.find(f).sort("at", -1).limit(100)]}


async def _own(oid: str, user: dict) -> dict:
    await plans.require(db(), user, FEATURE)
    o = await db().outreach.find_one({"_id": oid, "user_id": str(user["_id"])})
    if not o:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Draft not found."})
    return o


@router.get("/{oid}")
async def one(oid: str, user: dict = Depends(user_dep())):
    return public(await _own(oid, user))


class VariantIn(BaseModel):
    style: Literal["short", "warm", "direct"]
    subject: str = Field("", max_length=120)
    text: str = Field(..., min_length=1, max_length=2000)


class PatchIn(BaseModel):
    variants: Optional[list[VariantIn]] = Field(None, max_length=3)
    chosen: Optional[Literal["short", "warm", "direct"]] = None
    status: Optional[Literal["draft", "sent"]] = None


@router.patch("/{oid}")
async def patch(oid: str, body: PatchIn, user: dict = Depends(user_dep())):
    o = await _own(oid, user)
    s: dict = {"updated_at": utcnow()}
    if body.variants is not None:
        edits = {v.style: v for v in body.variants}
        s["variants"] = [{"style": v["style"], "subject": text(edits[v["style"]].subject, 120) if v["style"] in edits else v.get("subject", ""),
                          "text": _clean_text(edits[v["style"]].text, 2000) if v["style"] in edits else v["text"]}
                         for v in o["variants"]]
    if body.chosen is not None:
        s["chosen"] = body.chosen
    if body.status is not None and body.status != o.get("status"):
        s["status"] = body.status
        s["sent_at"] = utcnow() if body.status == "sent" else None
        if body.status == "sent":
            if o.get("contact_id"):
                await db().contacts.update_one({"_id": o["contact_id"], "user_id": o["user_id"]},
                                               {"$set": {"status": "contacted", "contacted_at": s["sent_at"]}})
            await events.track(db(), "outreach_sent", user_id=o["user_id"], props={"channel": o["channel"]})
    await db().outreach.update_one({"_id": oid}, {"$set": s})
    o.update(s)
    return public(o)


@router.delete("/{oid}")
async def remove(oid: str, user: dict = Depends(user_dep())):
    o = await _own(oid, user)
    await db().outreach.delete_one({"_id": o["_id"]})
    return {"ok": True}
