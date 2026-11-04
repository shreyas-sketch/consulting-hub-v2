"""Website Builder: the shape of a member's site, its pages and sections, and the checks every write goes through.

sites {_id, user_id, slug (unique), look, profile: {name, title}, pages: {key: [section]}, copy: {type: data},
       published, published_at, domain, domain_status, contact: {email, whatsapp, calendly}, logo_id, photo_id,
       proposal: {page, section_id, data, before, instruction, note, at} | None, undo: {page, section_id, data} | None,
       views, created_at, updated_at}
section {id, type, hidden, data}

Placeholders: anything the member still has to fill is written in square brackets ("[a result with a real number]").
The editor counts them; the live site leaves out every line that still has one, so a visitor never sees them.
"""
from __future__ import annotations

import copy as _copy
import re
import uuid

from .common import text

PAGES: list[tuple[str, str]] = [("home", "Home"), ("about", "About"), ("services", "Services"),
                                ("case-studies", "Case studies"), ("contact", "Contact")]
PAGE_KEYS = [k for k, _ in PAGES]
PAGE_LABEL = dict(PAGES)

# Section types: scalar fields (max chars), an optional list of objects or of strings, and a label for the editor.
SECTIONS: dict[str, dict] = {
    "hero": {"label": "Top of the page", "fields": {"kicker": 90, "headline": 120, "sub": 320, "cta": 40}},
    "problems": {"label": "Problems you solve", "fields": {"title": 100, "intro": 320},
                 "list": ("items", {"title": 90, "text": 280}, 6)},
    "method": {"label": "How you work", "fields": {"title": 100, "intro": 320},
               "list": ("steps", {"title": 70, "text": 260}, 8)},
    "services": {"label": "Services", "fields": {"title": 100, "intro": 320},
                 "list": ("items", {"name": 90, "text": 400, "fee": 60}, 6)},
    "about": {"label": "About you", "fields": {"title": 100, "text": 1600}, "strings": ("points", 160, 6),
              "long": {"text"}},
    "proof": {"label": "Case studies", "fields": {"title": 100, "intro": 320},
              "list": ("items", {"title": 100, "situation": 400, "action": 400, "result": 300}, 6)},
    "faq": {"label": "Questions", "fields": {"title": 100}, "list": ("items", {"q": 160, "a": 600}, 10)},
    "contact": {"label": "Contact", "fields": {"title": 100, "text": 400, "cta": 40}},
}
TYPES = list(SECTIONS)

# Which sections each page gets on the first build. One page (₹1,999 plan): everything on Home.
LAYOUT_ONE = {"home": ["hero", "problems", "method", "services", "about", "proof", "faq", "contact"]}
LAYOUT_FIVE = {"home": ["hero", "problems", "services", "proof", "contact"], "about": ["about", "method", "contact"],
               "services": ["services", "method", "faq", "contact"], "case-studies": ["proof", "contact"],
               "contact": ["contact", "faq"]}

# Akshat's six steps (the Strategic Thinking Framework), in plain words for a client.
SIX_STEPS = [("Understand the real problem", "We look at the whole situation first, so we fix the cause and not a symptom."),
             ("Agree on the goal", "We agree what success looks like, with a number we can both check."),
             ("Pick the right way to look at it", "I bring a proven way of breaking the problem down, so nothing important is missed."),
             ("Lay out the options", "You see every sensible option, with what each costs and what it gives you."),
             ("Choose what to do first", "We rank the options by impact and effort, and start where it pays off fastest."),
             ("Make it happen", "We write a clear plan with owners and dates, and I stay with you while it gets done.")]

PLACEHOLDER = re.compile(r"\[[^\[\]]{1,80}\]")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def para(v, n: int) -> str:
    """Text that keeps its paragraph breaks (About section)."""
    parts = [" ".join(p.split()) for p in re.split(r"\n\s*\n", str(v or ""))]
    return "\n\n".join(p for p in parts if p)[:n]


def blank(kind: str) -> dict:
    return normalize(kind, {})


def normalize(kind: str, data) -> dict:
    """Every write (AI or by hand) passes through here: known fields only, trimmed, lists capped."""
    spec = SECTIONS[kind]
    d = data if isinstance(data, dict) else {}
    long = spec.get("long", set())
    out = {k: (para(d.get(k), n) if k in long else text(d.get(k), n)) for k, n in spec["fields"].items()}
    if "list" in spec:
        key, fields, mx = spec["list"]
        rows = []
        for x in (d.get(key) or [])[:mx] if isinstance(d.get(key), list) else []:
            if not isinstance(x, dict):
                continue
            row = {f: text(x.get(f), n) for f, n in fields.items()}
            if any(row.values()):
                rows.append(row)
        out[key] = rows
    if "strings" in spec:
        key, n, mx = spec["strings"]
        vals = d.get(key) if isinstance(d.get(key), list) else []
        out[key] = [t for t in (text(x, n) for x in vals[:mx]) if t]
    return out


def section(kind: str, data: dict) -> dict:
    return {"id": new_id(), "type": kind, "hidden": False, "data": normalize(kind, _copy.deepcopy(data))}


def pages_from(copy: dict, page_keys: list[str]) -> dict:
    layout = LAYOUT_ONE if page_keys == ["home"] else LAYOUT_FIVE
    return {p: [section(t, copy.get(t) or {}) for t in layout.get(p, [])] for p in page_keys}


def page_sections(copy: dict, key: str) -> list[dict]:
    """A page added later (after an upgrade): its usual sections, from the site's own words."""
    return [section(t, copy.get(t) or {}) for t in LAYOUT_FIVE.get(key, ["contact"])]


def strings_of(data) -> list[str]:
    if isinstance(data, str):
        return [data]
    if isinstance(data, dict):
        return [s for v in data.values() for s in strings_of(v)]
    if isinstance(data, list):
        return [s for v in data for s in strings_of(v)]
    return []


def placeholders(data) -> int:
    return sum(len(PLACEHOLDER.findall(s)) for s in strings_of(data))


def site_placeholders(site: dict, page_keys: list[str]) -> list[dict]:
    """[{page, section_id, type, count}] for visible sections that still have something to fill."""
    out = []
    for p in page_keys:
        for s in (site.get("pages") or {}).get(p, []):
            n = 0 if s.get("hidden") else placeholders(s.get("data"))
            if n:
                out.append({"page": p, "section_id": s["id"], "type": s["type"], "count": n})
    return out


def _drop_sentences(s: str) -> str:
    """Live site: a sentence that still has a placeholder is left out."""
    if not PLACEHOLDER.search(s):
        return s
    paras = []
    for p in s.split("\n\n"):
        keep = [x for x in re.split(r"(?<=[.!?])\s+", p) if x and not PLACEHOLDER.search(x)]
        if keep:
            paras.append(" ".join(keep))
    return "\n\n".join(paras)


def public_data(kind: str, data: dict) -> dict | None:
    """What a visitor sees: list items with a placeholder are dropped, other text loses the sentences that have one.
    None when nothing worth showing is left."""
    spec = SECTIONS[kind]
    out = {k: _drop_sentences(v) if isinstance(v, str) else v for k, v in data.items()}
    if "list" in spec:
        key, fields, _ = spec["list"]
        must = [next(iter(fields))] + (["result"] if kind == "proof" else [])     # the item's name (and a case's result)
        out[key] = [{f: _drop_sentences(v or "") for f, v in x.items()} for x in data.get(key) or []
                    if not any(PLACEHOLDER.search(x.get(f) or "") for f in must)]
    if "strings" in spec:
        key = spec["strings"][0]
        out[key] = [x for x in data.get(key) or [] if not PLACEHOLDER.search(x)]
    if kind == "hero":
        return out if out.get("headline") else None
    if kind == "contact":
        return out
    if kind in ("problems", "method", "services", "proof", "faq"):
        return out if out.get(spec["list"][0]) else None
    if kind == "about":
        return out if (out.get("text") or out.get("points")) else None
    return out


def summary(kind: str, data: dict) -> str:
    """One line for the section list in the editor."""
    for k in ("headline", "title", "text", "intro"):
        if data.get(k):
            return text(data[k], 90)
    return SECTIONS[kind]["label"]
