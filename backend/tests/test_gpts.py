"""Action Hub (L1) and Mentorship (L2) tools: catalogue, locks, chats, metering, blueprint start, soft delete."""
from conftest import qa_login, run

import llm
from features import gpts
from growth.clock import ist_month_key


def _used(c):
    return c.get("/api/me/plan").json()["limits"]["gpt"]["used"]


def _capture(monkeypatch):
    seen = []

    async def fake_chat(**kw):
        seen.append(kw)
        return kw["fake"]()
    monkeypatch.setattr(llm, "complete_chat", fake_chat)
    return seen


def test_catalogue_and_locks(seeded_client):
    c = seeded_client
    qa_login(c, plan="l1")
    a = c.get("/api/gpts", params={"program": "action"}).json()
    assert a["feature"] == "action_tools" and not a["locked"] and len(a["items"]) == 18
    by = {g["slug"]: g for g in a["items"]}
    assert by["presentation-builder"]["redirect"] == "/app/decks" and by["website-builder"]["redirect"] == "/app/website"
    assert by["define-your-niche"]["starter"] == "Let's Go!!!" and by["define-your-niche"]["last_used"] is None
    assert all(not g["locked"] for g in a["items"])
    m = c.get("/api/gpts", params={"program": "mentorship"}).json()
    assert m["locked"] and len(m["items"]) == 33 and all(g["locked"] for g in m["items"])
    assert "noteology" not in {g["slug"] for g in m["items"]}
    assert {g["slug"]: g for g in m["items"]}["editorial-website-builder"]["redirect"] == "/app/website"
    assert c.get("/api/gpts/noteology").status_code == 404
    # L1 can't use mentorship tools
    r = c.post("/api/gpts/book-builder/conversations", json={})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    # redirect: no chat, no use
    r = c.post("/api/gpts/presentation-builder/conversations", json={}).json()
    assert r == {"redirect": "/app/decks"} and _used(c) == 0
    # ₹1,999 plan can't use action tools
    qa_login(c, plan="member")
    assert c.get("/api/gpts", params={"program": "action"}).json()["locked"]
    r = c.post("/api/gpts/define-your-niche/conversations", json={})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"


def test_start_reply_and_metering(seeded_client):
    c = seeded_client
    qa_login(c, plan="l1")
    r = c.post("/api/gpts/define-your-niche/conversations", json={})
    assert r.status_code == 200, r.text
    conv = r.json()
    assert conv["slug"] == "define-your-niche" and conv["title"] == "Define Your Niche"
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["messages"][0]["text"] == "Let's Go!!!"
    reply = conv["messages"][1]["text"]
    assert "Define Your Niche" in reply and "```text" in reply and "|---|" in reply
    assert _used(c) == 1
    r = c.post(f"/api/gpts/conversations/{conv['id']}/messages", json={"text": "I ran supply chain for 18 years in FMCG"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["message"]["role"] == "assistant" and "18 years" in out["message"]["text"]
    assert out["title"].startswith("I ran supply chain")
    assert _used(c) == 2
    full = c.get(f"/api/gpts/conversations/{conv['id']}").json()
    assert len(full["messages"]) == 4 and full["title"].startswith("I ran supply chain")
    mine = c.get("/api/gpts/define-your-niche/conversations").json()["items"]
    assert [x["id"] for x in mine] == [conv["id"]] and mine[0]["count"] == 4
    card = {g["slug"]: g for g in c.get("/api/gpts", params={"program": "action"}).json()["items"]}["define-your-niche"]
    assert card["last_id"] == conv["id"] and card["last_used"]
    # a typed first message is sent instead of the starter
    r = c.post("/api/gpts/golden-pyramid/conversations", json={"text": "Should we enter the Pune market?"}).json()
    assert r["messages"][0]["text"] == "Should we enter the Pune market?" and r["title"] == "Should we enter the Pune market?"
    assert _used(c) == 3


def test_ai_failure_refunds_and_saves_nothing(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")
    conv = c.post("/api/gpts/framework-builder/conversations", json={}).json()
    assert _used(c) == 1

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_chat", boom)
    r = c.post(f"/api/gpts/conversations/{conv['id']}/messages", json={"text": "Help me build a framework"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy"
    assert _used(c) == 1
    assert len(c.get(f"/api/gpts/conversations/{conv['id']}").json()["messages"]) == 2
    r = c.post("/api/gpts/golden-pyramid/conversations", json={})
    assert r.status_code == 503 and _used(c) == 1
    assert c.get("/api/gpts/golden-pyramid/conversations").json()["items"] == []


def test_monthly_limit(seeded_client, mdb):
    c = seeded_client
    me = qa_login(c, plan="l1")
    run(mdb.usage.update_one({"_id": f"{me['user']['id']}:{ist_month_key()}"}, {"$set": {"gpt": 300}}, upsert=True))
    r = c.post("/api/gpts/define-your-niche/conversations", json={})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_blueprint_first_message_and_system_prompt(seeded_client, monkeypatch):
    c = seeded_client
    qa_login(c, plan="l1")
    seen = _capture(monkeypatch)
    # no blueprint yet: the plain starter goes first
    r = c.post("/api/gpts/linkedin-and-social-media-blueprint-builder/conversations", json={}).json()
    assert r["messages"][0]["text"] == "Build my LinkedIn & Social Media Blueprint"
    assert c.get("/api/gpts/linkedin-and-social-media-blueprint-builder").json()["has_blueprint"] is False
    s = c.post("/api/start/snapshot", json={"experiences": ["Supply chain", "Team leadership"], "enjoy": [0],
                                             "industry": "FMCG", "years": 18})
    assert s.status_code == 200, s.text
    assert c.get("/api/gpts/linkedin-and-social-media-blueprint-builder").json()["has_blueprint"] is True
    r = c.post("/api/gpts/linkedin-and-social-media-blueprint-builder/conversations", json={}).json()
    first = r["messages"][0]["text"]
    assert first.startswith("Here is my finalized Niche Blueprint from Define Your Niche:\n\n") and "FINALIZED NICHE" in first
    kw = seen[-1]
    assert kw["model"] == "fast" and kw["max_tokens"] == 8000
    assert "PARTICIPANT KNOWLEDGE BASE" in kw["system"] and "PARTICIPANT: Demo Member" in kw["system"]
    assert "HUB FORMATTING NOTE" in kw["system"] and "Never name or hint at the company" in kw["system"]
    assert kw["messages"] == [{"role": "user", "content": first}]
    # an ordinary tool: 3,000 tokens
    c.post("/api/gpts/golden-pyramid/conversations", json={})
    assert seen[-1]["max_tokens"] == 3000
    # Strategy Thinking: a server-assigned client saved on the conversation and named in the system prompt
    r = c.post("/api/gpts/strategy-thinking-framework/conversations", json={}).json()
    assert r["messages"][0]["text"].startswith("Here is my finalized Niche Blueprint")
    assert "CLIENT FOR THIS CONVERSATION" in seen[-1]["system"]
    assert "```next" in r["messages"][1]["text"] and "```client" in r["messages"][1]["text"]


def test_l2_tools_skip_knowledge_for_own_input_gpts(seeded_client, monkeypatch, mdb):
    c = seeded_client
    me = qa_login(c, plan="l2")
    seen = _capture(monkeypatch)
    c.post("/api/start/snapshot", json={"experiences": ["Sales"], "industry": "Pharma", "years": 20})
    r = c.post("/api/gpts/credibility-code/conversations", json={})
    assert r.status_code == 200, r.text
    kw = seen[-1]
    assert kw["model"] == "strong" and kw["max_tokens"] == 8000
    assert "PARTICIPANT KNOWLEDGE BASE" not in kw["system"] and "PARTICIPANT: Demo Member" in kw["system"]
    assert r.json()["messages"][0]["text"].startswith("Here is my finalized Niche Blueprint")
    c.post("/api/gpts/consulting-pricing-advisor/conversations", json={})
    assert "PARTICIPANT KNOWLEDGE BASE" in seen[-1]["system"] and seen[-1]["max_tokens"] == 3000
    # strategy client stays the same unless a different client is asked for
    conv = c.post("/api/gpts/strategy-thinking-framework/conversations", json={}).json()
    first = run(mdb.gpt_conversations.find_one({"_id": conv["id"]}))["client"]
    c.post(f"/api/gpts/conversations/{conv['id']}/messages", json={"text": "LET'S SOLVE"})
    assert run(mdb.gpt_conversations.find_one({"_id": conv["id"]}))["client"] == first
    c.post(f"/api/gpts/conversations/{conv['id']}/messages", json={"text": "Give me a different client please"})
    again = run(mdb.gpt_conversations.find_one({"_id": conv["id"]}))["client"]
    assert again["name"] != first["name"] and again["word"] != first["word"]
    assert me["user"]["id"]


def test_delete_hides_from_member_keeps_for_admin(seeded_client):
    c = seeded_client
    me = qa_login(c, plan="l1")
    conv = c.post("/api/gpts/elevator-pitch-builder/conversations", json={}).json()
    assert c.delete(f"/api/gpts/conversations/{conv['id']}").json() == {"ok": True}
    assert c.get(f"/api/gpts/conversations/{conv['id']}").status_code == 404
    assert c.post(f"/api/gpts/conversations/{conv['id']}/messages", json={"text": "hi"}).status_code == 404
    assert c.get("/api/gpts/elevator-pitch-builder/conversations").json()["items"] == []
    card = {g["slug"]: g for g in c.get("/api/gpts", params={"program": "action"}).json()["items"]}["elevator-pitch-builder"]
    assert card["last_id"] is None
    assert c.get("/api/admin/gpts/conversations", params={"user_id": me["user"]["id"]}).status_code == 403
    qa_login(c, role="admin")
    rows = c.get("/api/admin/gpts/conversations", params={"user_id": me["user"]["id"]}).json()["items"]
    assert len(rows) == 1 and rows[0]["deleted"] and rows[0]["name"] == "Elevator Pitch Builder"
    full = c.get(f"/api/admin/gpts/conversations/{conv['id']}").json()
    assert full["deleted"] and len(full["messages"]) == 2


def test_other_members_cannot_read_a_conversation(seeded_client):
    c = seeded_client
    qa_login(c, plan="l1")
    conv = c.post("/api/gpts/golden-pyramid/conversations", json={}).json()
    qa_login(c, plan="l2")
    assert c.get(f"/api/gpts/conversations/{conv['id']}").status_code == 404
    assert c.delete(f"/api/gpts/conversations/{conv['id']}").status_code == 404


def test_trim_history_keeps_first_exchange():
    msgs = []
    for i in range(60):
        msgs += [{"role": "user", "text": f"q{i}"}, {"role": "assistant", "text": f"a{i}"}]
    msgs.append({"role": "user", "text": "last"})
    out = gpts.trim_history(msgs)
    assert out[0] == {"role": "user", "content": "q0"} and out[1]["content"] == "a0"
    assert out[2]["role"] == "user" and out[-1]["content"] == "last" and len(out) <= gpts.MAX_TURNS + 2
    big = [{"role": "user", "text": "x" * 50_000}, {"role": "assistant", "text": "y" * 50_000},
           {"role": "user", "text": "z" * 10}]
    out = gpts.trim_history(big)
    assert out[-1]["content"] == "z" * 10 and sum(len(m["content"]) for m in out) <= gpts.MAX_CHARS * 1.25
    assert out[0]["role"] == "user"
