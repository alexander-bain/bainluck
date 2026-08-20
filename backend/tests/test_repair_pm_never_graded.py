"""#1912 (CAL-P065) — the attended-apply rail for the never-graded PM cohort.

The write half of the ownership fix. 25,264 markets whose ``is_winner=false``
is the column default rather than a verdict, and which are 100%
venue-addressable — so the repair is not "can we find the answers" but "can we
write them under a plan somebody read".

These tests are about the REFUSALS, because that is what makes an attended
apply attended. A rail that writes correctly when everything is fine and also
writes when the plan is stale, the debt is open, or the row has drifted is not
an attended rail; it is an unattended one with a form to fill in.
"""

from __future__ import annotations

import time

import pytest

from app.tasks import repair_pm_never_graded as rail
from app.tasks.repair_pm_never_graded import (
    APPLY_MARKET_CAP,
    POPULATION_HAVING_SQL,
    WRITE_SOURCE,
    _apply_reviewed_plan,
    census,
    repair,
)
from app.utils.calibration_invalidation import new_obligation
from app.utils.repair_apply_plan import (
    REASON_PLAN_HASH_MISMATCH,
    REASON_PLAN_MISSING,
    PlannedLeg,
    build_plan,
)


# ---------------------------------------------------------------------------
# The cohort
# ---------------------------------------------------------------------------


def test_the_population_is_the_never_graded_cohort_not_the_mis_graded_one():
    """The split IS the finding. `bool_and(... IS NULL)` selects markets nothing
    ever decided; `bool_or(source = ANY(...))` would select ones a heuristic
    decided badly. They need opposite fixes and this rail does only the first."""
    assert "bool_and(fo.resolution_source IS NULL)" in POPULATION_HAVING_SQL
    assert "bool_or(fo.is_winner) IS NOT TRUE" in POPULATION_HAVING_SQL
    assert "pass2_loser" not in POPULATION_HAVING_SQL


def test_the_rail_and_the_drain_agree_about_who_is_in_the_cohort():
    """Two definitions of one cohort is how a repair writes to rows its census
    never counted. The drain's predicate is the same string."""
    from app.tasks.clob_resolve import _COHORT_NEVER_GRADED, _cohort_having

    drain = _cohort_having(_COHORT_NEVER_GRADED)
    for clause in ("bool_or(fo.is_winner) IS NOT TRUE",
                   "bool_and(fo.resolution_source IS NULL)"):
        assert clause in drain and clause in POPULATION_HAVING_SQL


def test_the_write_source_is_distinct_and_curve_eligible():
    """Revertible in ONE predicate without touching #989's cohort, and able to
    re-enter the curve — sources fail CLOSED, so an unregistered name would be
    silently curve-ineligible and the whole repair would be invisible."""
    from app.utils.resolution_authority import (
        CALIBRATION_TRUTH_ELIGIBLE_SOURCES,
        authority_tier,
        is_calibration_truth_eligible,
    )

    assert WRITE_SOURCE not in ("clob_authoritative", "clob_ordinal")
    assert authority_tier(WRITE_SOURCE) == 3
    assert is_calibration_truth_eligible(WRITE_SOURCE)
    assert WRITE_SOURCE in CALIBRATION_TRUTH_ELIGIBLE_SOURCES


def test_the_cap_is_a_module_constant_not_a_parameter():
    """"Capped" must not be dial-off-able mid-run."""
    import inspect

    assert APPLY_MARKET_CAP == 40
    assert "limit" in inspect.signature(repair).parameters
    src = inspect.getsource(repair)
    assert "min(limit or APPLY_MARKET_CAP, APPLY_MARKET_CAP)" in src


def test_the_dispatcher_can_actually_call_this_rail():
    """`routes/admin_repairs.py` calls `fn(db, apply, **extra)` — `apply` is
    POSITIONAL. A keyword-only `apply` would make the repair permanently
    un-appliable while looking perfectly correct in isolation."""
    import inspect

    for fn in (census, repair):
        params = list(inspect.signature(fn).parameters.values())
        assert params[0].name == "session"
        assert params[1].name == "apply"
        assert params[1].kind is not inspect.Parameter.KEYWORD_ONLY


def test_the_rail_is_registered_under_both_names():
    from app.routes.admin_repairs import _REPAIRS

    assert _REPAIRS["pm-never-graded-census"] == (
        "app.tasks.repair_pm_never_graded", "census")
    assert _REPAIRS["pm-never-graded"] == (
        "app.tasks.repair_pm_never_graded", "repair")


def test_the_docstring_catalog_did_not_drift_again():
    """The module docstring says in so many words that a third drift would
    prove the warning was decoration. This is that assertion."""
    import app.routes.admin_repairs as mod

    doc = mod.__doc__ or ""
    for name in mod._REPAIRS:
        assert name in doc, f"{name} missing from the docstring catalog"


# ---------------------------------------------------------------------------
# The census never writes, and an absent census is absent
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def all(self):
        return self._rows

    def first(self):
        # CAL-P076: the apply now re-reads a leg whose compare-and-set matched
        # nothing, to tell "this plan already wrote it" (a resume) from "someone
        # else moved it" (drift). No row here means not-ours, which keeps this
        # file's drift specimen a drift specimen.
        return self._rows[0] if self._rows else None


class _Row:
    def __init__(self, category, markets):
        self.category = category
        self.markets = markets


class _Session:
    def __init__(self, rows=(), raise_on_census=False):
        self.rows = rows
        self.raise_on_census = raise_on_census
        self.statements: list[str] = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.statements.append(sql)
        if "statement_timeout" in sql:
            return _Result()
        if self.raise_on_census:
            raise RuntimeError("canceling statement due to statement timeout")
        return _Result(self.rows)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_census_reports_the_whole_population_by_category():
    s = _Session([_Row("tennis", 25264), _Row("basketball", 900)])
    out = await census(s)
    assert out["measured"] is True
    assert out["total_markets"] == 26164
    assert out["by_category"]["tennis"] == 25264
    assert s.commits == 0
    assert not any(x.upper().startswith("UPDATE") for x in s.statements)


@pytest.mark.asyncio
async def test_census_is_bounded_and_a_timeout_is_absent_not_zero():
    """Gotcha #54. The entire argument for this repair rests on a population
    size; a census that dies must not report a comfortable one."""
    s = _Session(raise_on_census=True)
    out = await census(s)
    assert out["measured"] is False
    assert "census_timeout_or_error" in out["reason"]
    assert "total_markets" not in out
    assert any("statement_timeout" in x for x in s.statements)


@pytest.mark.asyncio
async def test_census_ignores_apply_and_cannot_be_switched_into_a_writer():
    s = _Session([_Row("tennis", 5)])
    out = await census(s, apply=True)
    assert out["measured"] is True
    assert s.commits == 0


# ---------------------------------------------------------------------------
# The apply refusals
# ---------------------------------------------------------------------------


def _plan(n=2):
    legs = [
        PlannedLeg(leg_id=900_000 + i, market_id=58_700_000 + (i // 2),
                   verdict="winner" if i % 2 == 0 else "loser",
                   expected_is_winner=False, expected_source=None)
        for i in range(n)
    ]
    return build_plan(legs, context={"owner": "test"})


@pytest.mark.asyncio
async def test_apply_refuses_when_there_is_no_plan(monkeypatch):
    async def _none():
        return None, REASON_PLAN_MISSING

    monkeypatch.setattr(rail, "_load_plan", _none)
    out = await _apply_reviewed_plan(_Session(), "anything", 0.0)
    assert out["wrote"] is False and out["success"] is False
    assert REASON_PLAN_MISSING in out["refused"]


@pytest.mark.asyncio
async def test_apply_refuses_a_stale_or_absent_plan_hash(monkeypatch):
    """The operator applying the page they read two pages ago."""
    plan = _plan()

    async def _load():
        return plan, "ok"

    monkeypatch.setattr(rail, "_load_plan", _load)

    for presented in (None, "", "deadbeef"):
        out = await _apply_reviewed_plan(_Session(), presented, 0.0)
        assert out["success"] is False, presented
        assert REASON_PLAN_HASH_MISMATCH in out["refused"], presented


@pytest.mark.asyncio
async def test_apply_refuses_when_the_debt_ledger_is_unreadable(monkeypatch):
    """An unreadable obligation is NOT an absence of debt. Fail closed, or the
    rail commits a second uninvalidated write on top of the first."""
    plan = _plan()

    async def _load():
        return plan, "ok"

    async def _ob():
        return None, "obligation unreadable: corrupt"

    monkeypatch.setattr(rail, "_load_plan", _load)
    monkeypatch.setattr(rail, "_load_obligation", _ob)

    out = await _apply_reviewed_plan(_Session(), plan.plan_hash, 0.0)
    assert out["success"] is False and out["wrote"] is False
    assert "OBLIGATION_LEDGER_UNREADABLE" in out["refused"]


@pytest.mark.asyncio
async def test_apply_refuses_a_new_plan_while_an_older_debt_is_open(monkeypatch):
    """CAL-P062's specimen. A retry must retry THAT plan, not start a new one
    on top of rows whose invalidation was never discharged."""
    plan = _plan()
    stale = new_obligation(plan_hash="some-other-hash", market_ids=[1],
                           leg_ids=[2], owner="prior")

    async def _load():
        return plan, "ok"

    async def _ob():
        return stale, "ok"

    monkeypatch.setattr(rail, "_load_plan", _load)
    monkeypatch.setattr(rail, "_load_obligation", _ob)

    out = await _apply_reviewed_plan(_Session(), plan.plan_hash, 0.0)
    assert out["success"] is False and out["wrote"] is False
    assert "PRIOR_OBLIGATION_OPEN_FOR_ANOTHER_PLAN" in out["refused"]
    assert out["plan_hash"] == "some-other-hash"  # the one to retry


# ---------------------------------------------------------------------------
# The write itself is compare-and-set
# ---------------------------------------------------------------------------


class _WriteSession(_Session):
    """Records UPDATEs and lets the test choose which ones 'take'."""

    def __init__(self, rowcounts):
        super().__init__()
        self.rowcounts = list(rowcounts)
        self.writes: list[tuple[str, dict]] = []
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        if sql.upper().startswith("UPDATE"):
            self.writes.append((sql, dict(params or {})))

            class _R:
                rowcount = self.rowcounts.pop(0) if self.rowcounts else 0

            return _R()
        return await super().execute(stmt, params)

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_the_write_is_compare_and_set_on_the_cohort_defining_state(
    monkeypatch,
):
    """Every leg was source-less and un-crowned when the dry-run read it. If
    that is no longer true at apply time, something else graded this market and
    we must not overwrite it — so the predicate is IN the statement, not a
    re-read before it."""
    plan = _plan(2)

    async def _load():
        return plan, "ok"

    async def _ob():
        return None, "missing"

    async def _save(_rec):
        return True, "ok"

    async def _inval(_session, _ids):
        return {"status": "invalidated"}

    monkeypatch.setattr(rail, "_load_plan", _load)
    monkeypatch.setattr(rail, "_load_obligation", _ob)
    monkeypatch.setattr(rail, "_save_obligation", _save)
    monkeypatch.setattr(
        "app.tasks.repair_kalshi_fabricated_loss.invalidate_calibration_generation",
        _inval,
    )

    s = _WriteSession([1, 1])
    out = await _apply_reviewed_plan(s, plan.plan_hash, time.monotonic())

    assert len(s.writes) == 2
    for sql, params in s.writes:
        assert "resolution_source IS NULL" in sql
        assert "is_winner IS NOT TRUE" in sql
        assert params["src"] == WRITE_SOURCE
    # Touches no prices — the repair supplies a verdict, not a number.
    assert not any("probability" in sql.lower() for sql, _ in s.writes)
    assert out["legs_written"] == 2
    assert out["success"] is True


@pytest.mark.asyncio
async def test_a_drifted_row_is_named_and_skipped_never_silently_overwritten(
    monkeypatch,
):
    plan = _plan(2)

    async def _load():
        return plan, "ok"

    async def _ob():
        return None, "missing"

    async def _save(_rec):
        return True, "ok"

    async def _inval(_session, _ids):
        return {"status": "invalidated"}

    monkeypatch.setattr(rail, "_load_plan", _load)
    monkeypatch.setattr(rail, "_load_obligation", _ob)
    monkeypatch.setattr(rail, "_save_obligation", _save)
    monkeypatch.setattr(
        "app.tasks.repair_kalshi_fabricated_loss.invalidate_calibration_generation",
        _inval,
    )

    s = _WriteSession([1, 0])  # second leg drifted
    out = await _apply_reviewed_plan(s, plan.plan_hash, time.monotonic())

    assert out["legs_written"] == 1
    assert out["legs_drifted"] == 1
    assert out["drift_reason"] == "CONCURRENT_ROW_DRIFT"
    assert s.rollbacks >= 1


@pytest.mark.asyncio
async def test_a_failed_invalidation_is_an_honest_false_with_rows_committed(
    monkeypatch,
):
    """The state CAL-P062 exists for. Rows are committed and the debt is
    persisted; the caller must retry the SAME plan_hash rather than re-plan."""
    plan = _plan(2)
    saved: list[dict] = []

    async def _load():
        return plan, "ok"

    async def _ob():
        return None, "missing"

    async def _save(rec):
        saved.append(rec)
        return True, "ok"

    async def _inval(_session, _ids):
        return {"status": "publish_failed"}

    monkeypatch.setattr(rail, "_load_plan", _load)
    monkeypatch.setattr(rail, "_load_obligation", _ob)
    monkeypatch.setattr(rail, "_save_obligation", _save)
    monkeypatch.setattr(
        "app.tasks.repair_kalshi_fabricated_loss.invalidate_calibration_generation",
        _inval,
    )

    s = _WriteSession([1, 1])
    out = await _apply_reviewed_plan(s, plan.plan_hash, time.monotonic())

    assert out["legs_written"] == 2      # the rows ARE committed
    assert out["success"] is False       # and the run says so
    assert out["invalidation_discharged"] is False
    assert "RETRY THE SAME plan_hash" in (out["note"] or "")
    # The debt was persisted BEFORE the invalidation was attempted.
    assert saved and saved[0]["state"] == "open"
    assert saved[0]["plan_hash"] == plan.plan_hash
