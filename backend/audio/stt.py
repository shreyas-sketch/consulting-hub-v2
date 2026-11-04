"""Speech to text (Career Story Bank voice notes, Pitch Practice). English.

Vendor: OpenAI audio API — POST https://api.openai.com/v1/audio/transcriptions (multipart: file, model).
Env: OPENAI_API_KEY, STT_MODEL (default gpt-4o-mini-transcribe). Fake mode returns `fake_text` (or a fixed sentence).

    text = await transcribe(data, filename="note.webm", content_type="audio/webm")
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from core.vendors import vendor_mode

URL = "https://api.openai.com/v1/audio/transcriptions"
MAX_BYTES = 24 * 1024 * 1024
FAKE_TEXT = ("In my last role I took over a plant where deliveries were late every week. I sat with the shift leads, "
             "found that one machine was down most afternoons, and we fixed the maintenance plan. In three months "
             "on-time delivery went from seventy to ninety-four percent.")


class STTError(RuntimeError):
    pass


def mode() -> str:
    return vendor_mode("openai")


async def transcribe(data: bytes, *, filename: str = "audio.webm", content_type: str = "audio/webm",
                     fake_text: Optional[str] = None, client: httpx.AsyncClient | None = None) -> str:
    if len(data) > MAX_BYTES:
        raise STTError("Recording is too long. Keep it under about 10 minutes.")
    m = mode()
    if m == "fake":
        return fake_text or FAKE_TEXT
    if m == "off":
        raise STTError("Voice notes are not set up yet (OPENAI_API_KEY).")
    c = client or httpx.AsyncClient(timeout=120)
    try:
        r = await c.post(URL, headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                         data={"model": os.environ.get("STT_MODEL", "gpt-4o-mini-transcribe"), "language": "en"},
                         files={"file": (filename, data, content_type)})
        if r.status_code >= 400:
            raise STTError(f"Transcription HTTP {r.status_code}")
        return " ".join(str((r.json() or {}).get("text") or "").split())
    except httpx.HTTPError as e:
        raise STTError(f"Transcription failed: {type(e).__name__}") from e
    finally:
        if client is None:
            await c.aclose()
