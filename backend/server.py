"""App entry point: `uvicorn server:app`.

`create_app(db=None)` is the composition root — the one place the app is assembled:

    settings check → logging → Sentry → database binding → middleware → error handlers
    → routers from the module registry (core.modules) → lifespan (indexes, flags, seed, scheduler) → SPA

Tests call `create_app(mongomock_db, start_jobs=False, seed=False, serve_spa=False)`.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import APIRouter, FastAPI  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

log = logging.getLogger("server")


class ConfigError(RuntimeError):
    """The environment is not safe to run in production (see core.settings.Settings.problems)."""


async def _on_startup(app: FastAPI, db, *, run_jobs: bool, do_seed: bool) -> None:
    from auth import seed_admin
    from core import flags
    from indexes import ensure_indexes
    from jobs.registry import claim_lock, release_lock, start_scheduler

    await ensure_indexes(db)
    await flags.refresh(db, force=True)
    # With several workers (WEB_CONCURRENCY > 1) every worker runs this at the same moment: only the one that wins
    # the Mongo lease seeds, so nothing is inserted twice.
    if await claim_lock(db, "_startup_seed", minutes=5):
        try:
            await seed_admin(db)
            from features.cases import ensure_seed
            await ensure_seed(db)
            if do_seed:
                from seed import seed_demo
                await seed_demo(db)
        finally:
            await release_lock(db, "_startup_seed")

    async def keep_flags_fresh():
        while True:
            await asyncio.sleep(flags.REFRESH_SECONDS)
            await flags.refresh(db, force=True)

    app.state.flag_task = asyncio.get_running_loop().create_task(keep_flags_fresh())
    if run_jobs:
        app.state.scheduler = start_scheduler(db)
        log.info("in-process scheduler started")


async def _on_shutdown(app: FastAPI) -> None:
    task = getattr(app.state, "flag_task", None)
    if task:
        task.cancel()
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler:
        scheduler.shutdown(wait=False)


def create_app(db=None, *, start_jobs: bool | None = None, seed: bool | None = None, serve_spa: bool = True) -> FastAPI:
    import state
    from accounts.routes import use_senders
    from core import errors, modules
    from core.health import router as health_router
    from core.logging import configure as configure_logging
    from core.middleware import RequestContextMiddleware
    from core.observability import init_sentry
    from core.settings import settings

    cfg = settings.app
    if cfg.is_production and (problems := settings.problems()):
        raise ConfigError("Refusing to start in production:\n- " + "\n- ".join(problems))
    configure_logging(cfg.log_level, json_lines=cfg.log_json)
    init_sentry("api")

    if db is None:
        from motor.motor_asyncio import AsyncIOMotorClient
        db = AsyncIOMotorClient(cfg.mongo_url, tz_aware=True)[cfg.db_name]
    state.set_db(db)
    use_senders(None)                                  # OTP senders are rebuilt from settings for this app

    run_jobs = cfg.inprocess_scheduler if start_jobs is None else start_jobs
    do_seed = cfg.qa_mode if seed is None else seed

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await _on_startup(app, db, run_jobs=run_jobs, do_seed=do_seed)
        try:
            yield
        finally:
            await _on_shutdown(app)

    app = FastAPI(title=f"{cfg.brand_name} API", version=cfg.release, docs_url="/api/swagger",
                  openapi_url="/api/openapi.json", lifespan=lifespan)

    # Middleware (last added runs first): request context wraps everything, so even CORS and domain routing
    # responses carry a request id.
    from features.website import install_domain_middleware
    install_domain_middleware(app)                    # member websites on their own domain / <slug>.SITES_DOMAIN
    if cfg.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=cfg.cors_origins, allow_credentials=True,
                           allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(RequestContextMiddleware, hsts=cfg.is_production)
    errors.install(app)

    api = APIRouter(prefix="/api")
    api.include_router(health_router)
    for m in modules.load():
        api.include_router(m.router)
        if m.public_router is not None:              # pages outside /api, e.g. member websites at /s/<name>
            app.include_router(m.public_router)
    app.include_router(api)

    if serve_spa:
        from core.spa import mount_spa
        mount_spa(app)                               # last: its catch-all answers anything left unmatched
    return app


def _default_app():
    from core.settings import settings
    return None if settings.app.lazy else create_app()


app = _default_app()
