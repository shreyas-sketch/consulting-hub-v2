"""Discovery Call Prep: everything for a 30-minute first call with a possible client, on one printable page.

call_preps {_id, user_id, input: {company, person, role, how_met, known, search}, news: [{title, url, source,
            published, why}], agenda: [{minutes, item}], opening, questions: [{step, question, why}],
            problems: [{problem, why}], objections: [{objection, answer}], avoid: [str], next_step,
            live_news, test, at}

Questions follow the six steps of Akshat's Strategic Thinking Framework (backend/gpts/prompts/
strategy-thinking-framework.md); Step 1 covers scope the way the Scope Clarifier does (region, product, channel,
time) and Step 2 digs for the real objective the way the Client Objective Decoder does (financial, process and
future-readiness goals; "what does success look like 6 months from now?"). Optional news: links come only from
the search results, picked by number.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import indexes
import llm
import plans
from core.deps import user_dep
from growth import events
from growth.clock import utcnow
from research import search
from state import db
from util import iso

from .common import clamp_int, run_metered, text, text_list
from .knowledge import knowledge, system_block
from .network import NO_VENDOR

router = APIRouter(prefix="/call-prep", tags=["discovery-call-prep"])

FEATURE = METER = "call_prep"
STEPS = {1: "Understand Scope", 2: "Identify Objective", 3: "Identify Framework", 4: "Generate Options",
         5: "Prioritize Options", 6: "Implementation Charter"}

events.register("call_prep_made", "Discovery Call Prep made (props.company, news)")
indexes.register("call_preps", [("user_id", 1), ("at", -1)])

SYSTEM = (
    "You prepare an experienced Indian professional, new to consulting, for a 30-minute discovery call with a "
    "possible first client. The goal of the call is to diagnose, not to sell: understand the real problem and its "
    "cost, agree what success looks like, and earn the next step. Use Akshat Dani's Strategic Thinking Framework: "
    "Step 1 Understand Scope (region, product, channel, time: turn vague words into one precise problem); Step 2 "
    "Identify Objective (from, to, by when; the real objective behind the stated one: financial, process or "
    "future-readiness; always ask what success looks like 6 months from now); Step 3 Identify Framework (the lens "
    "to analyse it); Step 4 Generate Options (what they have tried, what others do); Step 5 Prioritize Options "
    "(business benefit x ease); Step 6 Implementation Charter (owner, stakeholders, who decides, budget, how "
    "progress is measured). Questions are open, conversational and non-threatening, one idea each. Use only what you "
    "are told and the numbered news items; if unsure of a fact, don't state it. Plain English, short sentences. "
    "No mention of courses or programs. " + NO_VENDOR
)


class PrepIn(BaseModel):
    company: str = Field(..., min_length=2, max_length=120)
    person: str = Field("", max_length=120)
    role: str = Field("", max_length=120)
    how_met: str = Field("", max_length=300)
    known: str = Field("", max_length=2000)
    search: bool = False


def _fake(body: PrepIn, results: list[dict]) -> dict:
    co, who = body.company.strip(), (body.person or "they").split()[0]
    qs = [(1, f"When you say things aren't working, which part of {co} do you mean: which product, region or channel?"),
          (1, "Since when has this been happening?"),
          (2, "If we sat here six months from now and this was solved, what would be different?"),
          (2, "What number would tell you it's fixed: from where to where, by when?"),
          (3, "How do you look at this today: which reports or numbers do you check?"),
          (4, "What have you already tried, and what happened?"),
          (5, "If you could fix only one thing this quarter, what would it be?"),
          (6, "Who else would be involved in a decision like this?"),
          (6, "How would you want to track progress week to week?")]
    return {"agenda": [{"minutes": 3, "item": "Thank them, agree the time and what you'll cover"},
                       {"minutes": 12, "item": "Understand the situation: scope and what they've tried"},
                       {"minutes": 8, "item": "What success looks like, in numbers"},
                       {"minutes": 4, "item": "Play back what you heard"},
                       {"minutes": 3, "item": "Agree the next step"}],
            "opening": f"Thanks for making time{', ' + who if body.person else ''}. I'd like to understand what's going on at {co} before I suggest anything. Is 30 minutes still okay?",
            "questions": [{"step": s, "question": q, "why": "Test mode: live mode explains why each question matters."} for s, q in qs],
            "problems": [{"problem": "Growth is stretching the team", "why": "Common when a company of this size expands."},
                         {"problem": "Decisions sit with the owner", "why": "Typical of owner-led firms."},
                         {"problem": "Margins are slipping", "why": "Costs often rise faster than prices."}],
            "objections": [{"objection": "We've tried consultants before.", "answer": "Ask what didn't work last time, and how they'd want this to be different."},
                           {"objection": "What will it cost?", "answer": "Say it depends on the scope you agree, and offer a short written proposal with options."},
                           {"objection": "Let me think about it.", "answer": "Agree a date to speak again and ask what they need to decide."}],
            "avoid": ["Don't pitch your services in the first 20 minutes.", "Don't give the solution on the call.",
                      "Don't criticise their team or past decisions."],
            "next_step": "Offer to send a one-page summary of what you heard and two or three ways forward, and fix a 20-minute follow-up.",
            "news": [{"i": i + 1, "why": "Worth asking about early in the call."} for i in range(min(2, len(results)))]}


def _prompt(body: PrepIn, k: dict, results: list[dict]) -> str:
    news = "\n".join(f"[{i + 1}] {r['title']} ({r['source']}, {r['published'] or 'date unknown'}): {r['snippet'][:350]}"
                     for i, r in enumerate(results)) or "No news searched."
    return (f"{system_block(k) or 'Niche not chosen yet.'}\nConsultant title: {k.get('consultant_title') or 'not set'}\n\n"
            f"CALL WITH:\nCompany: {body.company}\nPerson: {body.person or 'not given'}\nRole: {body.role or 'not given'}\n"
            f"How they met: {body.how_met or 'not given'}\nWhat the consultant knows: {body.known or 'nothing more'}\n\n"
            f"NEWS ITEMS:\n{news}\n\n"
            "Write: agenda (4-6 items with minutes adding up to 30), opening (one natural opening line), questions "
            "(9-12, each with step 1-6 from the framework and why it matters; at least one per step, most in steps 1-2), "
            "problems (3 likely problems, each with why you think so), objections (3 likely objections, each with a calm "
            "answer), avoid (3-4 things not to say or do), next_step (the one next step to propose at the end), "
            "news (up to 2 of the numbered items worth raising, by number, with why).\n"
            'JSON: {"agenda": [{"minutes": 5, "item": ""}], "opening": "", "questions": [{"step": 1, "question": "", "why": ""}], '
            '"problems": [{"problem": "", "why": ""}], "objections": [{"objection": "", "answer": ""}], "avoid": [""], '
            '"next_step": "", "news": [{"i": 1, "why": ""}]}')


def public(p: dict) -> dict:
    return {k: p.get(k) for k in ("input", "news", "agenda", "opening", "questions", "problems", "objections", "avoid",
                                  "next_step", "live_news", "test")} | {"id": p["_id"], "at": iso(p["at"]), "steps": STEPS}


@router.post("")
async def make(body: PrepIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])

    async def work(plan: str):
        results = await search.news(f"{body.company} India", max_results=5) if body.search else []
        k = await knowledge(d, user)
        raw = await llm.complete_json(task="call_prep", system=SYSTEM, prompt=_prompt(body, k, results),
                                      fake=lambda: _fake(body, results), model="strong", max_tokens=2200)
        agenda = [{"minutes": clamp_int(a.get("minutes"), 1, 30, 5), "item": text(a.get("item"), 160)}
                  for a in (raw.get("agenda") or [])[:6] if isinstance(a, dict) and text(a.get("item"), 160)]
        questions = []
        for q in (raw.get("questions") or [])[:12]:
            if isinstance(q, dict) and text(q.get("question"), 240):
                questions.append({"step": clamp_int(q.get("step"), 1, 6, 1), "question": text(q.get("question"), 240),
                                  "why": text(q.get("why"), 240)})
        questions.sort(key=lambda q: q["step"])
        problems = [{"problem": text(x.get("problem"), 160), "why": text(x.get("why"), 240)}
                    for x in (raw.get("problems") or [])[:4] if isinstance(x, dict) and text(x.get("problem"), 160)]
        objections = [{"objection": text(x.get("objection"), 200), "answer": text(x.get("answer"), 400)}
                      for x in (raw.get("objections") or [])[:4]
                      if isinstance(x, dict) and text(x.get("objection"), 200) and text(x.get("answer"), 400)]
        opening, next_step = text(raw.get("opening"), 400), text(raw.get("next_step"), 400)
        if len(agenda) < 3 or len(questions) < 6 or not opening or not next_step:
            raise llm.LLMError("call_prep: incomplete")
        news = []
        for n in (raw.get("news") or [])[:8]:
            if len(news) >= 2:
                break
            try:
                i = int(n.get("i"))
                r = results[i - 1] if i >= 1 else None
            except (TypeError, ValueError, IndexError, AttributeError):
                r = None
            if r and not any(x["url"] == r["url"] for x in news):
                news.append({"title": r["title"], "url": r["url"], "source": r["source"], "published": r["published"],
                             "why": text(n.get("why"), 240)})
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "input": body.model_dump(), "news": news, "agenda": agenda,
               "opening": opening, "questions": questions, "problems": problems, "objections": objections,
               "avoid": text_list(raw.get("avoid"), 4, 200), "next_step": next_step, "live_news": bool(results),
               "test": any(r.get("test") for r in results), "at": utcnow()}
        await d.call_preps.insert_one(doc)
        await events.track(d, "call_prep_made", user_id=uid, props={"company": body.company[:60], "news": len(news)})
        return public(doc)
    return await run_metered(d, user, METER, work, access=FEATURE)


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    await plans.require(db(), user, FEATURE)
    rows = [{"id": p["_id"], "company": p["input"]["company"], "person": p["input"].get("person") or "", "at": iso(p["at"])}
            async for p in db().call_preps.find({"user_id": str(user["_id"])}, {"input": 1, "at": 1}).sort("at", -1).limit(50)]
    return {"items": rows}


async def _own(pid: str, user: dict) -> dict:
    await plans.require(db(), user, FEATURE)
    p = await db().call_preps.find_one({"_id": pid, "user_id": str(user["_id"])})
    if not p:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Call prep not found."})
    return p


@router.get("/{pid}")
async def one(pid: str, user: dict = Depends(user_dep())):
    return public(await _own(pid, user))


@router.delete("/{pid}")
async def remove(pid: str, user: dict = Depends(user_dep())):
    p = await _own(pid, user)
    await db().call_preps.delete_one({"_id": p["_id"]})
    return {"ok": True}
