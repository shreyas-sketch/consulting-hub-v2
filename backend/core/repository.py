"""Base class for data-access objects (the repository layer).

A repository owns one aggregate's collections: it is the only code that knows their field names, indexes and
query shapes. Services ask it for domain data in plain dicts and never touch Motor directly, so a schema change or
an index-driven query rewrite stays in one file, and services can be unit-tested with a fake repository.

    class CaseRepository(Repository):
        async def get_active(self, case_id): return await self.db.cases.find_one(...)

    repo = CaseRepository()            # uses the app's bound database (state.db())
    repo = CaseRepository(mongomock_db) # or an explicit one (tests, scripts, jobs with their own handle)
"""
from __future__ import annotations

from typing import Any, Optional


class Repository:
    def __init__(self, db: Optional[Any] = None) -> None:
        self._db = db

    @property
    def db(self):
        if self._db is not None:
            return self._db
        import state
        return state.db()
