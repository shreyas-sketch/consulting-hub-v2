"""Demo content for QA_MODE. Idempotent: only fills what's empty.

Everything here is SAMPLE content for testing. The real group session details, live case and knowledge base
are set by the team in Admin.
"""
from __future__ import annotations

import logging

log = logging.getLogger("seed")

KB_SAMPLE = ("SAMPLE (test mode) — replace with a real session transcript",
             "This is sample text so the knowledge base isn't empty in test mode. Upload real session transcripts "
             "and workbooks in Admin, Knowledge base, before switching Akshat AI on.")


async def seed_demo(db) -> dict:
    from features.cases import ensure_seed
    from features.kb import ingest
    out = {"cases": await ensure_seed(db)}
    if not await db.kb_docs.count_documents({}):
        await ingest(db, *KB_SAMPLE)
        out["kb"] = 1
    s = await db.settings.find_one({"_id": "app"}) or {}
    if not (s.get("group_session") or {}).get("when"):
        await db.settings.update_one({"_id": "app"}, {"$set": {"group_session": {
            "title": "Group session with Akshat (sample)", "when": "Saturday, 11:00 am IST",
            "link": "https://example.com/test-mode/group-session"}}}, upsert=True)
    return out
