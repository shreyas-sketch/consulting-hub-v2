"""LinkedIn Profile Review: screenshots → client's-eye review, and the 30-day post plan."""
import io
from datetime import timedelta

import pytest

from tests.conftest import qa_login


def _png(w=1080, h=900, color=(240, 244, 250)):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), color)
    ImageDraw.Draw(im).text((40, 40), "General Manager - Operations at ABC Ltd", fill=(10, 10, 10))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _used(client, key):
    me = client.get("/api/auth/me").json()

    def find(d):
        if isinstance(d, dict):
            if "limits" in d:
                return d["limits"]
            for v in d.values():
                r = find(v)
                if r:
                    return r
        return None
    return (find(me) or {}).get(key, {}).get("used", 0)


def _upload(client, files, target="Owner-run auto component makers in Pune"):
    return client.post("/api/linkedin-review", data={"target": target},
                       files=[("files", (n, b, t)) for n, b, t in files])


def test_review_from_screenshots_counts_one_go(client):
    qa_login(client, plan="l1")
    r = _upload(client, [("top.png", _png(), "image/png"), ("about.png", _png(), "image/png")])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["client_view"] and d["verdict"] and 0 <= d["score"] <= 100
    assert len(d["headlines"]) >= 2 and len(d["about"]) >= 200 and len(d["sections"]) >= 3
    assert d["images"] == 2 and d["read"]["headline"]
    assert _used(client, "li_review") == 1
    s = client.get("/api/linkedin-review").json()
    assert s["review"]["id"] == d["id"] and s["max_files"] == 5


def test_not_an_image_is_refused_and_costs_nothing(client):
    qa_login(client, plan="l1")
    r = _upload(client, [("notes.txt", b"just text", "text/plain")])
    assert r.status_code == 415
    assert _used(client, "li_review") == 0


def test_too_many_files_and_no_target(client):
    qa_login(client, plan="l1")
    r = _upload(client, [(f"{i}.png", _png(), "image/png") for i in range(6)])
    assert r.status_code == 422 and r.json()["detail"]["code"] == "too_many"
    r = _upload(client, [("a.png", _png(), "image/png")], target="")   # no niche chosen and nothing typed
    assert r.status_code == 422 and r.json()["detail"]["code"] == "target"
    assert _used(client, "li_review") == 0


def test_free_account_gets_one_review(client):
    qa_login(client, plan="free")
    assert _upload(client, [("a.png", _png(), "image/png")]).status_code == 200
    assert _upload(client, [("a.png", _png(), "image/png")]).status_code == 402


def test_tall_phone_screenshot_is_cut_into_readable_pieces():
    from features.linkedin_review import LONG_EDGE, prepare_images
    out = prepare_images([("phone.png", _png(1170, 2532))])
    assert len(out) == 2
    from PIL import Image
    for _, b in out:
        im = Image.open(io.BytesIO(b))
        assert im.format == "JPEG" and max(im.size) <= LONG_EDGE and im.size[1] / im.size[0] <= 1.6


def test_review_check_reads_real_model_shapes():
    from features.linkedin_review import clean_review
    raw = {"read": {"headline": "GM Ops"}, "client_view": ["I see a manager,", "not a consultant."],
           "sections": [{"section": "Profile photo", "status": "Strong", "now": "ok"},
                        {"name": "headline", "status": "improve", "change": "Lead with the client"},
                        {"key": "summary", "status": "missing"}, {"key": "nonsense"}],
           "headlines": ["I help pump makers grow dealer sales", {"headline": "Dealer network consultant", "angle": "Niche"}],
           "about": "x " * 150, "experience": [{"role": "GM", "bullets": "Cut cost 10%\nLed 40 people"}]}
    out = clean_review(raw)
    rv = out["review"]
    assert [s["key"] for s in rv["sections"]] == ["headline", "photo", "about"]
    assert rv["sections"][0]["fix"] == "Lead with the client" and rv["sections"][1]["status"] == "strong"
    assert [h["text"] for h in rv["headlines"]][1] == "Dealer network consultant"
    assert rv["experience"][0]["bullets"] == ["Cut cost 10%", "Led 40 people"]
    assert rv["score"] == 50 and rv["client_view"] == "I see a manager, not a consultant."


def test_review_check_refuses_incomplete_and_non_linkedin():
    import llm
    from core.errors import InvalidInput
    from features.linkedin_review import clean_review
    with pytest.raises(InvalidInput) as e:
        clean_review({"is_linkedin": False})
    assert e.value.detail["code"] == "not_linkedin"
    with pytest.raises(llm.LLMError) as e:
        clean_review({"client_view": "ok", "headlines": ["one"], "sections": [], "about": ""})
    assert "headlines" in str(e.value) and "about" in str(e.value)


def test_thirty_day_plan_dated_from_tomorrow_and_ticked_off(client):
    qa_login(client, plan="l1")
    _upload(client, [("a.png", _png(), "image/png")])
    r = client.post("/api/linkedin-review/plan", json={})
    assert r.status_code == 200, r.text
    p = r.json()
    assert len(p["posts"]) == 30 and [x["day"] for x in p["posts"]] == list(range(1, 31))
    from datetime import date
    first = date.fromisoformat(p["posts"][0]["date"])
    assert date.fromisoformat(p["posts"][29]["date"]) == first + timedelta(days=29)
    assert p["pillars"] and p["review_id"] and p["posted"] == 0
    r = client.patch(f"/api/linkedin-review/plan/{p['id']}/posts/3", json={"posted": True})
    assert r.status_code == 200 and r.json()["posted"] == 1 and r.json()["posts"][2]["posted"] is True
    assert client.patch(f"/api/linkedin-review/plan/{p['id']}/posts/31", json={"posted": True}).status_code == 404
    assert _used(client, "li_plan") == 1


def test_plan_check_needs_most_of_the_month():
    import llm
    from features.linkedin_review import clean_plan
    from datetime import date
    with pytest.raises(llm.LLMError):
        clean_plan({"pillars": [{"name": "A"}], "posts": [{"hook": "h", "text": "t" * 50}] * 10}, date(2026, 11, 9))
    ok = clean_plan({"pillars": ["Proof"], "posts": [{"hook": f"h{i}", "post": "word " * 20, "format": "Carousel"}
                                                      for i in range(32)]}, date(2026, 11, 9))
    assert len(ok["posts"]) == 30 and ok["posts"][0]["format"] == "carousel" and ok["posts"][0]["date"] == "2026-11-09"
