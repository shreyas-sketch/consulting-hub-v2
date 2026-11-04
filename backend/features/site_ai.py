"""Website Builder AI: the first build (every section from what the hub knows about the member) and edit by prompt
(Owner Desk's patch pattern: the AI rewrites only the one section the member points at, and nothing changes until the
member presses "Use this").

Never invented: proof comes only from the member's own career stories (or placeholders they fill), fees only from their
Offer Card, links only from their contact details. Any number the AI writes that isn't in the member's own facts (or in
their request) is replaced with a [number] placeholder before it is shown.
"""
from __future__ import annotations

import copy as _copy
import json
import re

import llm
from util import inr

from .common import text
from .site_model import PLACEHOLDER, SECTIONS, SIX_STEPS, normalize, strings_of

RULES = (
    "Never mention, name or hint at any AI provider or model: you are the hub's own website writer. "
    "You write consulting websites for experienced Indian professionals (15-35 years in jobs) who are starting out as "
    "independent consultants. Write as the consultant, in the first person ('I'), to a business owner or senior leader. "
    "Plain, warm, confident English. Short sentences, one idea per sentence. No buzzwords, no hype, no emojis, no "
    "exclamation marks. Never promise results or income. Use ONLY the facts given. Never invent clients, company names, "
    "numbers, years, awards, certifications, testimonials or results. Where a fact is needed and not given, write a "
    "short placeholder in square brackets telling the consultant what to add, for example [years in your industry]."
)

# ───────────────────────── the member's facts ─────────────────────────


async def _latest(coll, uid: str, n: int) -> list[dict]:
    """Newest first, whatever the other module calls its date field."""
    try:
        rows = [r async for r in coll.find({"user_id": uid}).limit(200)]
    except Exception:  # noqa: BLE001 — another builder's collection: never break the website on it
        return []

    def when(r):
        for k in ("updated_at", "at", "created_at"):
            if r.get(k) is not None:
                return str(r[k])
        return ""
    return sorted(rows, key=when, reverse=True)[:n]


def fee_text(f, t) -> str:
    def num(v):
        try:
            v = int(float(v))
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None
    a, b = num(f), num(t)
    if a and b and b > a:
        return f"{inr(a)} – {inr(b)}"
    if a or b:
        return f"From {inr(a or b)}"
    return ""


async def sources(db, user: dict, about_me: str = "") -> dict:
    from .knowledge import knowledge
    uid = str(user["_id"])
    try:
        k = await knowledge(db, user)
    except Exception:  # noqa: BLE001
        k = {}
    offer = None
    for o in await _latest(db.offer_cards, uid, 1):
        wyg = o.get("what_you_get")
        offer = {"offer_name": text(o.get("offer_name"), 120), "ideal_client": text(o.get("ideal_client"), 300),
                 "problem": text(o.get("problem"), 300), "outcome": text(o.get("outcome"), 300),
                 "what_you_get": [text(x, 160) for x in wyg][:8] if isinstance(wyg, list) else text(wyg, 600),
                 "fee": fee_text(o.get("fee_from_inr"), o.get("fee_to_inr"))}
    stories = []
    for s in await _latest(db.stories, uid, 6):
        st = {"title": text(s.get("title"), 100), "situation": text(s.get("situation"), 400),
              "what_i_did": text(s.get("what_i_did"), 400), "result": text(s.get("result"), 300)}
        if st["title"] or st["result"]:
            stories.append(st)
    return {"name": text(user.get("name"), 80), "title": text(k.get("consultant_title"), 120),
            "niche": text(k.get("niche"), 200), "value_proposition": text(k.get("value_proposition"), 400),
            "audience": text(k.get("target_audience"), 200), "industry": text(k.get("target_industry"), 120),
            "offer": offer, "stories": stories, "about_me": text(about_me, 800)}


def facts_text(src: dict) -> str:
    rows = [("Name", src["name"]), ("Consultant title", src["title"]), ("Niche", src["niche"]),
            ("Value proposition", src["value_proposition"]), ("Who they help", src["audience"]),
            ("Industry", src["industry"]), ("In their own words", src["about_me"])]
    out = [f"- {a}: {b}" for a, b in rows if b]
    o = src.get("offer")
    if o:
        wyg = "; ".join(o["what_you_get"]) if isinstance(o["what_you_get"], list) else o["what_you_get"]
        out.append("OFFER CARD: " + " | ".join(f"{a}: {b}" for a, b in [
            ("Offer", o["offer_name"]), ("Ideal client", o["ideal_client"]), ("Problem", o["problem"]),
            ("Outcome", o["outcome"]), ("What the client gets", wyg), ("Fee", o["fee"])] if b))
    for i, s in enumerate(src.get("stories") or []):
        out.append(f"CAREER STORY {i + 1}: {s['title']} | Situation: {s['situation']} | What I did: {s['what_i_did']} | "
                   f"Result: {s['result']}")
    return "\n".join(out) or "Nothing known yet. Use placeholders."


# ───────────────────────── numbers: only the member's own ─────────────────────────
NUM = re.compile(r"(?<![\w\[])(?:₹\s?)?\d[\d,]*(?:\.\d+)?")
CLAIM_AFTER = re.compile(r"^\s*\+?\s*(%|percent|x\b|times\b|years?\b|yrs?\b|clients?\b|companies\b|firms\b|businesses\b|"
                         r"projects?\b|lakhs?\b|crores?\b|cr\b|people\b|teams?\b|countries\b|cities\b|plants?\b|stores?\b|"
                         r"employees\b|members\b)", re.I)
ALWAYS_OK = {"24", "360"}


def _norm(n: str) -> str:
    n = re.sub(r"[₹,\s]", "", n)
    return n[:-2] if n.endswith(".0") else n


def numbers_in(*texts: str) -> set[str]:
    return {_norm(m.group(0)) for t in texts for m in NUM.finditer(t or "")}


def _scrub_text(s: str, allowed: set[str]) -> str:
    def rep(m):
        raw = m.group(0)
        n = _norm(raw)
        if n in allowed or n in ALWAYS_OK:
            return raw
        if not raw.startswith("₹") and len(n) == 1 and not CLAIM_AFTER.match(s[m.end():m.end() + 16]):
            return raw
        return "[number]"
    parts, last = [], 0
    for m in PLACEHOLDER.finditer(s):          # placeholders stay as written
        parts.append(NUM.sub(rep, s[last:m.start()]))
        parts.append(m.group(0))
        last = m.end()
    parts.append(NUM.sub(rep, s[last:]))
    return "".join(parts)


def scrub(data, allowed: set[str]):
    if isinstance(data, str):
        return _scrub_text(data, allowed)
    if isinstance(data, dict):
        return {k: scrub(v, allowed) for k, v in data.items()}
    if isinstance(data, list):
        return [scrub(v, allowed) for v in data]
    return data


def source_numbers(src: dict) -> set[str]:
    return numbers_in(*strings_of({k: v for k, v in src.items() if k != "name"}))


# ───────────────────────── first build ─────────────────────────
BUILD_SHAPE = (
    '{"hero": {"kicker": "", "headline": "", "sub": "", "cta": ""}, '
    '"problems": {"title": "", "intro": "", "items": [{"title": "", "text": ""}]}, '
    '"method": {"title": "", "intro": "", "steps": [{"title": "", "text": ""}]}, '
    '"services": {"title": "", "intro": "", "items": [{"name": "", "text": ""}]}, '
    '"about": {"title": "", "text": "", "points": [""]}, '
    '"proof": {"title": "", "intro": ""}, '
    '"faq": {"title": "", "items": [{"q": "", "a": ""}]}, '
    '"contact": {"title": "", "text": "", "cta": ""}, '
    '"seo": {"title": "", "description": ""}}'
)


def build_prompt(src: dict) -> str:
    steps = "; ".join(f"{i + 1}. {t}" for i, (t, _) in enumerate(SIX_STEPS))
    return (f"WHAT WE KNOW ABOUT THE CONSULTANT:\n{facts_text(src)}\n\n"
            "Write every section of their consulting website.\n"
            "- hero: kicker = their consultant title; headline = who they help and the result, max 12 words; sub = two "
            "short sentences on the problem they solve and how; cta = button text, max 5 words (e.g. Book a first call).\n"
            "- problems: 3 or 4 problems their ideal client has today, each a short title and one sentence, in the client's words.\n"
            f"- method: how they work, in exactly these 6 steps and this order: {steps}. Keep the step titles, write one "
            "sentence for each, fitted to their niche.\n"
            "- services: 1 to 3 services. If there is an Offer Card, the first service is that offer with its name; say "
            "what the client gets. Do not write fees.\n"
            "- about: 2 short paragraphs in the first person about their background and why clients can trust them, "
            "and up to 4 credibility points. Only facts given; placeholders for anything missing.\n"
            "- proof: a title and one intro sentence only (the case studies come from their own stories).\n"
            "- faq: 4 or 5 questions a business owner asks before hiring a consultant, answered plainly. Don't state "
            "fees, guarantees or timelines that are not given.\n"
            "- contact: a title, one or two sentences inviting a first conversation, and the button text.\n"
            "- seo: a page title (max 60 characters) and a description (max 155 characters).\n"
            f"JSON: {BUILD_SHAPE}")


def fake_build(src: dict) -> dict:
    name = src["name"] or "[your name]"
    title = src["title"] or "[your consultant title]"
    o = src.get("offer") or {}
    who = o.get("ideal_client") or src["audience"] or "[the clients you help]"
    problem = o.get("problem") or src["niche"] or "[the main problem you solve]"
    outcome = o.get("outcome") or "[the result clients get]"
    industry = src["industry"] or "[your industry]"
    return {
        "hero": {"kicker": title, "headline": f"Clear, practical help for {who}"[:120],
                 "sub": f"I work with {who} on {problem}. We start with one honest conversation about where you are today.",
                 "cta": "Book a first call"},
        "problems": {"title": "Problems I help solve", "intro": f"Most {industry} leaders I meet know something is off. These come up most.",
                     "items": [{"title": problem[:90], "text": "It costs more every month it stays unsolved."},
                               {"title": "Decisions sit with one person", "text": "Growth stalls when every call waits for the owner."},
                               {"title": "Plans that never get done", "text": "Good ideas get lost between meetings."}]},
        "method": {"title": "How I work", "intro": "Six clear steps, so you always know where we are.",
                   "steps": [{"title": t, "text": d} for t, d in SIX_STEPS]},
        "services": {"title": "How I can help", "intro": f"Work shaped around {who}.",
                     "items": [{"name": o.get("offer_name") or f"{title} engagement",
                                "text": f"We work on {problem} until you see {outcome}."},
                               {"name": "Diagnostic session", "text": "One focused session to find the real problem and the first move."}]},
        "about": {"title": f"About {name}",
                  "text": (f"I am {name}, a {title}. I have spent [how many] years in {industry}.\n\n"
                           f"Now I help {who} with {problem}."),
                  "points": ["[Your most senior role]", "[A result you are proud of, with a real number]"]},
        "proof": {"title": "Work I have done", "intro": "Real situations from my career, and what changed."},
        "faq": {"title": "Questions clients ask", "items": [
            {"q": "How do we start?", "a": "We have one conversation about where you are. If I can help, I send a short plan."},
            {"q": "Do you work with businesses like mine?", "a": f"I work with {who}. If you are not sure, ask me."},
            {"q": "How do you charge?", "a": "It depends on the scope. You get a clear fee before any work starts."},
            {"q": "How involved does my team need to be?", "a": "Enough to make decisions. I do the heavy lifting on analysis."}]},
        "contact": {"title": "Let's talk", "text": "Tell me what is going on in your business. I reply personally.",
                    "cta": "Send message"},
        "seo": {"title": f"{name} | {title}"[:60], "description": f"{title}. I help {who} with {problem}."[:155]},
    }


def proof_items(src: dict) -> list[dict]:
    """Case studies come only from the member's own career stories; with none, placeholders to fill."""
    items = [{"title": s["title"], "situation": s["situation"], "action": s["what_i_did"], "result": s["result"]}
             for s in (src.get("stories") or [])[:4]]
    return items or [{"title": "[The kind of company and your role there]", "situation": "[What was wrong when you started]",
                      "action": "[What you did, in two sentences]", "result": "[What changed, with a real number]"},
                     {"title": "[A second situation from your career]", "situation": "[The problem]",
                      "action": "[What you did]", "result": "[The result, with a real number]"}]


def finish_build(raw: dict, src: dict) -> tuple[dict, dict]:
    """Validate the AI's copy, keep Akshat's six steps, put in the member's own fee and stories. → (copy, seo)"""
    if not isinstance(raw, dict):
        raise llm.LLMError("site: not an object")
    allowed = source_numbers(src)
    raw = scrub({k: v for k, v in raw.items() if isinstance(v, dict)}, allowed)
    copy = {t: normalize(t, raw.get(t) or {}) for t in SECTIONS}
    steps = copy["method"]["steps"]
    copy["method"]["steps"] = [{"title": (steps[i]["title"] if i < len(steps) and steps[i]["title"] else t),
                                "text": (steps[i]["text"] if i < len(steps) and steps[i]["text"] else d)}
                               for i, (t, d) in enumerate(SIX_STEPS)]
    o = src.get("offer") or {}
    svc = copy["services"]["items"]
    for s in svc:
        s["fee"] = ""
    if o.get("offer_name"):
        if svc:
            svc[0]["name"] = o["offer_name"][:90]
        else:
            svc.append({"name": o["offer_name"][:90], "text": text(o.get("outcome"), 400), "fee": ""})
    if svc and o.get("fee"):
        svc[0]["fee"] = o["fee"]
    copy["proof"]["items"] = proof_items(src)
    copy["hero"]["kicker"] = copy["hero"]["kicker"] or src["title"]
    copy["hero"]["cta"] = copy["hero"]["cta"] or "Book a first call"
    copy["contact"]["cta"] = copy["contact"]["cta"] or "Send message"
    if (not copy["hero"]["headline"] or len(copy["problems"]["items"]) < 2 or not svc
            or len(copy["faq"]["items"]) < 2 or not copy["about"]["text"]):
        raise llm.LLMError("site: incomplete copy")
    seo_raw = raw.get("seo") or {}
    seo = {"title": text(seo_raw.get("title"), 70), "description": text(seo_raw.get("description"), 160)}
    return copy, seo


async def write_site(src: dict) -> tuple[dict, dict]:
    raw = await llm.complete_json(task="site_build", system=RULES, prompt=build_prompt(src),
                                  fake=lambda: fake_build(src), model="strong", max_tokens=3500)
    return finish_build(raw, src)


# ───────────────────────── edit one section by prompt ─────────────────────────
SHORTER = ("short", "brief", "concise", "fewer words", "tighter", "trim", "simple", "simpler", "plain")


def _first_sentence(s: str) -> str:
    if "\n\n" in s:
        return s.split("\n\n")[0]
    parts = re.split(r"(?<=[.!?])\s+", s)
    return parts[0] if len(parts) > 1 else s


def fake_edit(kind: str, data: dict, instruction: str) -> dict:
    t = instruction.lower()
    out = _copy.deepcopy(data)
    if any(w in t for w in SHORTER):
        def short(v):
            if isinstance(v, str):
                return _first_sentence(v)
            if isinstance(v, list):
                return [short(x) for x in v]
            if isinstance(v, dict):
                return {k: short(x) for k, x in v.items()}
            return v
        out = short(out)
    return {"data": out, "note": "Test mode edit. Live mode rewrites this section the way you asked."}


def edit_prompt(kind: str, data: dict, instruction: str, src: dict) -> str:
    return (f"WHAT WE KNOW ABOUT THE CONSULTANT:\n{facts_text(src)}\n\n"
            f"ONE SECTION OF THEIR WEBSITE ({SECTIONS[kind]['label']}), as JSON:\n{json.dumps(data, ensure_ascii=False)[:5000]}\n\n"
            f'The consultant asks: "{instruction}"\n\n'
            "Rewrite only this section to do what they ask. Keep the same keys and shape. Keep anything they did not ask "
            "to change. Use only the facts above, what is already in the section, and facts the consultant states in "
            "their request. If the request needs a fact that is not given, use a placeholder in square brackets. If the "
            "request is about colours, layout, order or pictures (you can't change those here), return the section "
            "unchanged and say so in note.\n"
            'JSON: {"data": { ...the section, same keys... }, "note": "one short sentence for the consultant, or empty"}')


async def edit_section(kind: str, data: dict, instruction: str, src: dict) -> tuple[dict, str]:
    raw = await llm.complete_json(task="site_edit", system=RULES, prompt=edit_prompt(kind, data, instruction, src),
                                  fake=lambda: fake_edit(kind, data, instruction), model="fast", max_tokens=1800)
    if not isinstance(raw, dict) or not isinstance(raw.get("data"), dict):
        raise llm.LLMError("site edit: no data")
    allowed = source_numbers(src) | numbers_in(instruction, *strings_of(data))
    new = normalize(kind, scrub(raw["data"], allowed))
    if kind == "hero" and not new["headline"]:
        raise llm.LLMError("site edit: empty headline")
    return new, text(raw.get("note"), 240)
