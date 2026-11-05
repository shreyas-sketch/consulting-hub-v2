"""Mobile OTP login that also signs people up.

POST /api/auth/otp/request  {phone, channel?}                      → {challenge_id, channel, sent_to, expires_in, resend_in, is_new, dev_code?}
POST /api/auth/otp/verify   {challenge_id, phone, code, name?, utm?, device_id?} → {user, is_new} + cookies
PATCH /api/auth/profile     {name?, email?}                         → {user}

A new number gets an account on verify: webinar attendees scan the QR, type their
number, and they're in. New accounts are free accounts (each webinar tool once).
There is no trial. One account per mobile number.
QA_MODE: codes go to the console sender, the code comes back as `dev_code`, and
000000 is accepted.
"""
from __future__ import annotations

import logging
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field

from core.errors import BadRequest, Conflict, Forbidden
from core.settings import settings
from growth import events
from growth.clock import utcnow

from . import otp_service
from .otp_providers import ConsoleSender, Senders, build_senders
from .phone import InvalidPhone, mask, normalise_in_mobile

log = logging.getLogger("accounts.routes")
router = APIRouter(prefix="/auth", tags=["auth-otp"])

_state: dict = {"senders": None, "fixed": False, "wa": None}


def use_senders(senders: Optional[Senders] = None) -> None:
    """Pin the OTP senders (tests, QA server). None = build them from settings and the WhatsApp switch."""
    _state["senders"] = senders
    _state["fixed"] = senders is not None


def _db():
    import state
    return state.db()


def _senders() -> Senders:
    from core.flags import is_on
    wa = is_on("WHATSAPP_OTP")
    if _state["senders"] is None or (not _state["fixed"] and _state["wa"] != wa):
        _state["senders"] = build_senders()
        _state["wa"] = wa
    return _state["senders"]


def client_ip(request: Request) -> str:
    """The caller's IP, for rate limits (OTP sends, the public diagnostic, the website lead form).

    Anyone can send X-Forwarded-For or CF-Connecting-IP, so only what our own proxies add is trusted. Railway's edge
    adds the address it saw as the LAST X-Forwarded-For entry; Railway staff: "The right most value of the
    X-Forwarded-For header is trustworthy" (station.railway.com/questions/edge-proxy-x-forwarded-for-and-x-real-ip-c5a50049).
      TRUSTED_PROXY_HOPS (default 1): proxies in front of the app that append to X-Forwarded-For; the client is that
        many entries from the right. 0 = ignore the header.
      BEHIND_CLOUDFLARE=true: Cloudflare sits in front of Railway, so read CF-Connecting-IP (only then).
    Without a trusted header: the socket address."""
    from core.settings import env_bool, env_int
    if env_bool("BEHIND_CLOUDFLARE"):
        v = (request.headers.get("cf-connecting-ip") or "").strip()
        if v:
            return v[:64]
    hops = env_int("TRUSTED_PROXY_HOPS", 1)
    if hops > 0:
        parts = [p.strip() for p in (request.headers.get("x-forwarded-for") or "").split(",") if p.strip()]
        if parts:
            return parts[max(0, len(parts) - hops)][:64]
    return ((request.client.host if request.client else "") or "")[:64]


class OtpRequestIn(BaseModel):
    phone: str = Field(..., max_length=20)
    channel: Literal["auto", "sms", "whatsapp"] = "auto"


class OtpVerifyIn(BaseModel):
    challenge_id: str = Field(..., max_length=64)
    phone: str = Field(..., max_length=20)
    code: str = Field(..., max_length=8)
    name: Optional[str] = Field(None, max_length=80)
    utm: dict = Field(default_factory=dict)
    device_id: Optional[str] = Field(None, max_length=128)


class ProfileIn(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    email: Optional[EmailStr] = None


_UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid", "fbclid", "src")
_SAFE = re.compile(r"[^A-Za-z0-9_.\-: ]")


def clean_utm(utm: dict) -> dict:
    return {k: _SAFE.sub("", str(v))[:100] for k, v in (utm or {}).items() if k in _UTM_KEYS and v}


def classify_source(utm: dict) -> str:
    """Acquisition source for Admin › Pulse. `?src=webinar` (the QR code) wins."""
    if utm.get("src"):
        return utm["src"].lower()[:30]
    if utm.get("gclid"):
        return "google_ads"
    if utm.get("fbclid"):
        return "meta_ads"
    src = (utm.get("utm_source") or "").lower()
    if src:
        return {"fb": "meta_ads", "facebook": "meta_ads", "instagram": "meta_ads", "ig": "meta_ads",
                "meta": "meta_ads", "google": "google_ads", "whatsapp": "whatsapp",
                "email": "email", "webinar": "webinar", "zoom": "webinar"}.get(src, src[:30])
    return "organic"


def admin_phones() -> set[str]:
    return settings.auth.admin_phones


@router.post("/otp/request")
async def otp_request(body: OtpRequestIn, request: Request, response: Response):
    try:
        phone = normalise_in_mobile(body.phone)
    except InvalidPhone as e:
        raise BadRequest(str(e), code="invalid_phone")
    anon = events.ensure_anon_cookie(request, response)
    is_new = not await _db().users.find_one({"phone": phone}, {"_id": 1})
    senders = _senders()
    ch = await otp_service.request_otp(_db(), senders, phone, channel=body.channel,      # OtpError is an AppError
                                       ip=client_ip(request), anon_id=anon)
    out = {"challenge_id": ch.challenge_id, "channel": ch.channel, "sent_to": mask(phone),
           "expires_in": ch.expires_in, "resend_in": ch.resend_in, "fell_back": ch.fell_back, "is_new": is_new}
    if settings.qa_mode and not settings.is_production:
        for s in (senders.sms, senders.whatsapp):
            if isinstance(s, ConsoleSender) and s.sent and s.sent[-1][0] == phone:
                out["dev_code"] = s.sent[-1][1]
                break
    return out


async def _qa_bypass(db, challenge_id: str, phone: str, code: str) -> bool:
    if not (settings.qa_mode and not settings.is_production and code == "000000"):
        return False
    res = await db.otp_challenges.update_one({"_id": challenge_id, "phone": phone, "consumed": False},
                                             {"$set": {"consumed": True, "consumed_at": utcnow()}})
    return res.modified_count == 1


async def create_member(db, phone: str, *, name: Optional[str], utm: dict, role: str = "user") -> dict:
    now = utcnow()
    doc = {"phone": phone, "phone_verified_at": now, "name": (name or "").strip() or None, "role": role,
           "status": "active", "created_at": now, "first_login_at": now,
           "acquisition": {"source": classify_source(utm), "utm": utm, "at": now}}
    try:
        res = await db.users.insert_one(doc)
        doc["_id"] = res.inserted_id
    except Exception:  # noqa: BLE001 — two verifies racing on one number
        return await db.users.find_one({"phone": phone})
    await events.track(db, "signup", user_id=str(doc["_id"]), props={"source": doc["acquisition"]["source"]})
    return doc


@router.post("/otp/verify")
async def otp_verify(body: OtpVerifyIn, request: Request, response: Response):
    from auth import public_user, set_auth_cookies
    db = _db()
    try:
        phone = normalise_in_mobile(body.phone)
    except InvalidPhone as e:
        raise BadRequest(str(e), code="invalid_phone")
    anon = events.anon_id_from(request)
    if not await _qa_bypass(db, body.challenge_id, phone, body.code.strip()):
        await otp_service.verify_otp(db, body.challenge_id, phone, body.code, anon_id=anon)

    now = utcnow()
    user = await db.users.find_one({"phone": phone})
    is_new = user is None
    role = "admin" if phone in admin_phones() else "user"
    if is_new:
        user = await create_member(db, phone, name=body.name, utm=clean_utm(body.utm), role=role)
    else:
        if (user.get("status") or "active") == "revoked":
            raise Forbidden("This account is disabled.", code="revoked")
        upd: dict = {"last_login_at": now}
        if role == "admin" and user.get("role") != "admin":
            upd["role"] = "admin"
        if body.name and not user.get("name"):
            upd["name"] = body.name.strip()
        await db.users.update_one({"_id": user["_id"]}, {"$set": upd})
        user.update(upd)
        await events.track(db, "login", user_id=str(user["_id"]))
    if body.device_id:
        await db.users.update_one({"_id": user["_id"]}, {"$addToSet": {"device_ids": body.device_id[:128]}})
    await events.identify(db, anon, str(user["_id"]))
    set_auth_cookies(response, str(user["_id"]), user.get("role") or "user")
    return {"user": public_user(user), "is_new": is_new}


def _user_dep():
    from auth import get_current_user
    return get_current_user


@router.patch("/profile")
async def update_profile(body: ProfileIn, user: dict = Depends(_user_dep())):
    from auth import public_user
    upd = {}
    if body.name is not None:
        upd["name"] = body.name.strip() or None
    if body.email is not None:
        email = body.email.lower().strip()
        staff = settings.auth.admin_email
        clash = await _db().users.find_one({"email": email, "_id": {"$ne": user["_id"]}})
        # Emails here aren't checked, so a member can't take the staff login email (seed_admin also refuses it).
        if clash or (staff and email == staff and not user.get("password_hash")):
            raise Conflict("Email already in use.", code="email_taken")
        upd["email"] = email
    if upd:
        await _db().users.update_one({"_id": user["_id"]}, {"$set": upd})
    return {"user": public_user({**user, **upd})}
