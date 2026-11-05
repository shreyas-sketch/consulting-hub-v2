"""Starting Point: Niche Snapshot (EDE: Experience, Demand, Enjoyment) and Goal Map.

The snapshot follows the current hub's "Define Your Niche" GPT (backend/gpts/prompts/define-your-niche.md):
each option comes with a specific consultant title, a value proposition in Akshat's format
("I help [audience] achieve [result] by helping them solve [problem]") and an INR fee range, so the chosen option
is a complete FINALIZED NICHE package that the L1 / L2 tools can start from (see `blueprint_text`).

snapshots {_id, user_id, input: {experiences, enjoy, industry, years}, options: [...], chosen, at}
goals     {_id: user_id, monthly_goal_inr, fee_inr, close_rate_pct, calls_per_lead, start_month, updated_at}

Niche Snapshot: the member lists up to 5 things they're experienced in and ticks the ones they enjoy.
AI suggests 3 niche options, each scored 1–10 on Experience, Demand and Enjoyment (total /30).
Goal Map is plain arithmetic, shown with its assumptions so the member can change them.
"""
from __future__ import annotations

import math
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

import llm
from core.deps import user_dep
from core.errors import NotFound
from growth import events
from growth.clock import utcnow
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
)

router = APIRouter(prefix="/start", tags=["starting-point"])
WEBINAR_QUEUE_WAIT = 45          # seconds a snapshot may wait for an AI slot when the whole webinar runs it at once

SYSTEM = (
    "You help experienced Indian professionals, mostly still in jobs with 10-25 years of experience, find a consulting "
    "niche using Akshat Dani's EDE framework. E = Experience: every skill, domain and problem they have solved, not "
    "their title. D = Demand: what Indian businesses are actively paying to solve today, not what sounds good. "
    "E = Enjoyment: what they truly enjoy, because they will do this for years. The niche sits where all three meet. "
    "A good niche is narrow: one kind of client, one painful problem, one clear result. Prioritise market demand and "
    "credibility over passion alone. Push for specificity: never a vague consultant title (say 'B2B Sales Growth "
    "Consultant for engineering MSMEs', not 'Business Consultant'). Fees in Indian rupees only, realistic for India: "
    "beginner consultants typically ₹10,000-₹50,000 per client, established ₹50,000-₹2,00,000, specialists "
    "₹2,00,000-₹10,00,000+; adjust for the niche and audience. Use plain English. Never promise income. " + NO_VENDOR
)
INCOME_NOTE = "Actual income depends on expertise, positioning, proof of results, sales ability, and client acquisition effectiveness."


class SnapshotIn(BaseModel):
    experiences: list[str] = Field(..., min_length=1, max_length=5)
    enjoy: list[int] = Field(default_factory=list, max_length=5)          # indexes into experiences
    industry: str = Field("", max_length=80)
    years: int = Field(15, ge=0, le=50)
    proof: str = Field("", max_length=300)                                 # achievements that give credibility

    @field_validator("experiences")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        out = [" ".join(x.split())[:80] for x in v if x and x.strip()]
        if not out:
            raise ValueError("Add at least one thing you're experienced in.")
        return out


def _fake(body: SnapshotIn) -> dict:
    ex = body.experiences
    ind = body.industry or "mid-size businesses"
    enjoyed = [ex[i] for i in body.enjoy if 0 <= i < len(ex)] or ex[:1]
    picks = [enjoyed[0], ex[min(1, len(ex) - 1)], ex[-1]]
    who = [f"Owner-led {ind} firms with ₹10–100 crore revenue", f"Growing {ind} companies opening new locations",
           f"Family-run {ind} businesses moving to the next generation"]
    prob = ["profit falling even as sales grow", "teams that can't keep up with growth", "no clear system for decisions"]
    out = []
    for i, p in enumerate(picks):
        e = 9 - i
        d = [8, 7, 6][i]
        j = 9 if p in enjoyed else 5
        out.append({"niche": f"{p} consulting for {ind}", "who": who[i], "problem": prob[i],
                    "result": f"Fix {prob[i]} within 90 days", "title": f"{p} Consultant for {ind.title()}",
                    "value_prop": f"I help {who[i].lower()} achieve steady profit growth by helping them solve {prob[i]}.",
                    "fee_low": [25000, 20000, 15000][i], "fee_high": [75000, 60000, 50000][i],
                    "experience": e, "demand": d, "enjoyment": j,
                    "why": f"Uses your {body.years} years in {p.lower()}; businesses pay to fix {prob[i]}."})
    return {"options": out, "note": "Test mode answer. Live mode writes these from your inputs."}


_SLOT = re.compile(r"\[[^\]]{2,40}\]")      # an unfilled "[target audience]" copied from the prompt's format


def _repair(row: dict) -> None:
    """Every later tool (website, outreach, network, decks) reads the chosen option, so an empty title or a value
    proposition with the prompt's [slots] still in it would spread as placeholders. Rebuild them from the parts."""
    for k in ("who", "problem", "result"):
        if _SLOT.search(row[k]):
            row[k] = ""
    if not row["title"] or _SLOT.search(row["title"]):
        row["title"] = f"{row['niche']} Consultant" if "consult" not in row["niche"].lower() else row["niche"]
    if not row["value_prop"] or _SLOT.search(row["value_prop"]):
        if row["who"] and row["result"] and row["problem"]:
            res = row["result"][0].lower() + row["result"][1:]
            prob = row["problem"][0].lower() + row["problem"][1:]
            row["value_prop"] = f"I help {row['who']} {res.rstrip('.')} by helping them solve {prob.rstrip('.')}."
        else:
            row["value_prop"] = ""


def _clean_options(raw: dict, body: SnapshotIn) -> list[dict]:
    opts = []
    for o in as_list(as_dict(raw).get("options"))[:3]:
        if not isinstance(o, dict) or not text(o.get("niche"), 120):
            continue
        lo, hi = clamp_int(o.get("fee_low"), 5000, 5_000_000, 20000), clamp_int(o.get("fee_high"), 5000, 10_000_000, 60000)
        row = {"niche": text(o.get("niche"), 120), "who": text(o.get("who"), 160), "problem": text(o.get("problem"), 160),
               "result": text(o.get("result"), 160), "why": text(o.get("why"), 300),
               "title": text(o.get("title"), 120), "value_prop": text(o.get("value_prop"), 300),
               "fee_low": min(lo, hi), "fee_high": max(lo, hi),
               "experience": clamp_int(o.get("experience"), 1, 10, 5), "demand": clamp_int(o.get("demand"), 1, 10, 5),
               "enjoyment": clamp_int(o.get("enjoyment"), 1, 10, 5)}
        _repair(row)
        row["total"] = row["experience"] + row["demand"] + row["enjoyment"]
        row["yearly_low"], row["yearly_high"] = row["fee_low"] * 4 * 12, row["fee_high"] * 4 * 12   # 4 clients a month
        opts.append(strip_providers(row))
    if len(opts) < 3:
        raise llm.LLMError("snapshot: fewer than 3 options")
    return sorted(opts, key=lambda r: -r["total"])


def _prompt(body: SnapshotIn) -> str:
    lines = [f"{i + 1}. {x}{' (enjoys this)' if i in body.enjoy else ''}" for i, x in enumerate(body.experiences)]
    return (f"Years of experience: {body.years}\nIndustry they know best: {body.industry or 'not given'}\n"
            "Things they are experienced in:\n" + "\n".join(lines) + "\n"
            f"Achievements that give them credibility: {body.proof or 'not given'}\n\n"
            "Suggest exactly 3 different niche options. For each give: niche (short name), who (the client: kind of "
            "business and size), problem (the painful problem you solve), result (what the client gets, with a time "
            "frame), title (a specific consultant title), value_prop (exactly: I help [target audience] achieve "
            "[desired result] by helping them solve [problem]), fee_low and fee_high (a realistic beginner fee range "
            "per client in rupees, whole numbers), experience (1-10, how well their experience fits), demand (1-10, how "
            "much Indian businesses pay for this today), enjoyment (1-10, high only if it builds on what they enjoy), "
            "why (one sentence).\n"
            'JSON: {"options": [{"niche": "", "who": "", "problem": "", "result": "", "title": "", "value_prop": "", '
            '"fee_low": 0, "fee_high": 0, "experience": 0, "demand": 0, "enjoyment": 0, "why": ""}], '
            '"note": "one sentence of advice on choosing"}')


def blueprint_text(o: dict, name: Optional[str] = None) -> str:
    """The chosen option as a FINALIZED NICHE package, in the shape the current hub's GPTs expect as a first message."""
    return (f"FINALIZED NICHE\n- Who I help: {o.get('who')}\n- What problem I solve: {o.get('problem')}\n"
            f"- What result I create: {o.get('result')}\n\nCONSULTANT IDENTITY\n{o.get('title') or o.get('niche')}\n\n"
            f"VALUE PROPOSITION\n{o.get('value_prop')}\n\nEARNING POTENTIAL\n"
            f"- Fee range: {inr(o.get('fee_low', 0))} – {inr(o.get('fee_high', 0))} per client\n"
            f"- 4 clients a month could represent {inr(o.get('yearly_low', 0))} – {inr(o.get('yearly_high', 0))} a year\n"
            f"- {INCOME_NOTE}" + (f"\n\nConsultant: {name}" if name else ""))


def _public(doc: dict) -> dict:
    return {"id": doc["_id"], "input": doc["input"], "options": doc["options"], "chosen": doc.get("chosen"),
            "note": doc.get("note"), "income_note": INCOME_NOTE, "at": iso(doc["at"])}


@router.post("/snapshot")
async def snapshot(body: SnapshotIn, user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    body.enjoy = sorted({i for i in body.enjoy if 0 <= i < len(body.experiences)})

    async def work(plan: str):
        raw = as_dict(await llm.complete_json(task="niche_snapshot", system=SYSTEM, prompt=_prompt(body),
                                              fake=lambda: _fake(body), model="fast", max_tokens=3000,
                                              queue_wait=WEBINAR_QUEUE_WAIT))
        opts = _clean_options(raw, body)
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "input": body.model_dump(), "options": opts, "chosen": 0,
               "note": strip_providers(text(raw.get("note"), 300)), "at": utcnow()}
        await db().snapshots.insert_one(doc)
        await events.track(db(), "snapshot_run", user_id=uid, props={"top_niche": opts[0]["niche"]})
        return _public(doc)
    return await run_metered(db(), user, "start", work)


class ChooseIn(BaseModel):
    index: int = Field(..., ge=0, le=2)


@router.post("/snapshot/{snap_id}/choose")
async def choose(snap_id: str, body: ChooseIn, user: dict = Depends(user_dep())):
    res = await db().snapshots.update_one({"_id": snap_id, "user_id": str(user["_id"])}, {"$set": {"chosen": body.index}})
    if not res.matched_count:
        raise NotFound("Snapshot not found.")
    return _public(await db().snapshots.find_one({"_id": snap_id}))


# ------------------------------------------------------------------ goal map ----
class GoalIn(BaseModel):
    monthly_goal_inr: int = Field(..., ge=10000, le=10_000_000)
    fee_inr: int = Field(..., ge=5000, le=10_000_000)
    close_rate_pct: int = Field(25, ge=5, le=80)          # assumption: 1 in 4 discovery calls becomes a client
    calls_per_lead: int = Field(3, ge=1, le=10)           # assumption: 3 conversations for every discovery call
    months: int = Field(6, ge=1, le=24)


def goal_map(g: dict) -> dict:
    clients = max(1, math.ceil(g["monthly_goal_inr"] / g["fee_inr"]))
    calls = math.ceil(clients * 100 / g["close_rate_pct"])
    convos = calls * g["calls_per_lead"]
    return {"clients_per_month": clients, "discovery_calls_per_month": calls, "conversations_per_month": convos,
            "conversations_per_week": math.ceil(convos / 4.3), "monthly_goal_inr": g["monthly_goal_inr"],
            "fee_inr": g["fee_inr"], "months": g["months"],
            "close_rate_pct": g["close_rate_pct"], "calls_per_lead": g["calls_per_lead"],     # the saved assumptions
            "assumptions": [f"{g['close_rate_pct']}% of discovery calls become clients",
                            f"{g['calls_per_lead']} conversations for every discovery call",
                            "Fee is per client per month"],
            "label": "Estimate from your numbers, not a promise of income."}


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    snap = await db().snapshots.find_one({"user_id": uid}, sort=[("at", -1)])
    goal = await db().goals.find_one({"_id": uid})
    return {"snapshot": _public(snap) if snap else None,
            "goal": {**goal_map(goal), "updated_at": iso(goal.get("updated_at"))} if goal else None}


@router.put("/goal")
async def save_goal(body: GoalIn, user: dict = Depends(user_dep())):
    uid = str(user["_id"])

    async def work(plan: str):
        g = body.model_dump()
        await db().goals.replace_one({"_id": uid}, {"_id": uid, **g, "updated_at": utcnow()}, upsert=True)
        await events.track(db(), "goal_saved", user_id=uid, props={"monthly_goal_inr": body.monthly_goal_inr})
        return goal_map(g)
    return await run_metered(db(), user, "goal", work, access="start")


@router.post("/goal/preview")
async def preview_goal(body: GoalIn, user: Optional[dict] = Depends(user_dep())):
    """Live numbers while typing. Free, not metered, nothing saved."""
    return goal_map(body.model_dump())
