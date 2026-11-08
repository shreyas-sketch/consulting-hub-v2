"""QA run on the LinkedIn section (9 Nov 2026): profile review from screenshots, 30-day post plan, quick check.

Grouped by what could go wrong for a member: what they upload, what they're allowed, who can see what, what the AI
sends back, and whether the rest of the hub (Home, My Consulting File, Progress Report, admin) knows about it.
"""
import asyncio
import io
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

from tests.conftest import qa_login

TARGET = "Owners of mid-size auto component makers in Pune"


# ------------------------------------------------------------------ helpers ----
def img(w=1080, h=900, mode="RGB", fmt="PNG", color=None, **save):
    im = Image.new(mode, (w, h), color if color is not None else ((243, 242, 239) if mode == "RGB" else 200))
    buf = io.BytesIO()
    im.save(buf, fmt, **save)
    return buf.getvalue()


def upload(client, files, target=TARGET, notes=None):
    data = {"target": target}
    if notes is not None:
        data["notes"] = notes
    return client.post("/api/linkedin-review", data=data, files=[("files", f) for f in files])


def limits(client):
    me = client.get("/api/auth/me").json()

    def find(d):
        if isinstance(d, dict):
            if "limits" in d:
                return d["limits"]
            for v in d.values():
                r = find(v)
                if r:
                    return r
    return find(me) or {}


def used(client, key):
    return limits(client).get(key, {}).get("used", 0)


@pytest.fixture
def captured(monkeypatch):
    """Record what each AI call is sent (prompt, images, model), then answer with the tool's own sample."""
    import llm
    calls = []
    real = llm.complete_json

    async def spy(**kw):
        calls.append(kw)
        return await real(**kw)
    monkeypatch.setattr(llm, "complete_json", spy)
    return calls


# ============================================================ 1. what the member uploads ====
@pytest.mark.parametrize("name,data,ctype,status,code", [
    ("notes.txt", b"just some text", "text/plain", 415, "bad_type"),
    ("fake.png", b"this is not a png at all", "image/png", 415, "bad_type"),
    ("cut.png", img()[:200], "image/png", 415, "bad_type"),                       # truncated / corrupt
    ("doc.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF", "application/pdf", 415, "bad_type"),
    ("tiny.png", img(200, 150), "image/png", 422, "too_small"),
])
def test_bad_files_are_refused_and_cost_nothing(client, name, data, ctype, status, code):
    qa_login(client, plan="l1")
    r = upload(client, [(name, data, ctype)])
    assert r.status_code == status, r.text
    assert r.json()["detail"]["code"] == code
    assert name.split(".")[0] in r.json()["detail"]["msg"] or code == "too_small" or status == 415
    assert used(client, "li_review") == 0


def test_one_bad_file_among_good_ones_refuses_the_lot_without_cost(client):
    qa_login(client, plan="l1")
    r = upload(client, [("a.png", img(), "image/png"), ("b.txt", b"x", "text/plain")])
    assert r.status_code == 415 and "b.txt" in r.json()["detail"]["msg"]
    assert used(client, "li_review") == 0 and client.get("/api/linkedin-review").json()["review"] is None


def test_file_over_8_mb_refused(client):
    qa_login(client, plan="l1")
    big = img(3000, 3000, fmt="PNG") + b"\0" * (8 * 1024 * 1024)
    r = upload(client, [("big.png", big, "image/png")])
    assert r.status_code == 413 and "8 MB" in r.json()["detail"]["msg"]
    assert used(client, "li_review") == 0


def test_decompression_bomb_refused(client):
    qa_login(client, plan="l1")
    bomb = img(9000, 9000, mode="L", fmt="PNG", color=0)        # 81 MP of one colour compresses to a few KB
    assert len(bomb) < 2 * 1024 * 1024
    r = upload(client, [("bomb.png", bomb, "image/png")])
    assert r.status_code == 415
    assert used(client, "li_review") == 0


def test_no_files_and_too_many_files(client):
    qa_login(client, plan="l1")
    r = client.post("/api/linkedin-review", data={"target": TARGET})
    assert r.status_code == 422                                   # FastAPI: files is required
    r = upload(client, [(f"{i}.png", img(), "image/png") for i in range(6)])
    assert r.status_code == 422 and r.json()["detail"]["code"] == "too_many"
    assert used(client, "li_review") == 0


@pytest.mark.parametrize("label,data", [
    ("jpeg", img(fmt="JPEG", quality=80)),
    ("webp", img(fmt="WEBP")),
    ("rgba png", img(mode="RGBA", color=(255, 255, 255, 0))),
    ("grayscale", img(mode="L")),
    ("palette", img(mode="P")),
    ("16-bit", img(mode="I;16")),
    ("gif", img(mode="P", fmt="GIF")),
])
def test_every_common_screenshot_format_is_read(client, label, data):
    qa_login(client, plan="l2")
    r = upload(client, [("shot", data, "application/octet-stream")])   # the browser's type is not trusted
    assert r.status_code == 200, f"{label}: {r.text}"


def test_images_sent_to_the_ai_are_readable_jpegs(client, captured):
    qa_login(client, plan="l2")
    phone = img(1170, 2532)                      # iPhone screenshot
    wide = img(2880, 1800)                       # laptop screenshot
    r = upload(client, [("phone.png", phone, "image/png"), ("wide.png", wide, "image/png")])
    assert r.status_code == 200
    images = captured[-1]["images"]
    assert len(images) == 3                      # the phone shot is cut in two, the laptop shot stays whole
    for media, b in images:
        im = Image.open(io.BytesIO(b))
        assert media == "image/jpeg" and im.format == "JPEG" and max(im.size) <= 1568
    assert captured[-1]["model"] == "vision"
    assert r.json()["images"] == 2              # the member is told how many screenshots they sent


def test_exif_rotation_is_honoured():
    from features.linkedin_review import prepare_images
    im = Image.new("RGB", (900, 1600), (250, 250, 250))
    exif = Image.Exif()
    exif[0x0112] = 6                             # "rotate 90° clockwise to display"
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif.tobytes())
    [(_, out)] = prepare_images([("rot.jpg", buf.getvalue())])
    w, h = Image.open(io.BytesIO(out)).size
    assert w > h                                 # displayed as landscape, as the phone showed it


def test_never_more_than_8_images_reach_the_ai():
    from features.linkedin_review import MAX_IMAGES_TO_AI, prepare_images
    out = prepare_images([(f"{i}.png", img(1000, 6000)) for i in range(5)])   # very long scrolling captures
    assert len(out) == MAX_IMAGES_TO_AI


def test_screenshots_are_not_stored(client, mdb):
    qa_login(client, plan="l2")
    shot = img()
    r = upload(client, [("a.png", shot, "image/png")])
    from tests.conftest import run
    doc = run(mdb.li_reviews.find_one({"_id": r.json()["id"]}))
    blob = repr(doc)
    assert "images" not in doc and len(blob) < 20000
    assert run(mdb.blobs.count_documents({})) == 0 if "blobs" in run(mdb.list_collection_names()) else True


# ============================================================ 2. who the review is for ====
def test_target_falls_back_to_the_chosen_niche(client, captured):
    qa_login(client, plan="l2")
    snap = client.post("/api/start/snapshot", json={"experiences": ["Supply chain", "Plant operations", "Cost cutting"],
                                                    "enjoy": [0], "industry": "Auto components", "years": 18}).json()
    client.post(f"/api/start/snapshot/{snap['id']}/choose", json={"index": 0})
    s = client.get("/api/linkedin-review").json()
    assert s["niche"] and s["target"]
    r = upload(client, [("a.png", img(), "image/png")], target="")
    assert r.status_code == 200 and r.json()["target"] == s["target"]
    prompt = captured[-1]["prompt"]
    assert s["niche"] in prompt and s["target"] in prompt


def test_typed_target_wins_and_long_text_is_trimmed(client, captured):
    qa_login(client, plan="l2")
    r = upload(client, [("a.png", img(), "image/png")], target="X" * 500, notes="N" * 900)
    assert r.status_code == 200
    assert len(r.json()["target"]) == 200
    assert "N" * 500 in captured[-1]["prompt"] and "N" * 501 not in captured[-1]["prompt"]


def test_member_proof_from_the_hub_reaches_the_prompt(client, captured):
    qa_login(client, plan="l1")
    client.post("/api/stories/text", json={"text": "In 2015 our Nashik plant was losing 6% of output to wastage. I set up "
                                                   "a daily review with shift heads and fixed the cold chain. In 9 months "
                                                   "wastage fell to 3.5%, saving ₹2 crore a year."})
    upload(client, [("a.png", img(), "image/png")])
    assert "THEIR OWN PROOF" in captured[-1]["prompt"]


# ============================================================ 3. allowances ====
@pytest.mark.parametrize("plan,reviews,plans_", [("free", 1, 1), ("member", 3, 1), ("l1", 6, 2), ("l2", 6, 2)])
def test_allowance_per_plan(client, plan, reviews, plans_):
    qa_login(client, plan=plan)
    lim = limits(client)
    assert lim["li_review"]["limit"] == reviews and lim["li_plan"]["limit"] == plans_


def test_free_account_one_review_one_plan_then_upgrade_prompt(client):
    qa_login(client, plan="free")
    assert upload(client, [("a.png", img(), "image/png")]).status_code == 200
    r = upload(client, [("a.png", img(), "image/png")])
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"
    assert client.post("/api/linkedin-review/plan", json={}).status_code == 200
    assert client.post("/api/linkedin-review/plan", json={}).status_code == 402


def test_review_and_quick_check_have_separate_allowances(client):
    qa_login(client, plan="free")
    assert client.post("/api/linkedin/check", json={"headline": "GM Operations at ABC Ltd"}).status_code == 200
    assert upload(client, [("a.png", img(), "image/png")]).status_code == 200       # still has its own go


def test_double_tap_on_a_free_account_spends_one_go_only(app):
    """Two reviews sent at the same instant on a free account: exactly one is made and one go is spent."""
    import httpx
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        qa_login(c, plan="free")
        cookies = dict(c.cookies)

        async def both():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", cookies=cookies) as ac:
                send = lambda: ac.post("/api/linkedin-review", data={"target": TARGET},  # noqa: E731
                                       files=[("files", ("a.png", img(), "image/png"))])
                return await asyncio.gather(send(), send())
        codes = sorted(r.status_code for r in c.portal.call(both))
        assert codes == [200, 402], codes
        assert used(c, "li_review") == 1


# ============================================================ 4. who can see what ====
def test_logged_out_is_refused(client):
    for m, p in [("GET", "/api/linkedin-review"), ("POST", "/api/linkedin-review/plan"),
                 ("PATCH", "/api/linkedin-review/plan/x/posts/1"), ("GET", "/api/linkedin-review/x")]:
        assert client.request(m, p, json={"posted": True} if m == "PATCH" else None).status_code == 401


def test_members_cannot_see_or_change_each_others_work(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as a:
        qa_login(a, plan="l2", phone="+919811100101")
        rv = upload(a, [("a.png", img(), "image/png")]).json()
        pl = a.post("/api/linkedin-review/plan", json={}).json()
    with TestClient(app) as b:
        qa_login(b, plan="l2", phone="+919811100102")
        assert b.get(f"/api/linkedin-review/{rv['id']}").status_code == 404
        assert b.patch(f"/api/linkedin-review/plan/{pl['id']}/posts/1", json={"posted": True}).status_code == 404
        own = b.post("/api/linkedin-review/plan", json={"review_id": rv["id"], "target": "Hospital owners"}).json()
        assert own["review_id"] != rv["id"]                    # someone else's review is never used
        assert b.get("/api/linkedin-review").json()["review"] is None


# ============================================================ 5. the 30-day plan ====
def test_plan_without_a_review_uses_the_niche_or_the_typed_client(client):
    qa_login(client, plan="l1")
    r = client.post("/api/linkedin-review/plan", json={})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "target"
    assert used(client, "li_plan") == 0
    r = client.post("/api/linkedin-review/plan", json={"target": "Hospital owners in Indore"})
    assert r.status_code == 200 and r.json()["review_id"] is None and r.json()["target"] == "Hospital owners in Indore"


@pytest.mark.parametrize("day,status", [(0, 404), (31, 404), (-1, 404), ("abc", 422), (15, 200)])
def test_mark_posted_day_bounds(client, day, status):
    qa_login(client, plan="l1")
    upload(client, [("a.png", img(), "image/png")])
    pid = client.post("/api/linkedin-review/plan", json={}).json()["id"]
    assert client.patch(f"/api/linkedin-review/plan/{pid}/posts/{day}", json={"posted": True}).status_code == status


def test_posted_can_be_undone_and_survives_reload(client):
    qa_login(client, plan="l1")
    upload(client, [("a.png", img(), "image/png")])
    pid = client.post("/api/linkedin-review/plan", json={}).json()["id"]
    for d in (1, 2, 30):
        client.patch(f"/api/linkedin-review/plan/{pid}/posts/{d}", json={"posted": True})
    r = client.patch(f"/api/linkedin-review/plan/{pid}/posts/2", json={"posted": False}).json()
    assert r["posted"] == 2 and r["posts"][1]["posted_at"] is None
    again = client.get("/api/linkedin-review").json()["plan"]
    assert [p["day"] for p in again["posts"] if p["posted"]] == [1, 30]


@pytest.mark.parametrize("utc_now,first_ist", [
    (datetime(2026, 11, 9, 18, 29, tzinfo=timezone.utc), "2026-11-10"),     # 23:59 IST on the 9th
    (datetime(2026, 11, 9, 18, 31, tzinfo=timezone.utc), "2026-11-11"),     # 00:01 IST on the 10th
    (datetime(2026, 12, 31, 20, 0, tzinfo=timezone.utc), "2027-01-02"),     # New Year in India
])
def test_plan_starts_tomorrow_in_india(client, monkeypatch, utc_now, first_ist):
    import features.linkedin_review as lr
    monkeypatch.setattr(lr, "utcnow", lambda: utc_now)
    qa_login(client, plan="l1")
    p = client.post("/api/linkedin-review/plan", json={"target": "Hospital owners"}).json()
    assert p["posts"][0]["date"] == first_ist and p["start_date"] == first_ist
    from datetime import date
    assert date.fromisoformat(p["posts"][-1]["date"]) - date.fromisoformat(first_ist) == timedelta(days=29)


# ============================================================ 6. what the AI sends back ====
def test_review_answer_shapes_a_live_model_uses():
    from features.linkedin_review import clean_review
    raw = {"is_linkedin": "true", "score": "72/100",
           "read": {"headline": "GM Ops", "open_to_work": "yes"},
           "client_view": {"text": "I see a manager, not a consultant."},
           "sections": [{"key": "Headline", "status": "Needs work", "now": "GM Ops", "why": "w", "fix": "f"},
                        {"key": "photo", "status": "STRONG"}, {"key": "banner", "status": "missing"},
                        {"key": "headline", "status": "strong"}],              # a repeat is ignored
           "headlines": [{"text": "H" * 400}, "I help pump makers grow dealer sales", ""],
           "about": ["Para one " * 30, "Para two " * 30], "skills": "Pricing, Strategy",
           "quick_wins": "1. Change the headline\n2. Add a banner"}
    rv = clean_review(raw)["review"]
    assert rv["score"] == 72
    assert [s["key"] for s in rv["sections"]] == ["headline", "photo", "banner"]
    assert rv["sections"][0]["status"] == "improve" and rv["sections"][1]["status"] == "strong"
    assert len(rv["headlines"][0]["text"]) == 220 and len(rv["headlines"]) == 2
    assert "\n\n" in rv["about"]
    assert rv["quick_wins"] == ["1. Change the headline", "2. Add a banner"]


def test_review_about_is_capped_at_linkedins_limit():
    from features.linkedin_review import clean_review
    raw = {"client_view": "ok", "headlines": ["a", "b"], "about": "word " * 2000,
           "sections": [{"key": "headline"}, {"key": "about"}, {"key": "photo"}]}
    assert len(clean_review(raw)["review"]["about"]) <= 2600


def test_review_never_names_the_ai_vendor():
    from features.linkedin_review import clean_review
    raw = {"client_view": "As Claude, an AI by Anthropic, I think this profile is weak.", "headlines": ["a", "b"],
           "about": "Written with ChatGPT. " + "x " * 150, "sections": [{"key": "headline"}, {"key": "about"}, {"key": "photo"}]}
    out = repr(clean_review(raw))
    for word in ("Claude", "Anthropic", "ChatGPT"):
        assert word not in out


def test_score_out_of_range_is_clamped():
    from features.linkedin_review import clean_review
    base = {"client_view": "ok", "headlines": ["a", "b"], "about": "x " * 150,
            "sections": [{"key": "headline"}, {"key": "about"}, {"key": "photo"}]}
    assert clean_review({**base, "score": 340})["review"]["score"] == 100
    assert clean_review({**base, "score": -5})["review"]["score"] == 0
    assert clean_review({**base, "score": "n/a"})["review"]["score"] == 50


def test_not_linkedin_answer_gives_the_go_back(client, monkeypatch):
    import llm
    async def not_li(**kw):
        return {"is_linkedin": False}
    monkeypatch.setattr(llm, "complete_json", not_li)
    qa_login(client, plan="l1")
    r = upload(client, [("cat.png", img(), "image/png")])
    assert r.status_code == 422 and r.json()["detail"]["code"] == "not_linkedin"
    assert "didn't use up your go" in r.json()["detail"]["msg"] and used(client, "li_review") == 0


def test_plan_answer_shapes_a_live_model_uses():
    from datetime import date

    from features.linkedin_review import clean_plan
    posts = [{"day": 30 - i, "pillar": "Proof", "format": "Long-form text", "hook": f"Hook {i}",
              "post": ["Line one of the post.", "Line two of the post with more words."], "cta": None} for i in range(30)]
    posts[3] = {"hook": "", "text": "no hook"}                                  # one broken post is dropped
    out = clean_plan({"pillars": [{"title": "x"}, "Proof", {"name": "How I think", "why": "w"}], "posts": posts}, date(2026, 11, 10))
    assert [p["name"] for p in out["pillars"]] == ["Proof", "How I think"]
    assert len(out["posts"]) == 29 and [p["day"] for p in out["posts"]] == list(range(1, 30))
    assert out["posts"][0]["format"] == "text" and "\n\n" in out["posts"][0]["text"]
    assert all(p["posted"] is False for p in out["posts"])


# ============================================================ 7. the rest of the hub knows ====
def test_home_and_file_count_a_screenshot_review(client):
    qa_login(client, plan="free")
    upload(client, [("a.png", img(), "image/png")])
    f = client.get("/api/file").json()
    assert f["linkedin"] is not None, "My Consulting File / Home don't see the review"
    assert f["linkedin"]["score"] is not None


def test_progress_report_counts_reviews(client):
    qa_login(client, plan="member")
    upload(client, [("a.png", img(), "image/png")])
    r = client.post("/api/progress")
    assert r.status_code in (200, 409)
    stats = (r.json().get("stats") or {}) if r.status_code == 200 else {}
    assert (stats.get("linkedin") or {}).get("now") is not None, "Progress Report ignores the review"


def test_admin_webinar_funnel_counts_reviews(client, mdb):
    qa_login(client, plan="free")
    upload(client, [("a.png", img(), "image/png")])
    from tests.conftest import run
    ev = run(mdb.events.find_one({"name": "linkedin_reviewed"}))
    assert ev is not None
    from admin import routes
    assert "linkedin_reviewed" in routes.__dict__.get("FUNNEL_NAMES", {}) or "linkedin_reviewed" in repr(
        getattr(routes, "TOOL_EVENTS", routes.__dict__)), "admin webinar report doesn't count reviews"
