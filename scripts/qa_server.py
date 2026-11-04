"""Run the whole app locally with sample data — no Mongo, no keys, no network.

    cd backend && python ../scripts/qa_server.py            # http://localhost:8765
    PORT=9000 python ../scripts/qa_server.py

QA_MODE=true: every vendor is fake (AI, web search, payments, WhatsApp), sample cases are seeded, OTP codes
are shown on the login screen (and 000000 works), and /api/qa/login logs in demo users:
    POST /api/qa/login {}                      → free account (as on the webinar)
    POST /api/qa/login {"plan": "member"}      → ₹1,999 plan
    POST /api/qa/login {"plan": "l1"}          → L1
    POST /api/qa/login {"plan": "l2"}          → L2 Mentorship
    POST /api/qa/login {"role": "admin"}       → admin (open /admin)
Data lives in memory and is gone when the server stops. Build the frontend first
(cd frontend && yarn build) to get the UI; otherwise only the API is served.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

os.environ.setdefault("QA_MODE", "true")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("JWT_SECRET", "qa-only-secret-change-me-0123456789")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("INPROCESS_SCHEDULER", "false")
os.environ.setdefault("FRONTEND_BUILD_DIR", str(ROOT / "frontend" / "build"))
os.environ.setdefault("ADMIN_PHONES", "+919000000002")
os.environ["APP_LAZY"] = "1"

import uvicorn  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

import server  # noqa: E402

app = server.create_app(AsyncMongoMockClient()["consultation_hub_qa"], start_jobs=False, seed=True)

if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8765")), log_level="info")
