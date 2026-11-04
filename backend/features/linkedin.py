"""LinkedIn Score + Improve.

linkedin_checks {_id, user_id, input: {headline, about, experience}, score, parts, problems, rewrites?, at}

The score is rule-based (instant, no AI cost): does the profile say who you help, what result you get, show proof
in numbers, and tell people what to do next? Paid plans also get AI rewrites following the current hub's
"LinkedIn Optimizer" GPT (backend/gpts/prompts/linkedin-optimizer.md): three headlines (authority, outcome and
niche angles, under 220 characters), an About section of 300–400 words (hook, story, who you help, what working
with you looks like, proof, call to action) and three post ideas, written around the member's chosen niche.
Members paste their text; we never log in to LinkedIn.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import llm
import plans
from core.deps import user_dep
from core.flags import is_on
from growth import events
from growth.clock import utcnow
from state import db
from util import iso

from .common import run_metered, text, text_list

router = APIRouter(prefix="/linkedin", tags=["linkedin"])

RESULT_WORDS = re.compile(r"\b(grow|growth|increase|reduce|cut|profit|revenue|sales|cost|scale|save|faster|margin|"
                          r"turnaround|transform|improve|double|crore|lakh)\w*|%|₹", re.I)
WHO_WORDS = re.compile(r"\b(help|helping|for|founders?|owners?|companies|businesses|brands|teams|leaders|ceos?|msmes?|smes?|"
                       r"startups?|manufacturers?|retailers?|hospitals?|schools?)\b", re.I)
JOB_HUNT = re.compile(r"\b(open to work|seeking|looking for (a )?(job|role|opportunit))", re.I)
BUZZ = re.compile(r"\b(passionate about|results[- ]driven|go-getter|dynamic professional|seasoned professional|"
                  r"hard[- ]working|team player|synergy)\b", re.I)
CTA = re.compile(r"\b(dm|message me|reach out|book|call|email|connect with me|let's talk|write to me|whatsapp)\b", re.I)
PROOF = re.compile(r"\d")
CONSULT = re.compile(r"\b(consult\w*|advis\w*|mentor\w*|framework\w*|clients?|diagnos\w*|strateg\w*)\b", re.I)


class CheckIn(BaseModel):
    headline: str = Field(..., min_length=5, max_length=300)
    about: str = Field("", max_length=3000)
    experience: str = Field("", max_length=3000)
    rewrite: bool = False


def _part(key: str, label: str, got: int, mx: int, tip: str) -> dict:
    return {"key": key, "label": label, "score": max(0, min(mx, got)), "max": mx, "tip": tip}


def score_profile(headline: str, about: str, experience: str) -> dict:
    h, a, e = headline.strip(), about.strip(), experience.strip()
    parts = []
    hs = (5 if 40 <= len(h) <= 220 else 2) + (10 if WHO_WORDS.search(h) else 0) + (10 if RESULT_WORDS.search(h) else 0)
    if JOB_HUNT.search(h):
        hs -= 8
    if BUZZ.search(h):
        hs -= 4
    parts.append(_part("headline", "Headline says who you help and the result", hs, 25,
                       "Write it as: I help [who] get [result]. Drop job-hunting words and phrases like 'passionate about'."))
    first = re.split(r"(?<=[.!?])\s|\n", a, maxsplit=1)[0] if a else ""
    ab = (8 if len(a) >= 600 else 4 if len(a) >= 200 else 0)
    ab += 7 if first and len(first) <= 200 and not re.match(r"^(i am|i'm|my name)", first, re.I) else 0
    ab += 8 if len(PROOF.findall(a)) >= 3 else 4 if PROOF.search(a) else 0
    ab += 6 if WHO_WORDS.search(a) else 0
    ab += 6 if CTA.search(a) else 0
    ab -= 4 if BUZZ.search(a) else 0
    parts.append(_part("about", "About section hooks, proves and asks", ab, 35,
                       "Open with the problem you solve, add 3 results in numbers, end with how to reach you."))
    if e:
        ex = (10 if len(PROOF.findall(e)) >= 3 else 5 if PROOF.search(e) else 0) + (10 if RESULT_WORDS.search(e) else 0)
        ex += 5 if e.count("\n") >= 2 or e.count("•") >= 2 or e.count("- ") >= 2 else 0
        parts.append(_part("experience", "Experience shows results, not duties", ex, 25,
                           "Rewrite each role as 3 results with numbers: what changed because of you."))
    pos = 15 if len(CONSULT.findall(h + " " + a)) >= 2 else 7 if CONSULT.search(h + " " + a) else 0
    parts.append(_part("positioning", "Reads like a consultant, not an employee", pos, 15,
                       "Use client words: who you work with, the problems you diagnose, your way of solving them."))
    got = sum(p["score"] for p in parts)
    mx = sum(p["max"] for p in parts)
    total = round(got * 100 / mx)
    problems = sorted(parts, key=lambda p: -(p["max"] - p["score"]) / p["max"])[:3]
    return {"score": total, "parts": parts, "experience_checked": bool(e),
            "problems": [{"key": p["key"], "label": p["label"], "tip": p["tip"]} for p in problems if p["score"] < p["max"]]}


SYSTEM = ("You are a personal branding expert helping experienced Indian professionals moving into consulting build a "
          "client-attracting LinkedIn presence. For a B2B consultant, LinkedIn is the number one business development "
          "tool. Headlines: under 220 characters, clearly state who they help and the outcome, confident and specific, "
          "never 'passionate about' or 'results-driven'. About section: 300-400 words in this order: a hook that stops "
          "the scroll, their story and credibility (brief, not a CV), who they help and what problems they solve, what "
          "working with them looks like, social proof, a clear call to action. Write like a real person, not a press "
          "release. No emojis. Never invent facts or numbers: use only what is in their text, and write [number] where "
          "a figure should go.")


def _fake_rewrite(h: str, niche: Optional[str]) -> dict:
    n = niche or "growing businesses"
    return {"headlines": [{"angle": "Authority", "text": f"[number] years fixing operations | Now helping {n} grow profit without adding cost"},
                          {"angle": "Outcome", "text": f"I help {n} find and fix margin leaks in 90 days"},
                          {"angle": "Niche", "text": f"Consultant for {n} · Ex-{h[:40]}"}],
            "about": f"Most {n} grow sales but lose profit on the way.\n\nI spent [number] years inside businesses like "
                     "yours, and I saw the same leaks again and again.\n\nI help owners find where the money goes and "
                     "fix it in 90 days. We start with a two-week diagnosis, agree on one number to move, and work on it "
                     "together.\n\nIn my career I have [result 1], [result 2] and [result 3].\n\n"
                     "If that sounds like your business, message me here.",
            "posts": [{"hook": "The day I found ₹[number] lakh hiding in a warehouse", "summary": "A story from your career that shows how you diagnose a problem."},
                      {"hook": "More sales won't fix your profit", "summary": "A counter-intuitive view from your niche, with one example."},
                      {"hook": "A 3-question check for margin leaks", "summary": "A mini-framework your ideal client can use this week."}],
            "note": "Test mode rewrite. Live mode writes this from your profile."}


async def _niche(uid: str) -> Optional[str]:
    s = await db().snapshots.find_one({"user_id": uid}, sort=[("at", -1)])
    if not s or not s.get("options"):
        return None
    o = s["options"][min(int(s.get("chosen") or 0), len(s["options"]) - 1)]
    return f"{o['niche']} — for {o['who']}"


def _public(d: dict) -> dict:
    return {"id": d["_id"], "score": d["score"], "parts": d["parts"], "problems": d["problems"],
            "experience_checked": d.get("experience_checked"), "rewrites": d.get("rewrites"),
            "rewrites_locked": d.get("rewrites_locked", False), "input": d["input"], "at": iso(d["at"])}


@router.post("/check")
async def check(body: CheckIn, user: dict = Depends(user_dep())):
    uid = str(user["_id"])

    async def work(plan: str):
        res = score_profile(body.headline, body.about, body.experience)
        rewrites, locked = None, False
        if body.rewrite:
            if not plans.plan_allows(plan, "linkedin_improve"):
                locked = True
            elif is_on("LINKEDIN_REWRITES"):
                niche = await _niche(uid)
                prompt = (f"Niche (from their Niche Snapshot): {niche or 'not chosen yet'}\nHeadline: {body.headline}\n"
                          f"About: {body.about or '(empty)'}\nExperience: {body.experience or '(not given)'}\n\n"
                          "Write 3 headline options (authority angle, outcome angle, niche angle), one About section of "
                          "300-400 words, and 3 post ideas (a personal story that shows expertise, a counter-intuitive "
                          "insight from their niche, a practical tip or mini-framework their ideal client would value).\n"
                          'JSON: {"headlines": [{"angle": "Authority", "text": ""}, {"angle": "Outcome", "text": ""}, '
                          '{"angle": "Niche", "text": ""}], "about": "", "posts": [{"hook": "", "summary": ""}]}')
                raw = await llm.complete_json(task="linkedin_rewrite", system=SYSTEM, prompt=prompt,
                                              fake=lambda: _fake_rewrite(body.headline, niche), model="strong", max_tokens=900)
                heads = []
                for x in (raw.get("headlines") or [])[:3]:
                    if isinstance(x, dict) and text(x.get("text"), 220):
                        heads.append({"angle": text(x.get("angle"), 20) or "Option", "text": text(x.get("text"), 220)})
                    elif isinstance(x, str) and text(x, 220):
                        heads.append({"angle": "Option", "text": text(x, 220)})
                posts = [{"hook": text(p.get("hook"), 160), "summary": text(p.get("summary"), 300)}
                         for p in (raw.get("posts") or [])[:3] if isinstance(p, dict) and p.get("hook")]
                rewrites = {"headlines": heads, "about": str(raw.get("about") or "")[:3500].strip(), "posts": posts,
                            "note": text(raw.get("note"), 200) or None}
                if not rewrites["headlines"] or not rewrites["about"]:
                    raise llm.LLMError("linkedin: empty rewrite")
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "input": body.model_dump(exclude={"rewrite"}), **res,
               "rewrites": rewrites, "rewrites_locked": locked, "at": utcnow()}
        await db().linkedin_checks.insert_one(doc)
        await events.track(db(), "linkedin_checked", user_id=uid, props={"score": res["score"], "rewrites": bool(rewrites)})
        return _public(doc)
    return await run_metered(db(), user, "linkedin", work)


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    rows = [_public(d) async for d in db().linkedin_checks.find({"user_id": str(user["_id"])}).sort("at", -1).limit(12)]
    return {"latest": rows[0] if rows else None, "history": [{"id": r["id"], "score": r["score"], "at": r["at"]} for r in rows]}


@router.get("/{check_id}")
async def one(check_id: str, user: dict = Depends(user_dep())):
    d = await db().linkedin_checks.find_one({"_id": check_id, "user_id": str(user["_id"])})
    if not d:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Not found."})
    return _public(d)
