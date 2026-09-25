"""#8692 — the golf move's basis bounds, pinned without a database.

The real guard is `tests/integration/test_golf_move_basis_between_rounds_8692_pg.py`
(production's Fitzpatrick rows through the shipped SQL on Postgres). This file runs
in every shard and pins what that gate is graded against: the two instants the
query is bound with, and that the measured between-round silence fits inside them.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.routes import golf as golf_route
from app.routes.golf import MOVE_BASIS_MAX_AGE, MOVE_BASIS_MIN_AGE, _fetch_24h_snapshots

NOW = datetime(2026, 9, 25, 19, 25, tzinfo=timezone.utc)


class _Row:
    def __init__(self, outcome_id, probability):
        self.outcome_id = outcome_id
        self.probability = probability


class _RecordingDb:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def execute(self, stmt, params=None):
        self.calls.append((stmt, params))
        return iter(self.rows)


async def test_the_query_is_bound_at_now_minus_23h_and_now_minus_36h():
    db = _RecordingDb([_Row(232672440, "0.169124")])
    got = await _fetch_24h_snapshots(db, [232672440, 231407113], NOW)
    assert got == {232672440: pytest.approx(0.169124)}
    ((stmt, params),) = db.calls
    assert stmt is golf_route._MOVE_BASIS_SQL
    assert params == {
        "outcome_ids": [232672440, 231407113],
        "newest": NOW - timedelta(hours=23),
        "oldest": NOW - timedelta(hours=36),
    }


async def test_no_outcomes_asks_nothing():
    db = _RecordingDb([])
    assert await _fetch_24h_snapshots(db, [], NOW) == {}
    assert db.calls == []


def test_the_cap_covers_the_measured_between_round_silence_and_no_more():
    """DataGolf's longest between-round silence on production was 13h
    (9/24 17:58Z → 9/25 06:51Z); a basis older than 36h is not "today"."""
    silence = datetime(2026, 9, 25, 6, 51, tzinfo=timezone.utc) - datetime(
        2026, 9, 24, 17, 58, tzinfo=timezone.utc
    )
    assert MOVE_BASIS_MIN_AGE == timedelta(hours=23)
    assert MOVE_BASIS_MIN_AGE + silence <= MOVE_BASIS_MAX_AGE == timedelta(hours=36)
