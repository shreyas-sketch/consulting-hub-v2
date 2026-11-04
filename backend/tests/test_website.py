"""Website Builder: first build, page caps, edit by prompt (proposal, refund), public pages and preview, the contact
form (honeypot, rate limit), images, own domain, and the middleware that serves a site on its own address."""
from fastapi.testclient import TestClient

from conftest import qa_login, run

import llm
from growth.clock import ist_month_key, utcnow

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def build(c, **body):
    r = c.post("/api/website/build", json=body)
    assert r.status_code == 200, r.text
    return r.json()["site"]


def page(site, key="home"):
    return next(p for p in site["pages"] if p["key"] == key)


def sec(site, typ, key="home"):
    return next(s for s in page(site, key)["sections"] if s["type"] == typ)


def niche(c):
    r = c.post("/api/start/snapshot", json={"experiences": ["Supply chain", "Team leadership"], "enjoy": [0],
                                            "industry": "FMCG", "years": 22})
    assert r.status_code == 200, r.text


def used(c):
    return c.get("/api/me/plan").json()["limits"]["site_ai"]["used"]


def test_member_builds_one_page_site(client):
    c = client
    qa_login(c, plan="member")
    st = c.get("/api/website").json()
    assert st["site"] is None and st["caps"] == {"pages": 1, "custom_domain": False, "editorial": False}
    assert next(lk for lk in st["looks"] if lk["key"] == "editorial")["locked"]
    site = build(c, look="mentor")
    assert [p["key"] for p in site["pages"]] == ["home"] and site["look"] == "mentor" and site["slug"] == "demo-member"
    assert [s["type"] for s in page(site)["sections"]] == ["hero", "problems", "method", "services", "about", "proof",
                                                           "faq", "contact"]
    assert len(sec(site, "method")["data"]["steps"]) == 6
    assert sec(site, "method")["data"]["steps"][0]["title"] == "Understand the real problem"
    proof = sec(site, "proof")
    assert proof["placeholders"] > 0 and proof["data"]["items"][0]["result"].startswith("[")   # never invented
    assert site["placeholders"] and not site["published"] and used(c) == 1
    assert c.post("/api/website/build", json={}).status_code == 409
    r = c.post("/api/website/pages", json={"key": "about"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked" and r.json()["detail"]["plan_needed"] == "l1"
    assert c.put("/api/website/settings", json={"look": "editorial"}).status_code == 403


def test_free_account_is_locked(client):
    qa_login(client, plan="free")
    r = client.get("/api/website")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    assert client.post("/api/website/build", json={}).status_code == 403


def test_build_limit(client, mdb):
    c = client
    me = qa_login(c, plan="member")["user"]
    run(mdb.usage.update_one({"_id": f"{me['id']}:{ist_month_key()}"}, {"$set": {"site_ai": 20, "user_id": me["id"]}},
                             upsert=True))
    r = c.post("/api/website/build", json={})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_l1_gets_five_pages_from_offer_card_and_stories(client, mdb):
    c = client
    me = qa_login(c, plan="l1")["user"]
    now = utcnow()
    run(mdb.offer_cards.insert_one({"_id": "o1", "user_id": me["id"], "offer_name": "Margin Rescue Sprint",
                                    "ideal_client": "Owner-led FMCG distributors", "problem": "falling margins",
                                    "outcome": "a clear margin plan", "what_you_get": ["Diagnosis", "Plan"],
                                    "fee_from_inr": 50000, "fee_to_inr": 150000, "at": now}))
    run(mdb.stories.insert_one({"_id": "st1", "user_id": me["id"], "title": "Turned around a loss-making depot",
                                "situation": "The depot lost money for 3 years.", "what_i_did": "I cut routes.",
                                "result": "Profit in 8 months.", "at": now}))
    site = build(c)
    assert [p["key"] for p in site["pages"]] == ["home", "about", "services", "case-studies", "contact"]
    svc = sec(site, "services")["data"]["items"][0]
    assert svc["name"] == "Margin Rescue Sprint" and svc["fee"] == "₹50,000 – ₹1,50,000"
    case = sec(site, "proof", "case-studies")["data"]["items"]
    assert case == [{"title": "Turned around a loss-making depot", "situation": "The depot lost money for 3 years.",
                     "action": "I cut routes.", "result": "Profit in 8 months."}]
    assert c.get("/api/website").json()["caps"] == {"pages": 5, "custom_domain": True, "editorial": False}
    assert c.delete("/api/website/pages/home").status_code == 400
    assert [p["key"] for p in c.delete("/api/website/pages/about").json()["site"]["pages"]] == \
        ["home", "services", "case-studies", "contact"]
    assert c.post("/api/website/pages", json={"key": "about"}).status_code == 200


def test_ai_numbers_not_in_the_members_facts_become_placeholders(client, monkeypatch):
    from features import site_ai
    assert site_ai.scrub("I have 30 years and helped 500 clients in 6 steps, 5 years ago", {"30"}) == \
        "I have 30 years and helped [number] clients in 6 steps, [number] years ago"
    assert site_ai.scrub("[e.g. 20 years] and ₹5 lakh", set()) == "[e.g. 20 years] and [number] lakh"
    c = client
    qa_login(c, plan="member")

    async def liar(**kw):
        d = kw["fake"]()
        d["hero"]["headline"] = "Grow profit 3x in 90 days"
        d["about"]["points"] = ["Worked with 120 companies"]
        return d
    monkeypatch.setattr(llm, "complete_json", liar)
    site = build(c)
    assert sec(site, "hero")["data"]["headline"] == "Grow profit [number]x in [number] days"
    assert sec(site, "about")["data"]["points"] == ["Worked with [number] companies"]


def test_edit_by_prompt_proposal_apply_and_undo(client):
    c = client
    qa_login(c, plan="member")
    site = build(c)
    hero = sec(site, "hero")
    before = hero["data"]["sub"]
    r = c.post(f"/api/website/sections/{hero['id']}/ai", json={"page": "home", "instruction": "Make this shorter"}).json()
    assert r["changed"] and r["proposal"]["before"]["sub"] == before and r["proposal"]["after"]["sub"] != before
    assert used(c) == 2
    st = c.get("/api/website").json()["site"]
    assert st["proposal"]["section_id"] == hero["id"] and sec(st, "hero")["data"]["sub"] == before   # not applied yet
    st = c.post("/api/website/proposal/apply").json()["site"]
    assert sec(st, "hero")["data"]["sub"] == r["proposal"]["after"]["sub"] and st["proposal"] is None and st["can_undo"]
    st = c.post("/api/website/undo").json()["site"]
    assert sec(st, "hero")["data"]["sub"] == before
    # a request that changes nothing gives the go back
    r = c.post(f"/api/website/sections/{hero['id']}/ai", json={"instruction": "Make the colours blue"}).json()
    assert r["changed"] is False and r["refunded"] and used(c) == 2
    # discard
    c.post(f"/api/website/sections/{hero['id']}/ai", json={"instruction": "shorter please"})
    assert c.post("/api/website/proposal/discard").json()["site"]["proposal"] is None


def test_edit_by_prompt_refunds_on_ai_error(client, monkeypatch):
    c = client
    qa_login(c, plan="member")
    site = build(c)
    assert used(c) == 1

    async def boom(**kw):
        raise llm.LLMError("busy")
    monkeypatch.setattr(llm, "complete_json", boom)
    r = c.post(f"/api/website/sections/{sec(site, 'faq')['id']}/ai", json={"instruction": "Make this shorter"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_busy"
    assert used(c) == 1


def test_manual_edit_hide_reorder_and_settings(client):
    c = client
    qa_login(c, plan="member")
    site = build(c)
    hero = sec(site, "hero")
    st = c.put(f"/api/website/sections/{hero['id']}", json={"data": {**hero["data"], "headline": "Profit help for distributors"}}).json()["site"]
    assert sec(st, "hero")["data"]["headline"] == "Profit help for distributors" and used(c) == 1   # by hand is free
    assert c.put(f"/api/website/sections/{hero['id']}", json={"data": {"headline": " "}}).status_code == 400
    faq = sec(st, "faq")
    st = c.put(f"/api/website/sections/{faq['id']}", json={"hidden": True}).json()["site"]
    assert sec(st, "faq")["hidden"]
    ids = [s["id"] for s in page(st)["sections"]][::-1]
    st = c.put("/api/website/pages/home/order", json={"ids": ids}).json()["site"]
    assert [s["id"] for s in page(st)["sections"]] == ids
    assert c.put("/api/website/pages/home/order", json={"ids": ids[1:]}).status_code == 400
    st = c.post("/api/website/pages/home/sections", json={"type": "faq"}).json()["site"]
    assert len(page(st)["sections"]) == 9
    contact = {"email": "asha@example.in", "whatsapp": "98765 43210", "calendly": "https://calendly.com/asha/intro"}
    st = c.put("/api/website/settings", json={"slug": "asha-mehta", "contact": contact, "title": "Margin consultant"}).json()["site"]
    assert st["slug"] == "asha-mehta" and st["contact"]["calendly"] == contact["calendly"]
    assert c.put("/api/website/settings", json={"slug": "No Spaces!"}).status_code == 400
    assert c.put("/api/website/settings", json={"contact": {**contact, "calendly": "javascript:alert(1)"}}).status_code == 400
    c.post("/api/auth/logout")
    qa_login(c, plan="l1")
    build(c)
    assert c.put("/api/website/settings", json={"slug": "asha-mehta"}).json()["detail"]["code"] == "slug_taken"


def test_public_page_404_until_published_and_preview_for_owner_only(client):
    c = client
    qa_login(c, plan="member")
    niche(c)
    site = build(c)
    slug = site["slug"]
    assert c.get(f"/s/{slug}").status_code == 404
    pv = c.get(f"/s/{slug}?preview=1")
    assert pv.status_code == 200 and "noindex" in pv.text and 'class="ph"' in pv.text and "Only you can see this" in pv.text
    c.post("/api/auth/logout")
    assert c.get(f"/s/{slug}?preview=1").status_code == 404
    qa_login(c, plan="l1")                                   # someone else, logged in
    assert c.get(f"/s/{slug}?preview=1").status_code == 404
    c.post("/api/auth/logout")
    qa_login(c, plan="member")
    st = c.post("/api/website/publish", json={"on": True}).json()["site"]
    assert st["published"] and st["published_at"]
    c.post("/api/auth/logout")
    r = c.get(f"/s/{slug}")
    assert r.status_code == 200 and sec(site, "hero")["data"]["headline"] in r.text
    assert '<meta property="og:title"' in r.text and "<title>" in r.text and 'name="description"' in r.text
    assert 'class="ph"' not in r.text and "[" not in r.text.split("<main>")[1].split("</main>")[0]   # placeholders left out
    assert "<script" not in r.text
    assert c.get(f"/s/{slug}/about").status_code == 404     # one page on the ₹1,999 plan
    assert c.get("/s/nobody-here").status_code == 404


def test_lead_form_honeypot_and_rate_limit(client, mdb):
    c = client
    owner = qa_login(c, plan="member")["user"]
    slug = build(c)["slug"]
    lead = {"name": "Ravi Shah", "email": "ravi@acme.in", "company": "Acme", "message": "Our margins fell."}
    c.post("/api/auth/logout")
    assert c.post(f"/api/website/public/{slug}/leads", json=lead).status_code == 404     # not live yet
    qa_login(c, plan="member")
    c.post("/api/website/publish", json={"on": True})
    c.post("/api/auth/logout")
    r = c.post(f"/api/website/public/{slug}/leads", data={**lead, "page": "home"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/s/{slug}?sent=1#contact"
    assert c.post(f"/api/website/public/{slug}/leads", json={**lead, "website": "http://spam"}).json() == {"ok": True}
    assert run(mdb.site_leads.count_documents({})) == 1                                   # honeypot not saved
    r = c.post(f"/api/website/public/{slug}/leads", json={"name": "Ravi"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "details"
    for _ in range(4):
        assert c.post(f"/api/website/public/{slug}/leads", json=lead).status_code == 200
    r = c.post(f"/api/website/public/{slug}/leads", json=lead)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "busy"
    assert run(mdb.site_leads.count_documents({})) == 5
    inbox = run(mdb.inbox.find_one({"user_id": owner["id"], "kind": "site_lead"}))
    assert inbox and "Ravi Shah from Acme" in inbox["body"]
    qa_login(c, plan="member")
    items = c.get("/api/website/leads").json()["items"]
    assert len(items) == 5 and items[0]["email"] == "ravi@acme.in" and "ip" not in items[0]
    assert c.get("/api/website").json()["site"]["leads_unread"] == 0


def test_images(client):
    c = client
    qa_login(c, plan="member")
    slug = build(c)["slug"]
    r = c.post("/api/website/images/logo", files={"file": ("logo.png", PNG, "image/png")})
    assert r.status_code == 200 and r.json()["site"]["logo_url"].startswith("/api/blobs/")
    img = c.get(f"/s/{slug}/img/logo")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert c.post("/api/website/images/photo", files={"file": ("a.gif", b"GIF89a....", "image/gif")}).status_code == 400
    big = PNG + b"\x00" * (2 * 1024 * 1024)
    assert c.post("/api/website/images/photo", files={"file": ("big.png", big, "image/png")}).status_code == 413
    assert c.delete("/api/website/images/logo").json()["site"]["logo_url"] is None


def test_own_domain_locked_for_member_and_connects_on_l1(client, monkeypatch):
    from features import website
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://hub.example.com")
    c = client
    qa_login(c, plan="member")
    build(c)
    r = c.put("/api/website/domain", json={"domain": "www.asha.in"})
    assert r.status_code == 403 and r.json()["detail"]["plan_needed"] == "l1"
    c.post("/api/auth/logout")
    qa_login(c, plan="l1")
    build(c)
    st = c.put("/api/website/domain", json={"domain": "https://Asha-Consulting.in/about"}).json()["site"]
    assert st["domain"] == "www.asha-consulting.in" and st["domain_status"] == "pending"
    assert st["dns"] == {"type": "CNAME", "name": "www", "value": "hub.example.com", "domain": "www.asha-consulting.in"}
    assert c.put("/api/website/domain", json={"domain": "not a domain"}).status_code == 400
    assert c.put("/api/website/domain", json={"domain": "x.hub.example.com"}).status_code == 400

    async def cname(d):
        return ["hub.example.com"]
    monkeypatch.setattr(website, "lookup_cname", cname)
    r = c.post("/api/website/domain/check").json()
    assert r["check"]["ok"] and r["site"]["domain_status"] == "pending"            # the check only reports
    site_id = r["site"]["id"]
    c.post("/api/auth/logout")
    qa_login(c, role="admin")
    assert c.post(f"/api/admin/website/domains/{site_id}", json={"status": "connected"}).json() == {"ok": True}
    qa_login(c, plan="l1")
    st = c.get("/api/website").json()["site"]
    assert st["domain_status"] == "connected" and st["url"] == "https://www.asha-consulting.in"
    assert c.delete("/api/website/domain").json()["site"]["domain"] is None


def test_middleware_serves_a_site_by_host(mdb, monkeypatch):
    import server
    from features import website
    monkeypatch.setenv("SITES_DOMAIN", "sites.example.com")
    website.clear_host_cache()
    app = server.create_app(mdb, start_jobs=False, seed=False, serve_spa=False)
    website.install_domain_middleware(app)
    with TestClient(app) as c:
        qa_login(c, plan="l1")
        niche(c)
        site = build(c)
        slug = site["slug"]
        c.put("/api/website/domain", json={"domain": "www.asha-consulting.in"})
        own = {"host": "www.asha-consulting.in"}
        assert c.get("/api/health", headers=own).status_code == 200    # a request is not routed until the team connects it
        c.post("/api/auth/logout")
        qa_login(c, role="admin")
        assert c.post(f"/api/admin/website/domains/{site['id']}", json={"status": "connected"}).status_code == 200
        qa_login(c, plan="l1")
        website.clear_host_cache()
        assert c.get("/", headers=own).status_code == 404               # not published yet
        c.post("/api/website/publish", json={"on": True})
        website.clear_host_cache()
        home = c.get("/", headers=own)
        assert home.status_code == 200 and sec(site, "hero")["data"]["cta"] in home.text
        assert 'href="/about"' in home.text and f"/s/{slug}" not in home.text.split("<main>")[1]
        assert c.get("/about", headers=own).status_code == 200
        assert c.get("/api/website", headers=own).status_code == 404    # the hub never answers on a member's address
        assert c.get("/login", headers=own).status_code == 404
        r = c.post(f"/api/website/public/{slug}/leads", headers=own, follow_redirects=False,
                   data={"name": "Meera", "phone": "9876543210", "page": "contact"})
        assert r.status_code == 303 and r.headers["location"] == "/contact?sent=1#contact"
        sub = c.get("/", headers={"host": f"{slug}.sites.example.com:443"})
        assert sub.status_code == 200 and sec(site, "hero")["data"]["cta"] in sub.text
        assert c.get("/", headers={"host": "nobody-here.sites.example.com"}).status_code == 404
        assert c.get("/api/health", headers={"host": "www.sites.example.com"}).status_code == 200   # reserved: the hub
        assert c.get("/api/health", headers={"host": "some-other-host.org"}).status_code == 200     # not a site: the hub
        assert c.get("/api/website").status_code == 200                  # the hub's own host is untouched
    website.clear_host_cache()
