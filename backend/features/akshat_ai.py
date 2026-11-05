"""Akshat AI (L1): ask a question, get an answer written only from Akshat's own sessions (the knowledge base).

akshat_threads   {_id, user_id, title, messages: [{role: user|assistant, text, at, status?, sources?, question_id?,
                  from_call?}], updated_at, created_at}
akshat_questions {_id, user_id, thread_id, question, status: queued|answered, answer?, answered_at?, answered_by?, at}

Retrieval: features.kb.search (BM25 over transcript chunks), k=6. The AI answers in Akshat's plain mentor voice and
only from those chunks; sources are picked by number, so a title is always a real knowledge-base document. When the
chunks don't cover the question it is saved for the next group call; the team answers it in Admin and the member gets
an inbox alert. Personal financial, tax, investment and legal advice is declined politely.

Metering (`akshat_ai`): the knowledge base is searched first. Only a real answer counts as a question: nothing found
(no AI call), "not covered" and "decline" give the use back. Wrong-shaped AI output → llm.LLMError (refund + busy).
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

import indexes
import llm
import plans
from core.deps import admin_dep, user_dep
from core.errors import NotFound
from growth import events
from growth.clock import utcnow
from notify import service as notify
from state import db
from util import iso

from . import kb
from .common import NO_VENDOR, as_dict, as_list, run_metered, strip_providers, text

router = APIRouter(tags=["akshat-ai"])

K = 6
QUEUED_TEXT = ("I couldn't find this in Akshat's sessions yet, so I won't guess. I've sent your question to the next "
               "group call, so Akshat can answer it there. You'll get a message in your inbox when the answer is ready. "
               "This didn't use up a question.")
DECLINE_TEXT = ("I can't give personal financial, tax, investment or legal advice. For that, please speak to a "
                "qualified professional who can look at your situation. Ask me anything about building your "
                "consulting practice and I'll answer from Akshat's sessions. This didn't use up a question.")
PERSONAL_ADVICE = re.compile(r"\b(should i (invest|buy|sell)|which (stock|share|mutual fund|fund)|mutual funds?|"
                             r"stock market|crypto\w*|my (taxes|tax return|itr|loan|emi)|file my (itr|gst)|"
                             r"legal advice|sue|lawsuit|my lawyer|divorce|court case)\b", re.I)

SYSTEM = (
    "You are Akshat AI inside the Consultation Hub. You answer members' questions the way Akshat Dani does in his "
    "sessions: plain, warm, direct, like a mentor talking to an experienced Indian professional who is becoming a "
    "consultant. Short sentences. Practical steps. No hype, no buzzwords, no emojis, never promise income.\n"
    "RULES\n"
    "- Answer ONLY from the numbered session excerpts you are given. Do not add facts, numbers, stories or advice that "
    "are not in them. If the excerpts do not really answer the question, set kind to \"not_covered\"; never guess.\n"
    "- Personal financial, tax, investment or legal advice for the member's own situation: set kind to \"decline\".\n"
    "- Speak as Akshat's teaching (\"In the sessions, Akshat says…\" or in his voice: \"Here's how I'd do it…\"). "
    "Write the answer in Markdown: a short paragraph, then a few bullets or numbered steps if it helps. 80-250 words.\n"
    "- Money in rupees (₹) with Indian grouping.\n"
    "- Never name or hint at the AI company or model behind you. You are the hub's Akshat AI.\n"
    "- \"sources\" are the numbers of the excerpts you actually used.\n" + NO_VENDOR
)

indexes.register("akshat_threads", [("user_id", 1), ("updated_at", -1)])
indexes.register("akshat_questions", [("status", 1), ("at", 1)])
indexes.register("akshat_questions", [("user_id", 1), ("at", -1)])
events.register("akshat_ai_asked", "Question to Akshat AI (props.status: answered|queued|declined, sources)")
events.register("akshat_ai_answered", "Team answered a queued Akshat AI question (props.question_id)")
notify.register_kind("akshat_ai")


class AskIn(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    thread_id: Optional[str] = Field(None, max_length=64)


def _fake(question: str, chunks: list[dict]) -> dict:
    if PERSONAL_ADVICE.search(question):
        return {"kind": "decline", "answer": "", "sources": []}
    if not chunks:
        return {"kind": "not_covered", "answer": "", "sources": []}
    return {"kind": "answer", "sources": [1],
            "answer": ("Test-mode answer. In live mode Akshat AI answers from the session excerpts it found.\n\n"
                       f"Your question was: \"{text(question, 160)}\"\n\n"
                       "- Start with the one problem your client feels most.\n- Say it back to them in their words.\n"
                       "- Agree one number to move in 90 days.")}


def _prompt(question: str, chunks: list[dict], earlier: list[dict]) -> str:
    ex = "\n\n".join(f"[{i + 1}] From \"{c.get('title') or 'Session'}\":\n{text(c.get('text'), 2400)}"
                     for i, c in enumerate(chunks))
    ctx = ""
    if earlier:
        ctx = "EARLIER IN THIS CHAT (context only, not a source):\n" + "\n".join(
            f"{'Member' if m['role'] == 'user' else 'Akshat AI'}: {text(m['text'], 400)}" for m in earlier) + "\n\n"
    return (f"{ctx}SESSION EXCERPTS:\n{ex}\n\nMEMBER'S QUESTION:\n{question}\n\n"
            'JSON: {"kind": "answer" | "not_covered" | "decline", "answer": "markdown, empty unless kind is answer", '
            '"sources": [1]}')


def _public_msg(m: dict, q: Optional[dict] = None) -> dict:
    out = {"role": m["role"], "text": m["text"], "at": iso(m.get("at")), "status": m.get("status"),
           "sources": m.get("sources") or [], "question_id": m.get("question_id"), "from_call": bool(m.get("from_call"))}
    if q is not None:
        out["question_status"] = q.get("status")
    return out


async def _thread(thread_id: str, uid: str) -> dict:
    t = await db().akshat_threads.find_one({"_id": thread_id, "user_id": uid})
    if not t:
        raise NotFound("Chat not found.")
    return t


def _q_public(q: dict) -> dict:
    return {"id": q["_id"], "question": q["question"], "status": q["status"], "answer": q.get("answer"),
            "thread_id": q.get("thread_id"), "at": iso(q.get("at")), "answered_at": iso(q.get("answered_at"))}


# ------------------------------------------------------------------ member ----
@router.post("/akshat-ai/ask")
async def ask(body: AskIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    question = " ".join(body.question.split())
    thread = await _thread(body.thread_id, uid) if body.thread_id else None
    earlier = [m for m in (thread or {}).get("messages", []) if m.get("text")][-6:]

    await plans.require(d, user, "akshat_ai")
    query = question
    prev_q = next((m["text"] for m in reversed(earlier) if m["role"] == "user"), "")
    if prev_q and len(kb.tokens(question)) < 6:
        query = f"{prev_q} {question}"               # short follow-ups ("and for MSMEs?") search with the last question
    chunks = await kb.search(d, query, k=K)          # search first: nothing found → no AI call, nothing counted
    if not chunks:
        return await _save(d, uid, thread, question, "decline" if PERSONAL_ADVICE.search(question) else "not_covered")

    async def work(plan: str):
        raw = await llm.complete_json(task="akshat_ai", system=SYSTEM, prompt=_prompt(question, chunks, earlier),
                                      fake=lambda: _fake(question, chunks), model="strong", max_tokens=900)
        if not isinstance(raw, dict):
            raise llm.LLMError("akshat_ai: not an object")
        raw = as_dict(raw)
        kind = raw.get("kind") if raw.get("kind") in ("answer", "not_covered", "decline") else None
        if kind is None:
            raise llm.LLMError("akshat_ai: bad kind")
        if kind != "answer":
            return plan, await _save(d, uid, thread, question, kind)
        answer = strip_providers(str(raw.get("answer") or "").strip()[:4000])
        if len(answer) < 20:
            raise llm.LLMError("akshat_ai: empty answer")
        titles: list[str] = []
        for n in as_list(raw.get("sources")):
            try:
                i = int(n)
                c = chunks[i - 1]
            except (TypeError, ValueError, IndexError):
                continue
            if i >= 1 and c.get("title") and c["title"] not in titles:
                titles.append(c["title"])
        if not titles:
            titles = list(dict.fromkeys(c["title"] for c in chunks[:2] if c.get("title")))
        return plan, await _save(d, uid, thread, question, "answer", answer=answer, titles=titles)

    plan, out = await run_metered(d, user, "akshat_ai", work, access="akshat_ai")
    if out["status"] != "answered":                  # "not covered" / decline: give the question back
        await plans.refund(d, user, "akshat_ai", plan)
        out["counted"] = False
    return out


async def _save(d, uid: str, thread: Optional[dict], question: str, kind: str, *, answer: str = "",
                titles: Optional[list[str]] = None) -> dict:
    """Store the member's question and the reply (answer, decline, or queued for the next group call)."""
    dup = None
    now = utcnow()
    um = {"role": "user", "text": question, "at": now}
    qid = None
    if kind == "answer":
        am = {"role": "assistant", "text": answer, "at": now, "status": "answered",
              "sources": [{"title": t} for t in (titles or [])[:4]]}
    elif kind == "decline":
        am = {"role": "assistant", "text": DECLINE_TEXT, "at": now, "status": "declined", "sources": []}
    else:
        dup = await d.akshat_questions.find_one({"user_id": uid, "status": "queued",
                                                 "question": {"$regex": f"^{re.escape(question)}$", "$options": "i"}})
        qid = dup["_id"] if dup else uuid.uuid4().hex
        am = {"role": "assistant", "text": QUEUED_TEXT, "at": now, "status": "queued", "sources": [], "question_id": qid}
    if thread:
        tid = thread["_id"]
        await d.akshat_threads.update_one({"_id": tid}, {"$push": {"messages": {"$each": [um, am]}},
                                                          "$set": {"updated_at": now}})
    else:
        tid = uuid.uuid4().hex
        await d.akshat_threads.insert_one({"_id": tid, "user_id": uid, "title": text(question, 80),
                                           "messages": [um, am], "created_at": now, "updated_at": now})
    if am["status"] == "queued" and not dup:
        await d.akshat_questions.insert_one({"_id": qid, "user_id": uid, "thread_id": tid, "question": question,
                                             "status": "queued", "answer": None, "at": now})
    await events.track(d, "akshat_ai_asked", user_id=uid,
                       props={"status": am["status"], "sources": len(am["sources"])})
    return {"thread_id": tid, "status": am["status"], "question_id": qid, "counted": am["status"] == "answered",
            "user_message": _public_msg(um), "message": _public_msg(am)}


@router.get("/akshat-ai/threads")
async def threads(user: dict = Depends(user_dep())):
    cur = db().akshat_threads.find({"user_id": str(user["_id"])}, {"title": 1, "updated_at": 1, "messages.status": 1}
                                   ).sort("updated_at", -1).limit(60)
    rows = []
    async for t in cur:
        st = [m.get("status") for m in t.get("messages") or []]
        rows.append({"id": t["_id"], "title": t.get("title") or "", "updated_at": iso(t.get("updated_at")),
                     "count": len(st), "queued": st.count("queued")})
    return {"items": rows}


@router.get("/akshat-ai/threads/{thread_id}")
async def thread(thread_id: str, user: dict = Depends(user_dep())):
    t = await _thread(thread_id, str(user["_id"]))
    ids = [m["question_id"] for m in t.get("messages") or [] if m.get("question_id")]
    qs = {q["_id"]: q async for q in db().akshat_questions.find({"_id": {"$in": ids}})} if ids else {}
    return {"id": t["_id"], "title": t.get("title") or "", "updated_at": iso(t.get("updated_at")),
            "messages": [_public_msg(m, qs.get(m.get("question_id")) if m.get("status") == "queued" else None)
                         for m in t.get("messages") or []]}


@router.get("/akshat-ai/questions")
async def my_questions(user: dict = Depends(user_dep())):
    cur = db().akshat_questions.find({"user_id": str(user["_id"])}).sort("at", -1).limit(100)
    return {"items": [_q_public(q) async for q in cur]}


# ------------------------------------------------------------------ admin ----
class AnswerIn(BaseModel):
    answer: str = Field(..., min_length=5, max_length=6000)


@router.get("/admin/akshat-questions")
async def admin_questions(status: Optional[str] = Query(None, pattern="^(queued|answered)$"),
                          _: dict = Depends(admin_dep())):
    d = db()
    flt = {"status": status} if status else {}
    rows = [q async for q in d.akshat_questions.find(flt).sort("at", 1 if status == "queued" else -1).limit(500)]
    oids = [ObjectId(q["user_id"]) for q in rows if ObjectId.is_valid(q["user_id"])]
    people = {str(u["_id"]): u async for u in d.users.find({"_id": {"$in": oids}}, {"name": 1, "phone": 1})} if oids else {}
    items = [_q_public(q) | {"user_id": q["user_id"], "name": (people.get(q["user_id"]) or {}).get("name"),
                             "phone": (people.get(q["user_id"]) or {}).get("phone")} for q in rows]
    counts = {s: await d.akshat_questions.count_documents({"status": s}) for s in ("queued", "answered")}
    return {"items": items, "counts": counts}


@router.post("/admin/akshat-questions/{qid}/answer")
async def admin_answer(qid: str, body: AnswerIn, admin: dict = Depends(admin_dep())):
    d = db()
    q = await d.akshat_questions.find_one({"_id": qid})
    if not q:
        raise NotFound("Question not found.")
    answer = body.answer.strip()
    now = utcnow()
    first = q.get("status") != "answered"
    await d.akshat_questions.update_one({"_id": qid}, {"$set": {"status": "answered", "answer": answer,
                                                                "answered_at": now, "answered_by": str(admin["_id"])}})
    if q.get("thread_id"):
        if first:
            await d.akshat_threads.update_one({"_id": q["thread_id"]}, {
                "$push": {"messages": {"role": "assistant", "text": answer, "at": now, "status": "answered",
                                       "sources": [], "question_id": qid, "from_call": True}},
                "$set": {"updated_at": now}})
        else:                                           # an edit: replace the earlier answer in the chat
            t = await d.akshat_threads.find_one({"_id": q["thread_id"]}, {"messages": 1})
            if t:
                msgs = [m | {"text": answer} if m.get("question_id") == qid and m.get("from_call") else m
                        for m in t.get("messages") or []]
                await d.akshat_threads.update_one({"_id": t["_id"]}, {"$set": {"messages": msgs}})
    await notify.alert(d, q["user_id"], "akshat_ai", "Akshat answered your question",
                       f"\"{text(q['question'], 120)}\" — {text(answer, 300)}",
                       link=f"/app/akshat-ai/{q['thread_id']}" if q.get("thread_id") else "/app/akshat-ai",
                       dedupe=f"akq:{qid}")
    await events.track(d, "akshat_ai_answered", user_id=q["user_id"], props={"question_id": qid})
    return _q_public(await d.akshat_questions.find_one({"_id": qid}))
