"""Webinar load test: the moment Akshat says "scan the QR and open your account".

Each simulated attendee: opens the page, signs up by OTP, then uses the webinar tools in the order the webinar
runs them (Readiness Score → Niche Snapshot → Goal Map → live case → Meeting Brief → LinkedIn Score → File).

Second scenario, Member: existing paid members (from seed_accounts.py → members.csv) log in and use paid tools
at the same time: home, Action Hub chat, Akshat AI, decks (made and downloaded), cases, plan.

Run against a STAGING copy with a real MongoDB and QA_MODE=true (fake vendors, OTP code returned by the API):

    python ../scripts/loadtest/seed_accounts.py 10000                     # 10,000 existing accounts
    QA_MODE=true LLM_FAKE_LATENCY_MS=6000 uvicorn server:app --workers 2 --port 8001
    locust -f scripts/loadtest/locustfile.py --host http://localhost:8001 -u 500 -r 10 -t 5m --headless Attendee
    locust -f scripts/loadtest/locustfile.py --host http://localhost:8001 -u 500 -r 10 -t 5m --headless Member

LLM_FAKE_LATENCY_MS makes each fake AI answer take as long as a real one and go through the same queue,
so the test shows what real AI latency does to waiting times.
"""
import csv
import itertools
import random
from pathlib import Path

from locust import HttpUser, between, task

_CSV = Path(__file__).with_name("members.csv")
_PAID = [r for r in csv.DictReader(_CSV.open())] if _CSV.exists() else []
_PAID = [r for r in _PAID if r["plan"] != "free"]
random.Random(3).shuffle(_PAID)
_NEXT = itertools.count()

ANSWER = ("The real problem is margin leakage: profit fell from 4% to 1.5% as the new stores opened. Objective: from "
          "1.5% to 3% in 90 days. Framework: margin leak check. Do first: fresh produce ordering. Owner: ops head; "
          "track wastage % weekly.")


# 40 companies: some repeat across attendees (as at a real webinar), so the 6-hour news cache helps but not fully.
COMPANIES = ["Haldiram's", "Tata Motors", "Marico", "Zydus", "Asian Paints", "Bajaj Auto", "Dabur", "Godrej Consumer",
             "Havells", "Pidilite", "Titan", "Britannia", "Mahindra Logistics", "Blue Dart", "Delhivery", "Cipla",
             "Lupin", "Apollo Hospitals", "Max Healthcare", "Infosys BPM", "Wipro", "Mphasis", "Zomato", "Nykaa",
             "Polycab", "Voltas", "Crompton", "Bikaji", "Jubilant FoodWorks", "Trent", "DMart", "Relaxo", "Page Industries",
             "Arvind", "Raymond", "Sun Pharma", "Torrent Power", "Thermax", "Kirloskar", "Amul"]


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
            self.client.post("/api/briefs", json={"company": random.choice(COMPANIES)},
                             name="brief (search + AI)")
        elif s == 5:
            self.client.post("/api/linkedin/check", json={"headline": "GM Operations at ABC Ltd", "about": "18 years in plants."},
                             name="linkedin score")
        else:
            self.client.get("/api/file", name="file")
            self.client.get("/api/me/plan", name="me/plan")


class Member(HttpUser):
    """An existing paid member during the day (₹1,999 / L1 / L2)."""
    wait_time = between(5, 20)

    def on_start(self):
        if not _PAID:
            raise RuntimeError("run seed_accounts.py first (members.csv)")
        row = _PAID[next(_NEXT) % len(_PAID)]
        self.plan = row["plan"]
        phone = row["phone"][3:]
        r = self.client.post("/api/auth/otp/request", json={"phone": phone}, name="otp request")
        d = r.json()
        self.client.post("/api/auth/otp/verify", json={"challenge_id": d["challenge_id"], "phone": phone,
                                                       "code": d.get("dev_code") or "000000"}, name="otp verify")
        self.conv = None

    @task(4)
    def home(self):
        self.client.get("/api/me/home", name="home")
        self.client.get("/api/me/plan", name="me/plan")

    @task(2)
    def cases(self):
        self.client.get("/api/cases", name="cases")

    @task(3)
    def action_hub_chat(self):
        if self.plan not in ("l1", "l2"):
            return self.client.get("/api/gpts", name="gpts list")
        if not self.conv:
            r = self.client.post("/api/gpts/define-your-niche/conversations", json={}, name="gpt start (AI)")
            self.conv = (r.json() or {}).get("id") if r.ok else None
        if self.conv:
            self.client.post(f"/api/gpts/conversations/{self.conv}/messages",
                             json={"text": "I ran supply chain for an FMCG company for 18 years. What niche fits?"},
                             name="gpt message (AI)")

    @task(2)
    def akshat_ai(self):
        if self.plan in ("l1", "l2"):
            self.client.post("/api/akshat-ai/ask", json={"question": "How do I price my first project?"},
                             name="akshat ai (AI)")

    @task(1)
    def deck(self):
        r = self.client.post("/api/decks", json={"source": "text", "title": "Cutting wastage in FMCG plants",
                                                 "audience": "Plant heads",
                                                 "notes": "Wastage is 6% of output. Target 3% in 90 days. Three levers: "
                                                          "ordering, cold chain, shift handover."},
                             name="deck make (AI + render)")
        if r.ok and (r.json() or {}).get("id"):
            did = r.json()["id"]
            self.client.get(f"/api/decks/{did}/file?kind=pptx", name="deck download pptx")
            self.client.get(f"/api/decks/{did}/file?kind=pdf", name="deck download pdf")
