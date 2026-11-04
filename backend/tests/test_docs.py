"""Doc Reader: reading PDF / DOCX / TXT / MD, the per-plan document cap, cited answers, summary, plan gates and metering."""
import io
import re

from conftest import qa_login, run

import llm
from features import docs as docs_f
from growth.clock import ist_month_key

REPORT = ("Quarterly operations review for Sharma Foods. Revenue grew 18% to Rs 42 crore in the quarter. "
          "Wastage at the Pune plant fell from 6.5% to 4.1% after the new cold storage. "
          "The board decided to open two new depots in Nagpur and Indore by March 2026. "
          "The main risk is the delay in hiring plant supervisors, which slows the second shift. "
          "Distributor margins stay at 9% and credit days rose to 45.")
HIRING = ("Hiring plan for the sales team. We will hire 12 field sales officers in Gujarat. "
          "Each officer gets a monthly target of 40 retailer visits. Training runs for three weeks in Ahmedabad. "
          "The hiring budget is Rs 60 lakh for the year.")


def make_pdf(pages: list[list[str]]) -> bytes:
    """A tiny real PDF (Helvetica text, one content stream per page) — no PDF library needed."""
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>", 3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
    kids, n = [], 4
    for lines in pages:
        content = ("BT /F1 11 Tf 14 TL 50 750 Td " + " ".join(f"({x}) Tj T*" for x in lines) + " ET").encode()
        objs[n + 1] = b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"
        objs[n] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                   b"/Contents %d 0 R >>" % (n + 1))
        kids.append(n)
        n += 2
    objs[2] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{k} 0 R" for k in kids).encode(), len(kids))
    out, offs = b"%PDF-1.4\n", {}
    for i in range(1, n):
        offs[i] = len(out)
        out += b"%d 0 obj\n" % i + objs[i] + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % n + b"".join(b"%010d 00000 n \n" % offs[i] for i in range(1, n))
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (n, xref)


def make_docx(paras: list[str], table: list[list[str]] | None = None) -> bytes:
    import docx
    d = docx.Document()
    for p in paras:
        d.add_paragraph(p)
    if table:
        t = d.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, val in enumerate(row):
                t.cell(r, c).text = val
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def upload(c, name: str, data: bytes, title: str | None = None, url: str = "/api/docs"):
    return c.post(url, files={"file": (name, data, "application/octet-stream")}, data={"title": title} if title else {})


def used(c, meter="doc_q"):
    return c.get("/api/me/plan").json()["limits"][meter]["used"]


def use_up(mdb, uid: str, meter: str, n: int):
    run(mdb.usage.update_one({"_id": f"{uid}:{ist_month_key()}"},
                             {"$set": {meter: n, "user_id": uid, "month": ist_month_key()}}, upsert=True))


# ------------------------------------------------------------------ extraction ----
def test_reads_txt_md_pdf_docx():
    t = docs_f.read_file(REPORT.encode(), "q3-review.txt")
    assert t["kind"] == "txt" and t["title"] == "q3-review" and t["words"] == len(REPORT.split()) and t["pages"] == 1

    md = docs_f.read_file(b"# Plan\n\n**Hire** 12 people in [Gujarat](https://x.com) this year.\n\n- Train them\n", "plan.md")
    assert "Hire 12 people in Gujarat" in md["text"] and "https" not in md["text"] and "#" not in md["text"]

    pdf = docs_f.read_file(make_pdf([["Page one talks about manage-", "ment of wastage at the Pune plant."] * 3,
                                     ["Page two covers the Nagpur depot and its opening by March 2026."] * 3]), "Review.pdf")
    assert pdf["kind"] == "pdf" and pdf["pages"] == 2 and not pdf["pages_estimated"]
    assert "Pune plant" in pdf["text"] and "Nagpur depot" in pdf["text"]
    chunks = docs_f.make_chunks(pdf["text"], pdf["page_starts"])
    assert chunks[0]["page"] == 1 and chunks[0]["tokens"] and chunks[0]["n"] == len(chunks[0]["tokens"])

    dx = docs_f.read_file(make_docx(["Client: Mehta Textiles.", "Problem: slow collections from dealers."],
                                    [["Metric", "Value"], ["Credit days", "62"]]), "brief.docx")
    assert dx["kind"] == "docx" and "Mehta Textiles" in dx["text"] and "Credit days | 62" in dx["text"]

    long = docs_f.read_file(("word " * 1000).encode(), "long.txt")
    parts = docs_f.make_chunks(long["text"])
    assert len(parts) == 4 and all(p["page"] is None for p in parts)


def test_bad_files_get_plain_messages(client):
    qa_login(client, plan="member")
    r = upload(client, "virus.exe", b"MZ....")
    assert r.status_code == 415 and r.json()["detail"]["code"] == "bad_type"
    r = upload(client, "scan.pdf", make_pdf([[], []]))                     # pages with no text = a scan
    assert r.status_code == 422 and r.json()["detail"]["code"] == "scanned" and "scan" in r.json()["detail"]["msg"]
    r = upload(client, "fake.pdf", b"hello this is not a pdf at all")
    assert r.status_code == 415
    r = upload(client, "empty.txt", b"")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "empty"
    big = b"a " * (docs_f.MAX_BYTES // 2 + 10)
    r = upload(client, "big.txt", big)
    assert r.status_code == 413 and "10 MB" in r.json()["detail"]["msg"]
    assert client.get("/api/docs/list").json()["count"] == 0


# ------------------------------------------------------------------ store, cap, delete ----
def test_upload_list_get_delete_keeps_no_file(client, mdb):
    qa_login(client, plan="member")
    r = upload(client, "Sharma Foods review.txt", REPORT.encode())
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["title"] == "Sharma Foods review" and doc["words"] > 40 and doc["chunks"] == 1 and doc["kind"] == "txt"
    lst = client.get("/api/docs/list").json()
    assert lst["count"] == 1 and lst["cap"] == 5 and lst["max_mb"] == 10
    one = client.get(f"/api/docs/{doc['id']}").json()
    assert one["preview"].startswith("Quarterly operations review") and one["summary"] is None
    stored = run(mdb.reader_docs.find_one({"_id": doc["id"]}))
    assert "data" not in stored and "text" not in stored                # text lives only in chunks; no original file
    assert run(mdb.blobs.count_documents({})) == 0
    assert client.delete(f"/api/docs/{doc['id']}").json()["ok"]
    assert client.get("/api/docs/list").json()["count"] == 0
    assert run(mdb.reader_chunks.count_documents({"doc_id": doc["id"]})) == 0
    assert client.get(f"/api/docs/{doc['id']}").status_code == 404


def test_member_cap_is_five_documents(client):
    qa_login(client, plan="member")
    ids = [upload(client, f"d{i}.txt", (REPORT + f" Note {i}.").encode()).json()["id"] for i in range(5)]
    r = upload(client, "six.txt", HIRING.encode())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "cap" and "Delete one" in r.json()["detail"]["msg"]
    client.delete(f"/api/docs/{ids[0]}")
    assert upload(client, "six.txt", HIRING.encode()).status_code == 200


def test_l1_cap_is_twenty(client):
    qa_login(client, plan="l1")
    assert client.get("/api/docs/list").json()["cap"] == 20


def test_free_account_is_locked(client):
    qa_login(client, plan="free")
    r = client.get("/api/docs/list")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    assert upload(client, "a.txt", REPORT.encode()).status_code == 403
    assert client.post("/api/docs/ask", json={"question": "What is the revenue?"}).status_code == 403


# ------------------------------------------------------------------ ask ----
def test_ask_answers_with_citations_to_real_chunks(client, mdb):
    qa_login(client, plan="member")
    a = upload(client, "review.txt", REPORT.encode()).json()
    b = upload(client, "hiring.pdf", make_pdf([[s + "." for s in HIRING.split(". ")]])).json()
    r = client.post("/api/docs/ask", json={"question": "How many sales officers will we hire in Gujarat?"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["covered"] and out["citations"] and re.search(r"\[1\]", out["answer"])
    for cte in out["citations"]:
        assert f"[{cte['n']}]" in out["answer"]
        chunk = run(mdb.reader_chunks.find_one({"doc_id": cte["doc_id"]}))
        assert cte["excerpt"].strip(" …") in chunk["text"]                  # the excerpt is really in the member's doc
    assert out["citations"][0]["doc_title"] == "hiring" and out["citations"][0]["page"] == 1
    assert used(client) == 1

    only_a = client.post("/api/docs/ask", json={"question": "What did the board decide about depots?", "doc_ids": [a["id"]]}).json()
    assert all(c["doc_id"] == a["id"] for c in only_a["citations"]) and only_a["citations"]
    assert used(client) == 2

    miss = client.post("/api/docs/ask", json={"question": "Quantum zebra telescope"}).json()
    assert miss["covered"] is False and miss["citations"] == [] and used(client) == 2      # not covered: not counted
    hist = client.get("/api/docs/list").json()["questions"]
    assert len(hist) == 3 and hist[0]["question"] == "Quantum zebra telescope"
    assert client.post("/api/docs/ask", json={"question": "Revenue?", "doc_ids": ["nope"]}).status_code == 400
    assert b["id"]


def test_made_up_citation_numbers_are_dropped(client, monkeypatch):
    qa_login(client, plan="member")
    upload(client, "review.txt", REPORT.encode())

    async def liar(**kw):
        return {"covered": True, "answer": "Revenue grew 18% [1]. Also see [7] and [1, 9]."}
    monkeypatch.setattr(llm, "complete_json", liar)
    out = client.post("/api/docs/ask", json={"question": "How much did revenue grow?"}).json()
    assert [c["n"] for c in out["citations"]] == [1] and "[7]" not in out["answer"] and "[9]" not in out["answer"]

    async def no_cites(**kw):
        return {"covered": True, "answer": "Revenue grew a lot."}
    monkeypatch.setattr(llm, "complete_json", no_cites)
    r = client.post("/api/docs/ask", json={"question": "How much did revenue grow?"})
    assert r.status_code == 503 and used(client) == 1                    # an uncited answer is refunded


def test_doc_question_limit_gives_402(client, mdb):
    me = qa_login(client, plan="member")
    upload(client, "review.txt", REPORT.encode())
    use_up(mdb, me["user"]["id"], "doc_q", 60)
    r = client.post("/api/docs/ask", json={"question": "How much did revenue grow?"})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_ai_failure_refunds_the_question(client, monkeypatch):
    qa_login(client, plan="member")
    doc = upload(client, "review.txt", REPORT.encode()).json()

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = client.post("/api/docs/ask", json={"question": "How much did revenue grow?"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy" and used(client) == 0
    assert client.post(f"/api/docs/{doc['id']}/summary").status_code == 503 and used(client) == 0


# ------------------------------------------------------------------ summary ----
def test_summary_counts_once_and_keeps_only_real_figures(client, monkeypatch):
    qa_login(client, plan="member")
    doc = upload(client, "review.txt", REPORT.encode()).json()
    s = client.post(f"/api/docs/{doc['id']}/summary").json()
    assert s["cached"] is False and s["summary"]["overview"] and len(s["summary"]["key_points"]) >= 2
    assert s["summary"]["risks"] and s["summary"]["decisions"] and s["summary"]["numbers"]
    assert used(client) == 1
    again = client.post(f"/api/docs/{doc['id']}/summary").json()
    assert again["cached"] is True and used(client) == 1
    assert client.get("/api/docs/list").json()["items"][0]["has_summary"]

    async def inventor(**kw):
        return {"overview": "A review.", "key_points": ["Revenue grew.", "Wastage fell."],
                "numbers": [{"figure": "18%", "meaning": "revenue growth"}, {"figure": "Rs 99 crore", "meaning": "made up"}],
                "decisions": [], "risks": []}
    monkeypatch.setattr(llm, "complete_json", inventor)
    s = client.post(f"/api/docs/{doc['id']}/summary", json={"refresh": True}).json()
    assert [n["figure"] for n in s["summary"]["numbers"]] == ["18%"] and used(client) == 2
