# Consultation Hub (new app)

The software layer of Akshat Dani's High Value Consulting funnel. Logo AD × SK.

- **Free account** — opened on the ₹99 webinar by mobile OTP. Each webinar tool once, then view-only.
- **₹1,999 plan** — ₹1,999 + GST a month, or ₹20,000 + GST a year.
- **L1** — ₹5,000 + GST a month, with the 4-3-2-1 action program inside.
- **L2 Mentorship** — ₹1.5L, sold by the team, switched on in Admin. L1 billing pauses during L2 and restarts after 6 months.

This is a new app. It does not touch the current hub (consultant.akshatdani.com).

## What's built (all four levels)

**Free account (webinar)**: login by mobile OTP, Readiness Score, Starting Point (Niche Snapshot + Goal Map), a case, Meeting Brief, LinkedIn Score, My Consulting File. Each tool once, then view-only.

**₹1,999 plan**: everything above, plus Weekly Case from real news, Presentation Builder, Visual Builder, Website Builder, Listen mode, Doc Reader, Progress Report, Support.

**L1**: everything above, plus the 4-3-2-1 action program, group calls with Akshat, recordings and workbooks, Session Recap Packs, the 18 Action Hub tools, Akshat AI, Offer Card, Career Story Bank, Industry Insight Pack, Portfolio Project, Pitch Practice (video), Research Notebook.

**L2 Mentorship**: everything above, plus the 34 Mentorship tools, Warm Network Finder, Outreach Drafter, Opportunity Radar, Discovery Call Prep, Proposal Follow-through, Client Diagnostic (with a public link for the client), Social Media Builder, Bootcamps.

**Billing**: Razorpay for all four levels, the one-time ₹1,999 offer when someone cancels L1, L1 pause during L2 and restart after 6 months. No free trial.

**Admin**: pulse, live webinar numbers, webinar report, members (grant, start L2), support inbox, Akshat AI questions, program, calls and events, recaps, library, bootcamps, weekly case, knowledge base, website domains, switches, vendors, jobs.

Calls are group calls only. There are no one-to-one calls anywhere in the app.

**Outside services**: Razorpay (payments), MSG91 (SMS login codes), AiSensy (WhatsApp), Anthropic (all AI text and web
search), Google Gemini (pitch videos and audio). Decks are made by the app itself.

**Start here**: `docs/CONSULTATION_HUB_A_TO_Z.md` explains the whole app in plain words.

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI app (`server.py`); tools in `features/` (one file each), plans and limits in `plans.py`, billing in `billing/`, admin in `admin/` |
| `backend/gpts/` | All 52 GPT prompts from the current hub, one file each, for L1 and L2 (see its README) |
| `frontend/` | React app in Akshat's design system (dark only), served by FastAPI |
| `scripts/qa_server.py` | Whole app on sample data: no database, no keys, no network |
| `scripts/loadtest/` | Load test: seed 10,000 accounts, then 500 webinar attendees or 500 paid members (Locust) |
| `docs/` | A-to-Z guide, handover, WhatsApp templates, QA report, load test, API, backend design, build guide; `docs/reference/` = the current hub's and the Leadership hub's working documents |

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
