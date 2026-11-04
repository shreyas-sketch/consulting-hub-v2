"""WhatsApp templates: every alert kind the app sends has a template, and the admin can send a test."""
import re

from conftest import login, qa_login

from notify import service, templates


def test_every_sent_kind_has_a_template():
    import server  # noqa: F401 — every tool registers its message kinds on import
    kinds = {t[0] for t in templates.ALERTS}
    unused = set(templates.catalogue()["not_sent_yet"])
    assert set(service.KINDS) - unused <= kinds          # no kind the app sends is missing a template
    for it in templates.catalogue("https://hub.example.com")["items"]:
        if it["kind"] == "otp":
            continue
        body = it["body"]
        assert body.count("{{1}}") == 1 and not body.startswith("{{") and not body.rstrip().endswith("}}")
        assert it["button_url"] == "https://hub.example.com/{{1}}" and len(it["button"]) <= 25
        assert it["campaign"] == f"alert_{it['kind']}"
        assert not re.search(r"[\U0001F300-\U0001FAFF]", body + it["sample"])        # no emojis


def test_admin_lists_templates_and_sends_a_test(client):
    qa_login(client, role="admin")
    d = client.get("/api/admin/whatsapp-templates").json()
    assert len(d["items"]) == 11 and d["items"][0]["kind"] == "otp"
    r = client.post("/api/admin/whatsapp-templates/test", json={"kind": "call"}).json()
    assert r["ok"] is True and r["campaign"] == "alert_call"
    assert client.post("/api/admin/whatsapp-templates/test", json={"kind": "nope"}).status_code == 404


def test_members_cannot_see_templates(client):
    login(client, phone="9876500011")
    assert client.get("/api/admin/whatsapp-templates").status_code in (401, 403)
