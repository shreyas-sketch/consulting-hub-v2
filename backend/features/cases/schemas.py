"""Request bodies and response shapes for cases. Mappers turn stored documents into what the API returns
(never raw Mongo documents: ids renamed, datetimes as ISO strings, the model answer only when earned)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from util import iso

from ..case_bank import CRITERIA


class AnswerIn(BaseModel):
    answer: str = Field(..., min_length=40, max_length=4000)


def criteria() -> list[dict]:
    return [{"key": k, "label": lbl} for k, lbl in CRITERIA]


def card(c: dict, *, live: bool, locked: bool) -> dict:
    return {"id": c["_id"], "title": c["title"], "company": c["company"], "industry": c["industry"],
            "city": c.get("city"), "kind": c.get("kind", "practice"), "week": c.get("week"), "live": live,
            "locked": locked, "source": c.get("source")}


def full(c: dict, answered: bool) -> dict:
    out = {**card(c, live=False, locked=False), "situation": c["situation"], "facts": c.get("facts", []),
           "question": c["question"], "framework_hint": c.get("framework_hint"), "criteria": criteria()}
    out["model_answer"] = c["model_answer"] if answered else None
    return out


def answer(a: dict) -> dict:
    return {"id": a["_id"], "case_id": a["case_id"], "answer": a["answer"], "scores": a["scores"],
            "overall": a["overall"], "good": a.get("good", []), "improve": a.get("improve", []),
            "summary": a.get("summary"), "at": iso(a["at"])}
