"""Small shared helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId


def iso(v: Any) -> Any:
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return v


def oid(v: str) -> Optional[ObjectId]:
    try:
        return ObjectId(v)
    except Exception:  # noqa: BLE001
        return None


def uid(user: dict) -> str:
    return str(user["_id"])


def r2(v: Optional[float], n: int = 2) -> Optional[float]:
    return None if v is None else round(float(v), n)


def smart_round(v: Optional[float]) -> Optional[float]:
    """Prices: keep significant digits for tiny coins."""
    if v is None:
        return None
    v = float(v)
    if v == 0:
        return 0.0
    a = abs(v)
    return round(v, 2 if a >= 1 else 4 if a >= 0.01 else 8 if a >= 0.000001 else 12)


def inr(v) -> str:
    """₹12,00,000 — Indian digit grouping."""
    n = int(round(float(v or 0)))
    s, neg = str(abs(n)), n < 0
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("−" if neg else "") + "₹" + s
