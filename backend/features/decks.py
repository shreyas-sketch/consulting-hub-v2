"""Presentation Builder: turn your notes, a case you solved or a Meeting Brief into a client-ready deck.

decks {_id, user_id, source text|case|brief, ref_id, title, input: {audience, notes}, slides, tone, theme, format pdf|pptx,
       status pending|ready|failed, gen_id, export_url, blob_id, error, refunded, test, polled_at, created_at, ready_at}

Rendering vendor: Gamma Generate API (vendor switch "gamma", env GAMMA_API_KEY), Classic generation endpoint:
    POST https://public-api.gamma.app/v1.0/generations   header X-API-KEY   → {generationId}
    GET  https://public-api.gamma.app/v1.0/generations/{generationId} → {status pending|completed|failed, exportUrl, ...}
    GET  https://public-api.gamma.app/v1.0/themes?type=standard&query=… → {data: [{id, name}], hasMore, nextCursor}
Body: inputText (built here, structured, Indian context, ₹), textMode "generate", format "presentation", numCards,
textOptions {amount, tone, audience, language}, exportAs pdf|pptx, cardOptions.dimensions 16x9, sharingOptions.
Docs ask for polling about every 5 s; export links expire after about a week, so the file is copied into our blob
store when the deck is ready and is always served through GET /api/decks/{id}/file. The provider's URLs and name
never reach the member. Fake mode ("test") completes at once with a clearly marked sample PDF.
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from datetime import timedelta
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

import indexes
import media
import plans
from core.deps import user_dep
from core.vendors import vendor_mode
from growth import events
from growth.clock import as_utc, ist_month_key, utcnow
from state import db
from util import iso

from .case_bank import model_answer_text
from .common import run_metered, text
from .knowledge import knowledge

log = logging.getLogger("features.decks")
router = APIRouter(prefix="/decks", tags=["presentation-builder"])

events.register("deck_made", "Presentation Builder deck started (props.source, slides, format)")
events.register("deck_ready", "Presentation Builder deck finished (props.ok)")
indexes.register("decks", [("user_id", 1), ("created_at", -1)])

GAMMA_BASE = "https://public-api.gamma.app/v1.0"
FAKE_EXPORT = "https://example.com/test-mode/deck"
POLL_SECONDS = 5
GIVE_UP_MINUTES = 15
MAX_FILE = media.MAX_BYTES

# Six curated themes (as in the Leadership hub's Slide Architect) and five tone presets.
THEMES = [
    {"key": "aurum", "name": "Aurum", "note": "Gold on dark"},
    {"key": "basic-dark", "name": "Basic Dark", "note": "Dark and simple"},
    {"key": "basic-light", "name": "Basic Light", "note": "Light and simple"},
    {"key": "ash", "name": "Ash", "note": "Soft grey"},
    {"key": "ashrose", "name": "Ashrose", "note": "Warm and calm"},
    {"key": "blueberry", "name": "Blueberry", "note": "Blue, corporate"},
]
TONES = [
    {"key": "clear", "label": "Clear and practical", "gamma": "Clear, practical and plain-spoken; short sentences"},
    {"key": "boardroom", "label": "Boardroom", "gamma": "Confident, formal and concise, for owners and senior leaders"},
    {"key": "persuasive", "label": "Persuasive", "gamma": "Persuasive: lead with the problem and its cost, then the recommendation"},
    {"key": "warm", "label": "Warm, first meeting", "gamma": "Warm and conversational, for a first meeting with a prospect"},
    {"key": "teaching", "label": "Teaching", "gamma": "Explains step by step, for a workshop or a talk"},
]
THEME_KEYS = {t["key"]: t for t in THEMES}
TONE_KEYS = {t["key"]: t for t in TONES}

INSTRUCTIONS = (
    "Audience is Indian business owners and senior leaders. Money in Indian rupees with Indian grouping "
    "(₹1,50,000; ₹12 lakh; ₹40 crore). Use only the numbers given in the input; never invent figures, client names, "
    "market sizes or statistics: where a number is needed but missing, write [add figure]. Action titles that state the "
    "point of each slide in 4-8 words, not the topic. 3-4 short bullets per slide. Plain English, no jargon, no hype. "
    "First slide: title and who is presenting. Last slide: one clear next step or decision. Do not mention any tool, "
    "software or service used to make the deck."
)


class GammaError(RuntimeError):
    pass


def busy_error() -> HTTPException:
    return HTTPException(status_code=503, detail={
        "code": "deck_busy", "msg": "The deck maker is busy right now. Try again in a few minutes. This didn't use up your go."})


# ------------------------------------------------------------------ vendor client ----
def gamma_mode() -> str:
    return vendor_mode("gamma")


def _headers() -> dict:
    return {"X-API-KEY": os.environ.get("GAMMA_API_KEY", ""), "Content-Type": "application/json", "Accept": "application/json"}


_THEME_CACHE: dict = {"at": 0.0, "map": {}}


async def gamma_theme_id(name: str, *, client: Optional[httpx.AsyncClient] = None) -> Optional[str]:
    """Standard theme name → themeId (cached 6 h). None → the workspace default theme."""
    if gamma_mode() != "live":
        return None
    if time.time() - _THEME_CACHE["at"] > 6 * 3600:
        found: dict = {}
        c = client or httpx.AsyncClient(timeout=15)
        try:
            after = None
            for _ in range(6):
                params = {"type": "standard", "limit": 50, **({"after": after} if after else {})}
                r = await c.get(f"{GAMMA_BASE}/themes", params=params, headers=_headers())
                r.raise_for_status()
                body = r.json() or {}
                for t in body.get("data") or []:
                    if t.get("id") and t.get("name"):
                        found[str(t["name"]).strip().lower()] = str(t["id"])
                after = body.get("nextCursor")
                if not body.get("hasMore") or not after:
                    break
            _THEME_CACHE.update(at=time.time(), map=found)
        except Exception as e:  # noqa: BLE001 — a deck in the default theme beats no deck
            log.warning("theme list failed: %s", e)
        finally:
            if client is None:
                await c.aclose()
    return _THEME_CACHE["map"].get(name.strip().lower())


async def gamma_create(body: dict, *, client: Optional[httpx.AsyncClient] = None) -> str:
    m = gamma_mode()
    if m == "fake":
        return f"test-{uuid.uuid4().hex[:16]}"
    if m == "off":
        raise GammaError("deck vendor not configured (GAMMA_API_KEY)")
    c = client or httpx.AsyncClient(timeout=30)
    try:
        r = await c.post(f"{GAMMA_BASE}/generations", json=body, headers=_headers())
        if r.status_code >= 400:
            raise GammaError(f"create HTTP {r.status_code}: {r.text[:200]}")
        gid = (r.json() or {}).get("generationId")
        if not gid:
            raise GammaError("create: no generationId")
        return str(gid)
    except httpx.HTTPError as e:
        raise GammaError(f"create failed: {type(e).__name__}") from e
    finally:
        if client is None:
            await c.aclose()


async def gamma_status(gen_id: str, fmt: str, *, client: Optional[httpx.AsyncClient] = None) -> dict:
    if gen_id.startswith("test-"):
        return {"status": "completed", "exportUrl": f"{FAKE_EXPORT}.{fmt}"}
    if gamma_mode() == "off":
        raise GammaError("deck vendor not configured")
    c = client or httpx.AsyncClient(timeout=20)
    try:
        r = await c.get(f"{GAMMA_BASE}/generations/{gen_id}", headers=_headers())
        if r.status_code == 404:
            return {"status": "failed"}
        if r.status_code >= 400:
            raise GammaError(f"status HTTP {r.status_code}")
        return r.json() or {}
    except httpx.HTTPError as e:
        raise GammaError(f"status failed: {type(e).__name__}") from e
    finally:
        if client is None:
            await c.aclose()


def _ascii(s: str) -> str:
    s = s.replace("₹", "Rs ").replace("—", "-").replace("–", "-")
    return re.sub(r"[^\x20-\x7e]", "", s)


def test_pdf(title: str) -> bytes:
    """A one-page 16:9 PDF that says it is a test-mode sample (no network, no vendor)."""
    esc = lambda t: _ascii(t).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")  # noqa: E731
    content = (f"BT /F1 30 Tf 60 330 Td (TEST MODE - sample file, not a real deck) Tj ET\n"
               f"BT /F1 20 Tf 60 280 Td ({esc(title[:70])}) Tj ET\n"
               "BT /F1 14 Tf 60 240 Td (In live mode this file is the finished presentation.) Tj ET")
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 960 540] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


async def gamma_download(url: str, title: str, *, cap: bool = True, client: Optional[httpx.AsyncClient] = None) -> bytes:
    if url.startswith(FAKE_EXPORT):
        return test_pdf(title)
    c = client or httpx.AsyncClient(timeout=90, follow_redirects=True)
    try:
        r = await c.get(url)
        if r.status_code >= 400:
            raise GammaError(f"download HTTP {r.status_code}")
        if cap and len(r.content) > MAX_FILE:
            raise media.TooLarge("deck file too large to keep")
        return r.content
    except httpx.HTTPError as e:
        raise GammaError(f"download failed: {type(e).__name__}") from e
    finally:
        if client is None:
            await c.aclose()


# ------------------------------------------------------------------ input text ----
class DeckIn(BaseModel):
    source: Literal["text", "case", "brief"]
    id: Optional[str] = Field(None, max_length=64)        # case answer id (source "case") or brief id (source "brief")
    title: str = Field("", max_length=120)
    audience: str = Field("", max_length=160)
    notes: str = Field("", max_length=6000)
    slides: int = Field(8, ge=6, le=12)
    tone: str = Field("clear", max_length=20)
    theme: str = Field("aurum", max_length=30)
    format: Literal["pdf", "pptx"] = "pdf"


def _presenter(user: dict, k: dict) -> str:
    who = user.get("name") or "the consultant"
    return f"{who}, {k['consultant_title']}" if k.get("consultant_title") else who


def _flow(n: int, steps: list[str]) -> str:
    return f"SUGGESTED FLOW FOR {n} SLIDES: " + " → ".join(steps)


async def build_input(d, user: dict, body: DeckIn) -> dict:
    """{title, audience, input_text, ref_id} from the member's own data. Raises 400/404 in plain words."""
    uid = str(user["_id"])
    k = await knowledge(d, user)
    head = [f"Presented by: {_presenter(user, k)}",
            "Context: India. Money in Indian rupees (₹) with Indian grouping (₹1,50,000; ₹12 lakh; ₹40 crore)."]
    if k.get("value_proposition"):
        head.append(f"Presenter's positioning: {k['value_proposition']}")
    if body.source == "text":
        title = text(body.title, 120)
        if len(title) < 3:
            raise HTTPException(status_code=400, detail={"code": "title", "msg": "Give your deck a title."})
        notes = body.notes.strip()
        if len(notes) < 20:
            raise HTTPException(status_code=400, detail={"code": "notes", "msg": "Add your notes: a few lines on what the deck should say."})
        audience = text(body.audience, 160) or "Business owners and senior leaders"
        lines = [f"DECK TITLE: {title}", f"AUDIENCE: {audience}", *head, "", "WHAT THE DECK SHOULD SAY (the presenter's notes):",
                 notes, "", _flow(body.slides, ["Title", "The situation", "The problem and why it matters",
                                                "What we recommend", "How it works", "Plan and timeline", "Next step"])]
        return {"title": title, "audience": audience, "ref_id": None, "input_text": "\n".join(lines)}

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
                 "THE RECOMMENDATION (Strategic Thinking Framework: scope, objective, framework, options, do first, charter):",
                 model_answer_text(c["model_answer"]), "",
                 "THE PRESENTER'S OWN ANALYSIS (use its points where they add to the recommendation):", a["answer"][:3000],
                 "", _flow(body.slides, ["Title", "Where you are today", "The real problem", "Objective: from → to → by when",
                                         "What we found", "Options we considered", "Recommendation: do first",
                                         "How we run it: owner and metrics", "Next step"])]
        return {"title": title, "audience": audience, "ref_id": body.id, "input_text": "\n".join(lines)}

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
             _flow(body.slides, ["Title", "What we understand about you", "What's changing in your business",
                                 "Challenges companies like yours face", "How I work with clients", "Questions for today",
                                 "A next step"])]
    return {"title": title, "audience": audience, "ref_id": body.id, "input_text": "\n".join(lines)}


def gamma_body(*, title: str, audience: str, input_text: str, slides: int, tone: str, fmt: str, theme_id: Optional[str]) -> dict:
    body = {"inputText": input_text[:60000], "textMode": "generate", "format": "presentation", "numCards": slides,
            "cardSplit": "auto", "title": title[:200], "additionalInstructions": INSTRUCTIONS, "exportAs": fmt,
            "textOptions": {"amount": "medium", "tone": TONE_KEYS[tone]["gamma"], "audience": audience[:400], "language": "en"},
            "imageOptions": {"source": os.environ.get("GAMMA_IMAGE_SOURCE", "pictographic")},
            "cardOptions": {"dimensions": "16x9"},
            "sharingOptions": {"workspaceAccess": "view", "externalAccess": "noAccess"}}
    if theme_id:
        body["themeId"] = theme_id
    return body


# ------------------------------------------------------------------ status ----
def _filename(doc: dict) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", _ascii(doc["title"])).strip("-")[:60] or "deck"
    ext = "pdf" if doc.get("test") or doc["format"] == "pdf" else "pptx"
    return f"{slug}{'-test' if doc.get('test') else ''}.{ext}"


CTYPE = {"pdf": "application/pdf", "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}


def _public(doc: dict) -> dict:
    ready = doc["status"] == "ready"
    is_pdf = doc["format"] == "pdf" or doc.get("test")
    return {"id": doc["_id"], "title": doc["title"], "source": doc["source"], "ref_id": doc.get("ref_id"),
            "audience": doc.get("input", {}).get("audience"), "slides": doc["slides"], "tone": doc["tone"],
            "theme": doc["theme"], "format": doc["format"], "status": doc["status"], "error": doc.get("error"),
            "test": bool(doc.get("test")), "created_at": iso(doc["created_at"]), "ready_at": iso(doc.get("ready_at")),
            "file_name": _filename(doc) if ready else None,
            "download_url": f"/api/decks/{doc['_id']}/file" if ready else None,
            "open_url": f"/api/decks/{doc['_id']}/file?inline=1" if ready and is_pdf else None}


async def _fail(d, doc: dict, msg: str) -> dict:
    """Mark failed and give the go back (once, and only within the month it was counted in)."""
    upd = {"status": "failed", "error": msg}
    if not doc.get("refunded") and ist_month_key(as_utc(doc["created_at"])) == ist_month_key():
        await plans.refund(d, {"_id": doc["user_id"]}, "presentation")
        upd["refunded"] = True
    await d.decks.update_one({"_id": doc["_id"]}, {"$set": upd})
    await events.track(d, "deck_ready", user_id=doc["user_id"], props={"ok": False})
    return {**doc, **upd}


async def refresh(d, doc: dict, *, force: bool = False) -> dict:
    """Poll the vendor at most every POLL_SECONDS per deck; on completion copy the file into our store."""
    if doc["status"] != "pending":
        return doc
    now = utcnow()
    if not force:
        claim = await d.decks.update_one({"_id": doc["_id"], "status": "pending",
                                          "polled_at": {"$lte": now - timedelta(seconds=POLL_SECONDS)}},
                                         {"$set": {"polled_at": now}})
        if not claim.modified_count:
            return doc
    age = now - as_utc(doc["created_at"])
    try:
        st = await gamma_status(doc["gen_id"], doc["format"])
    except GammaError as e:
        log.warning("deck %s poll failed: %s", doc["_id"], e)
        if age > timedelta(minutes=GIVE_UP_MINUTES):
            return await _fail(d, doc, "The deck took too long. Your go was given back. Try again.")
        return doc
    status = str(st.get("status") or "").lower()
    if status == "completed":
        url = str(st.get("exportUrl") or "")
        if not url.startswith(("https://", "http://")):
            return await _fail(d, doc, "The deck couldn't be finished. Your go was given back. Try again.")
        upd = {"status": "ready", "ready_at": now, "export_url": url, "blob_id": None}
        try:
            data = await gamma_download(url, doc["title"])
            upd["blob_id"] = await media.save_blob(d, user_id=doc["user_id"], kind="deck", data=data, name=_filename(doc),
                                                   content_type=CTYPE["pdf" if doc.get("test") else doc["format"]])
        except (GammaError, media.TooLarge) as e:          # served straight from the export link while it lasts
            log.warning("deck %s not copied: %s", doc["_id"], e)
        await d.decks.update_one({"_id": doc["_id"]}, {"$set": upd})
        await events.track(d, "deck_ready", user_id=doc["user_id"], props={"ok": True})
        return {**doc, **upd}
    if status == "failed":
        return await _fail(d, doc, "The deck couldn't be made. Your go was given back. Try again.")
    if age > timedelta(minutes=GIVE_UP_MINUTES):
        return await _fail(d, doc, "The deck took too long. Your go was given back. Try again.")
    return doc


# ------------------------------------------------------------------ routes ----
@router.get("/options")
async def options():
    return {"themes": THEMES, "tones": [{"key": t["key"], "label": t["label"]} for t in TONES],
            "slides": {"min": 6, "max": 12, "default": 8}, "formats": [{"key": "pdf", "label": "PDF"},
                                                                       {"key": "pptx", "label": "PowerPoint"}]}


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
    theme = body.theme if body.theme in THEME_KEYS else "aurum"

    async def work(plan: str):
        built = await build_input(d, user, body)
        try:
            theme_id = await gamma_theme_id(THEME_KEYS[theme]["name"])
            gen_id = await gamma_create(gamma_body(title=built["title"], audience=built["audience"],
                                                   input_text=built["input_text"], slides=body.slides, tone=tone,
                                                   fmt=body.format, theme_id=theme_id))
        except GammaError as e:
            log.warning("deck create failed: %s", e)
            raise busy_error()
        now = utcnow()
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "source": body.source, "ref_id": built["ref_id"],
               "title": built["title"], "input": {"audience": built["audience"], "notes": body.notes[:6000]},
               "slides": body.slides, "tone": tone, "theme": theme, "format": body.format, "status": "pending",
               "gen_id": gen_id, "test": gen_id.startswith("test-"), "refunded": False, "polled_at": now,
               "created_at": now}
        await d.decks.insert_one(doc)
        await events.track(d, "deck_made", user_id=uid, props={"source": body.source, "slides": body.slides, "format": body.format})
        if doc["test"]:
            doc = await refresh(d, doc, force=True)            # fake mode completes at once
        return _public(doc)
    return await run_metered(d, user, "presentation", work)


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    rows = [_public(x) async for x in db().decks.find({"user_id": str(user["_id"])}).sort("created_at", -1).limit(50)]
    return {"items": rows}


async def _own(deck_id: str, user: dict) -> dict:
    doc = await db().decks.find_one({"_id": deck_id, "user_id": str(user["_id"])})
    if not doc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Deck not found."})
    return doc


@router.get("/{deck_id}")
async def one(deck_id: str, user: dict = Depends(user_dep())):
    doc = await _own(deck_id, user)
    return _public(await refresh(db(), doc))


@router.get("/{deck_id}/file")
async def file(deck_id: str, inline: bool = Query(False), user: dict = Depends(user_dep())):
    """The deck file, always through our own route (the vendor's link is never shown)."""
    doc = await _own(deck_id, user)
    if doc["status"] != "ready":
        raise HTTPException(status_code=409, detail={"code": "not_ready", "msg": "The deck isn't ready yet."})
    name = _filename(doc)
    ctype = CTYPE["pdf" if doc.get("test") else doc["format"]]
    data = None
    if doc.get("blob_id"):
        b = await media.get_blob(db(), doc["blob_id"])
        data = bytes(b["data"]) if b else None
    if data is None and doc.get("export_url"):
        try:
            data = await gamma_download(doc["export_url"], doc["title"], cap=False)
        except (GammaError, media.TooLarge):
            data = None
    if data is None:
        raise HTTPException(status_code=410, detail={"code": "expired", "msg": "This file is no longer available. Make the deck again."})
    disp = "inline" if inline and ctype == CTYPE["pdf"] else "attachment"
    return Response(data, media_type=ctype, headers={"Content-Disposition": f'{disp}; filename="{name}"',
                                                     "Cache-Control": "private, max-age=600"})
