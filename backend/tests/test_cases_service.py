"""CaseService against an in-memory repository: business rules tested without HTTP."""
import pytest
from core.errors import Locked, NotFound
from features.case_bank import CASES  # noqa: E402
from features.cases.repository import CaseRepository
from features.cases.service import CaseService
from tests.conftest import run

CASE = {**CASES[0], "_id": "c1", "kind": "practice", "active": True}


class MemoryCases(CaseRepository):
    def __init__(self, db, cases):
        super().__init__(db)
        self.cases = {c["_id"]: c for c in cases}
        self.answers: list[dict] = []

    async def get_active(self, case_id):
        return self.cases.get(case_id)

    async def list_active(self):
        return list(self.cases.values())

    async def best_answers_by_case(self, user_id):
        return {a["case_id"]: a for a in self.answers if a["user_id"] == user_id}

    async def answers_for(self, user_id, case_id):
        return [a for a in self.answers if a["user_id"] == user_id and a["case_id"] == case_id]

    async def add_answer(self, doc):
        self.answers.append(doc)


@pytest.fixture
def svc(mdb):
    import state
    state.set_db(mdb)
    return CaseService(MemoryCases(mdb, [CASE, {**CASE, "_id": "c2"}]))


def _user(mdb, plan_grant=None):
    from bson import ObjectId
    u = {"_id": ObjectId(), "phone": "+919876500000", "role": "user"}
    run(mdb.users.insert_one(u))
    return u


def test_missing_case_is_not_found(svc, mdb):
    with pytest.raises(NotFound):
        run(svc.detail(_user(mdb), "nope"))


def test_free_account_sees_other_cases_locked(svc, mdb):
    import appsettings
    run(mdb.settings.insert_one({"_id": "app", "live_case_id": "c1"}))
    appsettings.reset_cache()
    u = _user(mdb)
    out = run(svc.listing(u))
    by_id = {r["id"]: r for r in out["items"]}
    assert out["plan"] == "free" and by_id["c1"]["live"] and not by_id["c1"]["locked"] and by_id["c2"]["locked"]
    with pytest.raises(Locked):
        run(svc.detail(u, "c2"))


def test_free_account_answers_the_live_case_once_and_earns_the_model_answer(svc, mdb):
    import appsettings
    run(mdb.settings.insert_one({"_id": "app", "live_case_id": "c1"}))
    appsettings.reset_cache()
    u = _user(mdb)
    assert run(svc.detail(u, "c1"))["case"]["model_answer"] is None
    out = run(svc.submit_answer(u, "c1", "The real problem is margin since stores grew; target from 8% to 12% by March."))
    assert 0 <= out["answer"]["overall"] <= 10 and out["model_answer"] == CASE["model_answer"]
    assert run(svc.detail(u, "c1"))["case"]["model_answer"] == CASE["model_answer"]
    assert len(svc.repo.answers) == 1
