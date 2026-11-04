"""Portfolio Project: a practice client from the member's niche → their approach → feedback, a case study and a video script.

Step 1 "mock client meeting": the AI invents a realistic client from the member's niche, the way Part 1 of the current
hub's Strategy Thinking Framework GPT does (backend/gpts/prompts/strategy-thinking-framework.md): company type, size,
Indian city, the decision-maker's first name and title, and what they say in their own vague, emotional words.
Step 2: the member writes their approach with the six steps (scope, objective, framework and options, do first,
owner and metrics). Step 3: the AI scores it 0-10 on scope / objective / strategy / execution (same criteria as
features/cases.py), writes a polished case study (the six steps; the outcome is labelled "projected", because the client
is fictional) and a 60-90 second video script the member records on their own phone. The video is never uploaded.

portfolio_projects {_id, user_id, status brief|answered|done, niche, brief: {...}, answer?: {...},
                    review?: {scores, overall, good, improve, summary, case_study, video_script, script_seconds},
                    at, answered_at?, done_at?}

Metered (`portfolio`) when a project starts; the answer and the review are part of that project.
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
from state import db
from util import iso

from .case_bank import CRITERIA
from .common import busy_error, clamp_int, run_metered, text, text_list
from .knowledge import knowledge, system_block

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

events.register("portfolio_started", "Portfolio Project started (props.niche)")
events.register("portfolio_done", "Portfolio Project reviewed: case study + video script (props.score)")
indexes.register("portfolio_projects", [("user_id", 1), ("at", -1)])

STEPS = ["Understand scope", "Identify objective", "Identify framework", "Generate options", "Prioritise options",
         "Implementation charter"]
OUTCOME_LABEL = "Projected outcome: an estimate for a practice client, not a real result."
PRACTICE_NOTE = ("This is a practice project with a fictional client. Show it as a sample of how you work, "
                 "never as a real client result.")

FRAMEWORK = (
    "The Strategic Thinking Framework: Phase 1 Define the Problem (Step 1 Understand Scope: region, product, channel, "
    "time; Step 2 Identify Objective: from, to, in by when, definition of success and failure), Phase 2 Craft the "
    "Strategy (Step 3 Identify Framework: a structured lens that fits the problem; Step 4 Generate Options: same "
    "industry, adjacent industry, similar geography, customer research, out-of-the-box; Step 5 Prioritise: business "
    "benefit x ease, do first), Phase 3 Execute (Step 6 Implementation Charter: owner, stakeholders, incentives, "
    "capabilities, a leading metric weekly and a lagging metric monthly)."
)
SYSTEM_BRIEF = (
    "You run a mock client meeting for a member of Akshat Dani's 4-3-2-1 Consulting Action Program. Members are senior "
    "Indian professionals (mostly 40+, 15-35 years' experience) becoming consultants. Invent ONE fictional client that "
    "feels completely real for the member's niche: a typical company type and size (revenue or employees), an Indian "
    "city, years in business, the decision-maker's first name and title, how they found the consultant (one line), and "
    "what the decision-maker says in their own words: 3-5 sentences, vague and emotional, the way clients really talk, "
    "with one or two telling details but no diagnosis. Never use a real company name. Indian context (₹, lakh, crore). "
    "Plain English. Never mention or describe the AI or who makes it."
)
SYSTEM_REVIEW = (
    "You are the case coach for Akshat Dani's 4-3-2-1 Consulting Action Program. The member answered a practice client "
    f"using {FRAMEWORK} Score 4 criteria, each 0-10: scope (did they turn the client's vague words into one precise "
    "problem: where, what, since when), objective (from, to, by when, with numbers), strategy (a fitting framework, "
    "real options, a clear 'do first'), execution (who owns it, the first action, what to measure weekly and monthly). "
    "Be fair and encouraging but honest: a vague answer scores low. Then write a polished case study of this practice "
    "engagement in the member's voice, built on THEIR approach (sharpen it, fill small gaps sensibly, don't replace it), "
    "and a 60-90 second video script (about 150-220 words) the member will record on their phone to show how they "
    "think. The client is fictional: the expected outcome is a projection, so word it as 'we expect' or 'the plan aims "
    "to', never as an achieved result, and never present it as a real client. Use typical industry ranges, never cited "
    "statistics. Plain, spoken English to the member as 'you' in feedback; first person in the case study and script. "
    "No buzzwords, no hype, no emojis. Never promise income. Never mention or describe the AI or who makes it."
)


class AnswerIn(BaseModel):
    scope: str = Field(..., min_length=10, max_length=1500)
    objective: str = Field(..., min_length=10, max_length=1500)
    framework_options: str = Field(..., min_length=10, max_length=2500)
    do_first: str = Field(..., min_length=10, max_length=1500)
    owner_metrics: str = Field(..., min_length=10, max_length=1500)


# ------------------------------------------------------------------ step 1: the brief ----
def _fake_brief(k: dict) -> dict:
    ind = k.get("target_industry") or "manufacturing"
    return {"company": f"Shreeji {ind.title()} Pvt Ltd", "company_type": f"Family-owned {ind} business",
            "size": "₹80 crore revenue, 240 people", "city": "Pune", "years": 22,
            "decision_maker_name": "Rakesh", "decision_maker_title": "Managing Director",
            "how_found": "A friend shared your LinkedIn post about margins.",
            "client_words": ("Sales are up every year, but somehow there's never enough money at the end of the month. "
                             "My managers keep asking for more people. Last quarter we even missed two big orders. "
                             "I'm tired of fighting fires every day."),
            "note": "Test mode client. Live mode invents one from your niche."}


def _brief_prompt(k: dict) -> str:
    kb = system_block(k) or "Niche not chosen yet: pick a common problem for mid-size Indian businesses."
    return (f"{kb}\n\n" + (f"FINALIZED NICHE PACKAGE:\n{k['blueprint']}\n\n" if k.get("blueprint") else "")
            + 'JSON: {"company": "invented name", "company_type": "", "size": "", "city": "", "years": 0, '
            '"decision_maker_name": "first name", "decision_maker_title": "", "how_found": "", '
            '"client_words": "3-5 sentences in the client\'s own words"}')


def _clean_brief(raw: dict) -> dict:
    b = {"company": text(raw.get("company"), 80), "company_type": text(raw.get("company_type"), 120),
         "size": text(raw.get("size"), 120), "city": text(raw.get("city"), 60),
         "years": clamp_int(raw.get("years"), 1, 150, 15),
         "decision_maker_name": text(raw.get("decision_maker_name"), 40),
         "decision_maker_title": text(raw.get("decision_maker_title"), 80), "how_found": text(raw.get("how_found"), 200),
         "client_words": text(raw.get("client_words"), 900)}
    if not all(b[f] for f in ("company", "company_type", "size", "city", "decision_maker_name", "decision_maker_title",
                              "client_words")):
        raise llm.LLMError("portfolio brief: incomplete")
    return b


# ------------------------------------------------------------------ step 3: the review ----
def _fake_review(p: dict, a: dict) -> dict:
    words = " ".join(a.values()).lower()
    base = 4 + min(3, len(words.split()) // 60)
    hit = lambda *ks: any(x in words for x in ks)  # noqa: E731
    b = p["brief"]
    return {"scores": {"scope": base + (2 if hit("since", "region", "product", "channel") else 0),
                       "objective": base + (2 if hit("from", " to ", "by ", "%", "months") else 0),
                       "strategy": base + (2 if hit("framework", "option", "first") else 0),
                       "execution": base + (2 if hit("owner", "weekly", "monthly", "metric") else 0)},
            "good": ["You turned the client's words into a clear problem.", "Your first move is practical."],
            "improve": ["Put numbers on the objective: from, to, by when.", "Name one weekly and one monthly metric."],
            "summary": "Test mode feedback. Live mode reads your approach and scores it properly.",
            "case_study": {
                "title": f"Fixing cash flow at a {b['company_type'].lower()}",
                "client_context": f"{b['company']}, {b['company_type'].lower()} in {b['city']} ({b['size']}).",
                "challenge": f"{b['decision_maker_name']} said sales were growing but cash was always short.",
                "approach": [a["scope"], a["objective"], a["framework_options"].split(".")[0],
                             a["framework_options"], a["do_first"], a["owner_metrics"]],
                "expected_outcome": "We expect working capital to free up within 90 days if the plan holds.",
                "lessons": ["Start from the client's words, then make them precise.", "One owner, one weekly number.",
                            "Do the simplest high-benefit move first."]},
            "video_script": {
                "hook": "Sales up, cash down. I hear this from owners all the time.",
                "problem": f"Take a {b['company_type'].lower()} in {b['city']}: growing every year, yet short of cash every month.",
                "approach": "I start by making the problem precise, then set one clear objective, pick a framework, "
                            "and choose the one move to do first, with an owner and a weekly number.",
                "result": "The plan aims to free up cash within 90 days, tracked every week.",
                "call_to_action": "If this sounds like your business, message me. Let's look at your numbers together."}}


def _review_prompt(p: dict, a: dict, k: dict) -> str:
    b = p["brief"]
    return (f"{system_block(k)}\n\nTHE PRACTICE CLIENT:\n{b['company']} — {b['company_type']}, {b['size']}, {b['city']}, "
            f"{b['years']} years in business. Decision-maker: {b['decision_maker_name']}, {b['decision_maker_title']}.\n"
            f"What {b['decision_maker_name']} said: \"{b['client_words']}\"\n\n"
            "THE MEMBER'S APPROACH:\n"
            f"Scope: {a['scope']}\nObjective: {a['objective']}\nFramework and options: {a['framework_options']}\n"
            f"Do first: {a['do_first']}\nOwner and metrics: {a['owner_metrics']}\n\n"
            "Write: scores (4 criteria, 0-10), good (2-3 short things they did well), improve (2-3 short, specific "
            "things to improve), summary (1-2 sentences), case_study {title (max 10 words), client_context (2 sentences), "
            "challenge (2-3 sentences: the precise problem), approach (EXACTLY 6 strings, one per step in order: "
            f"{', '.join(STEPS)}), expected_outcome (1-2 sentences, a projection), lessons (3 short lines)}}, "
            "video_script {hook, problem, approach, result (the projected result), call_to_action} — 150-220 words in all.\n"
            'JSON: {"scores": {"scope": 0, "objective": 0, "strategy": 0, "execution": 0}, "good": [""], "improve": [""], '
            '"summary": "", "case_study": {"title": "", "client_context": "", "challenge": "", "approach": ["", "", "", '
            '"", "", ""], "expected_outcome": "", "lessons": [""]}, "video_script": {"hook": "", "problem": "", '
            '"approach": "", "result": "", "call_to_action": ""}}')


def _clean_review(raw: dict) -> dict:
    sc = raw.get("scores") or {}
    if not isinstance(sc, dict) or not all(k in sc for k, _ in CRITERIA):
        raise llm.LLMError("portfolio: missing scores")
    scores = {k: clamp_int(sc.get(k), 0, 10, 0) for k, _ in CRITERIA}
    cs = raw.get("case_study") if isinstance(raw.get("case_study"), dict) else {}
    vs = raw.get("video_script") if isinstance(raw.get("video_script"), dict) else {}
    steps = text_list(cs.get("approach"), 6, 700)
    case = {"title": text(cs.get("title"), 100), "client_context": text(cs.get("client_context"), 500),
            "challenge": text(cs.get("challenge"), 700),
            "approach": [{"step": i + 1, "name": STEPS[i], "text": t} for i, t in enumerate(steps)],
            "expected_outcome": text(cs.get("expected_outcome"), 400), "lessons": text_list(cs.get("lessons"), 4, 240)}
    script = {f: text(vs.get(f), 600) for f in ("hook", "problem", "approach", "result", "call_to_action")}
    if (len(steps) < 6 or not all(case[f] for f in ("title", "client_context", "challenge", "expected_outcome"))
            or not all(script.values())):
        raise llm.LLMError("portfolio: incomplete review")
    words = sum(len(v.split()) for v in script.values())
    return {"scores": scores, "overall": round(sum(scores.values()) / len(scores), 1),
            "good": text_list(raw.get("good"), 3, 200), "improve": text_list(raw.get("improve"), 3, 200),
            "summary": text(raw.get("summary"), 400), "case_study": case, "video_script": script,
            "script_words": words, "script_seconds": round(words / 2.5)}    # ~150 words a minute


def _card(d: dict) -> dict:
    b = d.get("brief") or {}
    return {"id": d["_id"], "status": d["status"], "company": b.get("company"), "city": b.get("city"),
            "decision_maker": f"{b.get('decision_maker_name', '')}, {b.get('decision_maker_title', '')}".strip(", "),
            "title": ((d.get("review") or {}).get("case_study") or {}).get("title") or b.get("company"),
            "overall": (d.get("review") or {}).get("overall"), "at": iso(d["at"])}


def _public(d: dict) -> dict:
    return {**_card(d), "niche": d.get("niche"), "brief": d.get("brief"), "answer": d.get("answer"),
            "review": d.get("review"), "criteria": [{"key": k, "label": lbl} for k, lbl in CRITERIA],
            "steps": STEPS, "outcome_label": OUTCOME_LABEL, "practice_note": PRACTICE_NOTE,
            "answered_at": iso(d.get("answered_at")), "done_at": iso(d.get("done_at"))}


async def _own(pid: str, uid: str) -> dict:
    d = await db().portfolio_projects.find_one({"_id": pid, "user_id": uid})
    if not d:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Project not found."})
    return d


@router.post("")
async def start(user: dict = Depends(user_dep())):
    """Step 1: a new practice client from the member's niche. Counts one portfolio project."""
    uid = str(user["_id"])

    async def work(plan: str):
        k = await knowledge(db(), user)
        raw = await llm.complete_json(task="portfolio_brief", system=SYSTEM_BRIEF, prompt=_brief_prompt(k),
                                      fake=lambda: _fake_brief(k), model="strong", max_tokens=700)
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "status": "brief", "niche": k.get("niche") or "",
               "brief": _clean_brief(raw), "answer": None, "review": None, "at": utcnow()}
        await db().portfolio_projects.insert_one(doc)
        await events.track(db(), "portfolio_started", user_id=uid, props={"niche": doc["niche"][:60]})
        return _public(doc)
    return await run_metered(db(), user, "portfolio", work)


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    return {"items": [_card(d) async for d in db().portfolio_projects.find({"user_id": str(user["_id"])})
                      .sort("at", -1).limit(48)]}


@router.get("/{pid}")
async def one(pid: str, user: dict = Depends(user_dep())):
    return _public(await _own(pid, str(user["_id"])))


async def _review(user: dict, p: dict) -> dict:
    k = await knowledge(db(), user)
    try:
        raw = await llm.complete_json(task="portfolio_review", system=SYSTEM_REVIEW, prompt=_review_prompt(p, p["answer"], k),
                                      fake=lambda: _fake_review(p, p["answer"]), model="strong", max_tokens=2600)
        review = _clean_review(raw)
    except llm.LLMError:
        raise busy_error()           # the answer is saved (status "answered"): "Get my feedback" tries again
    await db().portfolio_projects.update_one({"_id": p["_id"]}, {"$set": {"review": review, "status": "done",
                                                                          "done_at": utcnow()}})
    await events.track(db(), "portfolio_done", user_id=p["user_id"], props={"score": review["overall"]})
    return _public(await _own(p["_id"], p["user_id"]))


@router.post("/{pid}/answer")
async def answer(pid: str, body: AnswerIn, user: dict = Depends(user_dep())):
    """Step 2 + 3: save the member's approach, then get the feedback, case study and video script."""
    uid = str(user["_id"])
    await plans.require(db(), user, "portfolio")
    p = await _own(pid, uid)
    if p["status"] == "done":
        raise HTTPException(status_code=409, detail={"code": "done", "msg": "This project is finished. Start a new one."})
    ans = {k: v.strip() for k, v in body.model_dump().items()}
    await db().portfolio_projects.update_one({"_id": pid}, {"$set": {"answer": ans, "status": "answered",
                                                                     "answered_at": utcnow()}})
    return await _review(user, {**p, "answer": ans, "status": "answered"})


@router.post("/{pid}/review")
async def review(pid: str, user: dict = Depends(user_dep())):
    """Try the feedback again for a saved answer (after the AI was busy)."""
    await plans.require(db(), user, "portfolio")
    p = await _own(pid, str(user["_id"]))
    if p["status"] != "answered" or not p.get("answer"):
        raise HTTPException(status_code=409, detail={"code": "bad_status", "msg": "Write your approach first."})
    return await _review(user, p)
