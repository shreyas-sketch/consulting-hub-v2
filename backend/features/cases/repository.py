"""Data access for cases.

    cases        {_id, title, company, industry, city, situation, facts, question, framework_hint, model_answer,
                  kind practice|weekly, week?, source?: {title, url}, active, created_at}
    case_answers {_id, user_id, case_id, answer, scores: {criterion: 0-10}, overall, good, improve, summary, at}
"""
from __future__ import annotations

from typing import Optional

from core.repository import Repository
from growth.clock import utcnow

ACTIVE = {"active": {"$ne": False}}


class CaseRepository(Repository):
    async def get_active(self, case_id: str) -> Optional[dict]:
        return await self.db.cases.find_one({"_id": case_id, **ACTIVE})

    async def list_active(self) -> list[dict]:
        return [c async for c in self.db.cases.find(ACTIVE).sort([("week", -1), ("created_at", 1)])]

    async def upsert_practice(self, case: dict) -> bool:
        """Practice text is refreshed from code; `active` and `created_at` are kept. True when newly inserted."""
        body = {k: v for k, v in case.items() if k != "_id"}
        res = await self.db.cases.update_one({"_id": case["_id"]},
                                             {"$set": {**body, "kind": "practice"},
                                              "$setOnInsert": {"active": True, "created_at": utcnow()}},
                                             upsert=True)
        return bool(res.upserted_id)

    async def best_answers_by_case(self, user_id: str) -> dict[str, dict]:
        """case_id → the member's latest answer summary ({case_id, overall})."""
        cur = self.db.case_answers.find({"user_id": user_id}, {"case_id": 1, "overall": 1}).sort("at", 1)
        return {a["case_id"]: a async for a in cur}

    async def answers_for(self, user_id: str, case_id: str) -> list[dict]:
        cur = self.db.case_answers.find({"user_id": user_id, "case_id": case_id}).sort("at", -1)
        return [a async for a in cur]

    async def add_answer(self, doc: dict) -> None:
        await self.db.case_answers.insert_one(doc)
