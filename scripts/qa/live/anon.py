"""Live checks that need no login and send nothing to anyone."""
import time
import httpx

U = "https://consulting-hub-v2-production.up.railway.app"
c = httpx.Client(base_url=U, timeout=30, follow_redirects=False)
rows = []


def check(name, ok, detail=""):
    rows.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail else ""))


def get(p, **kw):
    t = time.perf_counter(); r = c.get(p, **kw); return r, round((time.perf_counter() - t) * 1000)


# health and config
r, ms = get("/api/health"); j = r.json()
check("health ok, production", r.status_code == 200 and j.get("ok") and j.get("env") == "production", f"{ms} ms, release {j.get('release')}")
r, ms = get("/api/health/ready"); check("database ready", r.json().get("mongo") == "ok", f"{ms} ms")
r, _ = get("/api/config"); check("public config has no secrets", r.status_code == 200 and not any(k in r.text.lower() for k in ("secret", "key", "token", "password")), r.text[:120])
r, _ = get("/api/plans/catalog"); cat = r.text
check("plans catalog lists the paid plans with GST prices", r.status_code == 200 and "1999" in cat.replace(",", "") or "1,999" in cat, cat[:120])

# security headers and transport
r, _ = get("/api/health")
h = {k.lower(): v for k, v in r.headers.items()}
check("HSTS on", "max-age" in h.get("strict-transport-security", ""))
check("nosniff", h.get("x-content-type-options") == "nosniff")
check("frame options", h.get("x-frame-options") in ("SAMEORIGIN", "DENY"))
check("request id returned", len(h.get("x-request-id", "")) >= 16)
check("server version not leaked", "uvicorn" not in h.get("server", "").lower(), h.get("server", ""))

# logged out is refused everywhere
for m, p in [("GET", "/api/auth/me"), ("GET", "/api/me/home"), ("GET", "/api/file"), ("GET", "/api/linkedin-review"),
             ("POST", "/api/briefs"), ("GET", "/api/admin/pulse"), ("GET", "/api/admin/users"), ("POST", "/api/qa/login")]:
    r = c.request(m, p, json={})
    ok = r.status_code in (401, 403, 404) and (p != "/api/qa/login" or r.status_code in (403, 404))
    check(f"logged out: {m} {p} refused", ok, str(r.status_code))
r = c.post("/api/qa/login", json={"plan": "l2"})
check("QA back-door login is OFF in production", r.status_code in (403, 404, 405), str(r.status_code))

# input validation without sending any message
r = c.post("/api/auth/otp/request", json={"phone": "12345"})
check("bad phone refused, nothing sent", r.status_code in (400, 422), f"{r.status_code} {r.text[:100]}")
r = c.post("/api/auth/otp/verify", json={"challenge_id": "x" * 32, "phone": "+919000000000", "code": "000000"})
check("verify with a made-up challenge refused", r.status_code in (400, 401, 404, 422), str(r.status_code))
r = c.get("/api/definitely-not-here")
check("unknown API path: JSON 404 envelope", r.status_code == 404 and r.json().get("detail", {}).get("code") == "not_found")
r = c.get("/api/cases/nope")
check("member endpoint logged out: JSON 401 envelope", r.status_code == 401 and r.json()["detail"]["code"] == "not_logged_in")
r = c.get("/s/this-site-does-not-exist-qa")
check("unknown member website: 404", r.status_code == 404, str(r.status_code))
r = c.get("/api/diagnostic/public/doesnotexist")
check("unknown public diagnostic: 404", r.status_code == 404, str(r.status_code))

# the app shell and deep links
for p in ["/", "/login", "/plans", "/terms", "/privacy", "/app/cases", "/app/linkedin", "/admin"]:
    r, ms = get(p)
    check(f"SPA {p} serves the app", r.status_code == 200 and '<div id="root">' in r.text, f"{ms} ms")
html = get("/")[0].text
import re
js = re.findall(r'src="(/static/js/[^"]+)"', html)
r = c.get(js[0]) if js else None
check("main script served and cached long", r is not None and r.status_code == 200 and "max-age" in r.headers.get("cache-control", ""),
      r.headers.get("cache-control", "") if r is not None else "no script")
check("index.html not cached long", "no-cache" in get("/")[0].headers.get("cache-control", "") or "max-age=0" in get("/")[0].headers.get("cache-control", ""),
      get("/")[0].headers.get("cache-control", ""))

# speed (5 tries each)
for p in ["/api/health", "/", "/api/plans/catalog"]:
    t = []
    for _ in range(5):
        t.append(get(p)[1])
    check(f"speed {p}: median under 800 ms", sorted(t)[2] < 800, f"median {sorted(t)[2]} ms, max {max(t)} ms")

print(f"\n{sum(rows)} of {len(rows)} passed")
