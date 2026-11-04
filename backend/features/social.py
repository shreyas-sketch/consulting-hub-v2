"""Social Media Builder: LinkedIn posts for the member's niche, on a calendar. The member posts them.

social_posts {_id, user_id, run_id, n, pillar, format, hook, text, date (YYYY-MM-DD, IST), story_title?,
              status draft|posted, posted_at, at, updated_at}

Follows the current hub's LinkedIn Content Strategist (backend/gpts/prompts/linkedin-content-strategist.md): four
pillars (expertise, story, opinion, value), a scroll-stopping first line (never "I am excited to share"), short
paragraphs, a question or call to action at the end, human not press-release. Formats: story, insight, framework,
myth vs fact, mini case. Story and mini-case posts use the member's Career Story Bank (`stories`: title, situation,
what_i_did, result) when there is one; otherwise they leave [square brackets] for the member's own example.
`posts` counts each post written (30 a month on L2); a run reserves the posts asked for and gives back any not written.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import indexes
import llm
import plans
from core.deps import user_dep
from growth import events
from growth.clock import IST, utcnow
from state import db
from util import iso

from .common import NO_VENDOR, as_dict, as_list, clamp_int, strip_providers, text
from .knowledge import knowledge, links_in, no_links, own_links, system_block
from .network import run_metered_n

router = APIRouter(prefix="/social", tags=["social-builder"])

FEATURE, METER = "social_builder", "posts"
PILLARS = {"expertise": "Expertise: frameworks, insights, analysis from the niche",
           "story": "Story: a personal or professional story that builds trust",
           "opinion": "Opinion: a clear point of view on a trend or a common mistake",
           "value": "Value: a practical tip or mini-framework the ideal client can use this week"}
FORMATS = {"story": "Story", "insight": "Insight", "framework": "Framework", "myth_fact": "Myth vs fact", "mini_case": "Mini case"}
PATTERN = {3: (0, 2, 4), 4: (0, 1, 3, 4), 5: (0, 1, 2, 3, 4)}       # Mon=0 posting days

events.register("posts_made", "Social Media Builder: posts written (props.n)")
indexes.register("social_posts", [("user_id", 1), ("date", 1)])

SYSTEM = (
    "You write LinkedIn posts for an experienced Indian professional who is launching as a consultant. For a B2B "
    "consultant LinkedIn builds the trust that brings clients, so every post shows real expertise and sounds like a "
    "person, not a press release. Rules: a scroll-stopping first line (never 'I am excited to share', never a "
    "question as the first line), short paragraphs of 1-3 lines, 120-220 words, plain words, no buzzwords, no "
    "emojis, at most 3 hashtags at the very end, end with a question or a soft call to action. Never invent the "
    "member's experiences, clients or numbers: use only the stories given; where a personal example or figure is "
    "needed and none is given, write it in [square brackets] for the member to fill. No income claims. Never "
    "include links or web addresses: LinkedIn shows fewer people posts with links, and the member adds their own. "
    + NO_VENDOR
)


class GenIn(BaseModel):
    count: int = Field(5, ge=1, le=10)
    pillars: list[Literal["expertise", "story", "opinion", "value"]] = Field(default_factory=lambda: list(PILLARS), min_length=1, max_length=4)
    formats: list[Literal["story", "insight", "framework", "myth_fact", "mini_case"]] = Field(default_factory=lambda: list(FORMATS), min_length=1, max_length=5)
    per_week: int = Field(3, ge=3, le=5)
    start_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    topic: str = Field("", max_length=200)
    use_stories: bool = True


def _today() -> date:
    return utcnow().astimezone(IST).date()


async def read_stories(uid: str) -> list[dict]:
    """Career Story Bank is another tool's collection: read only the fields we need, and never fail on it."""
    out = []
    try:
        async for s in db().stories.find({"user_id": uid}).sort("at", -1).limit(8):
            row = {"title": text(s.get("title"), 120), "situation": text(s.get("situation"), 500),
                   "what_i_did": text(s.get("what_i_did"), 500), "result": text(s.get("result"), 300)}
            if row["title"] or row["situation"]:
                out.append(row)
    except Exception:  # noqa: BLE001 — a missing or different collection means "no stories yet"
        return []
    return out


def schedule(start: date, n: int, per_week: int, taken: set[str]) -> list[str]:
    days, d = [], start
    while len(days) < n and d < start + timedelta(days=400):
        if d.weekday() in PATTERN[per_week] and d.isoformat() not in taken:
            days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def plan_slots(body: GenIn, dates: list[str], stories: list[dict]) -> list[dict]:
    slots, si = [], 0
    for i, dt in enumerate(dates):
        fmt = body.formats[i % len(body.formats)]
        pillar = body.pillars[i % len(body.pillars)]
        story = None
        if stories and (fmt in ("story", "mini_case") or pillar == "story"):
            story = stories[si % len(stories)]
            si += 1
        slots.append({"n": i + 1, "date": dt, "pillar": pillar, "format": fmt, "story": story})
    return slots


def _fake(k: dict, slots: list[dict]) -> dict:
    niche = k.get("niche") or "[your niche]"
    out = []
    for s in slots:
        st = s["story"]
        hook = {"story": f"The day {st['title'].lower() if st else '[a moment from your career]'} taught me something.",
                "insight": f"Most owners in {niche} look at the wrong number first.",
                "framework": "A 3-step check I use before any big decision.",
                "myth_fact": f"Myth: more sales will fix the profit problem.",
                "mini_case": f"A {niche} business, a stuck number, and 90 days."}[s["format"]]
        body = (f"{hook}\n\n" + (f"{st['situation']}\n\n{st['what_i_did']}\n\n{st['result']}\n\n" if st else
                                  "[Your example: the situation, what you did, what changed.]\n\n") +
                f"Here's what I've learned working in {niche}: the first problem a client names is rarely the real one.\n\n"
                "Start with one question: what has this cost you in the last 90 days?\n\n"
                "What would you add?\n\n(Test mode post. Live mode writes this for your niche.)")
        out.append({"n": s["n"], "hook": hook, "text": body})
    return {"posts": out}


def _prompt(k: dict, slots: list[dict], topic: str) -> str:
    rows = []
    for s in slots:
        st = s["story"]
        story = (f" | use this story: {st['title']} — situation: {st['situation']}; what I did: {st['what_i_did']}; "
                 f"result: {st['result']}") if st else ""
        rows.append(f"[{s['n']}] pillar: {PILLARS[s['pillar']]} | format: {FORMATS[s['format']]}{story}")
    return (f"{system_block(k) or 'Niche not chosen yet; write for experienced business owners in India.'}\n"
            f"Consultant title: {k.get('consultant_title') or 'not set'}\nTopic focus this time: {topic or 'any, within the niche'}\n\n"
            "POSTS TO WRITE (one per line, by number):\n" + "\n".join(rows) + "\n\n"
            "Write every post. Each: n, hook (the first line), text (the full post including the hook as its first line).\n"
            'JSON: {"posts": [{"n": 1, "hook": "", "text": ""}]}')


def _post_text(v) -> str:
    lines = [" ".join(ln.split()) for ln in str(v or "").replace("\r", "").split("\n")]
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return out[:3000]


def public(p: dict) -> dict:
    return {"id": p["_id"], "run_id": p.get("run_id"), "pillar": p["pillar"], "format": p["format"],
            "format_label": FORMATS.get(p["format"], p["format"]), "hook": p.get("hook", ""), "text": p["text"],
            "date": p["date"], "story_title": p.get("story_title") or "", "status": p.get("status", "draft"),
            "posted_at": iso(p.get("posted_at")), "at": iso(p["at"])}


@router.post("/generate")
async def generate(body: GenIn, user: dict = Depends(user_dep())):
    d = db()
    uid = str(user["_id"])
    await plans.require(d, user, FEATURE)
    today = _today()
    bad_start = HTTPException(status_code=422, detail={"code": "start_date", "msg": "Pick a start date between today and the next four months."})
    try:
        start = date.fromisoformat(body.start_date) if body.start_date else today + timedelta(days=1)
    except ValueError:                              # e.g. 2026-02-30: the right shape but not a real date
        raise bad_start
    if start < today or start > today + timedelta(days=120):
        raise bad_start
    body.pillars = list(dict.fromkeys(body.pillars))
    body.formats = list(dict.fromkeys(body.formats))

    async def work(plan: str, n: int):
        k = await knowledge(d, user)
        stories = await read_stories(uid) if body.use_stories else []
        taken = {p["date"] async for p in d.social_posts.find({"user_id": uid, "date": {"$gte": start.isoformat()}}, {"date": 1})}
        slots = plan_slots(body, schedule(start, n, body.per_week, taken), stories)
        raw = as_dict(await llm.complete_json(task="social_posts", system=SYSTEM, prompt=_prompt(k, slots, body.topic.strip()),
                                              fake=lambda: _fake(k, slots), model="strong",
                                              max_tokens=min(8000, 700 * n + 400)))
        allowed = (await own_links(d, user)) | links_in(body.topic)
        got: dict[int, dict] = {}
        for x in as_list(raw.get("posts")):
            if not isinstance(x, dict):
                continue
            i = clamp_int(x.get("n"), -1, 10_000, -1)
            t = no_links(strip_providers(_post_text(x.get("text") if isinstance(x.get("text"), str) else "")), allowed)
            if 1 <= i <= len(slots) and i not in got and len(t) >= 150:
                hook = no_links(strip_providers(text(x.get("hook"), 200)), allowed)
                got[i] = {"hook": hook or text(t.split("\n")[0], 200), "text": t}
        if not got:
            raise llm.LLMError("social: no posts")
        run_id, now = uuid.uuid4().hex, utcnow()
        docs = [{"_id": uuid.uuid4().hex, "user_id": uid, "run_id": run_id, "n": s["n"], "pillar": s["pillar"],
                 "format": s["format"], **got[s["n"]], "date": s["date"],
                 "story_title": (s["story"] or {}).get("title", ""), "status": "draft", "posted_at": None, "at": now,
                 "updated_at": now} for s in slots if s["n"] in got]
        await d.social_posts.insert_many(docs)
        await events.track(d, "posts_made", user_id=uid, props={"n": len(docs)})
        return {"items": [public(p) for p in docs], "stories_used": sum(1 for p in docs if p["story_title"])}, len(docs)
    return await run_metered_n(d, user, METER, body.count, work, access=FEATURE)


@router.get("")
async def listing(month: str = Query("", pattern=r"^(\d{4}-\d{2})?$"), user: dict = Depends(user_dep())):
    d = db()
    await plans.require(d, user, FEATURE)
    uid = str(user["_id"])
    m = month or _today().strftime("%Y-%m")
    y, mo = int(m[:4]), int(m[5:7])
    if not 1 <= mo <= 12 or not 2000 <= y <= 2100:
        raise HTTPException(status_code=422, detail={"code": "month", "msg": "That month isn't valid. Pick one from the calendar."})
    first = date(y, mo, 1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    items = [public(p) async for p in d.social_posts.find(
        {"user_id": uid, "date": {"$gte": first.isoformat(), "$lt": nxt.isoformat()}}).sort([("date", 1), ("n", 1)])]
    today = _today().isoformat()
    upcoming = await d.social_posts.count_documents({"user_id": uid, "date": {"$gte": today}, "status": "draft"})
    nxt_post = await d.social_posts.find_one({"user_id": uid, "date": {"$gte": today}, "status": "draft"}, sort=[("date", 1)])
    return {"month": m, "items": items, "upcoming": upcoming, "next_date": nxt_post["date"] if nxt_post else None,
            "stories": len(await read_stories(uid)), "pillars": {k: v.split(":")[0] for k, v in PILLARS.items()},
            "formats": FORMATS}


class PatchIn(BaseModel):
    text: Optional[str] = Field(None, min_length=20, max_length=3000)
    date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: Optional[Literal["draft", "posted"]] = None


@router.patch("/{pid}")
async def patch(pid: str, body: PatchIn, user: dict = Depends(user_dep())):
    await plans.require(db(), user, FEATURE)
    p = await db().social_posts.find_one({"_id": pid, "user_id": str(user["_id"])})
    if not p:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Post not found."})
    s: dict = {"updated_at": utcnow()}
    if body.text is not None:
        s["text"] = _post_text(body.text)
        s["hook"] = text(s["text"].split("\n")[0], 200)
    if body.date is not None:
        try:
            date.fromisoformat(body.date)
        except ValueError:
            raise HTTPException(status_code=422, detail={"code": "date", "msg": "That date isn't valid."})
        s["date"] = body.date
    if body.status is not None:
        s["status"] = body.status
        s["posted_at"] = utcnow() if body.status == "posted" else None
    await db().social_posts.update_one({"_id": pid}, {"$set": s})
    p.update(s)
    return public(p)


@router.delete("/{pid}")
async def remove(pid: str, user: dict = Depends(user_dep())):
    await plans.require(db(), user, FEATURE)
    r = await db().social_posts.delete_one({"_id": pid, "user_id": str(user["_id"])})
    return {"ok": r.deleted_count == 1}
