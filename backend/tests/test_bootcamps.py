"""Bootcamps (L2): tasks, link/text submissions, team review with feedback, completion %."""
from conftest import qa_login, run


def _bootcamp(c, **kw):
    body = {"n": 1, "title": "Your offer", "description": "Build an offer a client can say yes to.", "published": True,
            "tasks": [{"title": "Write your offer", "detail": "One page."}, {"title": "Price it", "detail": "Three options."}],
            "resources": [{"title": "Offer template", "url": "https://docs.google.com/document/d/1"}]} | kw
    r = c.post("/api/admin/bootcamps", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_submit_review_feedback_and_completion(client, mdb):
    qa_login(client, role="admin")
    b = _bootcamp(client)
    _bootcamp(client, n=2, title="Hidden draft", published=False)
    t1, t2 = b["tasks"][0]["id"], b["tasks"][1]["id"]

    qa_login(client, plan="l2")
    items = client.get("/api/bootcamps").json()["items"]
    assert [i["title"] for i in items] == ["Your offer"] and items[0]["progress"] == {"submitted": 0, "reviewed": 0, "total": 2, "pct": 0}
    d = client.get(f"/api/bootcamps/{b['id']}").json()
    assert d["resources"][0]["url"].startswith("https://") and d["task_list"][0]["submission"] is None
    url = f"/api/bootcamps/{b['id']}/tasks/{t1}"
    assert client.post(url, json={"text": "", "link": ""}).status_code == 400
    assert client.post(url, json={"link": "drive.google.com/x"}).status_code == 400
    assert client.post(f"/api/bootcamps/{b['id']}/tasks/nope", json={"text": "Hi"}).status_code == 404
    d = client.post(url, json={"text": "My offer: 90-day cost audit.", "link": "https://drive.google.com/file/d/abc"}).json()
    assert d["task_list"][0]["submission"]["status"] == "submitted" and d["progress"]["pct"] == 50
    d = client.post(url, json={"text": "My offer, v2."}).json()                # update in place
    assert d["task_list"][0]["submission"]["text"] == "My offer, v2." and run(mdb.bootcamp_submissions.count_documents({})) == 1

    qa_login(client, role="admin")
    s = client.get(f"/api/admin/bootcamps/{b['id']}/submissions").json()
    assert s["bootcamp"]["to_review"] == 1 and s["members"][0]["pct"] == 50 and s["members"][0]["phone"] == "+919000000013"
    sub = s["items"][0]
    assert sub["task_title"] == "Write your offer" and sub["status"] == "submitted"
    assert client.get(f"/api/admin/bootcamps/{b['id']}/submissions?status=reviewed").json()["items"] == []
    rv = client.post(f"/api/admin/bootcamps/submissions/{sub['id']}/review", json={"feedback": "Good. Name the client type."}).json()
    assert rv["status"] == "reviewed" and rv["feedback"].startswith("Good")
    assert client.get("/api/admin/bootcamps").json()["items"][0]["to_review"] == 0
    l2_id = str(run(mdb.users.find_one({"phone": "+919000000013"}))["_id"])
    alert = run(mdb.inbox.find_one({"user_id": l2_id, "kind": "bootcamp"}))
    assert alert and alert["link"] == f"/app/bootcamps/{b['id']}"

    qa_login(client, plan="l2")
    d = client.get(f"/api/bootcamps/{b['id']}").json()
    assert d["task_list"][0]["submission"]["feedback"] == "Good. Name the client type." and d["progress"]["reviewed"] == 1
    d = client.post(url, json={"text": "My offer, v3."}).json()                # changes go back for review, feedback kept
    assert d["task_list"][0]["submission"]["status"] == "submitted" and d["task_list"][0]["submission"]["feedback"]
    client.post(f"/api/bootcamps/{b['id']}/tasks/{t2}", json={"link": "https://drive.google.com/file/d/def"})
    assert client.get("/api/bootcamps").json()["items"][0]["progress"]["pct"] == 100


def test_unpublished_hidden_and_l1_locked(client):
    qa_login(client, role="admin")
    draft = _bootcamp(client, published=False)
    qa_login(client, plan="l2")
    assert client.get(f"/api/bootcamps/{draft['id']}").status_code == 404
    qa_login(client, plan="l1")
    for r in (client.get("/api/bootcamps"), client.get(f"/api/bootcamps/{draft['id']}"),
              client.post(f"/api/bootcamps/{draft['id']}/tasks/x", json={"text": "Hi"})):
        assert r.status_code == 403 and r.json()["detail"]["code"] == "locked" and r.json()["detail"]["plan_needed"] == "l2"


def test_admin_crud_and_guard(client):
    assert client.get("/api/admin/bootcamps").status_code == 401
    qa_login(client, plan="l2")
    assert client.get("/api/admin/bootcamps").status_code == 403
    assert client.post("/api/admin/bootcamps/submissions/x/review", json={"feedback": "ok ok"}).status_code == 403
    qa_login(client, role="admin")
    b = _bootcamp(client)
    keep = b["tasks"][0]["id"]
    e = client.put(f"/api/admin/bootcamps/{b['id']}", json={"n": 3, "title": "Offer, v2", "published": False,
                                                            "tasks": [{"id": keep, "title": "Write your offer"}, {"title": "New task"}]}).json()
    assert e["n"] == 3 and e["tasks"][0]["id"] == keep and len(e["tasks"]) == 2 and e["resources"] == []
    assert client.post("/api/admin/bootcamps", json={"title": "Bad", "resources": [{"title": "x", "url": "ftp://files/x"}]}).status_code == 400
    assert client.post("/api/admin/bootcamps/submissions/nope/review", json={"feedback": "ok ok"}).status_code == 404
    assert client.delete(f"/api/admin/bootcamps/{b['id']}").json()["ok"]
    assert client.get(f"/api/admin/bootcamps/{b['id']}/submissions").status_code == 404
