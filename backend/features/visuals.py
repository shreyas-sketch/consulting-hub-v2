"""Visual Builder: frameworks, charts and mind maps for slides and posts (our own renderer, drawn as SVG in the app).

visuals {_id, user_id, kind, title, prompt, numbers, spec, copied_from?, at, updated_at}

The member describes what they want (and pastes numbers for a chart). The AI returns a strict JSON spec for the kind;
every field is checked here. A chart may only use numbers the member gave: with no numbers we ask for them, and a
value the member didn't give fails the check (the go is given back). Editing labels, duplicating and deleting are free.

Kinds and specs (all have title, optional note):
    matrix      x_axis {label, low, high}, y_axis {label, low, high}, quadrants [TL, TR, BL, BR], items [{label, x, y}] (0-100)
    process     steps [{label, detail}]                     3-8
    pyramid     levels [{label, detail}] top first          3-6
    funnel      stages [{label, value, detail}] widest first 3-7
    mindmap     centre, branches [{label, leaves: [str]}]   2-6 branches, up to 4 leaves
    comparison  columns [str] 2-4, rows [{label, cells: [str]}] 2-8
    chart       chart bar|line|pie, unit, labels [str], series [{name, values: [number]}]
"""
from __future__ import annotations

import math
import re
import uuid
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import indexes
import llm
import plans
from core.deps import user_dep
from core.errors import BadRequest, NotFound
from growth import events
from growth.clock import utcnow
from state import db
from util import iso

from .common import clamp_int, run_metered, text

router = APIRouter(prefix="/visuals", tags=["visual-builder"])

events.register("visual_made", "Visual Builder visual made (props.kind)")
indexes.register("visuals", [("user_id", 1), ("at", -1)])

KINDS = ("matrix", "process", "pyramid", "funnel", "mindmap", "comparison", "chart")
CHARTS = ("bar", "line", "pie")

SYSTEM = (
    "You turn a consultant's description into the content of one clean business visual for a slide or a LinkedIn post. "
    "The readers are Indian business owners. Short labels (1-4 words), short details (under 12 words), plain English, "
    "no jargon, no emojis. Money in Indian rupees with Indian grouping (₹1,50,000). Never invent numbers: use only "
    "numbers the consultant wrote. For a chart, every value must be one of the consultant's numbers; if they gave no "
    'numbers, reply {"error": "need_numbers"}. Never mention AI providers or models. Reply with JSON only.'
)

SHAPES = {
    "matrix": ('{"title": "", "x_axis": {"label": "", "low": "Low", "high": "High"}, "y_axis": {"label": "", "low": "Low", '
               '"high": "High"}, "quadrants": ["top-left", "top-right", "bottom-left", "bottom-right"], '
               '"items": [{"label": "", "x": 0, "y": 0}], "note": ""}',
               "A 2x2 matrix. x and y are 0-100 (0 = low, 100 = high). Up to 10 items placed where they belong."),
    "process": ('{"title": "", "steps": [{"label": "", "detail": ""}], "note": ""}', "3 to 8 steps in order."),
    "pyramid": ('{"title": "", "levels": [{"label": "", "detail": ""}], "note": ""}', "3 to 6 levels, the top level first."),
    "funnel": ('{"title": "", "stages": [{"label": "", "value": "", "detail": ""}], "note": ""}',
               "3 to 7 stages, widest first. value only if the consultant gave a number for that stage, else empty."),
    "mindmap": ('{"title": "", "centre": "", "branches": [{"label": "", "leaves": [""]}], "note": ""}',
                "One centre idea, 3 to 6 branches, up to 4 short leaves each."),
    "comparison": ('{"title": "", "columns": ["", ""], "rows": [{"label": "", "cells": ["", ""]}], "note": ""}',
                   "2 to 4 columns (the things compared) and 2 to 8 rows (what they're compared on). One cell per column."),
    "chart": ('{"title": "", "chart": "bar", "unit": "", "labels": [""], "series": [{"name": "", "values": [0]}], "note": ""}',
              "chart is bar, line or pie. labels are the categories or periods. 1 to 3 series (pie: exactly 1), one "
              "value per label, using only the consultant's numbers. unit like '₹ lakh', '%', 'clients'."),
}

NUM_RE = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def numbers_in(s: str) -> list[float]:
    out = []
    for m in NUM_RE.findall(s or ""):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def _given(v: float, given: list[float]) -> bool:
    return any(math.isclose(v, g, rel_tol=1e-9, abs_tol=1e-9) for g in given)


class SpecError(ValueError):
    pass


def _t(v, n: int, what: str, required: bool = True) -> str:
    s = text(v, n)
    if required and not s:
        raise SpecError(f"{what} is empty")
    return s


def _items(v, lo: int, hi: int, what: str) -> list:
    if not isinstance(v, list) or len(v) < lo:
        raise SpecError(f"{what}: need at least {lo}")
    return v[:hi]


def _num(v) -> float:
    if isinstance(v, bool):
        raise SpecError("value is not a number")
    try:
        f = float(str(v).replace(",", "").replace("₹", "").strip())
    except (TypeError, ValueError):
        raise SpecError("value is not a number")
    if not math.isfinite(f):
        raise SpecError("value is not a number")
    return f


def clean_spec(kind: str, raw: Any, given: Optional[list[float]] = None) -> dict:
    """Strict spec check. `given` = the member's numbers (AI output); None = the member's own edit."""
    if not isinstance(raw, dict):
        raise SpecError("spec is not an object")
    out: dict = {"title": _t(raw.get("title"), 80, "title"), "note": text(raw.get("note"), 140)}
    if kind == "matrix":
        out["x_axis"], out["y_axis"] = {}, {}
        for ax in ("x_axis", "y_axis"):
            a = raw.get(ax) if isinstance(raw.get(ax), dict) else {}
            out[ax] = {"label": _t(a.get("label"), 30, f"{ax} label"), "low": text(a.get("low"), 16) or "Low",
                       "high": text(a.get("high"), 16) or "High"}
        q = raw.get("quadrants")
        if not isinstance(q, list) or len(q) != 4:
            raise SpecError("quadrants: need 4")
        out["quadrants"] = [text(x, 30) for x in q]
        out["items"] = [{"label": _t(i.get("label"), 30, "item"), "x": clamp_int(i.get("x"), 0, 100, 50),
                         "y": clamp_int(i.get("y"), 0, 100, 50)}
                        for i in _items(raw.get("items"), 1, 12, "items") if isinstance(i, dict) and text(i.get("label"), 30)]
        if not out["items"]:
            raise SpecError("items: none")
    elif kind in ("process", "pyramid"):
        key, lo, hi = ("steps", 3, 8) if kind == "process" else ("levels", 3, 6)
        rows = [{"label": _t(s.get("label"), 40, key), "detail": text(s.get("detail"), 120)}
                for s in _items(raw.get(key), lo, hi, key) if isinstance(s, dict) and text(s.get("label"), 40)]
        if len(rows) < lo:
            raise SpecError(f"{key}: need at least {lo}")
        out[key] = rows
    elif kind == "funnel":
        rows = []
        for s in _items(raw.get("stages"), 3, 7, "stages"):
            if not isinstance(s, dict) or not text(s.get("label"), 40):
                continue
            value = text(s.get("value"), 30)
            if value and given is not None and not all(_given(n, given) for n in numbers_in(value)):
                value = ""                                      # a number the member didn't give is dropped
            rows.append({"label": text(s.get("label"), 40), "value": value, "detail": text(s.get("detail"), 120)})
        if len(rows) < 3:
            raise SpecError("stages: need at least 3")
        out["stages"] = rows
    elif kind == "mindmap":
        out["centre"] = _t(raw.get("centre"), 40, "centre")
        br = []
        for b in _items(raw.get("branches"), 2, 6, "branches"):
            if isinstance(b, dict) and text(b.get("label"), 40):
                leaves = [text(x, 40) for x in (b.get("leaves") or [])[:4] if text(x, 40)] if isinstance(b.get("leaves"), list) else []
                br.append({"label": text(b.get("label"), 40), "leaves": leaves})
        if len(br) < 2:
            raise SpecError("branches: need at least 2")
        out["branches"] = br
    elif kind == "comparison":
        cols = [text(c, 30) for c in _items(raw.get("columns"), 2, 4, "columns")]
        if not all(cols):
            raise SpecError("columns: empty name")
        rows = []
        for r in _items(raw.get("rows"), 2, 8, "rows"):
            if isinstance(r, dict) and text(r.get("label"), 40):
                cells = [text(x, 60) for x in (r.get("cells") or [])] if isinstance(r.get("cells"), list) else []
                rows.append({"label": text(r.get("label"), 40), "cells": (cells + [""] * len(cols))[:len(cols)]})
        if len(rows) < 2:
            raise SpecError("rows: need at least 2")
        out["columns"], out["rows"] = cols, rows
    elif kind == "chart":
        ch = str(raw.get("chart") or "").lower()
        if ch not in CHARTS:
            raise SpecError("chart: bar, line or pie")
        labels = [text(x, 24) for x in _items(raw.get("labels"), 2, 12, "labels")]
        if not all(labels):
            raise SpecError("labels: empty label")
        series = []
        for s in _items(raw.get("series"), 1, 1 if ch == "pie" else 3, "series"):
            if not isinstance(s, dict) or not isinstance(s.get("values"), list) or len(s["values"]) != len(labels):
                raise SpecError("series: one value per label")
            vals = [_num(v) for v in s["values"]]
            if given is not None and not all(_given(v, given) for v in vals):
                raise SpecError("chart uses a number the member didn't give")
            series.append({"name": text(s.get("name"), 30) or out["title"][:30], "values": vals})
        if ch == "pie":
            if any(v < 0 for v in series[0]["values"]) or sum(series[0]["values"]) <= 0:
                raise SpecError("pie: values must be positive")
            if len(labels) > 8:
                raise SpecError("pie: up to 8 slices")
        out.update(chart=ch, unit=text(raw.get("unit"), 16), labels=labels, series=series)
    else:
        raise SpecError("unknown kind")
    return out


# ------------------------------------------------------------------ fakes ----
WORD_RE = re.compile(r"[A-Za-z][A-Za-z&'-]{2,}")
STOP = {"the", "and", "for", "with", "that", "this", "from", "show", "make", "want", "into", "our", "your", "their",
        "about", "what", "how", "chart", "matrix", "process", "pyramid", "funnel", "map", "mind", "comparison", "steps"}
PAIR_RE = re.compile(r"([A-Za-z][A-Za-z0-9 &'/-]{0,22}?)\s*[:=\-–]?\s*₹?\s*(-?\d[\d,]*(?:\.\d+)?)")


def _words(prompt: str, n: int) -> list[str]:
    seen, out = set(), []
    for w in WORD_RE.findall(prompt or ""):
        lw = w.lower()
        if lw not in STOP and lw not in seen:
            seen.add(lw)
            out.append(w.capitalize())
    fill = ["Clarity", "Focus", "Speed", "Cost", "Quality", "People", "Process", "Growth", "Cash", "Customers", "Margin", "Trust"]
    return (out + [f for f in fill if f.lower() not in seen])[:n]


def fake_spec(kind: str, prompt: str, numbers: str, chart: str) -> dict:
    w = _words(prompt, 12)
    title = " ".join(_words(prompt, 3)) or "My visual"
    note = "Test mode visual. Live mode writes it from your description."
    if kind == "matrix":
        return {"title": title, "x_axis": {"label": "Ease", "low": "Hard", "high": "Easy"},
                "y_axis": {"label": "Impact", "low": "Low", "high": "High"},
                "quadrants": ["Plan these", "Do first", "Drop", "Quick wins"],
                "items": [{"label": w[i], "x": (i * 37 + 20) % 90 + 5, "y": (i * 53 + 30) % 90 + 5} for i in range(5)], "note": note}
    if kind == "process":
        return {"title": title, "steps": [{"label": w[i], "detail": f"What happens at the {w[i].lower()} step"} for i in range(5)], "note": note}
    if kind == "pyramid":
        return {"title": title, "levels": [{"label": w[i], "detail": f"Built on {w[i + 1].lower()}"} for i in range(4)], "note": note}
    if kind == "funnel":
        nums = [n for n in NUM_RE.findall(f"{prompt} {numbers}")][:4]
        return {"title": title, "stages": [{"label": w[i], "value": nums[i] if i < len(nums) else "", "detail": ""} for i in range(4)], "note": note}
    if kind == "mindmap":
        return {"title": title, "centre": w[0], "branches": [{"label": w[i], "leaves": [w[(i + 3) % 12], w[(i + 5) % 12]]} for i in range(1, 5)], "note": note}
    if kind == "comparison":
        return {"title": title, "columns": ["Option A", "Option B"],
                "rows": [{"label": w[i], "cells": ["Strong", "Weak"] if i % 2 else ["Medium", "Strong"]} for i in range(4)], "note": note}
    src = f"{numbers}\n{prompt}"
    given = numbers_in(src)
    pairs = [(lbl.strip(), v) for lbl, v in PAIR_RE.findall(src)
             if lbl.strip() and _given(float(v.replace(",", "")), given)]
    if len(pairs) >= 2:
        labels, vals = [p[0][:24] for p in pairs[:8 if chart == "pie" else 12]], [float(p[1].replace(",", "")) for p in pairs]
    else:
        vals = numbers_in(src)
        labels = [f"Item {i + 1}" for i in range(min(len(vals), 8 if chart == "pie" else 12))]
    vals = vals[:len(labels)]
    if chart == "pie":
        vals = [abs(v) for v in vals]
    return {"title": title, "chart": chart, "unit": "", "labels": labels, "series": [{"name": title[:30], "values": vals}], "note": note}


# ------------------------------------------------------------------ routes ----
class VisualIn(BaseModel):
    kind: Literal["matrix", "process", "pyramid", "funnel", "mindmap", "comparison", "chart"]
    prompt: str = Field(..., min_length=5, max_length=2000)
    numbers: str = Field("", max_length=3000)
    chart: Literal["bar", "line", "pie"] = "bar"


class SpecIn(BaseModel):
    spec: dict


def _public(v: dict) -> dict:
    return {"id": v["_id"], "kind": v["kind"], "title": v["spec"].get("title") or v.get("title"), "spec": v["spec"],
            "prompt": v.get("prompt"), "numbers": v.get("numbers"), "copied_from": v.get("copied_from"),
            "at": iso(v["at"]), "updated_at": iso(v.get("updated_at"))}


def need_numbers() -> HTTPException:
    return BadRequest("Paste the numbers for your chart, for example: Apr 12, May 15, Jun 19. "
                                       "The chart uses only the numbers you give.", code="need_numbers")


@router.post("")
async def make(body: VisualIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])

    async def work(plan: str):
        given = numbers_in(f"{body.prompt}\n{body.numbers}")
        if body.kind == "chart" and len(given) < 2:
            raise need_numbers()
        hint = f"Chart type: {body.chart}.\n" if body.kind == "chart" else ""
        prompt = (f"Kind of visual: {body.kind}. {SHAPES[body.kind][1]}\n{hint}"
                  f"What the consultant wants:\n{body.prompt}\n"
                  + (f"Their numbers:\n{body.numbers}\n" if body.numbers.strip() else "")
                  + f"\nJSON: {SHAPES[body.kind][0]}")
        raw = await llm.complete_json(task=f"visual_{body.kind}", system=SYSTEM, prompt=prompt,
                                      fake=lambda: fake_spec(body.kind, body.prompt, body.numbers, body.chart),
                                      model="fast", max_tokens=1200)
        if isinstance(raw, dict) and raw.get("error") == "need_numbers":
            raise need_numbers()
        if body.kind == "chart" and isinstance(raw, dict) and not raw.get("chart"):
            raw["chart"] = body.chart
        try:
            spec = clean_spec(body.kind, raw, given=given if body.kind in ("chart", "funnel") else None)
        except SpecError as e:
            raise llm.LLMError(f"visual: {e}")
        now = utcnow()
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "kind": body.kind, "title": spec["title"], "prompt": body.prompt,
               "numbers": body.numbers, "spec": spec, "at": now, "updated_at": now}
        await d.visuals.insert_one(doc)
        await events.track(d, "visual_made", user_id=uid, props={"kind": body.kind})
        return _public(doc)
    return await run_metered(d, user, "visuals", work)


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    rows = [{"id": v["_id"], "kind": v["kind"], "title": v["spec"].get("title"), "at": iso(v["at"]),
             "updated_at": iso(v.get("updated_at"))}
            async for v in db().visuals.find({"user_id": str(user["_id"])}, {"kind": 1, "spec.title": 1, "at": 1, "updated_at": 1})
            .sort("at", -1).limit(100)]
    return {"items": rows}


async def _own(vid: str, user: dict) -> dict:
    await plans.require(db(), user, "visuals")
    v = await db().visuals.find_one({"_id": vid, "user_id": str(user["_id"])})
    if not v:
        raise NotFound("Visual not found.")
    return v


@router.get("/{vid}")
async def one(vid: str, user: dict = Depends(user_dep())):
    return _public(await _own(vid, user))


@router.put("/{vid}")
async def save(vid: str, body: SpecIn, user: dict = Depends(user_dep())):
    """The member's own edit of labels (and, for a chart, their own numbers). Free."""
    v = await _own(vid, user)
    try:
        spec = clean_spec(v["kind"], body.spec, given=None)
    except SpecError as e:
        raise BadRequest(f"This can't be saved: {e}.", code="bad_spec")
    await db().visuals.update_one({"_id": vid}, {"$set": {"spec": spec, "title": spec["title"], "updated_at": utcnow()}})
    return _public(await db().visuals.find_one({"_id": vid}))


@router.post("/{vid}/duplicate")
async def duplicate(vid: str, user: dict = Depends(user_dep())):
    v = await _own(vid, user)
    now = utcnow()
    spec = {**v["spec"], "title": text(f"{v['spec']['title']} (copy)", 80)}
    doc = {**v, "_id": uuid.uuid4().hex, "spec": spec, "title": spec["title"], "copied_from": vid, "at": now, "updated_at": now}
    await db().visuals.insert_one(doc)
    return _public(doc)


@router.delete("/{vid}")
async def remove(vid: str, user: dict = Depends(user_dep())):
    await _own(vid, user)
    await db().visuals.delete_one({"_id": vid})
    return {"ok": True}
