"""Visual Builder: every kind, chart numbers only from the member, edit / duplicate / delete free, plan and limit."""
from conftest import qa_login, run

import llm

PROMPTS = {
    "matrix": "Prioritise pricing, hiring, cash collection and a new warehouse for a ₹40 crore distributor",
    "process": "My five-step diagnosis process for family-run manufacturers",
    "pyramid": "What a consulting practice is built on: credibility, offer, network, process",
    "funnel": "My client funnel: 200 conversations, 40 discovery calls, 10 proposals, 4 clients",
    "mindmap": "Why owner-led businesses stall at ₹50 crore",
    "comparison": "Compare hiring a consultant, a full-time manager and doing it yourself",
}


def _used(c):
    return c.get("/api/me/plan").json()["limits"]["visuals"]["used"]


def test_every_kind_makes_a_clean_spec(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    for kind, prompt in PROMPTS.items():
        r = c.post("/api/visuals", json={"kind": kind, "prompt": prompt})
        assert r.status_code == 200, (kind, r.text)
        v = r.json()
        assert v["kind"] == kind and v["spec"]["title"]
    s = {v["kind"]: v for v in (c.get(f"/api/visuals/{i['id']}").json() for i in c.get("/api/visuals").json()["items"])}
    assert len(s["matrix"]["spec"]["quadrants"]) == 4 and all(0 <= i["x"] <= 100 for i in s["matrix"]["spec"]["items"])
    assert 3 <= len(s["process"]["spec"]["steps"]) <= 8 and 3 <= len(s["pyramid"]["spec"]["levels"]) <= 6
    assert all(st["value"] in ("", "200", "40", "10", "4") for st in s["funnel"]["spec"]["stages"])
    assert s["mindmap"]["spec"]["centre"] and len(s["mindmap"]["spec"]["branches"]) >= 2
    cmp_ = s["comparison"]["spec"]
    assert all(len(r["cells"]) == len(cmp_["columns"]) for r in cmp_["rows"])
    assert _used(c) == 6


def test_chart_uses_only_members_numbers(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="member")
    r = c.post("/api/visuals", json={"kind": "chart", "chart": "line", "prompt": "Monthly revenue in ₹ lakh",
                                     "numbers": "Apr 12, May 15, Jun 19, Jul 1,250.5"})
    assert r.status_code == 200, r.text
    sp = r.json()["spec"]
    assert sp["chart"] == "line" and sp["labels"] == ["Apr", "May", "Jun", "Jul"]
    assert sp["series"][0]["values"] == [12, 15, 19, 1250.5]
    pie = c.post("/api/visuals", json={"kind": "chart", "chart": "pie", "prompt": "Where my time goes",
                                       "numbers": "Clients 50, Sales 30, Admin 20"}).json()
    assert pie["spec"]["chart"] == "pie" and len(pie["spec"]["series"]) == 1
    # no numbers: ask for them, and the go is given back
    r = c.post("/api/visuals", json={"kind": "chart", "prompt": "A bar chart of my sales growth"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "need_numbers"
    assert _used(c) == 2
    # the AI slipping in a number the member didn't give fails the check (refund)
    real = llm.complete_json

    async def liar(**kw):
        out = await real(**kw)
        if "series" in out:
            out["series"][0]["values"][0] = 999
        return out
    monkeypatch.setattr(llm, "complete_json", liar)
    r = c.post("/api/visuals", json={"kind": "chart", "prompt": "Sales", "numbers": "Q1 10, Q2 20, Q3 30"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy"
    assert _used(c) == 2


def test_ai_says_need_numbers(seeded_client, monkeypatch):
    async def ask(**kw):
        return {"error": "need_numbers"}
    monkeypatch.setattr(llm, "complete_json", ask)
    c = seeded_client
    qa_login(c, plan="member")
    r = c.post("/api/visuals", json={"kind": "chart", "prompt": "Growth from 10 to 20 clients"})
    assert r.status_code == 400 and _used(c) == 0


def test_llm_error_refunds(seeded_client, monkeypatch):
    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    c = seeded_client
    qa_login(c, plan="member")
    r = c.post("/api/visuals", json={"kind": "process", "prompt": PROMPTS["process"]})
    assert r.status_code == 503 and _used(c) == 0


def test_edit_duplicate_delete_are_free(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    v = c.post("/api/visuals", json={"kind": "process", "prompt": PROMPTS["process"]}).json()
    spec = v["spec"]
    spec["title"] = "My diagnosis in five steps"
    spec["steps"][0]["label"] = "Listen first"
    e = c.put(f"/api/visuals/{v['id']}", json={"spec": spec})
    assert e.status_code == 200 and e.json()["spec"]["steps"][0]["label"] == "Listen first" and e.json()["title"] == spec["title"]
    assert c.put(f"/api/visuals/{v['id']}", json={"spec": {"title": "x", "steps": []}}).status_code == 400
    dup = c.post(f"/api/visuals/{v['id']}/duplicate").json()
    assert dup["id"] != v["id"] and dup["copied_from"] == v["id"] and dup["title"].endswith("(copy)")
    assert c.delete(f"/api/visuals/{v['id']}").json()["ok"]
    assert c.get(f"/api/visuals/{v['id']}").status_code == 404
    assert [i["id"] for i in c.get("/api/visuals").json()["items"]] == [dup["id"]]
    assert _used(c) == 1
    c.post("/api/auth/logout")
    qa_login(c, plan="member", phone="9000000032")
    assert c.get(f"/api/visuals/{dup['id']}").status_code == 404                     # not yours


def test_free_locked_and_limit(seeded_client, mdb):
    c = seeded_client
    qa_login(c, plan="free")
    r = c.post("/api/visuals", json={"kind": "pyramid", "prompt": PROMPTS["pyramid"]})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    c.post("/api/auth/logout")
    uid = qa_login(c, plan="member")["user"]["id"]
    from growth.clock import ist_month_key
    run(mdb.usage.update_one({"_id": f"{uid}:{ist_month_key()}"}, {"$set": {"visuals": 10, "user_id": uid}}, upsert=True))
    r = c.post("/api/visuals", json={"kind": "pyramid", "prompt": PROMPTS["pyramid"]})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_numbers_parser():
    from features.visuals import numbers_in
    assert numbers_in("₹1,50,000 and 12.5% from 3 stores, Q4") == [150000, 12.5, 3]
