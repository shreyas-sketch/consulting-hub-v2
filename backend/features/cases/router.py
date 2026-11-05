"""HTTP layer for cases: parse the request, call the service, return its dict. No business rules here."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from core.deps import user_dep

from .schemas import AnswerIn
from .service import CaseService

router = APIRouter(prefix="/cases", tags=["cases"])
CurrentUser = Depends(user_dep())


def get_service() -> CaseService:
    return CaseService()


@router.get("")
async def listing(user: dict = CurrentUser, svc: CaseService = Depends(get_service)):
    return await svc.listing(user)


@router.get("/{case_id}")
async def one(case_id: str, user: dict = CurrentUser, svc: CaseService = Depends(get_service)):
    return await svc.detail(user, case_id)


@router.post("/{case_id}/answer")
async def answer(case_id: str, body: AnswerIn, user: dict = CurrentUser, svc: CaseService = Depends(get_service)):
    return await svc.submit_answer(user, case_id, body.answer)
