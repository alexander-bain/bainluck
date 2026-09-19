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

    An eighth element, `observations`, is a list of `(hours_ago, probability)`
    written into `futures_odds_snapshots` and defaults to NONE AT ALL (#4079).
    That default is what keeps every pre-A4 case in this file meaning exactly
    what it meant: A4 reads the observed extremes through a lateral aggregate
    and `MIN` over an empty set is NULL, so a row with no observations is out of
    its scope by construction and is left to A's age sweep. A case only enters
    A4's population by deliberately saying what this outcome was seen at.

    A market is created per label so each case is independent.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.models import (
        FuturesMarket,
        FuturesOddsSnapshot,
        FuturesOutcome,
    )
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
            observations = row[7] if len(row) > 7 else ()
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

            # A row that relies on the DEFAULT price may not be self-refuting.
            #
            # #6536 added a sweep that retires a delta when
            # `current_probability - probability_change_24h` lands outside
            # [0, 1], and the default price is 0.5 — so any case seeding a delta
            # beyond +-0.5 and saying nothing about the price was silently
            # asking for an impossible row. Two of them existed, both in
            # `test_a_stale_delta_is_retired_and_a_fresh_one_is_not`, and the
            # damage ran both ways: its FRESH row was retired by A3 (a real
            # red), and its STALE row would have been retired by A3 too, so the
            # age sweep could have been deleted with that test still green.
            #
            # Stating a price is the opt-in. A case that names
            # `current_probability` is being deliberate — that is how the A3
            # cases seed their liars — and is left alone. A case that does not
            # gets this assertion, so the trap cannot be walked into twice.
            if len(row) <= 6 and delta is not None:
                implied_prior = 0.5 - delta
                assert 0.0 <= implied_prior <= 1.0, (
                    f"case {label!r} seeds delta {delta} against the default "
                    f"price 0.5, which implies a previous price of "
                    f"{implied_prior:.3f} — not a probability. A3 will retire "
                    "this row whatever its age or grading, so the case proves "
                    "nothing about the sweep it was written for. State a "
                    "`current_probability` (7th element) that makes the pair "
                    "possible, or state one deliberately to seed a liar."
                )

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
            for hours_ago, probability in observations:
                session.add(
                    FuturesOddsSnapshot(
                        outcome_id=outcome.id,
                        bookmaker="kalshi",
                        probability=probability,
                        captured_at=now - timedelta(hours=hours_ago),
                    )
                )
            ids[label] = (market.id, outcome.id)
        await session.commit()

    await engine.dispose()
    return ids


def _run_task(
    batch: int | None = None,
    graded_batch: int | None = None,
    impossible_batch: int | None = None,
    unobserved_batch: int | None = None,
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
    real_unobserved_batch = tasks_mod.UNOBSERVED_PRIOR_BATCH
    base_mod.get_task_session = lambda: _Ctx()
    warm_mod.warm_futures_movers = _no_warm
    if batch is not None:
        tasks_mod.STALE_DELTA_BATCH = batch
    if graded_batch is not None:
        tasks_mod.GRADED_DELTA_BATCH = graded_batch
    if impossible_batch is not None:
        tasks_mod.IMPOSSIBLE_PRIOR_BATCH = impossible_batch
    if unobserved_batch is not None:
        tasks_mod.UNOBSERVED_PRIOR_BATCH = unobserved_batch
    try:
        return update_max_movement.run()
    finally:
        base_mod.get_task_session = real_session
        warm_mod.warm_futures_movers = real_warm
        tasks_mod.STALE_DELTA_BATCH = real_batch
        tasks_mod.GRADED_DELTA_BATCH = real_graded_batch
        tasks_mod.IMPOSSIBLE_PRIOR_BATCH = real_impossible_batch
        tasks_mod.UNOBSERVED_PRIOR_BATCH = real_unobserved_batch


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
                # Priced at 0.20, so each row's delta implies a previous price
                # of 0.915 — a real quote. Both rows are therefore POSSIBLE, and
                # age is the only thing that can separate them. Before #6536
                # both carried the default 0.5, which implies 1.215: A3 would
                # have retired the stale row as well, and this case would have
                # stayed green with the age sweep deleted.
                ("dead", "open", 73, -0.715, 0.715, None, 0.20),
                ("live", "open", 1, -0.715, 0.715, None, 0.20),
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
    ids = asyncio.run(_reset_and_seed([("dead", "open", 73, -0.715, 0.715, None, 0.20)]))
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
            for label, hours, delta, price in (
                ("old", 73, 0.90, 0.95),
                ("new", 2, 0.11, 0.50),
            ):
                session.add(
                    FuturesOutcome(
                        market_id=market.id,
                        external_id=f"OUT-{label}",
                        name=label,
                        is_winner=False,
                        # Priced so `price - delta` is a real probability: the
                        # stale leg must be reachable only by AGE, never by
                        # #6536's self-refuting sweep, or deleting the age
                        # sweep would leave this case green.
                        current_probability=price,
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
                ("dead", "open", 73, -0.715, 0.715, None, 0.20),
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
                ("huge", "open", 73, 0.88, 0.88, None, 0.90),
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
        _reset_and_seed([("mixed", "open", 0, 0.88, 0.88, "api_settlement", 0.90)])
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
                ("all-graded", "open", 0, 0.70, 0.70, "game_score", 0.75),
                ("part-graded", "open", 0, 0.60, 0.60, "api_settlement", 0.65),
                ("live", "open", 1, 0.20, 0.20, None),
                ("stale", "open", 96, 0.90, 0.90, None, 0.95),
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
        _reset_and_seed([("settled-only", "open", 0, 0.55, 0.55, "api_settlement", 0.60)])
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
                ("big", "open", 0, 0.80, 0.80, "api_settlement", 0.85),
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


# ---------------------------------------------------------------------------
# A4 — the OVERSTATED-MOVE sweep (#4079).
#
# Every row here is seeded FRESH (1 hour), UNGRADED and PRICE-POSSIBLE, which is
# the isolation this section rests on and it is stricter than A3's. A row that
# is also stale goes to A, also graded goes to A2, and — the trap specific to
# this statement — a row whose implied prior falls outside [0, 1] goes to A3,
# which runs first. A case that fails A3 as well proves nothing about A4, so
# every liar below implies a perfectly legal price; what is wrong with it is the
# DISTANCE it claims to have travelled, not the arithmetic.
# ---------------------------------------------------------------------------


def test_a_move_the_series_cannot_support_is_retired() -> None:
    """THE ship, on rows: a 7% market did not fall 74 points today.

    `liar` is the production specimen in miniature — "Kanye West performs in
    Russia by October 31?", read off Discover page one at 01:50Z on 2026-09-19
    as "Down 74 points today — now 7% chance". Its own polymarket day ran 0.0525
    to 0.1005, so the deepest fall its series can support is about three points.

    It is fresh, ungraded, and its implied prior (0.809) is a legal probability,
    so A, A2 and A3 all structurally decline it. If A4 is removed, nothing else
    in the task can clear this row — which is exactly the state production was
    in when it was photographed.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "liar",
                    "open",
                    1,
                    -0.740,
                    0.740,
                    None,
                    0.069,
                    [(1, 0.0985), (2, 0.0975), (13, 0.0525), (20, 0.1005)],
                ),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert after["liar"][0] is None, (
        "a fresh, ungraded row claiming a 74-point fall survived on an outcome "
        "whose whole observed day ran between 0.0525 and 0.1005. This is #4079 "
        f"verbatim. got {after['liar'][0]}"
    )
    assert result["unobserved_retired"] == 1, (
        "the run must report what it retired under its own counter: folded into "
        "`impossible_retired` the first big drain would be invisible. "
        f"got {result}"
    )


def test_a_move_the_series_does_support_keeps_its_delta_byte_for_byte() -> None:
    """THE control, and the one that decides whether this statement may ship.

    `honest` is the other production card read in the same pass — "Rain in
    Denver in Sep 2026?" / "Above 1 inch", served as "up 54 points today". Its
    own kalshi series holds 0.28 inside the window, so a 57-point rise is
    supported and the caption is TRUE.

    `drifted` is the SAME card after the delta-blind writer nudged its price
    0.83 -> 0.85 without touching the delta — which is what actually happened
    between two reads twenty minutes apart. The first draft of A4 asked whether
    the implied prior (now 0.31 rather than 0.29) appeared in the series and
    retired this row; the shipped predicate widens the supportable rise to 0.57
    and keeps it. Drift in the direction the delta already claims must never be
    able to convert an honest caption into a swept one.

    Both assertions are on the VALUE, not on "not None": a statement that
    rewrote an honest delta to something else would pass a null check.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("honest", "open", 1, 0.540, 0.540, None, 0.83,
                 [(1, 0.83), (4, 0.29), (8, 0.28), (14, 0.44)]),
                ("drifted", "open", 1, 0.540, 0.540, None, 0.85,
                 [(1, 0.85), (4, 0.29), (8, 0.28), (14, 0.44)]),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert after["honest"][0] == pytest.approx(0.540), (
        "0.83 against a +0.54 delta is supported by a series holding 0.28 four "
        f"hours earlier. The move happened; retiring it deletes a true caption. "
        f"got {after['honest'][0]}"
    )
    assert after["drifted"][0] == pytest.approx(0.540), (
        "two points of delta-blind drift retired an honest caption — this is "
        "the exact-prior draft's failure, and the reason the shipped predicate "
        f"tests overstatement instead. got {after['drifted'][0]}"
    )
    assert result["unobserved_retired"] == 0, (
        f"nothing should have been retired on this fixture. got {result}"
    )


def test_an_understated_delta_is_never_swept() -> None:
    """One-directional: a claim SMALLER than the real move is left standing.

    `shy` moved 30 points by its own series and claims 10. That is not a lie a
    reader is harmed by, it is not provable as wrong from a per-write delta, and
    sweeping it would make the statement bidirectional — which is what makes the
    drift-safety argument above true. If a comparator is ever flipped, this is
    the case that notices.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("shy", "open", 1, 0.100, 0.100, None, 0.50,
                 [(1, 0.50), (6, 0.20)]),
            ]
        )
    )
    _run_task()
    after = asyncio.run(_read(ids))

    assert after["shy"][0] == pytest.approx(0.100), (
        "a delta understating its own observed move was swept, so the predicate "
        f"is no longer one-directional. got {after['shy'][0]}"
    )


def test_a_row_we_never_observed_in_the_window_is_left_to_the_age_sweep() -> None:
    """"We never looked" is not "we looked and it never went there" (#53).

    `MIN` over an empty set is NULL, so `obs.lo IS NOT NULL` is what confines
    the sweep to rows we actually watched. Without it — if the CASE were ever
    rewritten into something NULL-tolerant — A4 would retire the entire
    unobserved tail on a comparison that examined nothing. Those rows are A's
    population by construction. This one is seeded FRESH so A declines it too:
    if A4 over-reaches, nothing else in the task hides it.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("unseen", "open", 1, 0.300, 0.300, None, 0.40),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert after["unseen"][0] == pytest.approx(0.300), (
        "an outcome with no observations in the window was swept by a "
        "comparison that could not evaluate it — absence of evidence read as "
        f"evidence. got {after['unseen'][0]}"
    )
    assert result["unobserved_retired"] == 0, (
        f"nothing should have been retired on this fixture. got {result}"
    )


def test_an_observation_outside_the_window_does_not_rescue_a_liar() -> None:
    """The extremes come from MOVEMENT_WINDOW_HOURS of series, nothing wider.

    `rescued_late` was at 0.809 thirty hours ago and nowhere near it since. The
    price WAS 0.809 once — it was not today, and "today" is the only claim the
    caption makes. `rescued_inside` held the same price eighteen hours ago,
    inside the window, so its fall really is supported and it must survive. If
    the lateral loses its window bound the first row lives and the sweep
    silently becomes a lifetime test that fires on almost nothing.
    """
    from app.tasks import MOVEMENT_WINDOW_HOURS

    ids = asyncio.run(
        _reset_and_seed(
            [
                ("rescued_late", "open", 1, -0.740, 0.740, None, 0.069,
                 [(1, 0.0985), (MOVEMENT_WINDOW_HOURS + 6, 0.809)]),
                ("rescued_inside", "open", 1, -0.740, 0.740, None, 0.069,
                 [(1, 0.0985), (MOVEMENT_WINDOW_HOURS - 6, 0.809)]),
            ]
        )
    )
    _run_task()
    after = asyncio.run(_read(ids))

    assert after["rescued_late"][0] is None, (
        "an observation OUTSIDE the window kept a delta alive, so the sweep is "
        "asking about the outcome's lifetime rather than about today. got "
        f"{after['rescued_late'][0]}"
    )
    assert after["rescued_inside"][0] == pytest.approx(-0.740), (
        "an observation INSIDE the window at 0.809 makes a 74-point fall "
        f"supported, and a supported move must keep its delta. got "
        f"{after['rescued_inside'][0]}"
    )


def test_the_tolerance_is_a_pad_and_not_a_second_opinion() -> None:
    """A hair of overstatement is forgiven; a real one is not.

    The pad exists because `current_probability` can be a blend while a snapshot
    row is one book's raw number. It must be small enough that it cannot rescue
    a lie: `near` overstates its supportable rise by half a tolerance and
    survives, `far` overstates by ten and is retired.
    """
    from app.tasks import UNOBSERVED_PRIOR_TOLERANCE as TOL

    ids = asyncio.run(
        _reset_and_seed(
            [
                # supportable rise 0.50 - 0.205 = 0.295; claim 0.30 is TOL/2 over
                ("near", "open", 1, 0.300, 0.300, None, 0.50,
                 [(1, 0.50), (3, 0.20 + TOL / 2)]),
                # supportable rise 0.50 - 0.30 = 0.20; claim 0.30 is 10x TOL over
                ("far", "open", 1, 0.300, 0.300, None, 0.50,
                 [(1, 0.50), (3, 0.20 + TOL * 10)]),
            ]
        )
    )
    _run_task()
    after = asyncio.run(_read(ids))

    assert after["near"][0] == pytest.approx(0.300), (
        "a claim half a tolerance beyond what the series supports was treated "
        f"as a lie. got {after['near'][0]}"
    )
    assert after["far"][0] is None, (
        "a claim ten tolerances beyond what the series supports survived, so "
        f"the pad has become a second opinion about the move. got "
        f"{after['far'][0]}"
    )


def test_a_delta_below_the_card_floor_is_left_alone() -> None:
    """The floor is a COST bound on a beat, and it is the copy layer's own.

    Below `MODERATE_MOVEMENT_THRESHOLD` no card names a mover and no chip is
    drawn, so a sub-floor delta cannot reach a reader to lie to them. Bounding
    the statement there is what keeps a snapshot join affordable every ten
    minutes.

    Both rows are seeded against a series whose minimum IS the current price, so
    the supportable rise is zero and BOTH claims are overstatements. The only
    thing separating them is the floor — which is what makes this a test of the
    floor rather than of the predicate.
    """
    from app.utils.futures_highlights import MODERATE_MOVEMENT_THRESHOLD

    under = MODERATE_MOVEMENT_THRESHOLD - 0.001
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("under_floor", "open", 1, under, under, None, 0.50,
                 [(1, 0.50), (3, 0.51)]),
                ("at_floor", "open", 1, MODERATE_MOVEMENT_THRESHOLD,
                 MODERATE_MOVEMENT_THRESHOLD, None, 0.50,
                 [(1, 0.50), (3, 0.51)]),
            ]
        )
    )
    _run_task()
    after = asyncio.run(_read(ids))

    assert after["under_floor"][0] == pytest.approx(under), (
        "a delta below the threshold at which a card names a mover was swept, "
        "so the beat is paying a snapshot join for rows no reader can see. got "
        f"{after['under_floor'][0]}"
    )
    assert after["at_floor"][0] is None, (
        "a delta exactly AT the threshold is nameable on a card, so it is in "
        f"scope. got {after['at_floor'][0]}"
    )


def test_a_closed_market_is_not_swept_here() -> None:
    """A4 is scoped to open markets; the graded tail is A2's, by its own design.

    Not defensive narrowing: A2 drains 1.87 M graded rows on a predicate that
    needs no snapshot join, and duplicating that population here would pay for
    the join twice and drain it slower.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("closed", "closed", 1, -0.740, 0.740, None, 0.069,
                 [(1, 0.0985), (3, 0.0975)]),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert after["closed"][0] == pytest.approx(-0.740), (
        "a closed market was swept by A4 — that population is A2's and the "
        f"scopes now overlap. got {after['closed'][0]}"
    )
    assert result["unobserved_retired"] == 0, (
        f"nothing should have been retired on this fixture. got {result}"
    )


def test_the_superset_identity_survives_the_overstated_sweep() -> None:
    """`max_movement_24h == MAX(ABS(change))`, still exactly true after A4.

    The property `/api/futures/movers` rests on (LAT-P108). A4 clears outcomes,
    so B and C must run over what it left — and a market whose only delta A4
    retired must go NULL, not keep its seeded maximum.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("swept_alone", "open", 1, -0.740, 0.740, None, 0.069,
                 [(1, 0.0985), (3, 0.0975)]),
                ("kept", "open", 1, 0.120, 0.120, None, 0.40,
                 [(1, 0.40), (3, 0.28)]),
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
    assert asyncio.run(_identity_holds()) == []


def test_the_overstated_sweep_is_bounded_and_takes_the_biggest_first() -> None:
    """Bounded like A, A2 and A3, and magnitude-ordered for the same reason.

    The larger the claimed move, the more likely this task's own
    `ORDER BY abs(probability_change_24h) DESC` and `/api/futures/movers` pick
    the row as a card's headline mover, so a bounded run must clear the loudest
    lie first.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("loudest", "open", 1, -0.740, 0.740, None, 0.069,
                 [(1, 0.0985), (3, 0.0975)]),
                ("quieter", "open", 1, -0.300, 0.300, None, 0.069,
                 [(1, 0.0985), (3, 0.0975)]),
            ]
        )
    )
    result = _run_task(unobserved_batch=1)
    after = asyncio.run(_read(ids))

    assert result["unobserved_retired"] == 1, (
        f"the batch bound was not honoured. got {result['unobserved_retired']}"
    )
    assert after["loudest"][0] is None, (
        "a bounded run must retire the biggest liar first — the one most likely "
        f"to be chosen as a headline mover. got {after['loudest'][0]}"
    )
    assert after["quieter"][0] == pytest.approx(-0.300), (
        "the smaller lie should still be waiting for the next run. got "
        f"{after['quieter'][0]}"
    )
