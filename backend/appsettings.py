"""Admin-editable app settings (one Mongo document, cached briefly).

    settings {_id: "app", live_case_id, group_session: {title, when, link}, support_whatsapp}

`live_case_id` is the case shown on the webinar ("One live case"). Change it in Admin before each webinar.
`group_session` is Akshat's group session for account holders who didn't buy L1 — shown on their home screen.
"""
from __future__ import annotations

import time
from copy import deepcopy

from core.errors import BadRequest

DEFAULTS: dict = {
    "live_case_id": "retail-chain-margins",
    "group_session": {"title": "Group session with Akshat", "when": "", "link": ""},
    "support_whatsapp": "",
}

_cache: dict = {"at": 0.0, "value": None}
TTL = 20


async def get(db) -> dict:
    if _cache["value"] is not None and time.time() - _cache["at"] < TTL:
        return deepcopy(_cache["value"])
    doc = await db.settings.find_one({"_id": "app"}) or {}
    out = deepcopy(DEFAULTS)
    for k in DEFAULTS:
        if k in doc and doc[k] is not None:
            out[k] = doc[k]
    _cache.update(at=time.time(), value=out)
    return deepcopy(out)


def _bad(field: str, msg: str):
    return BadRequest(msg, code="bad_setting", field=field)


def _text(v, n: int) -> str:
    return str(v or "").strip()[:n]


async def update(db, patch: dict) -> dict:
    """Raises 400 {code: bad_setting} for a case id that doesn't exist or a link that isn't a web link."""
    if not isinstance(patch, dict):
        raise _bad("settings", "Settings must be an object.")
    clean: dict = {}
    if patch.get("live_case_id"):
        from features import cases
        cid = _text(patch["live_case_id"], 80)
        if not await cases.get_case(db, cid):
            raise _bad("live_case_id", "That case doesn't exist. Pick one from the list.")
        clean["live_case_id"] = cid
    if isinstance(patch.get("group_session"), dict):
        g = patch["group_session"]
        link = _text(g.get("link"), 300)
        if link and not link.startswith(("https://", "http://")):
            raise _bad("group_session.link", "The session link must start with https://")
        clean["group_session"] = {"title": _text(g.get("title"), 120) or DEFAULTS["group_session"]["title"],
                                  "when": _text(g.get("when"), 60), "link": link}
    if "support_whatsapp" in patch:
        clean["support_whatsapp"] = _text(patch["support_whatsapp"], 20)
    if clean:
        await db.settings.update_one({"_id": "app"}, {"$set": clean}, upsert=True)
    _cache["value"] = None
    return await get(db)


def reset_cache() -> None:
    _cache["value"] = None
