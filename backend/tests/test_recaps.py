"""Session Recap Pack: transcript → AI recap (validated) → audio → publish adds the KB doc and alerts L1+ members."""
from conftest import qa_login, run

import llm
from audio import tts

VTT = ("WEBVTT\n\n1\n00:00:01.000 --> 00:00:05.000\nToday we talk about pricing your first consulting project.\n\n"
       "2\n00:00:05.000 --> 00:00:09.000\nNever price by the hour when the client buys a result.\n\n"
       "3\n00:00:09.000 --> 00:00:14.000\nStart with the value of the problem to the business, then pick a fee.\n\n"
       "4\n00:00:14.000 --> 00:00:20.000\nA member asked what to do when a client says it is too expensive. "
       "Ask what result they expected and shrink the scope, not the fee.\n")


def _upload(c, title="Pricing your first project", **data):
    r = c.post("/api/admin/recaps", files={"file": ("session.vtt", VTT.encode(), "text/vtt")},
               data={"title": title, "date": "2026-11-08", **data})
    return r


def _members(c):
    for p in ("member", "l1", "l2"):
        qa_login(c, plan=p)


def test_recap_made_published_alerts_and_kb(client, mdb):
    _members(client)
    qa_login(client, role="admin")
    call = client.post("/api/admin/calls", json={"title": "Group call: pricing", "when": "2026-10-25T19:00",
                                                 "recording_url": "https://vimeo.com/76979871"}).json()
    r = _upload(client, call_id=call["id"])
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["status"] == "draft" and rec["has_audio"] and rec["audio_url"] == f"/api/recaps/{rec['id']}/audio"
    assert rec["summary"] and len(rec["key_ideas"]) >= 2 and len(rec["action_points"]) >= 2 and rec["frameworks"]
    assert rec["questions_answered"][0]["q"] and rec["call_id"] == call["id"] and rec["words"] > 40
    assert run(mdb.kb_chunks.count_documents({})) == 0                     # only on publish

    qa_login(client, plan="l1")
    assert client.get("/api/recaps").json()["items"] == []
    assert client.get(f"/api/recaps/{rec['id']}").status_code == 404     # drafts are hidden

    qa_login(client, role="admin")
    p = client.post(f"/api/admin/recaps/{rec['id']}/publish").json()
    assert p["status"] == "published" and p["kb_chunks"] >= 1 and p["alerted"] == 3   # l1, l2, admin
    assert run(mdb.kb_docs.count_documents({})) == 1 and run(mdb.kb_chunks.count_documents({})) >= 1
    again = client.post(f"/api/admin/recaps/{rec['id']}/publish").json()
    assert again["alerted"] == 0 and again["kb_chunks"] == 0 and run(mdb.kb_docs.count_documents({})) == 1

    member_id = str(run(mdb.users.find_one({"phone": "+919000000011"}))["_id"])
    l1_id = str(run(mdb.users.find_one({"phone": "+919000000012"}))["_id"])
    assert run(mdb.inbox.count_documents({"user_id": member_id, "kind": "recap"})) == 0
    alert = run(mdb.inbox.find_one({"user_id": l1_id, "kind": "recap"}))
    assert alert["link"] == f"/app/recaps/{rec['id']}" and "Pricing" in alert["title"]

    qa_login(client, plan="l1")
    items = client.get("/api/recaps").json()["items"]
    assert [i["id"] for i in items] == [rec["id"]] and items[0]["has_audio"]
    full = client.get(f"/api/recaps/{rec['id']}").json()
    assert full["call"]["recording_url"] == "https://vimeo.com/76979871" and full["action_points"]
    a = client.get(full["audio_url"])
    assert a.status_code == 200 and a.headers["content-type"].startswith("audio/") and a.content[:4] == b"RIFF"
    part = client.get(full["audio_url"], headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and len(part.content) == 10 and part.headers["content-range"].startswith("bytes 0-9/")
    past = client.get("/api/calls").json()["past"]
    assert past[0]["recap_id"] == rec["id"]


def test_lower_plan_locked_and_admin_guard(client):
    qa_login(client, plan="member")
    r = client.get("/api/recaps")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    assert client.get("/api/recaps/x/audio").status_code == 403
    qa_login(client, plan="l1")
    assert _upload(client).status_code == 403
    assert client.get("/api/admin/recaps").status_code == 403


def test_ai_failure_and_bad_shape_store_nothing(client, mdb, monkeypatch):
    qa_login(client, role="admin")

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = _upload(client)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy"

    async def junk(**kw):
        return {"summary": "Too short", "key_ideas": [], "action_points": "do it"}
    monkeypatch.setattr(llm, "complete_json", junk)
    assert _upload(client).status_code == 503
    assert run(mdb.recaps.count_documents({})) == 0


def test_audio_failure_keeps_recap_and_retry(client, monkeypatch):
    qa_login(client, role="admin")
    real = tts.speak

    async def down(text, **kw):
        raise tts.TTSError("down")
    monkeypatch.setattr(tts, "speak", down)
    rec = _upload(client).json()
    assert rec["has_audio"] is False and rec["audio_error"]
    assert client.post(f"/api/admin/recaps/{rec['id']}/audio").status_code == 503
    monkeypatch.setattr(tts, "speak", real)
    fixed = client.post(f"/api/admin/recaps/{rec['id']}/audio").json()
    assert fixed["has_audio"] and fixed["audio_error"] is None


def test_upload_rules_edit_unpublish_delete(client, mdb):
    qa_login(client, role="admin")
    bad = client.post("/api/admin/recaps", files={"file": ("x.pdf", b"%PDF", "application/pdf")}, data={"title": "Session"})
    assert bad.status_code == 400
    short = client.post("/api/admin/recaps", files={"file": ("x.txt", b"Hello there.", "text/plain")}, data={"title": "Session"})
    assert short.status_code == 400 and short.json()["detail"]["code"] == "empty"
    assert _upload(client, call_id="nope").status_code == 400
    assert _upload(client, date="8 Nov").status_code == 400
    rec = _upload(client).json()
    body = {"title": "Pricing, edited", "date": "2026-11-09", "summary": "We talked about pricing by the value of the result, not by the hour.",
            "key_ideas": ["Price the result", "Shrink scope, not fee"], "frameworks": [{"name": "Value pricing", "how_to_use": "Find the value first."}],
            "action_points": ["Write your fee for one project", "Test it with one client"], "questions_answered": []}
    e = client.put(f"/api/admin/recaps/{rec['id']}", json=body).json()
    assert e["title"] == "Pricing, edited" and e["date"] == "2026-11-09" and e["has_audio"]
    assert client.put(f"/api/admin/recaps/{rec['id']}", json={**body, "key_ideas": ["one"]}).status_code == 400
    client.post(f"/api/admin/recaps/{rec['id']}/publish")
    assert client.post(f"/api/admin/recaps/{rec['id']}/unpublish").json()["status"] == "draft"
    assert client.get("/api/admin/recaps").json()["items"][0]["id"] == rec["id"]
    assert client.delete(f"/api/admin/recaps/{rec['id']}").json()["ok"]
    assert run(mdb.kb_docs.count_documents({})) == 0 and run(mdb.kb_chunks.count_documents({})) == 0
    assert run(mdb.blobs.count_documents({"kind": "recap_audio"})) == 0
