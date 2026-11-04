"""Helpers every tool uses: plan check + metering + refund when the work fails."""
from __future__ import annotations

from typing import Awaitable, Callable, Optional

from fastapi import HTTPException

import llm
import plans


def busy_error() -> HTTPException:
    return HTTPException(status_code=503, detail={
        "code": "ai_busy", "msg": "The AI is busy right now. Try again in a minute. This didn't use up your go."})


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
