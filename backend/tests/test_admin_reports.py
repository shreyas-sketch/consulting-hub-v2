"""Admin report counts: grants count as their plan, admins and revoked accounts stay out."""
from conftest import login, qa_login

from growth.clock import IST, utcnow


def test_reports_count_grants_and_skip_admins_and_revoked(client):
    for ph, name in (("9876500001", "Granted"), ("9876500002", "Revoked"), ("9876500003", "Plain")):
        login(client, phone=ph, name=name)
        client.post("/api/auth/logout")
    qa_login(client, role="admin")
    ids = {u["name"]: u["id"] for u in client.get("/api/admin/users").json()["items"]}
    client.post(f"/api/admin/users/{ids['Granted']}/grant", json={"plan": "l1", "months": 1})
    client.post(f"/api/admin/users/{ids['Revoked']}/status", json={"status": "revoked"})
    p = client.get("/api/admin/pulse").json()
    mix = {m["plan"]: m["count"] for m in p["plan_mix"]}
    assert mix["l1"] == 1 and p["kpis"]["granted_active"] == 1 and p["kpis"]["l1_active"] == 1 and p["kpis"]["mrr_inr"] == 0
    t = utcnow().astimezone(IST).date().isoformat()
    w = client.get(f"/api/admin/webinar?start={t}&end={t}").json()
    assert w["accounts"] == 2                     # revoked and admin left out
    assert w["group_session_list"] == 1           # only "Plain": "Granted" has a plan
    csv = client.get(f"/api/admin/webinar/group-session.csv?start={t}&end={t}").text
    assert "Plain" in csv and "Granted" not in csv and "Revoked" not in csv and "Admin" not in csv
