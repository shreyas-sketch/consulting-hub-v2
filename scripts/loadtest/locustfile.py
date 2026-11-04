"""Webinar load test: the moment Akshat says "scan the QR and open your account".

Each simulated attendee: opens the page, signs up by OTP, then uses the webinar tools in the order the webinar
runs them (Readiness Score → Niche Snapshot → Goal Map → live case → Meeting Brief → LinkedIn Score → File).

Run against a STAGING copy with a real MongoDB and QA_MODE=true (fake vendors, OTP code returned by the API):

    QA_MODE=true LLM_FAKE_LATENCY_MS=6000 LLM_MAX_CONCURRENCY=32 uvicorn server:app --workers 2 --port 8001
    locust -f scripts/loadtest/locustfile.py --host http://localhost:8001 -u 500 -r 10 -t 5m --headless

LLM_FAKE_LATENCY_MS makes each fake AI answer take as long as a real one and go through the same queue,
so the test shows what real AI latency does to waiting times.
"""
import random

from locust import HttpUser, between, task

ANSWER = ("The real problem is margin leakage: profit fell from 4% to 1.5% as the new stores opened. Objective: from "
          "1.5% to 3% in 90 days. Framework: margin leak check. Do first: fresh produce ordering. Owner: ops head; "
          "track wastage % weekly.")


class Attendee(HttpUser):
    wait_time = between(2, 8)

    def on_start(self):
        self.client.get("/", name="page /")
        phone = "9" + "".join(random.choice("0123456789") for _ in range(9))
        r = self.client.post("/api/auth/otp/request", json={"phone": phone}, name="otp request")
        d = r.json()
        self.client.post("/api/auth/otp/verify", json={"challenge_id": d["challenge_id"], "phone": phone,
                                                       "code": d.get("dev_code") or "000000", "name": "Load Test",
                                                       "utm": {"src": "webinar"}}, name="otp verify")
        self.step = 0

    @task
    def next_tool(self):
        s = self.step
        self.step += 1
        if s == 0:
            self.client.get("/api/me/home", name="home")
            self.client.post("/api/readiness", json={"scores": {k: random.randint(2, 9) for k in
                                                                ("diagnosis", "offer", "acquisition", "pricing", "delivery", "visibility")},
                                                     "potential": 8}, name="readiness")
        elif s == 1:
            self.client.post("/api/start/snapshot", json={"experiences": ["Supply chain", "Team leadership", "Cost cutting"],
                                                          "enjoy": [0], "industry": "FMCG", "years": 18}, name="snapshot (AI)")
        elif s == 2:
            self.client.post("/api/start/goal/preview", json={"monthly_goal_inr": 300000, "fee_inr": 50000}, name="goal preview")
            self.client.put("/api/start/goal", json={"monthly_goal_inr": 300000, "fee_inr": 50000}, name="goal save")
        elif s == 3:
            self.client.get("/api/cases", name="cases")
            self.client.post("/api/cases/retail-chain-margins/answer", json={"answer": ANSWER}, name="case answer (AI)")
        elif s == 4:
            self.client.post("/api/briefs", json={"company": random.choice(["Haldiram's", "Tata Motors", "Marico", "Zydus"])},
                             name="brief (search + AI)")
        elif s == 5:
            self.client.post("/api/linkedin/check", json={"headline": "GM Operations at ABC Ltd", "about": "18 years in plants."},
                             name="linkedin score")
        else:
            self.client.get("/api/file", name="file")
            self.client.get("/api/me/plan", name="me/plan")
