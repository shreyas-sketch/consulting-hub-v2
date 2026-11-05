"""Proposal Follow-through: call notes in, a client-ready proposal and a follow-up plan out.

proposals {_id, user_id, client: {company, person, role}, input: {notes, fee_low, fee_high, call_prep_id},
           title, data: {context, objective, phases, deliverables, timeline, options, next_steps}, markdown,
           followups: [{n, day, text, due (YYYY-MM-DD IST)|None, done, done_at}],
           status draft|sent|fu1|fu2|fu3|won|lost, sent_at, history: [{status, at}], at, updated_at}

The approach is the six stages from "How This Becomes Your Proposal" in Akshat's Strategic Thinking Framework
(backend/gpts/prompts/strategy-thinking-framework.md): Scope Note → Objective Statement → Diagnostic Report →
Options Paper → Prioritisation & Recommendation → Implementation Charter. Three investment options in ₹ follow the
Consulting Pricing Advisor (anchor with a fuller option, offer alternatives instead of discounts) and stay near the
member's own fee range. The server writes the Markdown from checked fields, so every ₹ figure is formatted
and in range. The member sends the proposal and the follow-ups; the daily job "proposal_followups" (09:30 IST)
puts a reminder in their inbox when a follow-up is due.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator

import indexes
import llm
import plans
from core.deps import user_dep
from core.errors import NotFound
from growth import events
from growth.clock import IST, as_utc, utcnow
from jobs import registry as jobs
from notify import service as notify
from state import db
from util import inr, iso

from .common import (
    NO_VENDOR,
    as_dict,
    as_list,
    clamp_int,
    run_metered,
    strip_providers,
    text,
    text_list,
)
from .knowledge import knowledge, links_in, no_links, own_links, system_block

router = APIRouter(prefix="/proposals", tags=["proposals"])

FEATURE, METER = "proposal", "proposal"
STAGES = [("Scope Note", "Step 1 · Understand Scope"), ("Objective Statement", "Step 2 · Identify Objective"),
          ("Diagnostic Report", "Step 3 · Identify Framework"), ("Options Paper", "Step 4 · Generate Options"),
          ("Prioritisation & Recommendation", "Step 5 · Prioritize Options"),
          ("Implementation Charter", "Step 6 · Implementation Charter")]
FOLLOW_DAYS = (2, 5, 10)
STATUSES = ("draft", "sent", "fu1", "fu2", "fu3", "won", "lost")
OPEN = ("sent", "fu1", "fu2")

events.register("proposal_made", "Proposal Follow-through: proposal written (props.company)")
events.register("proposal_status", "Proposal Follow-through: status changed (props.status)")
indexes.register("proposals", [("user_id", 1), ("at", -1)])
indexes.register("proposals", [("status", 1), ("sent_at", 1)])
notify.register_kind("proposal")
jobs.register("proposal_followups", "Proposal follow-up reminders", ("daily", 9, 30), "features.proposals:job_followups")

SYSTEM = (
    "You turn a discovery call into a clear, client-ready consulting proposal for an experienced Indian professional "
    "who is launching as a consultant. Use only what the call notes say about the client; never invent facts, numbers "
    "or results; where a figure is needed but unknown, write [number] for the consultant to fill. The approach follows "
    "Akshat Dani's six proposal stages, in order: Scope Note (Step 1 Understand Scope), Objective Statement (Step 2 "
    "Identify Objective: from, to, by when), Diagnostic Report (Step 3 Identify Framework), Options Paper (Step 4 "
    "Generate Options), Prioritisation & Recommendation (Step 5 business benefit x ease), Implementation Charter "
    "(Step 6 owner, stakeholders, metrics). Price with three options in Indian rupees, whole numbers, near the "
    "consultant's fee range: a focused option, a recommended option and a fuller option (anchor with the fuller one; "
    "alternatives instead of discounts). Plain, confident English, short sentences, no buzzwords. Follow-up messages "
    "are short, warm and helpful, never pushy: day 2 checks it arrived and offers to walk through it, day 5 adds one "
    "useful thought for their problem, day 10 makes it easy to say yes, no or not now. Never include links or web "
    "addresses; the consultant adds their own. " + NO_VENDOR
)


class ProposalIn(BaseModel):
    company: str = Field(..., min_length=2, max_length=120)
    person: str = Field("", max_length=120)
    role: str = Field("", max_length=120)
    notes: str = Field(..., min_length=40, max_length=6000)
    fee_low_inr: int = Field(..., ge=5000, le=10_000_000)
    fee_high_inr: int = Field(..., ge=5000, le=10_000_000)
    call_prep_id: Optional[str] = Field(None, max_length=40)

    @model_validator(mode="after")
    def _order(self):
        if self.fee_high_inr < self.fee_low_inr:
            self.fee_low_inr, self.fee_high_inr = self.fee_high_inr, self.fee_low_inr
        return self


def _fake(body: ProposalIn) -> dict:
    co = body.company.strip()
    lo, hi = body.fee_low_inr, body.fee_high_inr
    first = (body.person or "there").split()[0]
    return {"title": f"Proposal for {co}",
            "context": f"In our conversation you described what is slowing {co} down. This proposal sets out how we "
                       "would find the real cause, agree what success looks like and put a plan in place. (Test mode: live "
                       "mode writes this from your call notes.)",
            "objective": {"from": "[where things are today]", "to": "[the result you want]", "by_when": "[date]"},
            "phases": [{"stage": s, "what": f"{s}: agreed with you and written up in one page.", "when": f"Week {i + 1}"}
                       for i, (s, _) in enumerate(STAGES)],
            "deliverables": ["A one-page scope note", "A diagnostic report with findings", "An options paper with a clear recommendation",
                             "An implementation charter with owners and weekly measures"],
            "timeline": [{"when": "Weeks 1-2", "what": "Scope and diagnosis"}, {"when": "Weeks 3-4", "what": "Options and recommendation"},
                         {"when": "Weeks 5-6", "what": "Implementation charter and handover"}],
            "options": [{"name": "Diagnose", "price_inr": lo, "includes": "Scope note, objective statement and diagnostic report"},
                        {"name": "Diagnose and plan", "price_inr": (lo + hi) // 2, "includes": "Everything in Diagnose, plus options paper and recommendation"},
                        {"name": "Plan and launch", "price_inr": hi, "includes": "Everything above, plus implementation charter and 4 weeks of support"}],
            "next_steps": ["Reply with the option that suits you", "We fix a start date", "First working session in week 1"],
            "followups": [{"day": 2, "text": f"Hi {first}, just checking the proposal reached you. Happy to walk you through it on a 15-minute call this week."},
                          {"day": 5, "text": f"Hi {first}, one thought since we spoke: [one useful idea for their problem]. It fits into the diagnostic stage of the proposal."},
                          {"day": 10, "text": f"Hi {first}, I don't want to crowd your inbox. If now isn't the right time, that's completely fine. Just let me know either way."}]}


def _prompt(body: ProposalIn, k: dict, me: str, prep: Optional[dict]) -> str:
    extra = ""
    if prep:
        extra = ("\nFROM THE CALL PREP:\nLikely problems: " + "; ".join(p["problem"] for p in prep.get("problems") or []) +
                 "\nNext step proposed: " + (prep.get("next_step") or ""))
    return (f"{system_block(k) or 'Niche not chosen yet.'}\nConsultant: {me or 'not given'}, "
            f"{k.get('consultant_title') or 'Consultant'}\n\nCLIENT: {body.company}; {body.person or 'contact not named'}"
            f"{', ' + body.role if body.role else ''}\nFEE RANGE: {inr(body.fee_low_inr)} to {inr(body.fee_high_inr)} per engagement\n"
            f"CALL NOTES:\n{body.notes}{extra}\n\n"
            "Write: title, context (2-4 sentences in the client's terms), objective (from, to, by_when), phases (exactly "
            "6, one per stage in order, each with what the client receives and when), deliverables (4-6), timeline "
            "(3-5 rows), options (exactly 3, each with name, price_inr and includes), next_steps (2-4), followups "
            "(exactly 3: day 2, day 5, day 10, each a short message the consultant can send).\n"
            'JSON: {"title": "", "context": "", "objective": {"from": "", "to": "", "by_when": ""}, '
            '"phases": [{"stage": "Scope Note", "what": "", "when": ""}], "deliverables": [""], '
            '"timeline": [{"when": "", "what": ""}], "options": [{"name": "", "price_inr": 0, "includes": ""}], '
            '"next_steps": [""], "followups": [{"day": 2, "text": ""}]}')


def _cell(v: str) -> str:
    return (v or "").replace("|", "/").replace("\n", " ").strip() or "—"


def build_markdown(title: str, client: dict, me: str, my_title: str, data: dict, on: date) -> str:
    who = ", ".join(x for x in [client.get("person"), client.get("role"), client["company"]] if x)
    o = data["objective"]
    lines = [f"# {title}", "", f"**Prepared for:** {who}  ", f"**Prepared by:** {', '.join(x for x in [me, my_title] if x) or '[your name]'}  ",
             f"**Date:** {on.day} {on.strftime('%B %Y')}", "", "## Context", "", data["context"], "",
             "## Objective", "", "| From | To | By when |", "|---|---|---|",
             f"| {_cell(o['from'])} | {_cell(o['to'])} | {_cell(o['by_when'])} |", "",
             "## Approach", "", "| Stage | Framework step | What you receive | When |", "|---|---|---|---|"]
    lines += [f"| {p['stage']} | {p['step']} | {_cell(p['what'])} | {_cell(p['when'])} |" for p in data["phases"]]
    lines += ["", "## Deliverables", ""] + [f"- {x}" for x in data["deliverables"]]
    lines += ["", "## Timeline", "", "| When | What happens |", "|---|---|"]
    lines += [f"| {_cell(t['when'])} | {_cell(t['what'])} |" for t in data["timeline"]]
    lines += ["", "## Investment", "", "| Option | Investment | What's included |", "|---|---|---|"]
    lines += [f"| {_cell(x['name'])} | {inr(x['price_inr'])} | {_cell(x['includes'])} |" for x in data["options"]]
    lines += ["", "Fees exclude GST where it applies.", "", "## Next steps", ""]
    lines += [f"{i + 1}. {x}" for i, x in enumerate(data["next_steps"])]
    return "\n".join(lines) + "\n"


def _ist_today(now=None) -> date:
    return as_utc(now or utcnow()).astimezone(IST).date()


def next_followup(p: dict) -> Optional[dict]:
    if p.get("status") not in OPEN:
        return None
    for f in p.get("followups") or []:
        if not f.get("done"):
            return f
    return None


def public(p: dict, today: Optional[date] = None) -> dict:
    today = today or _ist_today()
    nf = next_followup(p)
    nxt = None
    if nf:
        nxt = {"n": nf["n"], "day": nf["day"], "due": nf.get("due"), "text": nf["text"],
               "is_due": bool(nf.get("due") and nf["due"] <= today.isoformat())}
    return {"id": p["_id"], "client": p["client"], "input": p["input"], "title": p["title"], "data": p.get("data"),
            "markdown": p["markdown"], "followups": p["followups"], "status": p["status"], "next": nxt,
            "sent_at": iso(p.get("sent_at")), "history": [{"status": h["status"], "at": iso(h["at"])} for h in p.get("history") or []],
            "at": iso(p["at"]), "updated_at": iso(p.get("updated_at") or p["at"])}


@router.post("")
async def make(body: ProposalIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    await plans.require(d, user, FEATURE)
    prep = await d.call_preps.find_one({"_id": body.call_prep_id, "user_id": uid}) if body.call_prep_id else None

    async def work(plan: str):
        k = await knowledge(d, user)
        me = user.get("name") or ""
        raw = as_dict(await llm.complete_json(task="proposal", system=SYSTEM, prompt=_prompt(body, k, me, prep),
                                              fake=lambda: _fake(body), model="strong", max_tokens=2600))
        lo, hi = body.fee_low_inr, body.fee_high_inr
        o = as_dict(raw.get("objective"))
        phases_raw = [x for x in as_list(raw.get("phases")) if isinstance(x, dict)]
        phases = []
        for i, (stage, step) in enumerate(STAGES):
            src = next((x for x in phases_raw if text(x.get("stage"), 60).lower() == stage.lower()),
                       phases_raw[i] if i < len(phases_raw) else {})
            what = text(src.get("what"), 300)
            if not what:
                raise llm.LLMError(f"proposal: stage {stage} missing")
            phases.append({"stage": stage, "step": step, "what": what, "when": text(src.get("when"), 40)})
        options = []
        for x in as_list(raw.get("options"))[:3]:
            if not isinstance(x, dict) or not text(x.get("name"), 60):
                continue
            price = clamp_int(x.get("price_inr"), max(1000, lo // 2), hi * 3 // 2, (lo + hi) // 2)
            options.append({"name": text(x.get("name"), 60), "price_inr": int(round(price / 1000.0) * 1000) or price,
                            "includes": text(x.get("includes"), 300)})
        options.sort(key=lambda x: x["price_inr"])
        follow = {}
        for f in as_list(raw.get("followups")):
            if isinstance(f, dict) and clamp_int(f.get("day"), 0, 30, 0) in FOLLOW_DAYS:
                day = clamp_int(f.get("day"), 0, 30, 0)
                t = (f.get("text") if isinstance(f.get("text"), str) else "").strip()[:1200]
                if len(t) >= 20 and day not in follow:
                    follow[day] = t
        data = {"context": text(raw.get("context"), 1200),
                "objective": {"from": text(o.get("from"), 200), "to": text(o.get("to"), 200), "by_when": text(o.get("by_when"), 80)},
                "phases": phases, "deliverables": text_list(raw.get("deliverables"), 6, 200),
                "timeline": [{"when": text(t.get("when"), 40), "what": text(t.get("what"), 200)}
                             for t in as_list(raw.get("timeline"))[:5] if isinstance(t, dict) and text(t.get("what"), 200)],
                "options": options, "next_steps": text_list(raw.get("next_steps"), 4, 200)}
        if not data["context"] or len(options) < 3 or len(follow) < 3 or not data["deliverables"] or not data["next_steps"]:
            raise llm.LLMError("proposal: incomplete")
        # No invented links: only the member's own (site, booking link) or ones they typed in the call notes stay.
        allowed = (await own_links(d, user)) | links_in(body.notes)
        data = no_links(strip_providers(data), allowed)
        follow = no_links(strip_providers(follow), allowed)
        title = no_links(strip_providers(text(raw.get("title"), 140)), allowed) or f"Proposal for {body.company}"
        client = {"company": body.company.strip(), "person": body.person.strip(), "role": body.role.strip()}
        now = utcnow()
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "client": client,
               "input": body.model_dump(include={"notes", "fee_low_inr", "fee_high_inr", "call_prep_id"}), "title": title,
               "data": data, "markdown": build_markdown(title, client, me, k.get("consultant_title") or "", data, _ist_today(now)),
               "followups": [{"n": i + 1, "day": day, "text": follow[day], "due": None, "done": False, "done_at": None}
                             for i, day in enumerate(FOLLOW_DAYS)],
               "status": "draft", "sent_at": None, "history": [{"status": "draft", "at": now}], "at": now, "updated_at": now}
        await d.proposals.insert_one(doc)
        await events.track(d, "proposal_made", user_id=uid, props={"company": body.company[:60]})
        return public(doc)
    return await run_metered(d, user, METER, work, access=FEATURE)


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    await plans.require(db(), user, FEATURE)
    today = _ist_today()
    rows = []
    async for p in db().proposals.find({"user_id": str(user["_id"])}).sort("at", -1).limit(100):
        x = public(p, today)
        rows.append({k: x[k] for k in ("id", "client", "title", "status", "next", "sent_at", "at")} |
                    {"top_option_inr": max((o["price_inr"] for o in (p.get("data") or {}).get("options") or []), default=None)})
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    return {"items": rows, "counts": counts, "due": sum(1 for r in rows if r["next"] and r["next"]["is_due"])}


async def _own(pid: str, user: dict) -> dict:
    await plans.require(db(), user, FEATURE)
    p = await db().proposals.find_one({"_id": pid, "user_id": str(user["_id"])})
    if not p:
        raise NotFound("Proposal not found.")
    return p


@router.get("/{pid}")
async def one(pid: str, user: dict = Depends(user_dep())):
    return public(await _own(pid, user))


class FollowEdit(BaseModel):
    n: int = Field(..., ge=1, le=3)
    text: str = Field(..., min_length=5, max_length=1200)


class PatchIn(BaseModel):
    markdown: Optional[str] = Field(None, min_length=20, max_length=30000)
    title: Optional[str] = Field(None, min_length=2, max_length=140)
    status: Optional[Literal["draft", "sent", "fu1", "fu2", "fu3", "won", "lost"]] = None
    followup: Optional[FollowEdit] = None


def apply_status(p: dict, status: str, now) -> dict:
    """Returns the $set for a status change: sending fixes the follow-up dates (day 2, 5, 10 after sending, IST);
    fuN marks follow-ups 1..N done; back to draft clears them. "Still open" (won/lost back to sent) keeps the
    follow-ups already done, so the member carries on from the next one."""
    s: dict = {"status": status}
    fus = [dict(f) for f in p["followups"]]
    if status == "draft":
        s["sent_at"] = None
        for f in fus:
            f.update(due=None, done=False, done_at=None)
    elif status in ("sent", "fu1", "fu2", "fu3") or (status in ("won", "lost") and p.get("sent_at")):
        sent_at = p.get("sent_at") or now
        s["sent_at"] = sent_at
        base = _ist_today(sent_at)
        done_upto = {"sent": 0, "fu1": 1, "fu2": 2, "fu3": 3}.get(status, None)
        if status == "sent" and p.get("status") != "draft":
            done_upto = None                    # "Still open" after won/lost: keep each follow-up's done flag as it was
        for f in fus:
            f["due"] = (base + timedelta(days=f["day"])).isoformat()
            if done_upto is not None:
                f["done"] = f["n"] <= done_upto
                f["done_at"] = (f.get("done_at") or now) if f["done"] else None
    s["followups"] = fus
    return s


@router.patch("/{pid}")
async def patch(pid: str, body: PatchIn, user: dict = Depends(user_dep())):
    p = await _own(pid, user)
    now = utcnow()
    s: dict = {"updated_at": now}
    if body.markdown is not None:
        s["markdown"] = body.markdown.strip() + "\n"
    if body.title is not None:
        s["title"] = text(body.title, 140)
    if body.followup is not None:
        fus = [dict(f) for f in p["followups"]]
        for f in fus:
            if f["n"] == body.followup.n:
                f["text"] = body.followup.text.strip()
        p["followups"] = s["followups"] = fus
    push = None
    if body.status is not None and body.status != p["status"]:
        s.update(apply_status(p, body.status, now))
        push = {"history": {"status": body.status, "at": now}}
        await events.track(db(), "proposal_status", user_id=p["user_id"], props={"status": body.status})
    upd: dict = {"$set": s}
    if push:
        upd["$push"] = push
    await db().proposals.update_one({"_id": pid}, upd)
    return public(await db().proposals.find_one({"_id": pid}))


@router.delete("/{pid}")
async def remove(pid: str, user: dict = Depends(user_dep())):
    p = await _own(pid, user)
    await db().proposals.delete_one({"_id": p["_id"]})
    return {"ok": True}


async def job_followups(ctx) -> dict:
    """Daily 09:30 IST: one inbox reminder per follow-up that is due (deduped per proposal and follow-up)."""
    d, now = ctx.db, ctx.now
    today = _ist_today(now).isoformat()
    allowed = set(await plans.users_with(d, FEATURE, now))
    checked = sent = 0
    async for p in d.proposals.find({"status": {"$in": list(OPEN)}, "sent_at": {"$ne": None}}):
        checked += 1
        if p["user_id"] not in allowed:
            continue
        nf = next_followup(p)
        if not nf or not nf.get("due") or nf["due"] > today:
            continue
        who = p["client"].get("person") or p["client"]["company"]
        r = await notify.alert(d, p["user_id"], "proposal", f"Follow up with {who} today",
                               f"It's day {nf['day']} since you sent the proposal to {p['client']['company']}. "
                               "Your follow-up message is ready to copy. You send it; then mark it done.",
                               link=f"/app/proposals/{p['_id']}", dedupe=f"proposal:{p['_id']}:{nf['n']}:{nf['due']}")
        sent += 1 if r else 0
    return {"checked": checked, "alerts": sent}
