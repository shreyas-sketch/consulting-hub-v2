"""Central runtime configuration — the only module that reads the process environment.

Design
------
* **One source of truth.** Every environment variable the app understands is declared here, typed, with its default
  and a one-line note. Other modules ask `settings.<section>.<name>`; they never call `os.environ` themselves.
* **Read at access time.** Each value is a property that reads the environment when it is asked for. That keeps the
  object cheap, lets tests override a value with `monkeypatch.setenv` and lets an operator change a variable and
  restart a worker without an import-order surprise. Parsing is centralised (`env_bool`, `env_int`, `env_float`,
  `env_list`), so a malformed value falls back to its default instead of crashing a request.
* **Fail fast in production.** `settings.problems()` lists the misconfigurations that would make the app unsafe or
  broken (missing JWT secret, http public URL, fake vendors…). `server.create_app` refuses to start in production when
  the list is not empty, instead of failing on the first request that needs the value.

Sections: `app`, `auth`, `otp`, `llm`, `gemini`, `aisensy`, `msg91`, `razorpay`, `sites`, `pitch`.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_TRUE = ("1", "true", "yes", "on", "y")


# ------------------------------------------------------------------------------------------------ parsing helpers ----
def env_str(name: str, default: str = "") -> str:
    raw = os.environ.get(name)
    return default if raw is None or raw.strip() == "" else raw.strip()


def env_opt(name: str) -> Optional[str]:
    return env_str(name) or None


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def env_list(name: str, default: str = "") -> list[str]:
    return [p.strip() for p in (os.environ.get(name) or default).split(",") if p.strip()]


def env_raw(name: str) -> Optional[str]:
    """The raw value, untouched (None when unset). For the few callers that need to know 'unset' vs 'empty'."""
    return os.environ.get(name)


BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


# ------------------------------------------------------------------------------------------------------- sections ----
class _App:
    @property
    def env(self) -> str:                       # development | test | staging | production
        return env_str("APP_ENV", "development").lower()

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def qa_mode(self) -> bool:                  # whole app on fake vendors + sample data (refused in production)
        return env_bool("QA_MODE", False)

    @property
    def brand_name(self) -> str:
        return env_str("BRAND_NAME", "Consultation Hub")

    @property
    def public_base_url(self) -> str:
        return env_str("PUBLIC_BASE_URL", "http://localhost:8765").rstrip("/")

    @property
    def mongo_url(self) -> str:
        return env_str("MONGO_URL", "mongodb://localhost:27017")

    @property
    def db_name(self) -> str:
        return env_str("DB_NAME", "consultation_hub")

    @property
    def log_level(self) -> str:
        return env_str("LOG_LEVEL", "INFO").upper()

    @property
    def log_json(self) -> bool:                 # one JSON object per log line (Railway / log drains)
        return env_bool("LOG_JSON", self.is_production)

    @property
    def cors_origins(self) -> list[str]:
        return env_list("CORS_ORIGINS")

    @property
    def lazy(self) -> bool:                     # tests import server without building the default app
        return env_str("APP_LAZY") == "1"

    @property
    def inprocess_scheduler(self) -> bool:      # off when an external cron calls /api/jobs/tick
        return env_bool("INPROCESS_SCHEDULER", True)

    @property
    def ingest_key(self) -> str:                # X-Ingest-Key for external cron calls
        return env_str("INGEST_KEY")

    @property
    def frontend_build_dir(self) -> Path:
        return Path(env_str("FRONTEND_BUILD_DIR", str(REPO_DIR / "frontend" / "build")))

    @property
    def sentry_dsn(self) -> str:
        return env_str("SENTRY_DSN")

    @property
    def sentry_traces_rate(self) -> float:
        return env_float("SENTRY_TRACES_SAMPLE_RATE", 0.05)

    @property
    def release(self) -> str:
        return env_str("RAILWAY_GIT_COMMIT_SHA", "dev")[:12]

    @property
    def trusted_proxy_hops(self) -> int:
        return env_int("TRUSTED_PROXY_HOPS", 1)


class _Auth:
    @property
    def jwt_secret(self) -> str:
        return env_str("JWT_SECRET")

    @property
    def cookie_secure(self) -> bool:
        return env_bool("COOKIE_SECURE", True)

    @property
    def cookie_samesite(self) -> str:
        return env_str("COOKIE_SAMESITE", "lax").lower()

    @property
    def cookie_domain(self) -> Optional[str]:
        return env_opt("COOKIE_DOMAIN")

    @property
    def admin_email(self) -> str:
        return env_str("ADMIN_EMAIL").lower()

    @property
    def admin_password(self) -> str:
        return os.environ.get("ADMIN_PASSWORD") or ""

    @property
    def admin_phones(self) -> set[str]:         # E.164 numbers that get the admin role on OTP login
        return set(env_list("ADMIN_PHONES"))


class _Otp:
    @property
    def secret(self) -> str:
        return env_str("OTP_SECRET") or env_str("JWT_SECRET")

    @property
    def provider_mode(self) -> str:             # live | console (console prints the code; QA default)
        return env_str("OTP_PROVIDER_MODE", "console" if settings.app.qa_mode else "live").lower()

    @property
    def max_per_ip_hour(self) -> int:
        return env_int("OTP_MAX_PER_IP_HOUR", 1000)

    @property
    def max_per_minute(self) -> int:            # global brake across the whole app; 0 = off
        return env_int("OTP_MAX_PER_MINUTE", 1200)

    @property
    def test_numbers(self) -> str:              # "phone:code,phone:code" fixed codes for store reviewers / QA
        return env_str("OTP_TEST_NUMBERS")


class _Llm:
    @property
    def api_key(self) -> str:
        return env_str("ANTHROPIC_API_KEY")

    def model(self, tier: str) -> str:
        defaults = {"fast": "claude-haiku-5-5", "strong": "claude-sonnet-5-5", "vision": "claude-opus-5-5"}
        return env_str(f"LLM_MODEL_{tier.upper()}", defaults[tier])

    @property
    def max_concurrency(self) -> int:           # in-flight AI calls per worker
        return env_int("LLM_MAX_CONCURRENCY", 48)

    @property
    def queue_wait_s(self) -> float:            # how long a call may wait for a slot before "busy"
        return env_float("LLM_QUEUE_WAIT_S", 15)

    @property
    def timeout_s(self) -> float:
        return env_float("LLM_TIMEOUT_S", 45)

    @property
    def fake_latency_ms(self) -> int:           # load tests: make the fake behave like a slow vendor
        return env_int("LLM_FAKE_LATENCY_MS", 0)


class _Gemini:
    @property
    def api_key(self) -> str:
        return env_str("GEMINI_API_KEY")

    @property
    def video_model(self) -> str:
        return env_str("GEMINI_MODEL")

    @property
    def tts_model(self) -> str:
        return env_str("GEMINI_TTS_MODEL")

    @property
    def tts_voice(self) -> str:
        return env_str("GEMINI_TTS_VOICE")

    @property
    def stt_model(self) -> str:
        return env_str("GEMINI_STT_MODEL")

    @property
    def poll_max_s(self) -> float:
        return env_float("GEMINI_POLL_MAX_S", 300)


class _AiSensy:
    @property
    def api_key(self) -> str:
        return env_str("AISENSY_API_KEY")

    @property
    def otp_campaign(self) -> str:
        return env_str("AISENSY_OTP_CAMPAIGN", "otp")

    def campaign(self, kind: str) -> str:
        return env_str(f"AISENSY_CAMPAIGN_{kind.upper()}", f"alert_{kind}")


class _Msg91:
    @property
    def auth_key(self) -> str:
        return env_str("MSG91_AUTH_KEY")

    @property
    def otp_template_id(self) -> str:
        return env_str("MSG91_OTP_TEMPLATE_ID")


class _Razorpay:
    @property
    def key_id(self) -> str:
        return env_str("RAZORPAY_KEY_ID")

    @property
    def key_secret(self) -> str:
        return env_str("RAZORPAY_KEY_SECRET")

    @property
    def webhook_secret(self) -> str:
        return env_str("RAZORPAY_WEBHOOK_SECRET")

    def plan_id(self, env_name: str) -> str:
        return env_str(env_name)


class _Sites:
    @property
    def domain(self) -> str:                    # wildcard domain for member sites: <slug>.SITES_DOMAIN
        return env_str("SITES_DOMAIN").lower().lstrip("*").strip(".")


class _Pitch:
    @property
    def tmp_dir(self) -> str:
        return env_str("PITCH_TMP_DIR")

    @property
    def max_concurrency(self) -> int:
        return env_int("PITCH_MAX_CONCURRENCY", 4)


class Settings:
    """`settings.app.env`, `settings.llm.model("fast")`… — see the module docstring."""

    app = _App()
    auth = _Auth()
    otp = _Otp()
    llm = _Llm()
    gemini = _Gemini()
    aisensy = _AiSensy()
    msg91 = _Msg91()
    razorpay = _Razorpay()
    sites = _Sites()
    pitch = _Pitch()

    # ---- flat aliases kept for the modules written against the first version of this file ----
    env = property(lambda self: self.app.env)
    is_production = property(lambda self: self.app.is_production)
    qa_mode = property(lambda self: self.app.qa_mode)
    brand_name = property(lambda self: self.app.brand_name)
    public_base_url = property(lambda self: self.app.public_base_url)
    mongo_url = property(lambda self: self.app.mongo_url)
    db_name = property(lambda self: self.app.db_name)
    cookie_secure = property(lambda self: self.auth.cookie_secure)
    cookie_samesite = property(lambda self: self.auth.cookie_samesite)
    cookie_domain = property(lambda self: self.auth.cookie_domain)
    sentry_dsn = property(lambda self: self.app.sentry_dsn)
    sentry_traces_rate = property(lambda self: self.app.sentry_traces_rate)
    release = property(lambda self: self.app.release)
    frontend_build_dir = property(lambda self: self.app.frontend_build_dir)
    inprocess_scheduler = property(lambda self: self.app.inprocess_scheduler)

    def problems(self) -> list[str]:
        """Misconfigurations that make a production deploy unsafe. Empty list = good to go."""
        out: list[str] = []
        a = self.app
        if len(self.auth.jwt_secret) < 32:
            out.append("JWT_SECRET must be set to a random string of at least 32 characters.")
        if a.qa_mode:
            out.append("QA_MODE must be off in production (it shows login codes on screen).")
        if not a.public_base_url.startswith("https://"):
            out.append("PUBLIC_BASE_URL must be the https:// address members open.")
        if not self.auth.cookie_secure:
            out.append("COOKIE_SECURE must be true in production.")
        if not self.auth.admin_phones and not self.auth.admin_email:
            out.append("Set ADMIN_PHONES (or ADMIN_EMAIL + ADMIN_PASSWORD) so someone can open the admin panel.")
        if a.mongo_url.startswith("mongodb://localhost"):
            out.append("MONGO_URL points at localhost; set the Atlas connection string.")
        from core.vendors import REQUIRED_KEYS
        for name in REQUIRED_KEYS:
            if env_str(f"{name.upper()}_MODE").lower() == "fake":
                out.append(f"{name.upper()}_MODE=fake is not allowed in production.")
        return out


settings = Settings()
