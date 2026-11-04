"""What every tool knows about the member — the new app's version of the current hub's Knowledge Base.

The current hub asks members to fill five fields once (niche, value proposition, target industry, target audience,
consulting business goal) and injects them into every GPT. Here they are filled automatically from Starting Point:
the chosen Niche Snapshot option and the Goal Map. `blueprint` is the FINALIZED NICHE package the current hub's
LinkedIn Blueprint, Strategy Thinking, Credibility Code and Document Builder GPTs take as their first message.
"""
from __future__ import annotations

from typing import Optional

from util import inr

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
