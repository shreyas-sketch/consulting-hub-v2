"""Mongo indexes, created at startup (idempotent)."""
from __future__ import annotations

import logging

log = logging.getLogger("indexes")

INDEXES = [
    ("users", [("phone", 1)], {"unique": True, "sparse": True}),
    ("users", [("email", 1)], {"unique": True, "sparse": True}),
    ("users", [("created_at", -1)], {}),
    ("plan_grants", [("ends_at", 1)], {}),
    ("plan_grants", [("user_id", 1)], {}),
    ("subscriptions", [("status", 1), ("current_end", 1)], {}),
    ("subscriptions", [("user_id", 1), ("status", 1)], {}),
    ("subscriptions", [("paused_for_l2", 1), ("resume_at", 1)], {"sparse": True}),
    ("usage", [("user_id", 1)], {}),
    ("job_locks", [("until", 1)], {}),
    ("job_runs", [("name", 1), ("at", -1)], {}),
    ("otp_challenges", [("phone", 1), ("created_at", -1)], {}),
    ("otp_challenges", [("ip", 1), ("created_at", -1)], {}),
    ("otp_challenges", [("purge_at", 1)], {"expireAfterSeconds": 0}),
    ("events", [("anon_id", 1)], {"sparse": True}),            # identify(): anon → user on sign-up
    ("events", [("name", 1), ("ts", 1), ("user_id", 1), ("anon_id", 1)], {}),   # admin reports
    ("events", [("user_id", 1), ("ts", -1)], {}),
    ("inbox", [("user_id", 1), ("at", -1)], {}),
    # webinar tools
    ("readiness", [("user_id", 1), ("at", -1)], {}),
    ("snapshots", [("user_id", 1), ("at", -1)], {}),
    ("case_answers", [("user_id", 1), ("at", -1)], {}),
    ("case_answers", [("case_id", 1), ("at", -1)], {}),
    ("cases", [("week", -1)], {"sparse": True}),
    ("briefs", [("user_id", 1), ("at", -1)], {}),
    ("linkedin_checks", [("user_id", 1), ("at", -1)], {}),
]


def register(coll: str, keys: list, opts: dict | None = None) -> None:
    """Feature modules add their indexes at import time."""
    INDEXES.append((coll, keys, opts or {}))


async def ensure_indexes(db) -> None:
    for coll, keys, opts in INDEXES:
        try:
            await db[coll].create_index(keys, **opts)
        except Exception as e:  # noqa: BLE001
            log.warning("index %s %s: %s", coll, keys, e)
