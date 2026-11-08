"""AI-failure QA: every AI tool under every way the AI can fail. Run against scripts/qa/ai_fault_server.py.

For each scenario a fresh L2 member does the setup with a healthy AI (documents, notebook, contacts, pitch thread,
portfolio project, website, a coaching chat), then the AI is switched to the scenario and every AI tool is called.
Each call checks:
  - what the member gets (status + error code + message),
  - that a failed call gives the use back (monthly usage unchanged),
  - that the server log names the real reason (a line per failure),
  - for the healthy scenarios, that the tool works and counts one use.

Usage: python scripts/qa/ai_busy_qa.py http://127.0.0.1:8002 <server log file> [out.json]
"""
import json
import random
import sys
import time
from pathlib import Path

import httpx

BASE, LOG = sys.argv[1].rstrip("/"), Path(sys.argv[2])
OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).with_name("ai_busy_results.json")
RUN = random.randint(100, 999)
BUSY_MSG = "The AI is busy right now. Try again in a minute. This didn't use up your go."

ANTHROPIC = ["ok", "fenced", "truncated", "vendor_error", "timeout", "queue_full", "not_json"]
GEMINI = ["g_ok", "g_busy_once", "g_busy", "g_fallback"]
HEALTHY = {"ok", "fenced", "g_ok", "g_busy_once", "g_fallback"}

ANSWER = ("The real problem is margin leakage: profit fell from 4% to 1.5% as the new stores opened. Objective: from "
          "1.5% to 3% in 90 days. Framework: margin leak check. Do first: fresh produce ordering. Owner: ops head; "
          "track wastage % weekly.")
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 2048
import struct  # noqa: E402
WAV = (b"RIFF" + struct.pack("<I", 36 + 16000) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16)
       + b"data" + struct.pack("<I", 16000) + b"\x00\x01" * 8000)
def _png():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1080, 900), (243, 242, 239)).save(buf, "PNG")
    return buf.getvalue()


PNG = _png()
CSV = "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n" + "\n".join(
    f"Person{i},Shah,https://linkedin.com/in/p{i},,Company {i} Pvt Ltd,{'Managing Director' if i % 2 else 'VP Operations'},0{i % 9 + 1} Jan 2024"
    for i in range(12))


def find(d, key):
    if isinstance(d, dict):
        if key in d:
            return d[key]
        for v in d.values():
            r = find(v, key)
            if r is not None:
                return r
    if isinstance(d, list):
        for v in d:
            r = find(v, key)
            if r is not None:
                return r
    return None


def first_id(j, *keys):
    if not isinstance(j, dict):
        return None
    for k in keys + ("id",):
        if isinstance(j.get(k), str):
            return j[k]
    for v in j.values():
        if isinstance(v, dict) and isinstance(v.get("id"), str):
            return v["id"]
    return None


class Member:
    def __init__(self, n):
        self.c = httpx.Client(base_url=BASE, timeout=120)
        r = self.c.post("/api/qa/login", json={"plan": "l2", "phone": f"+9181{RUN}{n:05d}"})
        assert r.status_code == 200, r.text

    def used(self):
        me = self.c.get("/api/auth/me").json()
        lim = find(me, "limits") or {}
        return {k: v.get("used", 0) for k, v in lim.items() if isinstance(v, dict)}

    def req(self, method, path, **kw):
        r = self.c.request(method, path, **kw)
        try:
            body = r.json()
        except ValueError:
            body = {"raw": r.text[:200]}
        return r.status_code, body


def scenario(name):
    httpx.post(f"{BASE}/api/_qa/scenario", json={"name": name}).raise_for_status()


def setup(m: Member) -> dict:
    """Everything the AI tools need, made while the AI is healthy."""
    scenario("ok")
    ctx = {}
    _, cases = m.req("GET", "/api/cases")
    ctx["case"] = next((c["id"] for c in (cases or {}).get("items", []) if c.get("live")), "retail-chain-margins")
    _, up = m.req("POST", "/api/docs", files={"file": ("notes.txt", ("The board decided to open two depots in Gujarat. "
                                                                    "Revenue grew 18 percent to 42 crore. ") * 20, "text/plain")})
    ctx["doc"] = first_id(up, "doc_id")
    _, nb = m.req("POST", "/api/notebook", json={"title": "Cold chain in Gujarat"})
    ctx["nb"] = first_id(nb, "project_id")
    m.req("POST", f"/api/notebook/{ctx['nb']}/sources/text", json={"title": "Notes", "text": (
        "Gujarat cut power tariffs for cold storage by 12% in 2026. Five new parks opened near Surat on 14 January 2027. ") * 5})
    m.req("POST", "/api/network/import", files={"file": ("Connections.csv", CSV.encode(), "text/csv")})
    _, net = m.req("GET", "/api/network")
    ctx["contacts"] = [x["id"] for x in (net or {}).get("items", [])][:3]
    _, tk = m.req("POST", "/api/pitch", json={"pitch_type": "elevator", "setting": "CII networking event",
                                              "audience": "MD of a mid-size pump maker"})
    ctx["pitch"] = first_id(tk, "thread_id")
    _, pf = m.req("POST", "/api/portfolio")
    ctx["portfolio"] = first_id(pf, "project_id")
    _, site = m.req("POST", "/api/website/build", json={})
    secs = find(site, "sections") or []
    ctx["section"] = next((s.get("id") or s.get("key") for s in secs if isinstance(s, dict)), None)
    _, conv = m.req("POST", "/api/gpts/define-your-niche/conversations", json={})
    ctx["conv"] = first_id(conv, "conversation_id")
    return ctx


def tools(ctx):
    """(name, kind, method, path, kwargs). kind: anthropic | gemini."""
    p = ctx
    return [
        ("Niche Snapshot", "anthropic", "POST", "/api/start/snapshot", {"json": {"experiences": ["Supply chain", "Team leadership", "Cost cutting"], "enjoy": [0], "industry": "FMCG", "years": 18}}),
        ("Weekly case scoring", "anthropic", "POST", f"/api/cases/{p['case']}/answer", {"json": {"answer": ANSWER}}),
        ("Meeting Brief", "anthropic", "POST", "/api/briefs", {"json": {"company": "Tata Motors", "purpose": "Discuss supplier costs"}}),
        ("LinkedIn rewrites", "anthropic", "POST", "/api/linkedin/check", {"json": {"headline": "GM Operations at ABC Ltd | Supply chain", "about": "18 years in FMCG plants.", "rewrite": True}}),
        ("Presentation Builder", "anthropic", "POST", "/api/decks", {"json": {"source": "text", "title": "Cutting wastage", "audience": "Plant heads", "notes": "Wastage is 6% of output. Target 3% in 90 days. Three levers: ordering, cold chain, shift handover."}}),
        ("Visual Builder", "anthropic", "POST", "/api/visuals", {"json": {"kind": "process", "prompt": "Five steps to cut plant wastage"}}),
        ("Listen mode", "anthropic", "POST", "/api/listen", {"json": {"source": "case", "id": "retail-chain-margins"}}),
        ("Doc Reader question", "anthropic", "POST", "/api/docs/ask", {"json": {"question": "What did the board decide about depots?"}}),
        ("Doc Reader summary", "anthropic", "POST", f"/api/docs/{p['doc']}/summary", {}),
        ("Website build", "anthropic", "POST", "/api/website/build", {"json": {}}),
        ("Website section edit", "anthropic", "POST", f"/api/website/sections/{p['section']}/ai", {"json": {"instruction": "Make it shorter and plainer"}}),
        ("Progress Report", "anthropic", "POST", "/api/progress", {}),
        ("Action Hub chat", "anthropic", "POST", f"/api/gpts/conversations/{p['conv']}/messages", {"json": {"text": "18 years in FMCG supply chain. Which niche fits?"}}),
        ("Akshat AI", "anthropic", "POST", "/api/akshat-ai/ask", {"json": {"question": "How do I price my first project?"}}),
        ("Offer Card", "anthropic", "POST", "/api/offer-card", {"json": {"offer_name": "90-day plant reset", "engagement": "90 days", "what_you_get": "Diagnosis, plan, weekly reviews", "fee_from_inr": 300000, "fee_to_inr": 600000}}),
        ("Story from text", "anthropic", "POST", "/api/stories/text", {"json": {"text": "In 2015 our Nashik plant was losing 6% of output to wastage. I set up a daily review with shift heads, fixed the cold chain and changed ordering. In 9 months wastage fell to 3.5%, saving ₹2 crore a year."}}),
        ("Insight Pack", "anthropic", "POST", "/api/insights", {"json": {"industry": "FMCG"}}),
        ("Portfolio new client", "anthropic", "POST", "/api/portfolio", {}),
        ("Portfolio feedback", "anthropic", "POST", f"/api/portfolio/{p['portfolio']}/review" if p.get("answered") else f"/api/portfolio/{p['portfolio']}/answer",
         {"json": {"scope": "Margin fell in 14 stores since expansion", "objective": "From 1.5% to 3% in 90 days", "framework_options": "Margin leak check: pricing, wastage, mix", "do_first": "Fix fresh produce ordering", "owner_metrics": "Ops head; wastage % weekly, margin monthly"}}),
        ("Pitch coach chat", "anthropic", "POST", f"/api/pitch/{p['pitch']}/chat", {"json": {"message": "How do I open?"}}),
        ("Notebook question", "anthropic", "POST", f"/api/notebook/{p['nb']}/ask", {"json": {"question": "What did the state do to power tariffs?"}}),
        ("Notebook briefing", "anthropic", "POST", f"/api/notebook/{p['nb']}/generate", {"json": {"kind": "briefing"}}),
        ("Notebook timeline", "anthropic", "POST", f"/api/notebook/{p['nb']}/generate", {"json": {"kind": "timeline"}}),
        ("Notebook audio overview", "anthropic", "POST", f"/api/notebook/{p['nb']}/audio", {}),
        ("Warm Network scoring", "anthropic", "POST", "/api/network/score", {"json": {"ids": p["contacts"]}}),
        ("Outreach Drafter", "anthropic", "POST", "/api/outreach", {"json": {"name": "Meera Kapoor", "role": "COO", "company": "Sunrise Textiles", "relationship": "worked together at Arvind", "channel": "email", "goal": "diagnostic_call"}}),
        ("Opportunity Radar", "anthropic", "POST", "/api/radar/run", {"json": {"industry": "Pharma", "city": "Pune"}}),
        ("Discovery Call Prep", "anthropic", "POST", "/api/call-prep", {"json": {"company": "Desai Pumps", "person": "Rahul Desai", "role": "MD", "how_met": "Ex-colleague", "known": "Sales flat for two years."}}),
        ("Proposal", "anthropic", "POST", "/api/proposals", {"json": {"company": "Desai Pumps", "person": "Rahul Desai", "role": "MD", "fee_low_inr": 150000, "fee_high_inr": 400000, "notes": "Sales flat for two years at ₹40 crore. Dealers in Gujarat complain about delivery times."}}),
        ("Client Diagnostic", "anthropic", "POST", "/api/diagnostic", {"json": {"topic": "Dealer network health", "audience": "Pump makers"}}),
        ("Social posts", "anthropic", "POST", "/api/social/generate", {"json": {"count": 3}}),
        ("LinkedIn profile review", "anthropic", "POST", "/api/linkedin-review", {"files": [("files", ("top.png", PNG, "image/png"))], "data": {"target": "Owners of auto component makers in Pune"}}),
        ("LinkedIn 30-day plan", "anthropic", "POST", "/api/linkedin-review/plan", {"json": {"target": "Owners of auto component makers in Pune"}}),
        ("Voice-note story", "gemini", "POST", "/api/stories/voice", {"files": {"file": ("note.wav", WAV, "audio/wav")}, "data": {"duration_s": "60"}}),
        ("Pitch video scorecard", "gemini", "POST", f"/api/pitch/{p['pitch']}/take", {"content": MP4, "headers": {"content-type": "video/mp4"}, "params": {"duration_s": 60, "filename": "p.mp4"}}),
    ]


def log_tail(offset):
    with LOG.open("r", errors="replace") as f:
        f.seek(offset)
        text = f.read()
    return text, LOG.stat().st_size


def load_knowledge_base():
    """Akshat AI answers only from the knowledge base; without material it routes questions to the team (no AI)."""
    a = httpx.Client(base_url=BASE, timeout=60)
    a.post("/api/qa/login", json={"role": "admin"}).raise_for_status()
    text = ("Akshat on pricing your first project: price by the outcome, not by the hour. Start with a paid diagnostic "
            "of two to four weeks, then a monthly retainer. Never discount the first project; add scope instead. ") * 20
    r = a.post("/api/admin/kb", files={"file": ("pricing.txt", text.encode(), "text/plain")})
    print("knowledge base upload:", r.status_code)


CHAT = {"Action Hub chat", "Pitch coach chat"}       # free text, not JSON: a plain sentence is a valid answer


def run():
    load_knowledge_base()
    results = []
    n = 0
    for sc in ANTHROPIC + GEMINI:
        n += 1
        m = Member(n)
        ctx = setup(m)
        kind = "gemini" if sc.startswith("g_") else "anthropic"
        for name, k, method, path, kw in tools(ctx):
            if k != kind:
                continue
            who = m
            if name == "Website build":          # setup already built this member's site; use one without a site
                n += 1
                who = Member(n)
            scenario(sc)
            before = who.used()
            off = LOG.stat().st_size
            stats0 = httpx.get(f"{BASE}/api/_qa/stats").json()
            t = time.perf_counter()
            status, body = who.req(method, path, **kw)
            ms = round((time.perf_counter() - t) * 1000)
            stats1 = httpx.get(f"{BASE}/api/_qa/stats").json()
            time.sleep(0.05)
            after = who.used()
            logs, _ = log_tail(off)
            spent = {f: after[f] - before.get(f, 0) for f in after if after[f] != before.get(f, 0)}
            detail = body.get("detail") if isinstance(body, dict) else None
            code = detail.get("code") if isinstance(detail, dict) else None
            msg = detail.get("msg") if isinstance(detail, dict) else (detail if isinstance(detail, str) else None)
            ai_calls = (stats1["anthropic_calls"] - stats0["anthropic_calls"]) if kind == "anthropic" else stats1["gemini_tries"]
            reason = [ln.strip()[:240] for ln in logs.splitlines()
                      if any(x in ln for x in ("AI work failed", "LLM task", "LLM reply cut", "transcription failed",
                                               "pitch video failed", "stayed busy", "gemini", "queue full", "timed out", "chat reply cut"))]
            row = {"scenario": sc, "tool": name, "status": status, "code": code, "msg": msg, "ms": ms, "spent": spent,
                   "ai_calls": ai_calls, "log": reason[:4]}
            healthy = sc in HEALTHY
            if healthy:
                row["pass"] = status == 200
                row["why"] = "" if row["pass"] else f"expected 200, got {status} {code}"
            else:
                problems = []
                if name in CHAT and sc == "not_json":
                    row["pass"], row["why"] = (status == 200), "a chat may answer in plain words"
                elif name in CHAT and sc == "truncated":
                    cut_logged = any("chat reply cut" in ln for ln in reason)
                    row["pass"] = status == 200 and cut_logged
                    row["why"] = "partial reply kept; " + ("cut logged" if cut_logged else "cut NOT logged")
                elif ai_calls == 0 and sc != "queue_full":
                    row["pass"], row["why"] = None, "tool made no AI call in this setup"
                else:
                    if status == 200:
                        problems.append("answered 200 although the AI failed (fallback or partial answer)")
                    elif status != 503:
                        problems.append(f"status {status} {code}, not 503")
                    if spent:
                        problems.append(f"use not given back: {spent}")
                    if status != 200 and not reason:
                        problems.append("no log line names the reason")
                    row["pass"] = not problems
                    row["why"] = "; ".join(problems)
            if name == "Portfolio feedback" and status != 200 and not ctx.get("answered"):
                ctx["answered"] = True       # the answer is saved; later scenarios use "Get my feedback"
            results.append(row)
            mark = {True: "PASS", False: "FAIL", None: "SKIP"}[row["pass"]]
            print(f"{mark} {sc:12} {name:24} {status} {code or '':14} {ms:>6} ms  spent={spent or '-'}  "
                  f"ai={ai_calls}  {row['why']}")
            sys.stdout.flush()
    scenario("ok")
    OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    p = sum(1 for r in results if r["pass"] is True)
    f = sum(1 for r in results if r["pass"] is False)
    s = sum(1 for r in results if r["pass"] is None)
    print(f"\n{len(results)} checks: {p} passed, {f} failed, {s} skipped")


if __name__ == "__main__":
    run()
