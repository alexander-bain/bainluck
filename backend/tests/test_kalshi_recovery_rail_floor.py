"""CAL-P009 (#651) — "oldest-first" needs a floor, or it never reaches the edge.

CAL-P008 measured Kalshi's retention: markets settled more than ~86 days ago are
gone (404 / 200-with-zero), markets settled inside ~74 days are fully retrievable.
This suite holds the consequence for the two rails that were still unbounded.

The sharpest case is `_backfill_kalshi_price_history`. Queue #152 deliberately
inverted its sort to oldest-resolved-first, with a comment saying it did so "to
harvest the 2-3mo EDGE cohort before it crosses the cliff". The intent was right
and the sort was right — but with no lower bound, oldest-first starts at rows that
crossed the cliff MONTHS ago and never arrives at the edge it was written to save.
That is the failure these tests pin: not a wrong order, a missing floor.

`_backfill_candlestick_snapshots` had no age bound at all. Its own cursor comment
already blames "the api_empty cohort PAST the ~2-3mo cliff" for starving later
series, and answers it with a rotation — which makes the starvation survivable
rather than stopping it being generated.
"""

from __future__ import annotations

import inspect
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from app.tasks.kalshi import (
    _backfill_candlestick_snapshots,
    _backfill_kalshi_price_history,
    _backfill_trade_history,
)
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS, is_provably_purged

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)

#: Every Kalshi rail that spends an API budget recovering historical prices.
BOUNDED_RAILS = (
    _backfill_trade_history,            # bounded by CAL-P008
    _backfill_candlestick_snapshots,    # bounded here
    _backfill_kalshi_price_history,     # bounded here
)


def _bounded_sql(fn) -> list[str]:
    """Every SELECT in `fn` that carries the purge bound."""
    src = inspect.getsource(fn)
    return [
        m.group(1).replace("%%", "%")
        for m in re.finditer(r'text\("""\s*(SELECT.*?)"""\)', src, re.S)
        if "purge_days" in m.group(1)
    ]


class TestEveryRecoveryRailIsBounded:
    """One horizon, applied everywhere, or the rails disagree about when data dies."""

    @pytest.mark.parametrize("fn", BOUNDED_RAILS, ids=lambda f: f.__name__)
    def test_rail_bounds_its_candidates_on_the_measured_horizon(self, fn):
        bounded = _bounded_sql(fn)
        assert bounded, f"{fn.__name__} selects candidates with no retention floor"
        for sql in bounded:
            assert "make_interval(days => :purge_days)" in sql

    @pytest.mark.parametrize("fn", BOUNDED_RAILS, ids=lambda f: f.__name__)
    def test_the_bound_is_the_shared_constant_not_a_local_number(self, fn):
        src = inspect.getsource(fn)
        assert "PROVABLY_PURGED_AGE_DAYS" in src
        # No hand-rolled day counts competing with the measured constant.
        assert "interval '90 days'" not in src
        assert "INTERVAL '90 days'" not in src

    @pytest.mark.parametrize("fn", BOUNDED_RAILS, ids=lambda f: f.__name__)
    def test_the_bind_survives_and_the_sql_compiles(self, fn):
        """The `:param::cast` drop class, which this repo has shipped before."""
        for sql in _bounded_sql(fn):
            stmt = text(sql)
            assert "purge_days" in stmt._bindparams
            stmt.compile(dialect=postgresql.dialect(paramstyle="numeric"))

    @pytest.mark.parametrize("fn", BOUNDED_RAILS, ids=lambda f: f.__name__)
    def test_null_settlement_dates_stay_candidates(self, fn):
        """Fail-open. A row we cannot date must be tried, never written off."""
        for sql in _bounded_sql(fn):
            window = sql[sql.index("purge_days") - 400 : sql.index("purge_days")]
            assert "IS NULL" in window, (
                f"{fn.__name__}: the retention bound has no NULL escape — dateless "
                "rows would be silently abandoned"
            )


class TestOldestFirstIsKeptInsideTheWindow:
    """The floor fixes #152's sort; it must not undo it."""

    def test_price_history_still_orders_oldest_resolved_first(self):
        src = inspect.getsource(_backfill_kalshi_price_history)
        assert "ORDER BY fm.resolution_date ASC NULLS LAST" in src

    def test_ordering_and_floor_appear_in_the_same_query(self):
        """Oldest-first on an unbounded set is the bug; together they are the fix."""
        bounded = _bounded_sql(_backfill_kalshi_price_history)
        assert any("ORDER BY fm.resolution_date ASC" in sql for sql in bounded)


class TestTheSelectionDefectItself:
    """Pure reproduction of what production did, independent of any SQL text.

    This is the non-vacuous core: given the real cohort's age distribution, an
    unbounded oldest-first selection returns only permanently-dead rows, and a
    bounded one returns exactly the rows that still have data.
    """

    # Ages measured against live Kalshi on 2026-08-07 (CAL-P008).
    COHORT = [
        ("KXNCAAMBSPREAD-26MAR07CINTCU-CIN7", 154),   # 404
        ("KXMLBHIT-26APR121610HOUSEA-SEACRALEIGH29-3", 117),  # 404
        ("KXMLBTB-26MAY131840COLPIT-COLTRUMFIELD64-3", 86),   # 404
        ("KXHIGHTBOS-26JUN27-T74", 41),               # 200, 100 trades
        ("KXDOTA2MAP-26JUL081000NEMTS-1-NEM", 30),    # 200, 100 trades
    ]

    def _rows(self):
        return [(t, NOW - timedelta(days=age)) for t, age in self.COHORT]

    def _select(self, rows, limit, bounded):
        candidates = [
            (t, d) for t, d in rows
            if not (bounded and is_provably_purged(d, NOW))
        ]
        candidates.sort(key=lambda r: r[1])  # oldest-resolved first (#152)
        return [t for t, _ in candidates[:limit]]

    def test_unbounded_oldest_first_returns_only_dead_rows(self):
        """Exactly the production failure: a full budget, zero recoverable rows."""
        picked = self._select(self._rows(), limit=3, bounded=False)
        assert picked == [
            "KXNCAAMBSPREAD-26MAR07CINTCU-CIN7",
            "KXMLBHIT-26APR121610HOUSEA-SEACRALEIGH29-3",
            "KXMLBTB-26MAY131840COLPIT-COLTRUMFIELD64-3",
        ]
        ages = dict(self.COHORT)
        assert all(ages[t] >= PROVABLY_PURGED_AGE_DAYS for t in picked)

    def test_bounded_oldest_first_returns_only_recoverable_rows(self):
        picked = self._select(self._rows(), limit=3, bounded=True)
        assert picked == ["KXHIGHTBOS-26JUN27-T74", "KXDOTA2MAP-26JUL081000NEMTS-1-NEM"]

    def test_the_edge_row_is_served_before_the_safe_one(self):
        """#152's intent, now actually achievable: closest to expiry goes first."""
        picked = self._select(self._rows(), limit=1, bounded=True)
        assert picked == ["KXHIGHTBOS-26JUN27-T74"]

    def test_a_dateless_row_is_never_dropped(self):
        rows = self._rows() + [("KXNODATE-FOO", None)]
        candidates = [
            t for t, d in rows if not is_provably_purged(d, NOW)
        ]
        assert "KXNODATE-FOO" in candidates
