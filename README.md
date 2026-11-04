# Consultation Hub (new app)

The software layer of Akshat Dani's High Value Consulting funnel. Logo AD × SK.

- **Free account** — opened on the ₹99 webinar by mobile OTP. Each webinar tool once, then view-only.
- **₹1,999 plan** — ₹1,999 + GST a month, or ₹20,000 + GST a year.
- **L1** — ₹5,000 + GST a month, with the 4-3-2-1 action program inside.
- **L2 Mentorship** — ₹1.5L, sold by the team, switched on in Admin. L1 billing pauses during L2 and restarts after 6 months.

This is a new app. It does not touch the current hub (consultant.akshatdani.com).

## What's built (stage 1)

- Login by mobile OTP (WhatsApp first, SMS fallback), "What's inside" page for visitors
- The six webinar tools: Readiness Score, Starting Point (Niche Snapshot + Goal Map), cases, Meeting Brief, LinkedIn Score, My Consulting File
- Plans and Razorpay billing for all four levels, the one-time ₹1,999 offer when someone cancels L1, L2 pause/restart
- Admin: pulse, live webinar numbers, webinar report + group-session list (CSV), members, live case + group session settings, switches, vendors, jobs, knowledge base

Stages 2–4 (the rest of the ₹1,999 plan, L1, L2) are in the product spec.

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI app (`server.py`); tools in `features/`, plans in `plans.py`, billing in `billing/`, admin in `admin/` |
| `backend/gpts/` | All 52 GPT prompts from the current hub, one file each, for L1 and L2 (see its README) |
| `frontend/` | React app in Akshat's design system (dark only), served by FastAPI |
| `scripts/qa_server.py` | Whole app on sample data: no database, no keys, no network |
| `scripts/loadtest/` | Webinar load test (Locust) |
| `docs/` | Handover, QA report, load test, API, backend design; `docs/reference/` = current hub's working document |

## Run it locally (test mode)

```bash
cd backend && pip install -r requirements-dev.txt
cd ../frontend && yarn install && yarn build
cd ../backend && python ../scripts/qa_server.py      # http://localhost:8765
```

Test mode: every vendor is fake, the OTP code shows on screen (000000 also works), and demo logins work:
`POST /api/qa/login` with `{}` (free), `{"plan":"member"}`, `{"plan":"l1"}`, `{"plan":"l2"}` or `{"role":"admin"}`.

Tests: `cd backend && pytest` · Build: `cd frontend && yarn build`

## Deploy

One Docker image on Railway (`Dockerfile`, `railway.json`). Health check: `/api/health`.
Settings: `backend/.env.example`. What the developer needs to set up: `docs/HANDOVER.md`.
