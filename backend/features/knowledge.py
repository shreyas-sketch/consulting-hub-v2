"""What every tool knows about the member — the new app's version of the current hub's Knowledge Base.

The current hub asks members to fill five fields once (niche, value proposition, target industry, target audience,
consulting business goal) and injects them into every GPT. Here they are filled automatically from Starting Point:
the chosen Niche Snapshot option and the Goal Map. `blueprint` is the FINALIZED NICHE package the current hub's
LinkedIn Blueprint, Strategy Thinking, Credibility Code and Document Builder GPTs take as their first message.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from util import inr

from .common import strip_links
from .start import blueprint_text


async def knowledge(db, user: dict) -> dict:
    uid = str(user["_id"])
    snap = await db.snapshots.find_one({"user_id": uid}, sort=[("at", -1)])
    goal = await db.goals.find_one({"_id": uid})
    o: Optional[dict] = None
    if snap and snap.get("options"):
        o = snap["options"][min(int(snap.get("chosen") or 0), len(snap["options"]) - 1)]
    industry = ((snap or {}).get("input") or {}).get("industry") or ""
    return {
        "niche": (o or {}).get("niche") or "",
        "value_proposition": (o or {}).get("value_prop") or "",
        "target_industry": industry,
        "target_audience": (o or {}).get("who") or "",
        "consulting_goal": f"{inr(goal['monthly_goal_inr'])} a month at {inr(goal['fee_inr'])} per client" if goal else "",
        "consultant_title": (o or {}).get("title") or "",
        "blueprint": blueprint_text(o, user.get("name")) if o else None,
    }


def system_block(k: dict) -> str:
    """The block the L1 / L2 tools add to a GPT's system prompt (same idea as the current hub's Knowledge Base block)."""
    rows = [("Niche", k["niche"]), ("Value proposition", k["value_proposition"]), ("Target industry", k["target_industry"]),
            ("Target audience", k["target_audience"]), ("Consulting business goal", k["consulting_goal"])]
    filled = [f"- {a}: {b}" for a, b in rows if b]
    if not filled:
        return ""
    return "PARTICIPANT KNOWLEDGE BASE (already known; don't ask for these again):\n" + "\n".join(filled)


def offer_block(k: dict) -> str:
    """Only the niche and offer wording. For prompts whose answer a prospect reads (Client Diagnostic thank-you):
    never the income goal, fees or the full blueprint, so nothing private can be echoed back to an outsider."""
    rows = [("Niche", k.get("niche")), ("Consultant title", k.get("consultant_title")),
            ("Value proposition", k.get("value_proposition"))]
    filled = [f"- {a}: {b}" for a, b in rows if b]
    return ("THE CONSULTANT'S OFFER:\n" + "\n".join(filled)) if filled else ""


# ---------------------------------------------------------------- the member's own links ----
# AI text may only carry links the member really owns (or typed in themselves); common.strip_links removes the rest.
_URL = re.compile(r"(https?://[^\s)<>\]]+|www\.[^\s)<>\]]+)", re.I)


def link_variants(u: str) -> set[str]:
    """The spellings of one link the AI might write: with https://, http:// or (for www. hosts) no scheme."""
    u = (u or "").strip().rstrip(".,;:!?").rstrip("/")
    if not u:
        return set()
    rest = re.sub(r"^https?://", "", u, flags=re.I)
    out = {u, f"https://{rest}", f"http://{rest}"}
    if rest.lower().startswith("www."):
        out.add(rest)
    return out


def links_in(*texts: str) -> set[str]:
    """Links the member typed into the tool themselves (call notes, context): theirs to keep."""
    out: set[str] = set()
    for t in texts:
        for m in _URL.finditer(t or ""):
            out |= link_variants(m.group(0))
    return out


async def own_links(db, user: dict) -> set[str]:
    """The member's website address(es), booking link and published diagnostic links. Never raises."""
    uid = str(user["_id"])
    out: set[str] = set()
    try:
        from core.settings import settings

        from .site_render import public_base, sites_domain
        site = await db.sites.find_one({"user_id": uid}, {"slug": 1, "domain": 1, "domain_status": 1, "contact": 1})
        if site:
            if site.get("slug"):
                out |= link_variants(f"{public_base()}/s/{site['slug']}")
                if sites_domain():
                    out |= link_variants(f"https://{site['slug']}.{sites_domain()}")
            if site.get("domain") and site.get("domain_status") == "connected":
                out |= link_variants(f"https://{site['domain']}")
            out |= link_variants((site.get("contact") or {}).get("calendly") or "")
        async for x in db.diagnostics.find({"user_id": uid}, {"cta_link": 1, "public_id": 1}).limit(50):
            out |= link_variants(x.get("cta_link") or "")
            if x.get("public_id"):
                out |= link_variants(f"{settings.public_base_url}/d/{x['public_id']}")
    except Exception:  # noqa: BLE001 — a missing collection just means fewer links are kept
        pass
    return out


def no_links(v: Any, allowed: Iterable[str] = ()) -> Any:
    """common.strip_links over every string in a dict / list (AI-written fields only, never search results)."""
    allowed = list(allowed)
    if isinstance(v, str):
        return strip_links(v, allowed).strip()
    if isinstance(v, list):
        return [no_links(x, allowed) for x in v]
    if isinstance(v, dict):
        return {k: no_links(x, allowed) for k, x in v.items()}
    return v
