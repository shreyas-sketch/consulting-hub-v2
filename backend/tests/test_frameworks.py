"""Work along with Akshat: the three workshop frameworks as interactive cases, save, and a proposal."""
import pytest

from tests.conftest import qa_login

NOKIA = {"circles": {"price": {"verdict": "works", "why": "Phones from about ₹1,500, anyone could afford one."},
                     "value": {"verdict": "fails", "why": "Stayed on Symbian; late to touchscreen smartphones."},
                     "availability": {"verdict": "works", "why": "Sold in every town, Tier 2 and Tier 3 too."}},
         "summary": "Price and reach held, but the value circle came apart when smartphones arrived."}
INTERIOR = {"percents": [60, 30, 10], "recommendation": "wait", "target_pct": 35, "months": 12,
            "reason": "60% comes from one developer; if they leave, the firm loses most of its revenue overnight."}
COACH = {"zone": 3, "fix": "reach", "actions": ["Run a free monthly career-switch webinar", "Partner with 3 HR communities",
                                               "Ask alumni for referrals with a small reward"]}
ALL = {"market-fit": NOKIA, "concentration-risk": INTERIOR, "growth-compass": COACH}

SITU = "A 6-year-old business with a team of 12; profitable, but the owner wants to grow and asked you to look first."
OWN = {"market-fit": {"client": "a family-run sweet shop chain in Pune", "product": "its dry-fruit mithai boxes",
                      "new_region": "Hyderabad", "situation": SITU},
       "concentration-risk": {"client": "a CA firm in Indore", "situation": SITU,
                              "sources": [{"name": "Audit for one group", "amount": 2_500_000},
                                          {"name": "GST filings", "amount": 1_500_000},
                                          {"name": "Personal tax", "amount": 750_000},
                                          {"name": "Advisory", "amount": 250_000}]},
       "growth-compass": {"client": "a yoga studio in Kochi", "situation": SITU, "reach_per_month": 3000,
                          "conversion_pct": 1.5, "reach_level": "high", "conversion_level": "low"}}
OWN_ANS = {"market-fit": {"circles": {"price": {"verdict": "works", "why": "Priced like local mithai shops there."},
                                      "value": {"verdict": "works", "why": "Dry-fruit boxes are a gifting staple."},
                                      "availability": {"verdict": "fails", "why": "No shops or delivery partner yet."}},
                          "summary": "Price and value hold; availability is the gap to close before the launch."},
           "concentration-risk": {"percents": [50, 30, 15, 5], "recommendation": "wait", "target_pct": 35, "months": 12,
                                  "reason": "Half the revenue is one audit group; losing it would halve the firm."},
           "growth-compass": {"zone": 2, "fix": "offer", "actions": ["Add a free first-class trial with follow-up",
                                                                     "Package a 3-month plan with a clear outcome",
                                                                     "Call every trial guest within a day"]}}


def niche(client):
    snap = client.post("/api/start/snapshot", json={"experiences": ["Retail operations", "Franchise growth", "Pricing"],
                                                    "enjoy": [0], "industry": "Retail", "years": 18}).json()
    client.post(f"/api/start/snapshot/{snap['id']}/choose", json={"index": 0})


def used(c, k):
    me = c.get("/api/auth/me").json()

    def find(d):
        if isinstance(d, dict):
            if "limits" in d:
                return d["limits"]
            for v in d.values():
                r = find(v)
                if r:
                    return r
    return (find(me) or {}).get(k, {}).get("used", 0)


def test_three_frameworks_in_workshop_order_for_every_plan(client):
    qa_login(client, plan="free")
    items = client.get("/api/frameworks").json()["items"]
    assert [x["key"] for x in items] == ["market-fit", "concentration-risk", "growth-compass"]
    assert all(not x["saved"] and x["score"] is None for x in items)
    d = client.get("/api/frameworks/concentration-risk").json()
    assert d["framework"]["case"]["total"] == 18_000_000 and d["mine"] is None
    assert d["akshat"] is None and "akshat" not in d["framework"]          # Akshat's read only after saving
    assert client.get("/api/frameworks/nope").status_code == 404


@pytest.mark.parametrize("key,body", [
    ("market-fit", {"circles": {"price": NOKIA["circles"]["price"]}, "summary": NOKIA["summary"]}),     # one circle
    ("market-fit", {**NOKIA, "summary": "  "}),
    ("market-fit", {**NOKIA, "circles": {**NOKIA["circles"], "value": {"verdict": "fails", "why": " "}}}),
    ("market-fit", {**NOKIA, "circles": {**NOKIA["circles"], "value": {"verdict": "maybe", "why": "it is unclear really"}}}),
    ("concentration-risk", {**INTERIOR, "percents": [60, 40]}),
    ("concentration-risk", {**INTERIOR, "percents": [160, 30, 10]}),
    ("concentration-risk", {**INTERIOR, "recommendation": "think"}),
    ("concentration-risk", {**INTERIOR, "reason": ""}),
    ("concentration-risk", {**INTERIOR, "months": 0}),
    ("growth-compass", {**COACH, "zone": 5}),
    ("growth-compass", {**COACH, "actions": ["", "two", "three"]}),
    ("growth-compass", {**COACH, "actions": ["Run a webinar every month"]}),
    ("growth-compass", {**COACH, "fix": "everything"}),
])
def test_incomplete_activity_is_refused_in_plain_words(client, key, body):
    qa_login(client, plan="free")
    r = client.put(f"/api/frameworks/{key}/response", json=body)
    assert r.status_code == 422, r.text
    msg = r.json()["detail"]["msg"]
    assert msg and "value_error" not in msg and "{" not in msg
    assert client.get(f"/api/frameworks/{key}").json()["mine"] is None


@pytest.mark.parametrize("key", list(ALL))
def test_right_answers_score_full_marks_and_show_akshats_read(client, key):
    qa_login(client, plan="free")
    d = client.put(f"/api/frameworks/{key}/response", json=ALL[key]).json()
    g = d["mine"]["grade"]
    assert g["correct"] is True and g["score"] == g["out_of"] and d["akshat"]["read"]
    row = next(x for x in client.get("/api/frameworks").json()["items"] if x["key"] == key)
    assert row["saved"] and row["score"] == row["out_of"] and not row["proposal"]


@pytest.mark.parametrize("key,body", [
    ("market-fit", {"circles": {"price": {"verdict": "works", "why": "Cheap"}, "value": {"verdict": "fails", "why": "No smartphones"},
                                "availability": {"verdict": "works", "why": "Everywhere"}}, "summary": "Value failed"}),
    ("concentration-risk", {**INTERIOR, "reason": "Too risky", "target_pct": 35.5}),
    ("growth-compass", {**COACH, "actions": ["Webinars", "Ads", "SEO"]}),
])
def test_short_real_answers_are_saved(client, key, body):
    """The page shows Save as soon as every step has an answer; the server must accept what it accepts."""
    qa_login(client, plan="free")
    r = client.put(f"/api/frameworks/{key}/response", json=body)
    assert r.status_code == 200, r.text


def test_wrong_answers_are_marked_point_by_point():
    from features.frameworks import grade
    g = grade("market-fit", {"circles": {"price": {"verdict": "fails"}, "value": {"verdict": "fails"},
                                         "availability": {"verdict": "works"}}, "summary": "x"})
    assert (g["score"], g["out_of"], g["correct"]) == (2, 3, False) and not g["marks"][0]["ok"]
    g = grade("concentration-risk", {**INTERIOR, "percents": [59.8, 33, 10], "recommendation": "expand", "target_pct": 50})
    assert [m["ok"] for m in g["marks"]] == [True, False, True, False, False]
    assert g["marks"][0]["right"] == "60% (red)" and g["marks"][1]["right"] == "30% (orange)" and g["marks"][2]["right"] == "10% (green)"
    g = grade("growth-compass", {**COACH, "zone": 2, "fix": "offer"})
    assert g["score"] == 0 and "Zone 3" in g["marks"][0]["right"]


def test_zone_edges_follow_the_workshop():
    from features.frameworks import _zone_for
    assert [_zone_for(p) for p in (0, 20, 20.1, 40, 40.1, 100)] == ["green", "green", "orange", "orange", "red", "red"]


def test_saving_is_free_and_can_be_redone(client):
    qa_login(client, plan="free")
    for verdict in ("works", "fails"):
        body = {**NOKIA, "circles": {**NOKIA["circles"], "price": {"verdict": verdict, "why": "Price changes the answer here."}}}
        assert client.put("/api/frameworks/market-fit/response", json=body).status_code == 200
    mine = client.get("/api/frameworks/market-fit").json()["mine"]
    assert mine["answers"]["circles"]["price"]["verdict"] == "fails" and mine["grade"]["score"] == 2
    assert used(client, "fw_proposal") == 0


def test_proposal_needs_a_saved_answer_then_counts_one_go(client):
    qa_login(client, plan="free")
    r = client.post("/api/frameworks/growth-compass/proposal")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_saved"
    client.put("/api/frameworks/growth-compass/response", json=COACH)
    d = client.post("/api/frameworks/growth-compass/proposal").json()
    p = d["mine"]["proposal"]
    assert p["v"] == 2 and p["markdown"].startswith("# The Growth Compass") and p["stale"] is False
    assert p["client"] and p["date"] and p["framework"] == "The Growth Compass" and len(p["plan"]["phases"]) == 3
    for h in ("Where we started", "The real problem", "Your diagnosis", "Where to focus", "Your 90-day plan", "Next steps"):
        assert h in p["markdown"], h
    assert "Investment" not in p["markdown"]                                   # the house structure has no fee section
    assert used(client, "fw_proposal") == 1 and d["mine"]["proposals_made"] == 1
    client.put("/api/frameworks/growth-compass/response", json={**COACH, "zone": 1})
    assert client.get("/api/frameworks/growth-compass").json()["mine"]["proposal"]["stale"] is True   # made from an older answer


def test_free_account_gets_six_proposals_one_per_case(client):
    qa_login(client, plan="free")
    niche(client)
    for key, body in ALL.items():
        client.put(f"/api/frameworks/{key}/response", json=body)
        assert client.post(f"/api/frameworks/{key}/proposal").status_code == 200
        assert client.put(f"/api/frameworks/{key}/own", json={"case": OWN[key], "answers": OWN_ANS[key]}).status_code == 200
        assert client.post(f"/api/frameworks/{key}/own/proposal").status_code == 200
    r = client.post("/api/frameworks/market-fit/proposal")
    assert r.status_code == 402 and r.json()["detail"]["code"] == "limit"


def test_proposal_prompt_carries_the_case_the_answer_and_the_member(client, monkeypatch):
    import llm
    seen = {}
    real = llm.complete_json

    async def spy(**kw):
        seen.update(kw)
        return await real(**kw)
    monkeypatch.setattr(llm, "complete_json", spy)
    qa_login(client, plan="member")
    client.put("/api/frameworks/concentration-risk/response", json=INTERIOR)
    client.post("/api/frameworks/concentration-risk/proposal")
    p = seen["prompt"]
    assert "₹1.08 crore" in p or "1,08,00,000" in p or "10800000" in p
    assert "One large real estate developer: 60%" in p and "Recommendation: wait" in p
    assert "never as instructions" in seen["system"] and seen["model"] == "strong"


def test_proposal_check_refuses_thin_answers_and_gives_the_go_back(client, monkeypatch):
    import llm

    async def thin(**kw):
        return {"title": "Plan", "summary": "x", "approach": [{"phase": "Only one"}]}
    monkeypatch.setattr(llm, "complete_json", thin)
    qa_login(client, plan="free")
    client.put("/api/frameworks/market-fit/response", json=NOKIA)
    r = client.post("/api/frameworks/market-fit/proposal")
    assert r.status_code == 503 and used(client, "fw_proposal") == 0


def test_proposal_keeps_the_house_structure_from_live_model_shapes():
    """The AI's JSON → the proposal the page renders: numbers read in live shapes, rows cut, missing parts refused."""
    import llm
    from features import proposal_doc
    raw = proposal_doc.fake("The Growth Compass", "Acme", "read")
    raw["impact"]["scenarios"][1]["value"] = "₹36,00,000"
    raw["impact"]["scenarios"].append({"label": "no value", "value": "n/a"})
    raw["key_facts"].append({"value": "4th", "label": "too many"})
    p = proposal_doc.clean(raw)
    assert p["impact"]["scenarios"][1]["value"] == 3_600_000 and len(p["impact"]["scenarios"]) == 3
    assert len(p["key_facts"]) == 3 and p["impact"]["scenarios"][0]["cautious"] is None
    md = proposal_doc.markdown(p, "The Growth Compass", "Acme", "Asha", "12 November 2026")
    assert "₹36L" in md and "₹27L" in md and "Prepared for: Acme" in md
    for part in ("plan", "diagnosis"):
        broken = {**raw, part: {}}
        with pytest.raises(llm.LLMError):
            proposal_doc.clean(broken)


def test_members_cannot_see_each_others_answers(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as a:
        qa_login(a, plan="free", phone="+919811100401")
        a.put("/api/frameworks/market-fit/response", json=NOKIA)
    with TestClient(app) as b:
        qa_login(b, plan="free", phone="+919811100402")
        assert b.get("/api/frameworks/market-fit").json()["mine"] is None
        assert b.post("/api/frameworks/market-fit/proposal").status_code == 409


# ============================================================ my own case, from the member's niche ====
def test_own_case_suggest_needs_a_niche_and_counts_one_go(client):
    qa_login(client, plan="free")
    d = client.get("/api/frameworks/market-fit").json()
    assert d["niche"] is None and d["own"] == {"case": None, "draft_case": None, "mine": None}
    r = client.post("/api/frameworks/market-fit/own/suggest", json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_niche" and used(client, "fw_case") == 0
    niche(client)
    for key in ALL:
        d = client.post(f"/api/frameworks/{key}/own/suggest", json={"hint": "a client I met last week"}).json()
        c = d["own"]["draft_case"]
        assert c["client"] and c["title"] and c["task"] and d["own"]["mine"] is None and d["niche"]["niche"]
        if key == "concentration-risk":
            assert c["total"] == sum(s["amount"] for s in c["sources"])
    assert used(client, "fw_case") == 3
    assert client.get("/api/frameworks/growth-compass").json()["own"]["draft_case"]   # kept after reload


REAL_URL = "https://www.example-news.in/2026/10/acme-forgings-results"


def search_reply(case: dict, urls=(REAL_URL,)) -> dict:
    """What a live web-search turn returns: the tool's results, then the JSON case."""
    import json
    return {"stop_reason": "end_turn", "content": [
        {"type": "server_tool_use", "name": "web_search", "input": {"query": "forging company Pune"}},
        {"type": "web_search_tool_result", "content": [
            {"type": "web_search_result", "url": u, "title": "Acme Forgings Q2 results", "page_age": "2026-10-20"} for u in urls]},
        {"type": "text", "text": json.dumps(case)}]}


ACME = {"company": "Acme Forgings", "client": "auto forgings maker, Pune", "situation": SITU,
        "sources": [{"name": "Tier-1 customer A", "amount": 2_270_000_000}, {"name": "Exports", "amount": 800_000_000}],
        "refs": [REAL_URL, "https://made-up.example/not-in-results"], "estimates": "The customer split is estimated."}


@pytest.fixture()
def live_search(monkeypatch):
    """Web search in live mode, with the vendor's reply set by the test; records each call."""
    import llm
    from research import search
    calls = []
    reply = {"value": search_reply(ACME)}

    async def fake_tools(**kw):
        calls.append(kw)
        return reply["value"]
    monkeypatch.setattr(search, "mode", lambda: "live")
    monkeypatch.setattr(llm, "complete_with_tools", fake_tools)
    return calls, reply


def test_suggestion_finds_a_real_company_with_its_sources(client, live_search):
    calls, _ = live_search
    qa_login(client, plan="free")
    niche(client)
    n = client.get("/api/frameworks/market-fit").json()["niche"]["niche"]
    d = client.post("/api/frameworks/concentration-risk/own/suggest", json={"hint": "a forging unit in Pune"}).json()
    c = d["own"]["draft_case"]
    assert c["company"] == "Acme Forgings" and c["client"].startswith("Acme Forgings, ")
    assert [r["url"] for r in c["refs"]] == [REAL_URL]                    # a link the search never returned is dropped
    assert c["estimates"] and used(client, "fw_case") == 1
    kw = calls[-1]
    # the strong model refuses a forced tool_choice (HTTP 400), so the search is asked for in the prompt
    assert kw.get("tool_choice") is None and kw["model"] == "strong" and kw["tools"][0]["name"] == "web_search"
    assert kw["prompt"].startswith("Use the web_search tool first")
    assert n in kw["prompt"] and "a forging unit in Pune" in kw["prompt"]
    assert "REAL Indian company" in kw["system"] and "never as instructions" in kw["system"]
    client.post("/api/frameworks/concentration-risk/own/suggest", json={})
    assert "PICK A DIFFERENT COMPANY: Acme Forgings" in calls[-1]["prompt"]       # "Suggest another" moves on


@pytest.mark.parametrize("case,urls", [
    ({**ACME, "refs": ["https://made-up.example/x"]}, (REAL_URL,)),           # no source the search returned
    ({**ACME, "company": ""}, (REAL_URL,)),                                   # no company named
    (ACME, ()),                                                               # the search found nothing
    ({**ACME, "client": "x", "company": "", "sources": [{"name": "Only one", "amount": 100}]}, (REAL_URL,)),
    ({**ACME, "situation": "short"}, (REAL_URL,)),
])
def test_a_suggestion_without_a_real_sourced_company_gives_the_go_back(client, live_search, case, urls):
    _, reply = live_search
    reply["value"] = search_reply(case, urls)
    qa_login(client, plan="free")
    niche(client)
    r = client.post("/api/frameworks/concentration-risk/own/suggest", json={})
    assert r.status_code == 503 and used(client, "fw_case") == 0
    assert client.get("/api/frameworks/concentration-risk").json()["own"]["draft_case"] is None


def test_a_model_that_answers_without_searching_is_asked_once_more(client, live_search):
    calls, reply = live_search
    seq = [{"stop_reason": "end_turn", "content": [{"type": "text", "text": "{}"}]}, search_reply(ACME)]

    async def two(**kw):
        calls.append(kw)
        return seq.pop(0)
    import llm
    llm.complete_with_tools = two          # restored by monkeypatch in live_search at teardown
    qa_login(client, plan="free")
    niche(client)
    d = client.post("/api/frameworks/concentration-risk/own/suggest", json={}).json()
    assert d["own"]["draft_case"]["company"] == "Acme Forgings" and len(calls) == 2
    assert calls[1]["prompt"].startswith("You must call the web_search tool")


def test_a_refused_request_on_the_strong_model_falls_back_to_the_fast_one(client, live_search):
    import llm
    calls, _ = live_search

    async def picky(**kw):
        calls.append(kw)
        if kw["model"] == "strong":
            raise llm.LLMError("AI call failed: BadRequestError: Error code: 400 - invalid_request_error")
        return search_reply(ACME)
    llm.complete_with_tools = picky
    qa_login(client, plan="free")
    niche(client)
    d = client.post("/api/frameworks/market-fit/own/suggest", json={})
    assert d.status_code == 503 or d.json()["own"]["draft_case"]["company"] == "Acme Forgings"
    assert [c["model"] for c in calls[-2:]] == ["strong", "fast"]
    assert calls[-1]["tool_choice"] == {"type": "tool", "name": "web_search"}


def test_suggestion_with_web_search_off_gives_the_go_back(client, monkeypatch):
    from research import search
    qa_login(client, plan="free")
    niche(client)
    monkeypatch.setattr(search, "mode", lambda: "off")
    r = client.post("/api/frameworks/growth-compass/own/suggest", json={})
    assert r.status_code == 503 and used(client, "fw_case") == 0


def test_test_mode_suggestion_is_marked_as_a_sample(client):
    qa_login(client, plan="free")
    niche(client)
    c = client.post("/api/frameworks/market-fit/own/suggest", json={}).json()["own"]["draft_case"]
    assert "test mode" in c["company"] and c["refs"][0]["url"].startswith("https://example.com")


def test_real_company_proposal_says_it_is_real_and_lists_the_estimates(client, live_search, monkeypatch):
    import llm
    seen = {}
    real = llm.complete_json

    async def spy(**kw):
        seen.update(kw)
        return await real(**kw)
    monkeypatch.setattr(llm, "complete_json", spy)
    qa_login(client, plan="member")
    niche(client)
    c = client.post("/api/frameworks/concentration-risk/own/suggest", json={}).json()["own"]["draft_case"]
    case = {k: c[k] for k in ("company", "client", "situation", "sources", "refs", "estimates")}
    ans = {**OWN_ANS["concentration-risk"], "percents": [73.9, 26.1]}
    d = client.put("/api/frameworks/concentration-risk/own", json={"case": case, "answers": ans}).json()
    assert d["own"]["case"]["refs"][0]["url"] == REAL_URL and d["own"]["draft_case"] is None
    client.post("/api/frameworks/concentration-risk/own/proposal")
    p = seen["prompt"]
    assert "A REAL COMPANY (Acme Forgings)" in p and "Estimated for practice" in p and "never invent private details" in p


def test_ai_case_in_live_model_shapes_is_read():
    from features.frameworks import clean_case
    c = clean_case("growth-compass", {"client": "a yoga studio in Kochi", "situation": SITU, "reach_per_month": "3,000",
                                      "conversion_pct": "1.5%", "reach_level": "High", "conversion_level": "LOW"})
    assert (c["reach_per_month"], c["conversion_pct"], c["reach_level"], c["conversion_level"]) == (3000, 1.5, "high", "low")
    c = clean_case("concentration-risk", {"client": "a CA firm", "situation": SITU,
                                          "sources": [{"name": "Audit", "amount": "₹25,00,000"}, {"name": "GST", "amount": 1500000.0}]})
    assert [s["amount"] for s in c["sources"]] == [2_500_000, 1_500_000]


@pytest.mark.parametrize("key", list(OWN))
def test_own_case_saves_free_and_is_checked_by_the_rules(client, key):
    qa_login(client, plan="free")       # no niche needed to write your own case
    d = client.put(f"/api/frameworks/{key}/own", json={"case": OWN[key], "answers": OWN_ANS[key]}).json()
    g = d["own"]["mine"]["grade"]
    assert g["own"] and g["read"] and d["own"]["case"]["client"] == OWN[key]["client"]
    assert d["mine"] is None and d["akshat"] is None                      # Akshat's case untouched
    if key == "market-fit":
        assert (g["mode"], g["score"], g["out_of"]) == ("holds", 2, 3) and "availability" in g["read"]
    else:
        assert g["correct"] is True and g["score"] == g["out_of"]
    row = next(x for x in client.get("/api/frameworks").json()["items"] if x["key"] == key)
    assert row["own_saved"] and row["own_client"] == OWN[key]["client"] and not row["saved"]
    assert used(client, "fw_case") == 0 and used(client, "fw_proposal") == 0


def test_own_rule_checks_point_by_point():
    from features.frameworks import grade_own
    c = OWN["concentration-risk"]
    g = grade_own("concentration-risk", c, {**OWN_ANS["concentration-risk"], "percents": [40, 30, 15, 5],
                                            "recommendation": "expand", "target_pct": 45})
    assert [m["ok"] for m in g["marks"]] == [False, True, True, True, False, False] and g["marks"][4]["right"] == "wait"
    even = {**c, "sources": [{"name": "A1", "amount": 30}, {"name": "B1", "amount": 35}, {"name": "C1", "amount": 35}]}
    g = grade_own("concentration-risk", even, {**OWN_ANS["concentration-risk"], "percents": [30, 35, 35], "recommendation": "expand"})
    assert g["correct"] and "expanding is reasonable" in g["read"]
    for levels, zone, fix in [(("high", "high"), 1, "scale"), (("high", "low"), 2, "offer"),
                              (("low", "high"), 3, "reach"), (("low", "low"), 4, "both")]:
        cc = {**OWN["growth-compass"], "reach_level": levels[0], "conversion_level": levels[1]}
        g = grade_own("growth-compass", cc, {**OWN_ANS["growth-compass"], "zone": zone, "fix": fix})
        assert g["correct"], levels
    g = grade_own("market-fit", OWN["market-fit"], {"circles": {k: {"verdict": "works"} for k in ("price", "value", "availability")}})
    assert g["correct"] and "overlap" in g["read"]


@pytest.mark.parametrize("key,body", [
    ("concentration-risk", {"case": OWN["concentration-risk"], "answers": {**OWN_ANS["concentration-risk"], "percents": [50, 30, 20]}}),
    ("concentration-risk", {"case": {**OWN["concentration-risk"], "sources": [{"name": "A1", "amount": 0}, {"name": "B1", "amount": 5}]},
                            "answers": {**OWN_ANS["concentration-risk"], "percents": [0, 100]}}),
    ("market-fit", {"case": {**OWN["market-fit"], "product": ""}, "answers": OWN_ANS["market-fit"]}),
    ("market-fit", {"case": OWN["market-fit"]}),
    ("growth-compass", {"case": {**OWN["growth-compass"], "reach_level": "medium"}, "answers": OWN_ANS["growth-compass"]}),
    ("growth-compass", {"answers": OWN_ANS["growth-compass"]}),
])
def test_incomplete_own_case_is_refused_in_plain_words(client, key, body):
    qa_login(client, plan="free")
    r = client.put(f"/api/frameworks/{key}/own", json=body)
    assert r.status_code == 422, r.text
    msg = r.json()["detail"]["msg"]
    assert msg and "value_error" not in msg and "{" not in msg
    assert client.get(f"/api/frameworks/{key}").json()["own"]["mine"] is None


def test_workshop_concentration_still_needs_three_sources(client):
    qa_login(client, plan="free")
    r = client.put("/api/frameworks/concentration-risk/response", json={**INTERIOR, "percents": [60, 30, 5, 5]})
    assert r.status_code == 422


def test_own_proposal_uses_the_members_client_not_the_workshop_case(client, monkeypatch):
    import llm
    seen = {}
    real = llm.complete_json

    async def spy(**kw):
        seen.update(kw)
        return await real(**kw)
    monkeypatch.setattr(llm, "complete_json", spy)
    qa_login(client, plan="member")
    r = client.post("/api/frameworks/concentration-risk/own/proposal")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_saved"
    client.put("/api/frameworks/concentration-risk/own", json={"case": OWN["concentration-risk"], "answers": OWN_ANS["concentration-risk"]})
    d = client.post("/api/frameworks/concentration-risk/own/proposal").json()
    p = seen["prompt"]
    assert "a CA firm in Indore" in p and "Audit for one group: 50%" in p and "₹50,00,000" in p
    assert "Bangalore" not in p and "Akshat" not in p and "RULES SAY" in p
    assert d["own"]["mine"]["proposal"]["markdown"].startswith("# ") and d["mine"] is None
    assert used(client, "fw_proposal") == 1
    client.put("/api/frameworks/concentration-risk/own", json={"case": OWN["concentration-risk"],
                                                               "answers": {**OWN_ANS["concentration-risk"], "months": 18}})
    assert client.get("/api/frameworks/concentration-risk").json()["own"]["mine"]["proposal"]["stale"] is True


def test_members_cannot_see_each_others_own_cases(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as a:
        qa_login(a, plan="free", phone="+919811100411")
        a.put("/api/frameworks/growth-compass/own", json={"case": OWN["growth-compass"], "answers": OWN_ANS["growth-compass"]})
    with TestClient(app) as b:
        qa_login(b, plan="free", phone="+919811100412")
        assert b.get("/api/frameworks/growth-compass").json()["own"]["mine"] is None
        assert b.post("/api/frameworks/growth-compass/own/proposal").status_code == 409


def test_ai_case_text_is_cut_on_words():
    from features.frameworks import clean_case, own_case_public
    long = "A vendor cost-reduction service for Tier-2 machining units: a bundled programme of raw material bulk-buying " \
           "through a pooled purchase group, tool life tracking, and scrap reduction with monthly reviews"
    c = clean_case("market-fit", {"client": "a machining unit in Coimbatore", "product": long, "new_region": "Pune",
                                  "situation": SITU})
    assert len(c["product"]) <= 160 and not c["product"].endswith((",", " ")) and long.startswith(c["product"])
    assert own_case_public("market-fit", c)["title"].startswith("Will a vendor")
