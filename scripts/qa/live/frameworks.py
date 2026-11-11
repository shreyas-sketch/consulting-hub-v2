"""Live QA of "Work along with Akshat" on production: Akshat's cases, the member's own client (AI suggestion from the
niche, and written by hand), rule checks, proposals with the real AI. Usage:
QA_TEST_CODES="+9199...:code" python frameworks.py <out dir>   (writes the AI cases and proposals there to read)."""
import json
import sys
from pathlib import Path

from session import call, limits, login

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
c, _ = login("+919999900001", "Rajesh Kulkarni (QA)")
rows = []


def check(name, ok, detail=""):
    rows.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail else ""), flush=True)


NOKIA = {"circles": {"price": {"verdict": "works", "why": "Phones from about ₹1,500, anyone could afford one."},
                     "value": {"verdict": "fails", "why": "Stayed on Symbian; late to touchscreen smartphones."},
                     "availability": {"verdict": "works", "why": "Sold in every town, Tier 2 and Tier 3 too."}},
         "summary": "Price and reach held, but the value circle came apart when smartphones arrived."}
INTERIOR = {"percents": [60, 30, 10], "recommendation": "wait", "target_pct": 35, "months": 12,
            "reason": "60% comes from one developer; if they leave, the firm loses most of its revenue overnight."}
COACH = {"zone": 3, "fix": "reach", "actions": ["Run a free monthly career-switch webinar", "Partner with 3 HR communities",
                                               "Ask alumni for referrals with a small reward"]}
ALL = {"market-fit": NOKIA, "concentration-risk": INTERIOR, "growth-compass": COACH}

lim0, _ = limits(c)
items = call(c, "list", "GET", "/api/frameworks")[0]["items"]
check("three frameworks in workshop order", [x["key"] for x in items] == list(ALL))

# ---- Akshat's cases: save (free) and marking
for key, body in ALL.items():
    d, s = call(c, f"save Akshat {key}", "PUT", f"/api/frameworks/{key}/response", json=body)
    g = (d.get("mine") or {}).get("grade") or {}
    check(f"{key}: right answer = full marks + Akshat's read", s == 200 and g.get("correct") and bool((d.get("akshat") or {}).get("read")))
d, s = call(c, "refused: incomplete", "PUT", "/api/frameworks/market-fit/response", ok=(422,), json={**NOKIA, "summary": "x"})
check("incomplete answer refused in plain words", s == 422 and "{" not in d["detail"]["msg"], d["detail"]["msg"])

# ---- My own client: suggested from the niche (real AI)
cases = {}
for key, hint in [("market-fit", ""), ("concentration-risk", ""), ("growth-compass", "a forging unit in Pune")]:
    d, s = call(c, f"suggest own {key}", "POST", f"/api/frameworks/{key}/own/suggest", ok=(200,), json={"hint": hint})
    cs = ((d or {}).get("own") or {}).get("draft_case") if s == 200 else None
    cases[key] = cs
    check(f"{key}: AI suggests a client case", bool(cs), str(d.get("detail") if isinstance(d, dict) and s != 200 else "")[:160])
    if cs:
        txt = json.dumps(cs, ensure_ascii=False).lower()
        check(f"{key}: a real company with public sources", bool(cs.get("company")) and len(cs.get("refs") or []) >= 1,
              f"{cs.get('company')} · {', '.join(r['source'] for r in cs.get('refs') or [])}")
        check(f"{key}: the client fits the niche (auto / forging / machining / vendor)",
              any(w in txt for w in ("auto", "forg", "machin", "stamp", "vendor", "component", "oem")), cs["client"])
        (OUT / f"case-{key}.json").write_text(json.dumps(cs, ensure_ascii=False, indent=2))

lim1, _ = limits(c)
n_ok = sum(1 for v in cases.values() if v)
check("each suggestion counted one fw_case", lim1["fw_case"]["used"] - lim0["fw_case"]["used"] == n_ok,
      f"{lim0['fw_case']['used']} -> {lim1['fw_case']['used']}")


def right_answers(key, cs):
    """What the framework's rules say for this case, so we can save a correct reading."""
    if key == "market-fit":
        return {"circles": {"price": {"verdict": "works", "why": "Priced in line with what buyers there already pay."},
                            "value": {"verdict": "works", "why": "Solves a cost problem buyers there already have."},
                            "availability": {"verdict": "fails", "why": "No local team or partner in the new region yet."}},
                "summary": "Price and value look sound; getting a local presence is the gap to close before launching."}
    if key == "concentration-risk":
        tot = sum(s["amount"] for s in cs["sources"])
        pc = [round(s["amount"] * 100 / tot, 1) for s in cs["sources"]]
        return {"percents": pc, "recommendation": "wait" if max(pc) > 40 else "expand", "target_pct": 35, "months": 12,
                "reason": "The biggest source decides how risky expansion is; the plan keeps every source at 40% or less."}
    z = {("high", "high"): (1, "scale"), ("high", "low"): (2, "offer"), ("low", "high"): (3, "reach"), ("low", "low"): (4, "both")}
    zone, fix = z[(cs["reach_level"], cs["conversion_level"])]
    return {"zone": zone, "fix": fix, "actions": ["Visit the top ten buyers with a cost-saving case", "Publish one plant case study a month",
                                                  "Offer a free vendor-cost health check"]}


for key, cs in cases.items():
    if not cs:
        continue
    case = {k: cs[k] for k in ("client", "situation", "product", "new_region", "sources", "reach_per_month", "conversion_pct",
                               "reach_level", "conversion_level", "company", "refs", "estimates") if k in cs}
    d, s = call(c, f"save own {key}", "PUT", f"/api/frameworks/{key}/own", json={"case": case, "answers": right_answers(key, cs)})
    g = (((d or {}).get("own") or {}).get("mine") or {}).get("grade") or {}
    check(f"{key}: own case saved and checked by the rules", s == 200 and g.get("own") and bool(g.get("read")),
          f"{g.get('score')} of {g.get('out_of')}")
    if key != "market-fit":
        check(f"{key}: a rule-right reading gets full marks", g.get("correct") is True)

# ---- written by hand: a case with bad input is refused, a good one is saved even without AI
bad = {"case": {"client": "x", "situation": "short", "sources": [{"name": "A", "amount": 0}]}, "answers": INTERIOR}
d, s = call(c, "refused: thin own case", "PUT", "/api/frameworks/concentration-risk/own", ok=(422,), json=bad)
check("a thin hand-written case is refused in plain words", s == 422 and "{" not in d["detail"]["msg"], d["detail"]["msg"])

# ---- proposals (real AI): Akshat's case and own client
for key in ("concentration-risk",):
    d, s = call(c, f"proposal Akshat {key}", "POST", f"/api/frameworks/{key}/proposal")
    p = ((d or {}).get("mine") or {}).get("proposal") or {}
    check(f"{key}: proposal on Akshat's case", bool(p.get("markdown")))
    if p:
        (OUT / f"proposal-akshat-{key}.md").write_text(p["markdown"])
for key, cs in cases.items():
    if not cs:
        continue
    d, s = call(c, f"proposal own {key}", "POST", f"/api/frameworks/{key}/own/proposal")
    p = (((d or {}).get("own") or {}).get("mine") or {}).get("proposal") or {}
    md = p.get("markdown") or ""
    check(f"{key}: proposal for my own client", bool(md))
    if md:
        (OUT / f"proposal-own-{key}.md").write_text(md)
        low = md.lower()
        check(f"{key}: own proposal is about my client, not the workshop case",
              not any(w in low for w in ("nokia", "interior design", "career-coaching", "bangalore interior")))
        check(f"{key}: has objective, approach, fee in ₹", all(h in md for h in ("## Objective", "## Approach")) and "₹" in md)

lim2, _ = limits(c)
check("listing shows own cases", sum(1 for x in call(c, "list again", "GET", "/api/frameworks")[0]["items"] if x["own_saved"]) == n_ok)
print(f"fw_proposal used {lim0['fw_proposal']['used']} -> {lim2['fw_proposal']['used']}; fw_case {lim0['fw_case']['used']} -> {lim2['fw_case']['used']}")
print(f"\n{sum(rows)} of {len(rows)} passed")
