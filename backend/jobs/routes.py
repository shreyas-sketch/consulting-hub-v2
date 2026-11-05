"""POST /api/jobs/tick (X-Ingest-Key) — runs every due job; for an external cron (every 5–15 min)."""
from fastapi import APIRouter, Depends

import state
from core.deps import require_ingest_key

from . import registry

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/tick")
async def tick(_: bool = Depends(require_ingest_key)):
    return {"ran": await registry.tick(state.db())}
