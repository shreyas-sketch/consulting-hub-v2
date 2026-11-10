"""Shared helpers for the live run: OTP login with a test number (nothing is sent), timed calls, a log of results."""
import json
import time
from pathlib import Path

import httpx

U = "https://consulting-hub-v2-production.up.railway.app"
OUT = Path(__file__).with_name("results.jsonl")
CODES = dict(p.split(":") for p in __import__("os").environ.get("QA_TEST_CODES", "").split(",") if ":" in p)  # "+9199...:code,..."


def login(phone, name):
    """Reuses a saved session for this number when it still works (login codes are limited to 5 an hour)."""
    jar = Path(__file__).with_name(f"cookies-{phone[-3:]}.json")
    if jar.exists():
        c = httpx.Client(base_url=U, timeout=200, cookies=json.loads(jar.read_text()))
        if c.get("/api/auth/me").status_code == 200:
            return c, {"reused": True}
    c = httpx.Client(base_url=U, timeout=200)
    r = c.post("/api/auth/otp/request", json={"phone": phone})
    if r.status_code == 429 and r.json().get("detail", {}).get("code") == "resend_cooldown":
        time.sleep(int(r.json()["detail"].get("retry_in", 30)) + 1)      # the 30 s gap between login codes
        r = c.post("/api/auth/otp/request", json={"phone": phone})
    assert r.status_code == 200, f"otp request {r.status_code} {r.text}"
    ch = r.json()
    r = c.post("/api/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "phone": phone, "code": CODES[phone], "name": name})
    assert r.status_code == 200, f"otp verify {r.status_code} {r.text}"
    jar.write_text(json.dumps(dict(c.cookies)))
    return c, ch


def call(c, label, method, path, ok=(200,), **kw):
    t = time.perf_counter()
    try:
        r = c.request(method, path, **kw)
        status = r.status_code
        try:
            body = r.json()
        except ValueError:
            body = {"_raw": r.text[:300], "_ctype": r.headers.get("content-type")}
    except Exception as e:  # noqa: BLE001
        status, body = -1, {"_error": repr(e)[:300]}
    s = round(time.perf_counter() - t, 1)
    good = status in ok
    detail = body.get("detail") if isinstance(body, dict) else None
    print(f"{'PASS' if good else 'FAIL'} {label:42} {status} {s:>6}s" + ("" if good else f"  {str(detail or body)[:220]}"), flush=True)
    with OUT.open("a") as f:
        f.write(json.dumps({"label": label, "path": path, "status": status, "secs": s, "ok": good,
                            "detail": str(detail)[:300] if not good else None}) + "\n")
    return body, status


def limits(c):
    me = c.get("/api/auth/me").json()

    def find(d):
        if isinstance(d, dict):
            if "limits" in d:
                return d["limits"]
            for v in d.values():
                r = find(v)
                if r:
                    return r
    return find(me) or {}, me
