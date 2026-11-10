"""Business rules for cases — no HTTP here.

Free accounts: the live case only, once. A case they answered stays theirs to open (read-only) after the live case
changes. Paid plans: every case, answers metered per month. The model answer is shown only after the member has sent
an answer to that case.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Optional

import appsettings
import llm
import plans
from core.errors import NotFound
from growth import events
from growth.clock import utcnow

from ..case_bank import CASES, CRITERIA
from ..common import as_dict, run_metered, strip_providers, text, text_list
from . import prompts, schemas
from .repository import CaseRepository

WEBINAR_QUEUE_WAIT = 45     # seconds a scoring call may wait for an AI slot when the whole webinar answers at once


class CaseService:
    def __init__(self, repo: Optional[CaseRepository] = None) -> None:
        self.repo = repo or CaseRepository()

    @property
    def db(self):
        return self.repo.db

    # ------------------------------------------------------------------------------------------------ helpers ----
    async def _context(self, user: dict) -> tuple[str, str]:
        plan = (await plans.effective_plan(self.db, user))["plan"]
        live_id = (await appsettings.get(self.db))["live_case_id"]
        return plan, live_id

    async def _require_case(self, case_id: str) -> dict:
        c = await self.repo.get_active(case_id)
        if not c:
            raise NotFound("Case not found.")
        return c

    # --------------------------------------------------------------------------------------------------- reads ----
    async def listing(self, user: dict) -> dict[str, Any]:
        plan, live_id = await self._context(user)
        done = await self.repo.best_answers_by_case(str(user["_id"]))
        items = []
        for c in await self.repo.list_active():
            live = c["_id"] == live_id
            answered = c["_id"] in done
            row = schemas.card(c, live=live, locked=plan == "free" and not live and not answered)
            row["my_score"] = done[c["_id"]]["overall"] if answered else None
            row["answered"] = answered
            row["read_only"] = plan == "free" and not live
            items.append(row)
        # Free: the live case, then the cases they answered before (theirs to reopen), then the locked ones.
        items.sort(key=lambda r: (not r["live"], plan == "free" and not r["answered"], r["kind"] != "weekly"))
        return {"plan": plan, "items": items}

    async def detail(self, user: dict, case_id: str) -> dict[str, Any]:
        c = await self._require_case(case_id)
        plan, live_id = await self._context(user)
        mine = [schemas.answer(a) for a in await self.repo.answers_for(str(user["_id"]), case_id)]
        # Free: the live case, or (read-only) one they already answered, so their score and model answer stay theirs.
        if plan == "free" and case_id != live_id and not mine:
            raise plans.locked_error("case", "member")
        read_only = plan == "free" and case_id != live_id
        return {"case": schemas.full(c, bool(mine)) | {"live": case_id == live_id, "read_only": read_only},
                "answers": mine}

    # -------------------------------------------------------------------------------------------------- writes ----
    async def submit_answer(self, user: dict, case_id: str, answer_text: str) -> dict[str, Any]:
        c = await self._require_case(case_id)
        uid = str(user["_id"])
        plan, live_id = await self._context(user)
        if plan == "free" and case_id != live_id:
            raise plans.locked_error("case", "member")

        async def work(_plan: str) -> dict[str, Any]:
            raw = as_dict(await llm.complete_json(
                task="case_score", system=prompts.SYSTEM, prompt=prompts.score_prompt(c, answer_text),
                fake=lambda: prompts.fake_score(c, answer_text), model="fast", max_tokens=700,
                queue_wait=WEBINAR_QUEUE_WAIT))
            scores = read_scores(raw.get("scores"))
            if scores is None:
                raise llm.LLMError(f"case_score: missing scores ({str(raw.get('scores'))[:120]})")   # refunded
            doc = {"_id": uuid.uuid4().hex, "user_id": uid, "case_id": case_id, "answer": answer_text.strip(),
                   "scores": scores, "overall": round(sum(scores.values()) / len(scores), 1),
                   "good": strip_providers(text_list(raw.get("good"), 3, 200)),
                   "improve": strip_providers(text_list(raw.get("improve"), 3, 200)),
                   "summary": strip_providers(text(raw.get("summary"), 400)), "at": utcnow()}
            await self.repo.add_answer(doc)
            await events.track(self.db, "case_answered", user_id=uid,
                               props={"case_id": case_id, "score": doc["overall"], "live": case_id == live_id})
            return {"answer": schemas.answer(doc), "model_answer": c["model_answer"], "criteria": schemas.criteria()}

        return await run_metered(self.db, user, "case", work)


# ------------------------------------------------------------------------------- module-level API for other modules ----
def _out_of_ten(v: Any) -> Optional[int]:
    """7, "7", "7/10", "7 out of 10", "70/100", {"score": 7} → 7 (0-10). Anything without a number → None."""
    if isinstance(v, dict):
        v = v.get("score", v.get("value", v.get("points")))
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return max(0, min(10, round(v)))
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:/|out of)\s*(\d+(?:\.\d+)?)", str(v), re.I)
    if m and float(m.group(2)) > 0:
        return max(0, min(10, round(float(m.group(1)) * 10 / float(m.group(2)))))
    m = re.search(r"-?\d+(?:\.\d+)?", str(v))
    return max(0, min(10, round(float(m.group())))) if m else None


def read_scores(sc: Any) -> Optional[dict[str, int]]:
    """The four criteria from the shapes a live model writes: a dict (any case), a list of {criterion, score}, scores
    as numbers or "6/10". None when a criterion is missing (the caller treats it as an incomplete answer)."""
    rows: dict[str, Any] = {}
    if isinstance(sc, dict):
        rows = {str(k).strip().lower(): v for k, v in sc.items()}
    elif isinstance(sc, list):
        for x in sc:
            if isinstance(x, dict):
                name = x.get("criterion") or x.get("key") or x.get("name")
                if name:
                    rows[str(name).strip().lower()] = x
    out = {k: _out_of_ten(rows.get(k)) for k, _ in CRITERIA}
    return None if any(v is None for v in out.values()) else out


async def ensure_seed(d) -> int:
    """Practice cases live in code (case_bank.py): refreshed on every start. Returns how many were new."""
    repo = CaseRepository(d)
    return sum([await repo.upsert_practice(c) for c in CASES])


async def get_case(d, case_id: str) -> Optional[dict]:
    return await CaseRepository(d).get_active(case_id)
