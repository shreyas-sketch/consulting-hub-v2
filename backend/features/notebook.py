"""Research Notebook (L1 and up): gather sources on one topic, ask questions with citations, turn them into a briefing,
FAQ, study guide or timeline, and listen to a short audio overview.

nb_projects {_id, user_id, title, description, audio?: {blob_id, sig, title, script, words, minutes, at}, at, updated_at}
nb_sources  {_id, project_id, user_id, kind file|text|url|doc, title, url?, doc_id?, words, pages?, chunks, ntok,
             truncated, test, at}
nb_chunks   {_id, source_id, project_id, user_id, title, i, page, text, tokens, n}
nb_notes    {_id, project_id, user_id, kind note|answer|briefing|faq|study|timeline, title, body (Markdown), at, updated_at}
nb_messages {_id, project_id, user_id, question, answer, covered, citations, at}

Projects are capped by plans.cap("research_projects", plan); 20 sources a project. Files are read the same way as
Doc Reader (text only; the file is not kept). Web pages come from research.search.extract. Questions and generated
outputs use the doc_q meter; the audio overview uses audio and is reused until the sources change.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from collections import Counter
from typing import Literal, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

import indexes
import llm
import media
import plans
from audio import tts
from core.deps import user_dep
from growth import events
from growth.clock import utcnow
from research import search
from state import db
from util import iso

from . import kb
from .common import as_list, run_metered, strip_providers, text, text_list
from .docs import (
    MAX_WORDS,
    NO_PROVIDER,
    NOT_COVERED,
    _nums,
    bad,
    cited_answer,
    claim_slot,
    clean_text,
    first_sentence,
    make_chunks,
    not_found,
    read_upload,
    retrieve,
    sentences,
    spread,
    strip_markdown,
    tidy,
)

router = APIRouter(prefix="/notebook", tags=["research-notebook"])

events.register("notebook_created", "Research Notebook project made")
events.register("notebook_source_added", "Research Notebook source added (props.kind, words)")
events.register("notebook_asked", "Research Notebook question answered (props.covered, cited)")
events.register("notebook_generated", "Research Notebook output made (props.kind)")
events.register("notebook_audio", "Research Notebook audio overview made (props.minutes)")
indexes.register("nb_projects", [("user_id", 1), ("updated_at", -1)])
indexes.register("nb_sources", [("project_id", 1), ("at", 1)])
indexes.register("nb_chunks", [("project_id", 1), ("tokens", 1)])
indexes.register("nb_chunks", [("source_id", 1), ("i", 1)])
indexes.register("nb_notes", [("project_id", 1), ("at", -1)])
indexes.register("nb_messages", [("project_id", 1), ("at", -1)])

MAX_SOURCES = 20
GEN_BUDGET = 9000                     # words of source text an output is made from
KINDS = {"briefing": "Briefing document", "faq": "FAQ", "study": "Study guide", "timeline": "Timeline"}
DATE = re.compile(r"\b(?:1[89]\d{2}|20\d{2})\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"
                  r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
                  r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+\d{1,4}\b", re.I)

GEN_SYSTEM = (
    "You turn a member's research sources into working material for an experienced Indian professional who is "
    "becoming a consultant. Use only the sources you are given. Don't add facts, figures or dates that aren't in them; "
    "quote figures exactly as written. Plain, short, spoken English. No buzzwords, no hype. " + NO_PROVIDER
)
AUDIO_SYSTEM = (
    "You write a spoken audio overview of a member's research sources, read aloud by one narrator. Length: 3 to 5 "
    "minutes, which is 450 to 700 words. Warm, clear, plain spoken English for an experienced Indian professional who "
    "is becoming a consultant. Say what the topic is, walk through the main points across the sources, give figures "
    "exactly as written, and end with two or three questions worth thinking about. No headings, no bullet points, no "
    "Markdown, no stage directions. Use only the sources. " + NO_PROVIDER
)


# ------------------------------------------------------------------ shapes ----
def _pub_project(p: dict, n_sources: int = 0, n_notes: int = 0) -> dict:
    return {"id": p["_id"], "title": p["title"], "description": p.get("description") or "", "sources": n_sources,
            "notes": n_notes, "at": iso(p["at"]), "updated_at": iso(p.get("updated_at") or p["at"])}


def _pub_source(s: dict) -> dict:
    return {"id": s["_id"], "kind": s["kind"], "title": s["title"], "url": s.get("url"), "doc_id": s.get("doc_id"),
            "words": s.get("words", 0), "pages": s.get("pages"), "truncated": bool(s.get("truncated")),
            "test": bool(s.get("test")), "at": iso(s["at"])}


def _pub_note(n: dict) -> dict:
    return {"id": n["_id"], "kind": n["kind"], "title": n["title"], "body": n["body"], "at": iso(n["at"]),
            "updated_at": iso(n.get("updated_at") or n["at"])}


def _pub_msg(m: dict) -> dict:
    return {"id": m["_id"], "question": m["question"], "answer": m["answer"], "covered": m["covered"],
            "citations": m.get("citations", []), "at": iso(m["at"])}


async def _project(pid: str, user: dict) -> dict:
    p = await db().nb_projects.find_one({"_id": pid, "user_id": str(user["_id"])})
    if not p:
        raise not_found("Project")
    return p


async def _sources(pid: str) -> list[dict]:
    return [s async for s in db().nb_sources.find({"project_id": pid}).sort("at", 1)]


def _sig(sources: list[dict]) -> str:
    return hashlib.sha1(",".join(sorted(s["_id"] for s in sources)).encode()).hexdigest()[:16]


async def _touch(pid: str) -> None:
    await db().nb_projects.update_one({"_id": pid}, {"$set": {"updated_at": utcnow()}})


def _audio_public(a: Optional[dict], sig: str) -> Optional[dict]:
    if not a or not a.get("blob_id"):
        return None
    return {"url": media.blob_url(a["blob_id"]), "title": a.get("title"), "script": a.get("script"),
            "minutes": a.get("minutes"), "fresh": a.get("sig") == sig, "at": iso(a.get("at"))}


# ------------------------------------------------------------------ projects ----
class ProjectIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=120)
    description: str = Field("", max_length=600)


class ProjectPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=120)
    description: Optional[str] = Field(None, max_length=600)


@router.get("")
async def listing(user: dict = Depends(user_dep())):
    d = db()
    plan = await plans.require(d, user, "research")
    items = []
    async for p in d.nb_projects.find({"user_id": str(user["_id"])}, {"audio": 0}).sort("updated_at", -1):
        items.append(_pub_project(p, await d.nb_sources.count_documents({"project_id": p["_id"]}),
                                  await d.nb_notes.count_documents({"project_id": p["_id"]})))
    return {"items": items, "count": len(items), "cap": plans.cap("research_projects", plan), "max_sources": MAX_SOURCES}


@router.post("")
async def create(body: ProjectIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    plan = await plans.require(d, user, "research")
    cap = plans.cap("research_projects", plan)
    full = bad("cap", f"You can keep {cap} projects at a time. Delete one to start another.", 409)
    if await d.nb_projects.count_documents({"user_id": uid}) >= cap:
        raise full
    now = utcnow()
    p = {"_id": uuid.uuid4().hex, "user_id": uid, "title": text(body.title, 120), "description": text(body.description, 600),
         "at": now, "updated_at": now}
    if not await claim_slot(d.nb_projects, p, {"user_id": uid}, cap):      # parallel creates can't pass the cap
        raise full
    await events.track(d, "notebook_created", user_id=uid)
    return _pub_project(p)


@router.get("/{pid}")
async def detail(pid: str, user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, "research")
    p = await _project(pid, user)
    sources = await _sources(pid)
    notes = [_pub_note(n) async for n in d.nb_notes.find({"project_id": pid}).sort("at", -1)]
    msgs = [_pub_msg(m) async for m in d.nb_messages.find({"project_id": pid}).sort("at", -1).limit(30)]
    return {"project": _pub_project(p, len(sources), len(notes)), "sources": [_pub_source(s) for s in sources],
            "notes": notes, "messages": list(reversed(msgs)), "audio": _audio_public(p.get("audio"), _sig(sources)),
            "max_sources": MAX_SOURCES, "kinds": [{"kind": k, "label": v} for k, v in KINDS.items()]}


@router.patch("/{pid}")
async def edit(pid: str, body: ProjectPatch, user: dict = Depends(user_dep())):
    await plans.require(db(), user, "research")
    p = await _project(pid, user)
    up = {k: text(v, 600 if k == "description" else 120) for k, v in body.model_dump(exclude_none=True).items()}
    if up:
        up["updated_at"] = utcnow()
        await db().nb_projects.update_one({"_id": pid}, {"$set": up})
        p |= up
    return _pub_project(p)


@router.delete("/{pid}")
async def remove(pid: str, user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, "research")
    p = await _project(pid, user)
    for coll in (d.nb_chunks, d.nb_sources, d.nb_notes, d.nb_messages):
        await coll.delete_many({"project_id": pid})
    await media.delete_blob(d, (p.get("audio") or {}).get("blob_id"))
    await d.nb_projects.delete_one({"_id": pid})
    return {"ok": True}


# ------------------------------------------------------------------ sources ----
def _sources_full():
    return bad("sources_full", f"A project holds up to {MAX_SOURCES} sources. Remove one to add another.", 409)


async def _room(pid: str) -> None:
    """Quick check before reading a file or a page. The real reservation is claim_slot in _add_source."""
    if await db().nb_sources.count_documents({"project_id": pid}) >= MAX_SOURCES:
        raise _sources_full()


def _prep(raw: str, *, markdown: bool = False) -> tuple[str, int, bool]:
    body = clean_text(strip_markdown(raw) if markdown else raw)
    words = body.split()
    if len(words) < 5:
        raise bad("empty", "There's not enough text there to use as a source.", 422)
    if len(words) > MAX_WORDS:
        return " ".join(words[:MAX_WORDS]), MAX_WORDS, True
    return body, len(words), False


async def _add_source(user: dict, pid: str, *, kind: str, title: str, body: str = "", words: int = 0,
                      page_starts: Optional[list[int]] = None, pages: Optional[int] = None, url: Optional[str] = None,
                      doc_id: Optional[str] = None, test: bool = False, truncated: bool = False,
                      chunks: Optional[list[dict]] = None) -> dict:
    d = db()
    uid = str(user["_id"])
    await _room(pid)
    sid = uuid.uuid4().hex
    title = text(title, 120) or "Untitled source"
    parts = chunks if chunks is not None else make_chunks(body, page_starts)
    rows = [{"_id": f"{sid}:{c['i']}", "source_id": sid, "project_id": pid, "user_id": uid, "title": title,
             "i": c["i"], "page": c.get("page"), "breaks": c.get("breaks") or [], "text": c["text"], "tokens": c["tokens"],
             "n": c.get("n") or len(c["tokens"])}
            for c in parts]
    s = {"_id": sid, "project_id": pid, "user_id": uid, "kind": kind, "title": title, "url": url, "doc_id": doc_id,
         "words": words, "pages": pages, "chunks": len(rows), "ntok": sum(r["n"] for r in rows), "truncated": truncated,
         "test": test, "at": utcnow()}
    if not await claim_slot(d.nb_sources, s, {"project_id": pid}, MAX_SOURCES):
        raise _sources_full()
    try:
        if rows:
            await d.nb_chunks.insert_many(rows)
    except BaseException:
        await d.nb_chunks.delete_many({"source_id": sid})
        await d.nb_sources.delete_one({"_id": sid})
        raise
    await _touch(pid)
    await events.track(d, "notebook_source_added", user_id=uid, props={"kind": kind, "words": words})
    return _pub_source(s)


@router.post("/{pid}/sources/file")
async def add_file(pid: str, file: UploadFile = File(...), title: Optional[str] = Form(None),
                   user: dict = Depends(user_dep())):
    await plans.require(db(), user, "research")
    await _project(pid, user)
    await _room(pid)
    got = await read_upload(file)
    return await _add_source(user, pid, kind="file", title=text(title, 120) or got["title"], body=got["text"],
                             words=got["words"], page_starts=got["page_starts"], pages=got["pages"],
                             truncated=got["truncated"])


class TextIn(BaseModel):
    title: str = Field("", max_length=120)
    text: str = Field(..., min_length=20, max_length=200_000)


@router.post("/{pid}/sources/text")
async def add_text(pid: str, body: TextIn, user: dict = Depends(user_dep())):
    await plans.require(db(), user, "research")
    await _project(pid, user)
    t, words, cut = _prep(body.text)
    return await _add_source(user, pid, kind="text", title=body.title or f"Pasted text: {' '.join(t.split()[:6])}",
                             body=t, words=words, truncated=cut)


class UrlIn(BaseModel):
    url: str = Field(..., min_length=8, max_length=500)


def _clean_url(u: str) -> str:
    u = u.strip()
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    host = urlparse(u).hostname or ""
    if "." not in host or " " in u:
        raise bad("bad_url", "That doesn't look like a web address. Paste the full link, like https://example.com/page.")
    return u


@router.post("/{pid}/sources/url")
async def add_url(pid: str, body: UrlIn, user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, "research")
    await _project(pid, user)
    url = _clean_url(body.url)
    await _room(pid)
    if await d.nb_sources.find_one({"project_id": pid, "url": url}, {"_id": 1}):
        raise bad("duplicate", "This page is already in the project.", 409)
    if search.mode() == "off":
        raise bad("web_off", "Adding web pages is switched off right now. Copy the page's text and add it as pasted text.", 503)
    found = await search.extract([url])
    if not found:
        raise bad("url_failed", "We couldn't read that page. Some sites block this. Copy the text and paste it instead.", 422)
    page = found[0]
    t, words, cut = _prep(page["text"])
    return await _add_source(user, pid, kind="url", title=page.get("title") or urlparse(url).hostname or url, body=t,
                             words=words, url=url, test=bool(page.get("test")), truncated=cut)


class DocIn(BaseModel):
    doc_id: str = Field(..., min_length=1, max_length=64)


@router.post("/{pid}/sources/doc")
async def add_doc(pid: str, body: DocIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    await plans.require(d, user, "research")
    await _project(pid, user)
    doc = await d.reader_docs.find_one({"_id": body.doc_id, "user_id": uid}, {"summary": 0})
    if not doc:
        raise not_found("Document")
    if await d.nb_sources.find_one({"project_id": pid, "doc_id": body.doc_id}, {"_id": 1}):
        raise bad("duplicate", "This document is already in the project.", 409)
    chunks = [c async for c in d.reader_chunks.find({"doc_id": body.doc_id, "user_id": uid}).sort("i", 1)]
    return await _add_source(user, pid, kind="doc", title=doc["title"], words=doc.get("words", 0), pages=doc.get("pages"),
                             doc_id=body.doc_id, truncated=bool(doc.get("truncated")), chunks=chunks)


@router.delete("/{pid}/sources/{sid}")
async def remove_source(pid: str, sid: str, user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, "research")
    await _project(pid, user)
    res = await d.nb_sources.delete_one({"_id": sid, "project_id": pid})
    if not res.deleted_count:
        raise not_found("Source")
    await d.nb_chunks.delete_many({"source_id": sid, "project_id": pid})
    await _touch(pid)
    return {"ok": True}


# ------------------------------------------------------------------ ask ----
class AskIn(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)


@router.post("/{pid}/ask")
async def ask(pid: str, body: AskIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    await plans.require(d, user, "research")
    p = await _project(pid, user)
    sources = await _sources(pid)
    if not sources:
        raise bad("no_sources", "Add a source first.")
    n = sum(s.get("chunks", 0) for s in sources)
    avg = sum(s.get("ntok", 0) for s in sources) / n if n else 1.0
    hits = await retrieve(d.nb_chunks, {"project_id": pid, "user_id": uid}, body.question, n_chunks=n, avg_len=avg)

    async def save(out: dict) -> dict:
        m = {"_id": uuid.uuid4().hex, "project_id": pid, "user_id": uid, "question": text(body.question, 1000),
             "answer": out["answer"], "covered": out["covered"], "citations": out["citations"], "at": utcnow()}
        await d.nb_messages.insert_one(m)
        await _touch(pid)
        await events.track(d, "notebook_asked", user_id=uid, props={"covered": out["covered"], "cited": len(out["citations"])})
        return _pub_msg(m)

    if not hits:
        return await save({"answer": NOT_COVERED.replace("your documents", "this project's sources"), "covered": False,
                           "citations": []})

    async def work(plan: str):
        ctx = f"PROJECT: {p['title']}" + (f" — {p['description']}" if p.get("description") else "") + "\n\n"
        out = await cited_answer(body.question, hits, task="notebook_ask", ref_key="source_id", context=ctx)
        return await save(out)
    return await run_metered(d, user, "doc_q", work, access="research")


# ------------------------------------------------------------------ generate ----
async def _context(pid: str, sources: list[dict], *, dated: bool = False) -> tuple[str, list[dict], list[str]]:
    """Evenly spaced excerpts from every source, within GEN_BUDGET words. Returns (block, sources used, texts)."""
    per = max(350, GEN_BUDGET // max(1, len(sources)))
    used, blocks, texts = [], [], []
    for s in sources:
        chunks = [c async for c in db().nb_chunks.find({"source_id": s["_id"], "project_id": pid}, {"text": 1, "i": 1}).sort("i", 1)]
        if dated:
            chunks = [c for c in chunks if DATE.search(c["text"])]
        picked = spread(chunks, per)
        if not picked:
            continue
        used.append(s)
        texts.extend(c["text"] for c in picked)
        blocks.append(f"SOURCE {len(used)}: {s['title']}\n" + "\n…\n".join(c["text"] for c in picked))
    return "\n\n".join(blocks), used, texts


def _top_terms(texts: list[str], n: int = 6) -> list[str]:
    c = Counter(t for x in texts for t in kb.tokens(x) if len(t) >= 5 and not t.isdigit())
    return [t for t, _ in c.most_common(n)]


def _fake_gen(kind: str, title: str, used: list[dict], texts: list[str]) -> dict:
    sents = [s for x in texts for s in sentences(x)] or [first_sentence(x) for x in texts]
    cyc = lambda i: text(sents[i % len(sents)], 220) if sents else "The sources say little here."  # noqa: E731
    if kind == "briefing":
        return {"title": f"{title}: briefing", "summary": " ".join(cyc(i) for i in range(2)),
                "sections": [{"heading": s["title"], "points": [cyc(i * 3 + j) for j in range(3)]} for i, s in enumerate(used[:4])],
                "takeaways": ["Check the figures in the sources before you use them with a client.",
                              "Write down the open questions to raise in your next client conversation."]}
    if kind == "faq":
        return {"items": [{"q": f"What do the sources say about {' '.join(kb.tokens(cyc(i))[:3]) or 'this'}?", "a": cyc(i)}
                          for i in range(8)]}
    if kind == "study":
        terms = _top_terms(texts) or ["topic", "source", "summary"]
        mean = lambda t: next((text(s, 200) for s in sents if t in s.lower()), "Used in the sources.")  # noqa: E731
        return {"summary": cyc(0), "key_terms": [{"term": t, "meaning": mean(t)} for t in terms],
                "quiz": [{"q": f"True or false: {cyc(i)}", "answer": "True. This is what the sources say."} for i in range(6)]}
    seen, events_ = set(), []
    for s in sents:
        m = DATE.search(s)
        if m and m.group(0).lower() not in seen:
            seen.add(m.group(0).lower())
            events_.append({"date": m.group(0), "event": text(s, 220)})
    return {"events": events_[:12]}


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items)


def _check_gen(kind: str, raw: dict, block: str) -> tuple[str, str]:
    """Validate the AI's JSON and render it as Markdown. Returns (title, body)."""
    if not isinstance(raw, dict):
        raise llm.LLMError(f"{kind}: bad shape")
    raw = strip_providers(raw)
    if kind == "briefing":
        summary = text(raw.get("summary"), 900)
        secs = [{"heading": text(x.get("heading"), 120), "points": text_list(x.get("points"), 6, 320)}
                for x in as_list(raw.get("sections"))[:6] if isinstance(x, dict)]
        secs = [x for x in secs if x["heading"] and x["points"]]
        if not summary or not secs:
            raise llm.LLMError("briefing: incomplete")
        take = text_list(raw.get("takeaways"), 6, 260)
        body = f"{summary}\n\n" + "\n\n".join(f"### {x['heading']}\n{_bullets(x['points'])}" for x in secs)
        if take:
            body += f"\n\n### What to do with this\n{_bullets(take)}"
        return text(raw.get("title"), 120) or KINDS[kind], body
    if kind == "faq":
        items = [(text(x.get("q"), 240), text(x.get("a"), 700)) for x in as_list(raw.get("items"))[:10] if isinstance(x, dict)]
        items = [x for x in items if x[0] and x[1]]
        if len(items) < 5:
            raise llm.LLMError("faq: too few")
        return KINDS[kind], "\n\n".join(f"**{q}**\n\n{a}" for q, a in items)
    if kind == "study":
        terms = [(text(x.get("term"), 80), text(x.get("meaning"), 300)) for x in as_list(raw.get("key_terms"))[:12]
                 if isinstance(x, dict)]
        terms = [x for x in terms if x[0] and x[1]]
        quiz = [(text(x.get("q"), 300), text(x.get("answer"), 400)) for x in as_list(raw.get("quiz"))[:10] if isinstance(x, dict)]
        quiz = [x for x in quiz if x[0] and x[1]]
        if len(terms) < 3 or len(quiz) < 3:
            raise llm.LLMError("study: incomplete")
        summary = text(raw.get("summary"), 600)
        body = (f"{summary}\n\n" if summary else "") + "### Key terms\n" + _bullets([f"**{t}**: {m}" for t, m in terms])
        body += "\n\n### Test yourself\n" + "\n\n".join(f"**{i + 1}. {q}**\n\nAnswer: {a}" for i, (q, a) in enumerate(quiz))
        return KINDS[kind], body
    seen = _nums(block)
    low = block.lower()
    rows = []
    for x in as_list(raw.get("events"))[:20]:
        if not isinstance(x, dict):
            continue
        date, what = text(x.get("date"), 60), text(x.get("event"), 300)
        found = _nums(date)
        ok = (found and found <= seen) if found else (date.lower() in low)       # dates only as written in the sources
        if date and what and ok:
            rows.append((date, what))
    if not rows:
        raise bad("no_dates", "We couldn't find dated events in your sources, so there's no timeline to make. "
                              "This didn't use up a question.", 422)
    return KINDS[kind], "\n".join(f"- **{dt}**: {w}" for dt, w in rows)


PROMPTS = {
    "briefing": ("Write a briefing document: title (short), summary (3-4 sentences: the main message across the sources), "
                 "sections (3-5, each a heading and 2-5 short points), takeaways (3-5 things the member should do or remember).\n"
                 'JSON: {"title": "", "summary": "", "sections": [{"heading": "", "points": [""]}], "takeaways": [""]}'),
    "faq": ("Write 8 to 10 questions a client or colleague would ask about this topic, each answered in 1-3 sentences "
            "from the sources.\nJSON: {\"items\": [{\"q\": \"\", \"a\": \"\"}]}"),
    "study": ("Write a study guide: summary (2-3 sentences), key_terms (6-10 terms, names or ideas from the sources, each "
              "with a plain meaning), quiz (6-8 short questions with answers, to check understanding).\n"
              'JSON: {"summary": "", "key_terms": [{"term": "", "meaning": ""}], "quiz": [{"q": "", "answer": ""}]}'),
    "timeline": ("List the dated events in the sources, in time order. Use only dates written in the sources, exactly as "
                 "written. Each item: the date and what happened, in one sentence. Leave out anything without a date.\n"
                 'JSON: {"events": [{"date": "", "event": ""}]}'),
}


class GenIn(BaseModel):
    kind: Literal["briefing", "faq", "study", "timeline"]


@router.post("/{pid}/generate")
async def generate(pid: str, body: GenIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    await plans.require(d, user, "research")
    p = await _project(pid, user)
    sources = await _sources(pid)
    if not sources:
        raise bad("no_sources", "Add a source first.")
    block, used, texts = await _context(pid, sources, dated=body.kind == "timeline")
    if not used and body.kind == "timeline":
        raise bad("no_dates", "Your sources don't mention any dates, so there's no timeline to make.", 422)
    if not used:
        raise bad("no_sources", "Add a source first.")

    async def work(plan: str):
        prompt = (f"PROJECT: {p['title']}" + (f" — {p['description']}" if p.get("description") else "") +
                  f"\n\nSOURCES:\n{block}\n\n{PROMPTS[body.kind]}")
        raw = await llm.complete_json(task=f"notebook_{body.kind}", system=GEN_SYSTEM, prompt=prompt,
                                      fake=lambda: _fake_gen(body.kind, p["title"], used, texts), model="strong",
                                      max_tokens=4000 if body.kind == "briefing" else 3000)   # room to finish the JSON
        title, md = _check_gen(body.kind, raw, block)
        md += "\n\n---\nMade from: " + " · ".join(s["title"] for s in used)
        now = utcnow()
        n = {"_id": uuid.uuid4().hex, "project_id": pid, "user_id": uid, "kind": body.kind, "title": title,
             "body": md, "at": now, "updated_at": now}
        await d.nb_notes.insert_one(n)
        await _touch(pid)
        await events.track(d, "notebook_generated", user_id=uid, props={"kind": body.kind})
        return _pub_note(n)
    return await run_metered(d, user, "doc_q", work, access="research")


# ------------------------------------------------------------------ notes ----
class NoteIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    body: str = Field(..., min_length=1, max_length=20_000)
    kind: Literal["note", "answer"] = "note"


class NotePatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=120)
    body: Optional[str] = Field(None, min_length=1, max_length=20_000)


@router.post("/{pid}/notes")
async def add_note(pid: str, body: NoteIn, user: dict = Depends(user_dep())):
    await plans.require(db(), user, "research")
    await _project(pid, user)
    now = utcnow()
    n = {"_id": uuid.uuid4().hex, "project_id": pid, "user_id": str(user["_id"]), "kind": body.kind,
         "title": text(body.title, 120), "body": tidy(body.body, 20_000), "at": now, "updated_at": now}
    await db().nb_notes.insert_one(n)
    await _touch(pid)
    return _pub_note(n)


@router.patch("/{pid}/notes/{nid}")
async def edit_note(pid: str, nid: str, body: NotePatch, user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, "research")
    await _project(pid, user)
    n = await d.nb_notes.find_one({"_id": nid, "project_id": pid})
    if not n:
        raise not_found("Note")
    up = {}
    if body.title is not None:
        up["title"] = text(body.title, 120)
    if body.body is not None:
        up["body"] = tidy(body.body, 20_000)
    if up:
        up["updated_at"] = utcnow()
        await d.nb_notes.update_one({"_id": nid}, {"$set": up})
        n |= up
    return _pub_note(n)


@router.delete("/{pid}/notes/{nid}")
async def remove_note(pid: str, nid: str, user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, "research")
    await _project(pid, user)
    if not (await d.nb_notes.delete_one({"_id": nid, "project_id": pid})).deleted_count:
        raise not_found("Note")
    return {"ok": True}


# ------------------------------------------------------------------ audio overview ----
def _fake_script(title: str, used: list[dict], texts: list[str]) -> dict:
    sents = [s for x in texts for s in sentences(x)] or texts or ["The sources are short."]
    names = ", ".join(s["title"] for s in used[:4])
    parts = [f"Welcome. This is a short audio overview of your research on {title}. It is made from {len(used)} "
             f"source{'s' if len(used) != 1 else ''}: {names}. Let's walk through what they say."]
    i = 0
    while sum(len(x.split()) for x in parts) < 470:
        parts.append(text(sents[i % len(sents)], 300))
        i += 1
    parts.append("That's the overview. Two questions to think about: what in these sources surprised you, and what "
                 "would you ask a client about it first? Thanks for listening.")
    return {"title": f"{title}: audio overview", "script": " ".join(parts)}


@router.post("/{pid}/audio")
async def audio_overview(pid: str, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    await plans.require(d, user, "research")
    p = await _project(pid, user)
    sources = await _sources(pid)
    if not sources:
        raise bad("no_sources", "Add a source first.")
    sig = _sig(sources)
    old = p.get("audio") or {}
    if old.get("blob_id") and old.get("sig") == sig:
        return _audio_public(old, sig) | {"cached": True}
    block, used, texts = await _context(pid, sources)

    async def work(plan: str):
        prompt = f"PROJECT: {p['title']}\n\nSOURCES:\n{block}\n\nWrite the script.\nJSON: {{\"title\": \"\", \"script\": \"\"}}"
        raw = await llm.complete_json(task="notebook_audio", system=AUDIO_SYSTEM, prompt=prompt,
                                      fake=lambda: _fake_script(p["title"], used, texts), model="strong", max_tokens=2000)
        script = text(strip_providers(strip_markdown(str(raw.get("script") or ""))), 9000) if isinstance(raw, dict) else ""
        words = len(script.split())
        if words < 250 or words > 1100:
            raise llm.LLMError("audio script: wrong length")
        try:
            data, ctype = await tts.speak(script)
            blob_id = await media.save_blob(d, user_id=uid, kind="notebook_audio", content_type=ctype, data=data,
                                            name=f"{p['title'][:80]} overview")
        except (tts.TTSError, media.TooLarge) as e:
            raise bad("audio_busy", "We couldn't make the audio right now. Try again in a few minutes. "
                                    "This didn't use up your go.", 503) from e
        a = {"blob_id": blob_id, "sig": sig, "title": text(raw.get("title"), 120) or f"{p['title']}: audio overview",
             "script": script, "words": words, "minutes": round(words / 150, 1), "at": utcnow()}
        await d.nb_projects.update_one({"_id": pid}, {"$set": {"audio": a, "updated_at": utcnow()}})
        await media.delete_blob(d, old.get("blob_id"))
        await events.track(d, "notebook_audio", user_id=uid, props={"minutes": a["minutes"]})
        return _audio_public(a, sig) | {"cached": False}
    return await run_metered(d, user, "audio", work, access="research")
