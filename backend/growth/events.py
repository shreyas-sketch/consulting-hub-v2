"""The single event table.

Every funnel step, message, tool run and payment lands here as one row:
    {_id, name, ts, user_id?, anon_id?, props, src}
Admin pulse, webinar report and usage charts read this collection. Names are a closed registry so a typo cannot
silently create a new metric.

Server code calls `track(db, name, ...)`. The browser posts to POST /api/events,
which accepts only the CLIENT_EVENTS subset (views and clicks); anything that
means money or a tool run is recorded server-side only.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from .clock import utcnow

log = logging.getLogger("growth.events")

EVENTS: dict[str, str] = {
    # acquisition & auth
    "page_view": "Any page view (props.path)",
    "otp_requested": "OTP sent (props.channel)",
    "otp_failed": "OTP send or verify failed (props.reason)",
    "signup": "New account created by OTP (props.source)",
    "login": "Existing account logged in",
    "staff_login": "Staff email login",
    # webinar tools
    "tool_opened": "A tool screen opened (props.tool) — client",
    "readiness_done": "Readiness Score saved (props.total, potential)",
    "snapshot_run": "Niche Snapshot made (props.top_niche)",
    "goal_saved": "Goal Map saved (props.monthly_goal_inr)",
    "case_answered": "Case answer scored (props.case_id, score, live)",
    "brief_made": "Meeting Brief made (props.company, sources)",
    "linkedin_checked": "LinkedIn Score run (props.score, rewrites)",
    "file_viewed": "My Consulting File opened",
    "group_session_clicked": "Group session link tapped — client",
    "limit_hit": "A metered feature hit its limit (props.feature, plan)",
    "locked_hit": "A locked feature was tried (props.feature, plan)",
    # money
    "upgrade_viewed": "Upgrade prompt or plans page shown (props.surface) — client",
    "checkout_opened": "Checkout opened (props.plan, period) — client",
    "checkout_started": "Checkout created server-side (props.plan, period)",
    "payment_captured": "Payment captured (props.plan, amount_inr)",
    "subscription_activated": "Subscription active (props.plan, period)",
    "subscription_cancelled": "Subscription cancelled (props.plan)",
    "downsell_offered": "₹1,999 plan offered once after an L1 cancel",
    "l2_started": "Admin started L2 for a member (props.l1_paused)",
    "l1_resumed": "L1 billing resumed after L2 (props.subscription_id)",
    "plan_granted": "Admin grant written (props.plan, months)",
    "share_clicked": "Share tapped (props.surface) — client",
    # messages
    "message_sent": "Inbox alert written (props.kind)",
    "feature_toggled": "Admin switched a feature (props.key, on)",
}

CLIENT_EVENTS = {"page_view", "tool_opened", "upgrade_viewed", "checkout_opened", "share_clicked", "group_session_clicked"}

_ANON_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
ANON_COOKIE = "ch_anon"
_MAX_PROPS = 30


class UnknownEvent(ValueError):
    pass


def _clean_props(props: Optional[dict]) -> dict:
    out: dict[str, Any] = {}
    for k, v in list((props or {}).items())[:_MAX_PROPS]:
        if not isinstance(k, str) or k.startswith("$") or "." in k:
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k[:40]] = v[:300] if isinstance(v, str) else v
        elif isinstance(v, (list, tuple)):
            out[k[:40]] = [x for x in v[:20] if isinstance(x, (str, int, float, bool))]
    return out


async def track(
    db, name: str, *, user_id: Optional[str] = None, anon_id: Optional[str] = None,
    props: Optional[dict] = None, src: str = "server", ts: Optional[datetime] = None,
    dedupe_key: Optional[str] = None,
) -> Optional[str]:
    """Record one event. Never raises on a DB error (analytics must not break a
    user action) — but an unknown name raises, so typos fail in tests."""
    if name not in EVENTS:
        raise UnknownEvent(name)
    doc = {
        "_id": dedupe_key or str(uuid.uuid4()),
        "name": name, "ts": ts or utcnow(),
        "user_id": user_id, "anon_id": anon_id,
        "props": _clean_props(props), "src": src,
    }
    try:
        await db.events.insert_one(doc)
    except Exception as e:  # noqa: BLE001 — duplicate dedupe_key or DB hiccup
        if "duplicate" not in str(e).lower():
            log.warning("event %s not recorded: %s", name, e)
        return None
    return doc["_id"]


async def identify(db, anon_id: Optional[str], user_id: str) -> int:
    """Stitch a visitor's anonymous events onto the account they just created
    or logged into, so the funnel starts at their first visit."""
    if not anon_id or not _ANON_RE.match(anon_id):
        return 0
    res = await db.events.update_many(
        {"anon_id": anon_id, "user_id": None}, {"$set": {"user_id": user_id}}
    )
    return res.modified_count


def anon_id_from(request: Request) -> Optional[str]:
    v = request.cookies.get(ANON_COOKIE)
    return v if v and _ANON_RE.match(v) else None


def ensure_anon_cookie(request: Request, response: Response) -> str:
    """Give every visitor a first-party anonymous id (1 year)."""
    from core.settings import settings
    existing = anon_id_from(request)
    if existing:
        return existing
    anon = uuid.uuid4().hex
    response.set_cookie(ANON_COOKIE, anon, max_age=365 * 86400, httponly=True,
                        secure=settings.cookie_secure, samesite="lax", path="/")
    return anon


# ---------------------------------------------------------------- routes ----
router = APIRouter(tags=["events"])
_db = None


def bind_db(db) -> None:
    global _db
    _db = db


class ClientEvent(BaseModel):
    name: str
    props: dict = Field(default_factory=dict)


async def _optional_user_id(request: Request) -> Optional[str]:
    try:
        from auth import get_current_user
        user = await get_current_user(request)
        return str(user["_id"])
    except Exception:  # noqa: BLE001 — anonymous is fine here
        return None


@router.post("/events", status_code=202)
async def post_event(body: ClientEvent, request: Request, response: Response):
    if body.name not in CLIENT_EVENTS:
        return {"accepted": False, "reason": "not a client event"}
    anon = ensure_anon_cookie(request, response)
    uid = await _optional_user_id(request)
    await track(_db, body.name, user_id=uid, anon_id=anon, props=body.props, src="web")
    return {"accepted": True}
