"""Meeting Brief: before you meet a company, get a one-page brief in a minute.

briefs {_id, user_id, input: {company, website, meeting_with, purpose}, about, news: [{title, url, source, published}],
        problems: [{problem, why}], questions: [str], opening: str, live_news: bool, test: bool, at}

News links come only from the search results (the AI picks them by number), so a brief can never show a link
that wasn't really found. With search off, the brief says it was made without live news.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import llm
from core.deps import user_dep
from core.errors import NotFound, TooManyRequests
from growth import events
from growth.clock import utcnow
from research import search
from state import db
from util import iso

from .common import (
    NO_VENDOR,
    as_dict,
    as_list,
    run_metered,
    strip_providers,
    text,
    text_list,
)
from .knowledge import links_in, no_links

router = APIRouter(prefix="/briefs", tags=["meeting-brief"])
events.register("brief_news_retried", "Meeting Brief: looked for news again (props.found)")
WEBINAR_QUEUE_WAIT = 45          # seconds a brief may wait for an AI slot when the whole webinar makes one at once

SYSTEM = (
    "You prepare a consultant for a first meeting with an Indian company. Use only the news items provided and what "
    "is generally known about this kind of business; if you are not sure about a fact, don't state it. Plain English, "
    "short sentences. The consultant is experienced but new to consulting. Refer to news only by its number; never "
    "write a link. " + NO_VENDOR
)


class BriefIn(BaseModel):
    company: str = Field(..., min_length=2, max_length=120)
    website: str = Field("", max_length=200)
    meeting_with: str = Field("", max_length=120)          # e.g. "Founder", "Head of Operations"
    purpose: str = Field("", max_length=300)               # what the meeting is about


def _fake(body: BriefIn, results: list[dict]) -> dict:
    co = body.company.strip()
    return {"about": f"{co} is the company you're meeting. In live mode this paragraph is written from the news and "
                     "what is known about the business.",
            "news": [{"i": i + 1, "why": "Shows where the company is putting its money right now."}
                     for i in range(min(3, len(results)))],
            "problems": [{"problem": "Growing sales without losing margin", "why": "Common when a company expands fast."},
                         {"problem": "Keeping good people", "why": "Growth stretches managers."},
                         {"problem": "Too many decisions sit with the owner", "why": "Typical of owner-led firms."}],
            "questions": ["What does a great year look like for you?", "What's slowing that down today?",
                          "What have you already tried?", "Who else is involved in this decision?",
                          "If we fixed one thing in 90 days, what should it be?"],
            "opening": f"I've been reading about {co}'s recent moves, and I'd love to understand what you're focused on this year."}


def _prompt(body: BriefIn, results: list[dict]) -> str:
    news = "\n".join(f"[{i + 1}] {r['title']} ({r['source']}, {r['published'] or 'date unknown'}): {r['snippet'][:400]}"
                     for i, r in enumerate(results)) or "No news found."
    return (f"Company: {body.company}\nWebsite: {body.website or 'not given'}\nMeeting with: {body.meeting_with or 'not given'}\n"
            f"Meeting purpose: {body.purpose or 'first conversation'}\n\nNEWS ITEMS:\n{news}\n\n"
            "Write: about (2-3 sentences on what the company does and where it stands), news (up to 3 of the numbered "
            "items that matter most for this meeting, by number, each with why it matters), problems (3 likely business "
            "problems, each with why you think so), questions (5 questions to ask in the meeting), opening (one natural "
            "opening line).\n"
            'JSON: {"about": "", "news": [{"i": 1, "why": ""}], "problems": [{"problem": "", "why": ""}], '
            '"questions": [""], "opening": ""}')


def _public(b: dict) -> dict:
    return {k: b.get(k) for k in ("about", "news", "problems", "questions", "opening", "live_news", "test", "input")} | {
        "id": b["_id"], "at": iso(b["at"]), "news_tries_left": max(0, 3 - int(b.get("news_tries") or 0))}


@router.post("")
async def make(body: BriefIn, user: dict = Depends(user_dep())):
    uid = str(user["_id"])

    async def work(plan: str):
        results = []
        results = await search.news(_query(body.model_dump()), max_results=6, queue_wait=45)   # every brief searches
        raw = as_dict(await llm.complete_json(task="meeting_brief", system=SYSTEM, prompt=_prompt(body, results),
                                              fake=lambda: _fake(body, results), model="fast", max_tokens=1400,
                                              queue_wait=WEBINAR_QUEUE_WAIT))
        news = []
        for n in as_list(raw.get("news"))[:12]:
            if len(news) >= 3:
                break                        # three good picks; repeats and bad numbers no longer use up a slot
            try:
                i = int(n.get("i"))
                if i < 1:                    # 0 or negative would wrap to the end of the list: not a real pick
                    continue
                r = results[i - 1]
            except (TypeError, ValueError, IndexError, AttributeError):
                continue
            if any(x["url"] == r["url"] for x in news):
                continue
            news.append({"title": r["title"], "url": r["url"], "source": r["source"], "published": r["published"],
                         "why": strip_providers(text(n.get("why"), 240))})
        problems = strip_providers([{"problem": text(p.get("problem"), 160), "why": text(p.get("why"), 240)}
                                    for p in as_list(raw.get("problems"))[:3] if isinstance(p, dict) and p.get("problem")])
        questions = strip_providers(text_list(raw.get("questions"), 5, 200))
        if not text(raw.get("about"), 600) or len(questions) < 3:
            raise llm.LLMError("brief: incomplete")
        ok_links = links_in(body.website, *(r["url"] for r in results))      # links in the text: only real ones
        written = no_links({"about": strip_providers(text(raw.get("about"), 600)), "problems": problems,
                            "questions": questions, "opening": strip_providers(text(raw.get("opening"), 300))}, ok_links)
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "input": body.model_dump(), **written, "news": news,
               "live_news": bool(results), "test": any(r.get("test") for r in results), "at": utcnow()}
        await db().briefs.insert_one(doc)
        await events.track(db(), "brief_made", user_id=uid, props={"company": body.company[:60], "sources": len(news)})
        return _public(doc)
    return await run_metered(db(), user, "brief", work)


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    rows = [{"id": b["_id"], "company": b["input"]["company"], "at": iso(b["at"])}
            async for b in db().briefs.find({"user_id": str(user["_id"])}, {"input.company": 1, "at": 1}).sort("at", -1).limit(50)]
    return {"items": rows}


@router.get("/{brief_id}")
async def one(brief_id: str, user: dict = Depends(user_dep())):
    b = await db().briefs.find_one({"_id": brief_id, "user_id": str(user["_id"])})
    if not b:
        raise NotFound("Brief not found.")
    return _public(b)


NEWS_TRIES = 3          # "Look for news again" on one brief: free, at most this many times


def _query(inp: dict) -> str:
    """'<company> India news <Month YYYY>': asks for this month's stories. The company's web address is left out:
    it pulled in the company's own pages and news hubs instead of reports about it."""
    from growth.clock import IST
    month = utcnow().astimezone(IST).strftime("%B %Y")
    return f"{inp['company']} India news {month}"


@router.post("/{brief_id}/news")
async def news_again(brief_id: str, user: dict = Depends(user_dep())):
    """A brief made without news (the search failed or found nothing) can look again, free, up to NEWS_TRIES times.
    A free account has one brief for life, so without this a failed search would stay in their brief for good."""
    uid = str(user["_id"])
    b = await db().briefs.find_one({"_id": brief_id, "user_id": uid})
    if not b:
        raise NotFound("Brief not found.")
    if b.get("news"):
        return _public(b)
    tries = int(b.get("news_tries") or 0)
    if tries >= NEWS_TRIES:
        raise TooManyRequests("We've looked for news on this company three times. Search the company yourself "
                              "before the meeting.", code="news_tries")
    inp = b["input"]
    results = await search.news(_query(inp), max_results=6, queue_wait=45)
    news = []
    if results:
        listing = "\n".join(f"[{i + 1}] {r['title']} ({r['source']}, {r['published'] or 'date unknown'}): "
                            f"{r['snippet'][:400]}" for i, r in enumerate(results))
        raw = as_dict(await llm.complete_json(
            task="meeting_brief_news", system=SYSTEM,
            prompt=(f"Company: {inp['company']}\nMeeting purpose: {inp.get('purpose') or 'first conversation'}\n\n"
                    f"NEWS ITEMS:\n{listing}\n\nPick up to 3 of the numbered items that matter most for this meeting, "
                    'each with why it matters.\nJSON: {"news": [{"i": 1, "why": ""}]}'),
            fake=lambda: {"news": [{"i": i + 1, "why": r.get("snippet", "")[:200]} for i, r in enumerate(results[:3])]},
            model="fast", max_tokens=600, fallback_on_error=True))
        for n in as_list(raw.get("news"))[:3]:
            try:
                i = int(n.get("i"))
                r = results[i - 1] if i >= 1 else None
            except (TypeError, ValueError, IndexError, AttributeError):
                r = None
            if r and not any(x["url"] == r["url"] for x in news):
                news.append({"title": r["title"], "url": r["url"], "source": r["source"], "published": r["published"],
                             "why": strip_providers(text(n.get("why"), 240))})
        if not news:                     # the AI picked nothing usable: the top results, links still only from search
            news = [{"title": r["title"], "url": r["url"], "source": r["source"], "published": r["published"],
                     "why": strip_providers(text(r.get("snippet"), 240))} for r in results[:3]]
    await db().briefs.update_one({"_id": brief_id}, {"$set": {
        "news": news, "live_news": bool(results), "test": any(r.get("test") for r in results),
        "news_tries": tries + 1, "news_at": utcnow()}})
    await events.track(db(), "brief_news_retried", user_id=uid, props={"found": len(news)})
    return _public(await db().briefs.find_one({"_id": brief_id})) | {"news_tries_left": NEWS_TRIES - tries - 1}
