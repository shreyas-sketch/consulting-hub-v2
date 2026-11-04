"""Put N member accounts into a staging database before a load test (default 10,000).

    cd backend && MONGO_URL=mongodb://localhost:27017 DB_NAME=hub_load python ../scripts/loadtest/seed_accounts.py 10000

Mix (roughly what the funnel looks like a few months in): 80% free webinar accounts, 12% ₹1,999 plan, 6% L1,
2% L2. Each account gets its signup event, a few tool events and this month's usage, so the admin reports and the
hot queries run against realistic volume. Phones are +91 70000 00000 upwards; members.csv lists phone + plan so
the "members" scenario in locustfile.py can log them in. Never run against production.
"""
import csv
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pymongo import MongoClient

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
name = os.environ.get("DB_NAME", "hub_load")
if os.environ.get("APP_ENV") == "production" or "prod" in name:
    sys.exit("refusing to seed a production database")

db = MongoClient(url)[name]
now = datetime.now(timezone.utc)
month = (now + timedelta(hours=5, minutes=30)).strftime("%Y-%m")
random.seed(7)
TOOLS = {"readiness": "readiness_done", "snapshot": "snapshot_run", "goal": "goal_saved", "case": "case_answered",
         "brief": "brief_made", "linkedin": "linkedin_checked"}
users, subs, grants, usage, evs, rows = [], [], [], [], [], []

for i in range(N):
    r = random.random()
    plan = "free" if r < 0.80 else "member" if r < 0.92 else "l1" if r < 0.98 else "l2"
    oid = __import__("bson").ObjectId()
    uid = str(oid)
    phone = f"+9170{i:08d}"
    joined = now - timedelta(days=random.randint(0, 180), minutes=random.randint(0, 1440))
    users.append({"_id": oid, "phone": phone, "phone_verified_at": joined, "name": f"Seed Member {i}", "role": "user",
                  "status": "active", "created_at": joined, "first_login_at": joined, "last_login_at": joined,
                  "acquisition": {"source": "webinar", "utm": {"src": "webinar"}, "at": joined}, "seed": True})
    evs.append({"_id": str(uuid.uuid4()), "name": "signup", "ts": joined, "user_id": uid, "anon_id": None,
                "props": {"source": "webinar"}, "src": "server", "seed": True})
    used = random.sample(list(TOOLS), random.randint(1, len(TOOLS)))
    if plan == "free":
        usage.append({"_id": f"{uid}:life", "user_id": uid, **{t: 1 for t in used}})
    else:
        usage.append({"_id": f"{uid}:{month}", "user_id": uid, "month": month, **{t: random.randint(0, 3) for t in used}})
    for t in used:
        evs.append({"_id": str(uuid.uuid4()), "name": TOOLS[t], "ts": joined + timedelta(minutes=5), "user_id": uid,
                    "anon_id": None, "props": {}, "src": "server", "seed": True})
    if plan in ("member", "l1"):
        subs.append({"_id": f"sub_seed_{i}", "user_id": uid, "plan": plan, "period": "monthly", "status": "active",
                     "current_start": now - timedelta(days=10), "current_end": now + timedelta(days=20),
                     "created_at": joined, "seed": True})
    elif plan == "l2":
        grants.append({"user_id": uid, "plan": "l2", "ends_at": now + timedelta(days=120), "by": "seed", "at": now,
                       "kind": "l2"})
    rows.append((phone, plan))

db.users.delete_many({"seed": True})
db.subscriptions.delete_many({"seed": True})
db.plan_grants.delete_many({"by": "seed"})
db.events.delete_many({"seed": True})
db.usage.delete_many({"_id": {"$in": [u["_id"] for u in usage]}})
for coll, docs in (("users", users), ("subscriptions", subs), ("plan_grants", grants), ("usage", usage), ("events", evs)):
    for k in range(0, len(docs), 5000):
        if docs[k:k + 5000]:
            db[coll].insert_many(docs[k:k + 5000], ordered=False)
out = Path(__file__).with_name("members.csv")
with out.open("w", newline="") as f:
    csv.writer(f).writerows([("phone", "plan"), *rows])
counts = {p: sum(1 for _, x in rows if x == p) for p in ("free", "member", "l1", "l2")}
print(f"seeded {N} accounts into {name}: {counts}; events {len(evs)}; wrote {out.name}")
