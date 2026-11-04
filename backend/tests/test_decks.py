"""Presentation Builder: sources, vendor fake, polling, download through our route, plan and limit."""
from datetime import timedelta

from conftest import qa_login, run

from growth.clock import utcnow

ANSWER = ("The real problem is margin leakage because discounts and wastage grew with the new stores. In grocery this "
          "is common. First split profit by store, then cut slow products, then fix fresh ordering. Measure wastage % weekly.")
TEXT = {"source": "text", "title": "Cutting wastage at Sharma Fresh Mart", "audience": "Owner and store managers",
        "notes": "Wastage is 9% against 4-5% at good stores. Discounts doubled. Plan: order by sell-through, mark down early, "
                 "cut slow products. Saves about ₹40 lakh a year.", "slides": 8, "tone": "boardroom", "theme": "aurum"}


def _used(c, meter="presentation"):
    return c.get("/api/me/plan").json()["limits"][meter]["used"]


def test_text_deck_ready_at_once_in_test_mode_and_served_by_us(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    opts = c.get("/api/decks/options").json()
    assert len(opts["themes"]) == 6 and len(opts["tones"]) == 5 and opts["slides"] == {"min": 6, "max": 12, "default": 8}
    r = c.post("/api/decks", json=TEXT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "ready" and d["test"] and d["slides"] == 8 and d["tone"] == "boardroom"
    assert d["download_url"] == f"/api/decks/{d['id']}/file" and d["open_url"].endswith("?inline=1")
    assert d["file_name"].endswith("-test.pdf")
    low = r.text.lower()
    assert "gamma" not in low and "example.com" not in low and "gen_id" not in low   # provider never shown
    f = c.get(d["download_url"])
    assert f.status_code == 200 and f.content.startswith(b"%PDF") and b"TEST MODE" in f.content
    assert f.headers["content-type"] == "application/pdf" and f.headers["content-disposition"].startswith("attachment")
    assert c.get(d["open_url"]).headers["content-disposition"].startswith("inline")
    assert c.get("/api/decks").json()["items"][0]["id"] == d["id"]
    assert c.get(f"/api/decks/{d['id']}").json()["status"] == "ready"
    assert _used(c) == 1


def test_deck_from_case_answer_and_brief_builds_structured_input(seeded_client, monkeypatch):
    from features import decks
    sent = []
    real = decks.gamma_create

    async def spy(body, **kw):
        sent.append(body)
        return await real(body, **kw)
    monkeypatch.setattr(decks, "gamma_create", spy)
    c = seeded_client
    qa_login(c, plan="member")
    a = c.post("/api/cases/retail-chain-margins/answer", json={"answer": ANSWER}).json()["answer"]
    b = c.post("/api/briefs", json={"company": "Haldiram's", "meeting_with": "Head of Ops"}).json()
    src = c.get("/api/decks/sources").json()
    assert src["answers"][0]["id"] == a["id"] and src["answers"][0]["company"] == "Sharma Fresh Mart"
    assert src["briefs"][0]["id"] == b["id"]
    d = c.post("/api/decks", json={"source": "case", "id": a["id"], "slides": 10, "format": "pptx"}).json()
    assert d["status"] == "ready" and d["title"].startswith("Sharma Fresh Mart") and d["format"] == "pptx"
    body = sent[-1]
    assert body["numCards"] == 10 and body["exportAs"] == "pptx" and body["format"] == "presentation"
    assert body["textMode"] == "generate" and body["cardOptions"]["dimensions"] == "16x9"
    it = body["inputText"]
    assert "₹" in it and "Selling more, earning less" in it
    assert "Fresh produce ordering" in it and ANSWER[:40] in it and "Margin leak check" in it
    assert "Indian" in body["additionalInstructions"] and "never invent" in body["additionalInstructions"]
    d2 = c.post("/api/decks", json={"source": "brief", "id": b["id"], "slides": 6}).json()
    assert d2["status"] == "ready" and "Haldiram's" in d2["title"] and "Haldiram's" in sent[-1]["inputText"]
    assert "QUESTIONS FOR TODAY" in sent[-1]["inputText"]


def test_bad_source_gives_go_back(seeded_client):
    c = seeded_client
    qa_login(c, plan="member", phone="9000000031")
    b = c.post("/api/briefs", json={"company": "Zydus"}).json()
    c.post("/api/auth/logout")
    qa_login(c, plan="member")
    assert c.post("/api/decks", json={"source": "brief", "id": b["id"]}).status_code == 404     # someone else's brief
    assert c.post("/api/decks", json={"source": "case", "id": "nope"}).status_code == 404
    assert c.post("/api/decks", json={"source": "text", "title": "Hi", "notes": "short"}).status_code == 400
    assert c.post("/api/decks", json={**TEXT, "slides": 13}).status_code == 422
    assert _used(c) == 0


def test_free_locked_and_member_limit(seeded_client):
    c = seeded_client
    qa_login(c, plan="free")
    r = c.post("/api/decks", json=TEXT)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    c.post("/api/auth/logout")
    qa_login(c, plan="member")
    assert c.post("/api/decks", json=TEXT).status_code == 200
    assert c.post("/api/decks", json=TEXT).status_code == 200
    r = c.post("/api/decks", json=TEXT)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_vendor_error_refunds(seeded_client, monkeypatch):
    from features import decks

    async def down(body, **kw):
        raise decks.GammaError("HTTP 500")
    monkeypatch.setattr(decks, "gamma_create", down)
    c = seeded_client
    qa_login(c, plan="member")
    r = c.post("/api/decks", json=TEXT)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "deck_busy"
    assert _used(c) == 0


def test_pending_deck_polls_at_most_every_5_seconds_then_copies_file(seeded_client, mdb, monkeypatch):
    from features import decks
    calls = []
    state = {"status": "pending"}

    async def create(body, **kw):
        return "live-gen-1"

    async def status(gen_id, fmt, **kw):
        calls.append(gen_id)
        return {"status": state["status"], "exportUrl": "https://files.vendor.example/x.pdf", "gammaUrl": "https://vendor/x"}

    async def download(url, title, **kw):
        return b"%PDF-1.4 real deck"
    monkeypatch.setattr(decks, "gamma_create", create)
    monkeypatch.setattr(decks, "gamma_status", status)
    monkeypatch.setattr(decks, "gamma_download", download)
    c = seeded_client
    qa_login(c, plan="member")
    d = c.post("/api/decks", json={**TEXT, "format": "pdf"}).json()
    assert d["status"] == "pending" and d["download_url"] is None and not d["test"]
    assert c.get(f"/api/decks/{d['id']}").json()["status"] == "pending" and calls == []      # polled < 5 s ago
    back = lambda: run(mdb.decks.update_one({"_id": d["id"]}, {"$set": {"polled_at": utcnow() - timedelta(seconds=6)}}))  # noqa: E731
    back()
    assert c.get(f"/api/decks/{d['id']}").json()["status"] == "pending" and calls == ["live-gen-1"]
    assert c.get(f"/api/decks/{d['id']}").json()["status"] == "pending" and len(calls) == 1
    state["status"] = "completed"
    back()
    r = c.get(f"/api/decks/{d['id']}")
    assert r.json()["status"] == "ready" and "vendor" not in r.text
    f = c.get(f"/api/decks/{d['id']}/file")
    assert f.content == b"%PDF-1.4 real deck" and f.headers["content-disposition"].startswith("attachment")
    assert run(mdb.decks.find_one({"_id": d["id"]}))["blob_id"]


def test_failed_generation_gives_the_go_back(seeded_client, mdb, monkeypatch):
    from features import decks

    async def create(body, **kw):
        return "live-gen-2"

    async def status(gen_id, fmt, **kw):
        return {"status": "failed", "error": {"message": "x"}}
    monkeypatch.setattr(decks, "gamma_create", create)
    monkeypatch.setattr(decks, "gamma_status", status)
    c = seeded_client
    qa_login(c, plan="member")
    d = c.post("/api/decks", json=TEXT).json()
    assert _used(c) == 1
    run(mdb.decks.update_one({"_id": d["id"]}, {"$set": {"polled_at": utcnow() - timedelta(seconds=6)}}))
    r = c.get(f"/api/decks/{d['id']}").json()
    assert r["status"] == "failed" and "given back" in r["error"]
    assert _used(c) == 0
    assert c.get(f"/api/decks/{d['id']}/file").status_code == 409
    run(mdb.decks.update_one({"_id": d["id"]}, {"$set": {"status": "pending", "polled_at": utcnow() - timedelta(seconds=6)}}))
    c.get(f"/api/decks/{d['id']}")
    assert _used(c) == 0                                             # refunded once only


def test_live_client_request_shape(monkeypatch):
    """The live Gamma call: Classic Generate API v1.0, X-API-KEY header, then status by generationId."""
    import asyncio

    import httpx
    from features import decks
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        if req.method == "POST":
            return httpx.Response(201, json={"generationId": "abc123"})
        return httpx.Response(200, json={"generationId": "abc123", "status": "completed", "exportUrl": "https://x/y.pdf"})
    monkeypatch.setenv("GAMMA_MODE", "live")
    monkeypatch.setenv("GAMMA_API_KEY", "sk-test")

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cl:
            gid = await decks.gamma_create({"inputText": "x", "numCards": 6}, client=cl)
            st = await decks.gamma_status(gid, "pdf", client=cl)
            return gid, st
    gid, st = asyncio.run(go())
    assert gid == "abc123" and st["status"] == "completed"
    assert str(seen[0].url) == "https://public-api.gamma.app/v1.0/generations" and seen[0].headers["X-API-KEY"] == "sk-test"
    assert str(seen[1].url) == "https://public-api.gamma.app/v1.0/generations/abc123"
