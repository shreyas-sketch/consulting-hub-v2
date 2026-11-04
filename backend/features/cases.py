"""Cases: the live case on the webinar, the practice bank, and (stage 2) the weekly case from real news.

cases        {_id, title, company, industry, city, situation, facts, question, framework_hint, model_answer,
              kind practice|weekly, week?, source?: {title, url}, active}
case_answers {_id, user_id, case_id, answer, scores: {criterion: 0-10}, overall, good, improve, summary, at}

Free accounts: the live case only, once. Paid: every case, answers metered per month.
The model answer is shown only after the member has sent an answer to that case.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import appsettings
import llm
import plans
from core.deps import user_dep
from growth import events
from growth.clock import utcnow
from state import db
from util import iso

from .case_bank import CASES, CRITERIA, model_answer_text
from .common import clamp_int, run_metered, text, text_list

router = APIRouter(prefix="/cases", tags=["cases"])

SYSTEM = (
    "You are the case coach for Akshat Dani's 4-3-2-1 Consulting Action Program. Members are senior Indian "
    "professionals (mostly 40+, 15-35 years' experience) becoming consultants. They answer a business case using the "
    "Strategic Thinking Framework: Phase 1 Define the Problem (Step 1 Understand Scope: region, product, channel, time; "
    "Step 2 Identify Objective: from, to, in by when, definition of success and failure), Phase 2 Craft the Strategy "
    "(Step 3 Identify Framework; Step 4 Generate Options; Step 5 Prioritize: business benefit x ease, do first), "
    "Phase 3 Execute (Step 6 Implementation Charter: owner, stakeholders, incentives, capabilities, a leading metric "
    "weekly and a lagging metric monthly). Score 4 criteria, each 0-10: scope (did they turn the client's vague words "
    "into one precise problem: where, what, since when), objective (from, to, by when, with numbers), strategy (a fitting "
    "framework, real options, and a clear 'do first'), execution (who owns it, the first action, what to measure weekly "
    "and monthly). Be fair and encouraging but honest: a vague answer scores low, and an answer can score well without "
    "naming the steps if the thinking is there. Write in plain English to the member as 'you'. No mention of courses "
    "or upsells."
)


async def ensure_seed(d) -> int:
    """Practice cases live in code: their text is refreshed on every start; `active` and `created_at` are kept."""
    n = 0
    for c in CASES:
        body = {k: v for k, v in c.items() if k != "_id"}
        res = await d.cases.update_one({"_id": c["_id"]}, {"$set": {**body, "kind": "practice"},
                                                           "$setOnInsert": {"active": True, "created_at": utcnow()}},
                                       upsert=True)
        n += 1 if res.upserted_id else 0
    return n


async def get_case(d, case_id: str) -> Optional[dict]:
    return await d.cases.find_one({"_id": case_id, "active": {"$ne": False}})


def _card(c: dict, *, live: bool, locked: bool) -> dict:
    return {"id": c["_id"], "title": c["title"], "company": c["company"], "industry": c["industry"],
            "city": c.get("city"), "kind": c.get("kind", "practice"), "week": c.get("week"), "live": live,
            "locked": locked, "source": c.get("source")}


def _full(c: dict, answered: bool) -> dict:
    out = {**_card(c, live=False, locked=False), "situation": c["situation"], "facts": c.get("facts", []),
           "question": c["question"], "framework_hint": c.get("framework_hint"),
           "criteria": [{"key": k, "label": lbl} for k, lbl in CRITERIA]}
    out["model_answer"] = c["model_answer"] if answered else None
    return out


@router.get("")
async def listing(user: dict = Depends(user_dep())):
    d = db()
    plan = (await plans.effective_plan(d, user))["plan"]
    live_id = (await appsettings.get(d))["live_case_id"]
    done = {a["case_id"]: a async for a in d.case_answers.find({"user_id": str(user["_id"])},
                                                               {"case_id": 1, "overall": 1}).sort("at", 1)}
    items = []
    async for c in d.cases.find({"active": {"$ne": False}}).sort([("week", -1), ("created_at", 1)]):
        live = c["_id"] == live_id
        row = _card(c, live=live, locked=plan == "free" and not live)
        row["my_score"] = done[c["_id"]]["overall"] if c["_id"] in done else None
        items.append(row)
    items.sort(key=lambda r: (not r["live"], r["kind"] != "weekly"))
    return {"plan": plan, "items": items}


@router.get("/{case_id}")
async def one(case_id: str, user: dict = Depends(user_dep())):
    d = db()
    c = await get_case(d, case_id)
    if not c:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Case not found."})
    plan = (await plans.effective_plan(d, user))["plan"]
    live_id = (await appsettings.get(d))["live_case_id"]
    if plan == "free" and case_id != live_id:
        raise plans.locked_error("case", "member")
    mine = [_answer(a) async for a in d.case_answers.find({"user_id": str(user["_id"]), "case_id": case_id}).sort("at", -1)]
    return {"case": _full(c, bool(mine)) | {"live": case_id == live_id}, "answers": mine}


class AnswerIn(BaseModel):
    answer: str = Field(..., min_length=40, max_length=4000)


def _fake_score(c: dict, answer: str) -> dict:
    a = answer.lower()
    words = len(a.split())
    base = 3 + min(4, words // 40)
    hit = lambda *ks: any(k in a for k in ks)  # noqa: E731
    s = {"scope": base + (2 if hit("real problem", "scope", "since", "stores", "because", "root") else 0),
         "objective": base + (2 if hit("from", " to ", "by ", "days", "months", "target", "%") else 0),
         "strategy": base + (2 if hit("framework", "option", "first", "priorit", "then") else 0),
         "execution": base + (2 if hit("owner", "measure", "track", "weekly", "every week", "metric") else 0)}
    return {"scores": {k: min(10, v) for k, v in s.items()},
            "good": ["You looked past the client's first words.", "Your options are in a sensible order."],
            "improve": ["Write the objective as from → to → by when, with numbers.", "Name who owns it and one number to track every week."],
            "summary": "Test mode score. Live mode reads your answer and scores it properly."}


def _prompt(c: dict, answer: str) -> str:
    facts = "\n".join(f"- {f}" for f in c.get("facts", []))
    return (f"CASE: {c['title']} ({c['company']}, {c['industry']})\n{c['situation']}\nFacts:\n{facts}\n"
            f"Question: {c['question']}\n\nREFERENCE ANSWER (for your judgement only, do not quote it):\n"
            f"{model_answer_text(c['model_answer'])}\n\nMEMBER'S ANSWER:\n{answer}\n\n"
            'JSON: {"scores": {"scope": 0, "objective": 0, "strategy": 0, "execution": 0}, '
            '"good": ["two short things they did well"], "improve": ["two short, specific things to improve"], '
            '"summary": "one or two sentences"}')


def _answer(a: dict) -> dict:
    return {"id": a["_id"], "case_id": a["case_id"], "answer": a["answer"], "scores": a["scores"],
            "overall": a["overall"], "good": a.get("good", []), "improve": a.get("improve", []),
            "summary": a.get("summary"), "at": iso(a["at"])}


@router.post("/{case_id}/answer")
async def answer(case_id: str, body: AnswerIn, user: dict = Depends(user_dep())):
    d = db()
    c = await get_case(d, case_id)
    if not c:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Case not found."})
    uid = str(user["_id"])
    live_id = (await appsettings.get(d))["live_case_id"]
    if (await plans.effective_plan(d, user))["plan"] == "free" and case_id != live_id:
        raise plans.locked_error("case", "member")

    async def work(plan: str):
        raw = await llm.complete_json(task="case_score", system=SYSTEM, prompt=_prompt(c, body.answer),
                                      fake=lambda: _fake_score(c, body.answer), model="fast", max_tokens=700)
        sc = raw.get("scores") or {}
        if not isinstance(sc, dict) or not all(k in sc for k, _ in CRITERIA):
            raise llm.LLMError("case_score: missing scores")
        scores = {k: clamp_int(sc.get(k), 0, 10, 0) for k, _ in CRITERIA}
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "case_id": case_id, "answer": body.answer.strip(),
               "scores": scores, "overall": round(sum(scores.values()) / len(scores), 1),
               "good": text_list(raw.get("good"), 3, 200), "improve": text_list(raw.get("improve"), 3, 200),
               "summary": text(raw.get("summary"), 400), "at": utcnow()}
        await d.case_answers.insert_one(doc)
        await events.track(d, "case_answered", user_id=uid,
                           props={"case_id": case_id, "score": doc["overall"], "live": case_id == live_id})
        return {"answer": _answer(doc), "model_answer": c["model_answer"],
                "criteria": [{"key": k, "label": lbl} for k, lbl in CRITERIA]}
    return await run_metered(d, user, "case", work)
