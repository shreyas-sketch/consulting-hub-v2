"""Group calls and events: plan filtering, .ics, reminders (24 h / 1 h, deduped), admin CRUD."""
from datetime import timedelta

from conftest import qa_login, run

from features import calls
from growth.clock import IST, utcnow
from jobs import registry


def _at(delta: timedelta) -> str:
    return (utcnow() + delta).astimezone(IST).strftime("%Y-%m-%dT%H:%M")


def _add(c, **kw):
    body = {"title": "Group call: pricing", "kind": "call", "plan_min": "l1", "when": _at(timedelta(hours=23)),
            "duration_min": 60, "link": "https://zoom.us/j/111", "notes": "Bring one question."} | kw
    r = c.post("/api/admin/calls", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _setup(c):
    qa_login(c, role="admin")
    call = _add(c)
    event = _add(c, title="December event", kind="event", plan_min="l2", when=_at(timedelta(days=30)), duration_min=240)
    past = _add(c, title="Group call: niche", when=_at(-timedelta(days=10)), recording_url="https://vimeo.com/76979871")
    return call, event, past


def test_member_sees_calls_for_their_plan(client):
    call, event, past = _setup(client)
    qa_login(client, plan="l1")
    d = client.get("/api/calls").json()
    assert d["next"]["id"] == call["id"] and d["next"]["link"] == "https://zoom.us/j/111" and d["next"]["when"].endswith("+05:30")
    assert [x["id"] for x in d["upcoming"]] == [call["id"]] and d["l2_events_hidden"] == 1
    assert [x["id"] for x in d["past"]] == [past["id"]] and d["past"][0]["recording_url"] and d["past"][0]["link"] == ""
    assert "IST" in d["next"]["when_label"]
    assert client.get(f"/api/calls/{event['id']}").json()["detail"]["code"] == "locked"
    assert client.get(f"/api/calls/{event['id']}.ics").status_code == 403

    qa_login(client, plan="l2")
    d = client.get("/api/calls").json()
    assert [x["id"] for x in d["upcoming"]] == [call["id"], event["id"]] and d["l2_events_hidden"] == 0
    assert client.get(f"/api/calls/{event['id']}").json()["kind"] == "event"


def test_ics_file(client):
    call, _, _ = _setup(client)
    qa_login(client, plan="l1")
    r = client.get(f"/api/calls/{call['id']}.ics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    body = r.text
    assert body.startswith("BEGIN:VCALENDAR\r\n") and "SUMMARY:Group call: pricing" in body
    assert "DTSTART:" in body and body.count("BEGIN:VEVENT") == 1 and "URL:https://zoom.us/j/111" in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    assert client.get("/api/calls/nope.ics").status_code == 404


def test_ics_folds_long_lines():
    c = {"_id": "x", "title": "Ü" * 80, "when": utcnow(), "duration_min": 60, "link": "", "notes": "a, b; c\nd"}
    text = calls.ics(c)
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    assert "a\\, b\\; c\\nd" in text.replace("\r\n ", "")


def test_lower_plan_locked_and_admin_guard(client):
    qa_login(client, plan="member")
    r = client.get("/api/calls")
    assert r.status_code == 403 and r.json()["detail"]["plan_needed"] == "l1"
    assert client.get("/api/admin/calls").status_code == 403
    qa_login(client, plan="l1")
    assert client.post("/api/admin/calls", json={"title": "X call", "when": "2026-12-01T19:00"}).status_code == 403


def test_reminders_24h_then_1h_deduped(client, mdb):
    qa_login(client, role="admin")
    call = _add(client)                                                   # starts in 23 h
    event = _add(client, title="L2 event", kind="event", plan_min="l2", when=_at(timedelta(minutes=50)))
    for p in ("member", "l1", "l2"):
        qa_login(client, plan=p)
    users = {p: str(run(mdb.users.find_one({"phone": ph}))["_id"])
             for p, ph in (("member", "+919000000011"), ("l1", "+919000000012"), ("l2", "+919000000013"))}

    now = utcnow()
    r = run(registry.run(mdb, "call_reminders", now))
    assert r["ok"] and r["result"]["calls"] == 2

    def rows(uid):
        return run(mdb.inbox.find({"user_id": uid, "kind": "call"}).to_list(50))
    assert rows(users["member"]) == []
    l1 = rows(users["l1"])
    assert len(l1) == 1 and "coming up" in l1[0]["title"] and l1[0]["link"] == "/app/calls"
    l2 = rows(users["l2"])
    assert len(l2) == 2 and any("in 1 hour" in x["title"] for x in l2)

    # the same run again sends nothing
    again = run(registry.run(mdb, "call_reminders", now + timedelta(minutes=30)))
    assert again["result"]["sent"] == 0 and len(rows(users["l1"])) == 1

    # 1 h before the call: the second reminder, once
    later = now + timedelta(hours=22, minutes=5)
    assert run(registry.run(mdb, "call_reminders", later))["result"]["sent"] >= 2
    assert run(registry.run(mdb, "call_reminders", later))["result"]["sent"] == 0
    assert [x["title"].split(":")[0] for x in sorted(rows(users["l1"]), key=lambda x: x["at"])] == \
        ["Group call coming up", "Group call in 1 hour"]

    # moving the call sends fresh reminders for the new time
    qa_login(client, role="admin")
    client.put(f"/api/admin/calls/{call['id']}", json={"title": call["title"], "when": _at(timedelta(hours=20)),
                                                        "link": "https://zoom.us/j/111"})
    assert run(registry.run(mdb, "call_reminders", now))["result"]["calls"] == 1
    assert len(rows(users["l1"])) == 3
    assert run(mdb.calls.find_one({"_id": event["id"]}))["reminded"][0].startswith("1h:")


def test_admin_crud_and_validation(client):
    qa_login(client, role="admin")
    a = _add(client)
    assert client.post("/api/admin/calls", json={"title": "Bad", "when": "next Saturday"}).status_code == 400
    assert client.post("/api/admin/calls", json={"title": "Bad", "when": "2026-12-01T19:00", "link": "zoom.us/j/1"}).status_code == 400
    assert client.post("/api/admin/calls", json={"title": "Bad", "when": "2026-12-01T19:00", "kind": "webinar"}).status_code == 422
    e = client.put(f"/api/admin/calls/{a['id']}", json={"title": "Renamed", "when": "2026-12-05T11:00", "duration_min": 90}).json()
    assert e["title"] == "Renamed" and e["when"] == "2026-12-05T11:00:00+05:30" and e["duration_min"] == 90
    items = client.get("/api/admin/calls").json()["items"]
    assert len(items) == 1 and items[0]["link"] == ""
    assert client.delete(f"/api/admin/calls/{a['id']}").json()["ok"]
    assert client.delete(f"/api/admin/calls/{a['id']}").status_code == 404
    assert client.put(f"/api/admin/calls/{a['id']}", json={"title": "X call", "when": "2026-12-05T11:00"}).status_code == 404
