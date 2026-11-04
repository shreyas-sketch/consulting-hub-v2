"""Opportunity Radar: companies in the member's niche showing a sign they may need help right now.

radar_runs      {_id, user_id, input: {niche, industry, city}, queries: [str], results_n, found_n, test, at}
radar_companies {_id, user_id, run_id, company, key, signal, summary, why, angle,
                 news: {title, url, source, published}, test, status new|saved|dismissed, at}

Each run searches recent news for signals (expansion, a new plant, funding, a leadership change, losses, layoffs,
new rules) and the AI picks up to 5 companies BY RESULT NUMBER, so every link shown came from the search. A company
the member already has is never shown twice. The `radar` meter counts companies found (10 a month on L2): the run
reserves what it may find and gives back what it didn't.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import indexes
import llm
import plans
from core.deps import user_dep
from growth import events
from growth.clock import utcnow
from research import search
from state import db
from util import iso

from .common import NO_VENDOR, as_dict, strip_providers, text
from .knowledge import knowledge, system_block
from .network import run_metered_n

router = APIRouter(prefix="/radar", tags=["opportunity-radar"])

FEATURE = METER = "radar"
PER_RUN = 5
SIGNALS = {"expansion": "Expansion", "new_plant": "New plant", "funding": "Funding", "leadership": "Leadership change",
           "losses": "Losses", "layoffs": "Layoffs", "new_rules": "New rules", "other": "Other news"}
GENERIC = {"ltd", "limited", "pvt", "private", "india", "indian", "inc", "llp", "co", "company", "corporation", "corp",
           "the", "and", "group", "industries", "enterprises", "solutions", "services", "works", "international"}

events.register("radar_run", "Opportunity Radar run (props.found, results)")
indexes.register("radar_companies", [("user_id", 1), ("at", -1)])
indexes.register("radar_companies", [("user_id", 1), ("key", 1)])
indexes.register("radar_runs", [("user_id", 1), ("at", -1)])

SYSTEM = (
    "You scan Indian business news for an experienced professional who is launching as a consultant. From the "
    "numbered news results, pick companies that show a real sign they may need this consultant's help soon: "
    "expansion, a new plant, funding, a leadership change, losses, layoffs or new rules. Use only the results given: "
    "the company must be named in the result you pick, and you refer to results only by their number. Never invent a "
    "company, a fact or a link. Skip results about listed giants where a new consultant has no realistic way in, "
    "unless the niche fits them exactly. Plain English, short sentences. " + NO_VENDOR
)


def company_key(name: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in GENERIC]
    return " ".join(words) or (name or "").lower().strip()


def _named_in(company: str, r: dict) -> bool:
    """The company must really be in that result: its distinctive first word, and most of the others."""
    hay = f"{r.get('title', '')} {r.get('snippet', '')}".lower()
    words = [w for w in company_key(company).split() if len(w) >= 3]
    if not words or words[0] not in hay:
        return False
    return sum(1 for w in words if w in hay) * 2 >= len(words)


def queries_for(industry: str, city: str) -> list[str]:
    where = f" {city}" if city else " India"
    return [f"{industry} company{where} expansion new plant", f"{industry}{where} raises funding investment",
            f"{industry}{where} appoints new CEO MD leadership change", f"{industry}{where} losses layoffs",
            f"{industry} India new rules regulation compliance"]


class RunIn(BaseModel):
    niche: str = Field("", max_length=160)
    industry: str = Field("", max_length=80)
    city: str = Field("", max_length=60)


def _fake(results: list[dict], n: int, industry: str, city: str) -> dict:
    kinds = list(SIGNALS)[:6]
    picks = []
    for i, r in enumerate(results[:n]):
        picks.append({"i": i + 1, "company": f"{city or 'India'} {industry.title()} Works {i + 1}", "signal": kinds[i % 6],
                      "summary": f"Test mode: {r['title'][:120]}.", "why": "A change like this usually means new problems to solve.",
                      "angle": "Congratulate them on the news and ask what it means for the team this year."})
    return {"companies": picks}


def _prompt(k: dict, niche: str, industry: str, city: str, results: list[dict], have: list[str], n: int) -> str:
    news = "\n".join(f"[{i + 1}] {r['title']} ({r['source']}, {r['published'] or 'date unknown'}): {r['snippet'][:350]}"
                     for i, r in enumerate(results))
    skip = ", ".join(have[:60]) or "none"
    return (f"{system_block(k)}\nNiche for this search: {niche or 'not given'}\nIndustry: {industry}\n"
            f"City: {city or 'anywhere in India'}\nAlready found before (skip these): {skip}\n\nNEWS RESULTS:\n{news}\n\n"
            f"Pick up to {n} different companies. For each: i (the result number), company (as named in that result), "
            f"signal (one of {', '.join(SIGNALS)}), summary (one sentence: what happened), why (one sentence: why it "
            "matters for this niche), angle (one sentence: how the consultant could open a conversation). "
            "Pick fewer, or none, if the results don't show real signals.\n"
            'JSON: {"companies": [{"i": 1, "company": "", "signal": "expansion", "summary": "", "why": "", "angle": ""}]}')


def public(c: dict) -> dict:
    return {"id": c["_id"], "run_id": c.get("run_id"), "company": c["company"], "signal": c["signal"],
            "signal_label": SIGNALS.get(c["signal"], "News"), "summary": c.get("summary", ""), "why": c.get("why", ""),
            "angle": c.get("angle", ""), "news": c.get("news"), "test": bool(c.get("test")),
            "status": c.get("status", "new"), "at": iso(c["at"])}


@router.post("/run")
async def run_radar(body: RunIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    await plans.require(d, user, FEATURE)
    k = await knowledge(d, user)
    niche = body.niche.strip() or k.get("niche") or ""
    industry = body.industry.strip() or k.get("target_industry") or ""
    city = body.city.strip()
    if len(industry) < 2:
        raise HTTPException(status_code=422, detail={"code": "industry", "msg": "Type the industry to watch, e.g. pharma or auto parts."})

    async def work(plan: str, n: int):
        qs = queries_for(industry, city)
        batches = await asyncio.gather(*(search.news(q, max_results=4) for q in qs))
        results, seen = [], set()
        for batch in batches:
            for r in batch:
                if r["url"] not in seen:
                    seen.add(r["url"])
                    results.append(r)
        results = results[:20]
        if not results:
            raise HTTPException(status_code=409, detail={
                "code": "no_news", "msg": "No news came back for that search. Try a wider industry or leave the city empty. This didn't use up any of your companies."})
        have = [c["company"] async for c in d.radar_companies.find({"user_id": uid}, {"company": 1}).sort("at", -1).limit(500)]
        have_keys = {company_key(x) for x in have}
        raw = as_dict(await llm.complete_json(task="radar_pick", system=SYSTEM,
                                              prompt=_prompt(k, niche, industry, city, results, have, n),
                                              fake=lambda: _fake(results, n, industry, city), model="fast", max_tokens=1400))
        if not isinstance(raw.get("companies"), list):
            raise llm.LLMError("radar: no companies list")
        run_id, now = uuid.uuid4().hex, utcnow()
        found = []
        for p in raw["companies"]:
            if len(found) >= n or not isinstance(p, dict):
                continue
            try:
                if int(p.get("i")) < 1:
                    continue
                r = results[int(p.get("i")) - 1]
            except (TypeError, ValueError, IndexError):
                continue
            name = text(p.get("company"), 120)
            key = company_key(name)
            if len(name) < 2 or key in have_keys or not _named_in(name, r) or not text(p.get("why"), 300):
                continue
            have_keys.add(key)
            sig = str(p.get("signal") or "").lower().strip()
            found.append({"_id": uuid.uuid4().hex, "user_id": uid, "run_id": run_id, "company": name, "key": key,
                          "signal": sig if sig in SIGNALS else "other",
                          **strip_providers({"summary": text(p.get("summary"), 300), "why": text(p.get("why"), 300),
                                             "angle": text(p.get("angle"), 300)}),
                          "news": {"title": r["title"], "url": r["url"], "source": r["source"], "published": r["published"]},
                          "test": bool(r.get("test")), "status": "new", "at": now})
        if found:
            await d.radar_companies.insert_many(found)
        await d.radar_runs.insert_one({"_id": run_id, "user_id": uid, "input": {"niche": niche, "industry": industry, "city": city},
                                       "queries": qs, "results_n": len(results), "found_n": len(found),
                                       "test": any(r.get("test") for r in results), "at": now})
        await events.track(d, "radar_run", user_id=uid, props={"found": len(found), "results": len(results)})
        return {"run_id": run_id, "found": [public(c) for c in found], "searched": len(results),
                "input": {"niche": niche, "industry": industry, "city": city},
                "test": any(r.get("test") for r in results)}, len(found)
    return await run_metered_n(d, user, METER, PER_RUN, work, access=FEATURE, partial=True)


@router.get("")
async def mine(status: Literal["", "new", "saved", "dismissed"] = "", user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, FEATURE)
    uid = str(user["_id"])
    f: dict = {"user_id": uid}
    f["status"] = status if status else {"$ne": "dismissed"}
    items = [public(c) async for c in d.radar_companies.find(f).sort("at", -1).limit(200)]
    runs = [{"id": r["_id"], "input": r["input"], "found": r["found_n"], "at": iso(r["at"])}
            async for r in d.radar_runs.find({"user_id": uid}).sort("at", -1).limit(10)]
    k = await knowledge(d, user)
    return {"items": items, "runs": runs, "signals": SIGNALS,
            "defaults": {"niche": k.get("niche") or "", "industry": k.get("target_industry") or ""}}


class PatchIn(BaseModel):
    status: Literal["new", "saved", "dismissed"]


@router.patch("/{cid}")
async def patch(cid: str, body: PatchIn, user: dict = Depends(user_dep())):
    await plans.require(db(), user, FEATURE)
    c = await db().radar_companies.find_one({"_id": cid, "user_id": str(user["_id"])})
    if not c:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Company not found."})
    await db().radar_companies.update_one({"_id": cid}, {"$set": {"status": body.status}})
    c["status"] = body.status
    return public(c)
