# Load test

## What was run (4 Nov 2026), measured

Set-up:

- A real MongoDB (8.3) with **10,000 existing accounts**: 8,051 free, 1,147 on the ₹1,999 plan, 605 on L1, 197 on L2, with their usage and about 45,000 events (`scripts/loadtest/seed_accounts.py`).
- The app with 2 workers, started the way production starts it.
- Every AI call and every web search set to take 6 seconds and go through the same queue as a real one (`LLM_FAKE_LATENCY_MS=6000`).
- Everything on one small test machine: 2 CPU cores, shared by the database, the app and the load generator.

### Run A: 500 webinar attendees at once

500 people arriving over 50 seconds. Each one signs up by OTP and then uses every webinar tool, with only 2–8 seconds between tools. That's harder than a real webinar, where Akshat spaces the tools out.

- 56,086 requests, **0 failed**
- All 500 signed up: login code median 0.07 s
- Screens without AI (home, readiness, goal map, LinkedIn score, cases, file): median 0.01–0.06 s, slowest 0.5 s
- Niche Snapshot (AI): median 8 s, 95% within 28 s
- Case scoring (AI): median 16 s, 95% within 31 s
- Meeting Brief (search + AI, two calls): median 19 s, 95% within 51 s
- Machine CPU at the peak: about 91%

### Run B: 500 paid members at once

500 existing members (₹1,999, L1, L2) log in and use the paid tools during the day: home, cases, Action Hub chat, Akshat AI, and making and downloading decks.

- 18,280 requests, **0 errors**
- 217 deck requests were correctly refused because those members had used their monthly deck limit
- Deck made: median 6.2 s, of which drawing the PowerPoint and PDF is about 0.2 s; download 0.01 s
- Action Hub chat: 6.0 s (the AI time itself)

### What the test found and what was fixed

- **Brief too slow:** the first run had the Meeting Brief at a median of 57 s (slowest 80 s). News for a company is now kept for 6 hours, so repeat companies are instant. The AI queue now holds 48 calls at once per worker, and the webinar tools wait up to 45 s for a slot instead of 15 s. If the AI is still busy, the page tries once more on its own.
- **Login-code limit too low:** the global cap on login codes was 300 a minute, which would have turned away part of a 500-person QR rush. It's now 1,200 a minute.
- **Dropped connections:** 16 requests in the first run were dropped connections caused by the test server's short keep-alive. Production already starts with 75 s, and the rerun with it had none.

## What this does not prove (untested)

- **Real AI speed and limits.** The 6-second figure is an estimate. The real limit is your Anthropic account's rate limit: 2 workers × 48 calls ≈ 1,000 calls a minute at a busy moment. Check Console › Limits before the webinar.
- **Railway and Atlas.** Their network and machine size weren't part of this test. The test machine was small, so Railway should do at least as well, but that hasn't been measured.
- **Real web search time.** It was set to 6 s; real searches can take longer.
- **Pitch videos.** Uploading 100 MB from phones wasn't load tested.

## How to run it again on staging

```bash
cd backend
MONGO_URL=... DB_NAME=hub_load python ../scripts/loadtest/seed_accounts.py 10000
QA_MODE=true LLM_FAKE_LATENCY_MS=6000 OTP_MAX_PER_IP_HOUR=100000 \
  uvicorn server:app --workers 2 --port 8001 --timeout-keep-alive 75
locust -f ../scripts/loadtest/locustfile.py --host http://localhost:8001 -u 500 -r 10 -t 6m --headless Attendee
locust -f ../scripts/loadtest/locustfile.py --host http://localhost:8001 -u 500 -r 10 -t 6m --headless Member
```

`OTP_MAX_PER_IP_HOUR` is raised only because every simulated person comes from one machine. Never use `QA_MODE` on the live database.
