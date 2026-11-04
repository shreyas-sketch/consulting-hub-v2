"""Regression tests for the pre-launch review (webinar tools + L2 tools): each test failed before its fix.

Items: 1 atomic count reserve, 2 diagnostic prompt privacy + safe thank-you, 3 public answer size caps,
4 free member keeps their answered case, 5/6 proposal follow-ups, 7/8/9 network import, 10 AI shapes,
11 LinkedIn token room, 12 file_viewed event, 13 Goal Map assumptions, 14 vendor rule, 15 brief pick 0,
16 social dates, 17 invented links, 18 AI queue wait."""
import asyncio
import json
from datetime import timedelta

from bson import ObjectId
from conftest import qa_login, run

import llm
from features import brief, cases, common, linkedin, network, proposals, start
from growth.clock import ist_month_key, utcnow
from research import search

ANSWER = ("The real problem is profit falling at the 5 new stores since last year because of discounts and wastage. "
          "Objective: from 1.5% to 3% profit in 90 days. Framework: margin leak check. Do first: fresh produce ordering. "
          "Owner: head of store ops, measure wastage weekly and profit monthly.")
BODY = {"company": "Desai Pumps", "person": "Rahul Desai",
        "notes": "They lose dealers every quarter and margins fell 4 points this year.",
        "fee_low_inr": 100000, "fee_high_inr": 300000}


def l2(c):
    return qa_login(c, plan="l2")["user"]["id"]


def used(c, meter):
    return c.get("/api/me/plan").json()["limits"][meter]["used"]


def published(c):
    x = c.post("/api/diagnostic", json={"topic": "Sales engine"}).json()
    return c.post(f"/api/diagnostic/{x['id']}/publish").json()


def answers_for(form, scale=4):
    return {q["id"]: (scale if q["kind"] == "scale" else "Dealers keep asking for credit.") for q in form["questions"]}


def shaped(monkeypatch, change):
    """Make the AI answer with the fake's content in a wrong shape."""
    real = llm.complete_json

    async def cj(**kw):
        raw = kw["fake"]()
        change(raw)
        return raw
    monkeypatch.setattr(llm, "complete_json", cj)
    return real


# ---------------------------------------------------------------- 1. count reserve is one atomic write ----
def test_parallel_reserve_cannot_pass_the_limit(mdb):
    uid = ObjectId()
    user = {"_id": uid, "role": "admin", "name": "X"}                  # admin = L2: 50 contacts a month
    key = f"{uid}:{ist_month_key()}"
    run(mdb.usage.insert_one({"_id": key, "user_id": str(uid), "contacts": 49}))

    class Slow:                                                         # real network latency between read and write
        def __init__(self, coll):
            self._c = coll

        def __getattr__(self, k):
            return getattr(self._c, k)

        async def find_one(self, *a, **k):
            r = await self._c.find_one(*a, **k)
            await asyncio.sleep(0.01)
            return r

    class DB:
        def __init__(self, d):
            self._d = d
            self.usage = Slow(d.usage)

        def __getattr__(self, k):
            return getattr(self._d, k)

    d = DB(mdb)

    async def go():
        return await asyncio.gather(*[network.reserve(d, user, "contacts", 1, access="network_finder") for _ in range(3)],
                                    return_exceptions=True)
    res = run(go())
    ok = [r for r in res if isinstance(r, tuple)]
    refused = [r for r in res if not isinstance(r, tuple)]
    assert len(ok) == 1 and all(getattr(e, "status_code", None) == 402 for e in refused)
    assert run(mdb.usage.find_one({"_id": key}))["contacts"] == 50


# ---------------------------------------------------------------- 2. diagnostic report: no private data, safe thank-you ----
def test_report_prompt_has_no_private_goal_and_thank_you_is_cleaned(client, mdb, monkeypatch):
    uid = l2(client)
    run(mdb.goals.insert_one({"_id": uid, "monthly_goal_inr": 500000, "fee_inr": 75000, "close_rate_pct": 25,
                              "calls_per_lead": 3, "months": 6, "updated_at": utcnow()}))
    run(mdb.snapshots.insert_one({"_id": "s1", "user_id": uid, "input": {"industry": "Pumps"}, "chosen": 0, "at": utcnow(),
                                  "options": [{"niche": "Dealer growth for pump makers", "who": "Owner-led pump makers",
                                               "title": "Dealer Growth Consultant", "value_prop": "I help pump makers grow dealers.",
                                               "fee_low": 50000, "fee_high": 150000, "yearly_low": 1, "yearly_high": 2}]}))
    p = published(client)
    seen = {}

    async def spy(**kw):
        seen[kw["task"]] = kw["prompt"]
        raw = kw["fake"]()
        raw["thank_you"] = ("Thank you, Anil. Your score shows strong sales. This report was written by ChatGPT. "
                            "Read more at https://evil.example/leak and www.spam.example today.")
        return raw
    monkeypatch.setattr(llm, "complete_json", spy)
    client.post("/api/auth/logout")
    form = client.get(f"/api/diagnostic/public/{p['public_id']}").json()
    r = client.post(f"/api/diagnostic/public/{p['public_id']}/responses",
                    json={"name": "Anil", "phone": "9876543210", "answers": answers_for(form)})
    assert r.status_code == 200, r.text
    prompt = seen["diagnostic_report"]
    assert "Dealer growth for pump makers" in prompt                               # niche / offer wording only
    assert "5,00,000" not in prompt and "75,000" not in prompt and "business goal" not in prompt.lower()
    assert "EARNING POTENTIAL" not in prompt and "1,50,000" not in prompt
    t = r.json()["thank_you"]
    assert "ChatGPT" not in t and "evil.example" not in t and "spam.example" not in t and t.startswith("Thank you, Anil")


def test_unusable_thank_you_falls_back_to_fixed_text(client, monkeypatch):
    l2(client)
    p = published(client)

    async def odd(**kw):
        raw = kw["fake"]()
        raw["thank_you"] = {"text": "not a string"}
        return raw
    monkeypatch.setattr(llm, "complete_json", odd)
    client.post("/api/auth/logout")
    form = client.get(f"/api/diagnostic/public/{p['public_id']}").json()
    r = client.post(f"/api/diagnostic/public/{p['public_id']}/responses",
                    json={"name": "Neha Rao", "phone": "9876543210", "answers": answers_for(form, 2)})
    assert r.status_code == 200 and r.json()["thank_you"].startswith("Thank you, Neha. Your overall score is 25%")


# ---------------------------------------------------------------- 3. public answers are size-capped ----
def test_public_answers_payload_is_capped(client):
    l2(client)
    p = published(client)
    client.post("/api/auth/logout")
    form = client.get(f"/api/diagnostic/public/{p['public_id']}").json()
    url = f"/api/diagnostic/public/{p['public_id']}/responses"
    a = answers_for(form)
    big = {**a, **{f"junk{i}": "x" * 1000 for i in range(3000)}}                  # ~3 MB
    r = client.post(url, json={"name": "Spam Bot", "phone": "9876543210", "answers": big})
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"
    many = {**a, **{f"j{i}": 1 for i in range(25)}}                              # small body, too many keys
    assert client.post(url, json={"name": "Spam Bot", "phone": "9876543210", "answers": many}).status_code == 422
    long = {**a, next(q["id"] for q in form["questions"] if q["kind"] == "short"): "y" * 600}
    r = client.post(url, json={"name": "Spam Bot", "phone": "9876543210", "answers": long})
    assert r.status_code == 422 and "500 characters" in json.dumps(r.json())
    assert client.post(url, json={"name": "Anil", "phone": "9876543210", "answers": a}).status_code == 200


# ---------------------------------------------------------------- 4. free member keeps their answered case ----
def test_free_keeps_read_only_view_of_answered_case(seeded_client):
    c = seeded_client
    qa_login(c, plan="free")
    assert c.post("/api/cases/retail-chain-margins/answer", json={"answer": ANSWER}).status_code == 200
    c.post("/api/auth/logout")
    qa_login(c, role="admin")
    assert c.post("/api/admin/settings", json={"live_case_id": "hospital-claims"}).status_code == 200
    c.post("/api/auth/logout")
    qa_login(c, plan="free")
    r = c.get("/api/cases/retail-chain-margins")
    assert r.status_code == 200
    one = r.json()
    assert one["case"]["read_only"] and not one["case"]["live"] and one["case"]["model_answer"] and one["answers"]
    items = c.get("/api/cases").json()["items"]
    assert items[0]["id"] == "hospital-claims" and items[0]["live"]
    mine = next(i for i in items if i["id"] == "retail-chain-margins")
    assert not mine["locked"] and mine["answered"] and mine["my_score"] is not None and items[1]["id"] == mine["id"]
    assert c.get("/api/cases/d2c-skincare-cac").status_code == 403                 # never answered: still locked
    assert c.post("/api/cases/retail-chain-margins/answer", json={"answer": ANSWER}).status_code == 403


# ---------------------------------------------------------------- 5/6. proposal follow-ups ----
def test_still_open_keeps_followups_done(client):
    l2(client)
    pid = client.post("/api/proposals", json=BODY).json()["id"]
    for s in ("sent", "fu1", "fu2", "won"):
        client.patch(f"/api/proposals/{pid}", json={"status": s})
    x = client.patch(f"/api/proposals/{pid}", json={"status": "sent"}).json()      # "Still open"
    assert [f["done"] for f in x["followups"]] == [True, True, False] and x["next"]["n"] == 3
    client.patch(f"/api/proposals/{pid}", json={"status": "draft"})
    x = client.patch(f"/api/proposals/{pid}", json={"status": "sent"}).json()      # sent again from draft: fresh start
    assert [f["done"] for f in x["followups"]] == [False, False, False] and x["next"]["n"] == 1


def test_resent_proposal_gets_its_reminder(client, mdb):
    from jobs.registry import Ctx
    l2(client)
    pid = client.post("/api/proposals", json=BODY).json()["id"]
    client.patch(f"/api/proposals/{pid}", json={"status": "sent"})
    now = utcnow()
    r1 = run(proposals.job_followups(Ctx(mdb, now + timedelta(days=3))))
    client.patch(f"/api/proposals/{pid}", json={"status": "draft"})
    doc = run(mdb.proposals.find_one({"_id": pid}))
    later = now + timedelta(days=7)
    run(mdb.proposals.update_one({"_id": pid}, {"$set": proposals.apply_status(doc, "sent", later)}))
    r2 = run(proposals.job_followups(Ctx(mdb, later + timedelta(days=3))))
    assert r1["alerts"] == 1 and r2["alerts"] == 1
    assert run(proposals.job_followups(Ctx(mdb, later + timedelta(days=3))))["alerts"] == 0    # still once per due date


# ---------------------------------------------------------------- 7/8/9. Warm Network Finder import ----
HDR = "First Name,Last Name,URL,Email Address,Company,Position,Connected On\r\n"


def test_csv_in_windows_1252_and_utf16(client):
    l2(client)
    row = "Zoë,Désai,,,Rénu Pvt Ltd,Founder,12 Mar 2019\r\n"
    r1 = client.post("/api/network/import", files={"file": ("Connections.csv", (HDR + row).encode("cp1252"), "text/csv")})
    assert r1.status_code == 200 and r1.json()["added"] == 1
    row2 = "Ananya,Iyer,,,Śrī Foods,CEO,01 Jan 2020\r\n"
    r2 = client.post("/api/network/import", files={"file": ("Connections.csv", (HDR + row2).encode("utf-16"), "text/csv")})
    assert r2.status_code == 200 and r2.json()["added"] == 1
    got = {i["name"]: i["company"] for i in client.get("/api/network").json()["items"]}
    assert got == {"Zoë Désai": "Rénu Pvt Ltd", "Ananya Iyer": "Śrī Foods"}
    assert network.decode_csv("Zoë".encode("utf-8")) == "Zoë"


def test_paste_with_spaced_header_is_read_not_500(client):
    l2(client)
    r = client.post("/api/network/paste", json={"text": "  First Name,Last Name,Company\nRavi,Mehta,Acme"})
    assert r.status_code == 200 and r.json()["added"] == 1
    assert client.get("/api/network").json()["items"][0]["name"] == "Ravi Mehta"
    r = client.post("/api/network/paste", json={"text": "First Name, Last Name"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "empty"


def test_over_cap_keeps_best_matches(client, monkeypatch):
    l2(client)
    monkeypatch.setattr(network, "CAP", 2)
    csv = (HDR + "Sunita,Rao,,,Infosys,Senior Analyst,05 Jan 2024\r\n"
           "Amit,Shah,,,TCS,Associate,05 Jan 2023\r\n"
           "Ravi,Mehta,,ravi@acme.in,Acme Pharma Pvt Ltd,Founder & MD,12 Mar 2015\r\n")
    r = client.post("/api/network/import", files={"file": ("Connections.csv", csv.encode(), "text/csv")}).json()
    names = [i["name"] for i in client.get("/api/network").json()["items"]]
    assert r["over_cap"] == 1 and r["added"] == 2 and names[0] == "Ravi Mehta" and "Sunita Rao" in names


# ---------------------------------------------------------------- 10. wrong AI shapes: refund + 503, never 500 ----
def test_snapshot_options_as_object(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="free")
    shaped(monkeypatch, lambda raw: raw.update(options={o["niche"]: o for o in raw["options"]}))
    r = c.post("/api/start/snapshot", json={"experiences": ["Sales"]})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy" and used(c, "start") == 0


def test_linkedin_headlines_as_object(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="member")
    shaped(monkeypatch, lambda raw: raw.update(headlines={h["angle"]: h["text"] for h in raw["headlines"]}))
    r = c.post("/api/linkedin/check", json={"headline": "GM Operations at ABC", "rewrite": True})
    assert r.status_code == 503 and used(c, "linkedin") == 0


def test_proposal_and_call_prep_wrong_shapes(client, monkeypatch):
    l2(client)
    shaped(monkeypatch, lambda raw: raw.update(options={o["name"]: o for o in raw["options"]}, timeline={"a": 1}))
    assert client.post("/api/proposals", json=BODY).status_code == 503 and used(client, "proposal") == 0
    shaped(monkeypatch, lambda raw: raw.update(agenda={"a": 1}, questions={"q": "x"}))
    assert client.post("/api/call-prep", json={"company": "Acme"}).status_code == 503 and used(client, "call_prep") == 0
    shaped(monkeypatch, lambda raw: raw.update(questions={"q": "x"}))
    assert client.post("/api/diagnostic", json={"topic": "Sales"}).status_code == 503 and used(client, "diagnostic") == 0
    shaped(monkeypatch, lambda raw: raw.update(posts={"n": 1}))
    assert client.post("/api/social/generate", json={"count": 1}).status_code == 503 and used(client, "posts") == 0


def test_brief_news_as_object_still_makes_a_brief(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="member")
    shaped(monkeypatch, lambda raw: raw.update(news={"i": 1}, problems={"p": 1}))
    r = c.post("/api/briefs", json={"company": "Acme"})
    assert r.status_code == 200 and r.json()["news"] == [] and r.json()["problems"] == []


# ---------------------------------------------------------------- 11. LinkedIn rewrite has room to finish ----
def test_linkedin_rewrite_token_room(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="member")
    seen = {}

    async def spy(**kw):
        seen[kw["task"]] = kw["max_tokens"]
        return kw["fake"]()
    monkeypatch.setattr(llm, "complete_json", spy)
    assert c.post("/api/linkedin/check", json={"headline": "GM Operations at ABC", "rewrite": True}).status_code == 200
    assert seen["linkedin_rewrite"] >= 1800


# ---------------------------------------------------------------- 12. file_viewed only when the File page opens ----
def test_file_view_event_only_from_the_file_page(seeded_client, mdb):
    c = seeded_client
    uid = qa_login(c, plan="free")["user"]["id"]
    for _ in range(3):                                   # Home reads /file on every visit
        assert c.get("/api/file").status_code == 200
    assert run(mdb.events.count_documents({"name": "file_viewed", "user_id": uid})) == 0
    assert c.post("/api/file/viewed").json() == {"ok": True}
    assert run(mdb.events.count_documents({"name": "file_viewed", "user_id": uid})) == 1


# ---------------------------------------------------------------- 13. Goal Map returns its assumptions ----
def test_goal_assumptions_come_back(seeded_client):
    c = seeded_client
    qa_login(c, plan="free")
    body = {"monthly_goal_inr": 300000, "fee_inr": 50000, "close_rate_pct": 50, "calls_per_lead": 2, "months": 6}
    assert c.put("/api/start/goal", json=body).status_code == 200
    g = c.get("/api/start").json()["goal"]
    assert g["close_rate_pct"] == 50 and g["calls_per_lead"] == 2
    p = c.post("/api/start/goal/preview", json={k: g[k] for k in body}).json()
    assert p["conversations_per_week"] == g["conversations_per_week"]


# ---------------------------------------------------------------- 14. vendor rule in webinar tools ----
def test_webinar_prompts_carry_the_vendor_rule():
    for mod in (start, cases, brief, linkedin):
        assert common.NO_VENDOR in mod.SYSTEM, mod.__name__


def test_vendor_names_stripped_from_member_text(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="member")
    shaped(monkeypatch, lambda raw: raw.update(summary="Scored by Claude from Anthropic: solid work.",
                                               good=["GPT-4 liked your scope.", "Clear owner."]))
    a = c.post("/api/cases/retail-chain-margins/answer", json={"answer": ANSWER}).json()["answer"]
    assert "Claude" not in a["summary"] and "Anthropic" not in a["summary"] and "GPT" not in " ".join(a["good"])


# ---------------------------------------------------------------- 15. brief pick 0 is not the last result ----
def test_brief_index_zero_is_skipped(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="member")
    res = [{"title": f"T{i}", "url": f"https://news.example/{i}", "source": "x", "published": "", "snippet": "s",
            "test": False} for i in range(1, 5)]

    async def fake_news(q, max_results=6, **k):
        return res
    monkeypatch.setattr(search, "news", fake_news)
    shaped(monkeypatch, lambda raw: raw.update(news=[{"i": 0, "why": "About result one"}, {"i": 2, "why": "Two"}]))
    b = c.post("/api/briefs", json={"company": "Acme"}).json()
    assert [n["url"] for n in b["news"]] == ["https://news.example/2"]


# ---------------------------------------------------------------- 16. impossible dates: 422, not 500 ----
def test_social_bad_month_and_date(client):
    l2(client)
    r = client.get("/api/social", params={"month": "2026-13"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "month"
    r = client.post("/api/social/generate", json={"count": 1, "start_date": "2026-02-30"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "start_date"
    assert used(client, "posts") == 0


# ---------------------------------------------------------------- 17. no invented links; the member's own stay ----
def test_invented_links_removed_own_links_kept(client, mdb, monkeypatch):
    uid = l2(client)
    run(mdb.sites.insert_one({"_id": "site1", "user_id": uid, "slug": "asha-mehta",
                              "contact": {"email": "", "whatsapp": "", "calendly": "https://cal.com/asha"}}))
    extra = " Book at https://cal.com/asha or see https://made-up.example/offer and www.fake.example now."

    def add_links(raw):
        if "variants" in raw:
            for v in raw["variants"]:
                v["text"] += extra
        if "posts" in raw:
            for p in raw["posts"]:
                p["text"] += extra
        if "context" in raw:
            raw["context"] += extra
            for f in raw["followups"]:
                f["text"] += extra
    shaped(monkeypatch, add_links)
    o = client.post("/api/outreach", json={"name": "Neha Shah", "channel": "email"}).json()
    s = client.post("/api/social/generate", json={"count": 1}).json()
    p = client.post("/api/proposals", json=BODY).json()
    texts = [v["text"] for v in o["variants"]] + [x["text"] for x in s["items"]] + \
            [p["data"]["context"], p["markdown"]] + [f["text"] for f in p["followups"]]
    for t in texts:
        assert "made-up.example" not in t and "fake.example" not in t, t
    assert all("https://cal.com/asha" in t for t in texts[:4])
    from features import diagnostic, outreach, social
    for system in (proposals.SYSTEM, outreach.SYSTEM, social.SYSTEM, diagnostic.REPORT_SYSTEM):
        assert "never include links" in system.lower()


# ---------------------------------------------------------------- 18. AI queue at the webinar spike ----
def test_queue_wait_per_call_and_default_concurrency(monkeypatch):
    monkeypatch.setattr(llm, "mode", lambda: "live")
    monkeypatch.setattr(llm, "_SEM", {"sem": None, "n": None})
    monkeypatch.delenv("LLM_MAX_CONCURRENCY", raising=False)
    assert llm._sem()._value == 48
    monkeypatch.setattr(llm, "_SEM", {"sem": None, "n": None})
    monkeypatch.setenv("LLM_MAX_CONCURRENCY", "1")
    monkeypatch.setenv("LLM_QUEUE_WAIT_S", "0.05")

    async def slow_call(**kw):
        await asyncio.sleep(0.3)
        return '{"a": 1}'
    monkeypatch.setattr(llm, "_call_text", slow_call)

    async def go():
        first = asyncio.ensure_future(llm.complete_json(task="t", system="s", prompt="p", fake=lambda: {}))
        await asyncio.sleep(0.01)
        short = await asyncio.gather(llm.complete_json(task="t", system="s", prompt="p", fake=lambda: {}),
                                     return_exceptions=True)
        long = await llm.complete_json(task="t", system="s", prompt="p", fake=lambda: {}, queue_wait=2)
        return await first, short[0], long
    first, short, long = run(go())
    assert first == {"a": 1} and isinstance(short, llm.LLMError) and long == {"a": 1}


def test_webinar_tools_wait_longer_for_a_slot(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="free")
    seen = {}

    async def spy(**kw):
        seen[kw["task"]] = kw.get("queue_wait")
        return kw["fake"]()
    monkeypatch.setattr(llm, "complete_json", spy)
    c.post("/api/start/snapshot", json={"experiences": ["Sales"]})
    c.post("/api/cases/retail-chain-margins/answer", json={"answer": ANSWER})
    c.post("/api/briefs", json={"company": "Acme"})
    assert seen == {"niche_snapshot": 45, "case_score": 45, "meeting_brief": 45}


def test_busy_gives_the_go_back_so_a_retry_counts_once(seeded_client, monkeypatch):
    """The page retries a 503 ai_busy POST once: the first try must already have handed the go back."""
    c = seeded_client
    qa_login(c, plan="free")                                           # one go for life
    real = llm.complete_json
    calls = {"n": 0}

    async def busy_once(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise llm.LLMError("AI is busy right now.")
        return await real(**kw)
    monkeypatch.setattr(llm, "complete_json", busy_once)
    r = c.post("/api/start/snapshot", json={"experiences": ["Sales"]})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy" and used(c, "start") == 0
    assert c.post("/api/start/snapshot", json={"experiences": ["Sales"]}).status_code == 200
    assert used(c, "start") == 1
