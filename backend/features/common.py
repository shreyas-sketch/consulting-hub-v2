"""Helpers every tool uses: plan check + metering + refund when the work fails."""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Iterable, Optional

from fastapi import HTTPException

import llm
import plans
from core.errors import AIBusy


def busy_error() -> HTTPException:
    return AIBusy("The AI is busy right now. Try again in a minute. This didn't use up your go.")


async def run_metered(db, user: dict, meter: str, work: Callable[[str], Awaitable], *, access: Optional[str] = None):
    """Check the plan opens `access` (default: the meter), count one use of `meter`, run `work(plan)`.
    Any failure gives the use back, so a member never loses a go to an AI or network error."""
    plan = await plans.require(db, user, access or meter)
    await plans.consume(db, user, meter, plan)
    try:
        return await work(plan)
    except llm.LLMError:
        await plans.refund(db, user, meter, plan)
        raise busy_error()
    except Exception:
        await plans.refund(db, user, meter, plan)
        raise


def clamp_int(v, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return default


def text(v, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def text_list(v, n_items: int, n_chars: int) -> list[str]:
    if not isinstance(v, list):
        return []
    return [t for t in (text(x, n_chars) for x in v[:n_items]) if t]


# ---------------------------------------------------------------- AI output guards ----
# Put NO_VENDOR in every system prompt. Run anything a member (or their client) reads through strip_providers.
NO_VENDOR = ("Never name or hint at any AI company, model or tool behind this; you are simply the hub's assistant. "
             "No emojis.")

PROVIDER_WORDS = re.compile(
    r"\b(google\s+(ai|deepmind|gemini|cloud|vertex)|gemini(\s+\d+(\.\d+)?)?(\s+(pro|flash|ultra|nano))?|deepmind|bard|"
    r"vertex\s+ai|openai|chat\s?gpt|gpt-?\d[\w.-]*|whisper|claude(\s+(opus|sonnet|haiku))?|anthropic|tavily|gamma\.app|"
    r"large\s+language\s+models?|llms?)\b", re.I)


def strip_providers(v: Any, word: str = "the AI") -> Any:
    """Replace provider/model names in strings (also inside dicts and lists)."""
    if isinstance(v, str):
        return re.sub(r"[ \t]{2,}", " ", PROVIDER_WORDS.sub(word, v))
    if isinstance(v, list):
        return [strip_providers(x, word) for x in v]
    if isinstance(v, dict):
        return {k: strip_providers(x, word) for k, x in v.items()}
    return v


def as_list(v: Any) -> list:
    """AI fields that should be lists: anything else becomes []. Use before slicing or iterating."""
    return v if isinstance(v, list) else []


def as_dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


URL_RX = re.compile(r"(https?://[^\s)<>\]]+|www\.[^\s)<>\]]+)", re.I)


def strip_links(v: str, allowed: Iterable[str] = ()) -> str:
    """Remove links the AI may have invented. Links in `allowed` (the member's own site, booking link) stay."""
    keep = {a.strip().rstrip("/").lower() for a in allowed if a}

    def repl(m: re.Match) -> str:
        u = m.group(0).rstrip(".,;:!?")
        tail = m.group(0)[len(u):]
        return m.group(0) if u.rstrip("/").lower() in keep else tail
    return re.sub(r"[ \t]{2,}", " ", URL_RX.sub(repl, v or ""))
