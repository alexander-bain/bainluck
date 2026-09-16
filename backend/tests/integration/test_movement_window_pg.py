"""item 12 — the movement window's SEMANTICS, proved against real Postgres.

`tests/test_movement_window.py` pins the wiring: which stamp is read, that the
sweep is bounded and magnitude-ordered, that all three statements share one
transaction. It cannot pin what the statements DO, because it answers them with
a recording double, and a double agrees with whatever the test told it.

Everything asserted here needs a real database and would be a fabrication
anywhere else:

  * `now() - (:window_hours * interval '1 hour')` — no double evaluates it, so
    the boundary between "kept" and "retired" cannot be observed without one;
  * `ORDER BY abs(...) DESC ... LIMIT` inside an `IN (SELECT ...)` — the whole
    reason the first run clears the visible lie rather than a random slice;
  * the `NOT EXISTS` in statement C, correlated against a table statement A just
    wrote in the same transaction.

And one property that is the point of the entire change and is invisible to any
instrument that does not hold rows:

    for every open market,  max_movement_24h == MAX(ABS(probability_change_24h))
    over its outcomes, or NULL when it has none.

That identity is what `/api/futures/movers` rests on — LAT-P108 proved the pool
it ranks is a SUPERSET of the answer only while the identity holds — so it is
asserted directly, on rows, rather than inferred from the SQL text.

Opt-in on `SEARCH_TEST_DATABASE_URL`, following
`test_futures_price_refresh_writes_pg.py`: there is no local Postgres in the
agent sandbox (`initdb` fails on `shmget`), so **CI is the environment that runs
this**, in the `search-recall` job, whose skip-detector refuses to let an unrun
gate read as a passing one.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres movement-window "
        "gate (CI job: search-recall)"
    ),
)


# ---------------------------------------------------------------------------
# Harness. Every block owns its own loop and its own engine: the task under test
# calls `asyncio.run` itself, so nothing may be shared across those boundaries.
# ---------------------------------------------------------------------------


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401  — registers every table on Base

    return create_async_engine(DB_URL)


async def _reset_and_seed(rows):
    """Rebuild the schema and seed `rows`, returning ids by label.

    Each row is (label, market_status, hours_since_write, delta, seed_max) and
    may carry a sixth element, `resolution_source`, defaulting to None — the
    marker a grading writer leaves and the predicate the GRADED sweep selects on
    (CERT-627). Five-tuples keep their original meaning exactly.

    A seventh element, `current_probability`, defaults to 0.5 — the value every
    pre-#6536 case was seeded with, so those cases are unchanged. It is a row
    parameter because the SELF-REFUTING sweep (A3) reads BOTH columns: its whole
    predicate is `current_probability - probability_change_24h` landing outside
    [0, 1], which no fixture with a constant price can express.

    A market is created per label so each case is independent.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.database import Base

    engine = _engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    ids: dict[str, tuple[int, int]] = {}
    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with maker() as session:
        for row in rows:
            label, status, hours, delta, seed_max = row[:5]
            resolution_source = row[5] if len(row) > 5 else None
            current_probability = row[6] if len(row) > 6 else 0.5
            market = FuturesMarket(
                source="kalshi",
                external_id=f"KXWINDOW-{label}",
                name=f"Window case {label}",
                category="futures",
                market_tier=1,
                status=status,
                max_movement_24h=seed_max,
                resolution_date=now + timedelta(days=30),
            )
            session.add(market)
            await session.flush()

            outcome = FuturesOutcome(
                market_id=market.id,
                external_id=f"OUT-{label}",
                name=label,
                is_winner=False,
                current_probability=current_probability,
                probability_change_24h=delta,
                last_updated=now - timedelta(hours=hours),
                resolution_source=resolution_source,
            )
            session.add(outcome)
            await session.flush()
            ids[label] = (market.id, outcome.id)
        await session.commit()

    await engine.dispose()
    return ids


def _run_task(
    batch: int | None = None,
    graded_batch: int | None = None,
    impossible_batch: int | None = None,
):
    """Drive the REAL `update_max_movement` against this database."""
    import app.tasks.base as base_mod
    import app.tasks.futures_movers_warm as warm_mod
    from app.tasks import update_max_movement

    class _Ctx:
        async def __aenter__(self):
            from sqlalchemy.ext.asyncio import async_sessionmaker

            self._engine = _engine()
            self._session = async_sessionmaker(self._engine, expire_on_commit=False)()
            return self._session

        async def __aexit__(self, *exc):
            await self._session.close()
            await self._engine.dispose()
            return False

    async def _no_warm(_session):
        return {"terminal": "skipped", "completed": 0}

    real_session, real_warm = base_mod.get_task_session, warm_mod.warm_futures_movers
    import app.tasks as tasks_mod

    real_batch = tasks_mod.STALE_DELTA_BATCH
    real_graded_batch = tasks_mod.GRADED_DELTA_BATCH
    real_impossible_batch = tasks_mod.IMPOSSIBLE_PRIOR_BATCH
    base_mod.get_task_session = lambda: _Ctx()
    warm_mod.warm_futures_movers = _no_warm
    if batch is not None:
        tasks_mod.STALE_DELTA_BATCH = batch
    if graded_batch is not None:
        tasks_mod.GRADED_DELTA_BATCH = graded_batch
    if impossible_batch is not None:
        tasks_mod.IMPOSSIBLE_PRIOR_BATCH = impossible_batch
    try:
        return update_max_movement.run()
    finally:
        base_mod.get_task_session = real_session
        warm_mod.warm_futures_movers = real_warm
        tasks_mod.STALE_DELTA_BATCH = real_batch
        tasks_mod.GRADED_DELTA_BATCH = real_graded_batch
        tasks_mod.IMPOSSIBLE_PRIOR_BATCH = real_impossible_batch


async def _read(ids):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = _engine()
    maker = async_sessionmaker(engine, expire_on_commit=False)
    out = {}
    async with maker() as session:
        for label, (market_id, outcome_id) in ids.items():
            delta = (
                await session.execute(
                    text(
                        "SELECT probability_change_24h FROM futures_outcomes "
                        "WHERE id = :i"
                    ),
                    {"i": outcome_id},
                )
            ).scalar()
            mx = (
                await session.execute(
                    text("SELECT max_movement_24h FROM futures_markets WHERE id = :i"),
                    {"i": market_id},
                )
            ).scalar()
            out[label] = (
                None if delta is None else float(delta),
                None if mx is None else float(mx),
            )
    await engine.dispose()
    return out


async def _identity_holds() -> list[str]:
    """Every open market's stored maximum equals the max over its outcomes."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = _engine()
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT fm.id, fm.max_movement_24h, agg.mx
                    FROM futures_markets fm
                    LEFT JOIN LATERAL (
                        SELECT MAX(ABS(fo.probability_change_24h)) AS mx
                        FROM futures_outcomes fo
                        WHERE fo.market_id = fm.id
                          AND fo.probability_change_24h IS NOT NULL
                    ) agg ON true
                    WHERE fm.status IN ('open', 'active')
                    """
                )
            )
        ).all()
    await engine.dispose()
    return [
        f"market {r[0]}: stored={r[1]} but MAX(ABS(change))={r[2]}"
        for r in rows
        if (r[1] is None) != (r[2] is None)
        or (r[1] is not None and r[2] is not None and abs(float(r[1]) - float(r[2])) > 1e-9)
    ]


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------


def test_a_stale_delta_is_retired_and_a_fresh_one_is_not() -> None:
    """The central claim, on rows: the sweep discriminates by age, not by value.

    `dead` is Alex's specimen in miniature — outcome 1597099 carried -0.715 with
    a stamp three days old and the page called it a 24-hour move.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("dead", "open", 73, -0.715, 0.715),
                ("live", "open", 1, -0.715, 0.715),
            ]
        )
    )
    _run_task()
    after = asyncio.run(_read(ids))

    assert after["dead"][0] is None, (
        "a delta on a row nothing has written for 73 hours survived the sweep — "
        f"this is the defect verbatim. got {after['dead'][0]}"
    )
    assert after["live"][0] == pytest.approx(-0.715), (
        "the sweep retired a delta on a row written an hour ago. Age is the "
        f"only discriminator it may use. got {after['live'][0]}"
    )


def test_the_boundary_is_the_named_window() -> None:
    """23h in, 25h out — the window is real and it is the constant's."""
    from app.tasks import MOVEMENT_WINDOW_HOURS

    ids = asyncio.run(
        _reset_and_seed(
            [
                ("inside", "open", MOVEMENT_WINDOW_HOURS - 1, 0.44, 0.44),
                ("outside", "open", MOVEMENT_WINDOW_HOURS + 1, 0.44, 0.44),
            ]
        )
    )
    _run_task()
    after = asyncio.run(_read(ids))

    assert after["inside"][0] == pytest.approx(0.44), (
        f"a row inside the window was retired: {after['inside']}"
    )
    assert after["outside"][0] is None, (
        f"a row outside the window was kept: {after['outside']}"
    )


# ---------------------------------------------------------------------------
# The market half — statement C, and the 26,076
# ---------------------------------------------------------------------------


def test_a_market_whose_last_delta_expired_goes_null_not_stale() -> None:
    """The 26,076 markets. NULL, and specifically not 0 and not the old value.

    Statement B cannot reach this market — it vanishes from the `GROUP BY` the
    moment its only delta is retired — so without statement C it keeps 0.715
    forever and goes on ranking as a top mover.
    """
    ids = asyncio.run(_reset_and_seed([("dead", "open", 73, -0.715, 0.715)]))
    _run_task()
    after = asyncio.run(_read(ids))

    assert after["dead"][1] is None, (
        "the market kept a maximum after its only delta expired. "
        f"got {after['dead'][1]} — 0 would be a fabricated 'no movement' and "
        "0.715 is the stale value that put it on the strip."
    )


def test_a_stale_leg_stops_dominating_a_market_that_still_moves() -> None:
    """The mixed market: the maximum falls to what actually moved today.

    This is the case that decides whether the strip improves or merely empties.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async def _seed_two_legged():
        from app.models.models import FuturesMarket, FuturesOutcome
        from app.services.database import Base

        engine = _engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        now = datetime.now(timezone.utc)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            market = FuturesMarket(
                source="kalshi",
                external_id="KXWINDOW-MIXED",
                name="Mixed",
                category="futures",
                market_tier=1,
                status="open",
                max_movement_24h=0.90,
                resolution_date=now + timedelta(days=30),
            )
            session.add(market)
            await session.flush()
            for label, hours, delta in (("old", 73, 0.90), ("new", 2, 0.11)):
                session.add(
                    FuturesOutcome(
                        market_id=market.id,
                        external_id=f"OUT-{label}",
                        name=label,
                        is_winner=False,
                        current_probability=0.5,
                        probability_change_24h=delta,
                        last_updated=now - timedelta(hours=hours),
                    )
                )
            await session.flush()
            mid = market.id
            await session.commit()
        await engine.dispose()
        return mid

    market_id = asyncio.run(_seed_two_legged())
    _run_task()

    async def _max():
        from sqlalchemy import text

        engine = _engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            v = (
                await session.execute(
                    text("SELECT max_movement_24h FROM futures_markets WHERE id = :i"),
                    {"i": market_id},
                )
            ).scalar()
        await engine.dispose()
        return None if v is None else float(v)

    assert asyncio.run(_max()) == pytest.approx(0.11), (
        "the market's maximum did not fall to its surviving leg — a six-week-old "
        "0.90 is still the number /api/futures/movers would rank it by"
    )


def test_the_superset_identity_holds_after_a_run() -> None:
    """`max_movement_24h == MAX(ABS(change))`, or NULL. /movers rests on this."""
    asyncio.run(
        _reset_and_seed(
            [
                ("dead", "open", 73, -0.715, 0.715),
                ("live", "open", 1, 0.22, 0.05),
                ("also_dead", "active", 200, 0.31, 0.31),
                ("fresh_zero", "open", 3, 0.0, 0.9),
            ]
        )
    )
    _run_task()

    breaks = asyncio.run(_identity_holds())
    assert breaks == [], (
        "the identity /api/futures/movers' pool bound rests on is broken: " + repr(breaks)
    )


# ---------------------------------------------------------------------------
# The bound, and the ordering that makes the first run count
# ---------------------------------------------------------------------------


def test_a_bounded_run_retires_the_biggest_liar_first() -> None:
    """With room for exactly one row, it must be the one on the strip.

    Ordering is the difference between Alex's strip being fixed on the first run
    and being fixed some hours later. Asserted by starving the batch.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("small", "open", 73, 0.03, 0.03),
                ("huge", "open", 73, 0.88, 0.88),
            ]
        )
    )
    result = _run_task(batch=1)
    after = asyncio.run(_read(ids))

    assert result["expired"] == 1, f"the batch bound was not applied: {result}"
    assert after["huge"][0] is None, (
        "the one row a starved run could afford to retire was not the biggest "
        f"false mover: {after}"
    )
    assert after["small"][0] == pytest.approx(0.03), (
        f"the starved run retired more than its batch: {after}"
    )
    assert result["backlog_drained"] is False, (
        f"a run that filled its batch called the backlog drained: {result}"
    )


def test_a_run_with_nothing_to_do_reports_a_drained_backlog() -> None:
    """And it must not disturb anything while saying so."""
    ids = asyncio.run(_reset_and_seed([("live", "open", 1, 0.22, 0.22)]))
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert result["expired"] == 0
    assert result["backlog_drained"] is True, result
    assert after["live"] == (pytest.approx(0.22), pytest.approx(0.22)), (
        f"an idle run moved a healthy row: {after}"
    )


# ---------------------------------------------------------------------------
# CERT-627 — the graded sweep, on real rows
#
# The age sweep discriminates by stamp. Grading writers refresh that stamp
# without polling a price (`backfill_winners` at ~25 sites every 6 hours,
# `clob_resolve` at one), so a settled outcome is BOTH dead and permanently
# "fresh". These cases are the ones a recording double cannot answer: they need
# `now() - interval` evaluated against a row a grading writer just stamped.
# ---------------------------------------------------------------------------


def test_a_graded_outcome_is_retired_even_with_a_brand_new_stamp() -> None:
    """The central CERT-627 claim, on rows.

    `graded` was written one minute ago — the age sweep cannot touch it and
    never will, because backfill_winners re-stamps it every 6 hours. `live` is
    equally fresh and ungraded, and must survive: this statement discriminates
    on deadness, not on recency.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("graded", "open", 0, 0.44, 0.44, "api_settlement"),
                ("live", "open", 0, 0.31, 0.31, None),
            ]
        )
    )
    _run_task()
    out = asyncio.run(_read(ids))

    assert out["graded"] == (None, None), (
        "a SETTLED outcome stamped one minute ago kept its frozen delta and its "
        "market kept ranking on /api/futures/movers. This is CERT-627: the age "
        f"sweep cannot reach a row a grading writer keeps touching. got={out['graded']}"
    )
    assert out["live"] == (0.31, 0.31), (
        "the graded sweep took a LIVE outcome with it — deadness is "
        f"resolution_source, not recency. got={out['live']}"
    )


def test_a_graded_leg_stops_dominating_a_market_that_still_trades() -> None:
    """The mixed market: one settled leg, one live leg, one market maximum.

    This is the shape that puts finished US Open matches on the strip. The
    market's published maximum must come from the leg that still moves.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ids = asyncio.run(
        _reset_and_seed([("mixed", "open", 0, 0.88, 0.88, "api_settlement")])
    )
    market_id, _ = ids["mixed"]

    async def _add_live_leg():
        from app.models.models import FuturesOutcome

        engine = _engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add(
                FuturesOutcome(
                    market_id=market_id,
                    external_id="OUT-mixed-live",
                    name="still trading",
                    is_winner=False,
                    current_probability=0.5,
                    probability_change_24h=0.12,
                    last_updated=datetime.now(timezone.utc),
                    resolution_source=None,
                )
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(_add_live_leg())
    _run_task()

    async def _max():
        engine = _engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            v = (
                await session.execute(
                    text("SELECT max_movement_24h FROM futures_markets WHERE id = :i"),
                    {"i": market_id},
                )
            ).scalar()
        await engine.dispose()
        return None if v is None else float(v)

    assert abs(asyncio.run(_max()) - 0.12) < 1e-9, (
        "the settled leg's 88-point ghost still sets the market's published "
        "24-hour movement while a live leg moved 12. That is the settled US "
        "Open match on the movers strip."
    )


def test_the_superset_identity_survives_the_graded_sweep() -> None:
    """A2 must leave `max_movement_24h == MAX(ABS(change))` exactly true.

    LAT-P108 refused the read-side freshness filter precisely because it breaks
    this identity, which `/api/futures/movers`' pool bound rests on. A statement
    that clears outcomes without letting B and C recompute would break it the
    same way.
    """
    asyncio.run(
        _reset_and_seed(
            [
                ("all-graded", "open", 0, 0.70, 0.70, "game_score"),
                ("part-graded", "open", 0, 0.60, 0.60, "api_settlement"),
                ("live", "open", 1, 0.20, 0.20, None),
                ("stale", "open", 96, 0.90, 0.90, None),
            ]
        )
    )
    _run_task()

    violations = asyncio.run(_identity_holds())
    assert violations == [], (
        "the graded sweep broke the superset identity /api/futures/movers "
        "depends on: " + "; ".join(violations)
    )


def test_a_market_whose_only_leg_was_graded_goes_null() -> None:
    """Statement C's reason, for the graded population.

    B drives off `GROUP BY market_id` over non-null deltas, so a market whose
    last delta A2 just retired VANISHES from the aggregate and would otherwise
    keep its old maximum forever.
    """
    ids = asyncio.run(
        _reset_and_seed([("settled-only", "open", 0, 0.55, 0.55, "api_settlement")])
    )
    _run_task()
    out = asyncio.run(_read(ids))

    assert out["settled-only"] == (None, None), (
        "a market whose every leg is settled kept its stale maximum — B cannot "
        f"lower a market it no longer sees. got={out['settled-only']}"
    )


def test_the_graded_sweep_is_bounded_and_takes_the_biggest_first() -> None:
    """Bounded per run, magnitude-ordered, so the visible strip converges first."""
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("big", "open", 0, 0.80, 0.80, "api_settlement"),
                ("small", "open", 0, 0.05, 0.05, "api_settlement"),
            ]
        )
    )
    result = _run_task(graded_batch=1)
    out = asyncio.run(_read(ids))

    assert result["graded_retired"] == 1, (
        f"the graded sweep ignored its batch bound: {result}"
    )
    assert out["big"] == (None, None), (
        "a bounded run retired the SMALL graded delta and left the 80-point one "
        f"on the strip — the ordering is wrong. got={out}"
    )
    assert out["small"][0] == 0.05, f"expected the tail to wait its turn: {out}"
    assert result["graded_backlog_drained"] is False, (
        f"a full graded batch reported the backlog drained: {result}"
    )


# ---------------------------------------------------------------------------
# A3 — the SELF-REFUTING sweep (#6536).
#
# Every row here is seeded FRESH (1 hour) and UNGRADED (`resolution_source`
# None), which is the isolation the whole section rests on: a row that is also
# stale, or also graded, would be retired by A or A2 and would prove nothing
# about A3. A control that fails two clauses isolates neither.
# ---------------------------------------------------------------------------


def test_an_impossible_prior_is_retired_on_a_fresh_ungraded_row() -> None:
    """THE ship, on rows: 8% cannot have risen 80 points.

    `liar` is the production specimen in miniature — outcome 227786168
    ("Vinted", #1 Free App in the US App Store) carried +0.800 against a stored
    price of 0.080, implying a previous price of -0.72, and Discover page one
    rendered it as a green "up 80 points" on 2026-09-16.

    It is fresh and ungraded, so A and A2 both structurally decline it. If A3 is
    removed, nothing else in the task can clear this row.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("liar", "open", 1, 0.800, 0.800, None, 0.08),
                ("honest", "open", 1, 0.040, 0.040, None, 0.30),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert after["liar"][0] is None, (
        "a fresh, ungraded row whose two columns imply a previous price of "
        "-0.72 survived the sweep — this is #6536 verbatim. got "
        f"{after['liar'][0]}"
    )
    assert after["honest"][0] == pytest.approx(0.040), (
        "0.30 against a +0.04 delta implies a previous price of 0.26, which is "
        "an ordinary move. Retiring it deletes real movement from the strip. "
        f"got {after['honest'][0]}"
    )
    assert result["impossible_retired"] == 1, (
        "the run must report what it retired: this counter is the only way to "
        f"see a price writer stranding deltas again. got {result}"
    )


def test_the_invariant_is_inclusive_at_zero_and_one() -> None:
    """Exactly 0 and exactly 1 are PRICES, so they are kept.

    Written `<= 0 or >= 1` the predicate would clear a delta describing a move
    off a 0% or 100% quote, both of which venues publish. These two rows are the
    negative control that tells the two predicates apart, and each fails exactly
    one side of the bound rather than both.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                # prior exactly 0.0
                ("prior_zero", "open", 1, 0.20, 0.20, None, 0.20),
                # prior exactly 1.0
                ("prior_one", "open", 1, -0.60, 0.60, None, 0.40),
                # prior just under 0 — the smallest real violation, 0.05pp,
                # which production carries 20 of.
                ("prior_under", "open", 1, 0.2005, 0.2005, None, 0.20),
            ]
        )
    )
    _run_task()
    after = asyncio.run(_read(ids))

    assert after["prior_zero"][0] == pytest.approx(0.20), (
        "an implied prior of exactly 0.0 is a price, not an impossibility"
    )
    assert after["prior_one"][0] == pytest.approx(-0.60), (
        "an implied prior of exactly 1.0 is a price, not an impossibility"
    )
    assert after["prior_under"][0] is None, (
        "both columns are numeric(7,6), so a prior of -0.0005 is exact "
        "arithmetic and the same non-simultaneity defect at a smaller "
        f"magnitude — not rounding noise to be tolerated. got "
        f"{after['prior_under'][0]}"
    )


def test_a_row_with_no_price_is_not_swept() -> None:
    """`NULL - x` is NULL, which is neither < 0 nor > 1.

    A withdrawn leg carries no price, so its delta cannot be shown to refute
    anything and A3 must leave it to A's age predicate. Without the explicit
    `current_probability IS NOT NULL` the row is silently never considered, and
    the predicate would not say so.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("withdrawn", "open", 1, 0.90, 0.90, None, None),
            ]
        )
    )
    _run_task()
    after = asyncio.run(_read(ids))

    assert after["withdrawn"][0] == pytest.approx(0.90), (
        "a row with no stored price was swept by a predicate that cannot "
        f"evaluate it. got {after['withdrawn'][0]}"
    )


def test_the_superset_identity_survives_the_impossible_sweep() -> None:
    """`max_movement_24h == MAX(ABS(change))`, still exactly true after A3.

    This is the property `/api/futures/movers` rests on (LAT-P108): the pool it
    ranks is a provable SUPERSET of the answer only while the identity holds. A3
    clears outcomes, so B and C must run over what it left — and a market whose
    only delta A3 retired must go NULL, not keep its seeded maximum.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("swept_alone", "open", 1, 0.800, 0.800, None, 0.08),
                ("kept", "open", 1, 0.120, 0.120, None, 0.40),
            ]
        )
    )
    _run_task()
    after = asyncio.run(_read(ids))

    assert after["swept_alone"] == (None, None), (
        "a market whose only surviving delta was retired kept its old maximum, "
        f"so the superset bound is now false. got {after['swept_alone']}"
    )
    assert after["kept"][0] == pytest.approx(0.120)
    assert after["kept"][1] == pytest.approx(0.120), (
        "the market maximum must equal MAX(ABS(change)) over what survived. "
        f"got {after['kept']}"
    )


def test_the_impossible_sweep_is_bounded_and_takes_the_biggest_first() -> None:
    """Bounded like A and A2, and magnitude-ordered for the same reason.

    The batch is a ceiling against one pathological writer, not a drain
    schedule. Ordering matters for the same reason it does in A: the larger the
    arithmetic impossibility, the more likely this task's own
    `ORDER BY abs(probability_change_24h) DESC` picks the row as a card's
    headline mover, so the first run must clear the loudest lie.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("loudest", "open", 1, 0.800, 0.800, None, 0.08),
                ("quieter", "open", 1, 0.550, 0.550, None, 0.225),
            ]
        )
    )
    result = _run_task(impossible_batch=1)
    after = asyncio.run(_read(ids))

    assert result["impossible_retired"] == 1, (
        f"the batch bound was not honoured. got {result['impossible_retired']}"
    )
    assert after["loudest"][0] is None, (
        "a bounded run must retire the biggest liar first — the one most likely "
        f"to be chosen as a headline mover. got {after['loudest'][0]}"
    )
    assert after["quieter"][0] == pytest.approx(0.550), (
        "the smaller impossibility should still be waiting for the next run. "
        f"got {after['quieter'][0]}"
    )
