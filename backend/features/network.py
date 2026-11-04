"""Warm Network Finder: the people the member already knows who could need them (or introduce them).

contacts {_id, user_id, key, first, last, name, url, email, company, position, connected_on, source csv|paste,
          pre_score 0-100, pre_why: [str], seniority, fit 1-10|None, why, angle, scored_at,
          status new|contacted, contacted_at, notes, at}

The member uploads LinkedIn's "Connections.csv" export (a few note lines sit above the header) or pastes a list.
Up to 5,000 contacts are kept. A free rule score ranks everyone at once (seniority + a match to the member's
niche and industry). The member then picks up to 10 at a time for an AI read: fit 1-10, why, and a suggested
angle. Each contact scored uses one of the month's `contacts` (50 on L2). Nothing is ever sent from here.

Also home to `run_metered_n`, the helper the count-based L2 tools share (contacts, radar companies, posts).
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from typing import Awaitable, Callable, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

import indexes
import llm
import plans
from core.deps import user_dep
from growth import events
from growth.clock import utcnow
from state import db
from util import iso

from .common import busy_error, clamp_int, text
from .knowledge import knowledge, system_block

router = APIRouter(prefix="/network", tags=["network-finder"])

FEATURE = "network_finder"
METER = "contacts"
CAP = 5000
MAX_FILE = 5 * 1024 * 1024
PICK_MAX = 10
NO_VENDOR = ("Never name or hint at any AI company, model or tool behind this; you are simply the hub's assistant. "
             "No emojis.")

events.register("network_imported", "Warm Network Finder: contacts imported (props.added, source)")
events.register("contacts_scored", "Warm Network Finder: contacts scored by AI (props.n)")
indexes.register("contacts", [("user_id", 1), ("pre_score", -1)])
indexes.register("contacts", [("user_id", 1), ("key", 1)])


# ---------------------------------------------------------------- metering for counted units ----
def _limit_error(meter: str, used: int, limit: int, left: int) -> HTTPException:
    unit = {"contacts": "contacts to score", "radar": "companies to find"}.get(meter) or plans.LIMIT_UNITS.get(meter, meter)
    return HTTPException(status_code=402, detail={
        "code": "limit", "feature": meter, "used": used, "limit": limit, "plan_needed": None, "once": False,
        "msg": f"You have {left} {unit} left this month. Choose {left} or fewer, or wait for the 1st."})


async def reserve(d, user: dict, meter: str, n: int, *, access: str, partial: bool = False) -> tuple[str, int]:
    """Check the plan opens `access`, then count `n` uses of `meter` at once.
    partial=True takes what is left (at least 1) instead of refusing. Returns (plan, n taken)."""
    plan = await plans.require(d, user, access)
    n = max(1, int(n))
    limit = plans.limit_for(meter, plan)
    key = plans.usage_key(str(user["_id"]), plan)
    if limit:
        used = int((await d.usage.find_one({"_id": key}) or {}).get(meter, 0))
        left = limit - used
        if 0 < left < n:
            if not partial:
                raise _limit_error(meter, used, limit, left)
            n = left
    await plans.consume(d, user, meter, plan)        # 403 when the plan has none, 402 when nothing is left
    if n > 1:
        await d.usage.update_one({"_id": key}, {"$inc": {meter: n - 1}})
    return plan, n


async def give_back(d, user: dict, meter: str, n: int, plan: str) -> None:
    if n > 0:
        await d.usage.update_one({"_id": plans.usage_key(str(user["_id"]), plan), meter: {"$gte": n}},
                                 {"$inc": {meter: -n}})


async def run_metered_n(d, user: dict, meter: str, n: int, work: Callable[[str, int], Awaitable[tuple]], *,
                        access: str, partial: bool = False):
    """Like common.run_metered for tools that count units: reserve n, run work(plan, n) -> (result, used),
    give back what wasn't used. Any failure gives back all of it."""
    plan, n = await reserve(d, user, meter, n, access=access, partial=partial)
    try:
        result, used = await work(plan, n)
    except llm.LLMError:
        await give_back(d, user, meter, n, plan)
        raise busy_error()
    except Exception:
        await give_back(d, user, meter, n, plan)
        raise
    await give_back(d, user, meter, n - max(0, min(n, int(used))), plan)
    return result


# ---------------------------------------------------------------- parsing ----
HEADERS = {"first name": "first", "firstname": "first", "last name": "last", "lastname": "last", "url": "url",
           "profile url": "url", "email address": "email", "email": "email", "company": "company",
           "position": "position", "title": "position", "connected on": "connected_on"}


def _clean(v, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def _key(c: dict) -> str:
    if c.get("url"):
        return c["url"].lower().rstrip("/")
    return f"{c['name']}|{c.get('company', '')}".lower()


def _row(first: str, last: str, url: str = "", email: str = "", company: str = "", position: str = "",
         connected_on: str = "") -> Optional[dict]:
    first, last = _clean(first, 60), _clean(last, 60)
    name = _clean(f"{first} {last}", 120)
    if not name:
        return None
    url = _clean(url, 300)
    if url and not url.lower().startswith(("https://", "http://")):
        url = ""
    email = _clean(email, 160)
    if email and "@" not in email:
        email = ""
    return {"first": first, "last": last, "name": name, "url": url, "email": email, "company": _clean(company, 160),
            "position": _clean(position, 200), "connected_on": _clean(connected_on, 20)}


def parse_connections_csv(raw: str) -> list[dict]:
    """LinkedIn's Connections.csv: skip the note lines above the 'First Name,Last Name,...' header."""
    raw = raw.lstrip("﻿")
    lines = raw.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.lstrip('﻿"').lower().startswith("first name") and "last name" in ln.lower()), None)
    if start is None:
        raise ValueError("no header")
    reader = csv.reader(io.StringIO("\n".join(lines[start:])))
    header = [HEADERS.get(h.strip().strip('"').lower(), "") for h in next(reader)]
    out = []
    for cells in reader:
        if not any(c.strip() for c in cells):
            continue
        rec = {k: cells[i] for i, k in enumerate(header) if k and i < len(cells)}
        r = _row(rec.get("first", ""), rec.get("last", ""), rec.get("url", ""), rec.get("email", ""),
                 rec.get("company", ""), rec.get("position", ""), rec.get("connected_on", ""))
        if r:
            out.append(r)
    return out


def parse_pasted(raw: str) -> list[dict]:
    """One person per line: 'Name, Role, Company' (comma or tab), or 'Name - Role at Company'.
    A pasted copy of the CSV (with its header) is read as the CSV."""
    if re.search(r"first name\s*,\s*last name", raw, re.I):
        return parse_connections_csv(raw)
    out = []
    for line in raw.splitlines():
        line = line.strip().strip("•-* ").strip()
        if not line:
            continue
        parts = [p.strip() for p in (line.split("\t") if "\t" in line else line.split(","))]
        if len(parts) == 1:
            parts = [p.strip() for p in re.split(r"\s+[-|–]\s+", line)]
        name = parts[0]
        position = parts[1] if len(parts) > 1 else ""
        company = ", ".join(parts[2:]) if len(parts) > 2 else ""
        if not company and re.search(r"\s+at\s+", position, re.I):
            position, company = [x.strip() for x in re.split(r"\s+at\s+", position, maxsplit=1, flags=re.I)]
        bits = name.split()
        r = _row(bits[0] if bits else "", " ".join(bits[1:]), company=company, position=position)
        if r:
            out.append(r)
    return out


# ---------------------------------------------------------------- rule pre-score ----
SENIORITY = [
    (re.compile(r"\b(co-?founder|founder)\b", re.I), "Founder", 40),
    (re.compile(r"\b(owner|proprietor)\b", re.I), "Owner", 40),
    (re.compile(r"\b(ceo|chief executive)\b", re.I), "CEO", 40),
    (re.compile(r"\b(md|managing director)\b", re.I), "MD", 38),
    (re.compile(r"\b(chairman|chairperson|president)\b", re.I), "President", 34),
    (re.compile(r"\b(c[fotmh]o|chro|cxo|chief [a-z]+ officer)\b", re.I), "CXO", 34),
    (re.compile(r"\bpartner\b", re.I), "Partner", 32),
    (re.compile(r"\bdirector\b", re.I), "Director", 30),
    (re.compile(r"\b(vp|svp|evp|vice president)\b", re.I), "VP", 28),
    (re.compile(r"\bhead\b", re.I), "Head", 26),
    (re.compile(r"\b(gm|general manager)\b", re.I), "GM", 24),
]
OWNER_LED = re.compile(r"\b(pvt|private limited|llp|enterprises|industries|traders|& sons|and sons|group)\b", re.I)
STOP = {"and", "the", "for", "with", "from", "that", "this", "into", "their", "them", "your", "help", "helping",
        "company", "companies", "business", "businesses", "consulting", "consultant", "growth", "india", "indian",
        "owner", "owners", "firms", "firm", "led", "mid", "size", "sized", "small", "medium", "large", "revenue",
        "crore", "lakh", "achieve", "solve", "problem", "problems", "team", "teams", "leaders", "people", "who"}
SYNONYMS = {
    "manufacturing": ["manufactur", "industries", "engineering", "steel", "plastics", "auto", "pumps", "castings"],
    "fmcg": ["fmcg", "foods", "consumer", "beverages", "snacks", "dairy"],
    "healthcare": ["hospital", "clinic", "health", "pharma", "diagnostic", "medical"],
    "hospital": ["hospital", "clinic", "health", "medical"],
    "pharma": ["pharma", "life sciences", "labs", "biotech", "drugs"],
    "retail": ["retail", "stores", "mart", "fashion", "apparel"],
    "technology": ["technolog", "software", "infotech", "tech", "digital", "systems"],
    "software": ["software", "tech", "infotech", "saas", "systems"],
    "real estate": ["realty", "builders", "developers", "properties", "estate", "infra"],
    "education": ["school", "academy", "education", "university", "institute", "learning", "edtech"],
    "finance": ["finance", "capital", "bank", "nbfc", "financial", "insurance", "wealth"],
    "logistics": ["logistics", "transport", "freight", "shipping", "supply chain", "warehous"],
    "textile": ["textile", "fabrics", "garments", "apparel", "yarn"],
    "hospitality": ["hotel", "resort", "hospitality", "restaurant", "foods"],
    "automotive": ["auto", "motors", "automotive", "vehicles"],
    "chemicals": ["chemical", "polymers", "paints", "coatings"],
}


def niche_terms(k: dict) -> list[str]:
    blob = " ".join([k.get("niche") or "", k.get("target_industry") or "", k.get("target_audience") or ""]).lower()
    words = {w for w in re.findall(r"[a-z][a-z&]+", blob) if len(w) >= 4 and w not in STOP}
    terms = set(words)
    for base, syn in SYNONYMS.items():
        if base in blob:
            terms.update(syn)
    return sorted(terms)


def pre_score(c: dict, terms: list[str]) -> tuple[int, list[str], str]:
    pos, company = c.get("position") or "", c.get("company") or ""
    score, why, level = 0, [], ""
    for rx, label, pts in SENIORITY:
        if rx.search(pos):
            score, level = pts, label
            why.append(f"Decision-maker ({label})")
            break
    hay = f" {company} {pos} ".lower()
    hits = [t for t in terms if t in hay]
    if hits:
        score += 25 if len(hits) == 1 else 40
        why.append(f"Matches your niche ({', '.join(hits[:2])})")
    if OWNER_LED.search(company):
        score += 10
        why.append("Owner-led company")
    if c.get("email"):
        score += 10
        why.append("Shared their email")
    return min(100, score), why, level


# ---------------------------------------------------------------- shapes ----
def public(c: dict) -> dict:
    return {"id": c["_id"], "name": c["name"], "first": c.get("first", ""), "url": c.get("url") or "",
            "email": c.get("email") or "", "company": c.get("company") or "", "position": c.get("position") or "",
            "connected_on": c.get("connected_on") or "", "source": c.get("source"), "pre_score": c.get("pre_score", 0),
            "pre_why": c.get("pre_why") or [], "seniority": c.get("seniority") or "", "fit": c.get("fit"),
            "why": c.get("why") or "", "angle": c.get("angle") or "", "scored_at": iso(c.get("scored_at")),
            "status": c.get("status") or "new", "contacted_at": iso(c.get("contacted_at")), "notes": c.get("notes") or "",
            "at": iso(c.get("at"))}


async def get_contact(uid: str, cid: str) -> Optional[dict]:
    return await db().contacts.find_one({"_id": cid, "user_id": uid})


async def _store(user: dict, rows: list[dict], source: str) -> dict:
    d = db()
    uid = str(user["_id"])
    k = await knowledge(d, user)
    terms = niche_terms(k)
    have = await d.contacts.count_documents({"user_id": uid})
    keys = {c["key"] async for c in d.contacts.find({"user_id": uid}, {"key": 1})}
    room = max(0, CAP - have)
    docs, dupes, over = [], 0, 0
    now = utcnow()
    for r in rows:
        key = _key(r)
        if key in keys:
            dupes += 1
            continue
        if len(docs) >= room:
            over += 1
            continue
        keys.add(key)
        score, why, level = pre_score(r, terms)
        docs.append({"_id": uuid.uuid4().hex, "user_id": uid, "key": key, **r, "source": source, "pre_score": score,
                     "pre_why": why, "seniority": level, "fit": None, "why": "", "angle": "", "status": "new",
                     "notes": "", "at": now})
    if docs:
        await d.contacts.insert_many(docs)
    await events.track(d, "network_imported", user_id=uid, props={"added": len(docs), "source": source})
    return {"added": len(docs), "duplicates": dupes, "over_cap": over, "total": have + len(docs), "cap": CAP}


@router.post("/import")
async def import_csv(file: UploadFile = File(...), user: dict = Depends(user_dep())):
    await plans.require(db(), user, FEATURE)
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail={"code": "bad_type", "msg": "Upload the Connections.csv file from LinkedIn."})
    raw = await file.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE:
        raise HTTPException(status_code=400, detail={"code": "too_large", "msg": "That file is over 5 MB. Upload Connections.csv only."})
    try:
        rows = parse_connections_csv(raw.decode("utf-8-sig", errors="ignore"))
    except (ValueError, StopIteration, csv.Error):
        raise HTTPException(status_code=400, detail={
            "code": "bad_csv", "msg": "This doesn't look like LinkedIn's Connections.csv. It needs the columns First Name, Last Name and Company."})
    if not rows:
        raise HTTPException(status_code=400, detail={"code": "empty", "msg": "No people found in that file."})
    return await _store(user, rows, "csv")


class PasteIn(BaseModel):
    text: str = Field(..., min_length=3, max_length=200_000)


@router.post("/paste")
async def paste(body: PasteIn, user: dict = Depends(user_dep())):
    await plans.require(db(), user, FEATURE)
    rows = parse_pasted(body.text)
    if not rows:
        raise HTTPException(status_code=400, detail={"code": "empty", "msg": "Put one person on each line: Name, Role, Company."})
    return await _store(user, rows, "paste")


@router.get("")
async def listing(q: str = Query("", max_length=80), status: Literal["", "new", "contacted"] = "",
                  scored: Literal["", "yes", "no"] = "", senior: bool = False, min_fit: int = Query(0, ge=0, le=10),
                  sort: Literal["pre", "fit", "name"] = "pre", page: int = Query(0, ge=0, le=200),
                  user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, FEATURE)
    uid = str(user["_id"])
    f: dict = {"user_id": uid}
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        f["$or"] = [{"name": rx}, {"company": rx}, {"position": rx}]
    if status:
        f["status"] = status
    if scored == "yes" or min_fit:
        f["fit"] = {"$gte": max(1, min_fit)}
    elif scored == "no":
        f["fit"] = None
    if senior:
        f["seniority"] = {"$ne": ""}
    order = {"pre": [("pre_score", -1), ("name", 1)], "fit": [("fit", -1), ("pre_score", -1)], "name": [("name", 1)]}[sort]
    size = 50
    total = await d.contacts.count_documents(f)
    items = [public(c) async for c in d.contacts.find(f).sort(order).skip(page * size).limit(size)]
    counts = {"all": await d.contacts.count_documents({"user_id": uid}),
              "scored": await d.contacts.count_documents({"user_id": uid, "fit": {"$gte": 1}}),
              "contacted": await d.contacts.count_documents({"user_id": uid, "status": "contacted"})}
    return {"items": items, "total": total, "page": page, "size": size, "counts": counts, "cap": CAP, "pick_max": PICK_MAX}


SYSTEM = (
    "You help an experienced Indian professional who is launching as a consultant find the warm contacts most likely "
    "to become a first paying client, or to introduce them to one. You see only each person's name, role, company "
    "and when they connected. Judge fit 1-10: 9-10 = a decision-maker at exactly the kind of business the consultant "
    "serves; 6-8 = a likely buyer or a strong introducer; 3-5 = possible introducer; 1-2 = unlikely. Never invent facts "
    "about a person or their company; if you don't know the company, say what the role suggests. The angle is how to "
    "start a warm, human conversation (reconnect, ask for their view, offer something useful), never a pitch. "
    "Plain English, short sentences. " + NO_VENDOR
)


def _fake_scores(rows: list[dict]) -> dict:
    out = []
    for i, c in enumerate(rows):
        fit = max(1, min(10, round((c.get("pre_score") or 0) / 10) or 2))
        why = "; ".join(c.get("pre_why") or []) or "Not much to go on from the role alone."
        lead = c.get("first") or c["name"].split()[0]
        angle = (f"Ask {lead} what's top of mind for {c.get('company') or 'their team'} this year."
                 if c.get("seniority") else f"Reconnect with {lead} and ask who they know in your niche.")
        out.append({"i": i + 1, "fit": fit, "why": f"Test mode: {why}.", "angle": angle})
    return {"scores": out}


def _prompt(k: dict, rows: list[dict]) -> str:
    lines = "\n".join(f"[{i + 1}] {c['name']} | {c.get('position') or 'role unknown'} | {c.get('company') or 'company unknown'}"
                      f" | connected {c.get('connected_on') or 'date unknown'}" for i, c in enumerate(rows))
    return (f"{system_block(k) or 'The consultant has not chosen a niche yet; judge on seniority.'}\n"
            f"Consultant title: {k.get('consultant_title') or 'not set'}\n\nCONTACTS:\n{lines}\n\n"
            "Score every contact by its number. For each: fit (1-10), why (one sentence), angle (one sentence on how "
            "to open a warm conversation).\n"
            'JSON: {"scores": [{"i": 1, "fit": 7, "why": "", "angle": ""}]}')


class ScoreIn(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=PICK_MAX)


@router.post("/score")
async def score(body: ScoreIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    await plans.require(d, user, FEATURE)
    ids = list(dict.fromkeys(body.ids))
    rows = [c async for c in d.contacts.find({"_id": {"$in": ids}, "user_id": uid})]
    if not rows:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Pick people from your list first."})
    rows.sort(key=lambda c: ids.index(c["_id"]))

    async def work(plan: str, n: int):
        k = await knowledge(d, user)
        raw = await llm.complete_json(task="network_score", system=SYSTEM, prompt=_prompt(k, rows),
                                      fake=lambda: _fake_scores(rows), model="fast", max_tokens=1600)
        got: dict[int, dict] = {}
        for s in raw.get("scores") or []:
            if not isinstance(s, dict):
                continue
            i = clamp_int(s.get("i"), -1, 10_000, -1)
            if not 1 <= i <= len(rows) or i in got or s.get("fit") is None or not text(s.get("why"), 300):
                continue
            got[i] = {"fit": clamp_int(s.get("fit"), 1, 10, 5), "why": text(s.get("why"), 300),
                      "angle": text(s.get("angle"), 300)}
        if not got:
            raise llm.LLMError("network_score: no scores")
        now = utcnow()
        out = []
        for i, c in enumerate(rows, start=1):
            if i in got:
                await d.contacts.update_one({"_id": c["_id"]}, {"$set": {**got[i], "scored_at": now}})
                c.update(got[i], scored_at=now)
            out.append(public(c))
        await events.track(d, "contacts_scored", user_id=uid, props={"n": len(got)})
        return {"items": out, "scored": len(got)}, len(got)
    return await run_metered_n(d, user, METER, len(rows), work, access=FEATURE)


@router.get("/{cid}")
async def one(cid: str, user: dict = Depends(user_dep())):
    await plans.require(db(), user, FEATURE)
    c = await get_contact(str(user["_id"]), cid)
    if not c:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Contact not found."})
    return public(c)


class PatchIn(BaseModel):
    status: Optional[Literal["new", "contacted"]] = None
    notes: Optional[str] = Field(None, max_length=2000)


@router.patch("/{cid}")
async def patch(cid: str, body: PatchIn, user: dict = Depends(user_dep())):
    await plans.require(db(), user, FEATURE)
    uid = str(user["_id"])
    c = await get_contact(uid, cid)
    if not c:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Contact not found."})
    s: dict = {}
    if body.status is not None:
        s["status"] = body.status
        s["contacted_at"] = utcnow() if body.status == "contacted" else None
    if body.notes is not None:
        s["notes"] = body.notes.strip()
    if s:
        await db().contacts.update_one({"_id": cid}, {"$set": s})
        c.update(s)
    return public(c)


@router.delete("/{cid}")
async def remove(cid: str, user: dict = Depends(user_dep())):
    await plans.require(db(), user, FEATURE)
    r = await db().contacts.delete_one({"_id": cid, "user_id": str(user["_id"])})
    return {"ok": r.deleted_count == 1}


@router.delete("")
async def clear(user: dict = Depends(user_dep())):
    await plans.require(db(), user, FEATURE)
    r = await db().contacts.delete_many({"user_id": str(user["_id"])})
    return {"ok": True, "deleted": r.deleted_count}
