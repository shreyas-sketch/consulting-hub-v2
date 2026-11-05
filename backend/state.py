"""The process-wide database handle: the one place every module gets the database from.

`server.create_app(db)` binds it once at start-up (tests bind a mongomock database). Modules call `db()` when they
handle a request or run a job; nothing keeps its own copy, so there is exactly one binding to reason about.
"""
_db = {"db": None}


def set_db(db) -> None:
    _db["db"] = db


def is_bound() -> bool:
    return _db["db"] is not None


def db():
    if _db["db"] is None:
        raise RuntimeError("database not bound")
    return _db["db"]
