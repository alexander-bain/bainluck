"""CAL-P143 — D22: a diagnostic count stops taking the publish down with it.

LANDS AT ``backend/tests/test_calibration_soft_stage_d22.py`` with
``artifacts/cal-p143/d22-diagnostics-nonblocking.patch``. RED against the tree
as it stands (``PhaseRunner`` has no ``soft_stage``), GREEN against the patched
one — proved by ``artifacts/cal-p143/verify-d22.py``.

The guards are shaped around the three ways this change could go wrong:

* it could swallow a failure and publish a DEFAULT that reads as evidence —
  the reason ``contract_ok`` is ``None`` and not ``True`` on an unobserved beat;
* it could leave the session unusable, which is what a bare ``try`` does after
  a statement timeout — the reason there is a savepoint at all;
* it could hide the degradation, which is how a standing defect becomes
  invisible instead of fixed — the reason the stage name is recorded.
"""

from __future__ import annotations

import contextlib

import pytest

from app.tasks.calibration_main_build import PhaseRunner, SoftStageOutcome
from app.tasks.precompute_calibration import _build_truth_evidence

COMMON = dict(mex_normalized_markets=7, mex_published_markets=7,
              published_outcomes=100, published_questions=50)


class _FakeSavepoint:
    def __init__(self, log):
        self.log = log

    async def rollback(self):
        self.log.append("rollback")

    async def commit(self):
        self.log.append("commit")


class _FakeSession:
    def __init__(self):
        self.log: list[str] = []

    async def begin_nested(self):
        self.log.append("begin_nested")
        return _FakeSavepoint(self.log)


@pytest.fixture()
def runner():
    r = PhaseRunner.__new__(PhaseRunner)
    r.degraded_stages = []

    @contextlib.contextmanager
    def _stage(name):
        yield

    r.stage = _stage
    return r


# ---------------------------------------------------------------------------
# 1. The mechanism
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_raising_soft_stage_does_not_end_the_beat(runner):
    db = _FakeSession()
    async with runner.soft_stage(db, "read:truth_census") as soft:
        raise RuntimeError("canceling statement due to statement timeout")
    assert soft.failed is True
    assert "statement timeout" in soft.error
    assert db.log == ["begin_nested", "rollback"], (
        "the savepoint must be rolled back — a statement timeout aborts the "
        "whole transaction, and without ROLLBACK TO SAVEPOINT every later read "
        "and the phase commit fail too"
    )
    assert runner.degraded_stages == ["read:truth_census"]


@pytest.mark.asyncio
async def test_a_clean_soft_stage_commits_and_is_not_degraded(runner):
    db = _FakeSession()
    async with runner.soft_stage(db, "read:date_range") as soft:
        pass
    assert soft.failed is False
    assert db.log == ["begin_nested", "commit"]
    assert runner.degraded_stages == []


@pytest.mark.asyncio
async def test_the_session_is_still_usable_after_a_degraded_stage(runner):
    """The whole point: the NEXT read still happens."""
    db = _FakeSession()
    async with runner.soft_stage(db, "read:truth_census"):
        raise RuntimeError("boom")
    async with runner.soft_stage(db, "read:date_range") as second:
        pass
    assert second.failed is False
    assert db.log == ["begin_nested", "rollback", "begin_nested", "commit"]


def test_the_outcome_object_defaults_to_not_failed():
    o = SoftStageOutcome()
    assert o.failed is False and o.error is None


# ---------------------------------------------------------------------------
# 2. The payload — an unobserved census must not read as a clean one
# ---------------------------------------------------------------------------

def test_an_observed_clean_census_reads_ok():
    ev = _build_truth_evidence({"eligible": {"outcomes": 10, "markets": 2}}, **COMMON)
    assert ev["census_observed"] is True
    assert ev["contract_ok"] is True
    assert ev["contract_status"] == "ok"


def test_an_observed_violation_still_reads_as_a_violation():
    ev = _build_truth_evidence({"unknown": {"outcomes": 3, "markets": 1}}, **COMMON)
    assert ev["census_observed"] is True
    assert ev["contract_ok"] is False
    assert ev["contract_status"] == "violated"
    assert ev["contract_violations"]


def test_an_unobserved_census_is_not_a_verdict():
    """gotcha #53. The failure mode this replaces is the one-line version of
    the fix — ``truth_by_class = {}`` — under which every ``.get`` default is
    zero and the contract reports CLEAN on no evidence whatsoever."""
    ev = _build_truth_evidence(None, **COMMON)
    assert ev["census_observed"] is False
    assert ev["contract_status"] == "unobserved"
    assert ev["contract_ok"] is None, (
        "True would claim the contract holds and False would claim a violation; "
        "neither was observed"
    )
    assert ev["contract_violations"] == []


def test_a_violation_found_on_a_degraded_beat_outranks_unobserved():
    """``partition_invariant`` is derived from the aggregate, not the census, so
    it still answers when the census did not run — and a RED it finds must not
    be downgraded to 'we didn't look'."""
    ev = _build_truth_evidence(None, mex_normalized_markets=7,
                               mex_published_markets=9,
                               published_outcomes=100, published_questions=50)
    assert ev["census_observed"] is False
    assert ev["partition_invariant"]["ok"] is False
    assert any("partition invariant" in v for v in ev["contract_violations"])
    assert ev["contract_status"] == "violated"
    assert ev["contract_ok"] is False
