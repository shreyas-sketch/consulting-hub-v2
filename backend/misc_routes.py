"""Small routes: plan catalog, my plan, app config, QA login."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

import appsettings
import plans
from core.deps import user_dep
from core.settings import settings
from growth.clock import utcnow
from state import db

router = APIRouter(tags=["misc"])


@router.get("/plans/catalog")
async def catalog():
    return {"gst_pct": plans.GST_PCT, "plans": plans.CATALOG,
            "features": [{"key": k, **v} for k, v in plans.FEATURES.items()]}


@router.get("/me/plan")
async def my_plan(user: dict = Depends(user_dep())):
    return await plans.plan_info(db(), user)


@router.get("/me/home")
async def my_home(user: dict = Depends(user_dep())):
    """What the home screen needs beyond the plan: the group session invite and support contact."""
    s = await appsettings.get(db())
    return {"group_session": s["group_session"], "support_whatsapp": s["support_whatsapp"]}


@router.get("/config")
async def config():
    return {"brand_name": settings.brand_name, "qa_mode": settings.qa_mode and not settings.is_production}


QA_PHONES = {"free": "+919000000010", "member": "+919000000011", "l1": "+919000000012", "l2": "+919000000013"}


class QaLoginIn(BaseModel):
    phone: Optional[str] = Field(None, max_length=20)
    role: Literal["user", "admin"] = "user"
    plan: Optional[Literal["free", "member", "l1", "l2"]] = None


@router.post("/qa/login")
async def qa_login(body: QaLoginIn, response: Response):
    """QA_MODE only: log in as a demo member on any plan (default: free) or the demo admin."""
    if not settings.qa_mode or settings.is_production:
        raise HTTPException(status_code=404, detail={"code": "not_found", "msg": "Not found"})
    from datetime import timedelta
    from accounts.phone import normalise_in_mobile
    from accounts.routes import create_member
    from auth import public_user, set_auth_cookies
    d = db()
    default = "+919000000002" if body.role == "admin" else QA_PHONES[body.plan or "free"]
    phone = normalise_in_mobile(body.phone or default)
    user = await d.users.find_one({"phone": phone})
    if not user:
        user = await create_member(d, phone, name="Admin (QA)" if body.role == "admin" else "Demo Member",
                                   utm={"src": "qa"}, role=body.role)
    if body.plan:
        now = utcnow()
        await d.plan_grants.delete_many({"user_id": str(user["_id"])})
        if body.plan != "free":
            await d.plan_grants.insert_one({"user_id": str(user["_id"]), "plan": body.plan,
                                            "ends_at": now + timedelta(days=31), "by": "qa", "at": now})
    if body.role == "admin" and user.get("role") != "admin":
        await d.users.update_one({"_id": user["_id"]}, {"$set": {"role": "admin"}})
        user["role"] = "admin"
    set_auth_cookies(response, str(user["_id"]), user.get("role") or "user")
    return {"user": public_user(user), "plan": await plans.plan_info(d, user)}
