"""Career Story Bank: voice note or typed story → proof story; the audio is never stored."""
from conftest import qa_login, run

import llm
from audio import stt
from features import stories

STORY = ("When I joined the Pune plant, deliveries were late almost every week and customers were angry. I sat with the "
         "shift leads and found one machine was down most afternoons. We changed the maintenance plan and moved one "
         "shift. In three months on-time delivery went from 70% to 94%.")
AUDIO = b"\x1a\x45\xdf\xa3" + b"\x00" * 6000


def used(c, meter="story"):
    return c.get("/api/me/plan").json()["limits"][meter]["used"]


def test_question_of_the_week_rotates():
    assert len(stories.QUESTIONS) >= 20
    from datetime import datetime, timedelta, timezone
    d = datetime(2026, 11, 2, 6, tzinfo=timezone.utc)
    a, b = stories.question_of_week(d), stories.question_of_week(d + timedelta(days=7))
    assert a["text"] != b["text"] and a["week"] == "2026-W45"
    assert stories.question_of_week(d + timedelta(days=2))["text"] == a["text"]


def test_voice_note_becomes_a_story_and_audio_is_not_kept(seeded_client, mdb):
    c = seeded_client
    qa_login(c, plan="l1")
    q = c.get("/api/stories").json()
    assert q["question"]["text"] and q["items"] == [] and not q["answered_this_week"]
    r = c.post("/api/stories/voice", files={"file": ("note.webm", AUDIO, "audio/webm;codecs=opus")},
               data={"question": q["question"]["text"], "duration_s": "75"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["source"] == "voice" and s["transcript"] == stt.FAKE_TEXT
    for f in ("title", "situation", "what_i_did", "result", "what_it_proves", "linkedin_post", "pitch_line"):
        assert s[f], f
    assert used(c) == 1
    # nothing audio-like anywhere: no blob, no bytes in the story document
    assert run(mdb.blobs.count_documents({})) == 0
    doc = run(mdb.stories.find_one({"_id": s["id"]}))
    assert not any(isinstance(v, (bytes, bytearray)) for v in doc.values())
    assert not any(k in doc for k in ("audio", "audio_blob_id", "file"))
    assert c.get("/api/stories").json()["answered_this_week"]


def test_typed_story_edit_delete(seeded_client):
    c = seeded_client
    qa_login(c, plan="l1")
    r = c.post("/api/stories/text", json={"text": STORY, "question": "Tell me about a turnaround."})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["source"] == "text" and "70%" in " ".join(s["numbers"]) + s["result"]
    e = c.put(f"/api/stories/{s['id']}", json={"title": "The Pune turnaround", "situation": s["situation"],
                                               "what_i_did": s["what_i_did"], "result": s["result"],
                                               "what_it_proves": s["what_it_proves"], "numbers": ["70% to 94%", " "],
                                               "linkedin_post": s["linkedin_post"], "pitch_line": s["pitch_line"]})
    assert e.status_code == 200 and e.json()["title"] == "The Pune turnaround" and e.json()["numbers"] == ["70% to 94%"]
    assert c.get("/api/stories").json()["items"][0]["title"] == "The Pune turnaround"
    assert c.delete(f"/api/stories/{s['id']}").json() == {"ok": True}
    assert c.get(f"/api/stories/{s['id']}").status_code == 404
    assert c.post("/api/stories/text", json={"text": "too short"}).status_code == 422


def test_upload_checks(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")
    r = c.post("/api/stories/voice", files={"file": ("notes.txt", b"hello" * 400, "text/plain")})
    assert r.status_code == 415
    r = c.post("/api/stories/voice", files={"file": ("n.m4a", AUDIO, "audio/mp4")}, data={"duration_s": "900"})
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_long"
    monkeypatch.setattr(stories, "MAX_AUDIO_BYTES", 2000)
    r = c.post("/api/stories/voice", files={"file": ("n.mp3", AUDIO, "audio/mpeg")})
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"
    assert used(c) == 0


def test_story_locked_for_member(seeded_client):
    c = seeded_client
    qa_login(c, plan="member")
    assert c.post("/api/stories/text", json={"text": STORY}).status_code == 403
    r = c.post("/api/stories/voice", files={"file": ("note.webm", AUDIO, "audio/webm")})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"


def test_story_limit(seeded_client):
    c = seeded_client
    qa_login(c, plan="l1")
    for _ in range(6):
        assert c.post("/api/stories/text", json={"text": STORY}).status_code == 200
    r = c.post("/api/stories/text", json={"text": STORY})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_stt_and_ai_failures_refund(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")

    async def deaf(*a, **kw):
        raise stt.STTError("down")
    monkeypatch.setattr(stt, "transcribe", deaf)
    r = c.post("/api/stories/voice", files={"file": ("note.webm", AUDIO, "audio/webm")})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "stt_failed"
    assert used(c) == 0

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = c.post("/api/stories/text", json={"text": STORY})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy"
    assert used(c) == 0
