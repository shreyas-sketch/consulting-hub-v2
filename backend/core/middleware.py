"""HTTP middleware: request id, access log, security headers.

Written as plain ASGI middleware (not `BaseHTTPMiddleware`) so streaming responses (audio, decks, PDFs) pass through
untouched and there is no per-request task overhead at webinar load.

* **Request id** — reuses an incoming `X-Request-ID` (Railway's edge or a client) when it is sane, else makes one.
  It is put on `request.state.request_id`, into every log line of the request (see `core.logging`) and on the
  response as `X-Request-ID`, so a member's "it failed" can be matched to the server log.
* **Access log** — one line per API request: method, path, status, duration. Health checks are skipped.
* **Security headers** — conservative defaults that don't break the SPA or member websites.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
log = logging.getLogger("access")

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_SKIP_LOG = ("/api/health",)
SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"x-frame-options", b"SAMEORIGIN"),
    (b"permissions-policy", b"camera=(self), microphone=(self), geolocation=()"),   # Pitch Practice records video
)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = ""
        for k, v in scope.get("headers") or ():
            if k == b"x-request-id":
                incoming = v.decode("latin-1")
                break
        rid = incoming if _SAFE_ID.match(incoming or "") else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = rid
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = [h for h in message.get("headers", []) if h[0].lower() != b"x-request-id"]
                headers.append((b"x-request-id", rid.encode()))
                present = {h[0].lower() for h in headers}
                for name, value in SECURITY_HEADERS:
                    if name not in present:
                        headers.append((name, value))
                if self.hsts and b"strict-transport-security" not in present:
                    headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            if path.startswith("/api") and not path.startswith(_SKIP_LOG):
                ms = (time.perf_counter() - started) * 1000
                log.info("%s %s %s %.0fms", scope.get("method"), path, status_holder["status"], ms)
            request_id_var.reset(token)
