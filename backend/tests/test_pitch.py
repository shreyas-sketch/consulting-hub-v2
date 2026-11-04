"""Pitch Practice: threads, video takes (streamed to a temp file, then deleted), initial and comparison reports,
30-minute cooldown, strict validation with refunds, follow-up chat, provider words stripped, and the video engine client."""
import json
import os
import struct
from datetime import timedelta

import httpx
import pytest
from conftest import qa_login, run

import llm
from features import pitch, pitch_video
from growth.clock import utcnow


def mp4(seconds=62, pad=4096) -> bytes:
    ftyp = struct.pack(">I4s4sI", 16, b"ftyp", b"isom", 0)
    mvhd_body = b"\x00\x00\x00\x00" + struct.pack(">IIII", 0, 0, 1000, int(seconds * 1000)) + b"\x00" * 80
    mvhd = struct.pack(">I4s", 8 + len(mvhd_body), b"mvhd") + mvhd_body
    moov = struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd
    mdat = struct.pack(">I4s", 8 + pad, b"mdat") + b"\x00" * pad
    return ftyp + mdat + moov                 # moov at the end, like most phone recordings


WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 5000


@pytest.fixture
def tmpdir_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PITCH_TMP_DIR", str(tmp_path))
    return tmp_path


def used(c):
    return c.get("/api/me/plan").json()["limits"]["pitch"]["used"]


def new_thread(c, **body):
    r = c.post("/api/pitch", json={"pitch_type": "elevator", **body})
    assert r.status_code == 200, r.text
    return r.json()


def upload(c, tid, data=None, ct="video/mp4", name="take.mp4", duration=62):
    return c.post(f"/api/pitch/{tid}/take", params={"duration_s": duration, "filename": name},
                  content=mp4() if data is None else data, headers={"Content-Type": ct})


def skip_cooldown(mdb, tid):
    run(mdb.pitch_threads.update_one({"_id": tid}, {"$set": {"last_upload_at": utcnow() - timedelta(minutes=31)}}))


def test_mp4_duration_and_sniff(tmp_path):
    p = tmp_path / "a.mp4"
    p.write_bytes(mp4(seconds=95.5))
    assert abs(pitch.mp4_duration(str(p)) - 95.5) < 0.01
    assert pitch.sniff(mp4()[:64], "mp4") and pitch.sniff(WEBM[:64], "webm")
    assert not pitch.sniff(b"hello world, not a video at all....", "mp4") and not pitch.sniff(mp4()[:64], "mkv")


def test_first_take_then_cooldown_then_comparison(seeded_client, mdb, tmpdir_env):
    c = seeded_client
    qa_login(c, plan="l1")
    t = new_thread(c)
    assert t["messages"][0]["kind"] == "intro" and "Pitch Coach" in t["messages"][0]["content"]
    assert t["can_upload"] and t["takes"] == []

    r = upload(c, t["id"])
    assert r.status_code == 200, r.text
    d = r.json()
    rep = d["takes"][0]["report"]
    assert rep["kind"] == "initial" and set(rep["scorecard"]) == set(pitch.METRIC_KEYS)
    assert all(0 <= m["score"] <= 10 and m["justification"] for m in rep["scorecard"].values())
    assert len(rep["top_changes"]) == 5 and 8 <= len(rep["specific_observations"]) <= 12
    assert 4 <= len(rep["strengths"]) <= 6 and 4 <= len(rep["weaknesses"]) <= 6 and rep["practice_assignment"]
    assert d["takes"][0]["duration_s"] == 62.0                # from the file's own header
    assert not d["can_upload"] and 1790 <= d["cooldown_seconds_remaining"] <= 1800 and d["next_upload_at"]
    assert os.listdir(tmpdir_env) == []                       # temp video removed
    assert used(c) == 1

    r = upload(c, t["id"])
    assert r.status_code == 429 and r.json()["detail"]["code"] == "cooldown" and r.json()["detail"]["seconds"] > 0
    assert used(c) == 1 and os.listdir(tmpdir_env) == []

    skip_cooldown(mdb, t["id"])
    assert c.get(f"/api/pitch/{t['id']}").json()["can_upload"]
    r = upload(c, t["id"], data=WEBM, ct="video/webm;codecs=vp8,opus", name="take.webm", duration=70)
    assert r.status_code == 200, r.text
    d = r.json()
    cmp_ = d["takes"][1]["report"]
    assert cmp_["kind"] == "comparison" and d["takes"][1]["duration_s"] == 70.0
    for k in pitch.METRIC_KEYS:
        row = cmp_["scorecard"][k]
        assert row["previous_score"] == rep["scorecard"][k]["score"]
        assert row["delta"] == round(row["score"] - row["previous_score"], 1)
    assert any(cmp_["scorecard"][k]["delta"] < 0 for k in pitch.METRIC_KEYS)        # fake has one drop
    assert cmp_["improvements"] and cmp_["persisting_issues"] and len(cmp_["top_changes"]) == 5
    assert cmp_["previous_overall"] == rep["overall"]
    assert used(c) == 2 and os.listdir(tmpdir_env) == []
    items = c.get("/api/pitch").json()
    assert items["items"][0]["takes"] == 2 and items["limits"]["cooldown_minutes"] == 30 and len(items["types"]) == 4


def test_comparison_uses_stored_prior_scores(seeded_client, mdb, tmpdir_env, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")
    t = new_thread(c, pitch_type="fee")
    first = upload(c, t["id"]).json()["takes"][0]["report"]
    skip_cooldown(mdb, t["id"])
    prior_for_fake = {"scorecard": first["scorecard"]}

    async def wrong_prev(path, *, mime, system, prompt, fake, **kw):
        assert "PRIOR REPORT" in prompt and "kind" in prompt and mime == "video/mp4"
        r = pitch._fake_comparison({"pitch_type": "fee"}, prior_for_fake)
        for v in r["scorecard"].values():
            v["previous_score"], v["delta"] = 0, 99                 # the engine got these wrong
        return r
    monkeypatch.setattr(pitch_video, "analyse", wrong_prev)
    rep = upload(c, t["id"]).json()["takes"][1]["report"]
    for k in pitch.METRIC_KEYS:
        assert rep["scorecard"][k]["previous_score"] == first["scorecard"][k]["score"]
        assert rep["scorecard"][k]["delta"] != 99


def test_bad_output_and_engine_errors_refund_and_remove_temp(seeded_client, tmpdir_env, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")
    t = new_thread(c)

    async def short(path, *, fake, **kw):
        assert os.path.exists(path)
        r = fake()
        r["top_changes"] = r["top_changes"][:4]                  # must be exactly 5
        return r
    monkeypatch.setattr(pitch_video, "analyse", short)
    r = upload(c, t["id"])
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy"
    assert used(c) == 0 and os.listdir(tmpdir_env) == []

    async def scoreless(path, *, fake, **kw):
        r = fake()
        r["scorecard"]["confidence"]["score"] = "great"
        return r
    monkeypatch.setattr(pitch_video, "analyse", scoreless)
    assert upload(c, t["id"]).status_code == 503 and used(c) == 0

    async def down(path, **kw):
        raise pitch_video.VideoError("HTTP 500 from the vendor")
    monkeypatch.setattr(pitch_video, "analyse", down)
    r = upload(c, t["id"])
    assert r.status_code == 503 and r.json()["detail"]["code"] == "video_busy"
    assert "vendor" not in r.text and "500" not in r.json()["detail"]["msg"]
    assert used(c) == 0 and os.listdir(tmpdir_env) == []
    assert c.get(f"/api/pitch/{t['id']}").json()["can_upload"]     # a failed take starts no cooldown


def test_upload_checks(seeded_client, mdb, tmpdir_env, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")
    t = new_thread(c)
    r = upload(c, t["id"], data=b"x" * 5000, ct="text/plain", name="notes.txt")
    assert r.status_code == 415
    r = upload(c, t["id"], data=b"not really a video file" * 200)           # says mp4, isn't
    assert r.status_code == 415 and r.json()["detail"]["code"] == "bad_type"
    r = upload(c, t["id"], data=mp4(seconds=9 * 60), duration=60)           # the file's header wins over the browser
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_long"
    r = upload(c, t["id"], duration=9 * 60)
    assert r.status_code == 413
    monkeypatch.setattr(pitch, "MAX_BYTES", 3000)
    r = upload(c, t["id"])
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"
    assert used(c) == 0 and os.listdir(tmpdir_env) == []
    run(mdb.pitch_threads.update_one({"_id": t["id"]}, {"$set": {"busy_until": utcnow() + timedelta(minutes=5)}}))
    monkeypatch.setattr(pitch, "MAX_BYTES", 100 * 1024 * 1024)
    r = upload(c, t["id"])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "busy"            # one take at a time per practice
    assert c.post("/api/pitch", json={"pitch_type": "other"}).status_code == 422
    o = new_thread(c, pitch_type="other", setting="Board update to my old company's leadership", audience="CXOs")
    assert o["setting"].startswith("Board update") and o["audience"] == "CXOs"


def test_pitch_locked_for_member(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    r = c.post("/api/pitch", json={"pitch_type": "elevator"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"


def test_pitch_limit(seeded_client, mdb, tmpdir_env):
    c = seeded_client
    qa_login(c, plan="l1")
    for _ in range(4):
        assert upload(c, new_thread(c)["id"]).status_code == 200
        run(mdb.pitch_threads.update_many({}, {"$set": {"last_upload_at": utcnow() - timedelta(minutes=31)}}))  # the pause is per member
    r = upload(c, new_thread(c)["id"])
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"
    assert os.listdir(tmpdir_env) == []


def test_follow_up_chat_and_provider_words(seeded_client, tmpdir_env, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")
    t = new_thread(c, pitch_type="discovery")

    async def chatty(path, *, fake, **kw):
        r = fake()
        r["overall_summary"] = "Gemini 3.8 Flash says you are calm. Our Google AI engine agrees."
        return r
    monkeypatch.setattr(pitch_video, "analyse", chatty)
    d = upload(c, t["id"]).json()
    assert "Gemini" not in json.dumps(d) and "Google" not in json.dumps(d)

    r = c.post(f"/api/pitch/{t['id']}/chat", json={"message": "How do I fix the first change?"})
    assert r.status_code == 200, r.text
    msgs = r.json()["messages"]
    assert msgs[-2]["role"] == "user" and msgs[-1]["role"] == "assistant" and "**" in msgs[-1]["content"]
    assert used(c) == 1                                        # chat is not metered

    seen = {}

    async def leaky(**kw):
        seen.update(kw)
        return "As Claude by Anthropic (an LLM), I'd say: slow down."
    monkeypatch.setattr(llm, "complete_chat", leaky)
    r = c.post(f"/api/pitch/{t['id']}/chat", json={"message": "What powers you?"})
    reply = r.json()["messages"][-1]["content"]
    assert "Claude" not in reply and "Anthropic" not in reply and "LLM" not in reply and "slow down" in reply
    assert seen["messages"][0]["role"] == "user" and seen["messages"][-1]["content"].endswith("What powers you?")
    assert "FOLLOW-UP MODE" in seen["system"] and "NOT JSON" in seen["system"] and seen["model"] == "strong"

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_chat", boom)
    assert c.post(f"/api/pitch/{t['id']}/chat", json={"message": "Hello?"}).status_code == 503
    assert c.delete(f"/api/pitch/{t['id']}").json() == {"ok": True}


# ------------------------------------------------------------------ the video engine client (live, mocked HTTP) ----
def _engine(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_video_engine_live_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_MODE", "live")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    video = tmp_path / "v.mp4"
    video.write_bytes(mp4())
    calls = []
    polls = {"n": 0}

    async def handler(req: httpx.Request):
        body = await req.aread()
        calls.append((req.method, req.url.path, req.headers.get("x-goog-upload-command")))
        assert req.headers.get("x-goog-api-key") == "test-key" or req.url.params.get("upload_id")
        if req.url.path == "/upload/v1beta/files" and req.headers.get("x-goog-upload-command") == "start":
            assert req.headers["x-goog-upload-header-content-length"] == str(len(video.read_bytes()))
            assert req.headers["x-goog-upload-header-content-type"] == "video/mp4"
            return httpx.Response(200, headers={"x-goog-upload-url": "https://generativelanguage.googleapis.com/upload/v1beta/files?upload_id=u1"})
        if req.url.params.get("upload_id") == "u1":
            assert req.headers["x-goog-upload-command"] == "upload, finalize" and body == video.read_bytes()
            assert req.headers["content-length"] == str(len(body))
            return httpx.Response(200, json={"file": {"name": "files/abc", "uri": "https://x/files/abc", "state": "PROCESSING",
                                                      "mimeType": "video/mp4"}})
        if req.method == "GET" and req.url.path == "/v1beta/files/abc":
            polls["n"] += 1
            return httpx.Response(200, json={"name": "files/abc", "state": "ACTIVE" if polls["n"] > 1 else "PROCESSING"})
        if req.url.path == "/v1beta/models/gemini-3.8-flash:generateContent":
            j = json.loads(body)
            part = j["contents"][0]["parts"][0]["fileData"]
            assert part == {"mimeType": "video/mp4", "fileUri": "https://x/files/abc"}
            assert j["generationConfig"]["responseMimeType"] == "application/json" and j["systemInstruction"]["parts"][0]["text"] == "SYS"
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"text": "thinking...", "thought": True}, {"text": '```json\n{"kind": "initial", "ok": 1}\n```'}]}}]})
        if req.method == "DELETE" and req.url.path == "/v1beta/files/abc":
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {req.method} {req.url}")

    out = run(pitch_video.analyse(str(video), mime="video/mp4", system="SYS", prompt="P", fake=lambda: {},
                                  client=_engine(handler), poll_s=0))
    assert out == {"kind": "initial", "ok": 1}
    assert calls[-1][0] == "DELETE" and polls["n"] == 2


def test_video_engine_failures_still_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_MODE", "live")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    video = tmp_path / "v.webm"
    video.write_bytes(WEBM)
    deleted = []

    def make(gen_status, state="ACTIVE", text_out="{}"):
        async def handler(req: httpx.Request):
            await req.aread()
            if req.headers.get("x-goog-upload-command") == "start":
                return httpx.Response(200, headers={"x-goog-upload-url": "https://u/up?upload_id=1"})
            if req.url.host == "u":
                return httpx.Response(200, json={"file": {"name": "files/z", "uri": "https://x/z", "state": state}})
            if req.method == "DELETE":
                deleted.append(req.url.path)
                return httpx.Response(200, json={})
            if "generateContent" in req.url.path:
                if gen_status != 200:
                    return httpx.Response(gen_status, json={"error": {"message": "quota"}})
                return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text_out}]}}]})
            return httpx.Response(200, json={"state": state})
        return handler

    with pytest.raises(pitch_video.VideoError):
        run(pitch_video.analyse(str(video), mime="video/webm", system="S", prompt="P", fake=dict, client=_engine(make(400)), poll_s=0))
    with pytest.raises(pitch_video.VideoError):
        run(pitch_video.analyse(str(video), mime="video/webm", system="S", prompt="P", fake=dict,
                                client=_engine(make(200, state="FAILED")), poll_s=0))
    with pytest.raises(pitch_video.BadOutput):
        run(pitch_video.analyse(str(video), mime="video/webm", system="S", prompt="P", fake=dict,
                                client=_engine(make(200, text_out="Sorry, I can't.")), poll_s=0))
    assert deleted == ["/v1beta/files/z"] * 3


def test_video_engine_off_is_paused(seeded_client, tmpdir_env, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")
    t = new_thread(c)
    monkeypatch.setenv("GEMINI_MODE", "off")
    r = upload(c, t["id"])
    assert r.status_code == 503 and r.json()["detail"]["code"] == "paused" and used(c) == 0
    assert c.get("/api/pitch").json()["available"] is False
