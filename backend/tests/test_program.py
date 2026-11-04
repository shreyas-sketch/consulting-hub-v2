"""4-3-2-1 program: auto-enrolment, coach for month 1 (kept on L2), task progress, admin cohorts and enrolments."""
from datetime import timedelta

from conftest import qa_login, run

from features import program


def _day(delta: int) -> str:
    return (program.ist_today() + timedelta(days=delta)).isoformat()


def _cohort(c, name, start, active=True, coach=None):
    body = {"name": name, "start_date": start, "active": active, "days": [
        {"n": 1, "title": "Find your niche", "when": f"{start}T19:00", "link": "https://zoom.us/j/1",
         "tasks": [{"text": "Fill the EDE sheet"}, {"text": "Pick one niche"}]},
        {"n": 2, "title": "Your offer", "when": f"{start}T19:00", "tasks": [{"text": "Write your offer in one line"},
                                                                          {"text": "Share it with your coach"}]}]}
    if coach:
        body["default_coach"] = coach
    r = c.post("/api/admin/program/cohorts", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_enrol_next_cohort_coach_and_progress(client, mdb):
    qa_login(client, role="admin")
    _cohort(client, "Old batch", _day(-60))
    nxt = _cohort(client, "Next batch", _day(3), coach={"name": "Priya", "whatsapp": "98765 43210"})
    _cohort(client, "Paused batch", _day(1), active=False)
    assert nxt["default_coach"]["whatsapp"] == "+919876543210" and nxt["days"][0]["when"].endswith("+05:30")
    assert len({t["id"] for d in nxt["days"] for t in d["tasks"]}) == 4

    qa_login(client, plan="l1")
    p = client.get("/api/program").json()
    assert p["enrolled"] and p["cohort"]["name"] == "Next batch" and p["cohort"]["starts_in_days"] == 3
    assert p["coach_status"] == "active" and p["coach"]["name"] == "Priya"
    assert p["coach"]["whatsapp_link"] == "https://wa.me/919876543210" and p["coach_note"] is None
    assert p["progress"] == {"done": 0, "total": 4, "pct": 0} and p["next_day"] == 1
    e = run(mdb.program_enrollments.find_one({}))
    assert (e["coach_until"].date() - program.start_utc(_day(3)).date()).days == 30
    # the second open does not enrol again
    assert client.get("/api/program").json()["cohort"]["id"] == nxt["id"]
    assert run(mdb.program_enrollments.count_documents({})) == 1

    t1, t2 = nxt["days"][0]["tasks"][0]["id"], nxt["days"][0]["tasks"][1]["id"]
    r = client.post(f"/api/program/tasks/{t1}", json={"done": True}).json()
    assert r["progress"] == {"done": 1, "total": 4, "pct": 25}
    client.post(f"/api/program/tasks/{t2}", json={"done": True})
    client.post(f"/api/program/tasks/{t2}", json={"done": True})             # twice counts once
    p = client.get("/api/program").json()
    assert p["progress"]["pct"] == 50 and p["days"][0]["done"] == 2 and p["days"][0]["tasks"][0]["done"] is True
    assert client.post(f"/api/program/tasks/{t2}", json={"done": False}).json()["progress"]["done"] == 1
    assert client.post("/api/program/tasks/nope1234", json={"done": True}).status_code == 404


def test_fallback_to_latest_cohort_coach_ended_points_to_support(client):
    qa_login(client, role="admin")
    _cohort(client, "Very old", _day(-120))
    _cohort(client, "Old", _day(-60), coach={"name": "Ravi", "whatsapp": "9876500001"})
    qa_login(client, plan="l1")
    p = client.get("/api/program").json()
    assert p["cohort"]["name"] == "Old" and p["coach"] is None and p["coach_status"] == "ended"
    assert p["coach_note"] == program.SUPPORT_NOTE and p["support_link"] == "/app/support"


def test_l2_keeps_the_coach(client):
    qa_login(client, role="admin")
    _cohort(client, "Old", _day(-60), coach={"name": "Ravi", "whatsapp": "9876500001"})
    qa_login(client, plan="l2")
    p = client.get("/api/program").json()
    assert p["coach_status"] == "active" and p["coach"]["name"] == "Ravi" and p["coach_until"] is None


def test_no_cohort_yet(client):
    qa_login(client, plan="l1")
    p = client.get("/api/program").json()
    assert p["enrolled"] is False and p["cohort"] is None and p["msg"]
    assert client.post("/api/program/tasks/abcd1234", json={"done": True}).status_code == 404


def test_lower_plans_are_locked(client):
    for plan in ("free", "member"):
        qa_login(client, plan=plan)
        r = client.get("/api/program")
        assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
        assert r.json()["detail"]["plan_needed"] == "l1"
        assert client.post("/api/program/tasks/abcd1234", json={"done": True}).status_code == 403


def test_admin_guard(client):
    assert client.get("/api/admin/program/cohorts").status_code == 401
    qa_login(client, plan="l2")
    assert client.get("/api/admin/program/cohorts").status_code == 403
    assert client.get("/api/admin/program/enrollments").status_code == 403
    assert client.post("/api/admin/program/cohorts", json={"name": "X", "start_date": _day(1)}).status_code == 403


def test_admin_enrolments_move_and_coach(client):
    qa_login(client, role="admin")
    a = _cohort(client, "A", _day(2), coach={"name": "Priya", "whatsapp": "9876543210"})
    b = _cohort(client, "B", _day(40))
    qa_login(client, plan="l1")
    client.get("/api/program")
    client.post(f"/api/program/tasks/{a['days'][0]['tasks'][0]['id']}", json={"done": True})
    qa_login(client, role="admin")
    rows = client.get("/api/admin/program/enrollments").json()["items"]
    assert len(rows) == 1
    row = rows[0]
    assert row["phone"] == "+919000000012" and row["plan"] == "l1" and row["progress"]["pct"] == 25
    assert row["cohort_name"] == "A" and row["coach"]["name"] == "Priya" and row["own_coach"] is False and row["coach_on"]
    assert client.get(f"/api/admin/program/enrollments?cohort_id={b['id']}").json()["items"] == []
    assert client.get("/api/admin/program/cohorts").json()["items"][-1]["enrolled"] == 1

    # own coach, bad number, then move to cohort B
    assert client.put(f"/api/admin/program/enrollments/{row['id']}/coach", json={"name": "Sam", "whatsapp": "123"}).status_code == 400
    r = client.put(f"/api/admin/program/enrollments/{row['id']}/coach",
                   json={"name": "Sam", "whatsapp": "+91 99887 76655", "until": _day(90)}).json()
    assert r["coach"]["name"] == "Sam" and r["own_coach"] and r["coach"]["whatsapp"] == "+919988776655"
    m = client.post(f"/api/admin/program/enrollments/{row['id']}/move", json={"cohort_id": b["id"]}).json()
    assert m["cohort_name"] == "B" and m["progress"]["done"] == 0
    assert client.post(f"/api/admin/program/enrollments/{row['id']}/move", json={"cohort_id": "nope"}).status_code == 404

    # cohort with members can't be deleted; empty one can
    assert client.delete(f"/api/admin/program/cohorts/{b['id']}").status_code == 409
    assert client.delete(f"/api/admin/program/cohorts/{a['id']}").json()["ok"]

    qa_login(client, plan="l1")
    p = client.get("/api/program").json()
    assert p["cohort"]["name"] == "B" and p["coach"]["name"] == "Sam"


def test_admin_days_tasks_and_default_coach(client):
    qa_login(client, role="admin")
    c = _cohort(client, "A", _day(5))
    r = client.put(f"/api/admin/program/cohorts/{c['id']}/days/3",
                   json={"n": 3, "title": "Pricing", "when": "2026-12-01T19:30+05:30",
                         "recording_url": "https://vimeo.com/1", "tasks": [{"text": "Set your day rate"}]})
    days = r.json()["days"]
    assert [d["n"] for d in days] == [1, 2, 3] and days[2]["when"].startswith("2026-12-01T19:30")
    keep = days[0]["tasks"][0]["id"]
    r = client.put(f"/api/admin/program/cohorts/{c['id']}/days/1",
                   json={"n": 1, "title": "Niche, again", "tasks": [{"id": keep, "text": "Fill the EDE sheet"}]}).json()
    assert r["days"][0]["title"] == "Niche, again" and r["days"][0]["tasks"][0]["id"] == keep
    assert client.put(f"/api/admin/program/cohorts/{c['id']}/days/1", json={"n": 2, "title": "Clash"}).status_code == 409
    assert client.put(f"/api/admin/program/cohorts/{c['id']}/days/4",
                      json={"n": 4, "title": "Bad link", "link": "zoom.us/j/1"}).status_code == 400
    assert client.put(f"/api/admin/program/cohorts/{c['id']}/days/4",
                      json={"n": 4, "title": "Bad date", "when": "next tuesday"}).status_code == 400
    assert [d["n"] for d in client.delete(f"/api/admin/program/cohorts/{c['id']}/days/2").json()["days"]] == [1, 3]
    co = client.put(f"/api/admin/program/cohorts/{c['id']}/coach", json={"name": "Neha", "whatsapp": "9123456780"}).json()
    assert co["default_coach"]["name"] == "Neha"
    assert client.put(f"/api/admin/program/cohorts/{c['id']}/coach", json={"name": ""}).json()["default_coach"] is None
    e = client.put(f"/api/admin/program/cohorts/{c['id']}", json={"name": "A renamed", "start_date": _day(6), "active": False}).json()
    assert e["name"] == "A renamed" and e["active"] is False and len(e["days"]) == 2       # days kept when not sent
    assert client.post("/api/admin/program/cohorts", json={"name": "Bad", "start_date": "2026-02-30"}).status_code == 400
