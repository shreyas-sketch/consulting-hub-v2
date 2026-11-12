"""The client proposal from a framework activity, in the structure of Akshat's Growth Compass proposal (Nov 2026):

  cover · contents · 01 Where we started · 02 The real problem · 03 The framework · 04 Your diagnosis
  (the numbers, the verdict, the lever) · 05 Why nothing moved · 06 Where to focus · 07 Your 90-day plan ·
  08 What it's worth · 09 Next steps

The AI writes the words and the numbers (JSON below); the page renders it as a designed document (React
`ProposalDoc`), with the framework's own picture drawn from the case and the member's answers, and `markdown` is the
plain version for copying. No fee section: the proposal sells the diagnosis and the plan.
"""
from __future__ import annotations

from typing import Any, Optional

import llm

from .common import as_dict, as_list, strip_providers, text, text_list

VERSION = 2

SECTIONS = [  # (anchor, title) in page order; the page and the markdown share them
    ("situation", "Where we started"), ("problem", "The real problem"), ("framework", "The framework"),
    ("diagnosis", "Your diagnosis"), ("why", "Why nothing moved"), ("focus", "Where to focus"),
    ("plan", "Your 90-day plan"), ("impact", "What it's worth"), ("next", "Next steps"),
]

SHAPE = (
    "Write the proposal as a short, confident story to the client, in the consultant's voice ('I', 'you'), in this "
    "structure. Keep every line short: these are headlines and captions on designed pages, not paragraphs.\n"
    "tagline: one line under the framework's name on the cover, e.g. 'A diagnostic of your business, and a 90-day "
    "plan to grow it.'\n"
    "client_descriptor: 3-8 words on what the client does, e.g. 'Online coaching for career switchers'.\n"
    "1. WHERE WE STARTED. hook: the question the client brought, in their own words, split in two: quote_start and "
    "quote_end (e.g. 'I am doing everything right.' / 'Why am I not growing?'). situation: 2-4 short sentences. "
    "key_facts: exactly 3 big numbers from the case, each value (short: '3 years', '₹18L', '0%') and label. tried: up "
    "to 3 things the client already tried (title, one-line detail, result such as 'No change in revenue'); [] if the "
    "case says nothing was tried.\n"
    "2. THE REAL PROBLEM. reframe: muted (what it is not, e.g. 'You weren't doing the wrong things.'), headline and "
    "accent (one sentence split in two, e.g. 'You were doing the right things' / 'for the wrong problem.'). "
    "problem: 2-3 sentences. possibilities: the 2 or 3 things it could be, each tag (one word) and statement (short).\n"
    "3. YOUR DIAGNOSIS. diagnosis.headline and accent (e.g. 'Two questions.' / 'Two numbers.'); questions: 2 or 3, "
    "each question, value (the big number, short) and unit (a few words); note: one line on checking the numbers. "
    "verdict: the result in 1-3 words (e.g. 'Zone 3', 'Red zone', 'Value fails'); verdict_line: one line (e.g. 'Low "
    "reach. Healthy conversion.'); verdict_text: 2 sentences; points: exactly 3 short findings, each title (e.g. 'Not "
    "the product', 'It's reach') and text.\n"
    "lever: headline and accent (e.g. 'Reach is' / 'the lever.'), text (2 sentences), chain: 3 or 4 steps that walk "
    "the client's own numbers to the result, each value (short), label and op (the operation to the next step, at most 12 characters, "
    "e.g. '× 2%'; '' on the last), insight (one line, e.g. 'Every 50 new people who see your offer is worth about ₹30,000.') and "
    "insight_basis (how that number was worked out).\n"
    "4. WHY NOTHING MOVED. why.intro (1-2 sentences); items: one per thing tried (or, if nothing was tried, the 2-3 "
    "moves an owner would usually make), each title, aimed_at (a few words), what_it_did, why_not (why the number "
    "did not move); bridge: one line, e.g. 'The fix isn't more effort. It's effort pointed at reach.'\n"
    "5. WHERE TO FOCUS. focus.headline and accent (one sentence split in two); text (one line); leave: 3-4 things to "
    "leave as they are (2-5 words each); invest: the one thing to put money and time into (1-2 words); invest_text (one line); "
    "channels: exactly 3, each name and text.\n"
    "6. YOUR 90-DAY PLAN. plan.intro (one line); metric (what the plan moves, 2-4 words, e.g. 'Target monthly reach'); baseline "
    "(today's level, e.g. 'Today: ~250 people a month see your offer'); phases: exactly 3 (Days 1-30, Days 31-60, "
    "Days 61-90), each days, name (1-2 words), headline (one line), detail (1-2 sentences), why (why it works, one "
    "sentence) and target (at most 8 characters, e.g. '~400', '₹1.8Cr').\n"
    "7. WHAT IT'S WORTH. impact.headline and accent (e.g. 'What reach' / 'is worth.'); text (1-2 sentences); "
    "main_label and cautious_label (the two cases, e.g. 'If conversion holds at 2%' / 'If it dips to 1.5%'); "
    "scenarios: 3 (today first), each label, sub (a few words) and value and cautious (whole rupees a year; cautious "
    "0 for today); highlights: exactly 3 big takeaways, each value and label; note: the assumptions, and that it is "
    "not a guarantee.\n"
    "8. NEXT STEPS. close: muted, headline and accent (the closing message in three parts, e.g. 'You don't need to "
    "rebuild your business.' / 'You need more people to discover' / 'what you've already built.'); next_steps: 4, "
    "each title, detail and when (e.g. 'Week 1', 'Day 1', 'Days 30, 60, 90').\n"
    "Use only numbers from the case and the analysis, or simple sums of them; say what is assumed. Plain words, no "
    "jargon, no hype, no emojis, no guarantees. No fees.\n"
    'JSON: {"tagline": "", "client_descriptor": "", "hook": {"quote_start": "", "quote_end": ""}, "situation": "", '
    '"key_facts": [{"value": "", "label": ""}], "tried": [{"title": "", "detail": "", "result": ""}], '
    '"reframe": {"muted": "", "headline": "", "accent": ""}, "problem": "", '
    '"possibilities": [{"tag": "", "statement": ""}], '
    '"diagnosis": {"headline": "", "accent": "", "questions": [{"question": "", "value": "", "unit": ""}], "note": "", '
    '"verdict": "", "verdict_line": "", "verdict_text": "", "points": [{"title": "", "text": ""}]}, '
    '"lever": {"headline": "", "accent": "", "text": "", "chain": [{"value": "", "label": "", "op": ""}], '
    '"insight": "", "insight_basis": ""}, '
    '"why": {"intro": "", "items": [{"title": "", "aimed_at": "", "what_it_did": "", "why_not": ""}], "bridge": ""}, '
    '"focus": {"headline": "", "accent": "", "text": "", "leave": [""], "invest": "", "invest_text": "", '
    '"channels": [{"name": "", "text": ""}]}, '
    '"plan": {"intro": "", "metric": "", "baseline": "", "phases": [{"days": "", "name": "", "headline": "", '
    '"detail": "", "why": "", "target": ""}]}, '
    '"impact": {"headline": "", "accent": "", "text": "", "main_label": "", "cautious_label": "", '
    '"scenarios": [{"label": "", "sub": "", "value": 0, "cautious": 0}], "highlights": [{"value": "", "label": ""}], '
    '"note": ""}, '
    '"close": {"muted": "", "headline": "", "accent": ""}, "next_steps": [{"title": "", "detail": "", "when": ""}]}'
)


def _t(v: Any, n: int) -> str:
    """One line of text cut at a word near n, never mid-word."""
    v = text(v, 100_000)
    if len(v) <= n:
        return v
    cut = v[:n].rsplit(" ", 1)[0].rstrip(" ,;:-(")
    return cut if len(cut) >= n // 2 else v[:n]


def _num(v: Any) -> Optional[int]:
    try:
        n = int(round(float(str(v).replace(",", "").replace("₹", "").strip())))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _rows(v: Any, fields: dict[str, int], n: int, need: str) -> list[dict]:
    """A list of small objects: each field cut to its length; rows without `need` dropped."""
    out = []
    for x in as_list(v):
        if not isinstance(x, dict):
            continue
        row = {f: _t(x.get(f), m) for f, m in fields.items()}
        if row.get(need):
            out.append(row)
        if len(out) >= n:
            break
    return out


def _split(v: Any, fields: dict[str, int]) -> dict:
    d = as_dict(v)
    return {f: _t(d.get(f), m) for f, m in fields.items()}


def clean(raw: Any) -> dict:
    """The AI's JSON → the proposal the page renders. Raises LLMError when the story is missing a part it needs."""
    r = as_dict(raw)
    dg, lv, wy, fc, pl, im = (as_dict(r.get(k)) for k in ("diagnosis", "lever", "why", "focus", "plan", "impact"))
    scen = []
    for s in as_list(im.get("scenarios"))[:4]:
        if isinstance(s, dict) and _t(s.get("label"), 40) and _num(s.get("value")):
            scen.append({"label": _t(s.get("label"), 40), "sub": _t(s.get("sub"), 80),
                         "value": _num(s.get("value")), "cautious": _num(s.get("cautious"))})
    p = {
        "v": VERSION,
        "tagline": _t(r.get("tagline"), 140),
        "client_descriptor": _t(r.get("client_descriptor"), 80),
        "hook": _split(r.get("hook"), {"quote_start": 120, "quote_end": 120}),
        "situation": _t(r.get("situation"), 700),
        "key_facts": _rows(r.get("key_facts"), {"value": 16, "label": 80}, 3, "value"),
        "tried": _rows(r.get("tried"), {"title": 40, "detail": 140, "result": 60}, 3, "title"),
        "reframe": _split(r.get("reframe"), {"muted": 120, "headline": 120, "accent": 120}),
        "problem": _t(r.get("problem"), 500),
        "possibilities": _rows(r.get("possibilities"), {"tag": 24, "statement": 120}, 3, "statement"),
        "diagnosis": {**_split(dg, {"headline": 60, "accent": 60, "note": 240, "verdict": 30, "verdict_line": 120,
                                    "verdict_text": 400}),
                      "questions": _rows(dg.get("questions"), {"question": 140, "value": 16, "unit": 40}, 3, "value"),
                      "points": _rows(dg.get("points"), {"title": 40, "text": 160}, 3, "title")},
        "lever": {**_split(lv, {"headline": 60, "accent": 60, "text": 400, "insight": 200, "insight_basis": 200}),
                  "chain": _rows(lv.get("chain"), {"value": 16, "label": 80, "op": 24}, 4, "value")},
        "why": {**_split(wy, {"intro": 300, "bridge": 160}),
                "items": _rows(wy.get("items"), {"title": 40, "aimed_at": 60, "what_it_did": 200, "why_not": 240}, 3,
                               "title")},
        "focus": {**_split(fc, {"headline": 80, "accent": 80, "text": 240, "invest": 30, "invest_text": 200}),
                  "leave": [_t(x, 60) for x in text_list(fc.get("leave"), 4, 400)],
                  "channels": _rows(fc.get("channels"), {"name": 40, "text": 140}, 3, "name")},
        "plan": {**_split(pl, {"intro": 200, "metric": 70, "baseline": 120}),
                 "phases": _rows(pl.get("phases"), {"days": 20, "name": 30, "headline": 100, "detail": 260,
                                                    "why": 220, "target": 16}, 3, "name")},
        "impact": {**_split(im, {"headline": 60, "accent": 60, "text": 300, "main_label": 60, "cautious_label": 60,
                                 "note": 400}),
                   "scenarios": scen,
                   "highlights": _rows(im.get("highlights"), {"value": 16, "label": 140}, 3, "value")},
        "close": _split(r.get("close"), {"muted": 120, "headline": 120, "accent": 120}),
        "next_steps": _rows(r.get("next_steps"), {"title": 50, "detail": 200, "when": 30}, 5, "title"),
    }
    missing = [n for n, ok in [
        ("hook", p["hook"]["quote_start"] or p["hook"]["quote_end"]), ("situation", p["situation"]),
        ("key_facts", len(p["key_facts"]) >= 2), ("reframe", p["reframe"]["headline"]),
        ("verdict", p["diagnosis"]["verdict"]), ("questions", p["diagnosis"]["questions"]),
        ("focus", p["focus"]["invest"] or p["focus"]["channels"]), ("phases", len(p["plan"]["phases"]) >= 2),
        ("next_steps", len(p["next_steps"]) >= 2)] if not ok]
    if missing:
        raise llm.LLMError(f"framework proposal: incomplete ({', '.join(missing)})")
    return strip_providers(p)


def _inr_short(n: Optional[int]) -> str:
    """₹18L, ₹1.2Cr: how the proposal writes big rupee numbers."""
    if not n:
        return ""
    if n >= 10_000_000:
        return f"₹{n / 10_000_000:.1f}Cr".replace(".0Cr", "Cr")
    if n >= 100_000:
        return f"₹{n / 100_000:.1f}L".replace(".0L", "L")
    return f"₹{n:,}"


def markdown(p: dict, fw_name: str, client: str, prepared_by: str, date: str) -> str:
    """The same proposal as plain Markdown, for copying into an email or a document."""
    L = [f"# {fw_name}", "", p["tagline"], "",
         f"Prepared for: {client}" + (f" ({p['client_descriptor']})" if p["client_descriptor"] else ""),
         f"Prepared by: {prepared_by}", f"Date: {date}", ""]
    h = p["hook"]
    L += ["## 1. Where we started", "", f"> “{h['quote_start']} {h['quote_end']}”".replace("  ", " "), "",
          p["situation"], ""]
    L += [f"- **{f['value']}** {f['label']}" for f in p["key_facts"]] + [""]
    if p["tried"]:
        L += ["What you had already tried:", ""] + [f"- **{t['title']}**: {t['detail']} ({t['result']})" for t in p["tried"]] + [""]
    rf = p["reframe"]
    L += ["## 2. The real problem", "", f"*{rf['muted']}* **{rf['headline']} {rf['accent']}**".strip(), "", p["problem"], ""]
    L += [f"- **{x['tag']}**: {x['statement']}" for x in p["possibilities"]] + [""]
    d = p["diagnosis"]
    L += ["## 3. Your diagnosis", "", f"**{d['headline']} {d['accent']}**".strip(), ""]
    L += [f"- {q['question']} **{q['value']}** {q['unit']}" for q in d["questions"]] + [""]
    if d["note"]:
        L += [d["note"], ""]
    L += [f"### {d['verdict']}: {d['verdict_line']}", "", d["verdict_text"], ""]
    L += [f"- **{x['title']}**: {x['text']}" for x in d["points"]] + [""]
    lv = p["lever"]
    if lv["chain"]:
        L += [f"### {lv['headline']} {lv['accent']}".strip(), "", lv["text"], "",
              " → ".join(f"{c['value']} {c['label']}" + (f" ({c['op']})" if c["op"] else "") for c in lv["chain"]), ""]
        if lv["insight"]:
            L += [f"**{lv['insight']}** {lv['insight_basis']}".strip(), ""]
    w = p["why"]
    if w["items"]:
        L += ["## 4. Why nothing moved", "", w["intro"], ""]
        L += [f"- **{i['title']}** (aimed at {i['aimed_at']}): {i['what_it_did']} {i['why_not']}".strip() for i in w["items"]]
        L += ["", f"**{w['bridge']}**" if w["bridge"] else "", ""]
    f = p["focus"]
    L += ["## 5. Where to focus", "", f"**{f['headline']} {f['accent']}**".strip(), "", f["text"], ""]
    if f["leave"]:
        L += ["Leave as it is: " + ", ".join(f["leave"]) + ".", ""]
    L += [f"Invest here: **{f['invest']}**. {f['invest_text']}".strip(), ""]
    L += [f"{i}. **{c['name']}**: {c['text']}" for i, c in enumerate(f["channels"], 1)] + [""]
    pl = p["plan"]
    L += ["## 6. Your 90-day plan", "", pl["intro"], "", pl["baseline"], ""]
    for ph in pl["phases"]:
        L += [f"**{ph['days']}: {ph['name']}**. {ph['headline']}", "", ph["detail"],
              *([f"Why it works: {ph['why']}"] if ph["why"] else []),
              *([f"{pl['metric'] or 'Target'}: **{ph['target']}**"] if ph["target"] else []), ""]
    im = p["impact"]
    if im["scenarios"]:
        L += [f"## 7. {im['headline']} {im['accent']}".strip(), "", im["text"], ""]
        for s in im["scenarios"]:
            row = f"- **{s['label']}** ({s['sub']}): {_inr_short(s['value'])}" if s["sub"] else f"- **{s['label']}**: {_inr_short(s['value'])}"
            if s["cautious"]:
                row += f"; {im['cautious_label'] or 'cautious case'}: {_inr_short(s['cautious'])}"
            L.append(row)
        L += [""] + [f"- **{x['value']}** {x['label']}" for x in im["highlights"]] + ["", f"*{im['note']}*" if im["note"] else "", ""]
    c = p["close"]
    L += ["## 8. Next steps", "", f"*{c['muted']}* **{c['headline']} {c['accent']}**".strip(), ""]
    L += [f"{i}. **{s['title']}** ({s['when']}): {s['detail']}" for i, s in enumerate(p["next_steps"], 1)]
    return "\n".join(x for x in L if x is not None).replace("\n\n\n", "\n\n").strip()


def fake(fw_name: str, client: str, read: str) -> dict:
    """Test mode: a complete sample in the same shape (never shown as a real result)."""
    return {
        "tagline": "A diagnostic of your business, and a 90-day plan to grow it.",
        "client_descriptor": "Sample client (test mode)",
        "hook": {"quote_start": "I am doing everything right.", "quote_end": "Why am I not growing?"},
        "situation": f"{client[:200]} brought me this question. This is a sample proposal made in test mode.",
        "key_facts": [{"value": "3 years", "label": "in business"}, {"value": "₹18L", "label": "a year"},
                      {"value": "0%", "label": "growth"}],
        "tried": [{"title": "More content", "detail": "Posting more often.", "result": "No change in revenue"}],
        "reframe": {"muted": "You weren't doing the wrong things.", "headline": "You were doing the right things",
                    "accent": "for the wrong problem."},
        "problem": "It is almost always one of two things.",
        "possibilities": [{"tag": "Reach", "statement": "Not enough people see the offer."},
                          {"tag": "Conversion", "statement": "The people who see it don't buy."}],
        "diagnosis": {"headline": "Two questions.", "accent": "Two numbers.",
                      "questions": [{"question": "How many people see the offer each month?", "value": "250", "unit": "a month"},
                                    {"question": "How many of them buy?", "value": "2%", "unit": "about 1 in 50"}],
                      "note": "We confirm both numbers in week one.", "verdict": "Sample verdict",
                      "verdict_line": "Sample line.", "verdict_text": read[:300] or "Sample reading.",
                      "points": [{"title": "Not the product", "text": "Customers are happy."},
                                 {"title": "Not the price", "text": "Buyers buy."},
                                 {"title": "It's reach", "text": "Too few people see it."}]},
        "lever": {"headline": "Reach is", "accent": "the lever.", "text": "Follow the numbers through.",
                  "chain": [{"value": "250", "label": "see the offer", "op": "× 2%"},
                            {"value": "5", "label": "buy a month", "op": "× 12"},
                            {"value": "60", "label": "a year", "op": "× ₹30K"},
                            {"value": "₹18L", "label": "a year", "op": ""}],
                  "insight": "Every 50 new people is worth about ₹30,000.", "insight_basis": "₹18L ÷ 60."},
        "why": {"intro": "Each move was sensible.",
                "items": [{"title": "More content", "aimed_at": "existing followers", "what_it_did": "Reached the same people.",
                           "why_not": "It didn't widen the circle."}],
                "bridge": "The fix isn't more effort. It's effort pointed at reach."},
        "focus": {"headline": "Every rupee spent fixing what works", "accent": "is a rupee wasted.",
                  "text": "Leave the working parts alone.", "leave": ["Your product", "Your offer", "Your pricing"],
                  "invest": "Reach", "invest_text": "More of the right people discovering you.",
                  "channels": [{"name": "Stories", "text": "Results told by customers."},
                               {"name": "Referrals", "text": "A reason to spread the word."},
                               {"name": "Partnerships", "text": "A new audience."}]},
        "plan": {"intro": "Three moves, in sequence.", "metric": "Target monthly reach",
                 "baseline": "Today: ~250 people a month",
                 "phases": [{"days": "Days 1-30", "name": "Stories", "headline": "One story a day.", "detail": "Real results.",
                             "why": "Fast and cheap.", "target": "~400"},
                            {"days": "Days 31-60", "name": "Referrals", "headline": "Customers bring customers.",
                             "detail": "A reward for each referral.", "why": "They already believe in you.", "target": "500+"},
                            {"days": "Days 61-90", "name": "Partnership", "headline": "Borrow one audience.",
                             "detail": "One partner, one free session.", "why": "Trust, introduced.", "target": "600+"}]},
        "impact": {"headline": "What reach", "accent": "is worth.", "text": "Revenue at different levels of reach.",
                   "main_label": "If conversion holds", "cautious_label": "If it dips",
                   "scenarios": [{"label": "Today", "sub": "~250 a month", "value": 1_800_000, "cautious": 0},
                                 {"label": "2× reach", "sub": "~500 a month", "value": 3_600_000, "cautious": 2_700_000},
                                 {"label": "3× reach", "sub": "~750 a month", "value": 5_400_000, "cautious": 4_050_000}],
                   "highlights": [{"value": "2× revenue", "label": "if reach doubles"}, {"value": "+₹9L", "label": "cautious case"},
                                  {"value": "Monthly", "label": "tracking"}],
                   "note": "Sample projections, not a guarantee."},
        "close": {"muted": "You don't need to rebuild your business.", "headline": "You need more people to discover",
                  "accent": "what you've already built."},
        "next_steps": [{"title": "Confirm the numbers", "detail": "Check the records.", "when": "Week 1"},
                       {"title": "Go live", "detail": "Phase 1 begins.", "when": "Day 1"},
                       {"title": "Review every 30 days", "detail": "Side by side.", "when": "Days 30, 60, 90"}],
    }
