"""Doc Reader: upload a report, ask it questions, get answers that point to the exact lines (₹1,999 plan and up).

reader_docs      {_id, user_id, title, kind pdf|docx|txt|md, size, pages, pages_estimated, words, chunks, ntok,
                  truncated, summary?: {overview, key_points, numbers, decisions, risks, at}, at}
reader_chunks    {_id, doc_id, user_id, title, i, page, text, tokens, n}
reader_questions {_id, user_id, question, answer, covered, citations, doc_ids, at}

Privacy: the original file is never kept. We read the text, chunk it, and drop the file.
Retrieval is a plain BM25 over the member's own chunks (the same scorer as features/kb.py, per user).
The AI answers only from the numbered excerpts it is shown; citation numbers are checked against them, so an
answer can never point at text that isn't in the member's documents.

The extraction, chunking, retrieval and cited-answer helpers here are shared with features/notebook.py.
"""
from __future__ import annotations

import io
import math
import re
import uuid
from bisect import bisect_right
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

import indexes
import llm
import plans
from core.deps import user_dep
from growth import events
from growth.clock import utcnow
from state import db
from util import iso

from . import kb
from .common import NO_VENDOR, as_list, run_metered, strip_providers, text, text_list

router = APIRouter(prefix="/docs", tags=["doc-reader"])

events.register("doc_uploaded", "Doc Reader document added (props.kind, pages, words)")
events.register("doc_deleted", "Doc Reader document deleted")
events.register("doc_asked", "Doc Reader question answered (props.covered, cited, docs)")
events.register("doc_summary", "Doc Reader summary made (props.words)")
indexes.register("reader_docs", [("user_id", 1), ("at", -1)])
indexes.register("reader_chunks", [("user_id", 1), ("tokens", 1)])
indexes.register("reader_chunks", [("doc_id", 1), ("i", 1)])
indexes.register("reader_questions", [("user_id", 1), ("at", -1)])

MAX_BYTES = 10 * 1024 * 1024
MAX_WORDS = 300_000              # ~600 pages; anything longer is read up to here and marked "truncated"
TOP_K = 6
TYPES = {".pdf": "pdf", ".docx": "docx", ".txt": "txt", ".md": "md", ".markdown": "md"}
TYPE_MSG = "Upload a PDF, a Word file (.docx), or a .txt or .md file."

NO_PROVIDER = ("Never say which AI company or model you are and never name any AI provider or product. "
               "If asked, you are the hub's AI. " + NO_VENDOR)


def bad(code: str, msg: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "msg": msg})


def not_found(what: str = "Document") -> HTTPException:
    return bad("not_found", f"{what} not found.", 404)


# ------------------------------------------------------------------ reading files ----
def kind_of(filename: str) -> str:
    name = (filename or "").lower().strip()
    ext = name[name.rfind("."):] if "." in name else ""
    if ext not in TYPES:
        raise bad("bad_type", TYPE_MSG, 415)
    return TYPES[ext]


def title_from(filename: str) -> str:
    stem = (filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = stem.rsplit(".", 1)[0] if "." in stem else stem
    return text(re.sub(r"[_]+", " ", stem), 120) or "Untitled document"


_MD_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MD_MARK = re.compile(r"(^|\s)#{1,6}\s+|[*_`>|]{1,3}|^\s*[-+]\s+", re.M)


def strip_markdown(s: str) -> str:
    s = _MD_IMG.sub(" ", s)
    s = _MD_LINK.sub(r"\1", s)
    s = re.sub(r"^\s*-{3,}\s*$", " ", s, flags=re.M)
    return _MD_MARK.sub(" ", s)


def clean_text(s: str) -> str:
    """One page or file of raw text → single-spaced words. Joins words broken across lines with a hyphen."""
    s = (s or "").replace("\x00", " ").replace("\r", "\n").replace("­", "")
    s = re.sub(r"(\w)-\n\s*(\w)", r"\1\2", s)
    return " ".join(s.split())


def _pdf_pages(data: bytes) -> list[str]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                ok = reader.decrypt("")
            except Exception:  # noqa: BLE001
                ok = 0
            if not ok:
                raise bad("locked_pdf", "This PDF has a password. Save a copy without the password and upload that.")
        pages = list(reader.pages)
    except HTTPException:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as e:
        raise bad("unreadable", "We couldn't open this PDF. It may be damaged. Try saving it again and upload the new copy.") from e
    out = []
    for p in pages:
        try:
            out.append(p.extract_text() or "")
        except Exception:  # noqa: BLE001 — one bad page shouldn't sink the file
            out.append("")
    return out


def _docx_text(data: bytes) -> str:
    try:
        import docx
        d = docx.Document(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise bad("unreadable", "We couldn't open this Word file. Save it as .docx and try again.") from e
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(dict.fromkeys(cells)))
    return "\n".join(parts)


def _decode(data: bytes) -> str:
    encs = ("utf-16", "utf-8-sig") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig",)
    for enc in encs:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_file(data: bytes, filename: str) -> dict:
    """Bytes of an upload → {kind, title, text, words, pages, pages_estimated, page_starts, truncated}.
    Raises a plain 4xx for wrong type, unreadable, scanned or empty files. The bytes are not kept."""
    kind = kind_of(filename)
    if not data:
        raise bad("empty", "That file is empty.")
    if len(data) > MAX_BYTES:
        raise bad("too_large", "That file is bigger than 10 MB. Split it or save a smaller copy.", 413)
    if kind == "pdf":
        if not data.lstrip()[:5].startswith(b"%PDF"):
            raise bad("bad_type", "That file doesn't look like a PDF. " + TYPE_MSG, 415)
        raw_pages = _pdf_pages(data)
    elif kind == "docx":
        if not data.startswith(b"PK"):
            raise bad("bad_type", "That file doesn't look like a Word .docx file. Old .doc files need saving as .docx first.", 415)
        raw_pages = [_docx_text(data)]
    else:
        raw = _decode(data)
        raw_pages = [strip_markdown(raw) if kind == "md" else raw]
    pages = [clean_text(p) for p in raw_pages]
    counts = [len(p.split()) for p in pages]
    words = sum(counts)
    if kind == "pdf" and (words < 3 or words < 5 * len(pages)):
        raise bad("scanned", "This PDF looks like a scan (pictures of pages), so there is no text to read. "
                             "Upload the original Word or PDF file, or a copy with selectable text.", 422)
    if words < 3:
        raise bad("empty", "We found no text in that file.", 422)
    starts, at = [], 0
    for c in counts:
        starts.append(at)
        at += c
    full = " ".join(p for p in pages if p)
    truncated = words > MAX_WORDS
    if truncated:
        full = " ".join(full.split()[:MAX_WORDS])
        words = MAX_WORDS
    n_pages = len(pages) if kind == "pdf" else max(1, round(words / 500))
    return {"kind": kind, "title": title_from(filename), "size": len(data), "text": full, "words": words, "pages": n_pages,
            "pages_estimated": kind != "pdf", "page_starts": starts if kind == "pdf" else None, "truncated": truncated}


def make_chunks(full: str, page_starts: Optional[list[int]] = None) -> list[dict]:
    """kb.chunk + kb.tokens, with the page each chunk starts on (PDFs)."""
    step = int(kb.CHUNK_WORDS * 0.85)
    out = []
    for i, t in enumerate(kb.chunk(full)):
        toks = kb.tokens(t)
        page = bisect_right(page_starts, i * step) if page_starts else None
        out.append({"i": i, "page": page, "text": t, "tokens": toks, "n": len(toks)})
    return out


async def read_upload(file: UploadFile) -> dict:
    kind_of(file.filename or "")                       # wrong type → refuse before reading the bytes
    data = await file.read(MAX_BYTES + 1)
    try:
        return read_file(data, file.filename or "")
    finally:
        del data


# ------------------------------------------------------------------ retrieval ----
async def retrieve(coll, flt: dict, question: str, *, n_chunks: int, avg_len: float, k: int = TOP_K) -> list[dict]:
    """BM25 over one member's chunks: only chunks sharing a word with the question are read from Mongo."""
    q = list(dict.fromkeys(kb.tokens(question)))
    if not q or n_chunks <= 0:
        return []
    rows = [r async for r in coll.find({**flt, "tokens": {"$in": q}})]
    df = Counter(t for r in rows for t in set(r.get("tokens") or []) if t in q)
    avg = avg_len or 1.0
    scored = []
    for r in rows:
        tf = Counter(r.get("tokens") or [])
        ln = r.get("n") or sum(tf.values()) or 1
        s = 0.0
        for t in q:
            f = tf.get(t)
            if not f:
                continue
            idf = math.log(1 + (n_chunks - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * ln / avg))
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: (-x[0], str(x[1].get("_id"))))
    return [r | {"score": round(s, 3)} for s, r in scored[:k]]


def snippet(t: str, question: str, width: int = 48) -> str:
    """The ~50-word window of a chunk that best matches the question (what a citation shows)."""
    words = t.split()
    if len(words) <= width:
        return t
    q = set(kb.tokens(question))
    hits = [1 if q.intersection(kb.tokens(w)) else 0 for w in words]
    best, best_at, cur = -1, 0, sum(hits[:width])
    for i in range(0, len(words) - width + 1):
        if i:
            cur += hits[i + width - 1] - hits[i - 1]
        if cur > best:
            best, best_at = cur, i
    part = " ".join(words[best_at:best_at + width])
    return ("… " if best_at else "") + part + (" …" if best_at + width < len(words) else "")


def sentences(t: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t or "") if len(s.split()) >= 4]


def first_sentence(t: str, n: int = 220) -> str:
    s = sentences(t)
    return text(s[0] if s else t, n)


def spread(chunks: list[dict], budget_words: int) -> list[dict]:
    """Evenly spaced, non-overlapping chunks (they overlap by 15%) up to a word budget, in reading order."""
    if not chunks:
        return []
    per = max(1, len(chunks[0]["text"].split()))
    want = max(1, budget_words // per)
    pool = chunks[::2] if len(chunks) > 2 else chunks
    if len(pool) <= want:
        return pool
    stepf = len(pool) / want
    return [pool[int(i * stepf)] for i in range(want)]


# ------------------------------------------------------------------ cited answers ----
ASK_SYSTEM = (
    "You answer questions about a member's own documents inside a consulting hub. Members are experienced Indian "
    "professionals getting ready to work as consultants. Use ONLY the numbered excerpts you are given: no outside "
    "knowledge and no guessing. After each sentence that uses an excerpt, put its number in square brackets, like [1] "
    "or [2][3]. Use only numbers that appear in the excerpts list. Quote figures exactly as written. If the excerpts "
    "don't answer the question, set covered to false and say plainly that the documents don't cover it (you may say "
    "in one line what they do cover). Plain, short, spoken English. No buzzwords, no hype. " + NO_PROVIDER
)


def excerpt_block(hits: list[dict]) -> str:
    out = []
    for i, h in enumerate(hits):
        where = h.get("title") or "Document"
        if h.get("page"):
            where += f", page {h['page']}"
        out.append(f"[{i + 1}] ({where})\n{h['text']}")
    return "\n\n".join(out)


def fake_answer(question: str, hits: list[dict]) -> dict:
    lines = [f"- {first_sentence(h['text'], 200)} [{i + 1}]" for i, h in enumerate(hits[:2])]
    return {"covered": True, "answer": "Here is what your documents say.\n\n" + "\n".join(lines)}


_CITE = re.compile(r"\[(\d{1,2})\]")
_MULTI = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})+)\]")


def tidy(s: str, n: int = 5000) -> str:
    s = str(s or "").replace("\r", "").strip()
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n{3,}", "\n\n", s)[:n]


def check_citations(answer: str, n_hits: int) -> tuple[str, list[int]]:
    """Normalise [1, 2] → [1][2]; drop numbers that don't match an excerpt; return the cited numbers in order."""
    answer = _MULTI.sub(lambda m: "".join(f"[{x.strip()}]" for x in m.group(1).split(",")), answer)
    used: list[int] = []

    def keep(m):
        n = int(m.group(1))
        if 1 <= n <= n_hits:
            if n not in used:
                used.append(n)
            return m.group(0)
        return ""
    answer = _CITE.sub(keep, answer)
    return re.sub(r" +([.,;:])", r"\1", answer).strip(), used


async def cited_answer(question: str, hits: list[dict], *, task: str, ref_key: str, context: str = "") -> dict:
    """Ask the AI over numbered excerpts. Returns {answer, covered, citations: [{n, <ref_key>, doc_title, page, excerpt}]}.
    Wrong shape, or a "covered" answer with no real citation → LLMError (the caller refunds)."""
    prompt = (f"{context}QUESTION: {question}\n\nEXCERPTS:\n{excerpt_block(hits)}\n\n"
              "Answer in 2 to 6 short sentences, or a few bullet points (Markdown is fine).\n"
              'JSON: {"covered": true, "answer": ""}')
    raw = await llm.complete_json(task=task, system=ASK_SYSTEM, prompt=prompt, fake=lambda: fake_answer(question, hits),
                                  model="strong", max_tokens=1200)
    if not isinstance(raw, dict) or not isinstance(raw.get("answer"), str):
        raise llm.LLMError(f"{task}: bad shape")
    answer, used = check_citations(tidy(strip_providers(raw["answer"])), len(hits))
    covered = raw.get("covered") is not False
    if not answer:
        raise llm.LLMError(f"{task}: empty answer")
    if covered and not used:
        raise llm.LLMError(f"{task}: answer without citations")
    cites = []
    for n in used:
        h = hits[n - 1]
        cites.append({"n": n, ref_key: h.get(ref_key), "doc_title": h.get("title") or "Document", "page": h.get("page"),
                      "excerpt": snippet(h["text"], question)})
    return {"answer": answer, "covered": covered and bool(used), "citations": cites}


NOT_COVERED = ("I couldn't find this in your documents. Try other words, or check that the right document is "
               "uploaded.")


# ------------------------------------------------------------------ summary ----
SUM_SYSTEM = (
    "You summarise a member's document for an experienced professional who is becoming a consultant. Use only the "
    "text you are given. Plain, short, spoken English. Quote figures exactly as they appear; never work out or invent "
    "a number. If the document has no decisions or no risks, return an empty list for that part. " + NO_PROVIDER
)
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _nums(s: str) -> set[str]:
    return {m.replace(",", "").rstrip(".") for m in _NUM.findall(s or "")}


def fake_summary(title: str, body: str) -> dict:
    sents = sentences(body)
    pick = lambda *ks: [text(s, 220) for s in sents if any(k in s.lower() for k in ks)][:3]  # noqa: E731
    numbers = []
    for s in sents:
        m = _NUM.search(s)
        if m and len(numbers) < 3:
            numbers.append({"figure": m.group(0), "meaning": text(s, 160)})
    return {"overview": f"{title}: {first_sentence(body, 300)}",
            "key_points": [text(s, 220) for s in sents[:4]] or [text(body, 220)],
            "numbers": numbers, "decisions": pick("decid", "agreed", "approved", "will "),
            "risks": pick("risk", "delay", "concern", "issue")}


def check_summary(raw: dict, source: str) -> dict:
    if not isinstance(raw, dict):
        raise llm.LLMError("summary: bad shape")
    raw = strip_providers(raw)
    seen = _nums(source)
    numbers = []
    for x in as_list(raw.get("numbers"))[:8]:
        if not isinstance(x, dict):
            continue
        fig, meaning = text(x.get("figure"), 60), text(x.get("meaning"), 200)
        found = _nums(fig)
        if fig and meaning and found and found <= seen:        # every figure must be in the text it was given
            numbers.append({"figure": fig, "meaning": meaning})
    out = {"overview": text(raw.get("overview"), 700), "key_points": text_list(raw.get("key_points"), 8, 260),
           "numbers": numbers, "decisions": text_list(raw.get("decisions"), 6, 260),
           "risks": text_list(raw.get("risks"), 6, 260)}
    if not out["overview"] or len(out["key_points"]) < 2:
        raise llm.LLMError("summary: incomplete")
    return out


# ------------------------------------------------------------------ endpoints ----
def _public(d: dict) -> dict:
    return {"id": d["_id"], "title": d["title"], "kind": d["kind"], "size_kb": max(1, round((d.get("size") or 0) / 1024)),
            "pages": d.get("pages"), "pages_estimated": bool(d.get("pages_estimated")), "words": d.get("words", 0),
            "chunks": d.get("chunks", 0), "truncated": bool(d.get("truncated")), "has_summary": bool(d.get("summary")),
            "at": iso(d["at"])}


def _summary_public(s: Optional[dict]) -> Optional[dict]:
    if not s:
        return None
    return {k: s.get(k) for k in ("overview", "key_points", "numbers", "decisions", "risks")} | {"at": iso(s.get("at"))}


def _question_public(q: dict) -> dict:
    return {"id": q["_id"], "question": q["question"], "answer": q["answer"], "covered": q["covered"],
            "citations": q.get("citations", []), "doc_ids": q.get("doc_ids") or [], "at": iso(q["at"])}


async def user_docs(user: dict, ids: Optional[list[str]] = None) -> list[dict]:
    flt: dict = {"user_id": str(user["_id"])}
    if ids is not None:
        flt["_id"] = {"$in": list(ids)}
    return [x async for x in db().reader_docs.find(flt).sort("at", -1)]


@router.get("/list")
@router.get("")            # GET /api/docs is shadowed by the API's Swagger page (server.py docs_url); screens use /docs/list
async def listing(user: dict = Depends(user_dep())):
    plan = await plans.require(db(), user, "doc_reader")
    items = [_public(x) for x in await user_docs(user)]
    qs = [_question_public(q) async for q in db().reader_questions.find({"user_id": str(user["_id"])}).sort("at", -1).limit(10)]
    return {"items": items, "count": len(items), "cap": plans.cap("docs", plan), "max_mb": MAX_BYTES // (1024 * 1024),
            "types": sorted(set(TYPES)), "questions": qs}


async def claim_slot(coll, doc: dict, flt: dict, cap: int) -> bool:
    """Insert `doc`, then recount everything matching `flt`. Over `cap` → take ours out again and return False.
    Uploads that run at the same time can therefore never end above the cap (in a true tie both may be refused,
    and the member simply tries again). Counting first and inserting later let parallel uploads all pass."""
    await coll.insert_one(doc)
    if await coll.count_documents(flt) > cap:
        await coll.delete_one({"_id": doc["_id"]})
        return False
    return True


@router.post("")
async def upload(file: UploadFile = File(...), title: Optional[str] = Form(None), user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    plan = await plans.require(d, user, "doc_reader")
    cap = plans.cap("docs", plan)
    full = bad("cap", f"You can keep {cap} documents at a time. Delete one to add another.", 409)
    if await d.reader_docs.count_documents({"user_id": uid}) >= cap:
        raise full
    got = await read_upload(file)
    doc_id = uuid.uuid4().hex
    name = text(title, 120) or got["title"]
    parts = make_chunks(got["text"], got["page_starts"])
    rows = [{"_id": f"{doc_id}:{c['i']}", "doc_id": doc_id, "user_id": uid, "title": name, **c} for c in parts]
    doc = {"_id": doc_id, "user_id": uid, "title": name, "kind": got["kind"], "size": got["size"], "pages": got["pages"],
           "pages_estimated": got["pages_estimated"], "words": got["words"], "chunks": len(rows),
           "ntok": sum(c["n"] for c in parts), "truncated": got["truncated"], "at": utcnow()}
    if not await claim_slot(d.reader_docs, doc, {"user_id": uid}, cap):
        raise full
    try:
        if rows:
            await d.reader_chunks.insert_many(rows)
    except BaseException:
        await d.reader_chunks.delete_many({"doc_id": doc_id})
        await d.reader_docs.delete_one({"_id": doc_id})
        raise
    await events.track(d, "doc_uploaded", user_id=uid, props={"kind": got["kind"], "pages": got["pages"], "words": got["words"]})
    return _public(doc)


class AskIn(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    doc_ids: Optional[list[str]] = Field(None, max_length=50)


@router.post("/ask")
async def ask(body: AskIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    await plans.require(d, user, "doc_reader")
    docs = await user_docs(user, body.doc_ids)
    if not docs:
        raise bad("no_docs", "Pick at least one of your documents." if body.doc_ids else "Upload a document first.")
    ids = [x["_id"] for x in docs]
    n = sum(x.get("chunks", 0) for x in docs)
    avg = sum(x.get("ntok", 0) for x in docs) / n if n else 1.0
    hits = await retrieve(d.reader_chunks, {"user_id": uid, "doc_id": {"$in": ids}}, body.question, n_chunks=n, avg_len=avg)

    async def save(out: dict) -> dict:
        q = {"_id": uuid.uuid4().hex, "user_id": uid, "question": text(body.question, 1000), "answer": out["answer"],
             "covered": out["covered"], "citations": out["citations"], "doc_ids": ids, "at": utcnow()}
        await d.reader_questions.insert_one(q)
        await events.track(d, "doc_asked", user_id=uid, props={"covered": out["covered"], "cited": len(out["citations"]),
                                                               "docs": len(ids)})
        return _question_public(q)

    if not hits:                                   # nothing matched: say so, and don't count a question
        return await save({"answer": NOT_COVERED, "covered": False, "citations": []})

    async def work(plan: str):
        out = await cited_answer(body.question, hits, task="doc_reader_ask", ref_key="doc_id")
        return await save(out)
    return await run_metered(d, user, "doc_q", work, access="doc_reader")


class SummaryIn(BaseModel):
    refresh: bool = False


async def _own(doc_id: str, user: dict, projection: Optional[dict] = None) -> dict:
    doc = await db().reader_docs.find_one({"_id": doc_id, "user_id": str(user["_id"])}, projection)
    if not doc:
        raise not_found()
    return doc


@router.post("/{doc_id}/summary")
async def summary(doc_id: str, body: Optional[SummaryIn] = None, user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, "doc_reader")
    doc = await _own(doc_id, user)
    if doc.get("summary") and not (body and body.refresh):
        return {"id": doc_id, "title": doc["title"], "summary": _summary_public(doc["summary"]), "cached": True}
    chunks = [c async for c in d.reader_chunks.find({"doc_id": doc_id}, {"text": 1, "i": 1, "page": 1}).sort("i", 1)]
    picked = spread(chunks, 6000)
    source = "\n\n".join(c["text"] for c in picked)

    async def work(plan: str):
        prompt = (f"DOCUMENT: {doc['title']} ({doc.get('pages')} pages, {doc.get('words')} words"
                  f"{'; these are evenly spaced parts of it' if len(picked) < len(chunks) else ''})\n\nTEXT:\n{source}\n\n"
                  "Write: overview (2-3 sentences: what this document is and its main message), key_points (4-8), "
                  "numbers (up to 8 important figures exactly as written, each with what it means), decisions (what "
                  "was decided or agreed, if any), risks (risks, concerns or open issues, if any).\n"
                  'JSON: {"overview": "", "key_points": [""], "numbers": [{"figure": "", "meaning": ""}], '
                  '"decisions": [""], "risks": [""]}')
        raw = await llm.complete_json(task="doc_reader_summary", system=SUM_SYSTEM, prompt=prompt,
                                      fake=lambda: fake_summary(doc["title"], source), model="strong", max_tokens=1600)
        out = check_summary(raw, source) | {"at": utcnow()}
        await d.reader_docs.update_one({"_id": doc_id}, {"$set": {"summary": out}})
        await events.track(d, "doc_summary", user_id=str(user["_id"]), props={"words": doc.get("words", 0)})
        return {"id": doc_id, "title": doc["title"], "summary": _summary_public(out), "cached": False}
    return await run_metered(d, user, "doc_q", work, access="doc_reader")


@router.get("/{doc_id}")
async def one(doc_id: str, user: dict = Depends(user_dep())):
    await plans.require(db(), user, "doc_reader")
    doc = await _own(doc_id, user)
    first = await db().reader_chunks.find_one({"doc_id": doc_id, "i": 0}, {"text": 1})
    return _public(doc) | {"summary": _summary_public(doc.get("summary")),
                           "preview": " ".join(((first or {}).get("text") or "").split()[:120])}


@router.delete("/{doc_id}")
async def remove(doc_id: str, user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, "doc_reader")
    await _own(doc_id, user, {"_id": 1})
    await d.reader_chunks.delete_many({"doc_id": doc_id, "user_id": str(user["_id"])})
    await d.reader_docs.delete_one({"_id": doc_id})
    await events.track(d, "doc_deleted", user_id=str(user["_id"]))
    return {"ok": True}
