"""Presentation Builder engine, part 1: the slide schema and the layout every renderer draws from.

A deck is JSON: {"slides": [{"layout": "...", ...fields}]}. Eleven layouts, each with fixed fields and strict character
limits (LIMITS). `clean_deck()` checks the shape and the limits; `layout_deck()` turns a clean deck into boxes on a
960 x 540 pt canvas (16:9, the size of a widescreen PowerPoint slide): every text box gets its position, its font size
after fitting and its wrapped lines, measured with the real Manrope metrics. The PowerPoint and PDF renderers
(features/deck_render.py) and the HTML preview in the app draw exactly these boxes, so all three match.

Fitting: a box starts at its largest size and shrinks in 0.5 pt steps to its minimum. The character limits are set so the
longest allowed text still fits at the minimum size (tests/test_decks.py checks every layout). If text somehow still
doesn't fit (a member pastes very wide characters), the last line that fits ends with "…": text never leaves its box.

Fonts: backend/assets/fonts/Manrope-{Regular,SemiBold,Bold,ExtraBold}.ttf, made from the variable woff2 files in
@fontsource-variable/manrope (latin + latin-ext subsets, so ₹ is included) with fontTools varLib.instancer at 400, 600,
700 and 800, then merged. Licence: SIL OFL 1.1 (assets/fonts/OFL.txt). Widths come from those files, with no kerning and
no ligatures, the same way reportlab draws them; the HTML preview turns kerning and ligatures off to match.

Colours: Akshat Dani design system. Dark theme (default): background #14151A with a soft radial lift, ivory text,
gold #C9A84C as the one signal colour. Light theme for printing: white paper, ink #14151A, the same gold for rules and
fills and the deeper gold #8F7635 for small gold text. Teal and red are never used in decks.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ------------------------------------------------------------------ fonts and metrics ----
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONTS = {"regular": "Manrope-Regular", "semibold": "Manrope-SemiBold", "bold": "Manrope-Bold",
         "extrabold": "Manrope-ExtraBold"}
CSS_WEIGHT = {"regular": 400, "semibold": 600, "bold": 700, "extrabold": 800}
PPTX_BOLD = {"regular": False, "semibold": False, "bold": True, "extrabold": True}   # PowerPoint: "Manrope" ± bold


def _register() -> None:
    for name in FONTS.values():
        try:
            pdfmetrics.getFont(name)
        except KeyError:
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / f"{name}.ttf")))


_register()
_FACE = pdfmetrics.getFont(FONTS["regular"]).face
ASC = _FACE.ascent / 1000.0            # 1.066 em
DESC = -_FACE.descent / 1000.0         # 0.300 em
XH = 0.54                              # x-height (OS/2 sxHeight 1080 / 2000)
SUPPORTED = frozenset(chr(c) for c in _FACE.charToGlyph)


def text_width(s: str, font: str, size: float, cs: float = 0.0) -> float:
    return pdfmetrics.stringWidth(s, FONTS[font], size) + cs * len(s)


def baseline(size: float, lh: float) -> float:
    """Distance from the top of a line box (height lh pt) to the baseline, the way browsers place it (half-leading)."""
    return (lh - (ASC + DESC) * size) / 2 + ASC * size


# ------------------------------------------------------------------ themes ----
THEMES = {
    "dark": {"bg": "#14151A", "panel": "#1E2027", "raised": "#262932", "line": "#2A2D36", "line_strong": "#3A3E4A",
             "ink": "#F2EEE6", "muted": "#AFADA9", "faint": "#626161", "gold": "#C9A84C", "gold_text": "#C9A84C",
             "gold_deep": "#8F7635", "numeral": "#413A27", "on_gold": "#14151A",
             "lift": [[0, "#1E2027"], [0.5, "#17181E"], [0.8, "#14151A"]],
             "warm": [[0, "#26231D"], [0.55, "#1A1A1B"], [0.85, "#14151A"]]},
    "light": {"bg": "#FFFFFF", "panel": "#F6F4EF", "raised": "#EEEBE4", "line": "#E4E0D6", "line_strong": "#CFC9BC",
              "ink": "#14151A", "muted": "#5A5D66", "faint": "#9A9CA3", "gold": "#C9A84C", "gold_text": "#8F7635",
              "gold_deep": "#8F7635", "numeral": "#F2E9D2", "on_gold": "#14151A", "lift": None, "warm": None},
}
THEME_KEYS = tuple(THEMES)

# ------------------------------------------------------------------ schema ----
LIMITS = {
    "kicker": 32, "title": 80, "accent": 40, "notes": 500,
    "cover_title": 90, "subtitle": 150, "presenter": 90,
    "agenda_item": 64,
    "section_title": 70, "section_sub": 130,
    "bullet": 120,
    "col_heading": 40, "col_point": 90,
    "stat_value": 14, "stat_label": 70, "stat_note": 120,
    "quote": 220, "quote_by": 70,
    "step_title": 32, "step_text": 100,
    "axis": 28, "cell_title": 30, "cell_text": 90,
    "th": 24, "td": 48,
    "closing_title": 80, "closing_text": 170, "action": 90,
}
SLIDES_MIN, SLIDES_MAX = 6, 14

# field: (kind, limit key or spec, required, min, max)
_COMMON = {"kicker": ("text", "kicker", False), "notes": ("text", "notes", False)}
_HEAD = {**_COMMON, "title": ("text", "title", True), "accent": ("text", "accent", False)}
SPEC: dict[str, dict] = {
    "title": {**_COMMON, "title": ("text", "cover_title", True), "accent": ("text", "accent", False),
              "subtitle": ("text", "subtitle", False), "presenter": ("text", "presenter", False)},
    "agenda": {**_HEAD, "items": ("list", "agenda_item", True, 3, 6)},
    "section": {**_COMMON, "title": ("text", "section_title", True), "accent": ("text", "accent", False),
                "subtitle": ("text", "section_sub", False)},
    "bullets": {**_HEAD, "bullets": ("list", "bullet", True, 3, 6)},
    "two_column": {**_HEAD, "style": ("enum", ("compare", "before_after"), False),
                   "left": ("obj", {"heading": ("text", "col_heading", True), "points": ("list", "col_point", True, 2, 5)}, True),
                   "right": ("obj", {"heading": ("text", "col_heading", True), "points": ("list", "col_point", True, 2, 5)}, True)},
    "big_number": {**_HEAD, "stats": ("objs", {"value": ("text", "stat_value", True), "label": ("text", "stat_label", True)}, True, 1, 3),
                   "note": ("text", "stat_note", False)},
    "quote": {**_COMMON, "quote": ("text", "quote", True), "by": ("text", "quote_by", False)},
    "steps": {**_HEAD, "steps": ("objs", {"title": ("text", "step_title", True), "text": ("text", "step_text", False)}, True, 3, 6)},
    "grid_2x2": {**_HEAD, "x_axis": ("text", "axis", True), "y_axis": ("text", "axis", True),
                 "cells": ("objs", {"title": ("text", "cell_title", True), "text": ("text", "cell_text", False)}, True, 4, 4),
                 "highlight": ("index", 4, False)},
    "table": {**_HEAD, "columns": ("list", "th", True, 2, 4), "rows": ("rows", "td", True, 1, 5)},
    "closing": {**_COMMON, "title": ("text", "closing_title", True), "accent": ("text", "accent", False),
                "text": ("text", "closing_text", False), "action": ("text", "action", True)},
}
LAYOUTS = tuple(SPEC)


class BadDeck(ValueError):
    """The deck JSON has the wrong shape, or (for a member's edit) a text is longer than its limit."""


_SWAP = {"→": " to ", "⇒": " to ", "➜": " to ", "←": " from ", " ": " ", "\t": " ", "​": ""}
_LEAD = re.compile(r"^\s*(?:[-•*·▪■]|\d{1,2}[.)])\s+")


def clean_text(v) -> str:
    """One line of plain text: whitespace collapsed, characters the font doesn't have swapped or dropped."""
    s = str(v if v is not None else "")
    for a, b in _SWAP.items():
        s = s.replace(a, b)
    s = "".join(ch for ch in s if ch in SUPPORTED or ch.isspace())
    return " ".join(s.split())


def _fit_limit(s: str, n: int, strict: bool, where: str) -> str:
    if len(s) <= n:
        return s
    if strict:
        raise BadDeck(f"{where} can be up to {n} characters.")
    cut = s[:n - 1].rstrip()
    if " " in cut[n // 2:]:
        cut = cut[:cut.rfind(" ")].rstrip(" ,;:-–—")
    return cut + "…"


def _clean_field(spec: tuple, v, *, strict: bool, where: str):
    kind = spec[0]
    if kind == "text":
        s = clean_text(v)
        return _fit_limit(s, LIMITS[spec[1]], strict, where)
    if kind == "enum":
        return v if v in spec[1] else spec[1][0]
    if kind == "index":
        try:
            i = int(v)
        except (TypeError, ValueError):
            return None
        return i if 0 <= i < spec[1] else None
    if kind == "list":
        if not isinstance(v, list):
            raise BadDeck(f"{where}: expected a list.")
        out = [_fit_limit(_LEAD.sub("", clean_text(x)), LIMITS[spec[1]], strict, f"{where} item {i + 1}")
               for i, x in enumerate(v)]
        out = [x for x in out if x][:spec[4]]
        if len(out) < spec[3]:
            raise BadDeck(f"{where}: needs at least {spec[3]} items.")
        return out
    if kind == "obj":
        if not isinstance(v, dict):
            raise BadDeck(f"{where}: expected an object.")
        return _clean_obj(spec[1], v, strict=strict, where=where)
    if kind == "objs":
        if not isinstance(v, list):
            raise BadDeck(f"{where}: expected a list.")
        out = [_clean_obj(spec[1], x, strict=strict, where=f"{where} {i + 1}") for i, x in enumerate(v) if isinstance(x, dict)]
        if strict and len(out) != len(v):
            raise BadDeck(f"{where}: every item needs its fields.")
        out = out[:spec[4]]
        if len(out) < spec[3]:
            raise BadDeck(f"{where}: needs at least {spec[3]} items.")
        return out
    if kind == "rows":
        if not isinstance(v, list):
            raise BadDeck(f"{where}: expected rows.")
        rows = [r for r in v if isinstance(r, list) and any(clean_text(c) for c in r)][:spec[4]]
        if len(rows) < spec[3]:
            raise BadDeck(f"{where}: needs at least {spec[3]} row.")
        return [[_fit_limit(clean_text(c), LIMITS[spec[1]], strict, f"{where} row {i + 1}") for c in r]
                for i, r in enumerate(rows)]
    raise BadDeck(f"unknown field kind {kind}")


def _clean_obj(fields: dict, raw: dict, *, strict: bool, where: str) -> dict:
    out = {}
    for name, spec in fields.items():
        if spec[0] in ("text", "enum", "index") and name not in raw:
            val = "" if spec[0] == "text" else _clean_field(spec, None, strict=strict, where=where)
        else:
            val = _clean_field(spec, raw.get(name), strict=strict, where=f"{where} {name}")
        if spec[0] == "text" and spec[2] and not val:
            raise BadDeck(f"{where}: {name.replace('_', ' ')} is empty.")
        out[name] = val
    return out


def clean_slide(raw, *, strict: bool = False, where: str = "Slide") -> dict:
    if not isinstance(raw, dict):
        raise BadDeck(f"{where}: not an object.")
    layout = str(raw.get("layout") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if layout not in SPEC:
        raise BadDeck(f"{where}: unknown layout {layout[:20]!r}.")
    s = {"layout": layout, **_clean_obj(SPEC[layout], raw, strict=strict, where=where)}
    if layout == "table":
        n = len(s["columns"])
        s["rows"] = [(r + [""] * n)[:n] for r in s["rows"]]
    if layout == "quote":
        s["quote"] = s["quote"].strip("\"“”'‘’ ") or s["quote"]
    return s


def clean_deck(raw, *, strict: bool = False) -> dict:
    """AI output (strict=False: too-long text is cut at a word and ends with …) or a member's edit (strict=True: a
    too-long text is an error). Raises BadDeck on a wrong shape."""
    slides = raw.get("slides") if isinstance(raw, dict) else None
    if not isinstance(slides, list):
        raise BadDeck("No slides.")
    if not strict and len(slides) > SLIDES_MAX:
        slides = slides[:SLIDES_MAX - 1] + slides[-1:]
    out = [clean_slide(s, strict=strict, where=f"Slide {i + 1}") for i, s in enumerate(slides)]
    if not SLIDES_MIN <= len(out) <= SLIDES_MAX:
        raise BadDeck(f"A deck has {SLIDES_MIN} to {SLIDES_MAX} slides.")
    if out[0]["layout"] != "title" or out[-1]["layout"] != "closing":
        raise BadDeck("A deck starts with a title slide and ends with a closing slide.")
    return {"slides": out}


# ------------------------------------------------------------------ words, wrapping, fitting ----
_MONEY = re.compile(r"₹\s?[\d][\d,.]*(?:\s?(?:lakh|lakhs|crore|crores|cr|Cr|L|K|k|lac|lacs)\b)?")


def words_of(text: str, color: str, gold: Optional[str] = None, accent: str = "", money: bool = False) -> list:
    """[(word, colour)]. Words inside the accent phrase (first match) or a ₹ figure (money=True) take the gold colour."""
    spans = []
    if gold and accent:
        i = text.lower().find(accent.lower())
        if i >= 0:
            spans.append((i, i + len(accent)))
    if gold and money:
        spans += [m.span() for m in _MONEY.finditer(text)]
    out, pos = [], 0
    for w in text.split(" "):
        if w:
            start, end = pos, pos + len(w)
            hit = any(a < end and start < b for a, b in spans)
            out.append((w, gold if hit else color))
        pos += len(w) + 1
    return out


def _break_word(word: str, color: str, width: float, font: str, size: float, cs: float) -> list:
    parts, cur = [], ""
    for ch in word:
        if cur and text_width(cur + ch, font, size, cs) > width:
            parts.append((cur, color))
            cur = ch
        else:
            cur += ch
    if cur:
        parts.append((cur, color))
    return parts


def wrap(words: list, width: float, font: str, size: float, cs: float) -> list:
    """Greedy wrap: [[(word, colour)]] per line. A word wider than the box is broken by characters."""
    lines, cur, cur_w = [], [], 0.0
    sp = text_width(" ", font, size, cs)
    for w, c in words:
        ww = text_width(w, font, size, cs)
        pieces = [(w, c, ww)] if ww <= width + 0.01 else [(p, c, text_width(p, font, size, cs))
                                                           for p, c in _break_word(w, c, width, font, size, cs)]
        for p, pc, pw in pieces:
            if cur and cur_w + sp + pw > width + 0.01:
                lines.append(cur)
                cur, cur_w = [], 0.0
            cur_w += (sp if cur else 0.0) + pw
            cur.append((p, pc))
    if cur:
        lines.append(cur)
    return lines


def _segments(words: list) -> list:
    """Merge neighbouring words of one colour: [[text, colour]], spaces kept with the first segment."""
    segs: list = []
    for i, (w, c) in enumerate(words):
        t = w + (" " if i < len(words) - 1 else "")
        if segs and segs[-1][1] == c:
            segs[-1][0] += t
        else:
            segs.append([t, c])
    return segs


def _ellipsize(line: list, width: float, font: str, size: float, cs: float) -> list:
    color = line[-1][1] if line else "#000000"
    line = list(line)
    while line:
        w, c = line[-1]
        cand = line[:-1] + [(w.rstrip(".,;:") + "…", c)]
        if text_width(" ".join(x for x, _ in cand), font, size, cs) <= width + 0.01:
            return cand
        line.pop()
    return [("…", color)]


class Box:
    """One text box to fit: paragraphs of (word, colour) at a width and a height."""

    def __init__(self, paras: list, w: float, h: float, *, max_lines: Optional[int] = None, indent: float = 0.0):
        self.paras, self.w, self.h, self.max_lines, self.indent = paras, w, h, max_lines, indent
        self.lines: list = []
        self.clipped = False


def _try(box: Box, font: str, size: float, lh: float, gap: float, cs: float) -> bool:
    box.lines = [wrap(p, box.w - box.indent, font, size, cs) for p in box.paras]
    n = sum(len(x) for x in box.lines)
    total = n * size * lh + gap * size * max(0, len(box.paras) - 1)
    if box.max_lines is not None and any(len(x) > box.max_lines for x in box.lines):
        return False
    return total <= box.h + 0.01


def fit(boxes: list, *, font: str, smax: float, smin: float, lh: float, gap: float = 0.0, cs_em: float = 0.0) -> float:
    """Largest size (0.5 pt steps, smax → smin) at which every box fits; all boxes share it. At smin, anything that
    still doesn't fit is cut to the lines that do, the last one ending with …"""
    size = smax
    while True:
        if all(_try(b, font, size, lh, gap, cs_em * size) for b in boxes):
            return size
        nxt = round(size - 0.5, 2)
        if nxt < smin - 1e-6:
            break
        size = nxt
    size = smin
    cs = cs_em * size
    for b in boxes:
        if _try(b, font, size, lh, gap, cs):
            continue
        b.clipped = True
        kept, used = [], 0.0
        for pi, p in enumerate(b.lines):
            room = int((b.h - used + 0.01) // (size * lh))
            if b.max_lines is not None:
                room = min(room, b.max_lines)
            if room <= 0:
                break
            take = p[:room]
            if len(take) < len(p):
                take[-1] = _ellipsize(take[-1], b.w - b.indent, font, size, cs)
                kept.append(take)
                break
            kept.append(take)
            used += len(take) * size * lh + gap * size
        if not kept and b.lines and b.lines[0]:
            kept = [[_ellipsize(b.lines[0][0], b.w - b.indent, font, size, cs)]]
        b.lines = kept
    return size


def _height(box: Box, size: float, lh: float, gap: float) -> float:
    n = sum(len(x) for x in box.lines)
    return n * size * lh + gap * size * max(0, len(box.lines) - 1) if n else 0.0


def _r(v: float) -> float:
    return round(float(v), 2)


def text_item(box: Box, x: float, y: float, *, font: str, size: float, lh: float, color: str, align: str = "l",
              gap: float = 0.0, cs_em: float = 0.0, bullet: Optional[dict] = None, valign: str = "top",
              h: Optional[float] = None, rot: int = 0, outline: Optional[dict] = None, deco: bool = False) -> dict:
    """A text item for the renderers. paras[].lines are lists of [text, colour] segments; paras[].runs is the whole
    paragraph as segments (PowerPoint wraps it itself); dy is the paragraph's top from the box top."""
    cs = cs_em * size
    lh_pt = size * lh
    bh = h if h is not None else box.h
    total = _height(box, size, lh, gap)
    off = (bh - total) / 2 if valign == "middle" else 0.0
    paras, dy = [], off
    for p_words, p_lines in zip(box.paras, box.lines):
        if not p_lines:
            continue
        lines = [_segments(ln) for ln in p_lines]
        widths = [text_width(" ".join(w for w, _ in ln), font, size, cs) for ln in p_lines]
        runs = _segments(p_words) if not box.clipped else _segments([w for ln in p_lines for w in ln])
        para = {"dy": _r(dy), "lines": lines, "widths": [_r(v) for v in widths], "runs": runs}
        if bullet:            # square marker centred on the first line's x-height
            para["mark"] = [0.5, _r(dy + baseline(size, lh_pt) - XH * size / 2 - bullet["size"] / 2)]
        paras.append(para)
        dy += len(p_lines) * lh_pt + gap * size
    item = {"t": "text", "x": _r(x), "y": _r(y), "w": _r(box.w), "h": _r(bh), "font": font, "size": size,
            "lh": _r(lh_pt), "base": _r(baseline(size, lh_pt)), "cs": _r(cs), "color": color, "align": align,
            "indent": _r(box.indent), "gap": _r(gap * size), "paras": paras, "clipped": box.clipped}
    if bullet:
        item["bullet"] = bullet
    if rot:
        item["rot"] = rot
    if outline:
        item["outline"] = outline
    if valign == "middle":
        item["valign"] = "middle"
    if deco:                 # a decorative glyph (section numeral, quote mark) that may sit outside its line box
        item["deco"] = True
    return item


# ------------------------------------------------------------------ shapes ----
def rect(x, y, w, h, *, fill=None, stroke=None, sw=0.0, r=0.0) -> dict:
    return {"t": "rect", "x": _r(x), "y": _r(y), "w": _r(w), "h": _r(h), "fill": fill, "stroke": stroke,
            "sw": _r(sw), "r": _r(r)}


def line(x1, y1, x2, y2, *, stroke, sw=1.0) -> dict:
    return {"t": "line", "x1": _r(x1), "y1": _r(y1), "x2": _r(x2), "y2": _r(y2), "stroke": stroke, "sw": _r(sw)}


def oval(x, y, w, h, *, fill=None, stroke=None, sw=0.0) -> dict:
    return {"t": "oval", "x": _r(x), "y": _r(y), "w": _r(w), "h": _r(h), "fill": fill, "stroke": stroke, "sw": _r(sw)}


def tri(x, y, w, h, *, fill, direction="right") -> dict:
    """Arrow head inside the box (x, y, w, h), pointing right or up."""
    return {"t": "tri", "x": _r(x), "y": _r(y), "w": _r(w), "h": _r(h), "fill": fill, "dir": direction}


# ------------------------------------------------------------------ grid ----
W, H = 960.0, 540.0
MX = 56.0
CW = W - 2 * MX                # 848
KICKER_Y = 40.0
HEAD_Y = 60.0
HEAD = {"font": "extrabold", "smax": 34.0, "smin": 24.0, "lh": 1.08, "cs": -0.02}
BODY_BOTTOM = 476.0
FOOTER_RULE_Y = 500.0


def _kicker(items: list, text: str, x: float, y: float, w: float, th: dict, color: Optional[str] = None) -> float:
    b = Box([words_of(text.upper(), color or th["gold_text"])], w, 14.0, max_lines=1)
    size = fit([b], font="semibold", smax=10.0, smin=7.5, lh=1.3, cs_em=0.18)
    items.append(text_item(b, x, y, font="semibold", size=size, lh=1.3, color=color or th["gold_text"], cs_em=0.18))
    return size * 1.3


def _headline(items: list, s: dict, th: dict) -> float:
    """Kicker + action title. Returns the y where the body starts."""
    if s.get("kicker"):
        _kicker(items, s["kicker"], MX, KICKER_Y, CW, th)
    b = Box([words_of(s["title"], th["ink"], th["gold_text"], s.get("accent", ""))], CW,
            2 * HEAD["smax"] * HEAD["lh"], max_lines=2)
    size = fit([b], font=HEAD["font"], smax=HEAD["smax"], smin=HEAD["smin"], lh=HEAD["lh"], cs_em=HEAD["cs"])
    items.append(text_item(b, MX, HEAD_Y, font=HEAD["font"], size=size, lh=HEAD["lh"], color=th["ink"], cs_em=HEAD["cs"]))
    return HEAD_Y + _height(b, size, HEAD["lh"], 0) + 26.0


def _footer(items: list, n: int, author: str, th: dict) -> None:
    items.append(line(MX, FOOTER_RULE_Y, W - MX, FOOTER_RULE_Y, stroke=th["gold_deep"], sw=0.75))
    color = th["gold_deep"] if th is THEMES["dark"] else th["muted"]
    if author:
        b = Box([words_of(author.upper(), color)], CW - 80, 12.0, max_lines=1)
        size = fit([b], font="semibold", smax=8.0, smin=6.5, lh=1.3, cs_em=0.2)
        items.append(text_item(b, MX, FOOTER_RULE_Y + 9, font="semibold", size=size, lh=1.3, color=color, cs_em=0.2))
    b = Box([words_of(str(n), color)], 60.0, 12.0, max_lines=1)
    fit([b], font="semibold", smax=8.0, smin=8.0, lh=1.3, cs_em=0.1)
    items.append(text_item(b, W - MX - 60, FOOTER_RULE_Y + 9, font="semibold", size=8.0, lh=1.3, color=color,
                           align="r", cs_em=0.1))


def _bullet(color: str, size: float) -> dict:
    return {"color": color, "size": _r(size)}


# ------------------------------------------------------------------ layouts ----
def _cover(s: dict, th: dict, items: list, ctx: dict) -> None:
    kb = s.get("kicker")
    tb = Box([words_of(s["title"], th["ink"], th["gold_text"], s.get("accent", ""))], 780.0, 3 * 52 * 1.06, max_lines=3)
    tsize = fit([tb], font="extrabold", smax=52.0, smin=34.0, lh=1.06, cs_em=-0.02)
    th_h = _height(tb, tsize, 1.06, 0)
    sb, ssize, sh = None, 0.0, 0.0
    if s.get("subtitle"):
        sb = Box([words_of(s["subtitle"], th["muted"])], 700.0, 3 * 20 * 1.4, max_lines=3)
        ssize = fit([sb], font="regular", smax=20.0, smin=15.0, lh=1.4)
        sh = _height(sb, ssize, 1.4, 0)
    block = (34.0 if kb else 0.0) + th_h + (22.0 + sh if sb else 0.0)
    top = max(64.0, 56.0 + (420.0 - 56.0 - block) / 2)
    y = top
    items.append(rect(MX, top - 26, 48.0, 3.0, fill=th["gold"]))
    if kb:
        _kicker(items, kb, MX, y, CW, th)
        y += 34.0
    items.append(text_item(tb, MX, y, font="extrabold", size=tsize, lh=1.06, color=th["ink"], cs_em=-0.02))
    y += th_h
    if sb:
        items.append(text_item(sb, MX, y + 22.0, font="regular", size=ssize, lh=1.4, color=th["muted"]))
    items.append(line(MX, 448.0, W - MX, 448.0, stroke=th["line_strong"], sw=0.75))
    if s.get("presenter"):
        pb = Box([words_of(s["presenter"], th["ink"])], CW, 20.0, max_lines=1)
        psize = fit([pb], font="semibold", smax=14.0, smin=10.0, lh=1.35)
        items.append(text_item(pb, MX, 462.0, font="semibold", size=psize, lh=1.35, color=th["ink"]))


def _agenda(s: dict, th: dict, items: list, ctx: dict) -> None:
    top = _headline(items, s, th)
    n = len(s["items"])
    row_h = min(68.0, (BODY_BOTTOM - top) / n)
    num_w = 64.0
    boxes = [Box([words_of(t, th["ink"], th["gold_text"], money=True)], CW - num_w, row_h - 12.0, max_lines=2)
             for t in s["items"]]
    size = fit(boxes, font="semibold", smax=21.0, smin=14.0, lh=1.25)
    items.append(line(MX, top, W - MX, top, stroke=th["line"], sw=0.75))
    for i, b in enumerate(boxes):
        ry = top + i * row_h
        hgt = _height(b, size, 1.25, 0)
        ty = ry + (row_h - hgt) / 2
        nb = Box([words_of(f"{i + 1:02d}", th["gold_text"])], num_w, size * 1.25, max_lines=1)
        fit([nb], font="extrabold", smax=size, smin=size, lh=1.25)
        items.append(text_item(nb, MX, ty, font="extrabold", size=size, lh=1.25, color=th["gold_text"]))
        items.append(text_item(b, MX + num_w, ty, font="semibold", size=size, lh=1.25, color=th["ink"]))
        items.append(line(MX, ry + row_h, W - MX, ry + row_h, stroke=th["line"], sw=0.75))


def _section(s: dict, th: dict, items: list, ctx: dict) -> None:
    num = f"{ctx['section_no']:02d}"
    nb = Box([words_of(num, th["numeral"])], 470.0, 280.0, max_lines=1)
    fit([nb], font="extrabold", smax=280.0, smin=280.0, lh=1.0, cs_em=-0.04)
    items.append(text_item(nb, -44.0, 122.0, font="extrabold", size=280.0, lh=1.0, color=th["numeral"], cs_em=-0.04,
                           outline={"color": th["numeral"], "w": 1.5}, deco=True))
    x, w = 400.0, W - MX - 400.0
    tb = Box([words_of(s["title"], th["ink"], th["gold_text"], s.get("accent", ""))], w, 3 * 44 * 1.06, max_lines=3)
    tsize = fit([tb], font="extrabold", smax=44.0, smin=30.0, lh=1.06, cs_em=-0.02)
    t_h = _height(tb, tsize, 1.06, 0)
    sb, ssize, s_h = None, 0.0, 0.0
    if s.get("subtitle"):
        sb = Box([words_of(s["subtitle"], th["muted"])], w, 3 * 19 * 1.4, max_lines=3)
        ssize = fit([sb], font="regular", smax=19.0, smin=14.0, lh=1.4)
        s_h = _height(sb, ssize, 1.4, 0)
    block = 30.0 + t_h + (18.0 + s_h if sb else 0.0)
    y = max(64.0, 56.0 + (BODY_BOTTOM - 56.0 - block) / 2)
    _kicker(items, s.get("kicker") or f"Section {num}", x, y, w, th)
    y += 30.0
    items.append(text_item(tb, x, y, font="extrabold", size=tsize, lh=1.06, color=th["ink"], cs_em=-0.02))
    if sb:
        items.append(text_item(sb, x, y + t_h + 18.0, font="regular", size=ssize, lh=1.4, color=th["muted"]))


def _bullets(s: dict, th: dict, items: list, ctx: dict) -> None:
    top = _headline(items, s, th)
    b = Box([words_of(t, th["ink"], th["gold_text"], money=True) for t in s["bullets"]], 800.0, BODY_BOTTOM - top,
            indent=26.0)
    size = fit([b], font="regular", smax=21.0, smin=13.0, lh=1.38, gap=0.7)
    items.append(text_item(b, MX, top, font="regular", size=size, lh=1.38, color=th["ink"], gap=0.7,
                           bullet=_bullet(th["gold"], max(5.0, size * 0.32))))


def _two_column(s: dict, th: dict, items: list, ctx: dict) -> None:
    top = _headline(items, s, th)
    ba = s.get("style") == "before_after"
    gap = 56.0 if ba else 20.0
    pw = (CW - gap) / 2
    full = BODY_BOTTOM - top
    pad = 22.0
    xs = [MX, MX + pw + gap]
    sides = [s["left"], s["right"]]
    head_colors = [th["ink"], th["gold_text"] if ba else th["ink"]]
    hb = [Box([words_of(c["heading"], head_colors[i])], pw - 2 * pad, 2 * 19 * 1.2, max_lines=2) for i, c in enumerate(sides)]
    hsize = fit(hb, font="bold", smax=19.0, smin=14.0, lh=1.2)
    hh = max(_height(b, hsize, 1.2, 0) for b in hb)
    ptop = top + pad + hh + 14.0
    pb = [Box([words_of(t, th["ink"], th["gold_text"], money=True) for t in c["points"]], pw - 2 * pad,
              top + full - pad - ptop, indent=18.0) for c in sides]
    psize = fit(pb, font="regular", smax=18.0, smin=12.0, lh=1.36, gap=0.55)
    p_h = max(_height(b, psize, 1.36, 0.55) for b in pb)
    ph = min(full, max(full * 0.6, ptop - top + p_h + pad + 6.0))      # panels hug their content
    for i, x in enumerate(xs):
        gold_edge = ba and i == 1
        items.append(rect(x, top, pw, ph, fill=th["panel"], stroke=th["gold"] if gold_edge else th["line"],
                          sw=1.25 if gold_edge else 0.75, r=14.0))
    if ba:
        cx, cy = MX + pw + gap / 2, top + ph / 2
        items.append(line(cx - 14, cy, cx + 4, cy, stroke=th["gold"], sw=2.0))
        items.append(tri(cx + 2, cy - 8, 12.0, 16.0, fill=th["gold"], direction="right"))
    for i, x in enumerate(xs):
        items.append(text_item(hb[i], x + pad, top + pad, font="bold", size=hsize, lh=1.2, color=head_colors[i]))
        marker = th["gold"] if (not ba or i == 1) else th["faint"]
        items.append(text_item(pb[i], x + pad, ptop, font="regular", size=psize, lh=1.36, color=th["ink"], gap=0.55,
                               bullet=_bullet(marker, max(4.0, psize * 0.3)), h=top + ph - pad - ptop))


def _big_number(s: dict, th: dict, items: list, ctx: dict) -> None:
    top = _headline(items, s, th)
    n = len(s["stats"])
    gap, pad = 20.0, 26.0
    cw = (CW - gap * (n - 1)) / n
    vmax = {1: 110.0, 2: 84.0, 3: 64.0}[n]
    vb = [Box([words_of(st["value"], th["gold_text"])], cw - 2 * pad, vmax * 1.0, max_lines=1) for st in s["stats"]]
    vsize = fit(vb, font="extrabold", smax=vmax, smin=24.0, lh=1.0, cs_em=-0.04)
    lb = [Box([words_of(st["label"], th["ink"])], cw - 2 * pad, 4 * 18 * 1.36, max_lines=4) for st in s["stats"]]
    lsize = fit(lb, font="regular", smax=18.0, smin=12.5, lh=1.36)
    l_h = max(_height(b, lsize, 1.36, 0) for b in lb)
    nb, nsize, n_h = None, 0.0, 0.0
    if s.get("note"):
        nb = Box([words_of(s["note"], th["muted"])], CW, 2 * 14 * 1.36, max_lines=2)
        nsize = fit([nb], font="regular", smax=14.0, smin=11.0, lh=1.36)
        n_h = _height(nb, nsize, 1.36, 0)
    room = BODY_BOTTOM - top - (18.0 + n_h if nb else 0.0)
    card_h = min(room, pad + vsize + 18.0 + 2.0 + 16.0 + l_h + pad)
    cy = top + (room - card_h) * 0.4
    if nb:
        items.append(text_item(nb, MX, cy + card_h + 18.0, font="regular", size=nsize, lh=1.36, color=th["muted"]))
    for i in range(n):
        x = MX + i * (cw + gap)
        items.append(rect(x, cy, cw, card_h, fill=th["panel"], stroke=th["line"], sw=0.75, r=14.0))
        items.append(text_item(vb[i], x + pad, cy + pad, font="extrabold", size=vsize, lh=1.0, color=th["gold_text"],
                               cs_em=-0.04))
        items.append(rect(x + pad, cy + pad + vsize + 18.0, 36.0, 2.0, fill=th["gold"]))
        items.append(text_item(lb[i], x + pad, cy + pad + vsize + 36.0, font="regular", size=lsize, lh=1.36,
                               color=th["ink"]))


def _quote(s: dict, th: dict, items: list, ctx: dict) -> None:
    has_k = bool(s.get("kicker"))
    if has_k:
        _kicker(items, s["kicker"], MX, KICKER_Y, CW, th)
    qb = Box([words_of(s["quote"], th["ink"], th["gold_text"], money=True)], 800.0, 6 * 32 * 1.3, max_lines=6)
    qsize = fit([qb], font="semibold", smax=32.0, smin=19.0, lh=1.3, cs_em=-0.01)
    q_h = _height(qb, qsize, 1.3, 0)
    bb, b_h = None, 0.0
    if s.get("by"):
        bb = Box([words_of("— " + s["by"], th["muted"])], 800.0, 22.0, max_lines=1)
        bsize = fit([bb], font="regular", smax=16.0, smin=12.0, lh=1.35)
        b_h = bsize * 1.35
    mark_h = 64.0
    block = mark_h + q_h + (20.0 + b_h if bb else 0.0)
    top_min = 72.0 if has_k else 48.0
    y = max(top_min, top_min + (BODY_BOTTOM - top_min - block) / 2)
    mb = Box([words_of("“", th["gold_text"])], 120.0, 120.0, max_lines=1)
    fit([mb], font="extrabold", smax=120.0, smin=120.0, lh=1.0)
    items.append(text_item(mb, MX - 6, y - 10.0, font="extrabold", size=120.0, lh=1.0, color=th["gold_text"], h=mark_h,
                           deco=True))
    y += mark_h
    items.append(text_item(qb, MX, y, font="semibold", size=qsize, lh=1.3, color=th["ink"], cs_em=-0.01))
    if bb:
        items.append(text_item(bb, MX, y + q_h + 20.0, font="regular", size=bsize, lh=1.35, color=th["muted"]))


def _num_circle(items: list, x: float, y: float, d: float, n: int, th: dict) -> None:
    items.append(oval(x, y, d, d, fill=th["bg"], stroke=th["gold"], sw=1.25))
    b = Box([words_of(str(n), th["gold_text"])], d, d, max_lines=1)
    size = round(d * 0.42 * 2) / 2
    fit([b], font="extrabold", smax=size, smin=size, lh=1.2)
    items.append(text_item(b, x, y, font="extrabold", size=size, lh=1.2, color=th["gold_text"], align="c",
                           valign="middle", h=d))


def _steps(s: dict, th: dict, items: list, ctx: dict) -> None:
    top = _headline(items, s, th)
    steps = s["steps"]
    n = len(steps)
    if n <= 4:
        gap, d = 24.0, 36.0
        cw = (CW - gap * (n - 1)) / n
        tb = [Box([words_of(st["title"], th["ink"])], cw, 3 * 19 * 1.2, max_lines=3) for st in steps]
        tsize = fit(tb, font="bold", smax=19.0, smin=13.0, lh=1.2)
        t_h = max(_height(b, tsize, 1.2, 0) for b in tb)
        ttop = top + d + 18.0
        xtop = ttop + t_h + 10.0
        xb = [Box([words_of(st.get("text", ""), th["muted"], th["gold_text"], money=True)], cw, BODY_BOTTOM - xtop)
              for st in steps]
        xsize = fit(xb, font="regular", smax=16.0, smin=11.5, lh=1.42)
        x_h = max(_height(b, xsize, 1.42, 0) for b in xb)
        shift = max(0.0, (BODY_BOTTOM - xtop - x_h) * 0.35)             # a short row sits a little lower
        top, ttop, xtop = top + shift, ttop + shift, xtop + shift
        for b in xb:
            b.h = BODY_BOTTOM - xtop
        for i in range(n):
            x = MX + i * (cw + gap)
            if i < n - 1:
                items.append(line(x + d + 8, top + d / 2, x + cw + gap - 8, top + d / 2, stroke=th["line_strong"], sw=1.0))
            _num_circle(items, x, top, d, i + 1, th)
            items.append(text_item(tb[i], x, ttop, font="bold", size=tsize, lh=1.2, color=th["ink"]))
            if steps[i].get("text"):
                items.append(text_item(xb[i], x, xtop, font="regular", size=xsize, lh=1.42, color=th["muted"]))
        return
    rows = 3
    gap, d = 32.0, 32.0
    cw = (CW - gap) / 2
    row_h = (BODY_BOTTOM - top) / rows
    inner = cw - d - 16.0
    tb = [Box([words_of(st["title"], th["ink"])], inner, 2 * 17 * 1.2, max_lines=2) for st in steps]
    tsize = fit(tb, font="bold", smax=17.0, smin=12.5, lh=1.2)
    t_h = max(_height(b, tsize, 1.2, 0) for b in tb)
    xb = [Box([words_of(st.get("text", ""), th["muted"], th["gold_text"], money=True)], inner, row_h - t_h - 6.0 - 14.0)
          for st in steps]
    xsize = fit([b for b, st in zip(xb, steps) if st.get("text")] or xb, font="regular", smax=14.5, smin=11.0, lh=1.36)
    left = (n + 1) // 2
    for i in range(n):
        col, row = (0, i) if i < left else (1, i - left)
        x, y = MX + col * (cw + gap), top + row * row_h
        _num_circle(items, x, y, d, i + 1, th)
        items.append(text_item(tb[i], x + d + 16.0, y + 4.0, font="bold", size=tsize, lh=1.2, color=th["ink"]))
        if steps[i].get("text"):
            items.append(text_item(xb[i], x + d + 16.0, y + 4.0 + t_h + 6.0, font="regular", size=xsize, lh=1.36,
                                   color=th["muted"]))
    items.append(line(MX + cw + gap / 2, top, MX + cw + gap / 2, BODY_BOTTOM - 8.0, stroke=th["line"], sw=0.75))


def _grid_2x2(s: dict, th: dict, items: list, ctx: dict) -> None:
    top = _headline(items, s, th)
    x0, x1 = MX + 34.0, W - MX
    y0, y1 = top, BODY_BOTTOM - 26.0
    ax = MX + 20.0
    items.append(line(ax, y1 + 8, ax, y0 + 8, stroke=th["line_strong"], sw=1.25))
    items.append(tri(ax - 5, y0, 10.0, 10.0, fill=th["line_strong"], direction="up"))
    items.append(line(x0, y1 + 12, x1 - 8, y1 + 12, stroke=th["line_strong"], sw=1.25))
    items.append(tri(x1 - 10, y1 + 7, 10.0, 10.0, fill=th["line_strong"], direction="right"))
    ylen = y1 - y0
    yb = Box([words_of(s["y_axis"].upper(), th["muted"])], ylen, 13.0, max_lines=1)
    ysize = fit([yb], font="semibold", smax=9.5, smin=7.0, lh=1.3, cs_em=0.14)
    items.append(text_item(yb, MX + 6 - ylen / 2, y0 + ylen / 2 - 6.5, font="semibold", size=ysize, lh=1.3,
                           color=th["muted"], align="c", cs_em=0.14, rot=-90))
    xbx = Box([words_of(s["x_axis"].upper(), th["muted"])], x1 - x0 - 16.0, 13.0, max_lines=1)
    xsz = fit([xbx], font="semibold", smax=9.5, smin=7.0, lh=1.3, cs_em=0.14)
    items.append(text_item(xbx, x0, y1 + 18.0, font="semibold", size=xsz, lh=1.3, color=th["muted"], align="r",
                           cs_em=0.14))
    g = 12.0
    cw, ch = (x1 - x0 - g) / 2, (y1 - y0 - g) / 2
    pad = 18.0
    hl = s.get("highlight")
    tb = [Box([words_of(c["title"], th["gold_text"] if i == hl else th["ink"])], cw - 2 * pad, 2 * 18 * 1.2, max_lines=2)
          for i, c in enumerate(s["cells"])]
    tsize = fit(tb, font="bold", smax=18.0, smin=13.0, lh=1.2)
    t_h = max(_height(b, tsize, 1.2, 0) for b in tb)
    xb = [Box([words_of(c.get("text", ""), th["muted"], th["gold_text"], money=True)], cw - 2 * pad, ch - 2 * pad - t_h - 8.0)
          for c in s["cells"]]
    xsize = fit(xb, font="regular", smax=15.0, smin=11.0, lh=1.38)
    for i, c in enumerate(s["cells"]):
        x, y = x0 + (i % 2) * (cw + g), y0 + (i // 2) * (ch + g)
        on = i == hl
        items.append(rect(x, y, cw, ch, fill=th["panel"], stroke=th["gold"] if on else th["line"], sw=1.5 if on else 0.75,
                          r=14.0))
        items.append(text_item(tb[i], x + pad, y + pad, font="bold", size=tsize, lh=1.2,
                               color=th["gold_text"] if on else th["ink"]))
        if c.get("text"):
            items.append(text_item(xb[i], x + pad, y + pad + t_h + 8.0, font="regular", size=xsize, lh=1.38,
                                   color=th["muted"]))


def _col_widths(cols: list, rows: list, total: float) -> list:
    n = len(cols)
    weights = []
    for c in range(n):
        cells = [cols[c]] + [r[c] for r in rows]
        avg = sum(len(x) for x in cells) / len(cells)
        weights.append(max(8.0, avg) ** 0.75)
    s = sum(weights)
    ws = [max(total * 0.16, total * w / s) for w in weights]
    k = total / sum(ws)
    return [w * k for w in ws]


def _table(s: dict, th: dict, items: list, ctx: dict) -> None:
    top = _headline(items, s, th)
    cols, rows = s["columns"], s["rows"]
    widths = _col_widths(cols, rows, CW)
    px, py = 12.0, 9.0
    avail = BODY_BOTTOM - top

    def fit_row(r: list, size: float) -> None:
        fit(r[:1], font="semibold", smax=size, smin=size, lh=1.3)       # first column semibold, the rest regular
        if len(r) > 1:
            fit(r[1:], font="regular", smax=size, smin=size, lh=1.3)

    size = 16.0
    while True:
        hs = max(9.0, min(12.0, round(size * 0.8 * 2) / 2))
        hb = [Box([words_of(c.upper(), th["muted"])], w - 2 * px, 2 * hs * 1.25, max_lines=2) for c, w in zip(cols, widths)]
        fit(hb, font="semibold", smax=hs, smin=hs, lh=1.25, cs_em=0.06)
        head_h = max(_height(b, hs, 1.25, 0) for b in hb) + 2 * py
        body = [[Box([words_of(cell, th["ink"], th["gold_text"], money=True)], w - 2 * px, 10_000.0)
                 for cell, w in zip(r, widths)] for r in rows]
        for r in body:
            fit_row(r, size)
        row_hs = [max(max(1, sum(len(x) for x in b.lines)) * size * 1.3 for b in r) + 2 * py for r in body]
        if head_h + sum(row_hs) <= avail + 0.01 or size <= 11.0:
            break
        size = round(size - 0.5, 2)
    if head_h + sum(row_hs) > avail + 0.01:              # last resort: cut each row to its share at 11 pt
        share = (avail - head_h) / len(rows)
        for r in body:
            for b in r:
                b.h = share - 2 * py
            fit_row(r, size)
        row_hs = [share] * len(rows)
    spare = avail - head_h - sum(row_hs)
    if spare > 0:                                        # spare room goes into the row padding (up to 15 pt)
        extra = min(6.0, spare / (2 * (len(rows) + 1)))
        py += extra
        head_h += 2 * extra
        row_hs = [h + 2 * extra for h in row_hs]
    xs = [MX + sum(widths[:i]) for i in range(len(widths))]
    rules = [line(MX, top + head_h, W - MX, top + head_h, stroke=th["gold_deep"], sw=1.25)]
    cells = []
    for c, b in enumerate(hb):
        b.h = head_h - 2 * py
        cells.append(text_item(b, xs[c] + px, top + py, font="semibold", size=hs, lh=1.25, color=th["muted"], cs_em=0.06))
    y = top + head_h
    for ri, r in enumerate(body):
        for c, b in enumerate(r):
            b.h = row_hs[ri] - 2 * py
            cells.append(text_item(b, xs[c] + px, y + py, font="semibold" if c == 0 else "regular", size=size, lh=1.3,
                                   color=th["ink"]))
        y += row_hs[ri]
        rules.append(line(MX, y, W - MX, y, stroke=th["line_strong"] if th is THEMES["light"] else th["line"], sw=0.75))
    items.append({"t": "table", "x": _r(MX), "y": _r(top), "w": _r(CW), "cols": [_r(w) for w in widths],
                  "rows": [_r(head_h)] + [_r(h) for h in row_hs], "px": px, "py": py, "rules": rules, "cells": cells,
                  "head_rule": th["gold_deep"], "row_rule": rules[-1]["stroke"]})


def _closing(s: dict, th: dict, items: list, ctx: dict) -> None:
    tb = Box([words_of(s["title"], th["ink"], th["gold_text"], s.get("accent", ""))], 800.0, 3 * 46 * 1.06, max_lines=3)
    tsize = fit([tb], font="extrabold", smax=46.0, smin=30.0, lh=1.06, cs_em=-0.02)
    t_h = _height(tb, tsize, 1.06, 0)
    xb, xsize, x_h = None, 0.0, 0.0
    if s.get("text"):
        xb = Box([words_of(s["text"], th["muted"], th["gold_text"], money=True)], 720.0, 4 * 20 * 1.45, max_lines=4)
        xsize = fit([xb], font="regular", smax=20.0, smin=14.0, lh=1.45)
        x_h = _height(xb, xsize, 1.45, 0)
    ab = Box([words_of(s["action"], th["on_gold"])], 800.0 - 48.0, 2 * 17 * 1.25, max_lines=2)
    asize = fit([ab], font="extrabold", smax=17.0, smin=12.5, lh=1.25)
    a_h = _height(ab, asize, 1.25, 0)
    a_w = max(text_width(" ".join(w for w, _ in ln), "extrabold", asize) for ln in (ab.lines[0] if ab.lines else [[]]))
    pill_h = a_h + 2 * 14.0
    block = 30.0 + t_h + (20.0 + x_h if xb else 0.0) + 34.0 + pill_h
    y = max(56.0, 56.0 + (BODY_BOTTOM - 56.0 - block) / 2)
    _kicker(items, s.get("kicker") or "Next step", MX, y, CW, th)
    y += 30.0
    items.append(text_item(tb, MX, y, font="extrabold", size=tsize, lh=1.06, color=th["ink"], cs_em=-0.02))
    y += t_h
    if xb:
        items.append(text_item(xb, MX, y + 20.0, font="regular", size=xsize, lh=1.45, color=th["muted"]))
        y += 20.0 + x_h
    y += 34.0
    pw = min(800.0, a_w + 48.0 + 6.0)                   # 6 pt slack so PowerPoint never wraps the last word
    items.append(rect(MX, y, pw, pill_h, fill=th["gold"], r=min(pill_h / 2, 26.0)))
    ab.w = pw - 48.0
    items.append(text_item(ab, MX + 24.0, y + 14.0, font="extrabold", size=asize, lh=1.25, color=th["on_gold"]))


DRAW = {"title": _cover, "agenda": _agenda, "section": _section, "bullets": _bullets, "two_column": _two_column,
        "big_number": _big_number, "quote": _quote, "steps": _steps, "grid_2x2": _grid_2x2, "table": _table,
        "closing": _closing}


def layout_slide(s: dict, *, theme: str = "dark", n: int = 1, author: str = "", section_no: int = 1) -> dict:
    th = THEMES.get(theme, THEMES["dark"])
    items: list = []
    DRAW[s["layout"]](s, th, items, {"section_no": section_no, "n": n})
    if s["layout"] != "title":
        _footer(items, n, author, th)
    bg = {"color": th["bg"], "grad": None}
    stops = th["warm"] if s["layout"] == "closing" else th["lift"]
    if stops:
        corner = (W, H) if s["layout"] == "closing" else ((0.0, 0.0) if n % 2 else (W, 0.0))
        bg["grad"] = {"cx": corner[0], "cy": corner[1], "rx": 700.0, "ry": 500.0, "stops": stops}
    return {"layout": s["layout"], "n": n, "bg": bg, "items": items}


def layout_deck(deck: dict, *, theme: str = "dark", author: str = "") -> list:
    out, sec = [], 0
    for i, s in enumerate(deck["slides"]):
        if s["layout"] == "section":
            sec += 1
        out.append(layout_slide(s, theme=theme, n=i + 1, author=author, section_no=max(1, sec)))
    return out


def clipped(slides: list) -> list:
    """[(slide number, item index)] for any text that had to be cut — the overflow guard in the tests."""
    hits = []
    for sl in slides:
        for i, it in enumerate(sl["items"]):
            texts = it["cells"] if it["t"] == "table" else [it] if it["t"] == "text" else []
            hits += [(sl["n"], i) for t in texts if t.get("clipped")]
    return hits
