"""Text to speech (Listen mode, Session Recap audio, Insight Pack audio).

Vendor: OpenAI audio API — POST https://api.openai.com/v1/audio/speech {model, voice, input, response_format: mp3}.
Input is limited per call, so long text is split at sentence ends and the MP3 parts are joined (MP3 frames concatenate).
Env: OPENAI_API_KEY, TTS_MODEL (default gpt-4o-mini-tts), TTS_VOICE (default alloy).
Fake mode returns one second of silent WAV so tests and QA need no network.

    data, content_type = await speak(text)
"""
from __future__ import annotations

import io
import os
import re
import wave

import httpx

from core.vendors import vendor_mode

URL = "https://api.openai.com/v1/audio/speech"
CHUNK = 3500


class TTSError(RuntimeError):
    pass


def mode() -> str:
    return vendor_mode("openai")


def _silent_wav(seconds: float = 1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buf.getvalue()


def split_text(text: str, n: int = CHUNK) -> list[str]:
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", " ".join(text.split())):
        if len(cur) + len(sent) + 1 > n and cur:
            parts.append(cur)
            cur = ""
        cur = f"{cur} {sent}".strip()
        while len(cur) > n:
            parts.append(cur[:n])
            cur = cur[n:]
    if cur:
        parts.append(cur)
    return parts


async def speak(text: str, *, client: httpx.AsyncClient | None = None) -> tuple[bytes, str]:
    m = mode()
    if m == "fake":
        return _silent_wav(), "audio/wav"
    if m == "off":
        raise TTSError("Audio is not set up yet (OPENAI_API_KEY).")
    c = client or httpx.AsyncClient(timeout=90)
    out = b""
    try:
        for part in split_text(text):
            r = await c.post(URL, headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                             json={"model": os.environ.get("TTS_MODEL", "gpt-4o-mini-tts"),
                                   "voice": os.environ.get("TTS_VOICE", "alloy"), "input": part, "response_format": "mp3"})
            if r.status_code >= 400:
                raise TTSError(f"TTS HTTP {r.status_code}")
            out += r.content
    except httpx.HTTPError as e:
        raise TTSError(f"TTS failed: {type(e).__name__}") from e
    finally:
        if client is None:
            await c.aclose()
    return out, "audio/mpeg"
