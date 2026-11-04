"""Regression tests for the L1 / ₹1,999 pre-launch review (each one failed before its fix).

Pitch: length checks (engine duration, required browser duration, 0 mvhd), member-wide 30-minute pause, monthly fair use.
Website: AI edit returns the editor state, one WhatsApp per lead burst, own domains as requests the team connects,
images follow the page rules. Weekly case: one current case, failed runs are retried. Akshat AI: only real answers count.
Wrong-shaped AI fields give the busy message (or are dropped), never a 500. Recaps leave the knowledge base when hidden.
Doc / notebook caps hold under parallel uploads. Support: reopening by reply respects the open-question cap.
Prompts and tool replies never name an AI vendor."""
import asyncio
import json
import os
import re
import struct
import time
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import qa_login, run

import llm
from growth.clock import utcnow

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 5000
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def mp4(seconds=62.0, pad=4096) -> bytes:
    ftyp = struct.pack(">I4s4sI", 16, b"ftyp", b"isom", 0)
    mvhd_body = b"\x00\x00\x00\x00" + struct.pack(">IIII", 0, 0, 1000, int(seconds * 1000)) + b"\x00" * 80
    mvhd = struct.pack(">I4s", 8 + len(mvhd_body), b"mvhd") + mvhd_body
    moov = struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd
    mdat = struct.pack(">I4s", 8 + pad, b"mdat") + b"\x00" * pad
    return ftyp + mdat + moov


@pytest.fixture
def tmpdir_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PITCH_TMP_DIR", str(tmp_path))
    return tmp_path


def used(c, meter):
    return c.get("/api/me/plan").json()["limits"][meter]["used"]


def take(c, tid, data, ct, name, duration=None):
    params = {"filename": name}
    if duration is not None:
        params["duration_s"] = duration
    return c.post(f"/api/pitch/{tid}/take", params=params, content=data, headers={"Content-Type": ct})


def new_practice(c, **body):
    r = c.post("/api/pitch", json={"pitch_type": "elevator", **body})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def past_pause(mdb):
    run(mdb.pitch_threads.update_many({}, {"$set": {"last_upload_at": utcnow() - timedelta(minutes=31)}}))


# ------------------------------------------------------------------ 1. Pitch: the 8-minute rule ----
def test_pitch_length_needs_a_real_duration(seeded_client, mdb, tmpdir_env):
    from features import pitch
    c = seeded_client
    qa_login(c, plan="l1")
    tid = new_practice(c)
    # WEBM / MKV carry no length we read: the browser's duration is required
    for name, ct in (("long.mkv", "video/x-matroska"), ("long.webm", "video/webm")):
        r = take(c, tid, WEBM, ct, name)
        assert r.status_code == 422 and r.json()["detail"]["code"] == "no_duration", r.text
    assert take(c, tid, WEBM, "video/webm", "long.webm", duration=1800).status_code == 413
    # an MP4 whose mvhd says 0 (fragmented recordings) is "unknown", not 0 seconds
    p = tmpdir_env / "zero.mp4"
    p.write_bytes(mp4(seconds=0))
    assert pitch.mp4_duration(str(p)) is None
    p.unlink()
    r = take(c, tid, mp4(seconds=0), "video/mp4", "zero.mp4")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "no_duration"
    assert used(c, "pitch") == 0 and os.listdir(tmpdir_env) == []
    r = take(c, tid, mp4(seconds=0), "video/mp4", "zero.mp4", duration=61)
    assert r.status_code == 200, r.text
    assert r.json()["takes"][0]["duration_s"] == 61.0


def test_engine_duration_over_limit_is_refused_and_refunded(seeded_client, tmpdir_env, monkeypatch):
    from features import pitch_video
    c = seeded_client
    qa_login(c, plan="l1")
    tid = new_practice(c)
    seen = {}

    async def too_long(path, *, max_seconds=None, info=None, **kw):
        seen["max"] = max_seconds
        raise pitch_video.TooLong(1500.0)
    monkeypatch.setattr(pitch_video, "analyse", too_long)
    r = take(c, tid, WEBM, "video/webm", "t.webm", duration=60)          # the browser said 60 s; the engine saw 25 min
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_long"
    assert seen["max"] == 482 and used(c, "pitch") == 0 and os.listdir(tmpdir_env) == []
    assert c.get(f"/api/pitch/{tid}").json()["can_upload"]

    async def measured(path, *, fake, info=None, **kw):
        info["seconds"] = 75.0
        return fake()
    monkeypatch.setattr(pitch_video, "analyse", measured)
    r = take(c, tid, WEBM, "video/webm", "t.webm", duration=60)
    assert r.status_code == 200 and r.json()["takes"][0]["duration_s"] == 75.0     # the engine's length is kept


def test_video_engine_reads_file_duration_and_deletes(tmp_path, monkeypatch):
    from features import pitch_video
    monkeypatch.setenv("GEMINI_MODE", "live")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    video = tmp_path / "v.webm"
    video.write_bytes(WEBM)
    calls = []

    def engine(duration):
        async def handler(req: httpx.Request):
            await req.aread()
            calls.append((req.method, req.url.path))
            if req.headers.get("x-goog-upload-command") == "start":
                return httpx.Response(200, headers={"x-goog-upload-url": "https://u/up?upload_id=1"})
            if req.url.host == "u":
                return httpx.Response(200, json={"file": {"name": "files/z", "uri": "https://x/z", "state": "PROCESSING"}})
            if req.method == "GET":
                return httpx.Response(200, json={"name": "files/z", "state": "ACTIVE",
                                                 "videoMetadata": {"videoDuration": duration}})
            if req.method == "DELETE":
                return httpx.Response(200, json={})
            if "generateContent" in req.url.path:
                return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"kind": "initial"}'}]}}]})
            raise AssertionError(req.url)
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(pitch_video.TooLong) as e:
        run(pitch_video.analyse(str(video), mime="video/webm", system="S", prompt="P", fake=dict,
                                client=engine("600.5s"), poll_s=0, max_seconds=482))
    assert e.value.seconds == 600.5
    assert ("DELETE", "/v1beta/files/z") in calls and not any("generateContent" in p for _, p in calls)
    calls.clear()
    info = {}
    out = run(pitch_video.analyse(str(video), mime="video/webm", system="S", prompt="P", fake=dict,
                                  client=engine("95.25s"), poll_s=0, max_seconds=482, info=info))
    assert out == {"kind": "initial"} and info["seconds"] == 95.25 and calls[-1][0] == "DELETE"
    assert pitch_video.video_seconds({"videoMetadata": {"videoDuration": {"seconds": "12", "nanos": 500000000}}}) == 12.5
    assert pitch_video.video_seconds({"state": "ACTIVE"}) is None


# ------------------------------------------------------------------ 6. Pitch: fair use + one pause per member ----
def test_pitch_chat_and_practices_have_monthly_fair_use(seeded_client, tmpdir_env, monkeypatch):
    from features import pitch
    monkeypatch.setattr(pitch, "MAX_CHAT", 2)
    monkeypatch.setattr(pitch, "MONTHLY_CHAT", 3)
    monkeypatch.setattr(pitch, "MONTHLY_PRACTICES", 2)
    c = seeded_client
    qa_login(c, plan="l1")
    a, b = new_practice(c), new_practice(c)
    r = c.post("/api/pitch", json={"pitch_type": "elevator"})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "fair_use"
    assert c.post(f"/api/pitch/{a}/chat", json={"message": "How do I start?"}).status_code == 200

    async def boom(**kw):
        raise llm.LLMError("busy")
    real = llm.complete_chat
    monkeypatch.setattr(llm, "complete_chat", boom)
    assert c.post(f"/api/pitch/{a}/chat", json={"message": "again"}).status_code == 503       # given back
    monkeypatch.setattr(llm, "complete_chat", real)
    assert c.post(f"/api/pitch/{a}/chat", json={"message": "again"}).status_code == 200
    d = c.post(f"/api/pitch/{b}/chat", json={"message": "and here?"})
    assert d.status_code == 200 and d.json()["chat_left"] == 0 and d.json()["chat_month_left"] == 0
    r = c.post(f"/api/pitch/{b}/chat", json={"message": "one more"})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "fair_use"
    assert used(c, "pitch") == 0                     # fair use, not the plan meter


def test_pitch_pause_is_per_member_across_practices(seeded_client, mdb, tmpdir_env):
    c = seeded_client
    uid = qa_login(c, plan="l1")["user"]["id"]
    a, b = new_practice(c), new_practice(c)
    assert take(c, a, mp4(), "video/mp4", "a.mp4").status_code == 200
    r = take(c, b, mp4(), "video/mp4", "b.mp4")
    assert r.status_code == 429 and r.json()["detail"]["code"] == "cooldown"
    one = c.get(f"/api/pitch/{b}").json()
    assert not one["can_upload"] and 1790 <= one["cooldown_seconds_remaining"] <= 1800
    assert all(not x["can_upload"] for x in c.get("/api/pitch").json()["items"])
    past_pause(mdb)
    run(mdb.pitch_members.update_one({"_id": uid}, {"$set": {"busy_until": utcnow() + timedelta(minutes=5)}}))
    r = take(c, b, mp4(), "video/mp4", "b.mp4")                 # a take of theirs is still being analysed elsewhere
    assert r.status_code == 409 and r.json()["detail"]["code"] == "busy"
    assert run(mdb.pitch_threads.find_one({"_id": b}))["busy_until"] is None          # the practice lock was released
    run(mdb.pitch_members.update_one({"_id": uid}, {"$set": {"busy_until": None}}))
    assert take(c, b, mp4(), "video/mp4", "b.mp4").status_code == 200
    assert run(mdb.pitch_members.find_one({"_id": uid}))["busy_until"] is None


# ------------------------------------------------------------------ 2. Website: AI edit shows the proposal ----
def test_ai_edit_returns_the_editor_state_with_the_proposal(client):
    c = client
    qa_login(c, plan="member")
    site = c.post("/api/website/build", json={}).json()["site"]
    hero = next(s for s in site["pages"][0]["sections"] if s["type"] == "hero")
    r = c.post(f"/api/website/sections/{hero['id']}/ai", json={"page": "home", "instruction": "make it shorter please"})
    assert r.status_code == 200 and r.json()["changed"] is True
    body = r.json()
    assert body["site"]["proposal"]["section_id"] == hero["id"] and body["proposal"] and "looks" in body
    r = c.post(f"/api/website/sections/{hero['id']}/ai", json={"page": "home", "instruction": "change the colours"})
    assert r.status_code == 200 and "site" in r.json()


# ------------------------------------------------------------------ 3. Website: one WhatsApp per site per hour ----
def test_every_lead_in_the_inbox_but_one_whatsapp_an_hour(client, mdb, monkeypatch):
    from features import website
    from notify import channels, service
    fake = channels.FakeChannel()
    monkeypatch.setenv("WHATSAPP_ALERTS", "true")
    monkeypatch.setitem(service._state, "wa", fake)
    monkeypatch.setitem(service._state, "wa_built", True)
    monkeypatch.setattr(service, "_quiet", lambda now: False)
    monkeypatch.setattr(website, "LEADS_PER_IP", (100, 600))
    c = client
    owner = qa_login(c, plan="member")["user"]
    slug = c.post("/api/website/build", json={}).json()["site"]["slug"]
    c.post("/api/website/publish", json={"on": True})
    c.post("/api/auth/logout")
    if 3600 - time.time() % 3600 < 5:                # don't straddle the top of the hour
        time.sleep(6)
    for i in range(6):
        r = c.post(f"/api/website/public/{slug}/leads", json={"name": f"Visitor {i}", "email": f"v{i}@acme.in", "message": "hi"})
        assert r.status_code == 200
    assert run(mdb.inbox.count_documents({"user_id": owner["id"], "kind": "site_lead"})) == 6
    assert [u for u, _ in fake.sent] == [owner["id"]]


# ------------------------------------------------------------------ 4. Website: own domains ----
@pytest.fixture
def hub(mdb, monkeypatch):
    import server
    from features import website
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://hub.example.com")
    monkeypatch.setenv("SITES_DOMAIN", "sites.example.com")
    website.clear_host_cache()
    app = server.create_app(mdb, start_jobs=False, seed=False, serve_spa=False)
    with TestClient(app) as c:
        yield c
    website.clear_host_cache()


def _member_site(c, phone, publish=True):
    qa_login(c, plan="l1", phone=phone)
    sid = c.post("/api/website/build", json={}).json()["site"]["id"]
    if publish:
        c.post("/api/website/publish", json={"on": True})
    return sid


def _as_admin(c, fn):
    c.post("/api/auth/logout")
    qa_login(c, role="admin")
    try:
        return fn()
    finally:
        c.post("/api/auth/logout")


def test_infrastructure_hosts_are_refused(hub):
    c = hub
    _member_site(c, "9811111111", publish=False)
    for bad in ("healthcheck.railway.app", "web-production-1a2b.up.railway.app", "x.railway.internal", "localhost",
                "dev.localhost", "10.0.0.1", "hub.example.com", "x.hub.example.com", "sites.example.com",
                "asha.sites.example.com"):
        r = c.put("/api/website/domain", json={"domain": bad})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_domain", bad
    assert c.get("/api/health", headers={"host": "healthcheck.railway.app"}).status_code == 200


def test_domain_is_a_request_until_the_team_connects_it(hub, mdb, monkeypatch):
    from features import website
    from jobs import registry
    c = hub
    own = {"host": "www.victim-consulting.in"}
    a = _member_site(c, "9811111111")
    st = c.put("/api/website/domain", json={"domain": "www.victim-consulting.in"}).json()["site"]
    assert st["domain_status"] == "pending"
    website.clear_host_cache()
    assert c.get("/api/health", headers=own).status_code == 200          # not routed: the hub still answers

    async def cname(d):
        return ["hub.example.com"]
    monkeypatch.setattr(website, "lookup_cname", cname)
    chk = c.post("/api/website/domain/check").json()
    assert chk["check"]["ok"] and not chk["check"]["connected"] and chk["site"]["domain_status"] == "pending"
    c.post("/api/auth/logout")
    b = _member_site(c, "9822222222")                                    # someone else may ask for the same name
    r = c.put("/api/website/domain", json={"domain": "www.victim-consulting.in"})
    assert r.status_code == 200 and r.json()["site"]["domain_status"] == "pending"
    c.post("/api/auth/logout")

    def connect_a_then_b():
        rows = {x["site_id"]: x for x in c.get("/api/admin/website/domains").json()["items"]}
        assert rows[a]["check"]["ok"] and rows[a]["name"] == "Demo Member" and rows[b]["check"] is None
        assert c.post(f"/api/admin/website/domains/{a}", json={"status": "connected"}).status_code == 200
        rows = {x["site_id"]: x for x in c.get("/api/admin/website/domains").json()["items"]}
        assert rows[a]["domain_status"] == "connected" and rows[b]["taken_by"] and rows[b]["domain_status"] == "pending"
        return c.post(f"/api/admin/website/domains/{b}", json={"status": "connected"})
    r = _as_admin(c, connect_a_then_b)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "domain_taken"
    website.clear_host_cache()
    page = c.get("/", headers=own)
    assert page.status_code == 200 and "<main>" in page.text                 # A's site, now that the team connected it

    # A drops below L1: the site stops showing at once, and the domain is freed 30 days later
    qa_login(c, plan="member", phone="9811111111")
    website.clear_host_cache()
    assert c.get("/", headers=own).status_code == 404
    now = utcnow()
    assert run(registry.run(mdb, "site_domains_release", now))["result"]["marked"] == 1
    assert run(registry.run(mdb, "site_domains_release", now + timedelta(days=10)))["result"]["released"] == 0
    assert run(registry.run(mdb, "site_domains_release", now + timedelta(days=31)))["result"]["released"] == 1
    s = run(mdb.sites.find_one({"_id": a}))
    assert "domain" not in s and s["domain_request"] == "www.victim-consulting.in" and s["domain_status"] == "pending"
    website.clear_host_cache()
    assert c.get("/api/health", headers=own).status_code == 200
    r = _as_admin(c, lambda: c.post(f"/api/admin/website/domains/{b}", json={"status": "connected"}))
    assert r.status_code == 200


def test_old_unverified_claims_are_not_routed(hub, mdb):
    from features import website
    c = hub
    a = _member_site(c, "9811111111")
    c.post("/api/auth/logout")
    b = _member_site(c, "9822222222")
    c.post("/api/auth/logout")
    # a claim saved before this change: the unique `domain` field with status "waiting"
    run(mdb.sites.update_one({"_id": a}, {"$set": {"domain": "www.old-claim.in", "domain_status": "waiting"}}))
    run(mdb.sites.update_one({"_id": b}, {"$set": {"domain_request": "www.old-claim.in", "domain_status": "pending"}}))
    website.clear_host_cache()
    assert c.get("/api/health", headers={"host": "www.old-claim.in"}).status_code == 200
    r = _as_admin(c, lambda: c.post(f"/api/admin/website/domains/{b}", json={"status": "connected"}))
    assert r.status_code == 200
    sa = run(mdb.sites.find_one({"_id": a}))
    assert "domain" not in sa and sa["domain_request"] == "www.old-claim.in"
    assert run(mdb.sites.find_one({"_id": b}))["domain"] == "www.old-claim.in"


# ------------------------------------------------------------------ 14. Website: images follow the page rules ----
def test_site_images_only_for_live_sites_or_the_owner(client):
    c = client
    qa_login(c, plan="member")
    slug = c.post("/api/website/build", json={}).json()["site"]["slug"]
    c.post("/api/website/images/photo", files={"file": ("me.png", PNG, "image/png")})
    assert c.get(f"/s/{slug}/img/photo").status_code == 200              # the owner's preview
    c.post("/api/auth/logout")
    assert c.get(f"/s/{slug}").status_code == 404
    assert c.get(f"/s/{slug}/img/photo").status_code == 404
    qa_login(c, plan="member")
    c.post("/api/website/publish", json={"on": True})
    c.post("/api/auth/logout")
    r = c.get(f"/s/{slug}/img/photo")
    assert r.status_code == 200 and "public" in r.headers["cache-control"]
    qa_login(c, plan="member", phone="9833333333")                       # another member: a live site is public
    assert c.get(f"/s/{slug}/img/photo").status_code == 200


def test_site_images_hidden_when_owner_loses_the_plan(client):
    c = client
    qa_login(c, plan="member", phone="9844444444")
    slug = c.post("/api/website/build", json={}).json()["site"]["slug"]
    c.post("/api/website/images/logo", files={"file": ("logo.png", PNG, "image/png")})
    c.post("/api/website/publish", json={"on": True})
    qa_login(c, plan="free", phone="9844444444")
    c.post("/api/auth/logout")
    assert c.get(f"/s/{slug}").status_code == 404 and c.get(f"/s/{slug}/img/logo").status_code == 404


# ------------------------------------------------------------------ 7 + 8. Weekly case ----
def test_make_one_now_twice_leaves_one_current_case(client, mdb):
    c = client
    qa_login(c, role="admin")
    a = c.post("/api/admin/weekly/generate").json()["item"]["id"]
    b = c.post("/api/admin/weekly/generate").json()["item"]["id"]
    assert run(mdb.cases.count_documents({"origin": "news", "kind": "weekly"})) == 1
    assert run(mdb.cases.find_one({"_id": b}))["kind"] == "weekly"
    assert run(mdb.cases.find_one({"_id": a}))["kind"] == "practice"
    assert [x["current"] for x in c.get("/api/admin/weekly").json()["items"]].count(True) == 1


def test_failed_weekly_run_is_marked_failed_and_retried(mdb, monkeypatch):
    from jobs import registry
    from research import search
    assert registry.JOBS["weekly_case_retry"][1] == ("daily", 10, 30)
    real = search.news

    async def none(q, max_results=8, **kw):
        return []
    monkeypatch.setattr(search, "news", none)
    now = utcnow()
    row = run(registry.run(mdb, "weekly_case", now))
    assert row["ok"] is False and "no_news" in row["error"]
    row = run(registry.run(mdb, "weekly_case_retry", now + timedelta(hours=4)))
    assert row["ok"] is False and run(mdb.cases.count_documents({"origin": "news"})) == 0
    monkeypatch.setattr(search, "news", real)
    row = run(registry.run(mdb, "weekly_case_retry", now + timedelta(hours=5)))
    assert row["ok"] and row["result"]["published"]
    # this week has a case now (even one the team switched off): the retry does nothing
    run(mdb.cases.update_many({}, {"$set": {"active": False}}))
    row = run(registry.run(mdb, "weekly_case_retry", now + timedelta(hours=6)))
    assert row["ok"] and row["result"]["skipped"] == "already_published"
    assert run(mdb.cases.count_documents({"origin": "news"})) == 1


# ------------------------------------------------------------------ 9 + 10. Akshat AI ----
PRICING = " ".join(["Price your consulting offer by the value of the result for the owner, never by the hour."] * 40)


def test_akshat_ai_counts_only_real_answers(seeded_client, mdb, monkeypatch):
    from features import akshat_ai, kb
    c = seeded_client
    qa_login(c, plan="l1")
    r = c.post("/api/akshat-ai/ask", json={"question": "How do I find my first client?"})   # empty knowledge base
    assert r.status_code == 200 and r.json()["status"] == "queued" and r.json()["counted"] is False
    assert used(c, "akshat_ai") == 0
    run(kb.ingest(mdb, "Session 1 – Pricing", PRICING))
    kb.reset_kb_cache()
    for kind in ("not_covered", "decline"):
        monkeypatch.setattr(akshat_ai, "_fake", lambda q, ch, k=kind: {"kind": k, "answer": "", "sources": []})
        r = c.post("/api/akshat-ai/ask", json={"question": f"How do I price my consulting offer ({kind})?"})
        assert r.status_code == 200 and r.json()["counted"] is False
        assert used(c, "akshat_ai") == 0
    monkeypatch.setattr(akshat_ai, "_fake", lambda q, ch: {"kind": "answer", "answer": "Price the result. " * 4, "sources": [1]})
    r = c.post("/api/akshat-ai/ask", json={"question": "How do I price my consulting offer?"})
    assert r.json()["status"] == "answered" and r.json()["counted"] is True and used(c, "akshat_ai") == 1


def test_akshat_ai_wrong_shapes_and_vendor_words(seeded_client, mdb, monkeypatch):
    from features import akshat_ai, kb
    run(kb.ingest(mdb, "Session 1 – Pricing", PRICING))
    kb.reset_kb_cache()
    c = seeded_client
    qa_login(c, plan="l1")
    monkeypatch.setattr(akshat_ai, "_fake", lambda q, ch: {"kind": "answer", "sources": 1,
                                                           "answer": "As Claude from Anthropic I say: price the result, not the hour."})
    r = c.post("/api/akshat-ai/ask", json={"question": "How do I price my consulting offer?"})
    assert r.status_code == 200, r.text
    msg = r.json()["message"]
    assert msg["sources"] == [{"title": "Session 1 – Pricing"}]              # a number, not a list: fallback titles
    assert "Claude" not in msg["text"] and "Anthropic" not in msg["text"] and "price the result" in msg["text"]
    monkeypatch.setattr(akshat_ai, "_fake", lambda q, ch: {"kind": ["answer"], "answer": "x" * 40})
    before = used(c, "akshat_ai")
    r = c.post("/api/akshat-ai/ask", json={"question": "How do I price my consulting offer now?"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy" and used(c, "akshat_ai") == before


# ------------------------------------------------------------------ 10. Other wrong-shaped AI fields ----
def test_insight_pack_wrong_shapes(seeded_client, monkeypatch):
    from features import insights
    orig = insights._fake
    c = seeded_client
    qa_login(c, plan="l1")

    def news_dict(industry, niche, results):
        out = orig(industry, niche, results)
        out["news"] = {"i": 1, "why": "x"}
        return out
    monkeypatch.setattr(insights, "_fake", news_dict)
    r = c.post("/api/insights", json={"industry": "FMCG"})
    assert r.status_code == 200 and r.json()["news"] == []

    def trends_dict(industry, niche, results):
        out = orig(industry, niche, results)
        out["trends"] = {"trend": "x"}
        return out
    monkeypatch.setattr(insights, "_fake", trends_dict)
    before = used(c, "insight")
    r = c.post("/api/insights", json={"industry": "FMCG"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy" and used(c, "insight") == before


def test_doc_summary_and_notebook_wrong_shapes(client, monkeypatch):
    from features import docs, notebook
    c = client
    qa_login(c, plan="l1")
    body = ("Margins fell in the north region by 4 percent last quarter. The board agreed to review pricing. " * 30).encode()
    doc = c.post("/api/docs", files={"file": ("report.txt", body, "text/plain")}).json()
    real_sum = docs.fake_summary
    monkeypatch.setattr(docs, "fake_summary", lambda t, b: {**real_sum(t, b), "numbers": {"figure": "4", "meaning": "x"}})
    r = c.post(f"/api/docs/{doc['id']}/summary", json={})
    assert r.status_code == 200 and r.json()["summary"]["numbers"] == []

    pid = c.post("/api/notebook", json={"title": "Pricing"}).json()["id"]
    c.post(f"/api/notebook/{pid}/sources/text", json={"title": "Notes", "text": body.decode()})
    real_gen = notebook._fake_gen
    for kind, key in (("briefing", "sections"), ("faq", "items"), ("study", "quiz"), ("timeline", "events")):
        monkeypatch.setattr(notebook, "_fake_gen", lambda k, t, u, x, key=key: {**real_gen(k, t, u, x), key: {"q": "x"}})
        before = used(c, "doc_q")
        r = c.post(f"/api/notebook/{pid}/generate", json={"kind": kind})
        assert r.status_code in (422, 503), (kind, r.status_code, r.text)
        assert used(c, "doc_q") == before


def test_recap_frameworks_wrong_shape(client, monkeypatch):
    from features import recaps
    real = recaps.fake_recap
    monkeypatch.setattr(recaps, "fake_recap", lambda t, x: {**real(t, x), "frameworks": {"name": "x"},
                                                            "questions_answered": "none"})
    vtt = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:05.000\n" + "Never price by the hour when the client buys a result. " * 20
    qa_login(client, role="admin")
    r = client.post("/api/admin/recaps", files={"file": ("s.vtt", vtt.encode(), "text/vtt")}, data={"title": "Pricing"})
    assert r.status_code == 200, r.text
    assert r.json()["frameworks"] == [] and r.json()["questions_answered"] == []


# ------------------------------------------------------------------ 11. Recaps leave the knowledge base when hidden ----
def test_recap_unpublish_removes_it_from_akshat_ai(client, mdb):
    from features import kb
    vtt = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:05.000\n" + "Never price by the hour when the client buys a result. " * 20
    c = client
    qa_login(c, role="admin")
    rid = c.post("/api/admin/recaps", files={"file": ("s.vtt", vtt.encode(), "text/vtt")},
                 data={"title": "Pricing", "date": "2026-11-08"}).json()["id"]
    pub = c.post(f"/api/admin/recaps/{rid}/publish").json()
    assert pub["kb_chunks"] >= 1 and pub["kb_doc_id"]
    off = c.post(f"/api/admin/recaps/{rid}/unpublish").json()
    assert off["status"] == "draft" and off["kb_doc_id"] is None
    assert run(mdb.kb_docs.count_documents({})) == 0 and run(mdb.kb_chunks.count_documents({})) == 0
    kb.reset_kb_cache()
    assert run(kb.search(mdb, "price by the hour")) == []
    again = c.post(f"/api/admin/recaps/{rid}/publish").json()               # publishing again adds it back
    assert again["kb_chunks"] >= 1 and again["kb_doc_id"] and again["alerted"] == 0
    kb.reset_kb_cache()
    assert run(kb.search(mdb, "price by the hour"))[0]["title"].startswith("Session: Pricing")


# ------------------------------------------------------------------ 12. Caps hold under parallel uploads ----
def _parallel(app, cookies, reqs):
    async def go():
        tr = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=tr, base_url="http://testserver", cookies=cookies) as ac:
            return [r.status_code for r in await asyncio.gather(*(fn(ac) for fn in reqs))]
    return asyncio.run(go())


def test_doc_and_notebook_caps_hold_in_parallel(mdb, monkeypatch):
    import server
    from features import docs, notebook
    real = docs.read_upload

    async def slow(file):
        await asyncio.sleep(0.05)              # stands in for Motor round trips / PDF parsing time
        return await real(file)
    monkeypatch.setattr(docs, "read_upload", slow)
    monkeypatch.setattr(notebook, "read_upload", slow)
    monkeypatch.setattr(notebook, "MAX_SOURCES", 3)
    app = server.create_app(mdb, start_jobs=False, seed=False, serve_spa=False)
    body = ("Margins fell in the north region last quarter. " * 40).encode()
    with TestClient(app) as c:
        qa_login(c, plan="l1")
        for i in range(18):
            assert c.post("/api/docs", files={"file": (f"d{i}.txt", body, "text/plain")}).status_code == 200
        for i in range(3):
            assert c.post("/api/notebook", json={"title": f"Project {i}"}).status_code == 200
        pid = c.get("/api/notebook").json()["items"][0]["id"]
        cookies = dict(c.cookies)
    codes = _parallel(app, cookies, [lambda ac, i=i: ac.post("/api/docs", files={"file": (f"r{i}.txt", body, "text/plain")})
                                     for i in range(4)])
    assert run(mdb.reader_docs.count_documents({})) <= 20 and codes.count(200) <= 2, codes
    _parallel(app, cookies, [lambda ac, i=i: ac.post("/api/notebook", json={"title": f"More {i}"}) for i in range(3)])
    assert run(mdb.nb_projects.count_documents({})) <= 4
    _parallel(app, cookies, [lambda ac, i=i: ac.post(f"/api/notebook/{pid}/sources/file",
                                                     files={"file": (f"s{i}.txt", body, "text/plain")}) for i in range(5)])
    assert run(mdb.nb_sources.count_documents({"project_id": pid})) <= 3
    n_src = {s["_id"] for s in run(mdb.nb_sources.find({"project_id": pid}).to_list(None))}
    assert {ch["source_id"] for ch in run(mdb.nb_chunks.find({"project_id": pid}).to_list(None))} <= n_src


# ------------------------------------------------------------------ 15. Support: reopening respects MAX_OPEN ----
def test_reply_to_closed_ticket_respects_open_cap(client, mdb, monkeypatch):
    from features import support
    monkeypatch.setattr(support, "MAX_OPEN", 2)
    c = client
    qa_login(c, plan="member")
    ids = [c.post("/api/support/tickets", json={"subject": f"Question {i}", "text": "Please help me"}).json()["id"]
           for i in range(2)]
    c.post(f"/api/support/tickets/{ids[0]}/close")
    ids.append(c.post("/api/support/tickets", json={"subject": "Question 3", "text": "Please help me"}).json()["id"])
    r = c.post(f"/api/support/tickets/{ids[0]}/reply", json={"text": "still need this"})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many"
    assert run(mdb.support_tickets.find_one({"_id": ids[0]}))["status"] == "closed"
    assert run(mdb.support_tickets.count_documents({"status": {"$ne": "closed"}})) == 2
    assert c.post(f"/api/support/tickets/{ids[1]}/reply", json={"text": "more detail"}).status_code == 200   # open: fine


# ------------------------------------------------------------------ 5. No AI vendor names in tools ----
VENDOR = re.compile(r"chat\s?gpt|\bgpts?\b|openai|claude|gemini|custom gpt|anthropic|\bllms?\b", re.I)


def test_prompts_never_name_an_ai_vendor():
    prompts = sorted((Path(__file__).resolve().parent.parent / "gpts" / "prompts").glob("*.md"))
    assert len(prompts) == 52
    hits = [(p.name, m.group(0)) for p in prompts for m in VENDOR.finditer(p.read_text(encoding="utf-8"))]
    assert hits == []


def test_tool_replies_are_stripped_of_vendor_names(client, monkeypatch):
    c = client
    qa_login(c, plan="l1")

    async def leaky(**kw):
        return "Paste this into ChatGPT. As GPT-4o by OpenAI (an LLM) I suggest: start with one client."
    monkeypatch.setattr(llm, "complete_chat", leaky)
    r = c.post("/api/gpts/elevator-pitch-builder/conversations", json={"text": "Help me with my pitch"})
    assert r.status_code == 200, r.text
    reply = r.json()["messages"][-1]["text"]
    assert not VENDOR.search(reply) and "start with one client" in reply
    conv = c.get(f"/api/gpts/conversations/{r.json()['id']}").json()
    assert not VENDOR.search(json.dumps(conv["messages"]))
    r = c.post(f"/api/gpts/conversations/{r.json()['id']}/messages", json={"text": "and then?"})
    assert not VENDOR.search(r.json()["message"]["text"])
