# Load test

## Done so far (4 Nov 2026): smoke runs only

- Stage 1: 60 simulated attendees, 1,108 requests, **0 failed**
- After all stages were added: 60 simulated attendees for 90 seconds, 2,156 requests, **0 failed**
- Both ran on the in-memory test database with instant fake AI, so the timings **do not** show real speed. They only show the webinar flow works end to end with many people at once.

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

Pitch Practice is the heaviest tool (videos up to 100 MB). At most `PITCH_MAX_CONCURRENCY` (4) videos are analysed at once per worker; others wait. Check upload limits on Railway before launch.
