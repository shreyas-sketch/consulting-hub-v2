"""Industry Insight Pack: what is moving in the member's industry this month, and what to say about it.

The industry is the one from their Niche Snapshot (knowledge.target_industry) unless they type another. We run 2-3 news
searches; the AI writes a headline, 3 trends (with why each matters), 3 opportunities for a consultant in their niche,
5 talking points, 3 questions to ask clients, and picks up to 6 news items BY NUMBER from the search results, so a pack
can never show a link that wasn't really found (same rule as features/brief.py).

"Listen" turns a spoken version of the pack into audio (audio.tts), saved once per pack (media blob, private) and metered
on the shared `audio` meter; pressing Listen again plays the saved file.

insight_packs {_id, user_id, industry, niche, headline, trends: [{trend, why_it_matters}], opportunities: [str],
               talking_points: [str], questions_to_ask_clients: [str], news: [{title, url, source, published, why}],
               live_news: bool, test: bool, audio_blob_id?, at}
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
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

from .common import run_metered, text, text_list
from .knowledge import knowledge, system_block

router = APIRouter(prefix="/insights", tags=["insight-pack"])

events.register("insight_pack_made", "Industry Insight Pack made (props.industry, sources)")
events.register("insight_audio_made", "Insight Pack audio version made")
indexes.register("insight_packs", [("user_id", 1), ("at", -1)])

MAX_RESULTS = 12

SYSTEM = (
    "You write a short monthly industry briefing for a member of Akshat Dani's consulting program: an experienced "
    "Indian professional becoming a consultant, who wants to sound current in client conversations. Use the numbered "
    "news items provided and what is generally known about this industry in India. If you are not sure about a fact, "
    "don't state it. Never invent statistics, company names or events; present general patterns as patterns "
    "('many mid-size firms are...'), not as cited figures. Opportunities must suit a consultant in the member's niche: "
    "a problem a business owner would pay to have solved. Plain, short, spoken English. Indian context (₹, lakh, crore). "
    "No buzzwords, no hype, no emojis. Never promise income. Never mention or describe the AI or who makes it."
)


class PackIn(BaseModel):
    industry: str = Field("", max_length=80)


def _queries(industry: str, niche: str) -> list[str]:
    qs = [f"{industry} industry India trends", f"{industry} India companies latest news"]
    if niche:
        qs.append(f"{niche} {industry} India")
    return qs


async def _search(industry: str, niche: str) -> list[dict]:
    batches = await asyncio.gather(*(search.news(q, max_results=5) for q in _queries(industry, niche)),
                                   return_exceptions=True)
    out, seen = [], set()
    for b in batches:
        if isinstance(b, Exception):
            continue
        for r in b:
            if r.get("url") and r["url"] not in seen:
                seen.add(r["url"])
                out.append(r)
    return out[:MAX_RESULTS]


def _fake(industry: str, niche: str, results: list[dict]) -> dict:
    n = niche or "your niche"
    return {"headline": f"{industry}: costs are up, and owners want tighter control",
            "trends": [{"trend": "Costs rising faster than prices", "why_it_matters": "Margins are thin, so owners look for leaks."},
                       {"trend": "More buying moves online", "why_it_matters": "Sales teams need new habits and new numbers."},
                       {"trend": "Second-generation owners taking charge", "why_it_matters": "They want systems, not gut feel."}],
            "opportunities": [f"A 2-week margin check, sold as the entry to {n}", "Setting up a weekly numbers review for owners",
                              "Helping a new manager team run without the founder"],
            "talking_points": ["Most owners know their sales number, few know their profit by product.",
                               "Rising costs hurt the firms that never tracked them weekly.",
                               "Online buyers compare more, so service speed matters more.",
                               "The next generation wants dashboards, not diaries.",
                               "Small fixes in pricing often beat big new projects."],
            "questions_to_ask_clients": ["Which of your products makes the most profit, not the most sales?",
                                         "What number do you look at every Monday?",
                                         "What would you fix first if you had one extra manager?"],
            "news": [{"i": i + 1, "why": "Shows where the industry is heading this month."} for i in range(min(4, len(results)))],
            "note": "Test mode pack. Live mode writes it from this month's news."}


def _prompt(industry: str, k: dict, results: list[dict]) -> str:
    news = "\n".join(f"[{i + 1}] {r['title']} ({r['source']}, {r.get('published') or 'date unknown'}): {r.get('snippet', '')[:400]}"
                     for i, r in enumerate(results)) or "No news found. Write from what is generally known; don't refer to specific recent events."
    kb = system_block(k)
    return (f"INDUSTRY: {industry}\n{kb}\n\nNEWS ITEMS:\n{news}\n\n"
            "Write: headline (one line, the big picture this month), trends (exactly 3, each {trend, why_it_matters} in "
            "one sentence), opportunities (exactly 3 for a consultant in this member's niche, one sentence each), "
            "talking_points (exactly 5 short things to say in a client conversation), questions_to_ask_clients (exactly "
            "3), news (up to 6 of the numbered items that matter most, by number, each with why it matters; [] if none).\n"
            'JSON: {"headline": "", "trends": [{"trend": "", "why_it_matters": ""}], "opportunities": [""], '
            '"talking_points": [""], "questions_to_ask_clients": [""], "news": [{"i": 1, "why": ""}]}')


def _clean(raw: dict, results: list[dict]) -> dict:
    trends = [{"trend": text(t.get("trend"), 160), "why_it_matters": text(t.get("why_it_matters"), 300)}
              for t in (raw.get("trends") or [])[:3] if isinstance(t, dict) and text(t.get("trend"), 160)]
    out = {"headline": text(raw.get("headline"), 200), "trends": trends,
           "opportunities": text_list(raw.get("opportunities"), 3, 300),
           "talking_points": text_list(raw.get("talking_points"), 5, 240),
           "questions_to_ask_clients": text_list(raw.get("questions_to_ask_clients"), 3, 240)}
    if (not out["headline"] or len(trends) < 3 or len(out["opportunities"]) < 3 or len(out["talking_points"]) < 5
            or len(out["questions_to_ask_clients"]) < 3):
        raise llm.LLMError("insight_pack: incomplete")
    news = []
    for n in (raw.get("news") or [])[:6]:
        try:
            idx = int(n.get("i"))
            if idx < 1:
                continue
            r = results[idx - 1]
        except (TypeError, ValueError, IndexError, AttributeError):
            continue
        if any(x["url"] == r["url"] for x in news):
            continue
        news.append({"title": r["title"], "url": r["url"], "source": r["source"], "published": r.get("published") or "",
                     "why": text(n.get("why"), 240)})
    out["news"] = news
    return out


def spoken(p: dict) -> str:
    """The pack as a short spoken briefing (what the Listen button plays)."""
    parts = [f"Your industry insight pack for {p['industry']}.", p["headline"].rstrip(".") + ".", "Three trends."]
    for i, t in enumerate(p["trends"]):
        parts.append(f"{['First', 'Second', 'Third'][i] if i < 3 else 'Next'}: {t['trend'].rstrip('.')}. {t['why_it_matters']}")
    parts.append("Three opportunities for you.")
    parts += [o for o in p["opportunities"]]
    parts.append("Five things you can say in your next client conversation.")
    parts += [t for t in p["talking_points"]]
    parts.append("And three questions to ask your clients.")
    parts += [q for q in p["questions_to_ask_clients"]]
    if p.get("news"):
        parts.append("In the news this month.")
        parts += [f"{n['title']}." + (f" {n['why']}" if n.get("why") else "") for n in p["news"][:3]]
    return " ".join(" ".join(parts).split())


def _public(d: dict) -> dict:
    return {"id": d["_id"], **{k: d.get(k) for k in ("industry", "niche", "headline", "trends", "opportunities",
                                                      "talking_points", "questions_to_ask_clients", "news")},
            "live_news": bool(d.get("live_news")), "test": bool(d.get("test")),
            "audio_url": media.blob_url(d.get("audio_blob_id")), "at": iso(d["at"])}


async def _own(pack_id: str, uid: str) -> dict:
    d = await db().insight_packs.find_one({"_id": pack_id, "user_id": uid})
    if not d:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Insight Pack not found."})
    return d


@router.post("")
async def make(body: PackIn, user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    await plans.require(db(), user, "insight_pack")
    k = await knowledge(db(), user)
    industry = text(body.industry, 80) or text(k.get("target_industry"), 80)
    if not industry:
        raise HTTPException(status_code=422, detail={"code": "no_industry", "msg": "Type the industry you work in."})
    niche = text(k.get("niche"), 120)

    async def work(plan: str):
        results = await _search(industry, niche)
        raw = await llm.complete_json(task="insight_pack", system=SYSTEM, prompt=_prompt(industry, k, results),
                                      fake=lambda: _fake(industry, niche, results), model="strong", max_tokens=1800)
        pack = _clean(raw, results)
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "industry": industry, "niche": niche, **pack,
               "live_news": bool(results), "test": any(r.get("test") for r in results), "audio_blob_id": None,
               "at": utcnow()}
        await db().insight_packs.insert_one(doc)
        await events.track(db(), "insight_pack_made", user_id=uid, props={"industry": industry[:60], "sources": len(pack["news"])})
        return _public(doc)
    return await run_metered(db(), user, "insight", work, access="insight_pack")


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    k = await knowledge(db(), user)
    rows = [{"id": d["_id"], "industry": d["industry"], "headline": d["headline"], "has_audio": bool(d.get("audio_blob_id")),
             "at": iso(d["at"])}
            async for d in db().insight_packs.find({"user_id": uid}, {"industry": 1, "headline": 1, "audio_blob_id": 1, "at": 1})
            .sort("at", -1).limit(36)]
    return {"industry": k.get("target_industry") or "", "items": rows}


@router.get("/{pack_id}")
async def one(pack_id: str, user: dict = Depends(user_dep())):
    return _public(await _own(pack_id, str(user["_id"])))


@router.post("/{pack_id}/audio")
async def listen(pack_id: str, user: dict = Depends(user_dep())):
    """Audio version of the pack: made once (metered on `audio`), then served from the saved file."""
    uid = str(user["_id"])
    p = await _own(pack_id, uid)
    if p.get("audio_blob_id") and await media.get_blob(db(), p["audio_blob_id"]):
        return {"audio_url": media.blob_url(p["audio_blob_id"]), "cached": True}

    async def work(plan: str):
        try:
            data, ctype = await tts.speak(spoken(p))
            blob_id = await media.save_blob(db(), user_id=uid, kind="insight_audio", content_type=ctype, data=data,
                                            name=f"insight-pack-{pack_id[:8]}")
        except (tts.TTSError, media.TooLarge):
            raise HTTPException(status_code=503, detail={
                "code": "audio_failed", "msg": "We couldn't make the audio just now. Try again in a minute. "
                                               "This didn't use up your go."})
        await db().insight_packs.update_one({"_id": pack_id, "user_id": uid}, {"$set": {"audio_blob_id": blob_id}})
        await events.track(db(), "insight_audio_made", user_id=uid)
        return {"audio_url": media.blob_url(blob_id), "cached": False}
    return await run_metered(db(), user, "audio", work, access="insight_pack")
