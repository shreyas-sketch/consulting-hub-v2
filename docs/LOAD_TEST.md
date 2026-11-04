# Load test

## Done so far (4 Nov 2026) — smoke run only

- 60 simulated attendees, each signing up by OTP and using all six tools
- 1,108 requests, **0 failed**
- This ran on the in-memory test database with instant fake AI, so the timings **do not** show real speed. It only shows the flow works end to end under parallel users.

## Still to do before the first live webinar

Run on a staging copy with a real MongoDB:

```bash
QA_MODE=true LLM_FAKE_LATENCY_MS=6000 LLM_MAX_CONCURRENCY=32 uvicorn server:app --workers 2 --port 8001
locust -f scripts/loadtest/locustfile.py --host http://localhost:8001 -u 500 -r 10 -t 5m --headless
```

- `-u 500 -r 10`: 500 people arriving over about a minute, like the QR moment
- `LLM_FAKE_LATENCY_MS=6000`: every AI answer takes 6 seconds, like a real one, and goes through the same queue
- Watch: failures (should be 0), and how long AI answers wait in the queue

The tools that use AI on the webinar: Niche Snapshot, case scoring, Meeting Brief. Readiness Score, Goal Map and LinkedIn Score are instant (no AI).
