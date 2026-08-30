"""LAT-P147 (#2328) — the top-1 observation loader, and the two ways it can lie.

## what shipped

`/api/tournaments/us-open` asked *when was each pinned outcome last observed?*
with `max(captured_at) ... GROUP BY outcome_id`. An aggregate cannot skip, so on
the register's 514 outcomes PostgreSQL read **342,059 index tuples and 175,754
buffer blocks to return 514 numbers** — 87-93% of the page's whole cold build,
and the reason the same statement cost 3.6 s one minute and 11.9 s the next.

`app.utils.latest_observation` asks it as one top-1 index probe per outcome.
Measured on production, same 514 ids, same minute: **1,766 ms -> 118 ms**,
**175,754 -> 3,407 buffer blocks**, **514 rows, 0 diffs**.

## 🔴 why these guards assert on RENDERED SQL rather than on rows

Neither of the two ways this rewrite can be wrong is reachable by a test that
executes rows in this suite, and pretending otherwise would ship a false green.

* **`captured_at IS NOT NULL`.** `ORDER BY x DESC` is `NULLS FIRST` in
  PostgreSQL, so without this predicate an outcome holding one NULL-`captured_at`
  row reports `None` where `max()` reports its real newest observation. **SQLite
  sorts the other way** — `[3, 1, None]` for `ORDER BY x DESC`, verified — so a
  SQLite behavioural test passes whether the predicate is there or not. It would
  be a green that means nothing.

* **A real-PostgreSQL gate cannot reach it either**, which is the sharper half.
  The column is nullable *in the deployed database* (`information_schema` says
  `is_nullable = YES`, production 2026-08-30) while the model declares
  `captured_at: Mapped[datetime]`. **The model and the deployed schema
  disagree.** Any gate built from `Base.metadata.create_all` — which is how both
  real-Postgres gates in this repo build their schema — emits a `NOT NULL`
  column and physically cannot hold the row that breaks the query. The oracle
  would refuse the input.

So the artifact under test is the statement AS POSTGRESQL RECEIVES IT, compiled
against the postgresql dialect. That string is what ran in the production
measurement above; asserting on it is asserting on the thing that was measured.
The `latest_observation` docstring carries the numbers.

## the second trap, which is why `NULLS LAST` is banned rather than preferred

`ORDER BY captured_at DESC NULLS LAST` is the spelling a later reader will reach
for, because it looks like the safe one and makes the predicate seem redundant.
It is answer-identical and **19x slower** — it does not match the index's own
ordering, so each probe stops being a one-row backward scan and becomes a Sort
over the whole group. Measured, same population, same minute:

    DESC (NULLS FIRST) + IS NOT NULL     124 ms    3,503 buffer blocks
    DESC NULLS LAST    + IS NOT NULL   2,408 ms  177,719 buffer blocks

That is the aggregate's cost back again wearing a safer-looking clause, so the
clause is a test failure and not a review comment.
"""

from __future__ import annotations

import inspect
import re

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models import FuturesOutcome
from app.utils.latest_observation import (
    latest_observed_at_subquery,
    load_latest_observed_at,
)

# No module-level `pytest.mark.asyncio`: `pytest.ini` runs asyncio in AUTO mode,
# and a blanket mark decorates the sync shape-assertions too, which pytest warns
# about twelve times. The async tests here need no mark at all.


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _rendered(ids=(1, 2, 3)) -> str:
    """The statement `load_latest_observed_at` issues, as PostgreSQL sees it.

    Built from the SHIPPED subquery rather than typed out here. A copy would be
    a self-oracle: it would keep proving that a string in a test file has the
    right shape while the module drifted away from it.
    """
    stmt = select(
        FuturesOutcome.id, latest_observed_at_subquery().label("observed_at")
    ).where(FuturesOutcome.id.in_(list(ids)))
    compiled = stmt.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return " ".join(str(compiled).split())


class _Rows:
    """What `session.execute(...)` returns: an object with `.all()`."""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Row:
    """A result row addressed by attribute, the way the loaders read them.

    🔴 A COLUMN THIS TEST DID NOT SET READS AS `None`, NOT AS AN AttributeError,
    and that is the point rather than a convenience. A real SQLAlchemy `Row`
    carries whatever the SELECT asked for, and `_load_prices`'s SELECT is a
    SHARED one — the ux stack adds `current_yes_bid`, `volume_24h` and
    `volume_updated_at` to it for a liquidity mark. A strict double turns "a
    sibling branch selected one more column" into five red tests in a file that
    has no opinion about liquidity, which is a test claiming ownership of a
    statement it merely borrows.

    Found by RUNNING the three-way merge against
    `program/ux-135-raw-category-keys` rather than reading it: the strict version
    of this class died five times with
    `AttributeError: '_Row' object has no attribute 'current_yes_bid'`.

    The columns this file DOES assert on are set explicitly and checked by value,
    so a typo surfaces as a wrong answer rather than a silent `None`.
    """

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return None


class _RecordingSession:
    """Captures every statement without touching a database."""

    def __init__(self, results=()):
        self.executed: list[object] = []
        self._results = list(results)

    async def execute(self, statement, params=None):
        self.executed.append(statement)
        if self._results:
            return self._results.pop(0)
        return _Rows([])

    def rendered(self) -> list[str]:
        return [
            " ".join(
                str(
                    s.compile(
                        dialect=postgresql.dialect(),
                        compile_kwargs={"literal_binds": True},
                    )
                ).split()
            )
            for s in self.executed
        ]


# --------------------------------------------------------------------------
# A. the statement's shape — the artifact that was measured
# --------------------------------------------------------------------------


class TestTheStatementPostgresReceives:
    def test_the_null_captured_at_predicate_is_present(self):
        """The one that makes this answer-identical to `max()`. See module doc."""
        assert (
            "futures_odds_snapshots.captured_at IS NOT NULL" in _rendered()
        ), "without this predicate a NULL captured_at wins its own group under DESC"

    def test_the_priced_predicate_is_present(self):
        """Dead today (schema NOT NULL) and carried anyway — it is the question.

        PostgreSQL removes it during planning, so it appears in the plan of
        neither form and costs nothing. It is the difference between right and
        wrong on the day `probability` becomes nullable.
        """
        assert "futures_odds_snapshots.probability IS NOT NULL" in _rendered()

    def test_the_order_is_newest_first(self):
        assert "ORDER BY futures_odds_snapshots.captured_at DESC" in _rendered()

    def test_no_explicit_nulls_clause(self):
        """`NULLS LAST` is 19x slower — the module docstring carries the numbers.

        Banned outright rather than "preferred against", because the failure is
        invisible: the answer stays correct and only the plan changes, so
        nothing but a measurement or this assertion can catch it.
        """
        rendered = _rendered()
        assert "NULLS LAST" not in rendered.upper()
        assert "NULLS FIRST" not in rendered.upper()

    def test_it_takes_exactly_one_row_per_outcome(self):
        assert re.search(r"LIMIT 1\b", _rendered())

    def test_it_is_correlated_to_the_outer_outcome(self):
        """A correlation that does not happen is a cross join wearing a LIMIT.

        Two assertions, because the join predicate alone does not prove it: with
        correlation switched off SQLAlchemy keeps the predicate and adds
        `futures_outcomes` to the SUBQUERY's own `FROM`, which is the whole
        product bounded to one row — right answer by luck on this shape, and an
        unbounded scan the moment the outer query changes.

        🔴 Note for a later reader: `.correlate(FuturesOutcome)` in the module is
        NOT what these assertions pin, and no mutant claims otherwise — removing
        it renders byte-identically, because SQLAlchemy auto-correlates here. It
        is kept as a statement of intent that survives a change to the outer
        query; `.correlate(None)` is the edit these two catch.
        """
        rendered = _rendered()
        assert "futures_odds_snapshots.outcome_id = futures_outcomes.id" in rendered
        assert "FROM futures_odds_snapshots WHERE" in rendered, rendered

    def test_the_aggregate_has_not_come_back(self):
        """The regression this whole ship exists to prevent."""
        rendered = _rendered().upper()
        assert "MAX(" not in rendered
        assert "GROUP BY" not in rendered

    def test_it_reads_the_snapshot_table_exactly_once(self):
        """A self-join would reintroduce the volume by another route."""
        assert _rendered().count("FROM futures_odds_snapshots") == 1

    # 🔴 The id bound is NOT asserted here, and the omission is deliberate.
    # `_rendered()` supplies its own `.where(...)`, so an assertion about the
    # bound in this class would be checking the test helper rather than the
    # module — a self-oracle. It survived M13 for exactly that reason. The real
    # one drives `load_latest_observed_at` and lives in `TestTheMappingItReturns`
    # below.


# --------------------------------------------------------------------------
# B. the mapping contract
# --------------------------------------------------------------------------


class TestTheMappingItReturns:
    async def test_no_ids_short_circuits_without_touching_the_session(self):
        session = _RecordingSession()
        assert await load_latest_observed_at(session, []) == {}
        assert session.executed == []

    async def test_an_unobserved_outcome_is_ABSENT_not_present_with_none(self):
        """The aggregate's shape, and callers depend on it.

        `.get(id)` yields `None` either way, but a caller that iterates or counts
        the mapping would silently start seeing outcomes never observed at all.
        """
        session = _RecordingSession(
            [_Rows([_Row(id=11, observed_at="T1"), _Row(id=12, observed_at=None)])]
        )
        got = await load_latest_observed_at(session, [11, 12])
        assert got == {11: "T1"}
        assert 12 not in got

    async def test_values_are_keyed_by_outcome_id(self):
        session = _RecordingSession(
            [_Rows([_Row(id=11, observed_at="T1"), _Row(id=12, observed_at="T2")])]
        )
        assert await load_latest_observed_at(session, [11, 12]) == {
            11: "T1",
            12: "T2",
        }

    async def test_a_generator_of_ids_is_accepted_and_not_consumed_twice(self):
        """`if not outcome_ids` on a generator is always False, and iterating it
        twice yields nothing the second time. Materialised once, deliberately."""
        session = _RecordingSession([_Rows([_Row(id=11, observed_at="T1")])])
        assert await load_latest_observed_at(session, (i for i in [11])) == {
            11: "T1"
        }
        assert len(session.executed) == 1

    async def test_an_empty_generator_is_the_empty_case_not_a_query(self):
        session = _RecordingSession()
        assert await load_latest_observed_at(session, (i for i in [])) == {}
        assert session.executed == []

    async def test_the_statement_it_issues_is_bounded_by_the_ids(self):
        """The probes are only cheap because something bounds how many run.

        Driven, not reconstructed: this renders what `load_latest_observed_at`
        ACTUALLY handed the session. The reconstructed version of this assertion
        supplied its own `WHERE` and let M13 — dropping the bound from the
        module, so the outer scan becomes one probe per outcome in the whole
        table — survive the battery.
        """
        session = _RecordingSession([_Rows([])])
        await load_latest_observed_at(session, [7, 8])
        issued = session.rendered()[0]
        assert "futures_outcomes.id IN (7, 8)" in issued, issued

    async def test_one_round_trip_not_one_per_outcome(self):
        """The probes are PostgreSQL's, not Python's. A per-id loop here would
        turn 514 index probes into 514 network round trips."""
        session = _RecordingSession([_Rows([])])
        await load_latest_observed_at(session, list(range(50)))
        assert len(session.executed) == 1


# --------------------------------------------------------------------------
# C. the route actually uses it — driven, not re-implemented
# --------------------------------------------------------------------------


class TestTheRouteIssuesIt:
    """Drives the real `_load_prices`. A test that rebuilt the statement itself
    would keep passing while the route went back to the aggregate."""

    @staticmethod
    def _session():
        return _RecordingSession(
            [
                _Rows(
                    [
                        _Row(
                            id=11,
                            name="Alcaraz",
                            current_probability=0.25,
                            opening_probability=0.20,
                        )
                    ]
                ),
                _Rows([_Row(id=11, observed_at="2026-08-30T00:00:00+00:00")]),
            ]
        )

    async def test_it_issues_exactly_two_statements(self):
        from app.routes import tournaments

        session = self._session()
        await tournaments._load_prices(session, [11])
        assert len(session.executed) == 2, session.rendered()

    async def test_neither_statement_aggregates(self):
        from app.routes import tournaments

        session = self._session()
        await tournaments._load_prices(session, [11])
        for rendered in session.rendered():
            upper = rendered.upper()
            assert "GROUP BY" not in upper, rendered
            assert "MAX(" not in upper, rendered

    async def test_the_second_statement_is_the_top_one_probe(self):
        from app.routes import tournaments

        session = self._session()
        await tournaments._load_prices(session, [11])
        second = session.rendered()[1]
        assert "LIMIT 1" in second
        assert "futures_odds_snapshots.captured_at IS NOT NULL" in second

    async def test_the_observed_time_reaches_the_payload(self):
        """The loader is wired to the field a reader sees, not just called."""
        from app.routes import tournaments

        prices = await tournaments._load_prices(self._session(), [11])
        assert prices[11]["observed_at"] == "2026-08-30T00:00:00+00:00"
        assert prices[11]["source_name"] == "Alcaraz"
        assert prices[11]["probability"] == pytest.approx(0.25)

    async def test_an_unobserved_outcome_reports_none_not_a_missing_key(self):
        """`observed_at` is a key every price carries; only its value goes None."""
        from app.routes import tournaments

        session = _RecordingSession(
            [
                _Rows(
                    [
                        _Row(
                            id=11,
                            name="Alcaraz",
                            current_probability=None,
                            opening_probability=None,
                        )
                    ]
                ),
                _Rows([_Row(id=11, observed_at=None)]),
            ]
        )
        prices = await tournaments._load_prices(session, [11])
        assert prices[11]["observed_at"] is None
        assert prices[11]["probability"] is None

    async def test_no_ids_issues_nothing(self):
        from app.routes import tournaments

        session = _RecordingSession()
        assert await tournaments._load_prices(session, []) == {}
        assert session.executed == []


# --------------------------------------------------------------------------
# D. one statement, one home
# --------------------------------------------------------------------------


class TestItIsShared:
    def test_the_route_delegates_rather_than_holding_its_own_copy(self):
        """Ruling 005. A second copy of this statement is a second thing to fix
        the next time the shape is wrong — and this one was wrong for months."""
        from app.routes import tournaments

        source = inspect.getsource(tournaments._load_prices)
        assert "load_latest_observed_at" in source
        assert "group_by" not in source

    def test_the_series_loader_was_left_alone(self):
        """`_load_series` is a different question (a daily mean over a window)
        and measured 310 ms. It is bounded by `MAX_SERIES_ROWS` and a cutoff, and
        this ship did not touch it — pinned so a later 'consistency' pass does
        not convert it to probes it has no use for."""
        from app.routes import tournaments

        source = inspect.getsource(tournaments._load_series)
        assert "date_trunc" in source
        assert "TREND_DAYS" in source
        assert "MAX_SERIES_ROWS" in source
