"""Progress Report: once a month, how far you've come and what to work on next.

progress_reports {_id, user_id, month "YYYY-MM" (IST), stats, summary, focus: [{title, why}], at}

Every number comes from the member's own data (readiness, case answers, briefs, LinkedIn checks, decks, visuals,
audio, tool events, Goal Map) over the last 30 days, compared with the 30 days before. The AI writes only a short
plain summary and 3 focus items for next month; any sentence or focus item with a number that isn't in the data
is dropped, and rule-based focus items fill the gap.

Job "progress_nudge" (daily 09:00 IST, acts on day 1 of the IST month): inbox alert to every member+ user.
"""
from __future__ import annotations

import re
import uuid
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends

import indexes
import llm
import plans
from core.deps import user_dep
from core.errors import NotFound
from growth import events
from growth.clock import IST, as_utc, ist_month_key, utcnow
from jobs import registry
from notify import service as notify
from state import db
from util import inr, iso

from .common import run_metered, text
from .readiness import SKILLS
from .readiness import score as readiness_score
from .start import goal_map

router = APIRouter(prefix="/progress", tags=["progress-report"])

events.register("progress_made", "Progress Report made (props.month)")
notify.register_kind("progress")
indexes.register("progress_reports", [("user_id", 1), ("month", -1)])
registry.register("progress_nudge", "Tell members their monthly Progress Report is ready to make (day 1, IST)",
                  ("daily", 9, 0), "features.progress:job_progress_nudge")

WINDOW_DAYS = 30
TOOL_EVENTS = {"readiness_done": "Readiness Score", "snapshot_run": "Niche Snapshot", "goal_saved": "Goal Map",
               "case_answered": "Cases", "brief_made": "Meeting Brief", "linkedin_checked": "LinkedIn Score",
               "deck_made": "Presentation Builder", "visual_made": "Visual Builder", "audio_made": "Listen mode"}

SYSTEM = (
    "You write a short monthly progress note for a senior Indian professional who is becoming a consultant in Akshat "
    "Dani's program. Plain spoken English, warm but honest, short sentences, no hype, no emojis. Talk to them as 'you'. "
    "The numbers are shown next to your note, so do not write any digits or figures yourself: describe what moved and "
    "what didn't in words. Never promise income. Never mention AI providers, models, courses or upsells."
)


def _avg(xs: list[float]) -> Optional[float]:
    return round(sum(xs) / len(xs), 1) if xs else None


def _diff(a, b):
    return None if a is None or b is None else round(a - b, 1)


async def build_stats(d, user: dict, now=None) -> dict:
    now = as_utc(now or utcnow())
    uid = str(user["_id"])
    start, prev_start = now - timedelta(days=WINDOW_DAYS), now - timedelta(days=2 * WINDOW_DAYS)
    win = {"$gte": start, "$lt": now}
    prev = {"$gte": prev_start, "$lt": start}

    rd = [r async for r in d.readiness.find({"user_id": uid, "at": {"$lt": now}}).sort("at", -1).limit(2)]
    readiness = None
    if rd:
        cur = readiness_score(rd[0]["scores"], rd[0].get("potential", 0))
        last = rd[1]["total"] if len(rd) > 1 else None
        weakest = cur["focus"][0] if cur.get("focus") else None
        readiness = {"now": cur["total"], "last": last, "change": _diff(cur["total"], last), "max": 60, "band": cur["band"],
                     "weakest": weakest["name"] if weakest else None, "weakest_key": weakest["key"] if weakest else None}

    cur_scores = [a["overall"] async for a in d.case_answers.find({"user_id": uid, "at": win}, {"overall": 1})]
    prev_scores = [a["overall"] async for a in d.case_answers.find({"user_id": uid, "at": prev}, {"overall": 1})]
    cases = {"solved": len(cur_scores), "avg": _avg(cur_scores), "prev_solved": len(prev_scores),
             "prev_avg": _avg(prev_scores), "avg_change": _diff(_avg(cur_scores), _avg(prev_scores))}

    briefs = {"made": await d.briefs.count_documents({"user_id": uid, "at": win}),
              "prev": await d.briefs.count_documents({"user_id": uid, "at": prev})}

    li_now = await d.linkedin_checks.find_one({"user_id": uid, "at": {"$lt": now}}, sort=[("at", -1)])
    li_before = await d.linkedin_checks.find_one({"user_id": uid, "at": {"$lt": start}}, sort=[("at", -1)])
    if li_now and li_before and li_now["_id"] == li_before["_id"]:
        li_before = await d.linkedin_checks.find_one({"user_id": uid, "at": {"$lt": as_utc(li_now["at"])}}, sort=[("at", -1)])
    linkedin = {"now": li_now["score"], "before": li_before["score"] if li_before else None,
                "change": _diff(li_now["score"], li_before["score"] if li_before else None)} if li_now else None

    made = {"decks": await d.decks.count_documents({"user_id": uid, "created_at": win, "status": {"$ne": "failed"}}),
            "visuals": await d.visuals.count_documents({"user_id": uid, "at": win, "copied_from": {"$exists": False}}),
            "audio": await d.audio_tracks.count_documents({"user_id": uid, "at": win})}

    counts: dict[str, int] = {}
    async for e in d.events.find({"user_id": uid, "ts": win, "name": {"$in": list(TOOL_EVENTS)}}, {"name": 1}):
        counts[e["name"]] = counts.get(e["name"], 0) + 1
    tools = sorted(({"key": k, "label": TOOL_EVENTS[k], "uses": n} for k, n in counts.items()), key=lambda t: -t["uses"])

    g = await d.goals.find_one({"_id": uid})
    goal = None
    if g:
        gm = goal_map(g)
        goal = {k: gm[k] for k in ("monthly_goal_inr", "fee_inr", "clients_per_month", "discovery_calls_per_month",
                                   "conversations_per_month", "conversations_per_week")}
        goal["label"] = gm["label"]

    return {"window": {"from": iso(start), "to": iso(now), "days": WINDOW_DAYS}, "readiness": readiness, "cases": cases,
            "briefs": briefs, "linkedin": linkedin, "made": made, "tools": tools, "goal": goal}


def _flat_numbers(v, out: set) -> set:
    if isinstance(v, bool) or v is None:
        return out
    if isinstance(v, (int, float)):
        for x in (v, abs(v)):
            out.add(f"{float(x):g}")
            out.add(f"{round(float(x), 1):g}")
        return out
    if isinstance(v, dict):
        for k, x in v.items():
            if k not in ("window",):
                _flat_numbers(x, out)
    elif isinstance(v, list):
        for x in v:
            _flat_numbers(x, out)
    return out


NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _ok_numbers(s: str, allowed: set) -> bool:
    for m in NUM_RE.findall(s):
        try:
            if f"{float(m.replace(',', '')):g}" not in allowed:
                return False
        except ValueError:
            return False
    return True


def clean_summary(md: str, allowed: set) -> str:
    """Drop any sentence that carries a number not in the data."""
    out_lines = []
    for line in str(md or "").replace("\r", "").split("\n")[:30]:
        parts = re.split(r"(?<=[.!?])\s+", line)
        kept = [p for p in parts if _ok_numbers(p, allowed)]
        if kept or not line.strip():
            out_lines.append(" ".join(kept))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out_lines)).strip()[:1800]


def rule_focus(stats: dict) -> list[dict]:
    """Focus items from the data alone: used to fill in when the AI's are missing or fail the check."""
    out = []
    r = stats.get("readiness")
    if r and r.get("weakest_key"):
        nxt = next((s["next"] for s in SKILLS if s["key"] == r["weakest_key"]), None)
        out.append({"title": f"Lift your weakest skill: {r['weakest']}", "why": nxt or "Work on it a little every week."})
    if stats["cases"]["solved"] < 4:
        out.append({"title": "Solve one case every week", "why": "Use the six steps each time. It is how clients will judge your thinking."})
    if not stats.get("linkedin") or (stats["linkedin"].get("now") or 0) < 70:
        out.append({"title": "Fix the top problem on your LinkedIn profile", "why": "It is the first place a prospect looks."})
    if stats["briefs"]["made"] == 0:
        out.append({"title": "Make a Meeting Brief before your next business conversation", "why": "You walk in prepared and ask better questions."})
    if not stats.get("goal"):
        out.append({"title": "Set your Goal Map", "why": "It turns your income goal into conversations a week."})
    out.append({"title": "Have two conversations a week with people who run a business", "why": "Clients come from conversations, not from tools."})
    return out


def _fake(stats: dict) -> dict:
    c = stats["cases"]
    moved = "You kept working on your cases" if c["solved"] else "You didn't solve a case this month"
    return {"summary": f"{moved}. Your numbers are on the left of this note.\n\nTest mode note. Live mode reads your "
                       "month and writes this in plain words.",
            "focus": [{"title": f["title"], "why": f["why"]} for f in rule_focus(stats)[:3]]}


def _prompt(stats: dict, k_name: str) -> str:
    r, c, li, b, m, g = (stats["readiness"], stats["cases"], stats["linkedin"], stats["briefs"], stats["made"],
                         stats["goal"])
    rd = "not done" if not r else "%s of 60 (%s), before %s, weakest skill %s" % (r["now"], r["band"], r["last"], r["weakest"])
    lk = "not checked" if not li else "%s of 100, before %s" % (li["now"], li["before"])
    used = ", ".join("%s (%s)" % (t["label"], t["uses"]) for t in stats["tools"]) or "none"
    gl = "not set" if not g else "%s a month, %s conversations a week" % (inr(g["monthly_goal_inr"]), g["conversations_per_week"])
    lines = [f"Member: {k_name}", "LAST 30 DAYS (compared with the 30 days before):",
             f"- Readiness Score: {rd}",
             f"- Cases solved: {c['solved']} (before {c['prev_solved']}); average score {c['avg']} of 10 (before {c['prev_avg']})",
             f"- Meeting Briefs: {b['made']} (before {b['prev']})",
             f"- LinkedIn Score: {lk}",
             f"- Decks {m['decks']}, visuals {m['visuals']}, audio {m['audio']}",
             f"- Tools used: {used}",
             f"- Goal Map: {gl}"]
    return ("\n".join(lines) + "\n\nWrite summary: 3-5 short sentences in Markdown (no headings) on what moved, what "
            "didn't and why it matters for getting clients, with no digits. Then focus: exactly 3 things to do next "
            "month, each a short action title and one sentence of why, with no digits.\n"
            'JSON: {"summary": "", "focus": [{"title": "", "why": ""}]}')


def _public(r: dict) -> dict:
    return {"id": r["_id"], "month": r["month"], "stats": r["stats"], "summary": r["summary"], "focus": r["focus"],
            "at": iso(r["at"])}


@router.post("")
async def make(user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])

    async def work(plan: str):
        stats = await build_stats(d, user)
        allowed = _flat_numbers(stats, set())
        raw = await llm.complete_json(task="progress_report", system=SYSTEM, prompt=_prompt(stats, user.get("name") or "Member"),
                                      fake=lambda: _fake(stats), model="fast", max_tokens=700)
        if not isinstance(raw, dict):
            raise llm.LLMError("progress: not an object")
        summary = clean_summary(str(raw.get("summary") or ""), allowed)
        if len(summary) < 20:
            raise llm.LLMError("progress: empty summary")
        focus = []
        for f in (raw.get("focus") or [])[:3] if isinstance(raw.get("focus"), list) else []:
            if isinstance(f, dict) and text(f.get("title"), 120):
                item = {"title": text(f.get("title"), 120), "why": text(f.get("why"), 240)}
                if _ok_numbers(item["title"] + " " + item["why"], allowed):
                    focus.append(item)
        for f in rule_focus(stats):
            if len(focus) >= 3:
                break
            if all(f["title"] != x["title"] for x in focus):
                focus.append(f)
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "month": ist_month_key(), "stats": stats, "summary": summary,
               "focus": focus[:3], "at": utcnow()}
        await d.progress_reports.insert_one(doc)
        await events.track(d, "progress_made", user_id=uid, props={"month": doc["month"]})
        return _public(doc)
    return await run_metered(d, user, "progress", work)


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    month = ist_month_key()
    rows = []
    async for r in db().progress_reports.find({"user_id": str(user["_id"])}).sort("at", -1).limit(24):
        rd = r["stats"].get("readiness") or {}
        rows.append({"id": r["_id"], "month": r["month"], "at": iso(r["at"]), "readiness": rd.get("now"),
                     "cases_solved": r["stats"]["cases"]["solved"]})
    return {"items": rows, "this_month": month, "made_this_month": any(r["month"] == month for r in rows)}


@router.get("/{report_id}")
async def one(report_id: str, user: dict = Depends(user_dep())):
    r = await db().progress_reports.find_one({"_id": report_id, "user_id": str(user["_id"])})
    if not r:
        raise NotFound("Report not found.")
    return _public(r)


async def job_progress_nudge(ctx) -> dict:
    local = as_utc(ctx.now).astimezone(IST)
    if local.day != 1:
        return {"skipped": "not_day_1"}
    month = ist_month_key(ctx.now)
    users = await plans.users_with(ctx.db, "progress", ctx.now)
    sent = await notify.alert_many(ctx.db, users, "progress", "Your Progress Report is ready to make",
                                   "See what moved in the last month and the three things to work on next. It takes a minute.",
                                   link="/app/progress", dedupe=f"progress:{month}")
    return {"sent": sent, "month": month}
