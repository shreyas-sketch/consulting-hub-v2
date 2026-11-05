"""Text to speech (Listen mode, Session Recap audio, Insight Pack audio, Notebook audio overview). English only.

Vendor switch "gemini" (core.vendors; GEMINI_MODE), the same key as Pitch Practice video analysis.
Google Gemini API, Interactions endpoint, exactly as in the speech generation guide (read 4 Nov 2026):
https://ai.google.dev/gemini-api/docs/speech-generation

    POST https://generativelanguage.googleapis.com/v1beta/interactions        header x-goog-api-key
    {"model": "gemini-3.8-flash-tts", "store": false,
     "input": [{"type": "user_input", "content": [{"type": "text", "text": "<words to read>",
                "annotations": [{"type": "speech_metadata", "style": "<delivery>"}]}]}],
     "response_format": {"type": "audio"},
     "generation_config": {"speech_config": [{"voice": "Iapetus"}]}}
    → steps[] with type "model_output" → content[] with type "audio" → data (base64; the guide takes the last one).

Unary output is WAV (RIFF header, 24 kHz, mono, 16-bit PCM). Headerless audio/l16 (little-endian, sample_rate from
the item, else 24 kHz) is accepted too. The 3.8 TTS models read the text as a verbatim transcript; delivery goes in
speech_metadata.style. "store": false because the Interactions API otherwise keeps each request (55 days, paid tier).

Models (https://ai.google.dev/gemini-api/docs/models): gemini-3.8-flash-tts (default) or gemini-3.8-flash-lite-tts
(cheaper, for high volume). Per call: 8,192 input tokens, 16,384 output tokens (25 audio tokens per second, about 10.9
minutes). Long text is split at sentence ends into CHUNK-character parts (about 3 minutes of speech each), read in
parallel (PARALLEL at a time) and joined with a short pause.

Pricing (https://ai.google.dev/gemini-api/docs/pricing, paid tier, to 31 Dec 2026; doubles from 1 Jan 2027):
flash-tts $0.50 per 1M text tokens in, $9.00 per 1M audio tokens out (10 minutes ≈ 15,000 tokens ≈ $0.14);
flash-lite-tts $6.00 per 1M audio tokens out (10 minutes ≈ $0.09).

The WAV is encoded to MP3 here (mono, BITRATE_KBPS) with lameenc (LAME; pip wheel, no ffmpeg in the image): media
blobs are capped at 15 MB and 10 minutes of 24 kHz WAV is about 29 MB; as MP3 it is about 3.6 MB.

Env: GEMINI_API_KEY; GEMINI_TTS_MODEL (default gemini-3.8-flash-tts); GEMINI_TTS_VOICE (default Iapetus, a prebuilt
"clear" voice; any prebuilt voice name works, or a voice id from the Extended Voice Library — e.g. an Indian English
voice picked in AI Studio). Fake mode returns one second of silent WAV so tests and QA need no network.

    data, content_type = await speak(text)        # live: (MP3 bytes, "audio/mpeg")
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import re
import wave

import httpx

from core.settings import settings
from core.vendors import vendor_mode

log = logging.getLogger("tts")

URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_MODEL = "gemini-3.8-flash-tts"
DEFAULT_VOICE = "Iapetus"
STYLE = "Calm, clear and unhurried, like a patient mentor explaining something to a colleague."
CHUNK = 3000
PARALLEL = 3
BITRATE_KBPS = 48
PAUSE_S = 0.35
DEFAULT_RATE = 24000


class TTSError(RuntimeError):
    pass


def mode() -> str:
    return vendor_mode("gemini")


def model_name() -> str:
    return (settings.gemini.tts_model or DEFAULT_MODEL)


def voice_name() -> str:
    return (settings.gemini.tts_voice or DEFAULT_VOICE)


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


def _body(part: str) -> dict:
    return {"model": model_name(), "store": False,
            "input": [{"type": "user_input", "content": [{"type": "text", "text": part,
                                                          "annotations": [{"type": "speech_metadata", "style": STYLE}]}]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice_name()}]}}


def _pcm(item: dict) -> tuple[bytes, int, int]:
    """One audio item → (16-bit little-endian PCM, sample rate, channels)."""
    try:
        raw = base64.b64decode(item.get("data") or "")
    except (ValueError, TypeError) as e:
        raise TTSError("audio: bad base64") from e
    if raw[:4] == b"RIFF":
        try:
            with wave.open(io.BytesIO(raw), "rb") as w:
                if w.getsampwidth() != 2:
                    raise TTSError(f"audio: {8 * w.getsampwidth()}-bit WAV")
                return w.readframes(w.getnframes()), w.getframerate(), w.getnchannels()
        except (wave.Error, EOFError) as e:
            raise TTSError("audio: bad WAV") from e
    mime = str(item.get("mime_type") or "").lower()
    if mime and "l16" not in mime and "pcm" not in mime:
        raise TTSError(f"audio: unexpected type {mime[:40]}")
    m = re.search(r"rate=(\d+)", mime)
    rate = int(item.get("sample_rate") or (m.group(1) if m else DEFAULT_RATE))
    return raw, rate, int(item.get("channels") or 1)


def audio_from_reply(data: dict) -> tuple[bytes, int, int]:
    """Interactions reply → PCM of the last audio item in the model output (as the guide's example reads it)."""
    if not isinstance(data, dict):
        raise TTSError("TTS: reply is not an object")
    if data.get("status") in ("failed", "cancelled"):
        raise TTSError(f"TTS: status {data.get('status')}")
    items = [c for st in data.get("steps") or [] if isinstance(st, dict) and st.get("type") == "model_output"
             for c in st.get("content") or [] if isinstance(c, dict) and c.get("type") == "audio" and c.get("data")]
    if not items:
        raise TTSError("TTS: no audio in the reply")
    pcm, rate, ch = _pcm(items[-1])
    if not pcm:
        raise TTSError("TTS: empty audio")
    return pcm, rate, ch


def to_mp3(pcm: bytes, rate: int, channels: int = 1) -> bytes:
    try:
        import lameenc
    except ImportError as e:  # the pip package is missing on this server
        raise TTSError("MP3 encoder (lameenc) is not installed") from e
    try:
        enc = lameenc.Encoder()
        enc.set_bit_rate(BITRATE_KBPS)
        enc.set_in_sample_rate(rate)
        enc.set_channels(channels)
        enc.set_quality(2)
        return bytes(enc.encode(pcm)) + bytes(enc.flush())
    except Exception as e:  # noqa: BLE001 — odd rate/channels from upstream
        raise TTSError(f"MP3 encoding failed: {type(e).__name__}") from e


def join_mp3(parts: list[tuple[bytes, int, int]]) -> bytes:
    """PCM parts → one MP3, with a short pause between parts. Parts in another format are encoded on their own
    (MP3 frames concatenate)."""
    out, run, fmt = b"", b"", None
    for pcm, rate, ch in parts:
        if fmt is not None and (rate, ch) != fmt:
            out += to_mp3(run, *fmt)
            run = b""
        elif run:
            run += b"\x00\x00" * ch * int(rate * PAUSE_S)
        fmt = (rate, ch)
        run += pcm
    if run and fmt:
        out += to_mp3(run, *fmt)
    return out


async def _speak_part(c: httpx.AsyncClient, key: str, part: str) -> tuple[bytes, int, int]:
    for attempt in range(2):
        r = await c.post(URL, json=_body(part), headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        if r.status_code in (429, 500, 503) and attempt == 0:
            await asyncio.sleep(2)
            continue
        if r.status_code >= 400:
            raise TTSError(f"TTS HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError as e:
            raise TTSError("TTS: reply is not JSON") from e
        return audio_from_reply(data)
    raise TTSError("TTS failed")


async def speak(text: str, *, client: httpx.AsyncClient | None = None) -> tuple[bytes, str]:
    m = mode()
    if m == "fake":
        return _silent_wav(), "audio/wav"
    if m == "off":
        raise TTSError("Audio is not set up yet (GEMINI_API_KEY).")
    parts = split_text(text)
    if not parts:
        raise TTSError("TTS: no text")
    key = settings.gemini.api_key
    c = client or httpx.AsyncClient(timeout=httpx.Timeout(150.0, connect=20.0))
    gate = asyncio.Semaphore(PARALLEL)

    async def one(part: str):
        async with gate:
            return await _speak_part(c, key, part)
    try:
        got = await asyncio.gather(*(one(p) for p in parts), return_exceptions=True)
    finally:
        if client is None:
            await c.aclose()
    for g in got:
        if isinstance(g, httpx.HTTPError):
            raise TTSError(f"TTS failed: {type(g).__name__}") from g
        if isinstance(g, BaseException):
            raise g
    return join_mp3(list(got)), "audio/mpeg"
