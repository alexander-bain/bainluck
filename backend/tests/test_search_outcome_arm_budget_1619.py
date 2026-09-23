"""LAT-P271 / #1619 — `/api/events/search`'s futures OUTCOME arm has its own budget,
and blowing it costs the reader the arm, never the whole futures bucket.

WHAT WAS WRONG. Every bound on this route is derived from the 20 s request
deadline, so the arm's `statement_timeout` was *whatever was left of 20 s* — a
residual, not a limit — and the reader waits out the residual. Measured on
production 2026-09-23 with `?debug_timing=1`, `stanley cup` interleaved as the
control, futures-stage ms with the arm merged:

    healthy        us recession 2026 114 · super bowl winner 139 · world cup
                   winner 173 · tour de france 176 · masters winner 204
    pathological   f1 winner 2,490 and 4,309 · f1 champion 3,170

`f1 winner` answered in 2.8 s and 4.6 s of wall clock. Its outcome arm returned
**0 rows in 1,318 ms** in production SQL: the entire wait bought nothing.

THE TWO FAILURE MODES THIS SUITE IS AIMED AT, both of which are invisible:

1. **A bound quietly widened back to the residual.** `_SEARCH_MIN_STAGE_TIMEOUT_MS`
   is 2,000 ms and this budget is 1,000 ms, so any future edit that routes the
   arm's bound through the stage floor — the obvious tidy-up, since every other
   bound on the route goes through it — either doubles the bound or, read as
   "below the floor ⇒ shed", sheds the arm on every request. Both look like a
   working fix from outside.
2. **Returning expired ORM rows.** A `statement_timeout` cancellation aborts the
   transaction, so recovery must roll back (gotcha #6: async rollback expires
   every ORM object the session holds). Rows fetched *before* that rollback
   cannot be handed to the serialiser; they must be re-read. A test that only
   checks the row IDs would pass on rows that raise the moment anything renders
   them, so the fake below marks post-rollback rows and the assertion is on the
   MARK, not on the ids.

The suite drives the real `_fetch_futures_window` against a model of the ORDER BY,
the same way `test_search_futures_tier_split.py` does, because the seeded CI
database cannot make a query slow enough to exercise any of this.
"""

from __future__ import annotations

import pytest

from app.routes import events as events_module
from app.routes.events import (
    _SEARCH_FUTURES_WINDOW,
    _SEARCH_MIN_STAGE_TIMEOUT_MS,
    _SEARCH_OUTCOME_ARM_TIMEOUT_MS,
    _fetch_futures_window,
    _search_outcome_arm_bound_ms,
)

WINDOW = _SEARCH_FUTURES_WINDOW
TIER1_ARMS = ["name", "ticker", "alias"]
OUTCOME_ARM = "outcome"


class QueryCanceledError(Exception):
    """What asyncpg raises on `statement_timeout`, by the name the route matches.

    `_is_query_timeout` keys on the class NAME and on SQLSTATE 57014; this double
    carries both, so the test cannot pass by accident on a broader `except`.
    """

    sqlstate = "57014"


class Row:
    def __init__(self, id: int, arms: set[str], sort: int, *, fresh: bool = False):
        self.id = id
        self.arms = arms
        self.sort = sort
        #: True when this row was read AFTER the recovery rollback, i.e. it is not
        #: an expired ORM instance. The whole point of assertion 2 above.
        self.fresh = fresh

    @property
    def tier(self) -> int:
        if "name" in self.arms:
            return 0
        if "ticker" in self.arms or "alias" in self.arms:
            return 1
        return 2


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class FakeDB:
    """Answers arms from a corpus; optionally cancels the outcome-arm statement.

    Records every statement it is given, `SET LOCAL` included, so "was the bound
    applied, and what was it" is answerable without reading the route.
    """

    def __init__(self, corpus: list[Row], *, cancel_outcome_arm: bool = False):
        self.corpus = corpus
        self.cancel_outcome_arm = cancel_outcome_arm
        self.executed: list[frozenset] = []
        self.timeouts_ms: list[int] = []
        self.rolled_back = False

    async def execute(self, marker):
        tag, arms = marker
        if tag == "TIMEOUT":
            self.timeouts_ms.append(arms)
            return _Result([])
        self.executed.append(arms)
        if self.cancel_outcome_arm and OUTCOME_ARM in arms:
            raise QueryCanceledError("canceling statement due to statement timeout")
        rows = [r for r in self.corpus if r.arms & arms]
        rows.sort(key=lambda r: (r.tier, r.sort))
        # Post-rollback reads hand back FRESH copies — an expired instance and a
        # re-read one are indistinguishable by id, which is exactly the trap.
        return _Result(
            [
                Row(r.id, r.arms, r.sort, fresh=self.rolled_back)
                for r in rows[:WINDOW]
            ]
        )

    async def rollback(self):
        self.rolled_back = True


def _candidates_in(arms):
    return frozenset(arms)


def _window_query(candidate_filter):
    return ("Q", candidate_filter)


@pytest.fixture(autouse=True)
def _capture_bounds(monkeypatch):
    """Route the real bound through the fake DB instead of emitting SQL."""

    async def _fake_apply(db, deadline=None, bound_ms=None):
        applied = bound_ms if bound_ms is not None else -1
        await db.execute(("TIMEOUT", applied))

    monkeypatch.setattr(
        events_module, "_apply_search_statement_timeout", _fake_apply
    )


async def _run(corpus, *, cancel=False, deadline=None):
    db = FakeDB(corpus, cancel_outcome_arm=cancel)
    rows, state = await _fetch_futures_window(
        db,
        _window_query,
        _candidates_in,
        list(TIER1_ARMS),
        OUTCOME_ARM,
        # Far enough out that the deadline residual is never the binding term —
        # this suite is about the arm's OWN budget.
        events_module.time.monotonic() + 60 if deadline is None else deadline,
    )
    return db, rows, state


def _thin_corpus():
    """Too few tier<=1 rows to fill the window, so the arm is load-bearing."""
    corpus = [Row(i, {"name"}, i) for i in range(3)]
    corpus += [Row(1000 + i, {OUTCOME_ARM}, 1000 + i) for i in range(30)]
    return corpus


# ---------------------------------------------------------------------------
# THE BUDGET IS THE ARM'S OWN
# ---------------------------------------------------------------------------


def test_the_bound_is_the_arms_budget_and_not_the_deadline_residual():
    """19 s left of the request must not become a 19 s arm."""
    far = events_module.time.monotonic() + 19.0

    assert _search_outcome_arm_bound_ms(far) == _SEARCH_OUTCOME_ARM_TIMEOUT_MS


def test_the_stage_floor_does_not_widen_or_strand_the_arm():
    """The #1 invisible failure: the floor is 2,000 ms, the budget is below it.

    Routing this bound through `_stage_timeout_ms` would return the floor (a
    silently doubled bound); reading `bound < floor` as "shed" would skip the arm
    on every request. Both are asserted against here, in one test, because they
    are the two directions of the same edit.
    """
    assert _SEARCH_OUTCOME_ARM_TIMEOUT_MS < _SEARCH_MIN_STAGE_TIMEOUT_MS, (
        "the premise of this guard is that the budget sits BELOW the stage floor; "
        "if that stops being true the guard stops testing anything"
    )
    bound = _search_outcome_arm_bound_ms(events_module.time.monotonic() + 19.0)

    assert bound == _SEARCH_OUTCOME_ARM_TIMEOUT_MS
    assert bound != _SEARCH_MIN_STAGE_TIMEOUT_MS
    assert bound is not None, "the arm must still run — shedding it always is a recall bug"


def test_the_deadline_still_wins_when_it_is_the_tighter_of_the_two():
    """A bound that could outlive the request deadline is no bound at all."""
    near = events_module.time.monotonic() + 0.2

    bound = _search_outcome_arm_bound_ms(near)

    assert bound is not None
    assert bound <= 250
    assert bound < _SEARCH_OUTCOME_ARM_TIMEOUT_MS


def test_the_arm_sheds_without_touching_the_database_when_no_time_is_left():
    """An honest "we ran out of time", not a statement issued to be cancelled."""
    assert _search_outcome_arm_bound_ms(events_module.time.monotonic() - 1.0) is None


async def test_the_bound_is_applied_before_the_arm_runs():
    """The saving asserted as a presence: no `SET LOCAL`, no budget."""
    db, _rows, state = await _run(_thin_corpus())

    assert state == "merged"
    assert db.timeouts_ms == [_SEARCH_OUTCOME_ARM_TIMEOUT_MS], (
        "the outcome arm ran without its own bound — the residual is back"
    )


async def test_the_cheap_arm_is_never_bounded_by_the_outcome_budget():
    """The tier<=1 arm runs before any of this and must keep the stage bound."""
    corpus = [Row(i, {"name"}, i) for i in range(WINDOW + 5)]
    db, _rows, state = await _run(corpus)

    assert state == "skipped"
    assert db.timeouts_ms == [], (
        "a 1,000 ms budget was armed for a stage it was not measured on"
    )


# ---------------------------------------------------------------------------
# BLOWING THE BUDGET COSTS THE ARM, NOT THE ANSWER
# ---------------------------------------------------------------------------


async def test_a_blown_budget_keeps_the_name_matches(caplog):
    """Before LAT-P271 this cancellation emptied the whole futures bucket.

    The caller treats an exception out of here as a recall failure and returns
    `futures: []` with `degraded`, which reads as "no matches" to every reader —
    the exact LAT-P002 shape this file keeps warning about. The expensive arm
    failing must not cost the cheap arm's answer.
    """
    db, rows, state = await _run(_thin_corpus(), cancel=True)

    assert state == "budget_exceeded"
    assert [r.id for r in rows] == [0, 1, 2]
    assert db.rolled_back, "a cancelled statement poisons the transaction"


async def test_the_returned_rows_are_read_after_the_rollback_not_before():
    """Gotcha #6, asserted on the MARK and not on the ids.

    `db.rollback()` expires every ORM instance the session holds, so the rows
    fetched before the arm ran cannot be returned — they would lazy-load on a
    rolled-back async session the moment the serialiser touched them. Ids alone
    cannot tell an expired row from a re-read one, so the fake tags the copies it
    hands out after the rollback and this asserts on the tag.
    """
    db, rows, state = await _run(_thin_corpus(), cancel=True)

    assert state == "budget_exceeded"
    assert rows, "the re-read returned nothing"
    assert all(r.fresh for r in rows), (
        "these rows were fetched before the recovery rollback expired them"
    )
    assert db.executed == [
        frozenset(TIER1_ARMS),
        frozenset({OUTCOME_ARM}),
        frozenset(TIER1_ARMS),
    ]


async def test_a_non_timeout_failure_still_raises():
    """Only the bound is absorbed. A real error must reach the caller.

    Swallowing every exception here would turn a broken query into a silently
    thin page — the same wrong-answer-that-looks-right class, arrived at from the
    other side.
    """

    class FakeDBBroken(FakeDB):
        async def execute(self, marker):
            tag, arms = marker
            if tag != "TIMEOUT" and OUTCOME_ARM in arms:
                raise RuntimeError("relation does not exist")
            return await super().execute(marker)

    db = FakeDBBroken(_thin_corpus())

    with pytest.raises(RuntimeError):
        await _fetch_futures_window(
            db,
            _window_query,
            _candidates_in,
            list(TIER1_ARMS),
            OUTCOME_ARM,
            events_module.time.monotonic() + 60,
        )


async def test_the_healthy_path_is_untouched():
    """LAT-P005's lesson: this buys no speed for a healthy query, and must not.

    A budget that changed the healthy answer would be LAT-P002 again. The merged
    page here is the same page `test_search_futures_tier_split.py` pins.
    """
    corpus = _thin_corpus()
    db, rows, state = await _run(corpus)

    assert state == "merged"
    assert [r.id for r in rows[:3]] == [0, 1, 2]
    assert len(rows) == WINDOW
    assert db.executed == [frozenset(TIER1_ARMS), frozenset({OUTCOME_ARM})]
