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
from decimal import Decimal

import pytest

from app.tasks import (
    DATED_BASIS_MIN_AGE_HOURS,
    GRADED_DELTA_BATCH,
    GRADED_RANK_BATCH,
    IMPOSSIBLE_PRIOR_BATCH,
    MOVEMENT_WINDOW_HOURS,
    STALE_DELTA_BATCH,
    STALE_RANK_BATCH,
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


def _max_movement_statements(session: _RecordingSession) -> list[str]:
    """B and C — the two statements that OWN `max_movement_24h`.

    Named by what they write rather than by which table they write, because
    "UPDATE futures_markets" stopped identifying them: #4079's A8/A9 publish the
    dated-basis bank into `market_metadata` on the same table and are not part
    of the recompute/clear pair. The pair below is a complement over one
    population and the tests about it mean exactly these two.
    """
    return [s for s in _markets_statements(session) if "max_movement_24h" in s]


def _dated_basis_statements(session: _RecordingSession) -> list[str]:
    """A8 and A9 — the statements that publish and retire the dated bank.

    Selected by the bank's KEY, not by `market_metadata`: #8612's A10 writes
    the same column under a different key and is not part of this bank.
    """
    from app.utils.futures_market_snapshot import DATED_BASIS_METADATA_KEY

    return [
        s for s in _markets_statements(session)
        if "market_metadata" in s and DATED_BASIS_METADATA_KEY in s
    ]


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
    markets = _max_movement_statements(session)

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
    recompute, clear = _max_movement_statements(run_task()[1])

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

    The list is consumed in EXECUTION order, so every statement added to the
    task shifts everything after it. Seven outcome sweeps now — A, A2, A3, A4,
    the two RANK sweeps A5/A6, and A7, the dated-direction sweep — then #4079's
    A8/A9, which publish and retire the dated-basis bank, then #8612's A10,
    which lists unpriced openings, which puts the two `max_movement_24h`
    statements at positions 11 and 12. Each counter is
    asserted against a DISTINCT value so a statement that read its sibling's
    rowcount could not pass — which is the whole reason this fixture is a
    sequence rather than a repeated number.
    """
    result, _ = run_task([12, 6, 9, 8, 1, 1, 5, 7, 3, 13, 4, 2])

    assert result["expired"] == 12
    assert result["graded_retired"] == 6
    assert result["impossible_retired"] == 9
    assert result["unobserved_retired"] == 8
    assert result["contradicted_retired"] == 5
    assert result["dated_basis_banked"] == 7
    assert result["dated_basis_unbanked"] == 3
    assert result["unpriced_openings_written"] == 13
    assert result["cleared_markets"] == 2
    assert result["backlog_drained"] is True, (
        f"a short run did not report the backlog drained: {result}"
    )


def test_the_result_still_carries_the_original_contract(run_task) -> None:
    """LAT-P115's keys survive: the warm is still reported, never swallowed.

    Positions 5 and 6 are #4079's rank sweeps A5/A6, position 7 is its
    dated-direction sweep A7, positions 8 and 9 are its dated-basis bank
    (A8) and unbank (A9) and position 10 is #8612's unpriced-opening list
    (A10), so the recompute is 11th.
    """
    result, _ = run_task([5, 3, 7, 2, 0, 0, 6, 4, 8, 10, 9, 1])

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
    THIRD outcome sweep (A3) and #4079 a FOURTH (A4), then two RANK sweeps
    (A5/A6) and a SEVENTH, the dated-direction sweep A7, all under the same
    obligation — so the count is the number of sweeps and the ordering claim is
    unchanged.

    The count is the half that catches a DROPPED sweep, which is why it is
    pinned here rather than left to the per-statement `_phase_*` helpers.
    """
    events = _statements(run_task()[1])
    outcome_idx = [i for i, s in enumerate(events) if "UPDATE futures_outcomes" in s]
    market_idx = [i for i, s in enumerate(events) if "UPDATE futures_markets" in s]

    assert len(outcome_idx) == 7, (
        f"expected all seven outcome sweeps, saw {len(outcome_idx)}: {events}"
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


def test_the_unobserved_sweep_refuses_a_foreign_probability_scale(
    run_task,
) -> None:
    """A4 subtracts two columns, and it may only do so on ONE scale (CERT-3107).

    `FuturesOddsSnapshot.probability` is one book's raw vig-inclusive number;
    its own column comment ends "Never compare a raw row to a blend", and #1844
    is the incident behind that sentence. A de-vigged consensus sits below every
    raw row it came from, so on a vigged outcome the observed extremes understate
    the supportable rise and A4 retires HONEST movement — the one direction it
    claims it cannot fail in.

    The clause must be `IS FALSE`. `NOT obs.foreign_scale` is NULL on an outcome
    with no rows in the window and TRUE-ish reasoning around it is how a
    fail-open creeps in; `IS FALSE` admits only the proven-clean case. The real
    behaviour is proved on Postgres (`test_movement_window_pg.py`); this asserts
    the clause and the bind are actually IN the statement, because a scope guard
    that is silently dropped leaves every other A4 test green.
    """
    from app.tasks import SCALE_IDENTICAL_SNAPSHOT_SOURCES

    sql, params = _phase_a4(run_task()[1])
    flat = " ".join(sql.split())

    assert "bool_or( s.bookmaker <> ALL(:scale_identical) ) AS foreign_scale" in flat, (
        "the lateral does not detect a foreign-scale row, so the sweep cannot "
        f"know whether its two operands are the same quantity: {flat}"
    )
    assert "obs.foreign_scale IS FALSE" in flat, (
        "the scale guard is not applied as `IS FALSE`, so an outcome carrying a "
        f"vig-inclusive row can still reach the comparison: {flat}"
    )
    assert params.get("scale_identical") == list(SCALE_IDENTICAL_SNAPSHOT_SOURCES), (
        "the admitted sources must be the named constant, bound as a list so "
        f"asyncpg sends a Postgres array to `ALL(...)`: {params}"
    )
    assert isinstance(params.get("scale_identical"), list), (
        "a tuple binds as a ROW, not an array, and `<> ALL(row)` is a different "
        f"question: {params}"
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
    assert params.get("floor") == Decimal(str(MODERATE_MOVEMENT_THRESHOLD)), (
        "the floor is not the copy layer's own mover threshold — restate it as "
        f"a literal and the two records drift silently apart: {params}"
    )
    assert params.get("tolerance") == Decimal(str(UNOBSERVED_PRIOR_TOLERANCE)), (
        f"the sweep does not run on its own tolerance constant: {params}"
    )


def test_the_unobserved_sweeps_thresholds_are_bound_as_exact_decimals(
    run_task,
) -> None:
    """A `float` bind here silently excludes the rows sitting ON the floor.

    Both columns A4 compares are `numeric(7, 6)`, so Postgres infers a bare
    parameter in `abs(probability_change_24h) >= $1` as NUMERIC, and asyncpg
    converts a Python double at its full binary value: `float(0.02)` becomes
    the numeric 0.0200000000000000004163…, strictly greater than a stored
    0.020000. A delta exactly at the threshold then fails its own floor.

    This is asserted on the TYPE rather than on the value because the value
    compares equal either way in Python — `0.02 == Decimal("0.02")` is False,
    but `float(Decimal("0.02")) == 0.02` is True, and a future refactor that
    "simplifies" the bind back to a float would keep every value assertion
    green. Only the real-Postgres gate can see the behaviour, and only this
    can see the cause.
    """
    _, params = _phase_a4(run_task()[1])

    for name in ("floor", "tolerance"):
        assert isinstance(params.get(name), Decimal), (
            f"{name!r} is bound as {type(params.get(name)).__name__}, not "
            "Decimal. asyncpg will send it as a numeric at its full binary "
            "value and the rows exactly on the threshold will be skipped. "
            f"params={params}"
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


# ---------------------------------------------------------------------------
# A5 / A6 — the RANK claim, which A/A2/A3/A4 swept the delta out from under
# ---------------------------------------------------------------------------
# #4079 finding 2. `rank_change_24h` is the delta's twin: same three writers,
# same statement, same per-poll semantics under a 24-hour name. Nothing ever
# swept it, so every row A through A4 cleared kept a rank claim that outlived
# the delta it was written beside. The reader meets that as a "New favorite"
# card reporting no movement for the leader whose lead supposedly just changed —
# `futures_highlights` reads `leader_was_different` off the rank-1 outcome's
# `rank_change_24h` ALONE and pays it `FUTURES_WEIGHTS["leader_change"] = +15`,
# while `feed.py`'s `movement` comes from `probability_change_24h`.
#
# Measured on production 2026-09-19: 394,345 outcomes carry a non-zero rank
# change; 373,272 (94.7%) are already dead by A's or A2's own predicate. Of 11
# served "New favorite" cards, the 4 whose leader served no movement were all
# graded rows with a live rank claim; the other 7 had real movement.
#
# These pin the WIRING, as everything above them does. The row-level semantics —
# that a stale rank claim is cleared, a LIVE one survives, and the two sweeps
# reach rows whose delta is already NULL — need real Postgres and live in
# `tests/integration/test_movement_window_pg.py`. The two files are a pair.


def _phase_a5(session: _RecordingSession) -> tuple[str, dict]:
    """The STALE RANK sweep: the fifth statement to touch futures_outcomes."""
    hits = [(sql, params) for sql, params in session.calls
            if "UPDATE futures_outcomes" in sql]
    if len(hits) < 5:
        raise AssertionError(
            "only four statements update futures_outcomes, so the STALE RANK "
            "sweep is GONE. Without it a row nothing has written in 24 hours "
            "keeps a frozen `rank_change_24h` after A retired its delta, and "
            "the card says 'New favorite' with no movement behind it. "
            "Statements seen: " + repr(_statements(session))
        )
    return hits[4]


def _phase_a6(session: _RecordingSession) -> tuple[str, dict]:
    """The GRADED RANK sweep: the sixth statement to touch futures_outcomes."""
    hits = [(sql, params) for sql, params in session.calls
            if "UPDATE futures_outcomes" in sql]
    if len(hits) < 6:
        raise AssertionError(
            "only five statements update futures_outcomes, so the GRADED RANK "
            "sweep is GONE. A5 cannot reach its rows: `backfill_winners` "
            "re-stamps `last_updated` at ~25 sites every six hours, so a "
            "settled board's rank arrows look fresh to any age test and are "
            "RE-ARMED twice a day — and all four repaired cards in this ship's "
            "own before/after were A6's. "
            "Statements seen: " + repr(_statements(session))
        )
    return hits[5]


def test_the_rank_claim_is_retired_and_not_only_the_delta() -> None:
    """The column is swept at all — the whole of #4079 finding 2.

    Read off the source rather than the recording double on purpose: the
    assertion is that `rank_change_24h = NULL` appears in this task's SQL, and a
    double that was handed the statements cannot fail that independently.
    """
    import inspect

    from app.tasks import update_max_movement

    src = inspect.getsource(update_max_movement)

    assert "rank_change_24h = NULL" in src, (
        "no statement in `update_max_movement` retires `rank_change_24h`. That "
        "is the state this ship ended: A through A4 retire the delta and leave "
        "the rank claim standing, so a card keeps asserting a leadership change "
        "with no movement to support it (#4079 finding 2)."
    )


def test_the_stale_rank_sweep_does_not_gate_on_the_delta(run_task) -> None:
    """A5's predicate must NOT require a surviving `probability_change_24h`.

    THIS IS THE TEST THAT MAKES THE SHIP NON-INERT, and it is the one the
    measurement bought. The obvious fix — adding `rank_change_24h = NULL` to
    A's own `SET` — is inert on every specimen that produced this ship, because
    A selects on `probability_change_24h IS NOT NULL` and those rows had their
    delta retired on an EARLIER run. Of the served "New favorite" leaders,
    `Flávio Bolsonaro` and `Scott Jennings` both carry a NULL delta beside a
    live rank claim; neither is selectable by A.
    """
    sql, params = _phase_a5(run_task()[1])

    select = sql.split("SELECT", 1)[1]
    assert "probability_change_24h" not in select, (
        "the stale RANK sweep gates on the delta, so it can only reach rows "
        "whose delta is still standing — which is precisely the set that does "
        "NOT need it. The rows serving the defect had their delta retired by A "
        "on an earlier run. Statement:\n" + sql
    )
    assert "rank_change_24h IS NOT NULL" in sql, sql
    assert params["window_hours"] == MOVEMENT_WINDOW_HOURS, params


def test_the_stale_rank_sweep_reads_last_updated(run_task) -> None:
    """A's stamp, for A's reason: "has any writer touched this row"."""
    sql, _ = _phase_a5(run_task()[1])

    assert "last_updated" in sql, sql
    assert "price_changed_at" not in sql, (
        "the rank sweep reads the price-move stamp instead of the write stamp. "
        "A row polled every hour and parked at one rank is being written and "
        "its rank change is honest; the rows here are ones NOTHING has "
        "written (#2024 records that reading as POLLER ALIVE). Statement:\n"
        + sql
    )


def test_the_graded_rank_sweep_does_not_gate_on_a_timestamp(run_task) -> None:
    """A6 is immune to A5 for exactly A2's reason, so it must not re-import it."""
    sql, _ = _phase_a6(run_task()[1])

    assert "resolution_source IS NOT NULL" in sql, sql
    assert "last_updated" not in sql, (
        "the graded RANK sweep gates on a timestamp, which makes it a copy of "
        "A5 that cannot reach the rows it exists for: `backfill_winners` "
        "re-stamps `last_updated` at ~25 sites every six hours, so the deadest "
        "boards in the table look fresh. Statement:\n" + sql
    )
    assert "is_winner" not in sql, (
        "the graded RANK sweep reads `is_winner`, which carries a server "
        "DEFAULT false and holds next to no grading information — 2,536 NULLs "
        "in 3,893,126 rows on production. `resolution_source` is the "
        "predicate, and A2 says so at length. Statement:\n" + sql
    )


def test_both_rank_sweeps_are_bounded_by_their_own_constants(run_task) -> None:
    """Separate constants, so neither can be tuned by moving the other."""
    a5_sql, a5_params = _phase_a5(run_task()[1])
    a6_sql, a6_params = _phase_a6(run_task()[1])

    for sql in (a5_sql, a6_sql):
        assert "LIMIT" in sql, (
            "an unbounded rank sweep: 373,272 rows were retirable when this "
            "shipped, and one UPDATE over them blows the task's 120 s "
            f"soft_time_limit and holds locks against four live pollers:\n{sql}"
        )
    assert a5_params["batch"] == STALE_RANK_BATCH, a5_params
    assert a6_params["batch"] == GRADED_RANK_BATCH, a6_params


def test_the_rank_sweeps_skip_a_stored_zero(run_task) -> None:
    """`!= 0` is load-bearing, and it is where A5/A6 part company with A.

    A clears a stored `0.0` because statement B aggregates `MAX(ABS(delta))`, so
    a surviving zero keeps a market inside that GROUP BY and blocks C from
    lowering it. `rank_change_24h` feeds no aggregate, and every consumer
    already reads 0 and NULL identically — `futures_highlights`
    (`rank_change and rank_change != 0`), `snippet_angles`, and iOS
    `FuturesDetailView` (`rankChange != 0`). Sweeping zeros would rewrite
    millions of rows and change nothing a reader can see.
    """
    for phase in (_phase_a5, _phase_a6):
        sql, _ = phase(run_task()[1])
        assert "rank_change_24h != 0" in sql, (
            "the rank sweep retires stored zeros, which costs a multi-million "
            f"row rewrite for no reader-visible change:\n{sql}"
        )


def test_the_fresh_row_sweeps_retire_the_rank_claim_too(run_task) -> None:
    """A3 and A4 are the ONLY places the pair can be retired together.

    A5 and A6 structurally cannot reach their rows — open, ungraded and freshly
    stamped by a delta-blind price writer, which is the entire reason A3 and A4
    exist — so if they do not take the rank claim with the delta, nothing does.
    """
    for label, phase in (("A3 (self-refuting)", _phase_a3),
                         ("A4 (unobserved prior)", _phase_a4)):
        sql, _ = phase(run_task()[1])
        assert "rank_change_24h = NULL" in sql, (
            f"{label} retires the delta and leaves the rank claim written "
            "beside it by the same writer at the same instant. A5 gates on "
            "`last_updated` and A6 on `resolution_source`; these rows are fresh "
            f"and ungraded, so neither can ever reach them:\n{sql}"
        )


def test_all_eight_statements_share_one_transaction(run_task) -> None:
    """A5/A6 join the existing transaction; they do not open a second one.

    Not for the superset bound — they touch no aggregate — but for the card: a
    commit landing between the delta sweeps and the rank sweeps would serve, for
    that window, exactly the "New favorite with no movement" this ship ends.
    """
    events = run_task()[1].events

    assert events.count("COMMIT") == 1, (
        f"a rank sweep added a commit; got {events.count('COMMIT')}: {events}"
    )
    assert events[-1] == "COMMIT", f"a statement ran after the commit: {events}"


def test_the_rank_counters_are_reported_separately(run_task) -> None:
    """A rank row must never be counted into the DELTA drain's counters.

    `expired`/`graded_retired`/`backlog_drained` are how the delta backlog is
    read. Folding rank rows in would make a finished delta drain look like a
    running one forever, since the rank backlog is a different population on a
    different schedule.
    """
    result, _ = run_task([3, 5, 9, 2, STALE_RANK_BATCH, 7, 11, 1])

    assert result["expired"] == 3, result
    assert result["graded_retired"] == 5, result
    assert result["impossible_retired"] == 9, result
    assert result["unobserved_retired"] == 2, result
    assert result["rank_expired"] == STALE_RANK_BATCH, result
    assert result["rank_graded_retired"] == 7, result

    assert result["backlog_drained"] is True, (
        "a full RANK batch reported the DELTA backlog as undrained — the two "
        f"populations drain on different schedules: {result}"
    )
    assert result["rank_backlog_drained"] is False, (
        f"a full rank batch reported the rank backlog drained: {result}"
    )


def test_a_short_rank_batch_reports_the_rank_backlog_drained(run_task) -> None:
    """And the day both rank sweeps come up short, the drain is over."""
    result, _ = run_task([2, 3, 4, 5, 6, 7, 8, 1])

    assert result["rank_backlog_drained"] is True, result


# ---------------------------------------------------------------------------
# #4079 / A8 + A9 — the sweep PUBLISHES the dated evidence, it does not only
# delete.
#
# Every statement above this point retires a delta. None of them can make the
# AMOUNT a card prints right, and none can cover the ten minutes between a price
# write and the next run. A8 banks one observed price per in-scope outcome with
# the instant it was observed; the copy layer subtracts it at serve time
# (`feed._dated_movement_change`, graded in
# `test_a_today_claim_rests_on_dated_evidence_4079.py`).
#
# These tests pin the WIRING, which is this file's whole job: the right key, the
# same evidentiary bar as A7, the untouched per-write column, and both halves
# inside the one transaction. The row-level semantics need real Postgres and
# live in `tests/integration/test_movement_window_pg.py`.
# ---------------------------------------------------------------------------


def _phase_a8(session: _RecordingSession) -> tuple[str, dict]:
    """The BANK: the statement that writes the dated basis into metadata."""
    for sql, params in session.calls:
        if "UPDATE futures_markets" in sql and "jsonb_object_agg" in sql:
            return sql, params
    raise AssertionError(
        "no statement banks a dated basis, so the copy layer has no evidence "
        "and every movement caption on the site is back to spending a per-write "
        "delta on the word 'today'. Statements seen: " + repr(_statements(session))
    )


def test_the_sweep_banks_a_dated_basis_under_the_key_the_reader_reads(
    run_task,
) -> None:
    """The producer and the consumer must spell the carrier key one way.

    A mismatch here is silent in the worst direction: nothing errors, the bank
    is simply never found, and every card goes quiet about movement with no red
    anywhere. Asserted against the RENDERED statement because the key is
    interpolated rather than bound — `jsonb_build_object` is `VARIADIC "any"`
    and asyncpg cannot infer a bare parameter's type for it.
    """
    from app.utils.futures_market_snapshot import DATED_BASIS_METADATA_KEY

    sql, _ = _phase_a8(run_task()[1])

    assert f"jsonb_build_object('{DATED_BASIS_METADATA_KEY}'" in sql, (
        "the bank is not written under the key `dated_movement_basis` that "
        f"`futures_market_snapshot.dated_movement_basis` reads: {sql}"
    )
    assert "coalesce(fm.market_metadata, '{}'::jsonb)" in sql, (
        "the bank must MERGE into the existing metadata; assigning it would "
        f"destroy every other key on the market: {sql}"
    )


def test_the_bank_stores_an_OBSERVATION_and_never_a_computed_change(
    run_task,
) -> None:
    """A price and an instant, never a delta — this is the between-sweeps fix.

    Bank a computed change and a poll landing thirty seconds later makes it a
    lie until the next run. Bank the basis and the same poll simply makes the
    card's own subtraction come out at the new correct number. A statement that
    banked `current_probability - basis` would pass every other test here.
    """
    sql, _ = _phase_a8(run_task()[1])

    assert "jsonb_build_array( round(q.basis, 6), to_char(" in sql, (
        "the bank cell must be [observed price, observed instant]. A computed "
        f"change here reopens the write-between-sweeps hole: {sql}"
    )
    assert "current_probability -" not in sql and "- obs.basis" not in sql, (
        f"the bank is storing a subtraction rather than an observation: {sql}"
    )


def test_the_bank_applies_A7s_evidentiary_bar_and_not_a_weaker_one(
    run_task,
) -> None:
    """A basis good enough to REFUTE a claim is the bar to STATE one.

    Same window, same minimum age, same single-source rule, same scale guard.
    Two bars here would be two answers to "what did this cost yesterday", and
    the weaker one would always be the one printing.
    """
    sql, params = _phase_a8(run_task()[1])

    assert "obs.sources = 1" in sql, (
        "the bank accepts a multi-source observation. A7 refuses one because it "
        "subtracts a blend from a single constituent's row and a systematic "
        f"offset between two sources would manufacture a move: {sql}"
    )
    assert "obs.foreign_scale IS FALSE" in sql, (
        f"the bank does not refuse a foreign probability scale: {sql}"
    )
    assert "obs.basis IS NOT NULL" in sql, (
        f"the bank does not require that an observation exists at all: {sql}"
    )
    assert params["window_hours"] == MOVEMENT_WINDOW_HOURS
    assert params["basis_age_hours"] == DATED_BASIS_MIN_AGE_HOURS, (
        "the bank accepted a basis younger than half the window — a twenty-"
        "minute-old price cannot date a claim about the day"
    )
    assert isinstance(params["floor"], Decimal), (
        "the floor must be bound as an exact Decimal; a float is strictly "
        "greater than the stored numeric and rows sitting exactly on the floor "
        "would be banked or skipped inconsistently with every sibling statement"
    )
    assert params["floor"] == Decimal(str(MODERATE_MOVEMENT_THRESHOLD))


def test_the_bank_refuses_a_basis_that_was_a_last_trade_on_an_empty_book(
    run_task,
) -> None:
    """#8594 — the one place A8's bar is stricter than A7's, pinned as wiring.

    The row semantics (the Thune and impeachment specimens, the tight-book
    control, the no-book and one-sided rows, the exact-rail boundary) live in
    `tests/integration/test_movement_window_pg.py`. This pins what a double can
    see: the rail is the feed's own constant bound as an exact Decimal, and the
    price test filters the BASIS only — `sources` and `foreign_scale` still read
    every observation, so a second source anywhere in the window still refuses.
    """
    from app.utils.feed_market_quality import FEED_PHANTOM_MIN_SPREAD

    sql, params = _phase_a8(run_task()[1])

    assert isinstance(params["max_spread"], Decimal), (
        "the rail must be bound as an exact Decimal; both book columns are "
        "numeric(5, 4) and a float 0.20 would move a book sitting on the rail"
    )
    assert params["max_spread"] == Decimal(str(FEED_PHANTOM_MIN_SPREAD))
    priced = (
        "((s.yes_bid IS NULL AND s.yes_ask IS NULL) "
        "OR s.yes_ask - s.yes_bid < :max_spread)"
    )
    assert sql.count(f"FILTER (WHERE {priced})") == 2, (
        "the basis and its instant must BOTH come from priced observations; "
        f"one without the other banks a price with another row's stamp: {sql}"
    )
    assert "count(DISTINCT s.bookmaker) AS sources" in sql, (
        f"the single-source count must still read every observation: {sql}"
    )


def test_the_bank_is_scoped_to_rows_a_reader_can_actually_see(run_task) -> None:
    """Only rows that MAKE a claim get evidence banked for them.

    Open market, non-null delta at or above the card floor. Widening this would
    bank the whole book into a size-capped shared load artifact for markets
    whose cards say nothing.
    """
    sql, _ = _phase_a8(run_task()[1])

    assert "m.status = 'open'" in sql, f"the bank is not scoped to open markets: {sql}"
    assert "abs(fo.probability_change_24h) >= :floor" in sql, (
        f"the bank is not scoped to rows at or above the card floor: {sql}"
    )
    assert "LIMIT :batch" in sql, (
        f"the bank is unbounded and can blow the task's soft_time_limit: {sql}"
    )
    assert "ORDER BY max(abs(q.delta)) DESC" in sql, (
        "if the batch ever binds, the markets that go unbanked must be the ones "
        f"whispering, not the ones shouting a number at page one: {sql}"
    )


def test_the_bank_never_writes_the_per_write_column(run_task) -> None:
    """🔴 The column keeps its meaning and every one of its other readers.

    `max_movement_24h`, `/api/futures/movers`' ranking and
    `compute_futures_highlight`'s CHOICE of which outcome a card names all key
    on `probability_change_24h`. Writing the windowed number into it — which is
    the obvious shortcut and the one A4 and A7 both refused — would silently
    convert a per-write column into a windowed one for the whole served book.
    """
    sql, _ = _phase_a8(run_task()[1])

    assert "SET probability_change_24h" not in sql, (
        f"the bank rewrote the per-write column instead of publishing beside it: {sql}"
    )
    assert "UPDATE futures_outcomes" not in sql


def test_an_unchanged_bank_is_not_rewritten(run_task) -> None:
    """`IS DISTINCT FROM` is a bloat guard, not an optimisation.

    A basis moves only when an observation ages out of the window — roughly
    seven times a day per outcome — while this task runs every ten minutes.
    Without the guard, 144 runs a day would rewrite ~1,495 JSONB cells apiece
    for no change.
    """
    from app.utils.futures_market_snapshot import DATED_BASIS_METADATA_KEY

    sql, _ = _phase_a8(run_task()[1])

    assert (
        f"(fm.market_metadata -> '{DATED_BASIS_METADATA_KEY}') IS DISTINCT FROM "
        "bank.payload" in sql
    ), f"every run rewrites every banked market: {sql}"


def test_a_market_out_of_claim_scope_loses_its_bank(run_task) -> None:
    """A9. The reader already fails closed on a stale bank — this is the carrier.

    A basis only ever gets older, so a bank nobody refreshes ages out of the
    window and the card stops saying "today" by itself. A9 is therefore about
    cost, not truth: without it every market that ever made a movement claim
    keeps a dead cell riding the size-capped shared load artifact for good.
    """
    from app.utils.futures_market_snapshot import DATED_BASIS_METADATA_KEY

    statements = _dated_basis_statements(run_task()[1])
    assert len(statements) == 2, (
        "expected BOTH dated-basis statements — the bank and the unbank. "
        f"got {len(statements)}: {statements}"
    )

    unbank = [s for s in statements if "jsonb_object_agg" not in s]
    assert unbank, f"nothing ever removes a dead bank: {statements}"
    sql = unbank[0]

    assert f"fm.market_metadata - CAST('{DATED_BASIS_METADATA_KEY}' AS text)" in sql, (
        f"the unbank must delete only its own key, never the metadata: {sql}"
    )
    assert f"jsonb_exists(fm.market_metadata, '{DATED_BASIS_METADATA_KEY}')" in sql, (
        f"the unbank is not scoped to markets that actually carry a bank: {sql}"
    )
    assert "NOT EXISTS" in sql and "abs(fo.probability_change_24h) >= :floor" in sql, (
        "the unbank must fire exactly when the market has left claim scope, on "
        f"the same predicate the bank selects with: {sql}"
    )


def test_the_bank_lands_inside_the_one_transaction(run_task) -> None:
    """A reader must never see a bank against un-swept deltas, or the reverse.

    Between A7's retirements and the bank there is a state where a card's
    evidence and its selection disagree; the single commit is what makes that
    state unobservable, exactly as it is for A/A2/A3/A4/A7 and B/C.
    """
    _, session = run_task()
    events = session.events

    assert events.count("COMMIT") == 1, (
        f"the sweep no longer commits exactly once: {events}"
    )
    commit = events.index("COMMIT")
    banked = [i for i, s in enumerate(events) if "jsonb_object_agg" in s]
    assert banked and max(banked) < commit, (
        f"the dated-basis bank landed outside the single transaction: {events}"
    )


def test_the_bank_runs_after_every_retirement_and_before_the_recompute(
    run_task,
) -> None:
    """Order is load-bearing in both directions.

    AFTER the retirements, so a delta A7 is about to retire never gets evidence
    banked for it. BEFORE B and C, so the run's arithmetic on the column reads
    one settled state rather than two.
    """
    events = _statements(run_task()[1])
    sweeps = [i for i, s in enumerate(events) if "UPDATE futures_outcomes" in s]
    bank = next(i for i, s in enumerate(events) if "jsonb_object_agg" in s)
    recompute = next(i for i, s in enumerate(events) if "max_movement_24h = sub.max_mv" in s)

    assert max(sweeps) < bank < recompute, (
        f"the bank is out of order — sweeps={sweeps} bank={bank} "
        f"recompute={recompute}: {events}"
    )
