"""Website Builder (₹1,999 plan and up), ported from Owner Desk and adapted to consultants.

One site per member: the AI writes every section from what the hub knows (Starting Point niche, Offer Card, career
stories), then the member edits each section by prompt (meter `site_ai`, a proposal they accept or discard) or by hand
(free), reorders and hides sections, picks a look, adds a logo and photo, and publishes.

Pages: plans.cap("site_pages") → ₹1,999 plan: Home only; L1/L2: Home, About, Services, Case studies, Contact.
Own domain: plans.cap("custom_domain") (L1/L2). The "editorial" look is L2 only.

Public site (outside /api, on `public_router`):
    GET /s/{slug}, /s/{slug}/{page}   HTML, only when published (or ?preview=1 for the logged-in owner)
    GET /s/{slug}/img/{logo|photo}    the site's images
    POST /api/website/public/{slug}/leads   contact form: no login, honeypot field "website", rate-limited per IP
On its own address (own domain, or <slug>.SITES_DOMAIN) the same pages answer at "/", "/about"… through
install_domain_middleware(app), which server.py must call; nothing else of the hub answers on a member's address.

    sites       see features/site_model.py
    site_leads  {_id, site_id, user_id, name, email, phone, company, message, page, ip_hash, at, read}
    site_rate   {_id: "<key>:<window>", n, purge_at}   (TTL)
"""
from __future__ import annotations

import copy as _copy
import hashlib
import logging
import re
import time
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

import indexes
import media
import plans
from core.deps import admin_dep, optional_user, user_dep
from growth import events
from growth.clock import utcnow
from notify import service as notify_service
from state import db
from util import iso, oid

from . import site_ai, site_looks
from . import site_model as M
from . import site_render as R
from .common import run_metered, text

log = logging.getLogger("website")
router = APIRouter(tags=["website-builder"])
public_router = APIRouter(tags=["website-public"])

events.register("site_built", "Website Builder: the AI wrote a site")
events.register("site_ai_edit", "Website Builder: a section rewritten by prompt")
events.register("site_published", "Website Builder: site published or taken offline")
events.register("site_lead", "Website Builder: a visitor sent the contact form")
indexes.register("sites", [("user_id", 1)], {"unique": True})
indexes.register("sites", [("slug", 1)], {"unique": True})
indexes.register("sites", [("domain", 1)], {"unique": True, "sparse": True})
indexes.register("site_leads", [("user_id", 1), ("at", -1)])
indexes.register("site_rate", [("purge_at", 1)], {"expireAfterSeconds": 0})
notify_service.register_kind("site_lead")

IMAGE_MAX = 2 * 1024 * 1024
LEADS_PER_IP = (5, 600)          # 5 messages per IP per site in 10 minutes
LEADS_PER_SITE = (40, 3600)      # and 40 an hour per site, whatever the source
RESERVED = {"admin", "api", "app", "www", "mail", "s", "static", "assets", "login", "hub", "help", "support", "blog",
            "docs", "status", "ftp", "smtp", "root", "dashboard", "consultation", "akshat", "test", "demo"}
SLUG_RX = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$")
EMAIL_RX = re.compile(r"^[A-Za-z0-9._%+'-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}$")
HOST_RX = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
SECOND_LEVEL = {"co.in", "net.in", "org.in", "firm.in", "gen.in", "ind.in", "ac.in", "edu.in", "res.in", "co.uk",
                "org.uk", "com.au", "net.au", "co.nz", "com.sg", "co.za", "com.my", "ae.org"}


def _err(status: int, code: str, msg: str, **extra) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "msg": msg, **extra})


def _locked(plan_needed: str, msg: str) -> HTTPException:
    return _err(403, "locked", msg, feature="website", plan_needed=plan_needed)


async def _site(uid: str) -> Optional[dict]:
    return await db().sites.find_one({"user_id": uid})


async def _need(user: dict) -> tuple[str, dict]:
    plan = await plans.require(db(), user, "website")
    site = await _site(str(user["_id"]))
    if not site:
        raise _err(404, "no_site", "Build your site first.")
    return plan, site


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:40].strip("-")
    return s if len(s) >= 3 and s not in RESERVED else "consultant"


async def unique_slug(base: str) -> str:
    for i in range(1, 200):
        s = base if i == 1 else f"{base[:36]}-{i}"
        if not await db().sites.find_one({"slug": s}, {"_id": 1}):
            return s
    return f"{base[:28]}-{int(time.time())}"


# ───────────────────────── domains ─────────────────────────
def _registrable(labels: list[str]) -> int:
    return 3 if len(labels) >= 3 and ".".join(labels[-2:]) in SECOND_LEVEL else 2


def clean_domain(raw: str) -> str:
    d = re.sub(r"^[a-z]+://", "", (raw or "").strip().lower()).split("/")[0].split(":")[0].strip(".")
    if not HOST_RX.match(d):
        raise _err(400, "bad_domain", "That doesn't look like a domain. Type it like www.yourname.in")
    labels = d.split(".")
    if len(labels) == _registrable(labels):
        d = "www." + d                      # most providers don't allow this record on the bare name
    app, sd = R.app_host(), R.sites_domain()
    if (app and (d == app or d.endswith("." + app))) or (sd and (d == sd or d.endswith("." + sd))):
        raise _err(400, "bad_domain", "Use a domain you own, like www.yourname.in")
    return d


def dns_steps(domain: str) -> dict:
    labels = domain.split(".")
    return {"type": "CNAME", "name": ".".join(labels[:len(labels) - _registrable(labels)]) or "@",
            "value": R.app_host(), "domain": domain}


async def lookup_cname(domain: str) -> list[str]:
    """Where the domain's CNAME points. Empty when there is none (or DNS can't be reached)."""
    try:
        import dns.asyncresolver
        ans = await dns.asyncresolver.resolve(domain, "CNAME", lifetime=4.0)
        return [str(r.target).rstrip(".").lower() for r in ans]
    except Exception:  # noqa: BLE001
        return []


# ───────────────────────── what the editor gets ─────────────────────────
def _section_out(s: dict) -> dict:
    return {"id": s["id"], "type": s["type"], "hidden": bool(s.get("hidden")), "data": s.get("data") or {},
            "label": M.SECTIONS[s["type"]]["label"], "summary": M.summary(s["type"], s.get("data") or {}),
            "placeholders": M.placeholders(s.get("data"))}


async def _state(user: dict, plan: str, site: Optional[dict]) -> dict:
    caps = {"pages": max(1, plans.cap("site_pages", plan)), "custom_domain": bool(plans.cap("custom_domain", plan)),
            "editorial": site_looks.allowed("editorial", plan)}
    out = {"looks": site_looks.listing(plan), "caps": caps, "plan": plan,
           "page_names": [{"key": k, "label": v} for k, v in M.PAGES],
           "section_types": [{"type": t, "label": v["label"]} for t, v in M.SECTIONS.items()],
           "sites_domain": R.sites_domain() or None, "dns_target": R.app_host()}
    if not site:
        src = await site_ai.sources(db(), user)
        out["site"] = None
        out["suggested_look"] = site_looks.suggest(src["industry"], src["niche"], src["title"])
        out["known"] = {"name": src["name"], "title": src["title"], "niche": src["niche"], "audience": src["audience"],
                        "offer": bool(src["offer"]), "stories": len(src["stories"])}
        return out
    live_keys = R.page_keys_for(site, plan)
    pages = [{"key": k, "label": M.PAGE_LABEL[k], "live": k in live_keys,
              "sections": [_section_out(s) for s in site["pages"][k]]} for k in M.PAGE_KEYS if k in site.get("pages", {})]
    unread = await db().site_leads.count_documents({"user_id": site["user_id"], "read": False})
    domain = site.get("domain")
    out["site"] = {
        "id": site["_id"], "slug": site["slug"], "look": site.get("look"), "profile": site.get("profile") or {},
        "pages": pages, "published": bool(site.get("published")), "published_at": iso(site.get("published_at")),
        "url": R.site_root(site, plan), "hub_url": f"{R.public_base()}/s/{site['slug']}",
        "preview_path": f"/s/{site['slug']}?preview=1", "contact": site.get("contact") or {},
        "logo_url": media.blob_url(site.get("logo_id")), "photo_url": media.blob_url(site.get("photo_id")),
        "domain": domain, "domain_status": site.get("domain_status") if domain else None,
        "dns": dns_steps(domain) if domain else None, "seo": site.get("seo") or {},
        "proposal": _proposal_out(site.get("proposal")), "can_undo": bool(site.get("undo")),
        "placeholders": M.site_placeholders(site, live_keys), "views": int(site.get("views") or 0),
        "leads_unread": unread, "updated_at": iso(site.get("updated_at")),
    }
    return out


def _proposal_out(p: Optional[dict]) -> Optional[dict]:
    if not p:
        return None
    return {"page": p["page"], "section_id": p["section_id"], "type": p["type"], "label": M.SECTIONS[p["type"]]["label"],
            "before": p["before"], "after": p["after"], "note": p.get("note") or "", "instruction": p.get("instruction"),
            "at": iso(p.get("at"))}


def _find(site: dict, sid: str, page: str = "") -> tuple[str, int]:
    for k in ([page] if page else []) + M.PAGE_KEYS:
        for i, s in enumerate((site.get("pages") or {}).get(k) or []):
            if s["id"] == sid:
                return k, i
    raise _err(404, "not_found", "That section isn't on your site any more.")


async def _save_page(site: dict, page: str, sections: list[dict], *, undo: bool = True, extra: Optional[dict] = None):
    upd = {f"pages.{page}": sections, "updated_at": utcnow(), **(extra or {})}
    if undo:
        upd["undo"] = {"page": page, "sections": _copy.deepcopy(site["pages"][page])}
    await db().sites.update_one({"_id": site["_id"]}, {"$set": upd})


async def _fresh(user: dict, plan: str) -> dict:
    return await _state(user, plan, await _site(str(user["_id"])))


# ───────────────────────── the editor's endpoints ─────────────────────────
@router.get("/website")
async def get_site(user: dict = Depends(user_dep())):
    plan = await plans.require(db(), user, "website")
    return await _state(user, plan, await _site(str(user["_id"])))


class BuildIn(BaseModel):
    look: str = Field("", max_length=20)
    about_me: str = Field("", max_length=800)       # optional: anything the site should say, in their words
    replace: bool = False                           # write the whole site again (keeps address, contact, images)


@router.post("/website/build")
async def build(body: BuildIn, user: dict = Depends(user_dep())):
    uid = str(user["_id"])
    plan = await plans.require(db(), user, "website")
    existing = await _site(uid)
    if existing and not body.replace:
        raise _err(409, "exists", "You already have a site. Edit it below.")
    look = body.look or (existing or {}).get("look") or ""
    if look and look not in site_looks.LOOKS:
        raise _err(400, "bad_look", "Pick one of the looks.")
    if look and not site_looks.allowed(look, plan):
        raise _locked("l2", "The Editorial look is part of the L2 Mentorship.")

    async def work(plan: str):
        src = await site_ai.sources(db(), user, body.about_me)
        copy, seo = await site_ai.write_site(src)
        keys = M.PAGE_KEYS[:max(1, plans.cap("site_pages", plan))]
        chosen = look or site_looks.suggest(src["industry"], src["niche"], src["title"])
        now = utcnow()
        fields = {"look": chosen, "pages": M.pages_from(copy, keys), "copy": copy, "seo": seo,
                  "profile": {"name": src["name"] or "Consultant", "title": src["title"]},
                  "proposal": None, "undo": None, "updated_at": now}
        if existing:
            await db().sites.update_one({"_id": existing["_id"]}, {"$set": fields})
        else:
            doc = {"_id": M.new_id() + M.new_id(), "user_id": uid, "slug": await unique_slug(slugify(src["name"])),
                   "published": False, "published_at": None, "contact": {"email": "", "whatsapp": "", "calendly": ""},
                   "logo_id": None, "photo_id": None, "views": 0, "created_at": now, **fields}
            try:
                await db().sites.insert_one(doc)
            except Exception as e:  # noqa: BLE001 — a double tap: the first build won
                if "duplicate" in str(e).lower():
                    raise _err(409, "exists", "You already have a site. Edit it below.")
                raise
        await events.track(db(), "site_built", user_id=uid, props={"look": chosen, "pages": len(keys),
                                                                   "offer": bool(src["offer"]), "stories": len(src["stories"])})
        return await _fresh(user, plan)
    return await run_metered(db(), user, "site_ai", work, access="website")


class ContactIn(BaseModel):
    email: str = Field("", max_length=160)
    whatsapp: str = Field("", max_length=24)
    calendly: str = Field("", max_length=300)        # their booking link (Calendly or any https link)


class SettingsIn(BaseModel):
    slug: Optional[str] = Field(None, max_length=60)
    look: Optional[str] = Field(None, max_length=20)
    name: Optional[str] = Field(None, max_length=80)
    title: Optional[str] = Field(None, max_length=120)
    contact: Optional[ContactIn] = None
    seo_title: Optional[str] = Field(None, max_length=70)
    seo_description: Optional[str] = Field(None, max_length=160)


def _clean_contact(c: ContactIn) -> dict:
    email = c.email.strip()
    if email and not EMAIL_RX.match(email):
        raise _err(400, "bad_email", "Check the email address.")
    wa = c.whatsapp.strip()
    if wa and not R.wa_digits(wa):
        raise _err(400, "bad_phone", "Type the WhatsApp number with 10 digits, like 98765 43210.")
    link = c.calendly.strip()
    if link and (not re.match(r"^https://[^\s/]+\.[^\s/]+(/\S*)?$", link) or len(link) > 300):
        raise _err(400, "bad_link", "Paste your booking link starting with https://")
    return {"email": email, "whatsapp": wa, "calendly": link}


@router.put("/website/settings")
async def update_settings(body: SettingsIn, user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    upd: dict = {}
    if body.slug is not None and body.slug.strip().lower() != site["slug"]:
        s = body.slug.strip().lower()
        if not SLUG_RX.match(s) or "--" in s:
            raise _err(400, "bad_slug", "Use 3 to 40 small letters, numbers and dashes, like asha-mehta.")
        if s in RESERVED:
            raise _err(409, "slug_taken", "That address is taken. Try another.")
        if await db().sites.find_one({"slug": s, "_id": {"$ne": site["_id"]}}, {"_id": 1}):
            raise _err(409, "slug_taken", "That address is taken. Try another.")
        upd["slug"] = s
    if body.look is not None:
        if body.look not in site_looks.LOOKS:
            raise _err(400, "bad_look", "Pick one of the looks.")
        if not site_looks.allowed(body.look, plan):
            raise _locked("l2", "The Editorial look is part of the L2 Mentorship.")
        upd["look"] = body.look
    if body.name is not None:
        if len(text(body.name, 80)) < 2:
            raise _err(400, "bad_name", "Add your name as it should show on the site.")
        upd["profile.name"] = text(body.name, 80)
    if body.title is not None:
        upd["profile.title"] = text(body.title, 120)
    if body.contact is not None:
        upd["contact"] = _clean_contact(body.contact)
    if body.seo_title is not None:
        upd["seo.title"] = text(body.seo_title, 70)
    if body.seo_description is not None:
        upd["seo.description"] = text(body.seo_description, 160)
    if upd:
        upd["updated_at"] = utcnow()
        try:
            await db().sites.update_one({"_id": site["_id"]}, {"$set": upd})
        except Exception as e:  # noqa: BLE001
            if "duplicate" in str(e).lower():
                raise _err(409, "slug_taken", "That address is taken. Try another.")
            raise
        clear_host_cache()
    return await _fresh(user, plan)


class PublishIn(BaseModel):
    on: bool


@router.post("/website/publish")
async def publish(body: PublishIn, user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    upd = {"published": body.on, "updated_at": utcnow()}
    if body.on and not site.get("published_at"):
        upd["published_at"] = utcnow()
    await db().sites.update_one({"_id": site["_id"]}, {"$set": upd})
    await events.track(db(), "site_published", user_id=site["user_id"], props={"on": body.on})
    return await _fresh(user, plan)


# pages and sections
class PageIn(BaseModel):
    key: str = Field(..., max_length=20)


@router.post("/website/pages")
async def add_page(body: PageIn, user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    if body.key not in M.PAGE_KEYS:
        raise _err(400, "bad_page", "Pick one of the pages.")
    if body.key in site["pages"]:
        raise _err(409, "exists", "That page is already on your site.")
    cap = max(1, plans.cap("site_pages", plan))
    if len(site["pages"]) >= cap:
        await events.track(db(), "locked_hit", user_id=site["user_id"], props={"feature": "website_pages", "plan": plan})
        raise _locked("l1", f"More pages come with L1. Your plan has {cap} page{'s' if cap > 1 else ''}.")
    await db().sites.update_one({"_id": site["_id"]}, {"$set": {
        f"pages.{body.key}": M.page_sections(site.get("copy") or {}, body.key), "updated_at": utcnow()}})
    return await _fresh(user, plan)


@router.delete("/website/pages/{key}")
async def remove_page(key: str, user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    if key == "home":
        raise _err(400, "home", "Home stays. You can hide its sections instead.")
    if key not in site["pages"]:
        raise _err(404, "not_found", "That page isn't on your site.")
    await db().sites.update_one({"_id": site["_id"]}, {"$unset": {f"pages.{key}": ""}, "$set": {"updated_at": utcnow()}})
    return await _fresh(user, plan)


class OrderIn(BaseModel):
    ids: list[str] = Field(..., max_length=20)


@router.put("/website/pages/{key}/order")
async def reorder(key: str, body: OrderIn, user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    cur = site["pages"].get(key)
    if cur is None:
        raise _err(404, "not_found", "That page isn't on your site.")
    by_id = {s["id"]: s for s in cur}
    if sorted(body.ids) != sorted(by_id):
        raise _err(400, "bad_order", "The page changed. Reload and try again.")
    await _save_page(site, key, [by_id[i] for i in body.ids])
    return await _fresh(user, plan)


class AddSectionIn(BaseModel):
    type: str = Field(..., max_length=20)


@router.post("/website/pages/{key}/sections")
async def add_section(key: str, body: AddSectionIn, user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    cur = site["pages"].get(key)
    if cur is None:
        raise _err(404, "not_found", "That page isn't on your site.")
    if body.type not in M.SECTIONS:
        raise _err(400, "bad_type", "Pick one of the sections.")
    if len(cur) >= 12:
        raise _err(400, "too_many", "A page can have up to 12 sections.")
    await _save_page(site, key, cur + [M.section(body.type, (site.get("copy") or {}).get(body.type) or {})])
    return await _fresh(user, plan)


class SectionIn(BaseModel):
    page: str = Field("", max_length=20)
    data: Optional[dict] = None
    hidden: Optional[bool] = None


@router.put("/website/sections/{sid}")
async def edit_section(sid: str, body: SectionIn, user: dict = Depends(user_dep())):
    """Edit by hand (free) or show / hide."""
    plan, site = await _need(user)
    page, i = _find(site, sid, body.page)
    secs = _copy.deepcopy(site["pages"][page])
    if body.data is not None:
        secs[i]["data"] = M.normalize(secs[i]["type"], body.data)
        if secs[i]["type"] == "hero" and not secs[i]["data"]["headline"]:
            raise _err(400, "empty", "The top of the page needs a headline.")
    if body.hidden is not None:
        secs[i]["hidden"] = body.hidden
    await _save_page(site, page, secs)
    return await _fresh(user, plan)


@router.delete("/website/sections/{sid}")
async def delete_section(sid: str, page: str = "", user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    page, i = _find(site, sid, page)
    secs = _copy.deepcopy(site["pages"][page])
    secs.pop(i)
    await _save_page(site, page, secs)
    return await _fresh(user, plan)


class PromptIn(BaseModel):
    page: str = Field("", max_length=20)
    instruction: str = Field(..., min_length=3, max_length=500)


@router.post("/website/sections/{sid}/ai")
async def ai_edit(sid: str, body: PromptIn, user: dict = Depends(user_dep())):
    """Edit by prompt: the AI rewrites this one section. Nothing changes until the member presses Use this."""
    await plans.require(db(), user, "website")
    site = await _site(str(user["_id"]))
    if not site:
        raise _err(404, "no_site", "Build your site first.")
    page, i = _find(site, sid, body.page)
    sec = site["pages"][page][i]
    instruction = text(body.instruction, 500)

    async def work(plan: str):
        src = await site_ai.sources(db(), user)
        new, note = await site_ai.edit_section(sec["type"], sec["data"], instruction, src)
        return plan, new, note
    plan, new, note = await run_metered(db(), user, "site_ai", work, access="website")
    if new == sec["data"]:
        await plans.refund(db(), user, "site_ai", plan)        # nothing to change: the go is given back
        return {"changed": False, "refunded": True, "note": note or "Nothing on this section needed to change for that.",
                "proposal": None}
    proposal = {"page": page, "section_id": sid, "type": sec["type"], "before": sec["data"], "after": new,
                "note": note, "instruction": instruction, "at": utcnow()}
    await db().sites.update_one({"_id": site["_id"]}, {"$set": {"proposal": proposal}})
    await events.track(db(), "site_ai_edit", user_id=site["user_id"], props={"type": sec["type"]})
    return {"changed": True, "refunded": False, "note": note, "proposal": _proposal_out(proposal)}


@router.post("/website/proposal/apply")
async def apply_proposal(user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    p = site.get("proposal")
    if not p:
        raise _err(404, "no_proposal", "There's no AI change waiting.")
    page, i = _find(site, p["section_id"], p["page"])
    secs = _copy.deepcopy(site["pages"][page])
    secs[i]["data"] = M.normalize(secs[i]["type"], p["after"])
    await _save_page(site, page, secs, extra={"proposal": None})
    return await _fresh(user, plan)


@router.post("/website/proposal/discard")
async def discard_proposal(user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    await db().sites.update_one({"_id": site["_id"]}, {"$set": {"proposal": None}})
    return await _fresh(user, plan)


@router.post("/website/undo")
async def undo(user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    u = site.get("undo")
    if not u or u.get("page") not in M.PAGE_KEYS:
        raise _err(404, "no_undo", "Nothing to undo.")
    await db().sites.update_one({"_id": site["_id"]}, {"$set": {f"pages.{u['page']}": u["sections"], "undo": None,
                                                                "updated_at": utcnow()}})
    return await _fresh(user, plan)


# images
def _image_type(data: bytes) -> Optional[str]:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/website/images/{kind}")
async def upload_image(kind: Literal["logo", "photo"], file: UploadFile = File(...), user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    data = await file.read(IMAGE_MAX + 1)
    if len(data) > IMAGE_MAX:
        raise _err(413, "too_large", "Pick an image under 2 MB.")
    ctype = _image_type(data)
    if not data or not ctype or (file.content_type or ctype) not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        raise _err(400, "bad_type", "Use a PNG, JPG or WebP image.")
    bid = await media.save_blob(db(), user_id=site["user_id"], kind=f"site_{kind}", content_type=ctype, data=data,
                                name=text(file.filename, 120) or kind, public=True)
    await db().sites.update_one({"_id": site["_id"]}, {"$set": {f"{kind}_id": bid, "updated_at": utcnow()}})
    await media.delete_blob(db(), site.get(f"{kind}_id"))
    return await _fresh(user, plan)


@router.delete("/website/images/{kind}")
async def remove_image(kind: Literal["logo", "photo"], user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    await media.delete_blob(db(), site.get(f"{kind}_id"))
    await db().sites.update_one({"_id": site["_id"]}, {"$set": {f"{kind}_id": None, "updated_at": utcnow()}})
    return await _fresh(user, plan)


# own domain (L1/L2)
class DomainIn(BaseModel):
    domain: str = Field(..., min_length=3, max_length=253)


def _domain_locked() -> HTTPException:
    return _locked("l1", "Your own domain comes with L1. On your plan the site lives on its own link.")


@router.put("/website/domain")
async def set_domain(body: DomainIn, user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    if not plans.cap("custom_domain", plan):
        raise _domain_locked()
    d = clean_domain(body.domain)
    if d != site.get("domain"):
        if await db().sites.find_one({"domain": d, "_id": {"$ne": site["_id"]}}, {"_id": 1}):
            raise _err(409, "domain_taken", "That domain is already connected to another site.")
        await db().sites.update_one({"_id": site["_id"]}, {"$set": {"domain": d, "domain_status": "waiting",
                                                                    "domain_at": utcnow(), "updated_at": utcnow()}})
        clear_host_cache()
    return await _fresh(user, plan)


@router.delete("/website/domain")
async def remove_domain(user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    await db().sites.update_one({"_id": site["_id"]}, {"$unset": {"domain": "", "domain_status": "", "domain_at": ""},
                                                       "$set": {"updated_at": utcnow()}})
    clear_host_cache()
    return await _fresh(user, plan)


@router.post("/website/domain/check")
async def check_domain(user: dict = Depends(user_dep())):
    plan, site = await _need(user)
    if not plans.cap("custom_domain", plan):
        raise _domain_locked()
    if not site.get("domain"):
        raise _err(404, "no_domain", "Add your domain first.")
    target = R.app_host()
    found = await lookup_cname(site["domain"])
    ok = bool(target) and any(t == target or t.endswith("." + target) for t in found)
    status = "connected" if ok else "waiting"
    await db().sites.update_one({"_id": site["_id"]}, {"$set": {"domain_status": status, "domain_checked_at": utcnow()}})
    clear_host_cache()
    state = await _fresh(user, plan)
    return {**state, "check": {"ok": ok, "found": found[:3]}}


# leads
@router.get("/website/leads")
async def leads(user: dict = Depends(user_dep())):
    await plans.require(db(), user, "website")
    uid = str(user["_id"])
    rows = [{"id": x["_id"], "name": x.get("name"), "email": x.get("email"), "phone": x.get("phone"),
             "company": x.get("company"), "message": x.get("message"), "page": x.get("page"), "read": bool(x.get("read")),
             "at": iso(x.get("at"))}
            async for x in db().site_leads.find({"user_id": uid}).sort("at", -1).limit(100)]
    await db().site_leads.update_many({"user_id": uid, "read": False}, {"$set": {"read": True}})
    return {"items": rows}


# ───────────────────────── the contact form on the public site ─────────────────────────
def _client_ip(request: Request) -> str:
    from accounts.routes import client_ip
    return client_ip(request)


async def _over(key: str, limit: int, window: int) -> bool:
    bucket = int(time.time() // window)
    doc = await db().site_rate.find_one_and_update(
        {"_id": f"{key}:{bucket}"}, {"$inc": {"n": 1}, "$setOnInsert": {"purge_at": utcnow() + timedelta(seconds=window * 2)}},
        upsert=True, return_document=ReturnDocument.AFTER)
    return int((doc or {}).get("n") or 0) > limit


def _back(request: Request, slug: str, page: str, q: str) -> RedirectResponse:
    base = "" if request.scope.get("site_base") == "" else f"/s/{slug}"
    path = (base or "/") if page == "home" else f"{base}/{page}"
    return RedirectResponse(f"{path}?{q}#contact", status_code=303)


async def _owner_plan(site: dict) -> Optional[str]:
    owner = await db().users.find_one({"_id": oid(site["user_id"]) or site["user_id"]})
    if not owner or owner.get("status") == "revoked":
        return None
    return (await plans.effective_plan(db(), owner))["plan"]


@router.post("/website/public/{slug}/leads")
async def public_lead(slug: str, request: Request):
    wants_json = "application/json" in (request.headers.get("content-type") or "")
    try:
        data = await request.json() if wants_json else dict(await request.form())
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict):
        data = {}
    page = str(data.get("page") or "home")
    page = page if page in M.PAGE_KEYS else "home"
    slug = slug.lower()[:60]
    if str(data.get("website") or "").strip():             # honeypot: a person never fills the hidden field
        return JSONResponse({"ok": True}) if wants_json else _back(request, slug, page, "sent=1")
    site = await db().sites.find_one({"slug": slug})
    plan = await _owner_plan(site) if site else None
    if not site or not site.get("published") or not plan or not plans.plan_allows(plan, "website"):
        if wants_json:
            raise _err(404, "not_found", "This site isn't live.")
        return HTMLResponse(R.not_found_html(), status_code=404)
    name = text(data.get("name"), 80)
    email = text(data.get("email"), 160)
    phone = re.sub(r"[^\d+]", "", str(data.get("phone") or ""))[:16]
    if len(name) < 2 or (not EMAIL_RX.match(email) and len(re.sub(r"\D", "", phone)) < 10):
        if wants_json:
            raise _err(400, "details", R.FORM_ERRORS["details"])
        return _back(request, slug, page, "err=details")
    ip = _client_ip(request)
    ip_hash = hashlib.sha256(f"{ip}|site-leads".encode()).hexdigest()[:20]
    if await _over(f"lead:{site['_id']}:{ip_hash}", *LEADS_PER_IP) or await _over(f"lead-site:{site['_id']}", *LEADS_PER_SITE):
        if wants_json:
            raise _err(429, "busy", R.FORM_ERRORS["busy"])
        return _back(request, slug, page, "err=busy")
    lead = {"_id": M.new_id() + M.new_id(), "site_id": site["_id"], "user_id": site["user_id"], "name": name,
            "email": email if EMAIL_RX.match(email) else "", "phone": phone, "company": text(data.get("company"), 120),
            "message": str(data.get("message") or "").strip()[:2000], "page": page, "ip_hash": ip_hash, "at": utcnow(),
            "read": False}
    await db().site_leads.insert_one(lead)
    who = name + (f" from {lead['company']}" if lead["company"] else "")
    reach = " · ".join(x for x in (lead["email"], lead["phone"]) if x)
    try:
        await notify_service.alert(db(), site["user_id"], "site_lead", "New message from your website",
                                   f"{who}: {text(lead['message'], 300) or '(no message)'} ({reach})", link="/app/website")
    except Exception:  # noqa: BLE001 — the lead is saved; an alert problem must not lose it
        log.warning("site lead alert failed", exc_info=True)
    await events.track(db(), "site_lead", user_id=site["user_id"], props={"page": page})
    return JSONResponse({"ok": True}) if wants_json else _back(request, slug, page, "sent=1")


# ───────────────────────── public pages (outside /api) ─────────────────────────
async def _serve(request: Request, slug: str, page: str) -> Response:
    site = await db().sites.find_one({"slug": (slug or "").lower()[:60]})
    if not site:
        return HTMLResponse(R.not_found_html(), status_code=404)
    plan = await _owner_plan(site)
    preview = False
    if request.query_params.get("preview") == "1":
        viewer = await optional_user(request)
        preview = bool(viewer) and str(viewer["_id"]) == site["user_id"]
    if not preview and (not plan or not site.get("published") or not plans.plan_allows(plan, "website")):
        return HTMLResponse(R.not_found_html(), status_code=404)
    plan = plan or "free"
    if page not in (R.page_keys_for(site, plan) if plans.plan_allows(plan, "website") else ["home"]):
        return HTMLResponse(R.not_found_html(), status_code=404)
    if not preview and request.method == "GET":
        await db().sites.update_one({"_id": site["_id"]}, {"$inc": {"views": 1}})
    base = "" if request.scope.get("site_base") == "" else f"/s/{site['slug']}"
    html = R.render(site, page, plan=plan if plans.plan_allows(plan, "website") else "member", preview=preview, base=base,
                    sent=request.query_params.get("sent") == "1", err=request.query_params.get("err", ""))
    headers = {"Cache-Control": "no-store" if preview else "no-cache"}
    if preview:
        headers["X-Robots-Tag"] = "noindex"
    return HTMLResponse(html, headers=headers)


@public_router.api_route("/s/{slug}", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
async def site_home(slug: str, request: Request):
    return await _serve(request, slug, "home")


@public_router.get("/s/{slug}/img/{kind}", include_in_schema=False)
async def site_image(slug: str, kind: str):
    site = await db().sites.find_one({"slug": (slug or "").lower()[:60]}, {"logo_id": 1, "photo_id": 1})
    bid = (site or {}).get(f"{kind}_id") if kind in ("logo", "photo") else None
    b = await media.get_blob(db(), bid) if bid else None
    if not b:
        return Response(status_code=404)
    return Response(bytes(b["data"]), media_type=b.get("content_type") or "image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@public_router.api_route("/s/{slug}/{page}", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
async def site_page(slug: str, page: str, request: Request):
    if page == "home":
        return RedirectResponse(f"/s/{slug}", status_code=301)
    return await _serve(request, slug, page)


# ───────────────────────── admin: own domains to set up at the host ─────────────────────────
@router.get("/admin/website/domains")
async def admin_domains(_: dict = Depends(admin_dep())):
    rows = [{"site_id": s["_id"], "user_id": s["user_id"], "slug": s["slug"], "domain": s.get("domain"),
             "domain_status": s.get("domain_status"), "published": bool(s.get("published")), "at": iso(s.get("domain_at"))}
            async for s in db().sites.find({"domain": {"$exists": True}}).sort("domain_at", -1).limit(500)]
    return {"items": rows, "target": R.app_host()}


class DomainStatusIn(BaseModel):
    status: Literal["waiting", "connected"]


@router.post("/admin/website/domains/{site_id}")
async def admin_domain_status(site_id: str, body: DomainStatusIn, _: dict = Depends(admin_dep())):
    r = await db().sites.update_one({"_id": site_id, "domain": {"$exists": True}}, {"$set": {"domain_status": body.status}})
    if not r.matched_count:
        raise _err(404, "not_found", "No site with a domain there.")
    clear_host_cache()
    return {"ok": True}


# ───────────────────────── serving a site on its own address ─────────────────────────
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "testserver", "::1"}
HOST_TTL = 60.0
_HOSTS: dict[str, tuple[float, Optional[str]]] = {}


def clear_host_cache() -> None:
    _HOSTS.clear()


async def resolve_host(host: str) -> Optional[str]:
    """None: not a member site's address (the hub answers). A slug: serve that site. "": a site address with nothing
    to serve (plan no longer includes an own domain) → 404."""
    if not host or host in LOCAL_HOSTS or host == R.app_host():
        return None
    sd = R.sites_domain()
    if sd and host.endswith("." + sd):
        label = host[: -len(sd) - 1]
        return label if SLUG_RX.match(label) and label not in RESERVED else None
    hit = _HOSTS.get(host)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    value: Optional[str] = None
    site = await db().sites.find_one({"domain": host}, {"slug": 1, "user_id": 1})
    if site:
        plan = await _owner_plan(site)
        value = site["slug"] if plan and plans.cap("custom_domain", plan) else ""
    if len(_HOSTS) > 5000:
        _HOSTS.clear()
    _HOSTS[host] = (time.monotonic() + HOST_TTL, value)
    return value


def site_path(slug: str, path: str) -> Optional[str]:
    """The hub path for a request on a site's own address; None for anything a site doesn't have."""
    p = (path or "/").rstrip("/") or "/"
    if p == "/":
        return f"/s/{slug}"
    seg = p.lstrip("/")
    if seg in M.PAGE_KEYS and seg != "home":
        return f"/s/{slug}/{seg}"
    if seg in ("img/logo", "img/photo"):
        return f"/s/{slug}/{seg}"
    if seg == f"api/website/public/{slug}/leads":
        return p
    return None


class SiteHostMiddleware:
    """Pure ASGI: requests whose Host is a member site's address are answered by that site only."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        raw = b""
        for k, v in scope.get("headers") or []:
            if k == b"host":
                raw = v
                break
        host = raw.decode("latin-1").strip().lower().rstrip(".")
        host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        try:
            slug = await resolve_host(host)
        except Exception:  # noqa: BLE001 — never take the hub down over a lookup
            log.warning("site host lookup failed for %s", host, exc_info=True)
            slug = None
        if slug is None:
            return await self.app(scope, receive, send)
        new = site_path(slug, scope.get("path") or "/") if slug else None
        if not new:
            return await HTMLResponse(R.not_found_html(), status_code=404)(scope, receive, send)
        scope = dict(scope)
        scope["path"] = new
        scope["raw_path"] = new.encode()
        scope["site_base"] = ""
        scope["site_host"] = host
        return await self.app(scope, receive, send)


def install_domain_middleware(app) -> None:
    """Called in server.create_app right after `app = FastAPI(...)`. Safe to call twice (second call does nothing)."""
    if getattr(app.state, "site_host_middleware", False):
        return
    app.state.site_host_middleware = True
    app.add_middleware(SiteHostMiddleware)
