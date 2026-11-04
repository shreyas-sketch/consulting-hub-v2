"""Warm Network Finder: LinkedIn CSV import (note lines above the header), paste, rule pre-score, AI scoring by
contact (metered per contact), filters, contacted + notes. L2 only."""
from conftest import qa_login, run

import llm
from features import network
from growth.clock import ist_month_key, utcnow

CSV = '''Notes:
"When exporting your connection data, you may notice that some of the email addresses are missing. You will only see email addresses for connections who have allowed their connections to see or download their email address using this setting https://www.linkedin.com/psettings/privacy/email. You can learn more here: https://www.linkedin.com/help/linkedin/answer/261"

First Name,Last Name,URL,Email Address,Company,Position,Connected On
Ravi,Mehta,https://www.linkedin.com/in/ravimehta,ravi@acmepharma.in,Acme Pharma Pvt Ltd,Founder & MD,12 Mar 2019
Sunita,Rao,https://www.linkedin.com/in/sunitarao,,Infosys,Senior Analyst,05 Jan 2021
Kumar,Iyer,https://www.linkedin.com/in/kiyer,,"Zen Labs, Pune",Head of Operations,30 Aug 2023
,,,,,,
'''


def l2(c, mdb, industry="Pharma"):
    uid = qa_login(c, plan="l2")["user"]["id"]
    run(mdb.snapshots.insert_one({"_id": f"snap-{uid}", "user_id": uid, "input": {"industry": industry}, "chosen": 0, "at": utcnow(),
                                  "options": [{"niche": "Supply chain consulting for pharma manufacturers",
                                               "who": "Owner-led pharma manufacturers", "title": "Pharma Supply Chain Consultant",
                                               "value_prop": "I help pharma MSMEs cut stock-outs.", "problem": "stock-outs",
                                               "result": "steady supply"}]}))
    return uid


def set_used(mdb, uid, meter, n):
    run(mdb.usage.update_one({"_id": f"{uid}:{ist_month_key()}"}, {"$set": {meter: n, "user_id": uid}}, upsert=True))


def used(c, meter):
    return c.get("/api/me/plan").json()["limits"][meter]["used"]


def upload(c, body=CSV, name="Connections.csv"):
    return c.post("/api/network/import", files={"file": (name, body.encode(), "text/csv")})


def test_csv_parsing_skips_linkedin_note_lines():
    rows = network.parse_connections_csv(CSV)
    assert [r["name"] for r in rows] == ["Ravi Mehta", "Sunita Rao", "Kumar Iyer"]
    assert rows[0]["email"] == "ravi@acmepharma.in" and rows[0]["connected_on"] == "12 Mar 2019"
    assert rows[2]["company"] == "Zen Labs, Pune" and rows[2]["position"] == "Head of Operations"
    # BOM + quoted header still parse
    assert len(network.parse_connections_csv("﻿" + CSV.replace("First Name,Last Name", '"First Name","Last Name"'))) == 3


def test_paste_formats():
    rows = network.parse_pasted("Neha Shah, Director, Bharat Forge\nAmit Joshi - VP Sales at Tata Motors\n"
                                "Priya Nair\tCEO\tNair Foods\n\n")
    assert [(r["name"], r["position"], r["company"]) for r in rows] == [
        ("Neha Shah", "Director", "Bharat Forge"), ("Amit Joshi", "VP Sales", "Tata Motors"), ("Priya Nair", "CEO", "Nair Foods")]
    assert len(network.parse_pasted(CSV)) == 3          # a pasted CSV is read as the CSV


def test_import_prescore_filters_and_dedupe(client, mdb):
    l2(client, mdb)
    r = upload(client)
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 3
    d = client.get("/api/network").json()
    assert [x["name"] for x in d["items"]][0] == "Ravi Mehta" and d["items"][-1]["name"] == "Sunita Rao"
    top = d["items"][0]
    assert top["seniority"] == "Founder" and any("niche" in w for w in top["pre_why"]) and top["fit"] is None
    assert d["counts"] == {"all": 3, "scored": 0, "contacted": 0}
    assert upload(client).json() == {"added": 0, "duplicates": 3, "over_cap": 0, "total": 3, "cap": 5000}
    assert client.get("/api/network?q=zen").json()["total"] == 1
    assert client.get("/api/network?senior=true").json()["total"] == 2
    assert used(client, "contacts") == 0                 # the rule score is free


def test_bad_files(client, mdb):
    l2(client, mdb)
    assert upload(client, "name,company\nA,B\n").json()["detail"]["code"] == "bad_csv"
    assert upload(client, CSV, name="contacts.xlsx").json()["detail"]["code"] == "bad_type"
    assert client.post("/api/network/paste", json={"text": "   \n  "}).status_code in (400, 422)


def test_cap_on_stored_contacts(client, mdb, monkeypatch):
    l2(client, mdb)
    monkeypatch.setattr(network, "CAP", 2)
    r = upload(client).json()
    assert r["added"] == 2 and r["over_cap"] == 1


def test_ai_score_counts_each_contact_then_contacted_and_notes(client, mdb):
    uid = l2(client, mdb)
    upload(client)
    ids = [x["id"] for x in client.get("/api/network").json()["items"][:2]]
    r = client.post("/api/network/score", json={"ids": ids})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["scored"] == 2 and all(1 <= x["fit"] <= 10 and x["why"] and x["angle"] for x in out["items"])
    assert used(client, "contacts") == 2
    assert client.get("/api/network?scored=yes&sort=fit").json()["total"] == 2
    p = client.patch(f"/api/network/{ids[0]}", json={"status": "contacted", "notes": "Call after Diwali"}).json()
    assert p["status"] == "contacted" and p["notes"] == "Call after Diwali" and p["contacted_at"]
    assert client.get("/api/network?status=contacted").json()["total"] == 1
    assert client.post("/api/network/score", json={"ids": [f"x{i}" for i in range(11)]}).status_code == 422   # 10 at a time


def test_limit_and_partial_limit(client, mdb):
    uid = l2(client, mdb)
    upload(client)
    ids = [x["id"] for x in client.get("/api/network").json()["items"]]
    set_used(mdb, uid, "contacts", 49)
    r = client.post("/api/network/score", json={"ids": ids[:2]})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit" and "1 contacts to score left" in r.json()["detail"]["msg"]
    assert client.post("/api/network/score", json={"ids": ids[:1]}).status_code == 200
    r = client.post("/api/network/score", json={"ids": ids[1:2]})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"
    assert used(client, "contacts") == 50


def test_ai_failure_refunds_every_contact(client, mdb, monkeypatch):
    l2(client, mdb)
    upload(client)
    ids = [x["id"] for x in client.get("/api/network").json()["items"]]

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = client.post("/api/network/score", json={"ids": ids})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy"
    assert used(client, "contacts") == 0


def test_partial_ai_answer_charges_only_scored(client, mdb, monkeypatch):
    l2(client, mdb)
    upload(client)
    ids = [x["id"] for x in client.get("/api/network").json()["items"]]

    async def one_only(**kw):
        return {"scores": [{"i": 2, "fit": 8, "why": "Runs operations at a lab.", "angle": "Ask about their plans."},
                           {"i": 9, "fit": 9, "why": "Not a real number", "angle": "x"}]}
    monkeypatch.setattr(llm, "complete_json", one_only)
    out = client.post("/api/network/score", json={"ids": ids}).json()
    assert out["scored"] == 1 and [x["fit"] for x in out["items"]] == [None, 8, None]
    assert used(client, "contacts") == 1


def test_lower_plans_locked(client):
    qa_login(client, plan="l1")
    assert client.get("/api/network").status_code == 403
    r = upload(client)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    assert client.post("/api/network/score", json={"ids": ["x"]}).status_code == 403
    r = client.post("/api/network/paste", json={"text": "Neha Shah, Director, Bharat Forge"})
    assert r.status_code == 403 and r.json()["detail"]["plan_needed"] == "l2"
