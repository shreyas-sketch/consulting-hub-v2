"""Listen mode: script → audio → blob; replays free; the weekly case's audio made once and shared."""
from conftest import qa_login, run

import llm
from audio import tts


def _used(c):
    return c.get("/api/me/plan").json()["limits"]["audio"]["used"]


def _publish_weekly(c):
    c.post("/api/auth/logout")
    qa_login(c, role="admin")
    cid = c.post("/api/admin/weekly/generate").json()["item"]["id"]
    c.post("/api/auth/logout")
    return cid


def test_case_and_brief_audio_then_free_replay(seeded_client, mdb):
    c = seeded_client
    qa_login(c, plan="member")
    r = c.post("/api/listen", json={"source": "case", "id": "hospital-claims"})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["url"].startswith("/api/blobs/") and not t["cached"] and not t["shared"]
    assert "Pause here" in t["script"] and 40 <= t["words"] <= 600
    a = c.get(t["url"])
    assert a.status_code == 200 and a.headers["content-type"].startswith("audio/")
    assert c.post("/api/listen", json={"source": "case", "id": "hospital-claims"}).json()["cached"] is True
    assert _used(c) == 1
    b = c.post("/api/briefs", json={"company": "Zydus", "meeting_with": "CFO"}).json()
    tb = c.post("/api/listen", json={"source": "brief", "id": b["id"]}).json()
    assert tb["title"] == "Brief: Zydus" and "Zydus" in tb["script"]
    assert _used(c) == 2
    mine = c.get("/api/listen").json()["items"]
    assert {m["source"] for m in mine} == {"case", "brief"} and all("script" not in m or m["script"] is None for m in mine)
    blob = run(mdb.blobs.find_one({"_id": t["url"].rsplit("/", 1)[1]}))
    assert blob["public"] is False
    c.post("/api/auth/logout")
    assert c.get(t["url"]).status_code == 401                          # private audio needs the owner
    qa_login(c, plan="member", phone="9000000041")
    assert c.post("/api/listen", json={"source": "brief", "id": b["id"]}).status_code == 404   # someone else's brief


def test_weekly_case_audio_is_shared(seeded_client, mdb):
    c = seeded_client
    cid = _publish_weekly(c)
    qa_login(c, plan="member")
    src = c.get("/api/listen/sources").json()
    assert src["weekly"][0]["id"] == cid and src["weekly"][0]["track"] is None and src["weekly"][0]["free"] is False
    first = c.post("/api/listen", json={"source": "case", "id": cid}).json()
    assert first["shared"] and not first["cached"] and _used(c) == 1
    c.post("/api/auth/logout")
    qa_login(c, plan="member", phone="9000000042")
    assert c.get("/api/listen/sources").json()["weekly"][0]["free"] is True
    second = c.post("/api/listen", json={"source": "case", "id": cid}).json()
    assert second["cached"] and second["url"] == first["url"] and _used(c) == 0
    assert c.get("/api/listen").json()["items"][0]["url"] == first["url"]
    c.post("/api/auth/logout")
    assert c.get(first["url"]).status_code == 200                      # public blob
    assert run(mdb.audio_tracks.count_documents({"ref_id": cid})) == 2


def test_free_locked_limit_and_refunds(seeded_client, mdb, monkeypatch):
    c = seeded_client
    qa_login(c, plan="free")
    r = c.post("/api/listen", json={"source": "case", "id": "hospital-claims"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    c.post("/api/auth/logout")
    qa_login(c, plan="member")

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = c.post("/api/listen", json={"source": "case", "id": "it-attrition"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy" and _used(c) == 0
    monkeypatch.undo()

    async def mute(text, **kw):
        raise tts.TTSError("down")
    monkeypatch.setattr(tts, "speak", mute)
    r = c.post("/api/listen", json={"source": "case", "id": "it-attrition"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "audio_busy" and _used(c) == 0
    monkeypatch.undo()
    for cid in ("retail-chain-margins", "d2c-skincare-cac", "auto-parts-delivery", "hospital-claims", "it-attrition"):
        assert c.post("/api/listen", json={"source": "case", "id": cid}).status_code == 200
    r = c.post("/api/listen", json={"source": "case", "id": "restaurant-aggregators"})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"
    assert c.post("/api/listen", json={"source": "case", "id": "it-attrition"}).json()["cached"]   # replays still free
    assert c.post("/api/listen", json={"source": "case", "id": "nope"}).status_code == 404


def test_long_script_is_cut_to_600_words(seeded_client, monkeypatch):
    async def long(**kw):
        return {"script": "This is one sentence of the case. " * 200}
    monkeypatch.setattr(llm, "complete_json", long)
    c = seeded_client
    qa_login(c, plan="member")
    t = c.post("/api/listen", json={"source": "case", "id": "coaching-conversions"}).json()
    assert t["words"] <= 600 and t["script"].endswith(".")
