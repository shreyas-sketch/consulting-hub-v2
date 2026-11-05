"""Claude calls behind one helper, with a deterministic fake for tests and QA.

    await complete_json(task="niche_snapshot", system=..., prompt=..., fake=lambda: {...})

Every caller passes `fake`: the shape the feature expects, built from the same inputs,
so QA mode and tests run with no key and no network. Live mode asks for JSON only and
parses the first JSON object in the reply.

Models (env): LLM_MODEL_FAST (default claude-haiku-5-5), LLM_MODEL_STRONG
(claude-sonnet-5-5), LLM_MODEL_VISION (claude-opus-5-5).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable, Optional

from core.settings import settings
from core.vendors import vendor_mode

log = logging.getLogger("llm")

MODELS = {
    "fast": lambda: settings.llm.model("fast"),
    "strong": lambda: settings.llm.model("strong"),
    "vision": lambda: settings.llm.model("vision"),
}


class LLMError(RuntimeError):
    pass


# Concurrency guard (load test, 3 Nov): a webinar puts hundreds of people on X-Ray / Ask at the same second.
# At most LLM_MAX_CONCURRENCY (48) calls are in flight per worker; the rest wait up to LLM_QUEUE_WAIT_S (15 s) for a
# slot, then fail fast with LLMError so the caller shows its rule-based answer instead of hanging. A caller can pass
# `queue_wait` to wait longer: the webinar tools (Niche Snapshot, case scoring, Meeting Brief) wait up to 45 s,
# because at the QR-code moment 500 people press the button in the same minute and a short wait beats "busy".
# Each call has a hard LLM_TIMEOUT_S. Size LLM_MAX_CONCURRENCY × workers against your Anthropic rate limit.
_SEM: dict = {"sem": None, "n": None}


def _wait_kw(queue_wait: Optional[float]) -> dict:
    """Pass queue_wait on to _guarded only when the caller set it (keeps _guarded's 3-argument call shape)."""
    return {"queue_wait": queue_wait} if queue_wait else {}


def _sem() -> asyncio.Semaphore:
    n = settings.llm.max_concurrency
    if _SEM["sem"] is None or _SEM["n"] != n:
        _SEM["sem"], _SEM["n"] = asyncio.Semaphore(n), n
    return _SEM["sem"]


async def _guarded(coro_fn, task: str, timeout: Optional[float] = None, queue_wait: Optional[float] = None):
    sem = _sem()
    wait = queue_wait or settings.llm.queue_wait_s
    try:
        await asyncio.wait_for(sem.acquire(), timeout=wait)
    except (asyncio.TimeoutError, TimeoutError):
        log.warning("LLM task %s: queue full, using fallback", task)
        raise LLMError("AI is busy right now.")
    try:
        limit = timeout or settings.llm.timeout_s
        return await asyncio.wait_for(coro_fn(), timeout=limit)
    except (asyncio.TimeoutError, TimeoutError):
        log.warning("LLM task %s timed out", task)
        raise LLMError("AI took too long.")
    finally:
        sem.release()


async def _call_text(*, model: str, max_tokens: int, system: str, content) -> str:
    resp = await _client().messages.create(model=MODELS[model](), max_tokens=max_tokens, system=system,
                                           messages=[{"role": "user", "content": content}])
    return "".join(getattr(b, "text", "") for b in resp.content)


def mode() -> str:
    return vendor_mode("anthropic")


_CLIENT: dict = {"c": None}


def _client():
    """One shared client per worker (connection pooling) instead of a new one per call."""
    if _CLIENT["c"] is None:
        import anthropic
        _CLIENT["c"] = anthropic.AsyncAnthropic(api_key=settings.llm.api_key, max_retries=1)
    return _CLIENT["c"]


def _parse(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise LLMError("no JSON in reply")
    return json.loads(text[start:end + 1])


async def complete_json(*, task: str, system: str, prompt: str, fake: Callable[[], Any], model: str = "fast",
                        max_tokens: int = 1200, images: Optional[list[tuple[str, bytes]]] = None,
                        fallback_on_error: bool = False, timeout: Optional[float] = None,
                        queue_wait: Optional[float] = None) -> dict:
    """images: [(media_type, bytes)] for vision tasks. fallback_on_error: return fake() instead of raising.
    timeout: seconds for this call (default LLM_TIMEOUT_S, 45); long documents pass more.
    queue_wait: seconds to wait for a free slot before "busy" (default LLM_QUEUE_WAIT_S, 15)."""
    try:
        return await _complete_json(task=task, system=system, prompt=prompt, fake=fake, model=model,
                                    max_tokens=max_tokens, images=images, timeout=timeout, queue_wait=queue_wait)
    except LLMError:
        if fallback_on_error:
            return fake()
        raise


async def _fake_with_latency(fake: Callable[[], Any], task: str, queue_wait: Optional[float] = None):
    """LLM_FAKE_LATENCY_MS (load tests only): make fake answers take as long as real ones and go through the
    same concurrency guard, so a load test shows what the real Anthropic latency does to queues."""
    ms = settings.llm.fake_latency_ms
    if ms <= 0:
        return fake()

    async def slow():
        await asyncio.sleep(ms / 1000)
        return fake()
    return await _guarded(slow, task, **_wait_kw(queue_wait))


async def _complete_json(*, task, system, prompt, fake, model, max_tokens, images, timeout=None, queue_wait=None) -> dict:
    m = mode()
    if m == "fake":
        return await _fake_with_latency(fake, task, queue_wait)
    if m == "off":
        raise LLMError("AI is not configured (ANTHROPIC_API_KEY).")
    content: list = []
    for media, data in images or []:
        import base64
        content.append({"type": "image", "source": {"type": "base64", "media_type": media,
                                                    "data": base64.b64encode(data).decode()}})
    content.append({"type": "text", "text": prompt + "\n\nReply with one JSON object only."})
    try:
        text = await _guarded(lambda: _call_text(model=model, max_tokens=max_tokens, system=system, content=content), task,
                              timeout or (120 if max_tokens > 3000 else None), **_wait_kw(queue_wait))
        return _parse(text)
    except LLMError:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("LLM task %s failed: %s", task, e)
        raise LLMError(f"AI call failed: {type(e).__name__}") from e


async def complete_text(*, task: str, system: str, prompt: str, fake: Callable[[], str], model: str = "strong",
                        max_tokens: int = 1200, queue_wait: Optional[float] = None) -> str:
    m = mode()
    if m == "fake":
        return await _fake_with_latency(fake, task, queue_wait)
    if m == "off":
        raise LLMError("AI is not configured (ANTHROPIC_API_KEY).")
    try:
        text = await _guarded(lambda: _call_text(model=model, max_tokens=max_tokens, system=system, content=prompt), task,
                              **_wait_kw(queue_wait))
        return text.strip()
    except LLMError:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("LLM task %s failed: %s", task, e)
        raise LLMError(f"AI call failed: {type(e).__name__}") from e


async def complete_chat(*, task: str, system: str, messages: list[dict], fake: Callable[[], str],
                        model: str = "fast", max_tokens: int = 2048, timeout: Optional[float] = None,
                        queue_wait: Optional[float] = None) -> str:
    """Multi-turn chat: messages = [{"role": "user"|"assistant", "content": str}, ...] ending with a user turn.
    Returns the assistant's text. Same queue, timeout and fake rules as complete_json."""
    m = mode()
    if m == "fake":
        return await _fake_with_latency(fake, task, queue_wait)
    if m == "off":
        raise LLMError("AI is not configured (ANTHROPIC_API_KEY).")
    msgs = [{"role": x["role"], "content": str(x["content"])} for x in messages if x.get("content")]

    async def call():
        resp = await _client().messages.create(model=MODELS[model](), max_tokens=max_tokens, system=system, messages=msgs)
        return "".join(getattr(b, "text", "") for b in resp.content)
    try:
        return (await _guarded(call, task, timeout or (150 if max_tokens > 3000 else None), **_wait_kw(queue_wait))).strip()
    except LLMError:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("LLM task %s failed: %s", task, e)
        raise LLMError(f"AI call failed: {type(e).__name__}") from e


async def complete_with_tools(*, task: str, system: str, prompt: str, tools: list[dict], model: str = "fast",
                              max_tokens: int = 1200, timeout: Optional[float] = None, max_continues: int = 2,
                              queue_wait: Optional[float] = None) -> dict:
    """One live call that uses Anthropic's server-side tools (web search, web fetch: the API runs them itself).

    Returns the reply as plain JSON, not SDK objects, so newer block types (web_search_tool_result,
    web_fetch_tool_result, …) reach the caller intact whatever SDK version is pinned:
        {"content": [every block of every turn, in order], "stop_reason": str, "usage": [usage of each turn]}
    A "pause_turn" stop (long tool turns) is continued by sending the assistant turn back unchanged, up to
    max_continues times. The whole exchange holds one slot of the concurrency guard and one timeout
    (default LLM_TIMEOUT_S). No fake here: the caller checks its own vendor switch first and keeps its own fake.
    Raises LLMError on any failure."""
    async def call():
        msgs: list = [{"role": "user", "content": prompt}]
        blocks: list = []
        usage: list = []
        stop = None
        for _ in range(max(0, max_continues) + 1):
            raw = await _client().messages.with_raw_response.create(
                model=MODELS[model](), max_tokens=max_tokens, system=system, messages=msgs, tools=tools)
            data = raw.http_response.json() or {}
            blocks.extend(b for b in (data.get("content") or []) if isinstance(b, dict))
            usage.append(data.get("usage") or {})
            stop = data.get("stop_reason")
            if stop != "pause_turn":
                break
            msgs = [{"role": "user", "content": prompt}, {"role": "assistant", "content": list(blocks)}]
        return {"content": blocks, "stop_reason": stop, "usage": usage}
    try:
        return await _guarded(call, task, timeout, **_wait_kw(queue_wait))
    except LLMError:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("LLM task %s failed: %s", task, e)
        raise LLMError(f"AI call failed: {type(e).__name__}") from e
