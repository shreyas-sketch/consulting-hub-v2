"""Recordings and workbooks (L1).

library_items {_id, title, kind video|workbook|link, url, description, plan_min l1|l2, section, order, published,
               file_id?, file_name?, file_size?, created_at, updated_at}

Members see published items their plan opens, grouped by section. YouTube links play in an embedded
youtube-nocookie player and Vimeo links in Vimeo's player; other links open in a new tab.
Workbook PDFs (≤ 15 MB) uploaded by the team are stored with media.save_blob (not public) and served through
GET /library/{id}/file after a plan check (the shared /api/blobs route only serves a file to its owner).
"""
from __future__ import annotations

import re
import uuid
from typing import Literal, Optional
from urllib.parse import parse_qs, quote, urlparse

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

import indexes
import media
import plans
from core.deps import admin_dep, user_dep
from core.errors import AppError, Locked, error
from growth.clock import utcnow
from state import db
from util import iso

router = APIRouter(tags=["library"])
member = APIRouter(prefix="/library")
admin = APIRouter(prefix="/admin/library")
Admin = Depends(admin_dep())

MAX_PDF = 15 * 1024 * 1024
URL_RX = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.I)
YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

indexes.register("library_items", [("published", 1), ("section", 1), ("order", 1)])


def _err(status: int, code: str, msg: str) -> AppError:
    return error(status, code, msg)


def embed_of(url: str) -> Optional[dict]:
    """YouTube / Vimeo page link → player URL. Anything else → None (opens in a new tab)."""
    try:
        p = urlparse((url or "").strip())
    except ValueError:
        return None
    host = (p.hostname or "").lower()
    for pre in ("www.", "m."):
        host = host.removeprefix(pre)
    parts = [x for x in p.path.split("/") if x]
    qs = parse_qs(p.query)
    vid = None
    if host == "youtu.be" and parts:
        vid = parts[0]
    elif host in ("youtube.com", "youtube-nocookie.com", "music.youtube.com"):
        if parts[:1] == ["watch"]:
            vid = (qs.get("v") or [None])[0]
        elif len(parts) >= 2 and parts[0] in ("embed", "shorts", "live", "v"):
            vid = parts[1]
    if vid and YT_ID.match(vid):
        return {"provider": "youtube", "src": f"https://www.youtube-nocookie.com/embed/{vid}?rel=0"}
    if host in ("vimeo.com", "player.vimeo.com"):
        nums = [i for i, x in enumerate(parts) if x.isdigit()]
        if nums:
            i = nums[0]
            h = (qs.get("h") or [None])[0]
            if not h and i + 1 < len(parts):
                h = parts[i + 1]
            h = h if h and re.fullmatch(r"[0-9a-f]{6,20}", h) else None
            return {"provider": "vimeo", "src": f"https://player.vimeo.com/video/{parts[i]}" + (f"?h={h}" if h else "")}
    return None


def _rank(p: str) -> int:
    return plans.RANK.get(p, plans.RANK["l2"])


def _out(it: dict) -> dict:
    url = it.get("url") or ""
    return {"id": it["_id"], "title": it["title"], "kind": it.get("kind", "video"), "description": it.get("description") or "",
            "section": it.get("section") or "General", "plan_min": it.get("plan_min", "l1"), "order": int(it.get("order") or 0),
            "url": url, "embed": embed_of(url) if url and it.get("kind") != "workbook" else None,
            "file_url": f"/api/library/{it['_id']}/file" if it.get("file_id") else None, "file_name": it.get("file_name")}


# ------------------------------------------------------------------ member ----
@member.get("")
async def listing(user: dict = Depends(user_dep())):
    d = db()
    plan = await plans.require(d, user, "recordings")
    allowed = [p for p in ("l1", "l2") if plans.RANK[plan] >= plans.RANK[p]]
    sections: dict[str, list] = {}
    async for it in d.library_items.find({"published": True, "plan_min": {"$in": allowed}}).sort([("order", 1), ("title", 1)]):
        if not (it.get("url") or it.get("file_id")):
            continue
        sections.setdefault(it.get("section") or "General", []).append(_out(it))
    hidden = 0 if "l2" in allowed else await d.library_items.count_documents({"published": True, "plan_min": "l2"})
    return {"sections": [{"name": k, "items": v} for k, v in sections.items()],
            "count": sum(len(v) for v in sections.values()), "l2_hidden": hidden}


@member.get("/{item_id}/file")
async def file(item_id: str, user: dict = Depends(user_dep())):
    d = db()
    plan = await plans.require(d, user, "recordings")
    it = await d.library_items.find_one({"_id": item_id})
    if not it or not it.get("file_id") or (not it.get("published") and user.get("role") != "admin"):
        raise _err(404, "not_found", "File not found.")
    if plans.RANK[plan] < _rank(it.get("plan_min", "l1")):
        raise Locked("This workbook is part of the L2 Mentorship.", feature="recordings", plan_needed="l2")
    b = await media.get_blob(d, it["file_id"])
    if not b:
        raise _err(404, "not_found", "File not found.")
    name = it.get("file_name") or "workbook.pdf"
    return Response(bytes(b["data"]), media_type=b.get("content_type") or "application/pdf",
                    headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}",
                             "Cache-Control": "private, max-age=3600"})


# ------------------------------------------------------------------ admin ----
class ItemIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=140)
    kind: Literal["video", "workbook", "link"] = "video"
    url: str = Field("", max_length=500)
    description: str = Field("", max_length=1000)
    plan_min: Literal["l1", "l2"] = "l1"
    section: str = Field("General", max_length=60)
    order: int = Field(0, ge=0, le=10000)
    published: bool = True


def _fields(body: ItemIn) -> dict:
    url = body.url.strip()
    if url and not URL_RX.match(url):
        raise _err(400, "bad_link", "The link must start with https://")
    if body.kind != "workbook" and not url:
        raise _err(400, "need_link", "Add the link for this video or page.")
    return {"title": " ".join(body.title.split()), "kind": body.kind, "url": url, "description": body.description.strip(),
            "plan_min": body.plan_min, "section": " ".join(body.section.split()) or "General", "order": body.order,
            "published": body.published}


def _admin_row(it: dict) -> dict:
    return {**_out(it), "published": bool(it.get("published")), "file_size": it.get("file_size"),
            "created_at": iso(it.get("created_at")), "updated_at": iso(it.get("updated_at"))}


async def _item(item_id: str) -> dict:
    it = await db().library_items.find_one({"_id": item_id})
    if not it:
        raise _err(404, "not_found", "Item not found.")
    return it


@admin.get("")
async def admin_list(_: dict = Admin):
    return {"items": [_admin_row(it) async for it in db().library_items.find({}).sort([("section", 1), ("order", 1), ("title", 1)])]}


@admin.post("")
async def admin_add(body: ItemIn, _: dict = Admin):
    now = utcnow()
    doc = {"_id": uuid.uuid4().hex, **_fields(body), "created_at": now, "updated_at": now}
    await db().library_items.insert_one(doc)
    return _admin_row(doc)


@admin.put("/{item_id}")
async def admin_edit(item_id: str, body: ItemIn, _: dict = Admin):
    await _item(item_id)
    await db().library_items.update_one({"_id": item_id}, {"$set": {**_fields(body), "updated_at": utcnow()}})
    return _admin_row(await _item(item_id))


@admin.delete("/{item_id}")
async def admin_delete(item_id: str, _: dict = Admin):
    it = await _item(item_id)
    await db().library_items.delete_one({"_id": item_id})
    await media.delete_blob(db(), it.get("file_id"))
    return {"ok": True}


@admin.post("/{item_id}/file")
async def admin_upload(item_id: str, file: UploadFile = File(...), _: dict = Admin):
    """Attach a workbook PDF (≤ 15 MB). Replaces the item's earlier file."""
    it = await _item(item_id)
    name = (file.filename or "workbook.pdf").strip()
    if not name.lower().endswith(".pdf"):
        raise _err(400, "bad_type", "Upload a PDF file.")
    raw = await file.read(MAX_PDF + 1)
    if len(raw) > MAX_PDF:
        raise _err(400, "too_large", "PDFs up to 15 MB.")
    if not raw.startswith(b"%PDF"):
        raise _err(400, "bad_type", "That file is not a PDF.")
    try:
        bid = await media.save_blob(db(), user_id=None, kind="workbook", content_type="application/pdf", data=raw,
                                    name=name, public=False)
    except media.TooLarge:
        raise _err(400, "too_large", "PDFs up to 15 MB.")
    await db().library_items.update_one({"_id": item_id}, {"$set": {
        "file_id": bid, "file_name": name[:200], "file_size": len(raw), "updated_at": utcnow()}})
    if it.get("file_id"):
        await media.delete_blob(db(), it["file_id"])
    return _admin_row(await _item(item_id))


@admin.delete("/{item_id}/file")
async def admin_remove_file(item_id: str, _: dict = Admin):
    it = await _item(item_id)
    await db().library_items.update_one({"_id": item_id}, {"$unset": {"file_id": "", "file_name": "", "file_size": ""},
                                                           "$set": {"updated_at": utcnow()}})
    await media.delete_blob(db(), it.get("file_id"))
    return _admin_row(await _item(item_id))


router.include_router(member)
router.include_router(admin)
