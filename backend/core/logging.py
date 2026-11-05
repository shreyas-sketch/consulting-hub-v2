"""Logging set-up: readable lines locally, one JSON object per line in production (Railway log search, drains).

Every record carries the current request id (`core.middleware.request_id_var`), so all lines of one request can be
found together. Configured once by `server.create_app`; calling it again is a no-op.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from .middleware import request_id_var

_configured = {"done": False}


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
               "level": record.levelname, "logger": record.name, "msg": record.getMessage(),
               "request_id": getattr(record, "request_id", "-")}
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False)


def configure(level: str = "INFO", json_lines: bool = False) -> None:
    if _configured["done"]:
        return
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(JsonFormatter() if json_lines else logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)            # added, not replacing: keeps pytest's and uvicorn's own handlers working
    root.setLevel(level)
    _configured["done"] = True
