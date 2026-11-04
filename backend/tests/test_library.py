"""Recordings and workbooks: sections, embedded players, PDF upload served with a plan check, admin guard."""
from conftest import qa_login

from features.library import embed_of

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _add(c, **kw):
    body = {"title": "Session 1: niche", "kind": "video", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "section": "Week 1", "order": 1, "plan_min": "l1", "published": True} | kw
    r = c.post("/api/admin/library", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_embed_links():
    assert embed_of("https://youtu.be/dQw4w9WgXcQ")["src"] == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0"
    assert embed_of("https://m.youtube.com/watch?feature=share&v=dQw4w9WgXcQ")["provider"] == "youtube"
    assert embed_of("https://www.youtube.com/shorts/dQw4w9WgXcQ")["provider"] == "youtube"
    assert embed_of("https://vimeo.com/76979871")["src"] == "https://player.vimeo.com/video/76979871"
    assert embed_of("https://vimeo.com/76979871/abc123def0")["src"] == "https://player.vimeo.com/video/76979871?h=abc123def0"
    assert embed_of("https://player.vimeo.com/video/76979871?h=ff00aa11")["src"].endswith("?h=ff00aa11")
    assert embed_of("https://drive.google.com/file/d/abc/view") is None
    assert embed_of("https://www.youtube.com/watch?v=short") is None


def test_member_library_sections_players_and_files(client):
    qa_login(client, role="admin")
    yt = _add(client)
    _add(client, title="Session 2: offer", url="https://vimeo.com/76979871", order=2)
    _add(client, title="Pricing article", kind="link", url="https://example.com/pricing", section="Reading", order=5)
    wb = _add(client, title="Week 1 workbook", kind="workbook", url="", order=3)
    l2 = _add(client, title="Mentor masterclass", kind="workbook", url="", plan_min="l2", section="Mentorship")
    _add(client, title="Draft video", published=False)
    assert client.post(f"/api/admin/library/{wb['id']}/file", files={"file": ("week1.pdf", PDF, "application/pdf")}).json()["file_name"] == "week1.pdf"
    client.post(f"/api/admin/library/{l2['id']}/file", files={"file": ("l2.pdf", PDF, "application/pdf")})

    qa_login(client, plan="l1")
    d = client.get("/api/library").json()
    assert [s["name"] for s in d["sections"]] == ["Week 1", "Reading"] and d["count"] == 4 and d["l2_hidden"] == 1
    week = d["sections"][0]["items"]
    assert [i["title"] for i in week] == ["Session 1: niche", "Session 2: offer", "Week 1 workbook"]
    assert week[0]["embed"]["src"].startswith("https://www.youtube-nocookie.com/embed/") and week[1]["embed"]["provider"] == "vimeo"
    assert d["sections"][1]["items"][0]["embed"] is None and week[2]["file_url"] == f"/api/library/{wb['id']}/file"
    f = client.get(week[2]["file_url"])
    assert f.status_code == 200 and f.content == PDF and f.headers["content-type"] == "application/pdf"
    r = client.get(f"/api/library/{l2['id']}/file")
    assert r.status_code == 403 and r.json()["detail"]["plan_needed"] == "l2"
    assert client.get(f"/api/library/{yt['id']}/file").status_code == 404

    qa_login(client, plan="l2")
    d = client.get("/api/library").json()
    assert "Mentorship" in [s["name"] for s in d["sections"]] and d["l2_hidden"] == 0
    assert client.get(f"/api/library/{l2['id']}/file").content == PDF


def test_workbook_without_file_is_hidden_and_lower_plan_locked(client):
    qa_login(client, role="admin")
    _add(client, title="Empty workbook", kind="workbook", url="")
    qa_login(client, plan="l1")
    assert client.get("/api/library").json()["count"] == 0
    qa_login(client, plan="member")
    r = client.get("/api/library")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"


def test_admin_upload_rules_and_crud(client):
    qa_login(client, role="admin")
    wb = _add(client, title="Workbook", kind="workbook", url="")
    up = f"/api/admin/library/{wb['id']}/file"
    assert client.post(up, files={"file": ("w.docx", b"PK..", "application/octet-stream")}).status_code == 400
    assert client.post(up, files={"file": ("w.pdf", b"not a pdf", "application/pdf")}).status_code == 400
    big = b"%PDF" + b"0" * (15 * 1024 * 1024)
    r = client.post(up, files={"file": ("big.pdf", big, "application/pdf")})
    assert r.status_code == 400 and "15 MB" in r.json()["detail"]["msg"]
    first = client.post(up, files={"file": ("a.pdf", PDF, "application/pdf")}).json()
    second = client.post(up, files={"file": ("b.pdf", PDF, "application/pdf")}).json()
    assert second["file_name"] == "b.pdf" and second["file_url"] == first["file_url"]
    assert client.delete(up).json()["file_url"] is None
    assert client.post("/api/admin/library", json={"title": "No link", "kind": "video"}).status_code == 400
    assert client.post("/api/admin/library", json={"title": "Bad link", "kind": "link", "url": "example.com"}).status_code == 400
    e = client.put(f"/api/admin/library/{wb['id']}", json={"title": "Workbook 1", "kind": "workbook", "section": "Week 2",
                                                           "published": False}).json()
    assert e["section"] == "Week 2" and e["published"] is False
    assert len(client.get("/api/admin/library").json()["items"]) == 1
    assert client.delete(f"/api/admin/library/{wb['id']}").json()["ok"]


def test_admin_guard(client):
    assert client.get("/api/admin/library").status_code == 401
    qa_login(client, plan="l2")
    assert client.get("/api/admin/library").status_code == 403
    assert client.post("/api/admin/library", json={"title": "X video", "url": "https://youtu.be/dQw4w9WgXcQ"}).status_code == 403
