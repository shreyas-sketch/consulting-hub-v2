"""Weekly case from real news: every Monday 06:30 IST a new case built on a real Indian business story.

The job searches Indian business news (a rotating list of queries: margins, expansion, layoffs, attrition, funding,
supply problems), the AI picks ONE story by its number and writes a case in exactly the case_bank shape
(title, company = the real company in the story, industry, city, situation, facts, question, framework_hint and a
model answer on the Strategic Thinking Framework, built with case_bank._ma). The source link comes only from the
search result, never from the AI. Bad AI output is skipped, never published.

    cases {..., kind: "weekly", week: "YYYY-Www", origin: "news", source: {title, url}, test, active, created_at}

When a new case is published (a newer week, or "Make one now" again in the same week), every other weekly case
becomes a practice case (kind "practice", week and source kept), so answers stay reachable and only the newest case
shows the "This week" chip. Members on any paid plan get an inbox alert (once per week, deduped).

Jobs: "weekly_case" (Mon 06:30 IST) fails (ok: false in Admin › Jobs) when no news came back or the AI output failed
the checks; "weekly_case_retry" (daily 10:30 IST) tries again only while this week has no case at all.

Admin: GET /admin/weekly · POST /admin/weekly/generate · POST /admin/weekly/{id}/active {active}
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import indexes
import llm
import plans
from core.deps import admin_dep
from growth import events
from growth.clock import IST, as_utc, utcnow
from jobs import registry
from notify import service as notify
from research import search
from state import db
from util import iso

from .case_bank import _ma
from .common import text, text_list

log = logging.getLogger("features.weekly")
router = APIRouter(tags=["weekly-case"])
Admin = Depends(admin_dep())

events.register("weekly_case_published", "Weekly case from real news published (props.case_id, week, company, test)")
notify.register_kind("weekly_case")
indexes.register("cases", [("origin", 1), ("week", -1)], {"sparse": True})
registry.register("weekly_case", "Publish the weekly case from real Indian business news", ("weekly", 0, 6, 30),
                  "features.weekly:job_weekly_case")
registry.register("weekly_case_retry", "Weekly case: try again if this week has none yet", ("daily", 10, 30),
                  "features.weekly:job_weekly_case_retry")

# Rotated one per run. Plain news queries; the AI then picks the story that makes the best case.
QUERIES = [
    "Indian company profit margins fall quarterly results",
    "Indian company expansion new plant stores investment",
    "India company layoffs restructuring cost cutting",
    "India employee attrition company hiring problem",
    "Indian startup raises funding crore growth plans",
    "India company supply shortage raw material costs production",
    "Indian brand losing market share competition",
    "Indian company working capital debt cash flow pressure",
]
OPTION_SOURCES = ["Same industry", "Adjacent industry", "Similar geography", "Customer research", "Out of the box"]

SYSTEM = (
    "You write the weekly business case for Akshat Dani's consulting program. Members are senior Indian professionals "
    "(mostly 40+, 15-35 years' experience) becoming consultants. Each week they solve a case built on a real Indian "
    "business story from the news, using the Strategic Thinking Framework: Phase 1 Define the Problem (Step 1 Understand "
    "Scope: region, product, channel, time; Step 2 Identify Objective: from, to, in by when, success and failure), "
    "Phase 2 Craft the Strategy (Step 3 Identify Framework; Step 4 Generate Options from five sources: same industry, "
    "adjacent industry, similar geography, customer research, out of the box; Step 5 Prioritize: business benefit x "
    "ease, do first), Phase 3 Execute (Step 6 Implementation Charter: owner, a leading metric weekly, a lagging metric "
    "monthly). Use only what the news item says about the company. Where you add figures to make the case workable, "
    "keep them modest and typical, and never present them as reported facts. Money in Indian rupees with Indian "
    "grouping (₹1,50,000; ₹12 crore). Plain English, short sentences, no jargon, no hype. Never mention AI providers, "
    "models, courses or upsells."
)


class LLMSkip(llm.LLMError):
    """AI output that fails validation: the case is not published."""


class WeeklyCaseNotMade(RuntimeError):
    """A scheduled run made no case (no news, or AI output that failed the checks): the run is recorded as failed."""


def week_key(now: Optional[datetime] = None) -> str:
    y, w, _ = as_utc(now or utcnow()).astimezone(IST).isocalendar()
    return f"{y}-W{w:02d}"


def _prompt(results: list[dict]) -> str:
    news = "\n".join(f"[{i + 1}] {r['title']} ({r['source']}, {r.get('published') or 'date unknown'}): {r['snippet'][:500]}"
                     for i, r in enumerate(results))
    return (
        f"NEWS ITEMS:\n{news}\n\n"
        "Pick the ONE item that makes the best consulting case: a named Indian company with a clear business problem "
        "(margins, growth, people, cash, supply, competition). Give its number as pick. Then write the case about that "
        "company.\n"
        "title: 3-7 words, the problem in plain words (not the company name). company: the company named in the item. "
        "industry: 'Sector · sub-sector'. city: the city or state it is based in, or 'India'. situation: 3-4 sentences. "
        "facts: 4 short facts (from the news, or clearly typical figures). question: what the owner or CEO asks, then "
        "'Take it through the framework'. framework_hint: one short question that points to the right lens.\n"
        "model_answer: scope_before (the client's vague words, in quotes style), scope_after (one precise problem: "
        "where, what, since when), objective {from, to, by}, success, failure, framework, framework_why, finding, "
        "options (exactly 5, one per source in this order: " + ", ".join(OPTION_SOURCES) + "), do_first, "
        "charter {owner, leading (a weekly number), lagging (a monthly number)}.\n"
        'JSON: {"pick": 1, "title": "", "company": "", "industry": "", "city": "", "situation": "", "facts": [""], '
        '"question": "", "framework_hint": "", "model_answer": {"scope_before": "", "scope_after": "", '
        '"objective": {"from": "", "to": "", "by": ""}, "success": "", "failure": "", "framework": "", '
        '"framework_why": "", "finding": "", "options": [{"source": "Same industry", "option": ""}], "do_first": "", '
        '"charter": {"owner": "", "leading": "", "lagging": ""}}}'
    )


def _fake(results: list[dict]) -> dict:
    r = results[0]
    company = " ".join(r["title"].split()[:2])
    return {
        "pick": 1, "title": "Growing fast, earning less", "company": company, "industry": "Manufacturing · consumer goods",
        "city": "India",
        "situation": f"{company} is in the news this week. Sales are growing, but costs are rising faster and profit "
                     "is under pressure. The leadership team wants to keep growing without losing more margin.",
        "facts": ["Raw material costs rose sharply this year", "Two new locations opened in the last 12 months",
                  "Discounts were raised to hold market share", "Test mode case: these facts are samples"],
        "question": "The CEO asks: how do we keep growing and get our margin back? Take it through the framework.",
        "framework_hint": "Where does each ₹100 of sales leak before it becomes profit?",
        "model_answer": {
            "scope_before": "We're growing, but we make less money.",
            "scope_after": "Profit as a share of sales fell over the last 12 months, mostly at the new locations and on discounted lines.",
            "objective": {"from": "Falling margin", "to": "Margin back to last year's level", "by": "2 quarters"},
            "success": "Margin back to last year's level while sales keep growing.",
            "failure": "No margin recovery at the 6-week check.",
            "framework": "Margin leak check: Profit = Sales − Cost of goods − Discounts − Operating costs",
            "framework_why": "It shows exactly where each rupee of sales leaks before it becomes profit.",
            "finding": "Growth was bought with discounts and new fixed costs before the new locations could pay for themselves.",
            "options": [{"source": s, "option": o} for s, o in zip(OPTION_SOURCES, [
                "Price increases on the lines with the strongest brand pull", "Cut the slowest-selling products, as quick-commerce brands do",
                "Renegotiate supply with nearby vendors to cut freight", "Ask 30 key buyers which offers actually change what they buy",
                "Pause new openings until the latest locations break even"])],
            "do_first": "Stop blanket discounts on the top lines: the fastest margin win.",
            "charter": {"owner": "Chief financial officer", "leading": "Discount as % of sales, every week",
                        "lagging": "Margin %, every month"}},
    }


def _need(v, n: int, what: str) -> str:
    t = text(v, n)
    if len(t) < 3:
        raise LLMSkip(f"weekly: missing {what}")
    return t


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", s.lower())


def clean_case(raw: dict, results: list[dict]) -> tuple[dict, dict]:
    """Strict check of the AI's case. Returns (case fields, chosen search result) or raises LLMSkip."""
    if not isinstance(raw, dict):
        raise LLMSkip("weekly: not an object")
    try:
        pick = int(raw.get("pick"))
    except (TypeError, ValueError):
        raise LLMSkip("weekly: no pick")
    if not 1 <= pick <= len(results):
        raise LLMSkip("weekly: pick out of range")
    r = results[pick - 1]
    company = _need(raw.get("company"), 80, "company")
    words = [w for w in _norm(company).split() if len(w) >= 3 and w not in {"ltd", "limited", "pvt", "the", "india", "and"}]
    hay = _norm(f"{r['title']} {r.get('snippet', '')}")
    if not words or not any(w in hay.split() for w in words):
        raise LLMSkip("weekly: company is not in the chosen story")
    facts = text_list(raw.get("facts"), 5, 200)
    if len(facts) < 3:
        raise LLMSkip("weekly: too few facts")
    situation = text(raw.get("situation"), 900)
    if len(situation) < 80:
        raise LLMSkip("weekly: situation too short")
    m = raw.get("model_answer")
    if not isinstance(m, dict):
        raise LLMSkip("weekly: no model answer")
    o = m.get("objective") if isinstance(m.get("objective"), dict) else {}
    ch = m.get("charter") if isinstance(m.get("charter"), dict) else {}
    opts = m.get("options") if isinstance(m.get("options"), list) else []
    by_src = {}
    for x in opts:
        if isinstance(x, dict) and text(x.get("option"), 200):
            src = text(x.get("source"), 40)
            match = next((s for s in OPTION_SOURCES if s.lower() == src.lower()), None)
            if match and match not in by_src:
                by_src[match] = text(x.get("option"), 200)
    if len(by_src) != 5:
        raise LLMSkip("weekly: options must cover the five sources")
    ma = _ma(_need(m.get("scope_before"), 200, "scope_before"), _need(m.get("scope_after"), 300, "scope_after"),
             _need(o.get("from"), 80, "objective.from"), _need(o.get("to"), 80, "objective.to"),
             _need(o.get("by"), 60, "objective.by"), _need(m.get("success"), 240, "success"),
             _need(m.get("failure"), 240, "failure"), _need(m.get("framework"), 200, "framework"),
             _need(m.get("framework_why"), 240, "framework_why"), _need(m.get("finding"), 400, "finding"),
             [(s, by_src[s]) for s in OPTION_SOURCES], _need(m.get("do_first"), 240, "do_first"),
             _need(ch.get("owner"), 100, "charter.owner"), _need(ch.get("leading"), 140, "charter.leading"),
             _need(ch.get("lagging"), 140, "charter.lagging"))
    case = {"title": _need(raw.get("title"), 80, "title"), "company": company,
            "industry": _need(raw.get("industry"), 60, "industry"), "city": text(raw.get("city"), 40) or "India",
            "situation": situation, "facts": facts, "question": _need(raw.get("question"), 400, "question"),
            "framework_hint": text(raw.get("framework_hint"), 160) or None, "model_answer": ma}
    return case, r


async def _recipients(d) -> list[str]:
    paid = await plans.nonfree_plans(d)
    revoked = {str(u["_id"]) async for u in d.users.find({"status": "revoked"}, {"_id": 1})}
    return [uid for uid in paid if uid not in revoked]


async def make_weekly_case(d, now: Optional[datetime] = None) -> dict:
    """Search → AI picks one story and writes the case → strict check → publish → alert paid members.
    Returns {published, ...} or {skipped: reason}. Never publishes bad AI output."""
    now = now or utcnow()
    week = week_key(now)
    n_made = await d.cases.count_documents({"origin": "news"})
    query = QUERIES[n_made % len(QUERIES)]
    results = await search.news(query, max_results=8)
    results = [r for r in results if r.get("url", "").startswith(("https://", "http://")) and r.get("title")]
    if not results:
        return {"skipped": "no_news", "query": query}
    try:
        raw = await llm.complete_json(task="weekly_case", system=SYSTEM, prompt=_prompt(results),
                                      fake=lambda: _fake(results), model="strong", max_tokens=2200)
        case, r = clean_case(raw, results)
    except llm.LLMError as e:
        log.warning("weekly case skipped: %s", e)
        return {"skipped": "bad_ai_output", "reason": str(e)[:200], "query": query}
    doc = {"_id": uuid.uuid4().hex, **case, "kind": "weekly", "week": week, "origin": "news",
           "source": {"title": r["title"][:200], "url": r["url"][:500]}, "test": bool(r.get("test")),
           "query": query, "active": True, "created_at": now}
    await d.cases.insert_one(doc)
    # Every other weekly case (older weeks, or an earlier one made this week) stays as a practice case: answers remain
    # reachable, and only the newest case is "This week".
    await d.cases.update_many({"origin": "news", "kind": "weekly", "_id": {"$ne": doc["_id"]}}, {"$set": {"kind": "practice"}})
    await events.track(d, "weekly_case_published", props={"case_id": doc["_id"], "week": week,
                                                          "company": case["company"][:60], "test": doc["test"]})
    sent = await notify.alert_many(d, await _recipients(d), "weekly_case", "This week's case is ready",
                                   f"{case['company']}: {case['title']}. Solve it and see the model answer.",
                                   link=f"/app/cases/{doc['_id']}", dedupe=f"weekly_case:{week}")
    return {"published": doc["_id"], "week": week, "company": case["company"], "alerts": sent, "test": doc["test"]}


def _made(res: dict) -> dict:
    """A scheduled run that made nothing raises, so job_runs records ok: false and Admin › Jobs shows it failed."""
    if res.get("published"):
        return res
    raise WeeklyCaseNotMade(f"{res.get('skipped')}: {res.get('reason') or res.get('query') or ''}"[:200])


async def job_weekly_case(ctx) -> dict:
    """Monday 06:30 IST. One case a week: a re-run in the same week does nothing."""
    week = week_key(ctx.now)
    if await ctx.db.cases.find_one({"origin": "news", "week": week, "active": {"$ne": False}}, {"_id": 1}):
        return {"skipped": "already_published", "week": week}
    return _made(await make_weekly_case(ctx.db, ctx.now))


async def job_weekly_case_retry(ctx) -> dict:
    """Daily 10:30 IST. Runs only while this week has no case at all (a case the team switched off counts as one,
    so a hidden case is not replaced behind their back)."""
    week = week_key(ctx.now)
    if await ctx.db.cases.find_one({"origin": "news", "week": week}, {"_id": 1}):
        return {"skipped": "already_published", "week": week}
    return _made(await make_weekly_case(ctx.db, ctx.now))


# ------------------------------------------------------------------ admin ----
def _row(c: dict, answers: int) -> dict:
    return {"id": c["_id"], "title": c["title"], "company": c["company"], "industry": c["industry"],
            "city": c.get("city"), "week": c.get("week"), "kind": c.get("kind"), "active": c.get("active", True) is not False,
            "current": c.get("kind") == "weekly", "source": c.get("source"), "test": bool(c.get("test")),
            "answers": answers, "created_at": iso(c.get("created_at"))}


@router.get("/admin/weekly")
async def admin_list(_: dict = Admin):
    d = db()
    rows = []
    async for c in d.cases.find({"origin": "news"}).sort([("week", -1), ("created_at", -1)]).limit(100):
        rows.append(_row(c, await d.case_answers.count_documents({"case_id": c["_id"]})))
    last = await d.job_runs.find_one({"name": {"$in": ["weekly_case", "weekly_case_retry"]}}, sort=[("at", -1)])
    return {"items": rows, "schedule": registry.schedule_text(("weekly", 0, 6, 30)), "this_week": week_key(),
            "last_run": {"at": iso(last["at"]), "ok": last.get("ok"), "result": last.get("result") or last.get("error")}
            if last else None}


@router.post("/admin/weekly/generate")
async def admin_generate(_: dict = Admin):
    d = db()
    res = await make_weekly_case(d)
    if not res.get("published"):
        msg = {"no_news": "No news came back from the search. Try again in a few minutes.",
               "bad_ai_output": "The case didn't pass the checks, so it wasn't published. Try again."}.get(res["skipped"], "Not published.")
        raise HTTPException(status_code=503, detail={"code": res["skipped"], "msg": msg})
    c = await d.cases.find_one({"_id": res["published"]})
    return {"item": _row(c, 0), "alerts": res["alerts"]}


class ActiveIn(BaseModel):
    active: bool


@router.post("/admin/weekly/{case_id}/active")
async def admin_active(case_id: str, body: ActiveIn, _: dict = Admin):
    d = db()
    res = await d.cases.update_one({"_id": case_id, "origin": "news"}, {"$set": {"active": body.active}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Weekly case not found."})
    c = await d.cases.find_one({"_id": case_id})
    return {"item": _row(c, await d.case_answers.count_documents({"case_id": case_id}))}
