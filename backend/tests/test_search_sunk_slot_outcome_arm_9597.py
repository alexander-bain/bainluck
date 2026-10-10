"""#9597 — the sunk-slot outcome arm's gate and its session discipline.

The route behaviour is pinned on a real database in
`tests/integration/test_search_sunk_slot_outcome_arm_9597_pg.py`; this file pins
the two things that do not need one: WHEN the arm may run (every other page must
pay nothing), and that its shed path never rolls the session back while
`deduped_futures` is live (gotcha #6, LAT-P255/#3731).
"""

from __future__ import annotations

import inspect
import time

import pytest

from app.routes import events as events_route
from app.routes.events import _SEARCH_FUTURES_PAGE, _needs_sunk_slot_outcome_arm


@pytest.mark.parametrize(
    "arm_state, answer_rows, over_cap, expected",
    [
        ("skipped", 4, {1}, True),  # the specimen: `red sox`
        ("skipped", _SEARCH_FUTURES_PAGE - 1, {1}, True),
        ("skipped", _SEARCH_FUTURES_PAGE, {1}, False),  # sunk rows never ship
        ("skipped", 4, set(), False),  # nothing was sunk
        ("merged", 4, {1}, False),  # the arm already ran
        ("absent", 4, {1}, False),
        ("shed", 4, {1}, False),
        ("budget_exceeded", 4, {1}, False),
        ("not_reached", 4, {1}, False),
    ],
)
def test_the_gate(arm_state, answer_rows, over_cap, expected):
    assert _needs_sunk_slot_outcome_arm(arm_state, answer_rows, over_cap) is expected


def test_the_fetch_uses_a_savepoint_and_never_a_session_rollback():
    src = inspect.getsource(events_route._fetch_sunk_slot_outcome_rows)
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    assert "await db.begin_nested()" in code
    assert "_recover_search_session" not in code
    assert "db.rollback(" not in code


class _CapturingSession:
    """Records every statement; answers each with no rows."""

    def __init__(self):
        self.statements = []

    async def execute(self, stmt, *args, **kwargs):
        self.statements.append(stmt)

        class _Result:
            def scalars(self):
                return self

            def unique(self):
                return self

            def all(self):
                return []

        return _Result()

    async def begin_nested(self):
        class _Savepoint:
            async def commit(self):
                pass

            async def rollback(self):
                pass

        return _Savepoint()


async def _sunk_slot_sql():
    """The arm's statement as Postgres receives it, over a stand-in window."""
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    from app.models.models import FuturesMarket

    db = _CapturingSession()
    rows, state = await events_route._fetch_sunk_slot_outcome_rows(
        db,
        lambda flt: select(FuturesMarket.id).where(flt, FuturesMarket.status == "open"),
        [FuturesMarket.name.ilike("%rangers%"),
         FuturesMarket.external_id.like("kxmlb%")],
        events_route._market_has_outcome(
            events_route.FuturesOutcome.name.ilike("%rangers%")
        ),
        time.monotonic() + 5,
    )
    assert (rows, state) == ([], "merged")
    window = [
        s for s in db.statements if "futures_markets" in str(s)
    ]
    assert len(window) == 1, db.statements
    return str(window[0].compile(dialect=postgresql.dialect()))


async def test_the_fetch_excludes_the_name_arms():
    """Without the exclusion the window's name-tier-first order returns the
    props whose OUTCOMES name the club, and no outcome-only row (the pg mutant)."""
    sql = await _sunk_slot_sql()
    assert "IS NOT true" in sql
    assert "futures_markets.name ILIKE" in sql
    assert "futures_markets.external_id" in sql


async def test_the_name_arms_are_tested_on_the_row_10803():
    """#10803: no candidate SET is built for either side. `NOT IN (UNION ...)`
    scanned 5,804 `rangers` name matches to drop them from ~39 rows, and the
    `IN (SELECT id ...)` self-join was its twin. Row-for-row identity with the
    old form is pinned on Postgres in
    `integration/test_search_sunk_slot_identity_10803_pg.py`."""
    sql = await _sunk_slot_sql()
    assert "NOT IN" not in sql
    assert "futures_markets.id IN" not in sql
    assert "UNION" not in sql


def test_the_route_reports_the_arm_state():
    src = inspect.getsource(events_route.search_events)
    assert '"futures_sunk_slot_arm": _futures_sunk_slot_arm' in src
    # The gate is counted fresh: an over-cap row is not an answer here.
    start = src.index("if _needs_sunk_slot_outcome_arm(")
    gate = src[start:src.index("_fetch_sunk_slot_outcome_rows(", start)]
    assert "m.id not in _over_match_cap_ids" in gate
