"""Knowledge base: Akshat's own sessions (transcripts, workbooks) for Akshat AI and Session Recaps (L1, stage 3).

kb_docs   {_id, title, words, chunks, uploaded_at}
kb_chunks {_id, doc_id, title, i, text, tokens: [str]}

Retrieval is a plain BM25 over chunk tokens (no embeddings vendor). Answers are written only from the
retrieved chunks. Uploads go through Admin › Knowledge base.
"""
from __future__ import annotations

import math
import re
import uuid
from collections import Counter

from growth.clock import utcnow
from util import iso

STOP = set("""a an the and or but if then so to of in on at for from by with without is are was were be been being it its this
that these those i you he she we they me my your our their them his her what which who whom how when where why can could
should would will just do does did not no yes as about into than too very also there here have has had get got""".split())
TOKEN = re.compile(r"[a-z0-9]+")
VTT_TS = re.compile(r"^\[?\d{1,2}:\d{2}(:\d{2})?(\.\d+)?\]?\s*(-->.*)?$")
CHUNK_WORDS = 350


def tokens(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 1]


def clean_transcript(raw: str) -> str:
    """Strip WEBVTT headers, cue numbers and timecodes; keep the words."""
    out = []
    lines = raw.replace("\r", "").split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.upper().startswith("WEBVTT") or "-->" in s or VTT_TS.match(s):
            continue
        if s.isdigit() and i + 1 < len(lines) and "-->" in lines[i + 1]:
            continue
        s = re.sub(r"^\[\d{1,2}:\d{2}(:\d{2})?\]\s*", "", s)
        out.append(s)
    return " ".join(out)


def chunk(text: str, n: int = CHUNK_WORDS) -> list[str]:
    words = text.split()
    step = int(n * 0.85)
    return [" ".join(words[i:i + n]) for i in range(0, max(1, len(words)), step) if words[i:i + n]]


async def ingest(d, title: str, raw: str) -> dict:
    text = clean_transcript(raw)
    parts = chunk(text)
    doc_id = uuid.uuid4().hex[:12]
    now = utcnow()
    rows = [{"_id": f"{doc_id}:{i}", "doc_id": doc_id, "title": title, "i": i, "text": t, "tokens": tokens(t)}
            for i, t in enumerate(parts)]
    if rows:
        await d.kb_chunks.insert_many(rows)
    doc = {"_id": doc_id, "title": title, "words": len(text.split()), "chunks": len(rows), "uploaded_at": now}
    await d.kb_docs.insert_one(doc)
    reset_kb_cache()
    return {"id": doc_id, "title": title, "chunks": len(rows), "words": doc["words"], "uploaded_at": iso(now)}


async def remove(d, doc_id: str) -> None:
    """Take one document (and its chunks) out of the knowledge base."""
    if not doc_id:
        return
    await d.kb_chunks.delete_many({"doc_id": doc_id})
    await d.kb_docs.delete_one({"_id": doc_id})
    reset_kb_cache()


_KB: dict = {"sig": None, "checked": 0.0, "rows": [], "tf": [], "lens": [], "avg": 1.0, "post": {}}


async def _kb_index(d) -> dict:
    """In-memory BM25 index of the knowledge base, one per worker. Rebuilt only when the KB changes
    (checked at most every 30 s). With ~1,800 transcript chunks the old
    per-question scan read up to 3–4 MB from Mongo and scored every chunk in Python (~120 ms of CPU per
    question); this answers from memory in a few ms."""
    import time
    now = time.time()
    if _KB["sig"] is not None and now - _KB["checked"] < 30:
        return _KB
    last = await d.kb_docs.find_one({}, sort=[("uploaded_at", -1)], projection={"uploaded_at": 1})
    sig = (await d.kb_docs.count_documents({}), await d.kb_chunks.count_documents({}),
           str((last or {}).get("uploaded_at")))
    _KB["checked"] = now
    if sig == _KB["sig"]:
        return _KB
    rows, tfs, lens, post = [], [], [], {}
    async for r in d.kb_chunks.find({}, {"tokens": 1, "text": 1, "title": 1}):
        i = len(rows)
        tf = Counter(r.get("tokens") or [])
        rows.append({"_id": r["_id"], "title": r.get("title"), "text": r.get("text", "")})
        tfs.append(tf)
        lens.append(sum(tf.values()))
        for t in tf:
            post.setdefault(t, []).append(i)
    _KB.update(sig=sig, rows=rows, tf=tfs, lens=lens, post=post, avg=(sum(lens) / len(lens)) if lens else 1.0)
    return _KB


async def search(d, query: str, k: int = 5) -> list[dict]:
    q = tokens(query)
    if not q:
        return []
    kb = await _kb_index(d)
    n = len(kb["rows"]) or 1
    scores: dict[int, float] = {}
    for t in set(q):
        docs = kb["post"].get(t)
        if not docs:
            continue
        idf = math.log(1 + (n - len(docs) + 0.5) / (len(docs) + 0.5))
        for i in docs:
            f = kb["tf"][i][t]
            scores[i] = scores.get(i, 0.0) + idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * kb["lens"][i] / kb["avg"]))
    best = sorted(scores.items(), key=lambda x: -x[1])[:k]
    return [kb["rows"][i] for i, sc in best if sc > 0]


def reset_kb_cache() -> None:
    _KB.update(sig=None, checked=0.0)

