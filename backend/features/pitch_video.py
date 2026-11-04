"""Video engine for Pitch Practice (same approach as the Leadership hub's Confidence Coach).

Vendor "gemini" (core.vendors.vendor_mode). Env: GEMINI_API_KEY, GEMINI_MODEL (default gemini-3.8-flash),
GEMINI_POLL_MAX_S (default 300). Written against the public Gemini API docs (ai.google.dev, v1beta REST):

  1. Files API resumable upload
       POST https://generativelanguage.googleapis.com/upload/v1beta/files
            X-Goog-Upload-Protocol: resumable, X-Goog-Upload-Command: start,
            X-Goog-Upload-Header-Content-Length, X-Goog-Upload-Header-Content-Type, body {"file": {"display_name"}}
       → upload URL in the `x-goog-upload-url` response header
       POST <upload url>  X-Goog-Upload-Command: "upload, finalize", X-Goog-Upload-Offset: 0, the bytes
       → {"file": {"name": "files/…", "uri": "…", "state": "PROCESSING" | "ACTIVE" | "FAILED"}}
  2. Poll GET /v1beta/files/… until state is ACTIVE (FAILED → error). The ACTIVE File carries
     videoMetadata.videoDuration ("123.4s", a google.protobuf.Duration string): when the caller passes max_seconds,
     a longer clip raises TooLong before any analysis (and the file is still deleted).
  3. POST /v1beta/models/{model}:generateContent with the file (fileData {mimeType, fileUri}), the prompt, a system
     instruction and generationConfig.responseMimeType "application/json"; text from candidates[0].content.parts.
  4. DELETE /v1beta/files/… right after (best effort; the vendor also drops files after 48 hours).

The video is streamed from our temp file in chunks (never read whole into memory). Fake mode returns `fake()` so tests
and QA run with no key and no network. Errors raise VideoError with a vendor-neutral message; callers never show the
vendor's own error text to a member.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, AsyncIterator, Callable, Optional

import httpx

from core.vendors import vendor_mode

log = logging.getLogger("pitch_video")

BASE = "https://generativelanguage.googleapis.com"
DEFAULT_MODEL = "gemini-3.8-flash"
CHUNK = 1024 * 1024


class VideoError(RuntimeError):
    """The video engine could not analyse the clip (network, quota, processing failed, empty answer)."""


class BadOutput(VideoError):
    """The engine answered, but not with one JSON object."""


class TooLong(VideoError):
    """The engine measured the clip as longer than the caller allows."""

    def __init__(self, seconds: float):
        super().__init__(f"clip is {seconds:.1f} s")
        self.seconds = seconds


def video_seconds(f: dict) -> Optional[float]:
    """Length of an ACTIVE File from its videoMetadata.videoDuration ("123.4s"); None when not reported."""
    vm = f.get("videoMetadata") or (f.get("metadata") or {}).get("videoMetadata") or {}
    v = vm.get("videoDuration") if isinstance(vm, dict) else None
    try:
        if isinstance(v, dict):                                 # {"seconds": "123", "nanos": 400000000}
            secs = float(v.get("seconds") or 0) + float(v.get("nanos") or 0) / 1e9
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            secs = float(v)
        elif isinstance(v, str) and v.strip():
            secs = float(v.strip().rstrip("s"))
        else:
            return None
    except (TypeError, ValueError):
        return None
    return secs if secs > 0 else None


def mode() -> str:
    return vendor_mode("gemini")


def model_name() -> str:
    return (os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL).strip()


async def _chunks(path: str) -> AsyncIterator[bytes]:
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            yield b


def parse_json(text: str) -> dict:
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < a:
        raise BadOutput("no JSON object in the answer")
    try:
        out = json.loads(t[a:b + 1])
    except json.JSONDecodeError as e:
        raise BadOutput(f"invalid JSON: {e.msg}") from e
    if not isinstance(out, dict):
        raise BadOutput("JSON is not an object")
    return out


async def _upload(c: httpx.AsyncClient, key: str, path: str, mime: str) -> dict:
    size = os.path.getsize(path)
    r = await c.post(f"{BASE}/upload/v1beta/files", json={"file": {"display_name": "practice-take"}}, headers={
        "x-goog-api-key": key, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(size), "X-Goog-Upload-Header-Content-Type": mime,
        "Content-Type": "application/json"})
    url = r.headers.get("x-goog-upload-url")
    if r.status_code >= 400 or not url:
        raise VideoError(f"upload start HTTP {r.status_code}")
    r = await c.post(url, content=_chunks(path), headers={
        "Content-Length": str(size), "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"})
    if r.status_code >= 400:
        raise VideoError(f"upload HTTP {r.status_code}")
    f = (r.json() or {}).get("file") or {}
    if not f.get("name") or not f.get("uri"):
        raise VideoError("upload: no file name")
    return f


async def _wait_active(c: httpx.AsyncClient, key: str, f: dict, poll_s: float, max_wait_s: float) -> dict:
    deadline = time.monotonic() + max_wait_s
    while (f.get("state") or "PROCESSING") != "ACTIVE":
        if f.get("state") == "FAILED":
            raise VideoError("processing failed")
        if time.monotonic() > deadline:
            raise VideoError("processing took too long")
        await asyncio.sleep(poll_s)
        r = await c.get(f"{BASE}/v1beta/{f['name']}", headers={"x-goog-api-key": key})
        if r.status_code >= 400:
            raise VideoError(f"file status HTTP {r.status_code}")
        f = {**f, **(r.json() or {})}
    return f


async def _generate(c: httpx.AsyncClient, key: str, f: dict, mime: str, system: str, prompt: str) -> str:
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"fileData": {"mimeType": f.get("mimeType") or mime, "fileUri": f["uri"]}},
                                                    {"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4, "maxOutputTokens": 16384}}
    url = f"{BASE}/v1beta/models/{model_name()}:generateContent"
    for attempt in range(2):
        r = await c.post(url, json=body, headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        if r.status_code in (429, 500, 503) and attempt == 0:
            await asyncio.sleep(4)
            continue
        if r.status_code >= 400:
            raise VideoError(f"generate HTTP {r.status_code}")
        data = r.json() or {}
        cands = data.get("candidates") or []
        if not cands:
            raise VideoError(f"no answer ({(data.get('promptFeedback') or {}).get('blockReason') or 'empty'})")
        parts = ((cands[0].get("content") or {}).get("parts")) or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
        if not text.strip():
            raise VideoError(f"empty answer ({cands[0].get('finishReason') or 'unknown'})")
        return text
    raise VideoError("generate failed")


async def _delete(c: httpx.AsyncClient, key: str, name: Optional[str]) -> None:
    if not name:
        return
    try:
        await c.delete(f"{BASE}/v1beta/{name}", headers={"x-goog-api-key": key})
    except Exception as e:  # noqa: BLE001 — best effort; the vendor drops files after 48 hours anyway
        log.info("video delete failed: %s", type(e).__name__)


async def analyse(path: str, *, mime: str, system: str, prompt: str, fake: Callable[[], Any],
                  client: Optional[httpx.AsyncClient] = None, poll_s: float = 3.0,
                  max_seconds: Optional[float] = None, info: Optional[dict] = None) -> dict:
    """Upload → wait until ACTIVE → check the engine's own duration → generate JSON → delete.
    Returns the parsed JSON object. `info["seconds"]` gets the engine's measured length (None when not reported).
    A clip longer than `max_seconds` raises TooLong (the file is deleted all the same)."""
    m = mode()
    if m == "fake":
        return fake()
    if m == "off":
        raise VideoError("video analysis is not configured")
    key = os.environ["GEMINI_API_KEY"]
    max_wait = float(os.environ.get("GEMINI_POLL_MAX_S", "300") or 300)
    c = client or httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=20.0))
    name = None
    try:
        f = await _upload(c, key, path, mime)
        name = f["name"]
        f = await _wait_active(c, key, f, poll_s, max_wait)
        secs = video_seconds(f)
        if info is not None:
            info["seconds"] = secs
        if max_seconds is not None and secs is not None and secs > max_seconds:
            raise TooLong(secs)
        return parse_json(await _generate(c, key, f, mime, system, prompt))
    except httpx.HTTPError as e:
        raise VideoError(f"network: {type(e).__name__}") from e
    finally:
        await _delete(c, key, name)
        if client is None:
            await c.aclose()
