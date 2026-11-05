"""Domain errors and the one place they are turned into HTTP responses.

Why
---
Services and routes raise *what went wrong* (`NotFound("Case not found.")`, `LimitReached(...)`), not how to encode it
on the wire. Every error has a stable machine `code` the frontend switches on (402 `limit` and 403 `locked` open the
upgrade sheet, 503 `ai_busy` retries once, 403 `revoked` logs out) and a plain-English `msg` a member can read.

Wire format (unchanged from the first version of the API, so the frontend contract holds):

    HTTP <status>
    {"detail": {"code": "<code>", "msg": "<sentence>", ...extra fields}}

`AppError` subclasses `HTTPException`, so FastAPI renders it natively and any existing `except HTTPException` keeps
working. `install(app)` adds the handlers for what is *not* an `AppError`: unexpected exceptions become a 500 with the
same envelope and the request id (never a stack trace), and every error response carries `X-Request-ID`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("core.errors")


class AppError(HTTPException):
    """Base class. Subclasses fix `status` and the default `code`; callers give the member-facing `msg`."""

    status: int = 400
    code: str = "bad_request"
    default_msg: str = "Something went wrong. Please try again."

    def __init__(self, msg: Optional[str] = None, *, code: Optional[str] = None, status: Optional[int] = None,
                 headers: Optional[dict[str, str]] = None, **extra: Any) -> None:
        self.code = code or self.code
        self.msg = msg or self.default_msg
        self.extra = extra
        super().__init__(status_code=status or self.status, detail={"code": self.code, "msg": self.msg, **extra},
                         headers=headers)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}({self.status_code}, {self.code!r}, {self.msg!r})"


class BadRequest(AppError):
    status, code = 400, "bad_request"


class Unauthorized(AppError):
    status, code, default_msg = 401, "not_logged_in", "Log in to continue."


class Forbidden(AppError):
    status, code, default_msg = 403, "forbidden", "You can't do that."


class Locked(AppError):
    """The member's plan does not include the feature (frontend opens the upgrade sheet)."""
    status, code, default_msg = 403, "locked", "This is on a higher plan."


class LimitReached(AppError):
    """The month's (or the free account's lifetime) allowance is used (frontend opens the upgrade sheet)."""
    status, code, default_msg = 402, "limit", "You've used this month's limit."


class NotFound(AppError):
    status, code, default_msg = 404, "not_found", "Not found."


class Conflict(AppError):
    status, code = 409, "conflict"


class Gone(AppError):
    status, code, default_msg = 410, "gone", "This is no longer available."


class PayloadTooLarge(AppError):
    status, code, default_msg = 413, "too_large", "That file is too large."


class UnsupportedMedia(AppError):
    status, code, default_msg = 415, "bad_type", "That file type isn't supported."


class InvalidInput(AppError):
    """A business-rule check on input failed (Pydantic handles shape; this is for 'pick a date in the next month')."""
    status, code, default_msg = 422, "invalid", "Please check what you typed."


class TooManyRequests(AppError):
    status, code, default_msg = 429, "too_many", "Too many tries. Wait a little and try again."


class UpstreamError(AppError):
    """A vendor (payments, messaging) refused or failed; nothing was changed on our side."""
    status, code, default_msg = 502, "upstream_failed", "A service we use didn't answer. Please try again."


class ServiceUnavailable(AppError):
    status, code, default_msg = 503, "busy", "This is busy right now. Try again in a minute."


class AIBusy(ServiceUnavailable):
    """The AI queue was full or the call failed; the use was given back (the frontend retries POSTs once)."""
    code = "ai_busy"
    default_msg = "The AI is busy right now. Try again in a minute. This didn't use up your go."


BY_STATUS: dict[int, type[AppError]] = {
    400: BadRequest, 401: Unauthorized, 402: LimitReached, 403: Forbidden, 404: NotFound, 409: Conflict,
    410: Gone, 413: PayloadTooLarge, 415: UnsupportedMedia, 422: InvalidInput, 429: TooManyRequests,
    502: UpstreamError, 503: ServiceUnavailable,
}



def error(status: int, code: str, msg: str, **extra: Any) -> AppError:
    """Build the right AppError subclass for a status chosen at runtime (module-level `_err` helpers use this)."""
    cls = BY_STATUS.get(status, AppError)
    return cls(msg, code=code, status=status, **extra)


# ------------------------------------------------------------------------------------------------------ handlers ----
def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or request.headers.get("X-Request-ID", "")


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    rid = _request_id(request)
    log.exception("unhandled error on %s %s (request %s)", request.method, request.url.path, rid)
    return JSONResponse(status_code=500, headers={"X-Request-ID": rid} if rid else None, content={"detail": {
        "code": "server_error", "msg": "Something went wrong on our side. Please try again.", "request_id": rid}})


def install(app: FastAPI) -> None:
    app.add_exception_handler(Exception, _unhandled)
