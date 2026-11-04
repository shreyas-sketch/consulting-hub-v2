"""Presentation Builder: our own deck engine. Sources, PowerPoint + PDF files, the overflow guard, plan and limit,
refunds, free owner-only edits, and owner-only files."""
import io

import pytest
from conftest import qa_login, run

ANSWER = ("The real problem is margin leakage because discounts and wastage grew with the new stores. In grocery this "
          "is common. First split profit by store, then cut slow products, then fix fresh ordering. Measure wastage % weekly.")
TEXT = {"source": "text", "title": "Cutting wastage at Sharma Fresh Mart", "audience": "Owner and store managers",
        "notes": "Wastage is 9% against 4-5% at good stores. Discounts doubled. Plan: order by sell-through, mark down early, "
                 "cut slow products. Saves about ₹40 lakh a year.", "slides": 8, "tone": "boardroom"}
VENDOR_WORDS = ("gamma", "anthropic", "claude", "openai", "gpt-", "sonnet", "haiku")


def _used(c, meter="presentation"):
    return c.get("/api/me/plan").json()["limits"][meter]["used"]


def _pptx(data: bytes):
    from pptx import Presentation
    return Presentation(io.BytesIO(data))


def _pdf_pages(data: bytes) -> int:
    from pypdf import PdfReader
    return len(PdfReader(io.BytesIO(data)).pages)


def _files_ok(c, d: dict, n: int):
    """Both files download through our route, python-pptx opens the PowerPoint, pypdf reads the PDF; n slides each."""
    p = c.get(d["files"]["pptx"]["url"])
    assert p.status_code == 200 and p.headers["content-disposition"].startswith("attachment")
    assert p.headers["content-disposition"].endswith('.pptx"') and "presentationml" in p.headers["content-type"]
    prs = _pptx(p.content)
    assert len(prs.slides) == n
    assert prs.slide_width == 12192000 and prs.slide_height == 6858000            # 16:9
    f = c.get(d["files"]["pdf"]["url"])
    assert f.status_code == 200 and f.content.startswith(b"%PDF") and f.headers["content-type"] == "application/pdf"
    assert _pdf_pages(f.content) == n
    return prs, f.content


def _texts(prs) -> str:
    out = []
    for s in prs.slides:
        for sh in s.shapes:
            if sh.has_text_frame:
                out.append(sh.text_frame.text)
            if getattr(sh, "has_table", False) and sh.has_table:
                out += [cell.text for row in sh.table.rows for cell in row.cells]
    return "\n".join(out)


# ------------------------------------------------------------------ happy paths ----
def test_text_deck_makes_pptx_and_pdf(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    opts = c.get("/api/decks/options").json()
    assert [t["key"] for t in opts["themes"]] == ["dark", "light"] and len(opts["tones"]) == 5
    assert opts["slides"] == {"min": 6, "max": 14, "default": 8} and opts["limits"]["bullet"] == 120
    r = c.post("/api/decks", json=TEXT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["slides"] == 8 and len(d["deck"]["slides"]) == 8 and len(d["layout"]) == 8
    assert d["deck"]["slides"][0]["layout"] == "title" and d["deck"]["slides"][-1]["layout"] == "closing"
    assert d["theme"] == "dark" and d["tone"] == "boardroom" and d["status"] == "ready"
    assert d["layout"][0]["bg"]["color"] == "#14151A" and d["canvas"] == {"w": 960.0, "h": 540.0}
    low = r.text.lower()
    assert not any(w in low for w in VENDOR_WORDS) and "gen_id" not in low and "export_url" not in low
    prs, pdf = _files_ok(c, d, 8)
    assert "Wastage" in _texts(prs) or "wastage" in _texts(prs)
    assert prs.core_properties.author == "Demo Member"                             # the member's name, never a tool
    assert d["author"] == "Demo Member" and d["deck"]["slides"][0]["presenter"] == "Demo Member"
    assert not any(w.encode() in pdf.lower() for w in VENDOR_WORDS)
    inline = c.get(d["files"]["pdf"]["url"] + "&inline=1")
    assert inline.headers["content-disposition"].startswith("inline")
    assert c.get("/api/decks").json()["items"][0] == {k: d[k] for k in ("id", "title", "source", "slides", "theme",
                                                                         "created_at", "updated_at")}
    assert c.get(f"/api/decks/{d['id']}").json()["layout"] == d["layout"]
    assert _used(c) == 1


def test_case_deck_uses_the_strategic_thinking_framework(seeded_client, monkeypatch):
    import llm
    seen = []
    real = llm.complete_json

    async def spy(**kw):
        seen.append(kw)
        return await real(**kw)
    monkeypatch.setattr(llm, "complete_json", spy)
    c = seeded_client
    qa_login(c, plan="member")
    a = c.post("/api/cases/retail-chain-margins/answer", json={"answer": ANSWER}).json()["answer"]
    src = c.get("/api/decks/sources").json()
    assert src["answers"][0]["id"] == a["id"] and src["answers"][0]["company"] == "Sharma Fresh Mart"
    r = c.post("/api/decks", json={"source": "case", "id": a["id"], "slides": 14, "theme": "light"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["title"].startswith("Sharma Fresh Mart") and d["slides"] == 14 and d["theme"] == "light"
    assert d["layout"][0]["bg"]["color"] == "#FFFFFF"
    call = [k for k in seen if k["task"] == "deck_writer"][-1]
    assert call["model"] == "strong"
    p = call["prompt"]
    assert "Step 1 Understand Scope" in p and "Implementation Charter" in p and "grid_2x2" in p
    assert "Selling more, earning less" in p and ANSWER[:40] in p and "Margin leak check" in p and "₹" in p
    assert "exactly 14 slides" in p
    assert "Never mention or hint at AI" in call["system"]
    layouts = {s["layout"] for s in d["deck"]["slides"]}
    assert {"two_column", "big_number", "table", "grid_2x2", "steps"} <= layouts
    prs, _ = _files_ok(c, d, 14)
    assert "Do first" in _texts(prs)


def test_brief_deck(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    b = c.post("/api/briefs", json={"company": "Haldiram's", "meeting_with": "Head of Ops"}).json()
    assert c.get("/api/decks/sources").json()["briefs"][0]["id"] == b["id"]
    r = c.post("/api/decks", json={"source": "brief", "id": b["id"], "slides": 6})
    assert r.status_code == 200, r.text
    d = r.json()
    assert "Haldiram's" in d["title"] and d["slides"] == 6 and d["ref_id"] == b["id"]
    _files_ok(c, d, 6)


def test_fourteen_slides_from_notes_cover_every_layout(seeded_client):
    from features import deck_layout as dl
    c = seeded_client
    qa_login(c, plan="l1")
    d = c.post("/api/decks", json={**TEXT, "slides": 14}).json()
    assert {s["layout"] for s in d["deck"]["slides"]} == set(dl.LAYOUTS)
    assert dl.clipped(d["layout"]) == []
    _files_ok(c, d, 14)


def test_bad_source_gives_go_back(seeded_client):
    c = seeded_client
    qa_login(c, plan="member", phone="9000000031")
    b = c.post("/api/briefs", json={"company": "Zydus"}).json()
    c.post("/api/auth/logout")
    qa_login(c, plan="member")
    assert c.post("/api/decks", json={"source": "brief", "id": b["id"]}).status_code == 404     # someone else's brief
    assert c.post("/api/decks", json={"source": "case", "id": "nope"}).status_code == 404
    assert c.post("/api/decks", json={"source": "text", "title": "Hi", "notes": "short"}).status_code == 400
    assert c.post("/api/decks", json={**TEXT, "slides": 15}).status_code == 422
    assert c.post("/api/decks", json={**TEXT, "slides": 5}).status_code == 422
    assert _used(c) == 0


# ------------------------------------------------------------------ plan, limit, refunds ----
def test_free_locked_and_member_limit(seeded_client):
    c = seeded_client
    qa_login(c, plan="free")
    r = c.post("/api/decks", json=TEXT)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    c.post("/api/auth/logout")
    qa_login(c, plan="member")
    assert c.post("/api/decks", json=TEXT).status_code == 200
    assert c.post("/api/decks", json=TEXT).status_code == 200
    r = c.post("/api/decks", json=TEXT)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_ai_error_refunds(seeded_client, monkeypatch):
    import llm

    async def down(**kw):
        raise llm.LLMError("timeout")
    monkeypatch.setattr(llm, "complete_json", down)
    c = seeded_client
    qa_login(c, plan="member")
    r = c.post("/api/decks", json=TEXT)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy"
    assert "AI is busy" in r.json()["detail"]["msg"] and _used(c) == 0
    assert c.get("/api/decks").json()["items"] == []


@pytest.mark.parametrize("bad", [
    {"slides": [{"layout": "nope", "title": "x"}] * 8},                                  # unknown layout
    {"slides": "eight slides"},                                                          # no list
    {"slides": [{"layout": "title", "title": "A deck"}] + [{"layout": "bullets", "title": "Point", "bullets": ["one"]}] * 6
     + [{"layout": "closing", "title": "Go", "action": "Call me"}]},                      # too few bullets
    {"slides": [{"layout": "bullets", "title": "Point", "bullets": ["a", "b", "c"]}] * 8},  # no title / closing slide
    {"slides": [{"layout": "title", "title": "A deck"}, {"layout": "closing", "title": "Go", "action": "Call"}]},  # too short
])
def test_wrong_shape_from_the_ai_refunds(seeded_client, monkeypatch, bad):
    import llm

    async def wrong(**kw):
        return bad
    monkeypatch.setattr(llm, "complete_json", wrong)
    c = seeded_client
    qa_login(c, plan="member")
    r = c.post("/api/decks", json=TEXT)
    assert r.status_code == 503 and _used(c) == 0


def test_too_long_ai_text_is_cut_at_a_word_not_failed(seeded_client, monkeypatch):
    import llm
    from features import deck_layout as dl
    long = "Profit fell from four percent of sales to one and a half percent " * 4

    async def wordy(**kw):
        d = kw["fake"]()
        d["slides"][1] = {"layout": "bullets", "title": long, "bullets": [long, "Short point", "Another point"],
                          "presenter": "Made up"}
        d["slides"][0]["presenter"] = "Someone else"
        return d
    monkeypatch.setattr(llm, "complete_json", wordy)
    c = seeded_client
    qa_login(c, plan="member")
    d = c.post("/api/decks", json=TEXT).json()
    s = d["deck"]["slides"][1]
    assert len(s["title"]) <= dl.LIMITS["title"] and s["title"].endswith("…") and " " in s["title"]
    assert len(s["bullets"][0]) <= dl.LIMITS["bullet"] and s["bullets"][0].endswith("…")
    assert d["deck"]["slides"][0]["presenter"] == "Demo Member" and "presenter" not in s     # the server sets it
    assert dl.clipped(d["layout"]) == []


# ------------------------------------------------------------------ the overflow guard ----
POOL = ["Maximum", "Working", "Momentum", "Wholesale", "Mumbai", "₹45,00,000", "MW", "Women", "Owners", "Growth",
        "Workflow", "Margin"]


def _wide(n: int, k: int = 0) -> str:
    """Exactly n characters of wide-letter words (about 20% wider than ordinary English)."""
    out, i = "", k
    while len(out) < n:
        out += (" " if out else "") + POOL[i % len(POOL)]
        i += 1
    out = out[:n].rstrip()
    return out + "M" * (n - len(out))


def _longest_slides() -> list:
    from features import deck_layout as dl
    L = dl.LIMITS

    def t(key, i=0):
        return _wide(L[key], i)

    def head():
        return {"kicker": t("kicker"), "title": t("title"), "accent": t("accent"), "notes": t("notes")}
    col = lambda k: {"heading": t("col_heading", k), "points": [t("col_point", i + k) for i in range(5)]}  # noqa: E731
    out = [
        {"layout": "title", "kicker": t("kicker"), "title": t("cover_title"), "subtitle": t("subtitle"), "presenter": t("presenter")},
        {"layout": "agenda", **head(), "items": [t("agenda_item", i) for i in range(6)]},
        {"layout": "section", "kicker": t("kicker"), "title": t("section_title"), "subtitle": t("section_sub")},
        {"layout": "bullets", **head(), "bullets": [t("bullet", i) for i in range(6)]},
        {"layout": "two_column", **head(), "style": "before_after", "left": col(0), "right": col(3)},
        {"layout": "two_column", **head(), "style": "compare", "left": col(1), "right": col(2)},
        {"layout": "quote", "kicker": t("kicker"), "quote": t("quote"), "by": t("quote_by")},
        {"layout": "grid_2x2", **head(), "x_axis": t("axis"), "y_axis": t("axis", 2), "highlight": 1,
         "cells": [{"title": t("cell_title", i), "text": t("cell_text", i)} for i in range(4)]},
        {"layout": "closing", "kicker": t("kicker"), "title": t("closing_title"), "text": t("closing_text"), "action": t("action")},
    ]
    for n in (1, 2, 3):
        out.append({"layout": "big_number", **head(), "note": t("stat_note"),
                    "stats": [{"value": t("stat_value", i), "label": t("stat_label", i)} for i in range(n)]})
    for n in (3, 4, 5, 6):
        out.append({"layout": "steps", **head(), "steps": [{"title": t("step_title", i), "text": t("step_text", i)} for i in range(n)]})
    for ncol in (2, 3, 4):
        out.append({"layout": "table", **head(), "columns": [t("th", i) for i in range(ncol)],
                    "rows": [[t("td", i + j) for i in range(ncol)] for j in range(5)]})
    return out


def _text_items(slide: dict) -> list:
    out = []
    for it in slide["items"]:
        if it["t"] == "text":
            out.append(it)
        elif it["t"] == "table":
            out += it["cells"]
    return out


def _assert_inside(slide: dict):
    from features import deck_layout as dl
    for it in _text_items(slide):
        used = sum(len(p["lines"]) for p in it["paras"]) * it["lh"] + it["gap"] * max(0, len(it["paras"]) - 1)
        if it.get("deco"):
            continue
        assert used <= it["h"] + 0.5, (slide["layout"], it["paras"][0]["runs"])
        for p in it["paras"]:
            for w in p["widths"]:
                assert w <= it["w"] - it["indent"] + 0.5, (slide["layout"], p["lines"])
        x, y, w, h = it["x"], it["y"], it["w"], it["h"]
        if it.get("rot"):                             # a quarter turn: the box on the slide is h wide and w tall
            cx, cy = x + w / 2, y + h / 2
            x, y, w, h = cx - h / 2, cy - w / 2, h, w
        assert x >= 0 and x + w <= dl.W + 0.01 and y >= 0 and y + h <= dl.H + 0.01, (slide["layout"], it["paras"][0]["runs"])
    for it in slide["items"]:                         # nothing but the footer goes below the footer rule
        if it["t"] in ("text", "rect") and it["y"] < dl.FOOTER_RULE_Y:
            assert it["y"] + it["h"] <= dl.FOOTER_RULE_Y + 0.01, (slide["layout"], it["t"])


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_longest_allowed_text_fits_in_every_layout(theme):
    from features import deck_layout as dl
    from features.deck_render import render_pdf, render_pptx
    slides = [dl.clean_slide(s, strict=True) for s in _longest_slides()]   # strict: every text is within its limit
    for s, raw in zip(slides, _longest_slides()):
        for k in ("title", "quote", "action"):
            if k in raw:
                assert s[k] == raw[k]                  # nothing was cut on the way in
    assert {s["layout"] for s in slides} == set(dl.LAYOUTS)
    laid = [dl.layout_slide(s, theme=theme, n=i + 1, author=_wide(60)) for i, s in enumerate(slides)]
    assert dl.clipped(laid) == []
    for sl in laid:
        _assert_inside(sl)
    pptx = render_pptx(laid, title="Longest", author="A", notes=[s.get("notes", "") for s in slides])
    assert len(_pptx(pptx).slides) == len(slides)
    assert _pdf_pages(render_pdf(laid, title="Longest", author="A")) == len(slides)


def test_impossible_text_is_cut_inside_its_box_never_outside():
    """Even text no real slide has (one 120-character word of W) stays inside its box: it ends with … instead."""
    from features import deck_layout as dl
    s = dl.clean_slide({"layout": "bullets", "title": "W" * 80, "bullets": ["W" * 120] * 6}, strict=True)
    sl = dl.layout_slide(s, n=2)
    assert dl.clipped([sl])
    _assert_inside(sl)


def test_member_edit_limits_are_strict():
    from features import deck_layout as dl
    with pytest.raises(dl.BadDeck) as e:
        dl.clean_slide({"layout": "bullets", "title": "x" * 81, "bullets": ["a", "b", "c"]}, strict=True)
    assert "80 characters" in str(e.value)
    with pytest.raises(dl.BadDeck):
        dl.clean_slide({"layout": "grid_2x2", "title": "t", "x_axis": "x", "y_axis": "y",
                        "cells": [{"title": "a"}] * 3}, strict=True)
    s = dl.clean_slide({"layout": "table", "title": "t", "columns": ["A", "B", "C"], "rows": [["1"], ["2", "3", "4", "5"]]})
    assert s["rows"] == [["1", "", ""], ["2", "3", "4"]]
    assert dl.clean_text("₹10 lakh → ₹15 lakh 🚀") == "₹10 lakh to ₹15 lakh"


# ------------------------------------------------------------------ edits, themes, ownership ----
def test_edit_and_theme_rerender_are_free_and_owner_only(seeded_client, mdb):
    c = seeded_client
    qa_login(c, plan="member")
    d = c.post("/api/decks", json=TEXT).json()
    d2 = c.post("/api/decks", json={**TEXT, "title": "Second deck"}).json()
    assert _used(c) == 2                                                     # the month's limit is used up
    old = run(mdb.decks.find_one({"_id": d["id"]}))["files"]
    slides = d["deck"]["slides"]
    i = next(k for k, s in enumerate(slides) if s["layout"] == "bullets")
    slides[i]["title"] = "Wastage is the biggest leak"
    slides[i]["accent"] = "biggest leak"
    slides[i]["bullets"] = ["Wastage is 9%.", "Good stores manage 4-5%.", "That gap is about ₹40 lakh a year."]
    slides[i]["notes"] = "Pause here and ask how they track wastage today."
    r = c.patch(f"/api/decks/{d['id']}", json={"slides": slides})
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["deck"]["slides"][i]["title"] == "Wastage is the biggest leak" and e["edited_at"]
    assert _used(c) == 2                                                     # free: no use counted, even at the limit
    prs, _ = _files_ok(c, e, 8)
    assert "Wastage is the biggest leak" in _texts(prs)
    assert prs.slides[i].notes_slide.notes_text_frame.text.startswith("Pause here")
    for f in old.values():                                                   # the old files are gone
        assert c.get(f"/api/blobs/{f['blob_id']}").status_code == 404
    t = c.patch(f"/api/decks/{d['id']}", json={"theme": "light"}).json()
    assert t["theme"] == "light" and t["layout"][1]["bg"]["color"] == "#FFFFFF" and _used(c) == 2
    _files_ok(c, t, 8)
    assert c.patch(f"/api/decks/{d['id']}", json={"title": "New name for it"}).json()["files"]["pdf"]["name"] == "New-name-for-it.pdf"
    bad = [dict(s) for s in t["deck"]["slides"]]
    bad[i]["title"] = "x" * 81
    r = c.patch(f"/api/decks/{d['id']}", json={"slides": bad})
    assert r.status_code == 400 and "80 characters" in r.json()["detail"]["msg"]
    assert c.patch(f"/api/decks/{d['id']}", json={"slides": t["deck"]["slides"][:-1]}).status_code == 400   # can't drop a slide
    swapped = list(reversed(t["deck"]["slides"]))
    assert c.patch(f"/api/decks/{d['id']}", json={"slides": swapped}).status_code == 400
    files = run(mdb.decks.find_one({"_id": d["id"]}))["files"]

    c.post("/api/auth/logout")                                               # someone else
    qa_login(c, plan="l2", phone="9000000077")
    assert c.get(f"/api/decks/{d['id']}").status_code == 404
    assert c.patch(f"/api/decks/{d['id']}", json={"theme": "dark"}).status_code == 404
    assert c.get(f"/api/decks/{d['id']}/file?kind=pdf").status_code == 404
    assert c.delete(f"/api/decks/{d['id']}").status_code == 404
    for f in files.values():
        assert c.get(f"/api/blobs/{f['blob_id']}").status_code == 404           # the blobs are owner-only too
    assert c.get("/api/decks").json()["items"] == []

    c.post("/api/auth/logout")
    qa_login(c, plan="member")
    for f in files.values():
        assert c.get(f"/api/blobs/{f['blob_id']}").status_code == 200
    assert c.delete(f"/api/decks/{d['id']}").json() == {"ok": True}
    assert c.get(f"/api/decks/{d['id']}").status_code == 404
    for f in files.values():
        assert run(mdb.blobs.find_one({"_id": f["blob_id"]})) is None
    assert [x["id"] for x in c.get("/api/decks").json()["items"]] == [d2["id"]]
    assert _used(c) == 2


def test_edit_that_changes_nothing_keeps_the_files(seeded_client, mdb):
    c = seeded_client
    qa_login(c, plan="member")
    d = c.post("/api/decks", json=TEXT).json()
    before = run(mdb.decks.find_one({"_id": d["id"]}))["files"]
    r = c.patch(f"/api/decks/{d['id']}", json={"theme": "dark"})
    assert r.status_code == 200 and run(mdb.decks.find_one({"_id": d["id"]}))["files"] == before
