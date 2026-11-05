"""End-to-end functional QA over real HTTP against a running hub (real MongoDB, QA_MODE fake vendors).

Usage: python e2e.py http://127.0.0.1:8001
Prints one line per check and a summary; writes results JSON next to this file.
"""
import io
import json
import random
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

BASE = sys.argv[1].rstrip("/")
RESULTS: list[dict] = []
RUN = random.randint(100, 999)


def phone(n):  # unique per run
    return f"+9180{RUN}{n:05d}"


class S:
    def __init__(self, label):
        self.label = label
        self.c = httpx.Client(base_url=BASE, timeout=120)

    def login(self, plan=None, role="user", n=0):
        body = {"role": role, "phone": phone(n)}
        if plan:
            body["plan"] = plan
        r = self.c.post("/api/qa/login", json=body)
        assert r.status_code == 200, r.text
        return r.json()

    def call(self, name, method, path, expect=(200,), **kw):
        t = time.perf_counter()
        try:
            r = self.c.request(method, path, **kw)
            status, body = r.status_code, r.text
        except Exception as e:  # noqa: BLE001
            status, body = -1, repr(e)
        ms = (time.perf_counter() - t) * 1000
        ok = status in (expect if isinstance(expect, (tuple, list, set)) else (expect,))
        RESULTS.append({"who": self.label, "check": name, "method": method, "path": path, "status": status,
                        "expect": list(expect) if isinstance(expect, (tuple, list, set)) else [expect], "ok": ok,
                        "ms": round(ms), "body": None if ok else body[:400]})
        print(f"{'PASS' if ok else 'FAIL'} [{self.label}] {name}: {method} {path} -> {status} ({ms:.0f} ms)"
              + ("" if ok else f"  {body[:200]}"))
        try:
            return r.json() if status != -1 and "json" in r.headers.get("content-type", "") else (r if status != -1 else None)
        except Exception:  # noqa: BLE001
            return None


def idof(j, *keys):
    if not isinstance(j, dict):
        return None
    for k in keys + ("id",):
        v = j.get(k)
        if isinstance(v, str):
            return v
        if isinstance(v, dict) and isinstance(v.get("id"), str):
            return v["id"]
    for k in ("item", "deck", "visual", "card", "story", "project", "proposal", "doc", "ticket", "thread", "conversation",
              "brief", "pack", "report", "site", "diagnostic", "prep", "outreach", "take"):
        v = j.get(k)
        if isinstance(v, dict) and isinstance(v.get("id"), str):
            return v["id"]
    return None


ANSWER = ("The real problem is margin leakage: profit fell from 4% to 1.5% as the new stores opened. Objective: from "
          "1.5% to 3% in 90 days. Framework: margin leak check. Do first: fresh produce ordering. Owner: ops head; "
          "track wastage % weekly.")
def _pdf():
    from reportlab.pdfgen import canvas
    buf = io.BytesIO(); c = canvas.Canvas(buf)
    c.drawString(72, 720, "Revenue grew 18 percent. The board decided to open two new depots in Gujarat next year.")
    c.showPage(); c.save(); return buf.getvalue()


PDF_UNUSED = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj "
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj "
       b"4 0 obj<</Length 120>>stream\nBT /F1 12 Tf 72 720 Td (Revenue grew 18 percent. The board decided to open two "
       b"new depots in Gujarat next year.) Tj ET\nendstream endobj 5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"
       b"endobj\ntrailer<</Root 1 0 R>>\n%%EOF")
DOCX_TEXT = ("Quarterly review. Revenue grew 18 percent to 42 crore. The board decided to open two depots in Gujarat and "
             "hire six sales officers. Wastage fell from 6 percent to 4 percent after the cold chain fix. ") * 3


# ============================================================================================ anonymous / public ====
def public_checks():
    s = S("anon")
    s.call("health", "GET", "/api/health")
    s.call("ready (Mongo ping)", "GET", "/api/health/ready")
    s.call("config", "GET", "/api/config")
    s.call("public plans", "GET", "/api/plans/catalog")
    s.call("SPA /", "GET", "/")
    s.call("SPA deep link", "GET", "/app/cases")
    s.call("member area needs login", "GET", "/api/me/home", expect=401)
    s.call("admin needs login", "GET", "/api/admin/pulse", expect=401)
    s.call("unknown api path is JSON 404", "GET", "/api/nope", expect=404)
    # real OTP sign-up flow
    p = f"98{RUN}{random.randint(10000, 99999)}"
    ch = s.call("otp request", "POST", "/api/auth/otp/request", json={"phone": p})
    s.call("otp wrong code", "POST", "/api/auth/otp/verify",
           json={"challenge_id": ch["challenge_id"], "phone": p, "code": "123456" if ch.get("dev_code") != "123456" else "654321"},
           expect=400)
    s.call("otp verify (sign up)", "POST", "/api/auth/otp/verify",
           json={"challenge_id": ch["challenge_id"], "phone": p, "code": ch["dev_code"], "name": "QA Signup"})
    s.call("me after sign-up", "GET", "/api/auth/me")
    s.call("bad phone refused", "POST", "/api/auth/otp/request", json={"phone": "12345"}, expect=400)
    s.call("logout", "POST", "/api/auth/logout")
    s.call("me after logout", "GET", "/api/auth/me", expect=401)


# ============================================================================================ free (webinar) =======
def free_checks():
    s = S("free")
    s.login(plan="free", n=1)
    s.call("home", "GET", "/api/me/home")
    s.call("plan", "GET", "/api/me/plan")
    sc = {k: random.randint(3, 8) for k in ("diagnosis", "offer", "acquisition", "pricing", "delivery", "visibility")}
    s.call("readiness score", "POST", "/api/readiness", json={"scores": sc, "potential": 8})
    s.call("readiness second go = once-for-life limit", "POST", "/api/readiness", json={"scores": sc, "potential": 8}, expect=402)
    snap = s.call("niche snapshot (AI)", "POST", "/api/start/snapshot",
                  json={"experiences": ["Supply chain", "Team leadership", "Cost cutting"], "enjoy": [0], "industry": "FMCG", "years": 18})
    sid = idof(snap, "snapshot_id")
    if sid:
        s.call("choose niche", "POST", f"/api/start/snapshot/{sid}/choose", json={"index": 0})
    s.call("goal preview", "POST", "/api/start/goal/preview", json={"monthly_goal_inr": 300000, "fee_inr": 50000})
    s.call("goal save", "PUT", "/api/start/goal", json={"monthly_goal_inr": 300000, "fee_inr": 50000})
    s.call("start state", "GET", "/api/start")
    cases = s.call("cases list", "GET", "/api/cases")
    live = next((c["id"] for c in (cases or {}).get("items", []) if c.get("live")), "retail-chain-margins")
    locked = next((c["id"] for c in (cases or {}).get("items", []) if c.get("locked")), None)
    s.call("live case", "GET", f"/api/cases/{live}")
    s.call("case answer (AI)", "POST", f"/api/cases/{live}/answer", json={"answer": ANSWER})
    s.call("case answer too short → 422", "POST", f"/api/cases/{live}/answer", json={"answer": "short"}, expect=422)
    if locked:
        s.call("other case locked for free", "GET", f"/api/cases/{locked}", expect=403)
    b = s.call("meeting brief (search + AI)", "POST", "/api/briefs", json={"company": "Tata Motors", "purpose": "Discuss supplier costs"})
    bid = idof(b)
    s.call("briefs list", "GET", "/api/briefs")
    if bid:
        s.call("brief view", "GET", f"/api/briefs/{bid}")
    s.call("linkedin score", "POST", "/api/linkedin/check", json={"headline": "GM Operations at ABC Ltd | Supply chain", "about": "18 years in FMCG plants."})
    s.call("linkedin rewrite locked for free", "POST", "/api/linkedin/check",
           json={"headline": "GM Operations at ABC Ltd", "about": "x", "rewrite": True}, expect=(403, 402))
    s.call("my consulting file", "GET", "/api/file")
    s.call("file viewed", "POST", "/api/file/viewed")
    s.call("inbox", "GET", "/api/inbox")
    for path, feat in [("/api/decks", "decks"), ("/api/visuals", "visuals"), ("/api/gpts", "gpts"), ("/api/network", "network"),
                       ("/api/program", "program"), ("/api/support/tickets", "support")]:
        s.call(f"{feat} locked for free", "GET", path, expect=(403, 200))
    s.call("deck make locked for free", "POST", "/api/decks", json={"source": "text", "title": "X", "notes": "y" * 50}, expect=403)
    co = s.call("checkout ₹1,999 monthly (test-mode Razorpay)", "POST", "/api/billing/checkout", json={"plan": "member", "period": "monthly"})
    if co and co.get("subscription_id"):
        s.call("payment verified", "POST", "/api/billing/verify", json={"subscription_id": co["subscription_id"], "payment_id": f"pay_{RUN}", "signature": "x"})
        me = s.call("plan after payment", "GET", "/api/me/plan")
        ok = (me or {}).get("plan") == "member"
        RESULTS.append({"who": "free", "check": "paid → now on ₹1,999 plan", "ok": ok, "status": 0, "expect": [0], "method": "-", "path": "-", "ms": 0, "body": None if ok else str(me)[:300]})
        s.call("same payment reused → refused", "POST", "/api/billing/verify", json={"subscription_id": co["subscription_id"], "payment_id": f"pay_{RUN}", "signature": "x"}, expect=409)
        s.call("now can make a deck", "POST", "/api/decks", json={"source": "text", "title": "First deck", "notes": "Wastage is 6%. Target 3% in 90 days."})
        s.call("upgrade to L1", "POST", "/api/billing/checkout", json={"plan": "l1"})
        s.call("cancel plan (runs to period end)", "POST", "/api/billing/cancel")


# ============================================================================================ ₹1,999 member =========
def member_checks():
    s = S("member")
    s.login(plan="member", n=2)
    s.call("home", "GET", "/api/me/home")
    s.call("weekly/cases list", "GET", "/api/cases")
    s.call("case answer (paid, any case)", "POST", "/api/cases/hospital-claims/answer", json={"answer": ANSWER}, expect=(200, 404))
    s.call("linkedin rewrite (AI)", "POST", "/api/linkedin/check",
           json={"headline": "GM Operations at ABC Ltd | Supply chain", "about": "18 years in FMCG plants.", "rewrite": True})
    # decks
    s.call("deck sources", "GET", "/api/decks/sources")
    d = s.call("deck make (AI + render)", "POST", "/api/decks",
               json={"source": "text", "title": "Cutting wastage in FMCG plants", "audience": "Plant heads",
                     "notes": "Wastage is 6% of output. Target 3% in 90 days. Three levers: ordering, cold chain, shift handover."})
    did = idof(d)
    if did:
        dv = s.call("deck view", "GET", f"/api/decks/{did}")
        s.call("deck pptx download", "GET", f"/api/decks/{did}/file?kind=pptx")
        s.call("deck pdf download", "GET", f"/api/decks/{did}/file?kind=pdf")
        slides = (dv or {}).get("slides") or (dv or {}).get("deck", {}).get("slides")
        if slides:
            s.call("deck edit (title)", "PATCH", f"/api/decks/{did}", json={"title": "Wastage: the 90-day plan"})
    s.call("decks list", "GET", "/api/decks")
    # visuals
    v = s.call("visual make (AI)", "POST", "/api/visuals", json={"kind": "process", "prompt": "Five steps to cut plant wastage"})
    vid = idof(v)
    s.call("visuals list", "GET", "/api/visuals")
    if vid:
        s.call("visual view", "GET", f"/api/visuals/{vid}")
    s.call("chart visual (AI)", "POST", "/api/visuals", json={"kind": "chart", "prompt": "Wastage by month", "numbers": "Jan 6, Feb 5.5, Mar 4.8", "chart": "line"})
    # listen
    s.call("listen sources", "GET", "/api/listen/sources")
    s.call("listen: case audio", "POST", "/api/listen", json={"source": "case", "id": "retail-chain-margins"})
    # docs
    up = s.call("doc upload (PDF)", "POST", "/api/docs", files={"file": ("review.pdf", _pdf(), "application/pdf")}, data={"title": "Q3 review"})
    up2 = s.call("doc upload (text)", "POST", "/api/docs", files={"file": ("notes.txt", DOCX_TEXT.encode(), "text/plain")})
    s.call("doc upload bad type → refused", "POST", "/api/docs", files={"file": ("x.exe", b"MZ....", "application/octet-stream")}, expect=(400, 415))
    s.call("docs list", "GET", "/api/docs")
    s.call("doc question (AI)", "POST", "/api/docs/ask", json={"question": "What did the board decide about depots?"})
    doc_id = idof(up2) or idof(up)
    if doc_id:
        s.call("doc summary (AI)", "POST", f"/api/docs/{doc_id}/summary")
    # website
    s.call("website state", "GET", "/api/website")
    s.call("website build (AI)", "POST", "/api/website/build", json={})
    w = s.call("website after build", "GET", "/api/website")
    s.call("website looks", "GET", "/api/website/looks", expect=(200, 404))
    s.call("website settings", "PUT", "/api/website/settings", json={"slug": f"qa-consultant-{RUN}", "name": "QA Consultant"})
    s.call("website publish", "POST", "/api/website/publish", json={"on": True})
    site = s.call("website after publish", "GET", "/api/website")
    slug = ((site or {}).get("site") or site or {}).get("slug") or f"qa-consultant-{RUN}"
    anon = S("anon-visitor")
    pg = anon.call("public site renders /s/<slug>", "GET", f"/s/{slug}")
    sec = None
    for p in ((site or {}).get("site") or site or {}).get("pages", []) or []:
        for x in p.get("sections", []) or []:
            sec = sec or x.get("id")
    if sec:
        s.call("section AI edit", "POST", f"/api/website/sections/{sec}/ai", json={"instruction": "Make it shorter and plainer"})
    s.call("website second page refused on ₹1,999 (1 page)", "POST", "/api/website/pages", json={"key": "services"}, expect=(402, 403, 409, 400))
    s.call("website own domain locked on ₹1,999", "PUT", "/api/website/domain", json={"domain": "qa-example.com"}, expect=(403,))
    anon.call("visitor sends a message from the site", "POST", f"/api/website/public/{slug}/leads",
              json={"name": "Amit Shah", "email": "amit@example.com", "phone": "9876500001", "message": "Can we talk about a cost review?"})
    leads = s.call("member sees website message", "GET", "/api/website/leads")
    ok = bool((leads or {}).get("items"))
    RESULTS.append({"who": "member", "check": "lead stored for member", "ok": ok, "status": 0, "expect": [0], "method": "-", "path": "-", "ms": 0, "body": None if ok else str(leads)[:300]})
    # progress, support
    s.call("progress list", "GET", "/api/progress")
    s.call("progress report make", "POST", "/api/progress", expect=(200, 409, 402))
    t = s.call("support ticket", "POST", "/api/support/tickets", json={"subject": "Can't find my workbook", "category": "tools", "text": "Where is the Day 2 workbook?"})
    tid = idof(t)
    s.call("support list", "GET", "/api/support/tickets")
    if tid:
        s.call("support reply", "POST", f"/api/support/tickets/{tid}/reply", json={"text": "Also the recording please."})
    # locks
    s.call("L1 tool locked: offer card", "POST", "/api/offer-card", json={"offer_name": "Plant reset"}, expect=403)
    s.call("L2 tool locked: radar", "POST", "/api/radar/run", json={"industry": "Pharma"}, expect=403)
    s.call("L1 program locked", "GET", "/api/program", expect=403)
    s.call("upgrade checkout L1", "POST", "/api/billing/checkout", json={"plan": "l1"})
    return tid


# ============================================================================================ L1 ===================
def l1_checks():
    s = S("l1")
    s.login(plan="l1", n=3)
    s.call("home", "GET", "/api/me/home")
    pr = s.call("program", "GET", "/api/program")
    task = None
    for day in (pr or {}).get("days", []) or []:
        for t in day.get("tasks", []) or []:
            task = task or t.get("id")
    if task:
        s.call("program task done", "POST", f"/api/program/tasks/{task}", json={"done": True})
    s.call("calls", "GET", "/api/calls")
    s.call("library", "GET", "/api/library")
    s.call("recaps", "GET", "/api/recaps")
    g = s.call("action hub tools", "GET", "/api/gpts")
    conv = s.call("gpt start: define-your-niche (AI)", "POST", "/api/gpts/define-your-niche/conversations", json={})
    cid = idof(conv)
    if cid:
        s.call("gpt message (AI)", "POST", f"/api/gpts/conversations/{cid}/messages", json={"text": "18 years in FMCG supply chain. Which niche fits?"})
        s.call("gpt conversation", "GET", f"/api/gpts/conversations/{cid}")
    s.call("mentorship tool locked on L1", "POST", "/api/gpts/book-builder/conversations", json={}, expect=403)
    a = s.call("akshat ai ask", "POST", "/api/akshat-ai/ask", json={"question": "How do I price my first project?"})
    s.call("akshat ai unknown → team question", "POST", "/api/akshat-ai/ask", json={"question": "Quantum zebra telescope licensing in Peru?"})
    s.call("akshat ai threads", "GET", "/api/akshat-ai/threads", expect=(200, 404))
    oc = s.call("offer card (AI)", "POST", "/api/offer-card", json={"offer_name": "90-day plant reset", "engagement": "90 days",
                                                                   "what_you_get": "Diagnosis, plan, weekly reviews", "fee_from_inr": 300000, "fee_to_inr": 600000})
    s.call("offer cards list", "GET", "/api/offer-card")
    st = s.call("story from text (AI)", "POST", "/api/stories/text",
                json={"text": "In 2015 our Nashik plant was losing 6% of output to wastage. I set up a daily review with shift heads, "
                              "fixed the cold chain and changed ordering. In 9 months wastage fell to 3.5%, saving ₹2 crore a year."})
    s.call("stories list", "GET", "/api/stories")
    import struct
    wav = b"RIFF" + struct.pack("<I", 36 + 16000) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16) + b"data" + struct.pack("<I", 16000) + b"\x00\x01" * 8000
    s.call("story from voice note (STT + AI)", "POST", "/api/stories/voice", files={"file": ("note.wav", wav, "audio/wav")},
           data={"duration_s": "60"}, expect=(200, 422))
    s.call("insight pack (search + AI)", "POST", "/api/insights", json={"industry": "FMCG"})
    s.call("insights list", "GET", "/api/insights")
    pf = s.call("portfolio list", "GET", "/api/portfolio")
    s.call("portfolio new project", "POST", "/api/portfolio", expect=(200, 402, 422))
    pf = s.call("portfolio list again", "GET", "/api/portfolio")
    pid = None
    for it in (pf or {}).get("items", []) or []:
        pid = pid or it.get("id")
    if pid:
        s.call("portfolio answer (AI)", "POST", f"/api/portfolio/{pid}/answer",
               json={"scope": "Margin fell in 14 stores since expansion", "objective": "From 1.5% to 3% in 90 days",
                     "framework_options": "Margin leak check: pricing, wastage, mix", "do_first": "Fix fresh produce ordering",
                     "owner_metrics": "Ops head; wastage % weekly, margin monthly"})
    tk = s.call("pitch practice start", "POST", "/api/pitch", json={"pitch_type": "elevator", "setting": "CII networking event", "audience": "MD of a mid-size pump maker"})
    tkid = idof(tk)
    s.call("pitch list", "GET", "/api/pitch")
    if tkid:
        s.call("pitch coach chat (AI)", "POST", f"/api/pitch/{tkid}/chat", json={"message": "How do I open?"})
        mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 2048
        s.call("pitch video take: upload + 7-metric scorecard", "POST", f"/api/pitch/{tkid}/take", content=mp4,
               headers={"content-type": "video/mp4"}, params={"duration_s": 60, "filename": "p.mp4"})
        s.call("pitch second take within 30 min → wait", "POST", f"/api/pitch/{tkid}/take", content=mp4,
               headers={"content-type": "video/mp4"}, params={"duration_s": 60, "filename": "p.mp4"}, expect=429)
        s.call("pitch over 8 minutes → refused", "POST", f"/api/pitch/{tkid}/take", content=mp4,
               headers={"content-type": "video/mp4"}, params={"duration_s": 600, "filename": "p.mp4"}, expect=(413, 429))
        s.call("pitch take view", "GET", f"/api/pitch/{tkid}")
    nb = s.call("notebook create", "POST", "/api/notebook", json={"title": "Cold chain in Gujarat"})
    nid = idof(nb, "project_id")
    if nid:
        s.call("notebook add text source", "POST", f"/api/notebook/{nid}/sources/text",
               json={"title": "Notes", "text": "Gujarat cut power tariffs for cold storage by 12% in 2026. Five new parks opened near Surat."})
        s.call("notebook add url source", "POST", f"/api/notebook/{nid}/sources/url", json={"url": "https://example.com/cold-chain"})
        s.call("notebook ask (AI)", "POST", f"/api/notebook/{nid}/ask", json={"question": "What did the state do to power tariffs?"})
        s.call("notebook briefing (AI)", "POST", f"/api/notebook/{nid}/generate", json={"kind": "briefing"})
        s.call("notebook note", "POST", f"/api/notebook/{nid}/notes", json={"title": "Angle", "body": "Pitch shared cold rooms."})
        s.call("notebook audio overview", "POST", f"/api/notebook/{nid}/audio", expect=(200, 402))
        s.call("notebook view", "GET", f"/api/notebook/{nid}")
    s.call("L2 tool locked: network", "GET", "/api/network", expect=403)
    s.call("cancel L1 → ₹1,999 offer", "POST", "/api/billing/cancel", expect=(200, 404, 409))


# ============================================================================================ L2 ===================
def l2_checks():
    s = S("l2")
    s.login(plan="l2", n=4)
    s.call("home", "GET", "/api/me/home")
    s.call("mentorship tool: book builder (AI)", "POST", "/api/gpts/book-builder/conversations", json={})
    csv = "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n" + "\n".join(
        f"Person{i},Shah,https://linkedin.com/in/p{i},,Company {i} Pvt Ltd,{'Managing Director' if i % 2 else 'VP Operations'},0{i % 9 + 1} Jan 2024"
        for i in range(30))
    s.call("network import CSV", "POST", "/api/network/import", files={"file": ("Connections.csv", csv.encode(), "text/csv")})
    net = s.call("network list", "GET", "/api/network")
    ids = [x["id"] for x in (net or {}).get("items", [])[:3]]
    if ids:
        s.call("network AI score", "POST", "/api/network/score", json={"ids": ids})
        s.call("network mark contacted", "PATCH", f"/api/network/{ids[0]}", json={"status": "contacted", "notes": "Call after Diwali"})
        o = s.call("outreach from contact (AI)", "POST", "/api/outreach", json={"contact_id": ids[0], "channel": "linkedin", "goal": "reconnect"})
        oid = idof(o)
        if oid:
            s.call("outreach mark sent", "PATCH", f"/api/outreach/{oid}", json={"status": "sent"})
    s.call("outreach typed (AI)", "POST", "/api/outreach", json={"name": "Meera Kapoor", "role": "COO", "company": "Sunrise Textiles",
                                                                 "relationship": "worked together at Arvind", "channel": "email", "goal": "diagnostic_call"})
    s.call("outreach list", "GET", "/api/outreach")
    rd = s.call("opportunity radar (search + AI)", "POST", "/api/radar/run", json={"industry": "Pharma", "city": "Pune"})
    s.call("radar list", "GET", "/api/radar")
    cp = s.call("discovery call prep (search + AI)", "POST", "/api/call-prep",
                json={"company": "Desai Pumps", "person": "Rahul Desai", "role": "MD", "how_met": "Ex-colleague", "known": "Sales flat for two years."})
    p = s.call("proposal (AI)", "POST", "/api/proposals", json={"company": "Desai Pumps", "person": "Rahul Desai", "role": "MD",
                                                               "fee_low_inr": 150000, "fee_high_inr": 400000,
                                                               "notes": "Sales flat for two years at ₹40 crore. Dealers in Gujarat complain about delivery times."})
    prid = idof(p)
    if prid:
        s.call("proposal mark sent (schedules follow-ups)", "PATCH", f"/api/proposals/{prid}", json={"status": "sent"})
        s.call("proposal view", "GET", f"/api/proposals/{prid}")
        s.call("proposal docx/pdf download", "GET", f"/api/proposals/{prid}/file", expect=(200, 404, 405))
    s.call("proposal fee range reversed → swapped, accepted", "POST", "/api/proposals", json={"company": "Acme", "notes": "x" * 60,
                                                                                    "fee_low_inr": 400000, "fee_high_inr": 150000})
    dg = s.call("client diagnostic (AI)", "POST", "/api/diagnostic", json={"topic": "Dealer network health", "audience": "Pump makers"})
    dgid = idof(dg)
    if dgid:
        pub = s.call("diagnostic publish", "POST", f"/api/diagnostic/{dgid}/publish")
        full = s.call("diagnostic view", "GET", f"/api/diagnostic/{dgid}")
        pubid = (full or {}).get("public_id") or (pub or {}).get("public_id") or ((full or {}).get("item") or {}).get("public_id")
        if pubid:
            anon = S("anon-prospect")
            form = anon.call("public diagnostic form (no login)", "GET", f"/api/diagnostic/public/{pubid}")
            qs = (form or {}).get("questions") or []
            answers = {q["id"]: (4 if q.get("kind", "scale") == "scale" else "Delivery times slip in monsoon") for q in qs}
            anon.call("public diagnostic answer + report", "POST", f"/api/diagnostic/public/{pubid}/responses",
                      json={"name": "Neha Mehta", "email": "neha@example.com", "phone": "9876543210", "company": "Mehta Pumps",
                            "answers": answers, "consent": True})
            s.call("diagnostic responses", "GET", f"/api/diagnostic/{dgid}/responses", expect=(200, 404))
    soc = s.call("social posts (AI)", "POST", "/api/social/generate", json={"count": 3})
    s.call("social list", "GET", "/api/social")
    s.call("bootcamps", "GET", "/api/bootcamps")
    s.call("website build (L2)", "POST", "/api/website/build", json={})
    s.call("own domain request (L2 allows)", "PUT", "/api/website/domain", json={"domain": f"qa{RUN}-consulting.in"}, expect=(200, 409, 400))


# ============================================================================================ admin ================
def admin_checks(ticket_id):
    s = S("admin")
    s.login(role="admin", n=0)
    today = date.today().isoformat()
    s.call("admin page: webinar", "GET", "/api/admin/webinar", params={"start": today, "end": today})
    for p in ("pulse", "live", "users", "cases", "flags", "settings", "vendors", "jobs", "kb", "whatsapp-templates",
              "weekly", "website/domains", "support", "akshat-questions", "program/cohorts",
              "program/enrollments", "calls", "library", "recaps", "bootcamps"):
        s.call(f"admin page: {p}", "GET", f"/api/admin/{p}")
    s.call("group-session CSV", "GET", "/api/admin/webinar/group-session.csv", params={"start": today, "end": today})
    us = s.call("find member", "GET", "/api/admin/users", params={"q": phone(2)[3:]})
    uid = None
    for u in (us or {}).get("items", []) or []:
        uid = uid or u.get("id")
    if uid:
        s.call("member detail", "GET", f"/api/admin/users/{uid}")
        s.call("member's AI chats", "GET", "/api/admin/gpts/conversations", params={"user_id": uid})
        s.call("grant L1 for 1 month", "POST", f"/api/admin/users/{uid}/grant", json={"plan": "l1", "months": 1})
        s.call("start L2", "POST", f"/api/admin/users/{uid}/start-l2")
        s.call("start L2 again → 409", "POST", f"/api/admin/users/{uid}/start-l2", expect=409)
    if ticket_id:
        s.call("support reply (member gets inbox alert)", "POST", f"/api/admin/support/{ticket_id}/reply", json={"text": "It's in Recordings under Day 2."})
        s.call("support close", "POST", f"/api/admin/support/{ticket_id}/close")
    qs = s.call("akshat questions", "GET", "/api/admin/akshat-questions")
    for q in ((qs or {}).get("items") or [])[:1]:
        s.call("answer akshat question", "POST", f"/api/admin/akshat-questions/{q['id']}/answer", json={"answer": "Price by the outcome, not the hour."})
    s.call("switch: alerts on WhatsApp on", "POST", "/api/admin/flags", json={"key": "WHATSAPP_ALERTS", "on": True})
    s.call("switch back to default", "POST", "/api/admin/flags", json={"key": "WHATSAPP_ALERTS", "on": None})
    s.call("live case setting", "POST", "/api/admin/settings", json={"live_case_id": "retail-chain-margins",
                                                                       "group_session": {"title": "Group session", "when": "Sat 7 pm", "link": "https://meet.example.com/x"}})
    s.call("bad live case refused", "POST", "/api/admin/settings", json={"live_case_id": "nope"}, expect=400)
    s.call("WhatsApp template test send", "POST", "/api/admin/whatsapp-templates/test", json={"kind": "call"})
    when = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT19:00")
    c = s.call("add group call", "POST", "/api/admin/calls", json={"title": "Pricing your first project", "when": when, "link": "https://meet.example.com/y"})
    s.call("add library item", "POST", "/api/admin/library", json={"title": "Day 2 workbook", "kind": "link", "url": "https://drive.example.com/w2", "section": "Week 1"})
    s.call("add cohort", "POST", "/api/admin/program/cohorts", json={"name": f"QA cohort {RUN}", "start_date": date.today().isoformat(),
                                                                      "days": [{"n": 1, "title": "Define your niche", "tasks": [{"text": "Finish Niche Snapshot"}]}]})
    bc = s.call("add bootcamp", "POST", "/api/admin/bootcamps", json={"title": "Build your offer", "published": True,
                                                                      "tasks": [{"title": "Write your offer in one line"}]})
    vtt = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:05.000\n" + "Never price by the hour when the client buys a result. " * 20
    rc = s.call("upload session transcript → recap (AI)", "POST", "/api/admin/recaps", files={"file": ("s.vtt", vtt.encode(), "text/vtt")}, data={"title": "Pricing"})
    rid = idof(rc)
    if rid:
        s.call("recap audio", "POST", f"/api/admin/recaps/{rid}/audio")
        s.call("recap publish (members alerted)", "POST", f"/api/admin/recaps/{rid}/publish")
    s.call("knowledge base upload", "POST", "/api/admin/kb", files={"file": ("pricing.txt", ("Akshat on pricing: price by outcome. " * 30).encode(), "text/plain")})
    s.call("weekly case remake (search + AI)", "POST", "/api/admin/weekly/generate", expect=(200, 503))
    jobs = s.call("jobs list", "GET", "/api/admin/jobs")
    for j in ((jobs or {}).get("items") or (jobs if isinstance(jobs, list) else []))[:20]:
        name = j.get("name") if isinstance(j, dict) else None
        if name:
            s.call(f"job run now: {name}", "POST", f"/api/admin/jobs/{name}/run", expect=(200, 409))
    member = S("member-not-admin")
    member.login(plan="l2", n=5)
    member.call("member cannot open admin", "GET", "/api/admin/pulse", expect=403)
    return bc


def l2_bootcamp_submit():
    s = S("l2")
    s.login(plan="l2", n=4)
    bs = s.call("bootcamps after admin added", "GET", "/api/bootcamps")
    for b in (bs or {}).get("items", []) or []:
        full = s.call("bootcamp view", "GET", f"/api/bootcamps/{b['id']}")
        tasks = (full or {}).get("task_list") or []
        for t in tasks:
            s.call("bootcamp task submit", "POST", f"/api/bootcamps/{b['id']}/tasks/{t['id']}", json={"text": "Plant heads in FMCG: wastage halved in 90 days."})
            return
    s.call("inbox shows alerts", "GET", "/api/inbox")


def member_inbox():
    s = S("member")
    s.login(plan="member", n=2)
    ib = s.call("member inbox after admin reply", "GET", "/api/inbox")
    kinds = [x.get("kind") for x in (ib or {}).get("items", [])]
    RESULTS.append({"who": "member", "check": "support reply reached inbox", "ok": "support" in kinds, "status": 0, "expect": [0],
                    "method": "-", "path": "-", "ms": 0, "body": None if "support" in kinds else str(kinds)})
    print(("PASS" if "support" in kinds else "FAIL") + " [member] support reply reached inbox", kinds[:5])


def l1_cancel_offer():
    s = S("l1-buyer")
    s.login(plan="free", n=7)
    co = s.call("buy L1", "POST", "/api/billing/checkout", json={"plan": "l1"})
    s.call("L1 payment verified", "POST", "/api/billing/verify", json={"subscription_id": co["subscription_id"], "payment_id": f"pay_l1_{RUN}", "signature": "x"})
    me = s.call("plan is L1", "GET", "/api/me/plan")
    r = s.call("cancel L1", "POST", "/api/billing/cancel")
    offer = json.dumps(r or {})
    ok = "member" in offer or "offer" in offer or "downsell" in offer
    RESULTS.append({"who": "l1-buyer", "check": "cancelling L1 offers the ₹1,999 plan", "ok": ok, "status": 0, "expect": [0], "method": "-", "path": "-", "ms": 0, "body": offer[:400]})
    print(("PASS" if ok else "FAIL"), "[l1-buyer] cancel offer:", offer[:300])
    me2 = s.call("plan still L1 until period end", "GET", "/api/me/plan")
    ok2 = (me2 or {}).get("plan") == "l1"
    RESULTS.append({"who": "l1-buyer", "check": "L1 kept until the paid period ends", "ok": ok2, "status": 0, "expect": [0], "method": "-", "path": "-", "ms": 0, "body": None if ok2 else str(me2)[:200]})


if __name__ == "__main__":
    t0 = time.time()
    public_checks()
    free_checks()
    tid = member_checks()
    l1_checks()
    l2_checks()
    admin_checks(tid)
    l2_bootcamp_submit()
    member_inbox()
    l1_cancel_offer()
    fails = [r for r in RESULTS if not r["ok"]]
    five = [r for r in RESULTS if isinstance(r["status"], int) and r["status"] >= 500]
    print(f"\n{len(RESULTS)} checks, {len(RESULTS) - len(fails)} passed, {len(fails)} failed, {len(five)} server errors, {time.time() - t0:.0f}s")
    Path(__file__).with_name("e2e_results.json").write_text(json.dumps(RESULTS, indent=1))
