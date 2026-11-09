from conftest import login, qa_login, run

from growth.clock import IST, utcnow


def _today():
    return utcnow().astimezone(IST).date().isoformat()


def test_admin_guard(client):
    assert client.get("/api/admin/pulse").status_code == 401
    qa_login(client)
    assert client.get("/api/admin/pulse").status_code == 403


def test_pulse_users_grant(client, mdb):
    login(client, utm={"src": "webinar"})
    co = client.post("/api/billing/checkout", json={"plan": "member", "period": "yearly"}).json()
    client.post("/api/billing/verify", json={"subscription_id": co["subscription_id"]})
    client.post("/api/auth/logout")
    login(client, phone="9876500099", name="Free one")
    client.post("/api/auth/logout")
    qa_login(client, role="admin")
    p = client.get("/api/admin/pulse").json()
    k = p["kpis"]
    assert k["users_total"] == 2 and k["member_active"] == 1 and k["member_yearly"] == 1 and k["mrr_inr"] == 1667
    assert {m["plan"]: m["count"] for m in p["plan_mix"]} == {"l2": 0, "l1": 0, "member": 1, "free": 1}
    assert any(s["source"] == "webinar" for s in p["by_source"]) and len(p["signups_by_day"]) == 14
    users = client.get("/api/admin/users?q=98765000").json()
    assert users["total"] == 1
    uid = users["items"][0]["id"]
    d = client.post(f"/api/admin/users/{uid}/grant", json={"plan": "l1", "months": 2}).json()
    assert d["plan"]["plan"] == "l1" and d["grants"]
    assert client.get("/api/admin/users?plan=l1").json()["total"] == 1
    assert client.post(f"/api/admin/users/{uid}/grant", json={"plan": "l2", "months": 1}).status_code == 422   # L2 = start-l2 only
    d = client.post(f"/api/admin/users/{uid}/grant", json={"plan": "free", "months": 0}).json()
    assert d["plan"]["plan"] == "free"
    d = client.post(f"/api/admin/users/{uid}/status", json={"status": "revoked"}).json()
    assert d["user"]["status"] == "revoked"
    assert client.get(f"/api/admin/users/{uid}").json()["events"]


def test_flags_settings_vendors(client):
    qa_login(client, role="admin")
    items = client.get("/api/admin/flags").json()["items"]
    assert {f["key"] for f in items} == {"WHATSAPP_OTP", "WEBINAR_TOOLS", "LINKEDIN_REWRITES", "WHATSAPP_ALERTS"}
    out = client.post("/api/admin/flags", json={"key": "LINKEDIN_REWRITES", "on": False}).json()["items"]
    assert next(f for f in out if f["key"] == "LINKEDIN_REWRITES")["on"] is False
    s = client.post("/api/admin/settings", json={"group_session": {"title": "Saturday group call", "when": "Sat 11 am",
                                                                   "link": "https://zoom.us/j/1"}}).json()
    assert s["group_session"]["when"] == "Sat 11 am"
    assert client.post("/api/admin/settings", json={"group_session": {"link": "zoom.us/j/1"}}).status_code == 400
    assert {v["name"] for v in client.get("/api/admin/vendors").json()["vendors"]} >= {"razorpay", "anthropic", "search"}


def test_group_session_shown_to_members(client):
    qa_login(client, role="admin")
    client.post("/api/admin/settings", json={"group_session": {"title": "Group call", "when": "Sat 11 am", "link": "https://zoom.us/j/1"}})
    client.post("/api/auth/logout")
    qa_login(client)
    assert client.get("/api/me/home").json()["group_session"]["link"] == "https://zoom.us/j/1"


def test_webinar_report_live_and_csv(seeded_client):
    c = seeded_client
    for ph in ("9876500011", "9876500012"):
        login(c, phone=ph, utm={"src": "webinar"})
        c.post("/api/readiness", json={"scores": {"diagnosis": 7, "offer": 1, "acquisition": 1, "pricing": 1,
                                                        "delivery": 1, "visibility": 1}, "potential": 6})
        c.post("/api/auth/logout")
    login(c, phone="9876500013", utm={"src": "webinar"})
    co = c.post("/api/billing/checkout", json={"plan": "l1"}).json()
    c.post("/api/billing/verify", json={"subscription_id": co["subscription_id"]})
    c.post("/api/auth/logout")
    qa_login(c, role="admin")
    t = _today()
    w = c.get(f"/api/admin/webinar?start={t}&end={t}").json()
    assert w["accounts"] == 3 and w["used_a_tool"] == 2 and w["bought"] == {"member": 0, "l1": 1}
    assert w["group_session_list"] == 2
    assert any(f["tool"] == "Readiness Score" and f["users"] == 2 for f in w["tool_usage"])
    live = c.get("/api/admin/live").json()
    assert live["accounts_15m"] == 3 and live["tools_15m"][0]["tool"] == "Readiness Score"
    csv = c.get(f"/api/admin/webinar/group-session.csv?start={t}&end={t}")
    assert csv.status_code == 200 and csv.text.count("\n") == 3 and "+919876500011" in csv.text
    assert "+919876500013" not in csv.text and ",12," in csv.text      # readiness 7 + 5 skills at 1 = 12
    assert c.get("/api/admin/webinar?start=2026-01-01&end=2026-12-31").status_code == 400


def test_knowledge_base_upload(client):
    qa_login(client, role="admin")
    vtt = b"WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\nA niche is where experience, demand and enjoyment meet.\n"
    up = client.post("/api/admin/kb", files={"file": ("niche.vtt", vtt, "text/vtt")}, data={"title": "Niche"}).json()
    assert up["chunks"] == 1 and up["words"] == 9
    assert any(k["title"] == "Niche" for k in client.get("/api/admin/kb").json()["items"])
    assert client.post("/api/admin/kb", files={"file": ("x.pdf", b"%PDF", "application/pdf")}).status_code == 400
    assert client.delete(f"/api/admin/kb/{up['id']}").json()["ok"]


def test_tick_due_and_ingest_key(client, mdb, monkeypatch):
    assert client.post("/api/jobs/tick").status_code == 401
    monkeypatch.setenv("INGEST_KEY", "k" * 20)
    r = client.post("/api/jobs/tick", headers={"X-Ingest-Key": "k" * 20})
    assert r.status_code == 200 and "l2_resume" in r.json()["ran"]
    from jobs import registry
    assert "l2_resume" not in run(registry.due(mdb))
