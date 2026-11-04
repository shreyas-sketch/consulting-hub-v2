"""Presentation Builder: turn your notes, a case you solved or a Meeting Brief into a client-ready deck.

decks {_id, user_id, source text|case|brief, ref_id, title, audience, tone, theme dark|light, author,
       deck: {slides: [...]}, slides (count), status "ready", rev, files: {pptx: {blob_id, size}, pdf: {blob_id, size}},
       edited_at, created_at, updated_at}

Our own deck engine, no outside deck service:
  1. The AI writes the deck as JSON in eleven fixed layouts (features/deck_layout.py: SPEC, LIMITS). The answer is
     checked field by field; a wrong shape raises llm.LLMError, so the member's go is given back.
  2. features/deck_layout.py places every box with the real Manrope metrics; features/deck_render.py draws the same
     boxes as PowerPoint (python-pptx) and PDF (reportlab). The app's HTML preview draws them too (GET returns `layout`).
  3. Both files are kept in the blob store (owner-only) and served through GET /api/decks/{id}/file?kind=pptx|pdf.
Only making a deck counts against the plan ("presentation"). Editing slide text and switching Dark / Light re-render for
free, for the owner only.
"""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import indexes
import llm
import media
from core.deps import user_dep
from growth import events
from growth.clock import utcnow
from state import db
from util import iso

from . import deck_layout as dl
from .case_bank import model_answer_text
from .common import run_metered, text
from .deck_render import render_pdf, render_pptx
from .knowledge import knowledge, system_block

log = logging.getLogger("features.decks")
router = APIRouter(prefix="/decks", tags=["presentation-builder"])

events.register("deck_made", "Presentation Builder deck made (props.source, slides, theme)")
events.register("deck_edited", "Presentation Builder deck re-rendered after an edit (props.what text|theme)")
indexes.register("decks", [("user_id", 1), ("created_at", -1)])

THEMES = [{"key": "dark", "name": "Dark", "note": "For screens and video calls"},
          {"key": "light", "name": "Light", "note": "White pages for printing"}]
TONES = [
    {"key": "clear", "label": "Clear and practical", "how": "Clear, practical and plain-spoken; short sentences."},
    {"key": "boardroom", "label": "Boardroom", "how": "Confident, formal and concise, for owners and senior leaders."},
    {"key": "persuasive", "label": "Persuasive", "how": "Persuasive: lead with the problem and its cost, then the recommendation."},
    {"key": "warm", "label": "Warm, first meeting", "how": "Warm and conversational, for a first meeting with a prospect."},
    {"key": "teaching", "label": "Teaching", "how": "Explains step by step, for a workshop or a talk."},
]
TONE_KEYS = {t["key"]: t for t in TONES}
CTYPE = {"pdf": "application/pdf", "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}

SYSTEM = (
    "You write client-ready slide decks for a senior Indian professional who is becoming an independent consultant in "
    "Akshat Dani's program. The deck is shown to the presenter's client: business owners and senior leaders in India. "
    "Plain spoken English: short sentences, no jargon, no buzzwords, no hype, no emojis. Every slide title is an action "
    "title: a short sentence (4-10 words, sentence case) that states the point of the slide, not its topic. Use only the "
    "facts and numbers in the material. Never invent figures, client names, market sizes, statistics or quotes; where a "
    "number is needed but not given, write [add figure]. Money in Indian rupees with Indian grouping (₹1,50,000; "
    "₹12 lakh; ₹40 crore). Never mention or hint at AI, AI providers or models, or any software, tool or service used to "
    "make the deck; never mention courses, programs or upsells. Reply with one JSON object only, in exactly the shape asked."
)


def _layout_guide(n: int) -> str:
    L = dl.LIMITS
    return f"""SLIDE LAYOUTS (numbers are the most characters allowed; shorter is better):
- title: title ≤{L['cover_title']}, subtitle ≤{L['subtitle']}. The first slide only. The presenter's name is added for you.
- agenda: title ≤{L['title']}, items: 3-6 strings ≤{L['agenda_item']}.
- section: title ≤{L['section_title']}, subtitle ≤{L['section_sub']}. A divider before a new part (decks of 10+ slides only).
- bullets: title ≤{L['title']}, bullets: 3-6 strings ≤{L['bullet']}.
- two_column: title ≤{L['title']}, style "compare" or "before_after", left and right: {{heading ≤{L['col_heading']}, points: 2-5 strings ≤{L['col_point']}}}. For before_after, left is today and right is after (the right side is highlighted).
- big_number: title ≤{L['title']}, stats: 1-3 of {{value ≤{L['stat_value']} (a number only, like "₹40 lakh", "9%", "3x", "90 days"), label ≤{L['stat_label']}}}, note ≤{L['stat_note']} (optional).
- quote: quote ≤{L['quote']} (words someone really said, taken from the material; never made up), by ≤{L['quote_by']}.
- steps: title ≤{L['title']}, steps: 3-6 of {{title ≤{L['step_title']}, text ≤{L['step_text']}}}.
- grid_2x2: title ≤{L['title']}, y_axis ≤{L['axis']} (high at the top), x_axis ≤{L['axis']} (high on the right), cells: exactly 4 of {{title ≤{L['cell_title']}, text ≤{L['cell_text']}}} in the order top-left, top-right, bottom-left, bottom-right; highlight: the index 0-3 of the cell to stress (for example "Do first").
- table: title ≤{L['title']}, columns: 2-4 strings ≤{L['th']}, rows: 1-5 rows, each a list with one string ≤{L['td']} per column.
- closing: title ≤{L['closing_title']} (the call to action), text ≤{L['closing_text']}, action ≤{L['action']} (one specific next step with a date or a decision, like "Agree the scope by Friday").
Every slide may also have: kicker ≤{L['kicker']} (1-4 words shown in capitals above the title), accent (a few words copied exactly from the title, shown in gold: the key phrase; at most one per title, not on every slide), notes ≤{L['notes']} (what the presenter says on this slide).
RULES: exactly {n} slides. The first slide is "title" and the last is "closing". Use at least 5 different layouts and never the same layout three times in a row. Keep within every limit.
JSON: {{"slides": [{{"layout": "title", "kicker": "", "title": "", "accent": "", "subtitle": "", "notes": ""}}, {{"layout": "bullets", "kicker": "", "title": "", "accent": "", "bullets": [""], "notes": ""}}, ...]}}"""


_STF: dict = {"text": None}


def stf_block() -> str:
    """The six-step Strategic Thinking Framework, from Akshat's own GPT prompt (backend/gpts/prompts)."""
    if _STF["text"] is None:
        p = Path(__file__).resolve().parent.parent / "gpts" / "prompts" / "strategy-thinking-framework.md"
        body = ""
        try:
            s = p.read_text(encoding="utf-8")
            a = s.find("THE FRAMEWORK")
            b = s.find("PART 1", a)
            body = s[a:b].strip() if a >= 0 and b > a else ""
        except OSError:
            pass
        _STF["text"] = body or (
            "THE FRAMEWORK: Phase 1 Define the Problem: Step 1 Understand Scope (region, product, channel, time); Step 2 "
            "Identify Objective (from, to, in by when; success; failure). Phase 2 Craft the Strategy: Step 3 Identify "
            "Framework; Step 4 Generate Options; Step 5 Prioritize Options (business benefit x ease: do first, plan "
            "carefully, quick win, avoid). Phase 3 Execute: Step 6 Implementation Charter (owner, stakeholders, "
            "incentives, capabilities, a leading metric weekly and a lagging metric monthly).")
    return _STF["text"]


class DeckIn(BaseModel):
    source: Literal["text", "case", "brief"]
    id: Optional[str] = Field(None, max_length=64)        # case answer id (source "case") or brief id (source "brief")
    title: str = Field("", max_length=120)
    audience: str = Field("", max_length=160)
    notes: str = Field("", max_length=6000)
    slides: int = Field(8, ge=dl.SLIDES_MIN, le=dl.SLIDES_MAX)
    tone: str = Field("clear", max_length=20)
    theme: str = Field("dark", max_length=10)


class DeckEdit(BaseModel):
    slides: Optional[list] = Field(None, max_length=dl.SLIDES_MAX)
    theme: Optional[Literal["dark", "light"]] = None
    title: Optional[str] = Field(None, max_length=120)


def _presenter(user: dict, k: dict) -> str:
    who = text(user.get("name"), 60)
    if not who:
        return ""
    return f"{who} · {k['consultant_title']}" if k.get("consultant_title") else who


# ------------------------------------------------------------------ source material ----
async def build_material(d, user: dict, body: DeckIn) -> dict:
    """What the deck is built from: {source, title, audience, ref_id, presenter, text (for the AI), data (for the
    fake)}. Raises 400 / 404 in plain words."""
    uid = str(user["_id"])
    k = await knowledge(d, user)
    head = ["Context: India. Money in Indian rupees (₹) with Indian grouping (₹1,50,000; ₹12 lakh; ₹40 crore)."]
    kb = system_block(k)
    if kb:
        head.append("ABOUT THE PRESENTER (use for positioning; never invent more):\n" + kb)
    base = {"presenter": _presenter(user, k), "author": text(user.get("name"), 60), "source": body.source}
    if body.source == "text":
        title = text(body.title, 120)
        if len(title) < 3:
            raise HTTPException(status_code=400, detail={"code": "title", "msg": "Give your deck a title."})
        notes = body.notes.strip()
        if len(notes) < 20:
            raise HTTPException(status_code=400, detail={"code": "notes", "msg": "Add your notes: a few lines on what the deck should say."})
        audience = text(body.audience, 160) or "Business owners and senior leaders"
        lines = [f"DECK TITLE: {title}", f"AUDIENCE: {audience}", *head, "",
                 "WHAT THE DECK SHOULD SAY (the presenter's own notes; their numbers are the only numbers you may use):",
                 notes, "", "SUGGESTED FLOW: title → the situation → the problem and why it matters → what we found → "
                 "what we recommend → how it works → plan and timeline → the next step."]
        return {**base, "title": title, "audience": audience, "ref_id": None, "text": "\n".join(lines),
                "data": {"notes": notes}}

    if not body.id:
        raise HTTPException(status_code=400, detail={"code": "pick", "msg": "Pick what to build the deck from."})
    if body.source == "case":
        a = await d.case_answers.find_one({"_id": body.id, "user_id": uid})
        c = await d.cases.find_one({"_id": a["case_id"]}) if a else None
        if not a or not c:
            raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "That case answer was not found."})
        title = text(body.title, 120) or f"{c['company']}: {c['title']}"
        audience = text(body.audience, 160) or f"Owner and leadership team of {c['company']}"
        facts = "\n".join(f"- {f}" for f in c.get("facts", []))
        lines = [f"DECK TITLE: {title}", f"AUDIENCE: {audience}", *head, "",
                 f"CLIENT: {c['company']} ({c['industry']}{', ' + c['city'] if c.get('city') else ''})",
                 "THE SITUATION:", c["situation"], "KEY FACTS:", facts, "THE CLIENT'S QUESTION:", c["question"], "",
                 "THE RECOMMENDATION (worked through the Strategic Thinking Framework):", model_answer_text(c["model_answer"]),
                 "", "THE PRESENTER'S OWN ANALYSIS (use its points where they add to the recommendation):", a["answer"][:3000],
                 "", "BUILD THE DECK ON THE STRATEGIC THINKING FRAMEWORK, in this order:", stf_block(), "",
                 "Map the steps to layouts: scope → two_column before_after (the client's words, then one precise "
                 "problem); objective → big_number (from, to, by when) with success and failure in the note; framework → "
                 "bullets (the lens and what it shows); options → table (source and option); prioritise → grid_2x2 with "
                 "y_axis 'Business benefit', x_axis 'Ease of doing it', cells Plan carefully, Do first, Avoid, Quick win, "
                 "and highlight the Do first cell; charter → steps or table (owner, first action, weekly leading metric, "
                 "monthly lagging metric); then closing with one clear next step. Drop or merge steps to fit the slide count."]
        return {**base, "title": title, "audience": audience, "ref_id": body.id, "text": "\n".join(lines),
                "data": {"case": c, "answer": a["answer"]}}

    b = await d.briefs.find_one({"_id": body.id, "user_id": uid})
    if not b:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "That Meeting Brief was not found."})
    co = b["input"]["company"]
    title = text(body.title, 120) or f"{co}: a first conversation"
    audience = text(body.audience, 160) or (b["input"].get("meeting_with") or f"Leadership team of {co}")
    news = "\n".join(f"- {n['title']} ({n.get('source', '')}): {n.get('why', '')}" for n in b.get("news") or [])
    probs = "\n".join(f"- {p['problem']}: {p.get('why', '')}" for p in b.get("problems") or [])
    qs = "\n".join(f"- {q}" for q in b.get("questions") or [])
    lines = [f"DECK TITLE: {title}", f"AUDIENCE: {audience}", *head, "",
             f"MEETING PURPOSE: {b['input'].get('purpose') or 'First conversation'}", f"ABOUT {co.upper()}:", b.get("about") or "",
             "RECENT NEWS:", news or "- none", "LIKELY CHALLENGES:", probs, "QUESTIONS FOR TODAY:", qs,
             f"OPENING: {b.get('opening') or ''}", "",
             "SUGGESTED FLOW: title → what we understand about you → what's changing in your business → challenges "
             "companies like yours face → how I work with clients → questions for today → a next step. Present the "
             "challenges as likely, to be checked in the meeting, not as facts."]
    return {**base, "title": title, "audience": audience, "ref_id": body.id, "text": "\n".join(lines), "data": {"brief": b}}


def _prompt(m: dict, n: int, tone: str) -> str:
    return (f"{m['text']}\n\nTONE: {TONE_KEYS[tone]['how']}\n\nWrite a {n}-slide deck from this material.\n\n"
            f"{_layout_guide(n)}")


# ------------------------------------------------------------------ the deterministic fake (tests and QA) ----
def _c(s: str, key: str) -> str:
    return dl._fit_limit(dl.clean_text(s), dl.LIMITS[key], False, "")


def _sentences(s: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", s or "") if len(x.strip()) > 3]


_NUM = re.compile(r"₹\s?[\d][\d,.]*(?:\s?(?:lakh|crore|cr|L|K))?|\d+(?:\.\d+)?\s?%|\d+(?:\.\d+)?x\b")


def _numbers(s: str) -> list[str]:
    out = []
    for m in _NUM.finditer(s or ""):
        v = m.group(0).strip()
        if v not in out:
            out.append(v)
    return out


def _pad(xs: list, n: int, fill: list) -> list:
    out = [x for x in xs if x]
    for f in fill:
        if len(out) >= n:
            break
        if f not in out:
            out.append(f)
    return out


def _fake_slides(m: dict) -> list[dict]:
    """Middle slides in order of importance, built only from the material."""
    d = m["data"]
    later = [
        {"layout": "section", "title": "What we recommend", "accent": "recommend",
         "subtitle": "The one move to start with, and how we will know it is working."},
        {"layout": "two_column", "kicker": "Two ways", "title": "Two ways to run the next 90 days", "style": "compare",
         "left": {"heading": "You run it", "points": ["Your team owns every step.", "Lower cost, slower start."]},
         "right": {"heading": "We run it together", "points": ["A weekly review with your team.", "I own the method; you own the results."]}},
        {"layout": "bullets", "kicker": "Risks", "title": "What could slow us down, and the fix", "bullets": [
            "Data is missing: we start with simple weekly numbers.", "Everything feels urgent: we rank by benefit and ease.",
            "The team is busy: one owner, one hour a week."]},
    ]
    if m["source"] == "case":
        c, ma = d["case"], d["case"]["model_answer"]
        o = ma["objective"]
        said = re.findall(r"[\"“]([^\"”]+)[\"”]", c["question"]) or [ma["scope_before"]]
        def stat(v: str, label: str) -> dict:
            nums = _numbers(v)
            return {"value": _c(nums[0] if nums else v, "stat_value"), "label": _c(label, "stat_label")}
        opts = ma["options"]
        return [
            {"layout": "agenda", "kicker": "Today", "title": "What we will cover today", "items": [
                "Where you are today", "The real problem", "What we found", "Options we considered", "What to do first",
                "How we run it"]},
            {"layout": "two_column", "kicker": "Scope", "title": "From a feeling to one clear problem", "style": "before_after",
             "left": {"heading": "What you said", "points": [_c(ma["scope_before"], "col_point"), _c(_sentences(c["situation"])[0], "col_point")]},
             "right": {"heading": "The problem, scoped", "points": [_c(x, "col_point") for x in _sentences(ma["scope_after"])[:3]] +
                       ([_c(c["facts"][0], "col_point")] if len(_sentences(ma["scope_after"])) < 2 else [])}},
            {"layout": "big_number", "kicker": "Objective", "title": _c(f"From {o['from']} to {o['to']} in {o['by']}", "title"),
             "stats": [stat(o["from"], f"Today: {o['from']}"), stat(o["to"], f"Goal: {o['to']}"), stat(o["by"], "To get there")],
             "note": _c(f"Failure: {ma['failure']}", "stat_note")},
            {"layout": "bullets", "kicker": "What we found", "title": _c(ma["framework"].split(":")[0], "title"),
             "bullets": [_c(x, "bullet") for x in ([ma["framework_why"]] + _sentences(ma["finding"]) + c.get("facts", []))[:5]]},
            {"layout": "table", "kicker": "Options", "title": "Five places we looked for options",
             "columns": ["Source", "The option"], "rows": [[_c(x["source"], "td"), _c(x["option"], "td")] for x in opts[:5]]},
            {"layout": "grid_2x2", "kicker": "Prioritise", "title": "Start with the clear do-first", "accent": "do-first",
             "y_axis": "Business benefit", "x_axis": "Ease of doing it", "highlight": 1, "cells": [
                {"title": "Plan carefully", "text": _c(opts[-1]["option"], "cell_text")},
                {"title": "Do first", "text": _c(ma["do_first"], "cell_text")},
                {"title": "Avoid", "text": "Spreading effort across every idea at once."},
                {"title": "Quick win", "text": _c(opts[1]["option"] if len(opts) > 1 else opts[0]["option"], "cell_text")}]},
            {"layout": "steps", "kicker": "How we run it", "title": "Who owns it and what we measure", "steps": [
                {"title": "Name the owner", "text": _c(ma["charter"]["owner"], "step_text")},
                {"title": "Start this week", "text": _c(ma["do_first"], "step_text")},
                {"title": "Track every week", "text": _c(ma["charter"]["leading"], "step_text")},
                {"title": "Review every month", "text": _c(ma["charter"]["lagging"], "step_text")}]},
            {"layout": "quote", "kicker": "In your words", "quote": _c(said[0], "quote"), "by": _c(f"{c['company']}", "quote_by")},
            {"layout": "bullets", "kicker": "Success", "title": "How we will know it worked", "bullets": [
                _c(f"Success: {ma['success']}", "bullet"), _c(f"Failure: {ma['failure']}", "bullet"),
                _c(f"Weekly: {ma['charter']['leading']}", "bullet")]},
        ] + later
    if m["source"] == "brief":
        b = d["brief"]
        co = b["input"]["company"]
        probs = b.get("problems") or []
        about = _pad([_c(x, "bullet") for x in _sentences(b.get("about") or "")], 3,
                     [f"{co} is the company we are meeting.", "We have read what is public about the business.",
                      "Today is about listening first."])
        news = [_c(n["title"], "bullet") for n in b.get("news") or []]
        qs = _pad([_c(q, "bullet") for q in b.get("questions") or []], 3,
                  ["What does a great year look like?", "What is slowing that down?", "What have you tried?"])
        return [
            {"layout": "agenda", "kicker": "Today", "title": "What I would like to cover today", "items": [
                "What we understand about you", "What is changing", "Challenges to check", "How I work", "Your questions"]},
            {"layout": "bullets", "kicker": "About you", "title": _c(f"What we understand about {co}", "title"), "bullets": about[:5]},
            {"layout": "bullets", "kicker": "What is changing", "title": "What is changing in your business",
             "bullets": _pad(news, 3, ["Your market is moving fast.", "Customers expect more for less.",
                                       "Good people are harder to keep."])[:5]},
            {"layout": "table", "kicker": "To check today", "title": "Challenges companies like yours often face",
             "columns": ["Likely challenge", "Why we think so"],
             "rows": [[_c(p["problem"], "td"), _c(p.get("why", ""), "td")] for p in probs[:5]] or [["[add challenge]", "[add reason]"]]},
            {"layout": "steps", "kicker": "How I work", "title": "How I work with clients", "steps": [
                {"title": "Listen first", "text": "One conversation to understand where you want to be."},
                {"title": "Find the real problem", "text": "Turn the feeling into one clear problem."},
                {"title": "Agree what success is", "text": "From, to and by when, in numbers."},
                {"title": "Run it together", "text": "One owner, weekly numbers, a monthly review."}]},
            {"layout": "bullets", "kicker": "Questions", "title": "Questions I would like to ask you", "bullets": qs[:5]},
            {"layout": "quote", "kicker": "Where I would start", "quote": _c(b.get("opening") or f"I would love to hear what {co} is focused on this year.", "quote"),
             "by": ""},
            {"layout": "big_number", "kicker": "The number that matters", "title": "One number to agree on today",
             "stats": [{"value": "[add figure]", "label": "The result you want in 90 days"}]},
            {"layout": "grid_2x2", "kicker": "Prioritise", "title": "How we would pick what to do first", "accent": "first",
             "y_axis": "Business benefit", "x_axis": "Ease of doing it", "highlight": 1, "cells": [
                {"title": "Plan carefully", "text": "Big, slower changes."}, {"title": "Do first", "text": "Big benefit and easy to start."},
                {"title": "Avoid", "text": "Hard work for little gain."}, {"title": "Quick win", "text": "Small, easy fixes."}]},
        ] + later
    notes = d["notes"]
    sents = [_c(x, "bullet") for x in _sentences(notes)]
    nums = _numbers(notes)
    stats = [{"value": _c(v, "stat_value"), "label": _c(next((s for s in _sentences(notes) if v in s), v), "stat_label")}
             for v in nums[:3]] or [{"value": "[add figure]", "label": "The number that matters most"}]
    head = sents[:5]
    rest = sents[5:] or sents[-2:]
    return [
        {"layout": "agenda", "kicker": "Today", "title": "What we will cover today", "items": [
            "Where things stand", "What we found", "What we recommend", "How we get there", "The next step"]},
        {"layout": "bullets", "kicker": "Where things stand", "title": "What we know today",
         "bullets": _pad(head, 3, ["[add a point from your notes]", "[add a second point]", "[add a third point]"])},
        {"layout": "big_number", "kicker": "The numbers", "title": "The numbers that matter most", "stats": stats},
        {"layout": "two_column", "kicker": "Before and after", "title": "Where we are and where we want to be",
         "style": "before_after",
         "left": {"heading": "Today", "points": _pad([_c(x, "col_point") for x in _sentences(notes)[:2]], 2, ["[add today]", "[add more]"])},
         "right": {"heading": "After", "points": _pad([_c(x, "col_point") for x in _sentences(notes)[2:4]], 2, ["[add the goal]", "[add more]"])}},
        {"layout": "steps", "kicker": "The plan", "title": "How we get there, step by step", "steps": [
            {"title": "Agree the goal", "text": "From, to and by when, in numbers."},
            {"title": "Fix the biggest leak", "text": _c(rest[0] if rest else "Start where the money is lost.", "step_text")},
            {"title": "Measure every week", "text": "One number, every week, one owner."},
            {"title": "Review and decide", "text": "A monthly review to keep, change or stop."}]},
        {"layout": "grid_2x2", "kicker": "Prioritise", "title": "Start with what is big and easy", "accent": "big and easy",
         "y_axis": "Business benefit", "x_axis": "Ease of doing it", "highlight": 1, "cells": [
            {"title": "Plan carefully", "text": "Big changes that need time and money."},
            {"title": "Do first", "text": _c(rest[0] if rest else "The biggest, easiest fix.", "cell_text")},
            {"title": "Avoid", "text": "Hard work for little gain."}, {"title": "Quick win", "text": "Small fixes we can make this week."}]},
        {"layout": "table", "kicker": "Options", "title": "The options side by side", "columns": ["Option", "Benefit", "Effort"],
         "rows": [["Fix the biggest leak", "High", "Low"], ["Change the process", "High", "Medium"], ["Do nothing", "None", "None"]]},
        {"layout": "quote", "kicker": "In short", "quote": _c(_sentences(notes)[0] if _sentences(notes) else notes, "quote"),
         "by": ""},
    ] + later


def fake_deck(m: dict, n: int) -> dict:
    middle = _fake_slides(m)
    extra = [{"layout": "bullets", "kicker": "More detail", "title": f"More detail, part {i + 1}",
              "bullets": ["[add a point]", "[add a point]", "[add a point]"]} for i in range(max(0, n - 2 - len(middle)))]
    middle = (middle + extra)[:n - 2]
    first = {"layout": "title", "kicker": "Proposal" if m["source"] != "brief" else "First conversation",
             "title": _c(m["title"], "cover_title"), "subtitle": _c(f"Prepared for {m['audience']}", "subtitle"),
             "notes": "Thank them for their time and say what they will have by the end of the meeting."}
    last = {"layout": "closing", "kicker": "Next step", "title": "Let's agree the first step", "accent": "first step",
            "text": "A short call this week to agree the scope, the owner and the first number we will track.",
            "action": "A 30-minute call this week to agree the scope"}
    return {"slides": [first, *middle, last]}


# ------------------------------------------------------------------ checking and rendering ----
def check_ai(raw, m: dict) -> dict:
    """Check the AI's deck against the layouts and limits. A wrong shape raises llm.LLMError (the go is given back)."""
    if isinstance(raw, dict) and "slides" not in raw and isinstance(raw.get("deck"), dict):
        raw = raw["deck"]
    try:
        deck = dl.clean_deck(raw, strict=False)
    except dl.BadDeck as e:
        log.warning("deck from the AI rejected: %s", e)
        raise llm.LLMError(f"deck: {e}") from e
    deck["slides"][0]["presenter"] = dl._fit_limit(m.get("presenter") or "", dl.LIMITS["presenter"], False, "")
    return deck


def render_files(deck: dict, *, theme: str, author: str, title: str) -> tuple[bytes, bytes]:
    slides = dl.layout_deck(deck, theme=theme, author=author)
    pptx = render_pptx(slides, title=title, author=author, notes=[s.get("notes", "") for s in deck["slides"]])
    pdf = render_pdf(slides, title=title, author=author)
    return pptx, pdf


def _slug(title: str) -> str:
    s = title.replace("₹", "Rs ").replace("—", "-").replace("–", "-")
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:60] or "deck"


async def _store(d, *, uid: str, deck: dict, theme: str, author: str, title: str) -> dict:
    pptx, pdf = await run_in_threadpool(render_files, deck, theme=theme, author=author, title=title)
    files, saved = {}, []
    try:
        for kind, data in (("pptx", pptx), ("pdf", pdf)):
            bid = await media.save_blob(d, user_id=uid, kind="deck", content_type=CTYPE[kind], data=data,
                                        name=f"{_slug(title)}.{kind}")
            saved.append(bid)
            files[kind] = {"blob_id": bid, "size": len(data)}
    except Exception:
        for bid in saved:
            await media.delete_blob(d, bid)
        raise
    return files


def _files(doc: dict) -> dict:
    out = {}
    for kind, f in (doc.get("files") or {}).items():
        out[kind] = {"url": f"/api/decks/{doc['_id']}/file?kind={kind}", "name": f"{_slug(doc['title'])}.{kind}",
                     "size": f.get("size")}
    return out


def _summary(doc: dict) -> dict:
    return {"id": doc["_id"], "title": doc["title"], "source": doc.get("source"), "slides": doc.get("slides"),
            "theme": doc.get("theme", "dark"), "created_at": iso(doc["created_at"]),
            "updated_at": iso(doc.get("updated_at") or doc["created_at"])}


def _public(doc: dict) -> dict:
    deck = doc.get("deck")
    out = {**_summary(doc), "ref_id": doc.get("ref_id"), "audience": doc.get("audience"), "tone": doc.get("tone"),
           "author": doc.get("author") or "", "status": doc.get("status", "ready"), "edited_at": iso(doc.get("edited_at")),
           "deck": deck, "layout": None, "files": _files(doc), "canvas": {"w": dl.W, "h": dl.H}}
    if deck:
        out["layout"] = dl.layout_deck(deck, theme=out["theme"], author=out["author"])
    return out


# ------------------------------------------------------------------ routes ----
@router.get("/options")
async def options():
    return {"themes": THEMES, "tones": [{"key": t["key"], "label": t["label"]} for t in TONES],
            "slides": {"min": dl.SLIDES_MIN, "max": dl.SLIDES_MAX, "default": 8}, "limits": dl.LIMITS,
            "layouts": list(dl.LAYOUTS)}


@router.get("/sources")
async def sources(user: dict = Depends(user_dep())):
    """What a deck can be built from: the member's case answers and Meeting Briefs."""
    d = db()
    uid = str(user["_id"])
    answers = []
    async for a in d.case_answers.find({"user_id": uid}).sort("at", -1).limit(30):
        c = await d.cases.find_one({"_id": a["case_id"]}, {"title": 1, "company": 1})
        if c:
            answers.append({"id": a["_id"], "case_id": a["case_id"], "title": c["title"], "company": c["company"],
                            "overall": a.get("overall"), "at": iso(a["at"])})
    briefs = [{"id": b["_id"], "company": b["input"]["company"], "at": iso(b["at"])}
              async for b in d.briefs.find({"user_id": uid}, {"input.company": 1, "at": 1}).sort("at", -1).limit(30)]
    return {"answers": answers, "briefs": briefs}


@router.post("")
async def make(body: DeckIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    tone = body.tone if body.tone in TONE_KEYS else "clear"
    theme = body.theme if body.theme in dl.THEME_KEYS else "dark"

    async def work(plan: str):
        m = await build_material(d, user, body)
        raw = await llm.complete_json(task="deck_writer", system=SYSTEM, prompt=_prompt(m, body.slides, tone),
                                      fake=lambda: fake_deck(m, body.slides), model="strong", max_tokens=7000,
                                      timeout=150)
        deck = check_ai(raw, m)
        files = await _store(d, uid=uid, deck=deck, theme=theme, author=m["author"], title=m["title"])
        now = utcnow()
        now = now.replace(microsecond=now.microsecond // 1000 * 1000)       # what Mongo keeps
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "source": body.source, "ref_id": m["ref_id"], "title": m["title"],
               "audience": m["audience"], "tone": tone, "theme": theme, "author": m["author"], "deck": deck,
               "slides": len(deck["slides"]), "status": "ready", "rev": 1, "files": files, "created_at": now,
               "updated_at": now}
        await d.decks.insert_one(doc)
        await events.track(d, "deck_made", user_id=uid, props={"source": body.source, "slides": doc["slides"], "theme": theme})
        return _public(doc)
    return await run_metered(d, user, "presentation", work)


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    rows = [_summary(x) async for x in db().decks.find({"user_id": str(user["_id"])}, {"deck": 0})
            .sort("created_at", -1).limit(50)]
    return {"items": rows}


async def _own(deck_id: str, user: dict) -> dict:
    doc = await db().decks.find_one({"_id": deck_id, "user_id": str(user["_id"])})
    if not doc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Deck not found."})
    return doc


@router.get("/{deck_id}")
async def one(deck_id: str, user: dict = Depends(user_dep())):
    return _public(await _own(deck_id, user))


@router.patch("/{deck_id}")
async def edit(deck_id: str, body: DeckEdit, user: dict = Depends(user_dep())):
    """Change slide text, the look (Dark / Light) or the deck title, and make the files again. Free: no plan use."""
    d = db()
    doc = await _own(deck_id, user)
    if not doc.get("deck"):
        raise HTTPException(status_code=409, detail={"code": "old_deck", "msg": "This deck can't be changed. Make it again."})
    deck, what = doc["deck"], []
    if body.slides is not None:
        old = deck["slides"]
        if len(body.slides) != len(old) or any(not isinstance(s, dict) or s.get("layout") != o["layout"]
                                               for s, o in zip(body.slides, old)):
            raise HTTPException(status_code=400, detail={"code": "shape", "msg": "Slides can't be added, removed or moved here."})
        try:
            deck = dl.clean_deck({"slides": body.slides}, strict=True)
        except dl.BadDeck as e:
            raise HTTPException(status_code=400, detail={"code": "slide", "msg": str(e)})
        what.append("text")
    theme = body.theme or doc.get("theme", "dark")
    if theme != doc.get("theme", "dark"):
        what.append("theme")
    title = doc["title"]
    if body.title is not None:
        t = text(body.title, 120)
        if len(t) < 3:
            raise HTTPException(status_code=400, detail={"code": "title", "msg": "Give your deck a title."})
        if t != title:
            title = t
            what.append("title")
    if not what:
        return _public(doc)
    files = await _store(d, uid=doc["user_id"], deck=deck, theme=theme, author=doc.get("author") or "", title=title)
    now = utcnow()
    res = await d.decks.update_one({"_id": doc["_id"], "rev": doc.get("rev", 1)},
                                   {"$set": {"deck": deck, "theme": theme, "title": title, "files": files,
                                             "slides": len(deck["slides"]), "updated_at": now,
                                             **({"edited_at": now} if "text" in what or "title" in what else {})},
                                    "$inc": {"rev": 1}})
    if not res.modified_count:                       # someone saved in between: keep theirs
        for f in files.values():
            await media.delete_blob(d, f["blob_id"])
        raise HTTPException(status_code=409, detail={"code": "changed", "msg": "This deck changed while you were saving. Open it again."})
    for f in (doc.get("files") or {}).values():
        await media.delete_blob(d, f.get("blob_id"))
    await events.track(d, "deck_edited", user_id=doc["user_id"], props={"what": ",".join(what)})
    return _public(await d.decks.find_one({"_id": doc["_id"]}))


@router.delete("/{deck_id}")
async def remove(deck_id: str, user: dict = Depends(user_dep())):
    d = db()
    doc = await _own(deck_id, user)
    for f in (doc.get("files") or {}).values():
        await media.delete_blob(d, f.get("blob_id"))
    await d.decks.delete_one({"_id": doc["_id"]})
    return {"ok": True}


@router.get("/{deck_id}/file")
async def file(deck_id: str, kind: Literal["pptx", "pdf"] = Query("pdf"), inline: bool = Query(False),
               user: dict = Depends(user_dep())):
    """The PowerPoint or PDF file, with a proper file name. Owner only (the blobs themselves are owner-only too)."""
    doc = await _own(deck_id, user)
    f = (doc.get("files") or {}).get(kind)
    b = await media.get_blob(db(), f["blob_id"]) if f else None
    if not b:
        raise HTTPException(status_code=410, detail={"code": "gone", "msg": "This file is no longer available. Make the deck again."})
    disp = "inline" if inline and kind == "pdf" else "attachment"
    return Response(bytes(b["data"]), media_type=CTYPE[kind],
                    headers={"Content-Disposition": f'{disp}; filename="{_slug(doc["title"])}.{kind}"',
                             "Cache-Control": "private, no-cache"})
