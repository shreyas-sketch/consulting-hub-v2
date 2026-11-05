"""The application kernel: settings, error envelope, request context middleware, module registry."""
import pytest
from fastapi import APIRouter

from tests.conftest import qa_login


# ------------------------------------------------------------------------------------------------------ settings ----
def test_settings_are_read_at_access_time(monkeypatch):
    from core.settings import settings
    monkeypatch.setenv("LLM_MAX_CONCURRENCY", "7")
    assert settings.llm.max_concurrency == 7
    monkeypatch.setenv("LLM_MAX_CONCURRENCY", "not-a-number")
    assert settings.llm.max_concurrency == 48                    # bad value → default, never a crash
    monkeypatch.setenv("LLM_MODEL_FAST", "some-model")
    assert settings.llm.model("fast") == "some-model"


def test_production_problems_listed(monkeypatch):
    from core.settings import settings
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "short")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://example.com")
    monkeypatch.setenv("RAZORPAY_MODE", "fake")
    probs = " ".join(settings.problems())
    for needle in ("JWT_SECRET", "QA_MODE", "PUBLIC_BASE_URL", "COOKIE_SECURE", "RAZORPAY_MODE=fake"):
        assert needle in probs


def test_production_refuses_to_start_with_unsafe_config(monkeypatch, mdb):
    import server
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(server.ConfigError):
        server.create_app(mdb, start_jobs=False, seed=False, serve_spa=False)


def test_production_config_clean_when_set(monkeypatch):
    from core.settings import settings
    for k, v in {"APP_ENV": "production", "JWT_SECRET": "x" * 40, "QA_MODE": "false",
                 "PUBLIC_BASE_URL": "https://hub.example.com", "COOKIE_SECURE": "true",
                 "ADMIN_PHONES": "+919000000001", "MONGO_URL": "mongodb+srv://u:p@cluster/x"}.items():
        monkeypatch.setenv(k, v)
    assert settings.problems() == []


# -------------------------------------------------------------------------------------------------------- errors ----
def test_app_error_keeps_wire_format():
    from core.errors import LimitReached, NotFound, error
    e = NotFound("Case not found.")
    assert e.status_code == 404 and e.detail == {"code": "not_found", "msg": "Case not found."}
    e = LimitReached("Used up.", feature="case", used=1, limit=1)
    assert e.status_code == 402 and e.detail["feature"] == "case" and e.detail["code"] == "limit"
    e = error(422, "start_date", "Pick a date.")
    assert type(e).__name__ == "InvalidInput" and e.detail == {"code": "start_date", "msg": "Pick a date."}


def test_unknown_route_and_typed_error_envelope(client):
    r = client.get("/api/cases/does-not-exist")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "not_logged_in"
    qa_login(client)
    r = client.get("/api/cases/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"detail": {"code": "not_found", "msg": "Case not found."}}


def test_unhandled_error_is_a_clean_500(mdb):
    import server
    from fastapi.testclient import TestClient
    app = server.create_app(mdb, start_jobs=False, seed=False, serve_spa=False)
    boom = APIRouter()

    @boom.get("/api/_boom")
    async def _boom():
        raise RuntimeError("secret internals")
    app.include_router(boom)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/_boom", headers={"X-Request-ID": "req-abcdef123"})
    assert r.status_code == 500
    body = r.json()["detail"]
    assert body["code"] == "server_error" and "secret" not in body["msg"]
    assert body["request_id"] == "req-abcdef123"


# ---------------------------------------------------------------------------------------------------- middleware ----
def test_request_id_and_security_headers(client):
    r = client.get("/api/health")
    rid = r.headers["x-request-id"]
    assert len(rid) == 32
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    r = client.get("/api/health", headers={"X-Request-ID": "edge-12345678"})
    assert r.headers["x-request-id"] == "edge-12345678"
    r = client.get("/api/health", headers={"X-Request-ID": "bad id with spaces\n"})
    assert r.headers["x-request-id"] != "bad id with spaces\n"


def test_readiness_uses_bound_database(client):
    r = client.get("/api/health/ready")
    assert r.status_code in (200, 503)
    assert "mongo" in r.json()


# ------------------------------------------------------------------------------------------------------- modules ----
def test_every_registered_module_mounts_a_router():
    from core import modules
    loaded = modules.load()
    assert len(loaded) == len(modules.ALL) == len(set(modules.ALL))
    assert all(isinstance(m.router, APIRouter) for m in loaded)
