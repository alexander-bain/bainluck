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
    MOVEMENT_WINDOW_HOURS,
    STALE_DELTA_BATCH,
    update_max_movement,
)


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
    result, _ = run_task([STALE_DELTA_BATCH, 11, 7, 3])

    assert result["expired"] == STALE_DELTA_BATCH
    assert result["backlog_drained"] is False, (
        "a run that retired a FULL batch reported the backlog drained — the one "
        f"reading that hides an unfinished sweep. result={result}"
    )


def test_a_short_batch_reports_the_backlog_as_drained(run_task) -> None:
    """And the day it comes up short, the sweep has caught up."""
    result, _ = run_task([12, 6, 4, 2])

    assert result["expired"] == 12
    assert result["graded_retired"] == 6
    assert result["cleared_markets"] == 2
    assert result["backlog_drained"] is True, (
        f"a short run did not report the backlog drained: {result}"
    )


def test_the_result_still_carries_the_original_contract(run_task) -> None:
    """LAT-P115's keys survive: the warm is still reported, never swallowed."""
    result, _ = run_task([5, 3, 9, 1])

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


def test_both_sweeps_run_before_either_market_statement(run_task) -> None:
    """B recomputes over what survived; C clears what has nothing left.

    If A2 landed after them the recompute would read rows A2 was about to
    retire, and the market maximum would be a full run stale.
    """
    events = _statements(run_task()[1])
    outcome_idx = [i for i, s in enumerate(events) if "UPDATE futures_outcomes" in s]
    market_idx = [i for i, s in enumerate(events) if "UPDATE futures_markets" in s]

    assert len(outcome_idx) == 2, (
        f"expected both outcome sweeps, saw {len(outcome_idx)}: {events}"
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
    result, _ = run_task([3, GRADED_DELTA_BATCH, 7, 1])

    assert result["graded_retired"] == GRADED_DELTA_BATCH
    assert result["graded_backlog_drained"] is False
    assert result["backlog_drained"] is False, (
        "the age sweep came up short so the run reported the whole backlog "
        f"drained, while the graded sweep filled its batch: {result}"
    )


def test_both_backlogs_empty_reports_drained(run_task) -> None:
    """And the day both come up short, the column is honest."""
    result, _ = run_task([2, 3, 4, 5])

    assert result["backlog_drained"] is True, f"{result}"
    assert result["graded_backlog_drained"] is True, f"{result}"
