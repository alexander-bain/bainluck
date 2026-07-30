"""Queue #284 Item 2 — resolved markets are frozen in the rolling shape beat.

A resolved market's shape determines its calibration cohort. The unattended
every-20-min recompute must NOT re-shape a settled row (that would move it
between published calibration cohorts with no version bump or review). What a
resolved-row recompute WOULD change is inspectable via a dry-run-ONLY census that
never writes a market or calibration row.
"""

import inspect

import pytest

from app.tasks.backfill_market_shapes import (
    _backfill_market_shapes,
    census_resolved_market_shapes,
)


# --- the unattended beat freezes resolved rows -----------------------------

def test_beat_excludes_resolved_rows():
    """The every-20-min sweep's driving SELECT skips resolved markets."""
    src = inspect.getsource(_backfill_market_shapes)
    assert "status IS DISTINCT FROM 'resolved'" in src, (
        "the rolling shape beat must exclude status='resolved' rows so an "
        "unattended recompute cannot move a settled market between calibration "
        "cohorts (#284 Item 2)"
    )


def test_beat_still_converges_open_rows():
    """The beat must NOT restrict itself to resolved rows — open/other rows still
    recompute (IS DISTINCT FROM keeps NULL-status rows in the sweep too)."""
    src = inspect.getsource(_backfill_market_shapes)
    assert "status = 'resolved'" not in src, (
        "the beat must exclude resolved rows, not restrict to them"
    )


# --- the census is write-free ----------------------------------------------

def test_census_is_write_free_and_dry_run_by_contract():
    src = inspect.getsource(census_resolved_market_shapes)
    upper = src.upper()
    assert "UPDATE FUTURES_MARKETS" not in upper
    assert "UPDATE FUTURES_OUTCOMES" not in upper
    assert "INSERT" not in upper and "DELETE FROM" not in upper
    # it inspects ONLY resolved rows
    assert "status = 'resolved'" in src


def test_census_does_not_bump_population_version():
    """No resolved rewrite ships in this queue, so CALIBRATION_POPULATION_VERSION
    is unchanged — the census only REPORTS that a future apply would require one."""
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

    assert CALIBRATION_POPULATION_VERSION == "q267"


# --- functional census run (mocked session + redis) ------------------------

class _Res:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _CensusSession:
    """Dispatches the census's read queries by SQL text; captures every stmt."""

    def __init__(self, market_rows):
        self._market_rows = market_rows
        self.executed = []

    async def execute(self, stmt, params=None):
        t = str(stmt)
        self.executed.append(t)
        if "COUNT(DISTINCT market_id)" in t:
            return _Res(scalar=1)
        if "GROUP BY group_id" in t:
            return _Res(rows=[])
        if "FROM futures_outcomes" in t:
            return _Res(rows=[(1, "Yes"), (1, "No"), (2, "Yes"), (2, "No")])
        if "FROM futures_markets" in t:
            # First page (cursor 0) yields the resolved rows; then empty → wrap.
            if not params or params.get("cursor", 0) == 0:
                return _Res(rows=self._market_rows)
            return _Res(rows=[])
        return _Res(rows=[])


class _FakeRedis:
    def get(self, key):
        return None

    def setex(self, key, ttl, value):
        return None

    def delete(self, key):
        return None


@pytest.mark.asyncio
async def test_census_reports_transitions_membership_and_bump(monkeypatch):
    monkeypatch.setattr(
        "app.tasks.backfill_market_shapes.get_redis_client",
        lambda *a, **k: _FakeRedis(),
    )

    # (id, source, external_id, event_id, group_id, group_type,
    #  mutually_exclusive, market_type, market_metadata)
    market_rows = [
        (1, "polymarket", "0xabc_yes", None, None, None, None, "duel", {}),
        (2, "kalshi", "KX-TEST", None, None, None, None, "field", {}),
    ]
    session = _CensusSession(market_rows)

    census = await census_resolved_market_shapes(session, apply=True)

    # Dry-run by contract even when apply=True is passed.
    assert census["mode"] == "dry_run"
    assert census["applied"] is False

    assert census["scanned"] == 2
    assert census["changed"] == 2  # both ["Yes","No"] resolved rows reshape → claim
    assert census["transitions"] == {"duel->claim": 1, "field->claim": 1}
    assert census["affected_published_membership"] == 1
    assert census["requires_population_version_bump"] is True
    assert census["current_population_version"] == "q267"

    # It NEVER issued a mutating statement.
    assert all(
        "UPDATE " not in t.upper() and "DELETE " not in t.upper()
        for t in session.executed
    ), session.executed


@pytest.mark.asyncio
async def test_census_no_changes_needs_no_bump(monkeypatch):
    """An empty resolved set (or none changed) reports no required version bump."""
    monkeypatch.setattr(
        "app.tasks.backfill_market_shapes.get_redis_client",
        lambda *a, **k: _FakeRedis(),
    )

    session = _CensusSession([])  # no resolved rows at all
    census = await census_resolved_market_shapes(session, apply=False)

    assert census["scanned"] == 0
    assert census["changed"] == 0
    assert census["affected_published_membership"] == 0
    assert census["requires_population_version_bump"] is False
