"""item 12 / CAL-P159 — `probability_change_24h` must not outlive its window.

## The defect, as the numbers that sized this file

`probability_change_24h` was never a 24-hour change. All four writers store
`new - previous` at write time — a PER-WRITE delta — and nothing recomputed it
over a window, so a row that stops being written keeps serving its last delta
forever while the column's name goes on promising a day.

Measured on production 2026-08-31, before the fix:

  * 2,186,901 outcomes carried a non-null delta; **1,604,840 (73%) had not been
    touched in 24 hours**, and 102,625 of those claimed a swing of >= 10 points.
  * 26,076 of the 31,568 open markets carrying a `max_movement_24h` had no fresh
    outcome at all — their entire "biggest 24h move" came from dead rows.
  * `GET /api/futures/movers?limit=20`, which labels itself `timeframe_hours: 24`:
    **17 of the 20 served rows were older than 24 hours; the oldest was
    2026-07-15, six weeks back.** Alex read one of them on market 109441 as a
    genuine -71.5 point day. That is the ship.

## What this file pins, and what it deliberately does NOT

It pins the WIRING, because the wiring is where every version of this bug has
lived: which stamp is consulted, that the sweep is bounded, that it is ordered
so the visible strip converges first, and that all three statements land in ONE
transaction.

It does NOT pin the row-level semantics — "a stale row is cleared, a fresh one
is not, and a market with nothing left goes NULL". Those need real Postgres
(`now() - interval`, `ORDER BY ... LIMIT` inside `IN`, and a `NOT EXISTS`
correlated against a live table), and asserting them against a recording double
would only prove the double agrees with itself. That gate is
`tests/integration/test_movement_window_pg.py`, named in CI's `search-recall`
job. THE TWO FILES ARE A PAIR; neither is sufficient.

⚠️ `backend/tests/test_movement_window.py` was cited by item 12's own filed
diagnosis as already pinning these semantics. **It did not exist.** The claim was
written and read three times before anyone ran `ls`. It exists now.
"""

from __future__ import annotations

import re

import pytest

from app.tasks import (
    GRADED_DELTA_BATCH,
    IMPOSSIBLE_PRIOR_BATCH,
    MOVEMENT_WINDOW_HOURS,
    STALE_DELTA_BATCH,
    UNOBSERVED_PRIOR_BATCH,
    UNOBSERVED_PRIOR_TOLERANCE,
    update_max_movement,
)
from app.utils.futures_highlights import MODERATE_MOVEMENT_THRESHOLD


# ---------------------------------------------------------------------------
# A recording session — it answers nothing, it only remembers what it was asked
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _RecordingSession:
    """Captures the statement stream, in order, with COMMIT as a real event.

    `rowcounts` is consumed in execution order so a test can say "statement A
    matched N rows" and drive the task's own arithmetic from it.
    """

    def __init__(self, rowcounts: list[int] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.events: list[str] = []
        self._rowcounts = list(rowcounts or [])

    async def execute(self, stmt, params=None):  # noqa: ANN001
        sql = " ".join(str(stmt).split())
        self.calls.append((sql, params or {}))
        self.events.append(sql)
        return _Result(self._rowcounts.pop(0) if self._rowcounts else 0)

    async def commit(self):
        self.events.append("COMMIT")


class _SessionCtx:
    def __init__(self, session: _RecordingSession) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def run_task(monkeypatch):
    """Drive the REAL `update_max_movement` body against a recording session.

    Patched at `app.tasks.base` / `app.tasks.futures_movers_warm` because the
    task imports both INSIDE its own body — patching `app.tasks` would miss.
    """

    def _run(rowcounts: list[int] | None = None) -> tuple[dict, _RecordingSession]:
        session = _RecordingSession(rowcounts)

        import app.tasks.base as base_mod
        import app.tasks.futures_movers_warm as warm_mod

        monkeypatch.setattr(base_mod, "get_task_session", lambda: _SessionCtx(session))

        async def _fake_warm(_session):
            return {"terminal": "ok", "completed": 1}

        monkeypatch.setattr(warm_mod, "warm_futures_movers", _fake_warm)

        result = update_max_movement.run()
        return result, session

    return _run


def _statements(session: _RecordingSession) -> list[str]:
    return [c[0] for c in session.calls]


def _phase_a(session: _RecordingSession) -> tuple[str, dict]:
    for sql, params in session.calls:
        if "UPDATE futures_outcomes" in sql:
            return sql, params
    raise AssertionError(
        "no statement updates futures_outcomes — the expiry sweep is GONE, which "
        "is the whole defect. Statements seen: " + repr(_statements(session))
    )


def _markets_statements(session: _RecordingSession) -> list[str]:
    return [s for s in _statements(session) if "UPDATE futures_markets" in s]


def _phase_a2(session: _RecordingSession) -> tuple[str, dict]:
    """The GRADED sweep: the second statement to touch futures_outcomes."""
    hits = [(sql, params) for sql, params in session.calls
            if "UPDATE futures_outcomes" in sql]
    if len(hits) < 2:
        raise AssertionError(
            "only one statement updates futures_outcomes, so the GRADED sweep is "
            "GONE. Without it a settled outcome keeps its frozen delta forever: "
            "backfill_winners re-stamps `last_updated` on ~25 sites every 6 hours, "
            "which makes the age sweep structurally unable to reach it. "
            "Statements seen: " + repr(_statements(session))
        )
    return hits[1]


# ---------------------------------------------------------------------------
# The sweep exists, and it consults the stamp that answers the right question
# ---------------------------------------------------------------------------


def test_expired_deltas_are_retired_at_the_source(run_task) -> None:
    """A row nothing has written inside the window loses its delta."""
    _, session = run_task()
    sql, _ = _phase_a(session)

    assert re.search(r"SET\s+probability_change_24h\s*=\s*NULL", sql), (
        "the sweep must NULL the delta itself, not merely re-aggregate it. "
        f"got: {sql}"
    )


def test_the_sweep_reads_last_updated_and_not_the_change_stamp(run_task) -> None:
    """POLLER ALIVE, not PRICE FRESH — and the difference is a real regression.

    `last_updated` is written unconditionally by every poll, so it answers "has
    any writer touched this row". `price_changed_at` (#2024) answers "did the
    price move". Keying the sweep on the latter would retire the honest ~0 delta
    of every STABLE price — a market parked at 3% for a week is being polled and
    its delta is correct — while leaving genuinely dead rows untouched whenever
    their last write happened to change something. That inverts the fix.
    """
    sql, _ = _phase_a(run_task()[1])

    assert "last_updated" in sql, f"the sweep stopped consulting last_updated: {sql}"
    assert "price_changed_at" not in sql, (
        "the sweep keyed on price_changed_at: that retires stable-but-polled "
        f"prices and spares dead rows. {sql}"
    )


def test_the_window_comes_from_the_named_constant(run_task) -> None:
    """One number, bound as a parameter, shared with `/movers`' `timeframe_hours`."""
    sql, params = _phase_a(run_task()[1])

    assert params.get("window_hours") == MOVEMENT_WINDOW_HOURS, (
        "the sweep's window is not MOVEMENT_WINDOW_HOURS. The column, the sweep "
        "and the payload field callers read must not be able to drift apart. "
        f"params={params}"
    )
    assert MOVEMENT_WINDOW_HOURS == 24, (
        "the constant no longer matches the name `probability_change_24h` nor "
        "the `timeframe_hours: 24` that /api/futures/movers publishes"
    )
    assert ":window_hours" in sql, f"the window was inlined rather than bound: {sql}"


# ---------------------------------------------------------------------------
# Bounded, and ordered so the USER-VISIBLE half converges first
# ---------------------------------------------------------------------------


def test_the_sweep_is_bounded_by_the_batch_constant(run_task) -> None:
    """1.6 M rows stood when this shipped; one unbounded UPDATE is an outage.

    The task carries `soft_time_limit=120` and runs against four live pollers.
    An unbounded sweep over the standing backlog blows the limit, holds row
    locks, and leaves 1.6 M dead tuples in one transaction.
    """
    sql, params = _phase_a(run_task()[1])

    assert params.get("batch") == STALE_DELTA_BATCH, (
        f"the sweep is not bounded by STALE_DELTA_BATCH. params={params}"
    )
    assert re.search(r"LIMIT\s+:batch", sql), (
        f"the batch parameter is not applied as a LIMIT: {sql}"
    )
    assert 0 < STALE_DELTA_BATCH <= 250_000, (
        "STALE_DELTA_BATCH left the range that fits inside the task's 120 s "
        f"soft_time_limit: {STALE_DELTA_BATCH}"
    )


def test_the_sweep_retires_the_biggest_liars_first(run_task) -> None:
    """The ordering IS the ship, not an optimisation.

    102,625 expired rows claimed >= 10 points and those are the only ones that
    reach `/api/futures/movers`. Measured on production, the 100,000th row by
    magnitude sits at exactly 0.100 — so magnitude-ordered, the FIRST run clears
    the entire visible lie and the tail drains behind it. Unordered or
    oldest-first leaves Alex's strip wrong for hours (gotcha #41).
    """
    sql, _ = _phase_a(run_task()[1])

    assert re.search(
        r"ORDER\s+BY\s+abs\s*\(\s*probability_change_24h\s*\)\s+DESC", sql, re.I
    ), (
        "the sweep is no longer magnitude-ordered, so the biggest false movers "
        f"are no longer retired first: {sql}"
    )


# ---------------------------------------------------------------------------
# The market-level half — statement B structurally cannot do this
# ---------------------------------------------------------------------------


def test_a_market_with_no_surviving_delta_is_cleared(run_task) -> None:
    """The 26,076, and the reason a second market statement has to exist.

    The recompute drives off `GROUP BY market_id` over non-null deltas, so a
    market whose last delta just expired VANISHES from the aggregate and keeps
    its old `max_movement_24h` forever. Sweeping the outcomes without this
    statement would have left every one of those markets ranked exactly where it
    is today — the fix would have looked done and changed nothing on the strip.
    """
    _, session = run_task()
    markets = _markets_statements(session)

    assert len(markets) == 2, (
        "expected BOTH market statements — the recompute and the clear. "
        f"got {len(markets)}: {markets}"
    )

    clearing = [s for s in markets if re.search(r"SET\s+max_movement_24h\s*=\s*NULL", s)]
    assert clearing, (
        "no statement can lower a market's max_movement_24h to NULL, so the "
        "26,076 markets whose outcomes all expired keep their stale maximum "
        f"forever. statements={markets}"
    )

    sql = clearing[0]
    assert "NOT EXISTS" in sql, (
        f"the clear is not scoped to markets with no surviving delta: {sql}"
    )
    assert "probability_change_24h IS NOT NULL" in sql, (
        "the clear's NOT EXISTS must test the same predicate the recompute "
        f"aggregates over, or the two disagree about what a live delta is: {sql}"
    )
    assert "'open'" in sql and "'active'" in sql, (
        f"the clear is not scoped to the statuses /movers serves: {sql}"
    )


def test_the_two_market_statements_are_complements(run_task) -> None:
    """Together they must cover every open market exactly once.

    The recompute handles markets that HAVE a surviving delta; the clear handles
    markets that have NONE. If either drops the status scope the pair stops
    partitioning the same population and `max_movement_24h == MAX(ABS(change))`
    — the identity `/movers`' pool bound rests on — silently stops holding.
    """
    recompute, clear = _markets_statements(run_task()[1])

    for name, sql in (("recompute", recompute), ("clear", clear)):
        assert re.search(r"status\s+IN\s*\(\s*'open'\s*,\s*'active'\s*\)", sql), (
            f"the {name} statement's status scope changed; the pair no longer "
            f"partitions one population: {sql}"
        )


# ---------------------------------------------------------------------------
# Ordering and atomicity
# ---------------------------------------------------------------------------


def test_the_sweep_runs_before_both_market_statements(run_task) -> None:
    """Order is load-bearing: B and C must see the swept state, not the old one."""
    events = _statements(run_task()[1])
    sweep = next(i for i, s in enumerate(events) if "UPDATE futures_outcomes" in s)
    markets = [i for i, s in enumerate(events) if "UPDATE futures_markets" in s]

    assert markets and sweep < min(markets), (
        "the market statements ran BEFORE the outcome sweep, so they recomputed "
        f"from deltas that were about to be retired. order={events}"
    )


def test_all_three_statements_share_one_transaction(run_task) -> None:
    """Between the sweep and the recompute the superset bound is FALSE.

    `/api/futures/movers` ranks a candidate pool by `max_movement_24h` and
    trusts it to be a superset of the true answer. A reader landing between A
    and C sees cleared outcomes against un-recomputed markets, where that is not
    true. One commit, at the end, is the guarantee.
    """
    _, session = run_task()
    events = session.events

    assert events.count("COMMIT") == 1, (
        f"expected exactly one commit; got {events.count('COMMIT')}: {events}"
    )
    assert events[-1] == "COMMIT", (
        f"a statement ran after the commit, outside the transaction: {events}"
    )


# ---------------------------------------------------------------------------
# The drain has to be observable while it runs
# ---------------------------------------------------------------------------


def test_a_full_batch_reports_the_backlog_as_undrained(run_task) -> None:
    """A run that fills its batch means more are waiting; say so."""
    result, _ = run_task([STALE_DELTA_BATCH, 11, 0, 7, 3])

    assert result["expired"] == STALE_DELTA_BATCH
    assert result["backlog_drained"] is False, (
        "a run that retired a FULL batch reported the backlog drained — the one "
        f"reading that hides an unfinished sweep. result={result}"
    )


def test_a_short_batch_reports_the_backlog_as_drained(run_task) -> None:
    """And the day it comes up short, the sweep has caught up.

    Six rowcounts because A4 (#4079) is the FOURTH statement to touch
    `futures_outcomes`; the list is consumed in execution order, so the two
    market statements are now positions 5 and 6. Each retirement counter is
    asserted against a DISTINCT value so a statement that read its sibling's
    rowcount could not pass — which is the whole reason this fixture is a
    sequence rather than a repeated number.
    """
    result, _ = run_task([12, 6, 9, 8, 4, 2])

    assert result["expired"] == 12
    assert result["graded_retired"] == 6
    assert result["impossible_retired"] == 9
    assert result["unobserved_retired"] == 8
    assert result["cleared_markets"] == 2
    assert result["backlog_drained"] is True, (
        f"a short run did not report the backlog drained: {result}"
    )


def test_the_result_still_carries_the_original_contract(run_task) -> None:
    """LAT-P115's keys survive: the warm is still reported, never swallowed."""
    result, _ = run_task([5, 3, 7, 2, 9, 1])

    assert result["updated"] == 9, f"the recompute's rowcount moved key: {result}"
    assert result["movers_warm"] == {"terminal": "ok", "completed": 1}
    assert result["window_hours"] == MOVEMENT_WINDOW_HOURS


# ---------------------------------------------------------------------------
# CERT-627 — a GRADED outcome is dead, and time cannot reach it
#
# The age sweep above gates on `last_updated`, which its own comment defines as
# "has any writer touched this row". Grading writers touch it without polling a
# price: `backfill_winners` stamps `last_updated = NOW()` at ~25 sites on a
# 6-hourly beat, `clob_resolve` at one more. Every one of those leaves
# `probability_change_24h` frozen at its last live value — so the deadest rows
# in the table are exactly the ones the age sweep can never expire, and their
# immunity is renewed twice a day.
#
# Measured on production 2026-08-31: of 2,186,901 non-null deltas, **1,870,447
# (85.5%) sit on graded outcomes**, 134,277 of them claiming >= 10 points.
# Simulating the post-age-sweep strip, 26 of the 120 strip-eligible open markets
# were fully settled, the first at rank 30 ("CA-34 House winner?"), then a
# settled IndyCar champion market and a run of FINISHED US Open matches at 49-60.
# ---------------------------------------------------------------------------


def test_a_graded_outcome_is_retired_by_its_own_statement(run_task) -> None:
    """There is a second outcome sweep and it selects on resolution_source."""
    sql, _ = _phase_a2(run_task()[1])

    assert "probability_change_24h = NULL" in sql, (
        f"the graded sweep does not clear the delta: {sql}"
    )
    assert "resolution_source IS NOT NULL" in sql, (
        "the graded sweep does not select graded rows, so it is not the "
        f"statement CERT-627 asked for: {sql}"
    )


def test_the_graded_sweep_does_not_gate_on_a_timestamp(run_task) -> None:
    """The point of A2 is that AGE CANNOT REACH THESE ROWS.

    A `last_updated` (or `price_changed_at`) predicate here would re-create the
    exact hole it exists to close: a grading writer refreshes the stamp, the row
    reads as fresh, and the frozen delta survives another day — every 6 hours,
    forever. This is the assertion that fails if someone "harmonises" the two
    sweeps into one.
    """
    sql, params = _phase_a2(run_task()[1])

    assert "last_updated" not in sql, (
        "the graded sweep gates on `last_updated` — but backfill_winners "
        "refreshes exactly that stamp every 6 hours on the rows this statement "
        f"targets, so gating on it makes the sweep a no-op: {sql}"
    )
    assert "price_changed_at" not in sql, (
        f"the graded sweep gates on a timestamp; deadness is not an age: {sql}"
    )
    assert "window_hours" not in params, (
        f"the graded sweep took a window; a settled market never un-settles: {params}"
    )


def test_the_graded_sweep_does_not_use_is_winner(run_task) -> None:
    """`is_winner` is nullable with a server DEFAULT false — it is non-null on
    every row in the table and carries no grading information whatsoever.

    Positive control, run against production on 2026-08-31 alongside the census:
    `count(*) FILTER (WHERE is_winner IS NULL)` over the delta-carrying rows
    returned **0**. A sweep keyed on `is_winner IS NOT NULL` would therefore
    match the ENTIRE table and wipe every live delta on the site.
    """
    sql, _ = _phase_a2(run_task()[1])

    assert "is_winner" not in sql, (
        "the graded sweep keys on `is_winner`, which is DEFAULT false and so is "
        "never NULL — this predicate matches every row in futures_outcomes and "
        f"would clear the movement column site-wide: {sql}"
    )


def test_the_graded_sweep_is_bounded_by_its_own_constant(
    run_task, monkeypatch
) -> None:
    """Bounded, and by GRADED_DELTA_BATCH — not by the age sweep's constant.

    Two backlogs of different sizes drain against different plans; tuning one
    must not silently move the other.

    ⚠️ The constant is MOVED before asserting, and that is the whole test.
    `GRADED_DELTA_BATCH` and `STALE_DELTA_BATCH` are both 100_000 today, so
    `params["batch"] == GRADED_DELTA_BATCH` passes identically when the
    statement is wired to the WRONG constant — a mutation battery caught that
    assertion surviving. Comparing against a value both arms share proves
    nothing; only a value that distinguishes them does.
    """
    import app.tasks as tasks_mod

    sentinel = STALE_DELTA_BATCH + 4242
    assert sentinel != STALE_DELTA_BATCH
    monkeypatch.setattr(tasks_mod, "GRADED_DELTA_BATCH", sentinel)

    sql, params = _phase_a2(run_task()[1])

    assert "LIMIT :batch" in sql, f"the graded sweep is unbounded: {sql}"
    assert params.get("batch") == sentinel, (
        "the graded sweep did not follow GRADED_DELTA_BATCH when it moved — it "
        f"is wired to some other constant (got {params.get('batch')!r}, want "
        f"{sentinel!r}; STALE_DELTA_BATCH is {STALE_DELTA_BATCH!r})"
    )


def test_the_graded_sweep_retires_the_biggest_liars_first(run_task) -> None:
    """Magnitude-ordered, so the first run clears what a reader can SEE.

    134,277 of the graded deltas claim >= 10 points; those are the only ones
    that reach `/api/futures/movers`. Unordered or id-ordered, the strip stays
    wrong for hours while the tail drains (gotcha #41).
    """
    sql, _ = _phase_a2(run_task()[1])

    assert re.search(r"ORDER BY abs\(probability_change_24h\) DESC", sql), (
        f"the graded sweep is not magnitude-ordered: {sql}"
    )


def _phase_a3(session: _RecordingSession) -> tuple[str, dict]:
    """The SELF-REFUTING sweep: the third statement to touch futures_outcomes."""
    hits = [(sql, params) for sql, params in session.calls
            if "UPDATE futures_outcomes" in sql]
    if len(hits) < 3:
        raise AssertionError(
            "only two statements update futures_outcomes, so the SELF-REFUTING "
            "sweep is GONE. Without it a row whose price was rewritten by a "
            "delta-blind writer keeps a delta describing a price it no longer "
            "holds, and `current - change` names a probability no venue quoted "
            "(#6536: an outcome at 8% wearing a green 'up 80 points' on "
            "Discover page one). A and A2 cannot reach those rows — the writer "
            "bumps `last_updated` hourly and they are not graded. "
            "Statements seen: " + repr(_statements(session))
        )
    return hits[2]


def test_the_self_refuting_sweep_reads_both_columns(run_task) -> None:
    """A3's predicate is the invariant, and it needs BOTH columns to be one.

    `probability_change_24h IS NOT NULL` alone is A's predicate; the subtraction
    against `current_probability` is what makes this statement about
    simultaneity rather than age. The NULL guard on the price is required and
    not decorative: `NULL - x` is NULL, which is neither < 0 nor > 1, so without
    it a withdrawn leg is silently never considered.
    """
    sql, _ = _phase_a3(run_task()[1])
    flat = " ".join(sql.split())

    assert "current_probability - probability_change_24h < 0" in flat, (
        f"the sweep does not test for a negative implied prior: {flat}"
    )
    assert "current_probability - probability_change_24h > 1" in flat, (
        f"the sweep does not test for an implied prior above 1: {flat}"
    )
    assert "current_probability IS NOT NULL" in flat, (
        f"the sweep does not exclude rows with no stored price: {flat}"
    )
    assert "SET probability_change_24h = NULL" in flat, (
        "the honest value for a self-refuting pair is NULL — the previous price "
        f"is unknowable at sweep time and a recompute would fabricate one: {flat}"
    )


def test_the_self_refuting_sweep_is_inclusive_at_the_bounds(run_task) -> None:
    """`< 0` and `> 1`, never `<= 0` or `>= 1`.

    An implied prior of exactly 0 or exactly 1 is a price venues publish, so the
    strict form is the difference between retiring lies and deleting real
    movement off a 0% or 100% quote.
    """
    sql, _ = _phase_a3(run_task()[1])
    flat = " ".join(sql.split())

    assert "<= 0" not in flat, (
        f"a prior of exactly 0.0 is a price, not an impossibility: {flat}"
    )
    assert ">= 1" not in flat, (
        f"a prior of exactly 1.0 is a price, not an impossibility: {flat}"
    )


def test_the_self_refuting_sweep_is_bounded_and_magnitude_ordered(run_task) -> None:
    """Bounded like its siblings, biggest liar first.

    The ordering is not cosmetic: this task's own sweep and
    `/api/futures/movers` both rank by `abs(probability_change_24h)`, so the
    larger the impossibility the likelier the row is chosen as a card's headline
    mover. A bounded run must clear the loudest lie first.
    """
    sql, params = _phase_a3(run_task()[1])
    flat = " ".join(sql.split())

    assert re.search(r"ORDER BY abs\(probability_change_24h\) DESC", flat), (
        f"the self-refuting sweep is not magnitude-ordered: {flat}"
    )
    assert "LIMIT :batch" in flat, f"the sweep is unbounded: {flat}"
    assert params.get("batch") == IMPOSSIBLE_PRIOR_BATCH, (
        f"the sweep does not run on its own batch constant: {params}"
    )


def test_both_sweeps_run_before_either_market_statement(run_task) -> None:
    """B recomputes over what survived; C clears what has nothing left.

    If A2 landed after them the recompute would read rows A2 was about to
    retire, and the market maximum would be a full run stale. #6536 adds a
    THIRD outcome sweep (A3) and #4079 a FOURTH (A4) under the same obligation,
    so the count is the number of sweeps and the ordering claim is unchanged.
    """
    events = _statements(run_task()[1])
    outcome_idx = [i for i, s in enumerate(events) if "UPDATE futures_outcomes" in s]
    market_idx = [i for i, s in enumerate(events) if "UPDATE futures_markets" in s]

    assert len(outcome_idx) == 4, (
        f"expected all four outcome sweeps, saw {len(outcome_idx)}: {events}"
    )
    assert max(outcome_idx) < min(market_idx), (
        "a market statement ran before an outcome sweep, so it recomputed over "
        f"rows that were about to be retired: {events}"
    )


def test_all_four_statements_share_one_transaction(run_task) -> None:
    """A2 joins the existing transaction; it does not open a second one."""
    events = run_task()[1].events

    assert events.count("COMMIT") == 1, (
        f"the graded sweep added a commit; got {events.count('COMMIT')}: {events}"
    )
    assert events[-1] == "COMMIT", f"a statement ran after the commit: {events}"


def test_a_full_graded_batch_reports_the_backlog_as_undrained(run_task) -> None:
    """`backlog_drained` is the AND of both sweeps.

    Reporting only the age sweep's would go true while 1.87 M graded deltas were
    still standing — a green light for the exact state A2 exists to end.
    """
    result, _ = run_task([3, GRADED_DELTA_BATCH, 0, 7, 1])

    assert result["graded_retired"] == GRADED_DELTA_BATCH
    assert result["graded_backlog_drained"] is False
    assert result["backlog_drained"] is False, (
        "the age sweep came up short so the run reported the whole backlog "
        f"drained, while the graded sweep filled its batch: {result}"
    )


def test_both_backlogs_empty_reports_drained(run_task) -> None:
    """And the day both come up short, the column is honest."""
    result, _ = run_task([2, 3, 4, 5, 6])

    assert result["backlog_drained"] is True, f"{result}"
    assert result["graded_backlog_drained"] is True, f"{result}"


# ---------------------------------------------------------------------------
# The WRITER-side semantics, ported from CAL-P159's file at this same path
# ---------------------------------------------------------------------------
# CAL-P173 (#1978), under INT-190 directive 936 step 2. Two lanes independently
# created `test_movement_window.py` for item 12. Everything above is lane1/Q482's
# sweep — the FIX. CAL-P159's 118-line file pinned the *unfixed writer
# semantics*, and the rebase that resolved the add/add collision took master's
# file whole, which silently dropped four pins.
#
# Two of the four were re-checked against this branch's code and survive; they
# are ported here rather than restored as a second file at the same path (which
# is what 936 forbids and what caused the collision). The other two were dropped
# on measurement, not on taste:
#
#   * `..._the_upstream_fix_has_not_silently_landed_elsewhere` pinned the
#     ABSENCE of the very sweep this file now tests — `app.tasks.__init__` has
#     `SET probability_change_24h = NULL` twice. Correct when written, obsolete
#     now.
#   * `..._the_movers_bound_still_documents_why_read_side_is_wrong` is covered
#     by `tests/test_futures_movers_pool_bound.py`.
#
# Why these two still earn their place AFTER the fix: the sweep retires stale
# deltas downstream, but no writer was changed. The field is still a per-write
# delta over whatever interval happened to elapse — the sweep bounds how long a
# lie survives, it does not make the number mean 24 hours. A reader who sees
# only the sweep will assume it does.


class TestTheFieldStillDoesNotMeanWhatItIsNamed:
    def test_every_writer_computes_a_per_write_delta_not_a_windowed_one(self):
        """All four writers store ``new - previous``, over whatever interval that was."""
        import inspect

        from app.tasks import futures as futures_task
        from app.tasks import kalshi as kalshi_task
        from app.tasks import polymarket as polymarket_task

        kalshi_src = inspect.getsource(kalshi_task)
        poly_src = inspect.getsource(polymarket_task)
        futures_src = inspect.getsource(futures_task)

        assert "- FuturesOutcome.current_probability" in kalshi_src
        assert "- FuturesOutcome.current_probability" in poly_src
        assert "prob_change = prob - old_prob" in futures_src

    def test_no_writer_recomputes_it_over_a_real_24_hour_window(self):
        """Renamed from ``test_nothing_recomputes_it_over_a_real_24_hour_window``.

        The original name and docstring became false the day lane1/Q482's sweep
        landed: something DOES now bound the field to a window. That something is
        `update_max_movement`, downstream of every writer — so the scope this
        pin can honestly claim is the WRITERS, and the name now says so.

        If this ever fails, a writer has grown a windowed recompute and the two
        mechanisms are both bounding the same column. Reconcile them before
        deleting this — do not simply relax it.
        """
        import inspect

        from app.tasks import futures as futures_task
        from app.tasks import kalshi as kalshi_task
        from app.tasks import polymarket as polymarket_task

        for mod in (kalshi_task, polymarket_task, futures_task):
            src = inspect.getsource(mod)
            assert "interval '24 hours'" not in src, mod.__name__


# ---------------------------------------------------------------------------
# #4079 — a delta claiming a move FROM A PRICE THIS OUTCOME NEVER HELD
#
# A3 asks whether the implied previous price is a legal probability. This asks
# the question A3 stands in for: whether it is a price this outcome actually
# quoted today. A3's population was 47 rows for exactly that reason, while 1,365
# of 2,403 reader-visible movers (57%, 903 markets, production 2026-09-19) claim
# a move from a price their own series never recorded in 24 hours.
#
# The wiring is pinned here and the BEHAVIOUR in the real-Postgres sibling: no
# double can evaluate a correlated EXISTS against `futures_odds_snapshots`.
# ---------------------------------------------------------------------------


def _phase_a4(session: _RecordingSession) -> tuple[str, dict]:
    """The UNOBSERVED-PRIOR sweep: the fourth statement to touch outcomes."""
    hits = [(sql, params) for sql, params in session.calls
            if "UPDATE futures_outcomes" in sql]
    if len(hits) < 4:
        raise AssertionError(
            "only three statements update futures_outcomes, so the "
            "UNOBSERVED-PRIOR sweep is GONE. Without it a delta stranded by a "
            "delta-blind price writer survives whenever the price it implies "
            "happens to be a legal probability — which is the overwhelming "
            "majority of them (#4079: 'Down 74 points today - now 7% chance' on "
            "Discover page one, on an outcome whose whole observed day ran "
            "between 5% and 10%). A, A2 and A3 all structurally decline those "
            "rows. Statements seen: " + repr(_statements(session))
        )
    return hits[3]


def test_the_unobserved_sweep_asks_the_series_not_the_row(run_task) -> None:
    """A4's predicate is a question about observations, not about arithmetic.

    A3 decides on the row alone. What makes this a different statement is that
    it reaches `futures_odds_snapshots` for what this outcome was actually seen
    at, and compares the claim against the extremes it finds there. A predicate
    that never reaches that table is A3 with extra words.
    """
    sql, _ = _phase_a4(run_task()[1])
    flat = " ".join(sql.split())

    assert "futures_odds_snapshots" in flat, (
        "the sweep never consults the observation record, so it cannot know "
        f"how far this outcome actually travelled: {flat}"
    )
    assert "min(s.probability) AS lo" in flat and "max(s.probability) AS hi" in flat, (
        "the sweep does not take the observed extremes, which are what bound "
        f"the largest rise and the largest fall the window can justify: {flat}"
    )
    assert "SET probability_change_24h = NULL" in flat, (
        "the honest value for a move that did not happen is NULL — recomputing "
        "it from the series would convert a per-write delta into a windowed one "
        f"for the whole served book: {flat}"
    )


def test_the_unobserved_sweep_only_fires_on_OVERSTATEMENT(run_task) -> None:
    """Both arms compare the CLAIM against what the series supports, one way.

    The rise arm must read `change > (current - lo) + tol` and the fall arm
    `change < (current - hi) - tol`. Flip either comparator, or point an arm at
    the wrong extreme, and the statement starts retiring deltas that UNDERSTATE
    a real move — which is not a lie a reader is harmed by and is not provable
    from the series anyway. The one-directionality is also the drift safety
    property: a delta-blind writer pushing the price further the way the delta
    already points widens the observed range and can only make this fire less.
    """
    sql, _ = _phase_a4(run_task()[1])
    flat = " ".join(sql.split())

    assert (
        "WHEN fo.probability_change_24h > 0 THEN fo.probability_change_24h > "
        "(fo.current_probability - obs.lo) + :tolerance" in flat
    ), (
        "the rise arm is not 'claimed rise exceeds the largest rise the window "
        f"supports': {flat}"
    )
    assert (
        "ELSE fo.probability_change_24h < (fo.current_probability - obs.hi) "
        "- :tolerance" in flat
    ), (
        "the fall arm is not 'claimed fall exceeds the deepest fall the window "
        f"supports': {flat}"
    )


def test_the_unobserved_sweep_separates_never_looked_from_never_happened(
    run_task,
) -> None:
    """`obs.lo IS NOT NULL` is load-bearing, not a null-safety habit.

    `MIN` over an empty set is NULL, and every comparison against NULL is NULL
    — so on an outcome with no observations the CASE is NULL and the row is not
    selected. The clause states that rather than leaving it to be rediscovered,
    because the failure it prevents is silent and total: absence of evidence
    read as evidence, over the whole unobserved tail (gotcha #53). Those rows
    are A's population anyway — nothing observed them, so nothing wrote them.
    """
    sql, _ = _phase_a4(run_task()[1])
    flat = " ".join(sql.split())

    assert "obs.lo IS NOT NULL" in flat, (
        "the sweep does not say it needs observations, so it cannot be read as "
        f"telling 'we never looked' from 'we looked and it never went there': {flat}"
    )


def test_the_unobserved_sweep_windows_the_observations(run_task) -> None:
    """The extremes come from MOVEMENT_WINDOW_HOURS of series, nothing wider.

    The caption this statement defends says "today". Unbounded, the lateral
    takes an outcome's lifetime extremes, every claim becomes supportable and
    the sweep fires on almost nothing — a green statement that does no work.
    """
    sql, params = _phase_a4(run_task()[1])
    flat = " ".join(sql.split())

    assert "s.captured_at > now() - (:window_hours * interval '1 hour')" in flat, (
        f"the observation window is not bounded by the named constant: {flat}"
    )
    assert params.get("window_hours") == MOVEMENT_WINDOW_HOURS, (
        f"the sweep does not run on the named window constant: {params}"
    )


def test_the_unobserved_sweep_is_scoped_to_what_a_reader_can_see(run_task) -> None:
    """Open markets, and deltas big enough for a card to name a mover.

    Both bounds are cost bounds on a ten-minute beat that now pays a snapshot
    join, and both are stated rather than assumed. The floor is imported from
    the module that owns the "is this a mover" decision, so the sweep and the
    copy layer cannot drift into disagreeing about which deltas reach a reader;
    the graded tail stays A2's, which needs no join to drain it.
    """
    sql, params = _phase_a4(run_task()[1])
    flat = " ".join(sql.split())

    assert "fm.status = 'open'" in flat, (
        f"the sweep is not scoped to open markets: {flat}"
    )
    assert "abs(fo.probability_change_24h) >= :floor" in flat, (
        f"the sweep has no magnitude floor, so it pays the join on rows no "
        f"reader can see: {flat}"
    )
    assert params.get("floor") == MODERATE_MOVEMENT_THRESHOLD, (
        "the floor is not the copy layer's own mover threshold — restate it as "
        f"a literal and the two records drift silently apart: {params}"
    )
    assert params.get("tolerance") == UNOBSERVED_PRIOR_TOLERANCE, (
        f"the sweep does not run on its own tolerance constant: {params}"
    )


def test_the_unobserved_sweep_is_bounded_and_magnitude_ordered(run_task) -> None:
    """Bounded like its three siblings, biggest liar first.

    Same reason as A3's: this task's own sweep and `/api/futures/movers` both
    rank by `abs(probability_change_24h)`, so the larger the fictional move the
    likelier the row is chosen as a card's headline mover.
    """
    sql, params = _phase_a4(run_task()[1])
    flat = " ".join(sql.split())

    assert re.search(r"ORDER BY abs\(fo\.probability_change_24h\) DESC", flat), (
        f"the unobserved-prior sweep is not magnitude-ordered: {flat}"
    )
    assert "LIMIT :batch" in flat, f"the sweep is unbounded: {flat}"
    assert params.get("batch") == UNOBSERVED_PRIOR_BATCH, (
        f"the sweep does not run on its own batch constant: {params}"
    )


def test_the_unobserved_count_is_reported_under_its_own_key(run_task) -> None:
    """`unobserved_retired`, never folded into `impossible_retired`.

    The two counters answer different questions about the same writers: one says
    a writer produced an arithmetically impossible pair, the other that it is
    stranding deltas that look legal. Folding them hides the first big drain
    behind a number that was already moving.
    """
    result, _ = run_task([1, 2, 3, 4, 5, 6])

    assert result["unobserved_retired"] == 4, (
        f"the fourth sweep's rowcount is not reported: {result}"
    )
    assert result["impossible_retired"] == 3, (
        f"A3's counter moved when A4 was added: {result}"
    )
