"""Research Notebook: L1 gate, project cap, the four kinds of source (file, text, URL, Doc Reader doc), cited answers,
generated outputs, free notes, the cached audio overview, metering and refunds."""
from conftest import qa_login, run

import llm
from audio import tts
from test_docs import HIRING, REPORT, make_pdf, upload, use_up, used

NOTES = ("Market notes on cold chain in India. In 2023 the cold storage market was worth Rs 2,400 crore in Maharashtra. "
         "In June 2024 the state cut power tariffs for cold storage units by 10%. "
         "Small food processors say their biggest problem is paying for idle capacity in the monsoon months.")


def new_project(c, title="Cold chain in western India"):
    r = c.post("/api/notebook", json={"title": title, "description": "For my first client pitch"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def add_text(c, pid, body=NOTES, title="Market notes"):
    r = c.post(f"/api/notebook/{pid}/sources/text", json={"title": title, "text": body})
    assert r.status_code == 200, r.text
    return r.json()


def test_member_plan_cannot_use_notebook(client):
    qa_login(client, plan="member")
    r = client.get("/api/notebook")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked" and r.json()["detail"]["plan_needed"] == "l1"
    assert client.post("/api/notebook", json={"title": "Test"}).status_code == 403


def test_project_cap_by_plan(client):
    qa_login(client, plan="l1")
    for i in range(4):
        new_project(client, f"Project {i}")
    r = client.post("/api/notebook", json={"title": "Fifth"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "cap"
    lst = client.get("/api/notebook").json()
    assert lst["count"] == 4 and lst["cap"] == 4 and lst["max_sources"] == 20
    qa_login(client, plan="l2")
    assert client.get("/api/notebook").json()["cap"] == 8


def test_sources_file_text_url_and_doc(client, mdb):
    qa_login(client, plan="l1")
    doc = upload(client, "Sharma review.txt", REPORT.encode()).json()
    pid = new_project(client)
    f = upload(client, "hiring.pdf", make_pdf([[s + "." for s in HIRING.split(". ")]]), url=f"/api/notebook/{pid}/sources/file").json()
    assert f["kind"] == "file" and f["title"] == "hiring" and f["pages"] == 1
    t = add_text(client, pid)
    assert t["kind"] == "text" and t["words"] > 30
    u = client.post(f"/api/notebook/{pid}/sources/url", json={"url": "www.example-news.in/cold-chain"}).json()
    assert u["kind"] == "url" and u["test"] is True and u["url"] == "https://www.example-news.in/cold-chain"
    assert "test mode" in u["title"].lower()
    assert client.post(f"/api/notebook/{pid}/sources/url", json={"url": "https://www.example-news.in/cold-chain"}).status_code == 409
    assert client.post(f"/api/notebook/{pid}/sources/url", json={"url": "not a link"}).status_code == 400
    d = client.post(f"/api/notebook/{pid}/sources/doc", json={"doc_id": doc["id"]}).json()
    assert d["kind"] == "doc" and d["title"] == "Sharma review" and d["doc_id"] == doc["id"]
    assert run(mdb.nb_chunks.count_documents({"source_id": d["id"]})) == run(mdb.reader_chunks.count_documents({"doc_id": doc["id"]}))
    assert client.post(f"/api/notebook/{pid}/sources/doc", json={"doc_id": "someone-elses"}).status_code == 404
    det = client.get(f"/api/notebook/{pid}").json()
    assert [s["kind"] for s in det["sources"]] == ["file", "text", "url", "doc"] and det["project"]["sources"] == 4
    assert run(mdb.blobs.count_documents({})) == 0                       # uploaded files are never stored
    assert client.delete(f"/api/notebook/{pid}/sources/{t['id']}").json()["ok"]
    assert run(mdb.nb_chunks.count_documents({"source_id": t["id"]})) == 0
    assert used(client) == 0                                             # adding sources is free


def test_url_source_when_web_reading_is_off(client, monkeypatch):
    qa_login(client, plan="l1")
    pid = new_project(client)
    monkeypatch.setenv("SEARCH_MODE", "off")
    r = client.post(f"/api/notebook/{pid}/sources/url", json={"url": "https://example.com/a"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "web_off" and "paste" in r.json()["detail"]["msg"].lower()

    async def nothing(urls, **kw):
        return []
    monkeypatch.setenv("SEARCH_MODE", "fake")
    from research import search
    monkeypatch.setattr(search, "extract", nothing)
    r = client.post(f"/api/notebook/{pid}/sources/url", json={"url": "https://example.com/a"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "url_failed"


def test_twenty_sources_max(client):
    qa_login(client, plan="l1")
    pid = new_project(client)
    for i in range(20):
        add_text(client, pid, f"Source number {i} talks about supply chain costs in Pune and Nashik.", f"S{i}")
    r = client.post(f"/api/notebook/{pid}/sources/text", json={"title": "One more", "text": NOTES})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sources_full"


def test_ask_cites_real_sources(client, mdb):
    qa_login(client, plan="l1")
    pid = new_project(client)
    assert client.post(f"/api/notebook/{pid}/ask", json={"question": "What changed?"}).status_code == 400   # no sources yet
    t = add_text(client, pid)
    u = client.post(f"/api/notebook/{pid}/sources/url", json={"url": "https://example.com/retail"}).json()
    out = client.post(f"/api/notebook/{pid}/ask", json={"question": "What did the state do to power tariffs for cold storage?"}).json()
    assert out["covered"] and out["citations"]
    for c in out["citations"]:
        assert c["source_id"] in (t["id"], u["id"]) and f"[{c['n']}]" in out["answer"]
        chunk = run(mdb.nb_chunks.find_one({"source_id": c["source_id"]}))
        assert c["excerpt"].strip(" …") in chunk["text"]
    assert out["citations"][0]["doc_title"] == "Market notes"
    assert used(client) == 1
    miss = client.post(f"/api/notebook/{pid}/ask", json={"question": "Quantum zebra telescope"}).json()
    assert miss["covered"] is False and used(client) == 1
    assert len(client.get(f"/api/notebook/{pid}").json()["messages"]) == 2


def test_generate_outputs_saved_as_notes(client):
    qa_login(client, plan="l1")
    pid = new_project(client)
    add_text(client, pid)
    client.post(f"/api/notebook/{pid}/sources/url", json={"url": "https://example.com/retail"})
    for kind in ("briefing", "faq", "study", "timeline"):
        r = client.post(f"/api/notebook/{pid}/generate", json={"kind": kind})
        assert r.status_code == 200, (kind, r.text)
        n = r.json()
        assert n["kind"] == kind and n["body"] and "Made from: Market notes" in n["body"]
    notes = client.get(f"/api/notebook/{pid}").json()["notes"]
    faq = next(n for n in notes if n["kind"] == "faq")
    assert faq["body"].count("**") >= 16                                  # 8+ questions
    tl = next(n for n in notes if n["kind"] == "timeline")
    assert "2024" in tl["body"] or "2023" in tl["body"]
    assert used(client) == 4


def test_timeline_needs_dates_and_made_up_dates_are_dropped(client, monkeypatch):
    qa_login(client, plan="l1")
    pid = new_project(client)
    add_text(client, pid, "Our team visits retailers every week and checks shelf space, prices and stock levels carefully.")
    r = client.post(f"/api/notebook/{pid}/generate", json={"kind": "timeline"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "no_dates" and used(client) == 0
    add_text(client, pid, NOTES, "Notes")

    async def inventor(**kw):
        return {"events": [{"date": "1999", "event": "Made up."}, {"date": "June 2024", "event": "Tariffs cut by 10%."}]}
    monkeypatch.setattr(llm, "complete_json", inventor)
    n = client.post(f"/api/notebook/{pid}/generate", json={"kind": "timeline"}).json()
    assert "June 2024" in n["body"] and "1999" not in n["body"] and used(client) == 1

    async def all_made_up(**kw):
        return {"events": [{"date": "1999", "event": "Made up."}]}
    monkeypatch.setattr(llm, "complete_json", all_made_up)
    r = client.post(f"/api/notebook/{pid}/generate", json={"kind": "timeline"})
    assert r.status_code == 422 and used(client) == 1                    # refunded


def test_notes_are_free_to_add_edit_delete(client):
    qa_login(client, plan="l1")
    pid = new_project(client)
    n = client.post(f"/api/notebook/{pid}/notes", json={"title": "My angle", "body": "Pitch idle-capacity sharing."}).json()
    assert n["kind"] == "note"
    e = client.patch(f"/api/notebook/{pid}/notes/{n['id']}", json={"body": "Pitch shared cold rooms."}).json()
    assert e["body"] == "Pitch shared cold rooms." and e["title"] == "My angle"
    assert client.delete(f"/api/notebook/{pid}/notes/{n['id']}").json()["ok"]
    assert client.get(f"/api/notebook/{pid}").json()["notes"] == [] and used(client) == 0


def test_audio_overview_is_cached_until_sources_change(client):
    qa_login(client, plan="l1")
    pid = new_project(client)
    assert client.post(f"/api/notebook/{pid}/audio").status_code == 400
    add_text(client, pid)
    a = client.post(f"/api/notebook/{pid}/audio").json()
    assert a["cached"] is False and a["url"].startswith("/api/blobs/") and a["fresh"]
    assert 250 <= len(a["script"].split()) <= 1100 and 3 <= a["minutes"] <= 7.5
    assert used(client, "audio") == 1
    got = client.get(a["url"])
    assert got.status_code == 200 and got.headers["content-type"].startswith("audio/")
    b = client.post(f"/api/notebook/{pid}/audio").json()
    assert b["cached"] is True and b["url"] == a["url"] and used(client, "audio") == 1
    add_text(client, pid, REPORT, "Review")
    assert client.get(f"/api/notebook/{pid}").json()["audio"]["fresh"] is False
    c = client.post(f"/api/notebook/{pid}/audio").json()
    assert c["cached"] is False and c["url"] != a["url"] and used(client, "audio") == 2
    assert client.get(a["url"]).status_code == 404                        # old audio removed


def test_audio_failure_refunds(client, monkeypatch):
    qa_login(client, plan="l1")
    pid = new_project(client)
    add_text(client, pid)

    async def broken(text, **kw):
        raise tts.TTSError("down")
    monkeypatch.setattr(tts, "speak", broken)
    r = client.post(f"/api/notebook/{pid}/audio")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "audio_busy" and used(client, "audio") == 0


def test_limit_402_and_refund_on_ai_error(client, mdb, monkeypatch):
    me = qa_login(client, plan="l1")
    pid = new_project(client)
    add_text(client, pid)

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = client.post(f"/api/notebook/{pid}/generate", json={"kind": "briefing"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy" and used(client) == 0
    r = client.post(f"/api/notebook/{pid}/ask", json={"question": "What did the state do to power tariffs?"})
    assert r.status_code == 503 and used(client) == 0
    monkeypatch.undo()
    use_up(mdb, me["user"]["id"], "doc_q", 150)
    r = client.post(f"/api/notebook/{pid}/ask", json={"question": "What did the state do to power tariffs?"})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_delete_project_removes_everything(client, mdb):
    qa_login(client, plan="l1")
    pid = new_project(client)
    add_text(client, pid)
    client.post(f"/api/notebook/{pid}/audio")
    client.post(f"/api/notebook/{pid}/notes", json={"title": "N", "body": "B"})
    assert client.patch(f"/api/notebook/{pid}", json={"title": "Renamed"}).json()["title"] == "Renamed"
    assert client.delete(f"/api/notebook/{pid}").json()["ok"]
    for coll in ("nb_projects", "nb_sources", "nb_chunks", "nb_notes", "blobs"):
        assert run(getattr(mdb, coll).count_documents({})) == 0, coll
    assert client.get(f"/api/notebook/{pid}").status_code == 404
