"""The hub with the AI in "live" mode but answered by a fault injector, for AI-failure QA (no keys, no network).

Every AI call runs the real code path (queue, time budget, JSON parsing, the tool's own checks, metering, refunds,
logging). Only the vendor's answer is simulated, and it comes from the tool's own `fake`, so a healthy answer is
always a valid one. POST /api/_qa/scenario {"name": ...} picks what the vendor does next:

  Anthropic (every text tool)                       Gemini (voice notes, Pitch Practice video)
  ok           the right JSON                       g_ok          answers at once
  fenced       JSON inside ```json fences + prose   g_busy_once   503 "high demand" twice, then answers
  truncated    JSON cut off at max_tokens           g_busy        503 on every try
  vendor_error 529 overloaded from the API          g_fallback    503 on the main model, the backup answers
  timeout      no answer within the time budget
  queue_full   no free AI slot
  not_json     a sentence instead of JSON
  busy_once    529 overloaded on the first call only (the page's own retry should recover)

Usage: python scripts/qa/ai_fault_server.py [port]   (in-memory Mongo, QA mode, the built React app)
"""
import asyncio
import contextvars
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8002
os.environ.update({"QA_MODE": "true", "APP_ENV": "development", "JWT_SECRET": "x" * 40, "COOKIE_SECURE": "false",
                   "MONGO_URL": "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=200", "DB_NAME": "hubqa",
                   "ADMIN_PHONES": "+919000000001", "PUBLIC_BASE_URL": f"http://127.0.0.1:{PORT}",
                   "GEMINI_API_KEY": "qa-key", "GEMINI_MODEL": "main-model"})
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import APIRouter  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

import llm  # noqa: E402
import server  # noqa: E402
from audio import stt  # noqa: E402
from features import pitch_video  # noqa: E402

STATE = {"name": "ok", "calls": 0}
FAKE = contextvars.ContextVar("fake", default=None)


# ------------------------------------------------------------------ Anthropic --------------------------------------
def _wrap(fn, *, chat=False):
    async def inner(*a, **kw):
        fake = kw.get("fake")
        FAKE.set(fake)
        return await fn(*a, **kw)
    return inner


class _Messages:
    async def create(self, *, model, max_tokens, system, messages, **_):
        STATE["calls"] += 1
        name = STATE["name"]
        fake = FAKE.get()
        out = fake() if fake else {}
        text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        stop = "end_turn"
        if name == "fenced":
            text = f"Here is the JSON you asked for:\n\n```json\n{text}\n```\nLet me know if you want changes."
        elif name == "truncated":
            text, stop = text[: max(10, int(len(text) * 0.55))], "max_tokens"
        elif name == "busy_once" and not STATE.get("failed_once"):
            STATE["failed_once"] = True
            raise RuntimeError("Error code: 529 - {'type': 'error', 'error': {'type': 'overloaded_error', 'message': 'Overloaded'}}")
        elif name == "vendor_error":
            raise RuntimeError("Error code: 529 - {'type': 'error', 'error': {'type': 'overloaded_error', 'message': 'Overloaded'}}")
        elif name == "timeout":
            await asyncio.sleep(5)
        elif name == "not_json":
            text = "I'm sorry, but I can't help with that request."
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop)


_STUB = SimpleNamespace(messages=_Messages())
llm._client = lambda: _STUB
llm.mode = lambda: "live"
for _n in ("complete_json", "complete_text", "complete_chat"):
    setattr(llm, _n, _wrap(getattr(llm, _n)))

_real_budget = llm.time_budget
llm.time_budget = lambda max_tokens, timeout=None: 1.5 if STATE["name"] == "timeout" else _real_budget(max_tokens, timeout)
_real_sem = llm._sem
llm._sem = lambda: asyncio.Semaphore(0) if STATE["name"] == "queue_full" else _real_sem()
_real_wait = llm._wait_kw
llm._wait_kw = lambda q: {"queue_wait": 1} if STATE["name"] == "queue_full" else _real_wait(q)


# ------------------------------------------------------------------ Gemini (httpx mock) ----------------------------
pitch_video.mode = lambda: "live"
stt.mode = lambda: "live"
pitch_video.RETRY_PAUSES_S = (0.05, 0.05, 0.05)
GEM = {"tries": 0}
_real_analyse = pitch_video.analyse


async def _analyse(path, **kw):
    FAKE.set(kw.get("fake"))
    return await _real_analyse(path, **kw)
pitch_video.analyse = _analyse


def _gemini(req: httpx.Request) -> httpx.Response:
    u = str(req.url)
    if req.method == "POST" and u.endswith("/upload/v1beta/files"):
        return httpx.Response(200, headers={"x-goog-upload-url": "https://upload.qa/session/1"}, json={})
    if u.startswith("https://upload.qa/"):
        return httpx.Response(200, json={"file": {"name": "files/qa1", "uri": "https://g/files/qa1", "state": "ACTIVE",
                                                  "mimeType": "video/mp4", "videoMetadata": {"videoDuration": "60s"}}})
    if req.method == "DELETE":
        return httpx.Response(200, json={})
    if req.method == "GET" and "/v1beta/files/" in u:
        return httpx.Response(200, json={"name": "files/qa1", "uri": "https://g/files/qa1", "state": "ACTIVE"})
    if ":generateContent" in u:
        GEM["tries"] += 1
        name = STATE["name"]
        busy = httpx.Response(503, json={"error": {"code": 503, "status": "UNAVAILABLE",
                                                   "message": "This model is currently experiencing high demand."}})
        if name == "g_busy" or (name == "g_busy_once" and GEM["tries"] <= 2) or (name == "g_fallback" and "main-model" in u):
            return busy
        fake = FAKE.get()
        body = json.loads(req.content)
        is_stt = "Transcribe" in json.dumps(body.get("contents"))
        out = {"text": stt.FAKE_TEXT} if is_stt or not fake else fake()
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(out)}]},
                                                         "finishReason": "STOP"}]})
    return httpx.Response(404, json={"error": {"message": f"qa mock: no route {req.method} {u}"}})


_RealAsync = httpx.AsyncClient


def _client_factory(*a, **kw):
    kw.pop("transport", None)
    return _RealAsync(*a, transport=httpx.MockTransport(_gemini), **kw)


pitch_video.httpx.AsyncClient = _client_factory   # the same httpx module object audio.stt uses


# ------------------------------------------------------------------ app -------------------------------------------
app = server.create_app(AsyncMongoMockClient()["hubqa"], start_jobs=False, seed=True, serve_spa=True)
qa = APIRouter()


@qa.post("/api/_qa/scenario")
async def scenario(body: dict):
    STATE["name"] = body.get("name", "ok")
    STATE["failed_once"] = False
    for k, v in (body.get("env") or {}).items():       # e.g. {"SEARCH_MODE": "off"}; settings are read per request
        if k in ("SEARCH_MODE",):
            os.environ[k] = v
    GEM["tries"] = 0
    if STATE["name"] == "g_fallback":
        os.environ["GEMINI_FALLBACK_MODEL"] = "backup-model"
    else:
        os.environ.pop("GEMINI_FALLBACK_MODEL", None)
    return {"scenario": STATE["name"]}


@qa.get("/api/_qa/stats")
async def stats():
    return {"scenario": STATE["name"], "anthropic_calls": STATE["calls"], "gemini_tries": GEM["tries"]}


app.router.routes.insert(0, qa.routes[0])
app.router.routes.insert(0, qa.routes[1])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
