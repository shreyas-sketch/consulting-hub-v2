"""Small file store in Mongo (audio, uploads, images). One document per file, up to MAX_BYTES.

    blobs {_id, user_id, kind, name, content_type, size, data: bytes, public: bool, at}

save_blob() returns the id; GET /api/blobs/{id} serves it to its owner, to admins, or to anyone when public=True
(website images, shared audio such as session recaps). Large videos are never stored: members keep those on their phone.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Request, Response

import state
from core.errors import NotFound, Unauthorized
from growth.clock import utcnow

MAX_BYTES = 15 * 1024 * 1024
router = APIRouter(tags=["files"])


class TooLarge(ValueError):
    pass


async def save_blob(db, *, user_id: Optional[str], kind: str, content_type: str, data: bytes, name: str = "",
                    public: bool = False) -> str:
    if len(data) > MAX_BYTES:
        raise TooLarge(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    _id = uuid.uuid4().hex
    await db.blobs.insert_one({"_id": _id, "user_id": user_id, "kind": kind, "name": name[:200],
                               "content_type": content_type, "size": len(data), "data": data, "public": public,
                               "at": utcnow()})
    return _id


async def get_blob(db, blob_id: str) -> Optional[dict]:
    return await db.blobs.find_one({"_id": blob_id})


async def delete_blob(db, blob_id: Optional[str]) -> None:
    if blob_id:
        await db.blobs.delete_one({"_id": blob_id})


def blob_url(blob_id: Optional[str]) -> Optional[str]:
    return f"/api/blobs/{blob_id}" if blob_id else None


@router.get("/blobs/{blob_id}")
async def serve(blob_id: str, request: Request):
    b = await get_blob(state.db(), blob_id)
    if not b:
        raise NotFound("File not found.")
    if not b.get("public"):
        try:
            from auth import get_current_user
            user = await get_current_user(request)
        except Exception:  # noqa: BLE001
            raise Unauthorized("Log in to open this file.", code="unauthorized")
        if (user.get("role") != "admin") and str(user["_id"]) != b.get("user_id"):
            raise NotFound("File not found.")
    return Response(bytes(b["data"]), media_type=b.get("content_type") or "application/octet-stream",
                    headers={"Cache-Control": "private, max-age=3600"})
