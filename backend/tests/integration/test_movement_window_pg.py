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
    wrote in the same transaction;
  * WHICH ROWS A `WHERE` CAN SEE — #4079's rank sweeps exist because A/A2 gate
    on `probability_change_24h IS NOT NULL` and so cannot select the rows whose
    delta they already retired. That claim is about set membership in a real
    table and there is no way to fake it.

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

    An eighth element, `observations`, is a list of
    `(hours_ago, probability)` — or `(hours_ago, probability, bookmaker)` —
    written into `futures_odds_snapshots` and defaults to NONE AT ALL (#4079).
    That default is what keeps every pre-A4 case in this file meaning exactly
    what it meant: A4 reads the observed extremes through a lateral aggregate
    and `MIN` over an empty set is NULL, so a row with no observations is out of
    its scope by construction and is left to A's age sweep. A case only enters
    A4's population by deliberately saying what this outcome was seen at.

    A ninth element, `rank_change_24h`, and a tenth, `rank`, both default to
    None — the columns the RANK sweeps A5/A6 read (#4079 finding 2). They are
    row parameters for the same reason `current_probability` is: `rank_change_24h`
    is written by the same three writers in the same statement as the delta and
    was then never swept, so the cases that matter are ones where the two columns
    DISAGREE — a NULL delta beside a live rank claim — which no fixture that
    derives one from the other can express.

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
            rank_change_24h = row[8] if len(row) > 8 else None
            rank = row[9] if len(row) > 9 else None
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
                rank_change_24h=rank_change_24h,
                rank=rank,
            )
            session.add(outcome)
            await session.flush()
            for observation in observations:
                # A third element names the BOOKMAKER, defaulting to the
                # prediction-market source every pre-CERT-3107 case meant
                # (#4079). It is optional so those cases read unchanged, and it
                # exists so a case can seed a vig-inclusive sportsbook row —
                # the one thing A4 must refuse to subtract from a blend.
                #
                # A fourth and fifth element are the BOOK (`yes_bid`,
                # `yes_ask`), defaulting to NULL — the no-book row every
                # pre-#8594 case meant. They exist so a case can seed a stale
                # last trade across an empty book, which A8 may not bank.
                hours_ago, probability = observation[:2]
                bookmaker = observation[2] if len(observation) > 2 else "kalshi"
                yes_bid = observation[3] if len(observation) > 3 else None
                yes_ask = observation[4] if len(observation) > 4 else None
                session.add(
                    FuturesOddsSnapshot(
                        outcome_id=outcome.id,
                        bookmaker=bookmaker,
                        probability=probability,
                        yes_bid=yes_bid,
                        yes_ask=yes_ask,
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
    contradicted_batch: int | None = None,
    stale_rank_batch: int | None = None,
    graded_rank_batch: int | None = None,
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
    real_contradicted_batch = tasks_mod.CONTRADICTED_DIRECTION_BATCH
    real_stale_rank_batch = tasks_mod.STALE_RANK_BATCH
    real_graded_rank_batch = tasks_mod.GRADED_RANK_BATCH
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
    if contradicted_batch is not None:
        tasks_mod.CONTRADICTED_DIRECTION_BATCH = contradicted_batch
    if stale_rank_batch is not None:
        tasks_mod.STALE_RANK_BATCH = stale_rank_batch
    if graded_rank_batch is not None:
        tasks_mod.GRADED_RANK_BATCH = graded_rank_batch
    try:
        return update_max_movement.run()
    finally:
        base_mod.get_task_session = real_session
        warm_mod.warm_futures_movers = real_warm
        tasks_mod.STALE_DELTA_BATCH = real_batch
        tasks_mod.GRADED_DELTA_BATCH = real_graded_batch
        tasks_mod.IMPOSSIBLE_PRIOR_BATCH = real_impossible_batch
        tasks_mod.UNOBSERVED_PRIOR_BATCH = real_unobserved_batch
        tasks_mod.CONTRADICTED_DIRECTION_BATCH = real_contradicted_batch
        tasks_mod.STALE_RANK_BATCH = real_stale_rank_batch
        tasks_mod.GRADED_RANK_BATCH = real_graded_rank_batch


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


def test_a_vigged_sportsbook_series_can_never_condemn_a_de_vigged_blend() -> None:
    """THE scale control (CERT-3107): A4 may not subtract across two scales.

    `FuturesOddsSnapshot.probability` is one book's RAW vig-inclusive number and
    its column comment says so in as many words — "Never compare a raw row to a
    blend" — because #1844 published an all-red movers row for months on exactly
    this subtraction. A de-vigged consensus sits BELOW every raw row it was built
    from, so on a vigged outcome the observed extremes understate the supportable
    rise by roughly the vig share.

    `vigged` is that arithmetic with honest inputs. The consensus moved 0.40 ->
    0.50 today, a true +10 points. Two sportsbooks priced it at 0.44 yesterday
    and 0.55 now — same journey, each inflated by about a tenth of vig. Read
    against the raw extremes the supportable rise is 0.50 - 0.44 = 0.06, so the
    claim clears the one-point tolerance and A4 WITHOUT the scale guard retires
    a caption that was TRUE. That is the one failure direction the statement
    claims it cannot have, so the guard is what earns the claim.

    `mixed` is the same refusal one step weaker: a single sportsbook row beside
    a prediction-market one. On the prediction-market rows alone the claim looks
    unsupportable, and it may still be — but `current_probability` on an outcome
    priced from both scales is not a quantity this statement can reason about,
    so the honest move is to leave the delta to A, A2 and A3.

    Both rows are fresh, ungraded and imply a legal prior (0.40), so nothing
    else in the task touches them: if they go NULL, A4 did it.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "vigged",
                    "open",
                    1,
                    0.10,
                    0.10,
                    None,
                    0.50,
                    [
                        (20, 0.44, "draftkings"),
                        (20, 0.445, "fanduel"),
                        (1, 0.55, "draftkings"),
                        (1, 0.554, "fanduel"),
                    ],
                ),
                (
                    "mixed",
                    "open",
                    1,
                    0.10,
                    0.10,
                    None,
                    0.50,
                    [(20, 0.48, "polymarket"), (1, 0.55, "draftkings")],
                ),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert after["vigged"][0] == pytest.approx(0.10), (
        "A4 retired a TRUE +10-point consensus move by measuring it against "
        "vig-inclusive sportsbook rows, which sit above the de-vigged blend and "
        "therefore understate every rise. This is #1844's subtraction and the "
        f"column comment forbids it. got {after['vigged'][0]}"
    )
    assert after["mixed"][0] == pytest.approx(0.10), (
        "an outcome carrying one foreign-scale row in the window was swept on "
        "the strength of its same-scale rows. The guard is per OUTCOME and "
        "fails closed on purpose: a blend of two scales is not a quantity this "
        f"statement can reason about. got {after['mixed'][0]}"
    )
    assert result["unobserved_retired"] == 0, (
        "neither row is in A4's scope, so the sweep must report retiring "
        f"nothing. got {result}"
    )


def test_the_scale_guard_does_not_cost_the_prediction_market_sweep() -> None:
    """The guard must be a scope, not an off switch — both sources stay live.

    A guard written as "skip anything with a snapshot I don't recognise" would
    pass the vigged control above and quietly retire nothing at all if a source
    name were mistyped. So this drives one liar per member of
    `SCALE_IDENTICAL_SNAPSHOT_SOURCES` and requires BOTH to be swept: polymarket
    carries 2,752 of the 3,108 rows A4 retires on production and kalshi the
    other 356, and a typo in either is a silent half-outage of the ship.
    """
    from app.tasks import SCALE_IDENTICAL_SNAPSHOT_SOURCES

    assert set(SCALE_IDENTICAL_SNAPSHOT_SOURCES) == {"kalshi", "polymarket"}, (
        "this case seeds one liar per named source; a new member needs a row "
        f"here or it ships unproven. got {SCALE_IDENTICAL_SNAPSHOT_SOURCES}"
    )
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    source,
                    "open",
                    1,
                    -0.60,
                    0.60,
                    None,
                    0.20,
                    [(20, 0.22, source), (1, 0.21, source)],
                )
                for source in SCALE_IDENTICAL_SNAPSHOT_SOURCES
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    for source in SCALE_IDENTICAL_SNAPSHOT_SOURCES:
        assert after[source][0] is None, (
            f"a {source}-sourced row claiming a 60-point fall survived on a "
            "series that never left 0.21-0.22. The scale guard is refusing a "
            f"source it is supposed to admit. got {after[source][0]}"
        )
    assert result["unobserved_retired"] == len(SCALE_IDENTICAL_SNAPSHOT_SOURCES), (
        "every named same-scale source must still be swept; a guard that "
        f"admits only one of them is half an outage. got {result}"
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


# ---------------------------------------------------------------------------
# A5 / A6 — the RANK claim, proved on rows (#4079 finding 2)
# ---------------------------------------------------------------------------
# `rank_change_24h` is the delta's twin — same three writers, same statement,
# same per-poll semantics under a 24-hour name — and until this shipped nothing
# swept it. So A through A4 retired deltas out from under rank claims that
# outlived them, and `futures_highlights` went on reading `leader_was_different`
# off the rank-1 outcome's `rank_change_24h` ALONE, printing "New favorite" and
# paying it +15 while `feed.py` served no movement for that leader.
#
# EVERY STALE/GRADED CASE HERE SEEDS A NULL DELTA BESIDE A LIVE RANK CLAIM,
# because that is the state the served specimens are actually in and it is the
# state the obvious fix cannot reach. Adding `rank_change_24h = NULL` to A's own
# `SET` is inert here: A selects on `probability_change_24h IS NOT NULL`, and
# these rows had their delta retired on an earlier run. Nothing short of a real
# database proves that, because the whole claim is about which rows a `WHERE`
# can see.
#
# Row shape: (label, status, hours, delta, seed_max, resolution_source,
#             current_probability, observations, rank_change_24h, rank)


async def _read_rank(ids):
    """`rank_change_24h` per label. Separate from `_read` so the tuple shape
    every earlier case destructures is untouched."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = _engine()
    maker = async_sessionmaker(engine, expire_on_commit=False)
    out = {}
    async with maker() as session:
        for label, (_market_id, outcome_id) in ids.items():
            out[label] = (
                await session.execute(
                    text(
                        "SELECT rank_change_24h FROM futures_outcomes WHERE id = :i"
                    ),
                    {"i": outcome_id},
                )
            ).scalar()
    await engine.dispose()
    return out


def test_a_stale_rank_claim_is_retired_even_though_its_delta_is_already_gone() -> None:
    """THE SHIP. A row A already swept keeps no rank claim.

    `stale_leader` is the shape of the served specimens: delta already NULL,
    rank 1, rank change live. It is UNREACHABLE by statement A — the
    `WHERE probability_change_24h IS NOT NULL` that found it on some earlier run
    excludes it now — so if this row still carries its rank claim after a run,
    the card goes on saying "New favorite" with no movement behind it, which is
    the entire defect.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("stale_leader", "open", 48, None, None, None, 0.40, (), 3, 1),
                ("fresh_leader", "open", 1, 0.10, 0.10, None, 0.40, (), 2, 1),
            ]
        )
    )
    result = _run_task()
    ranks = asyncio.run(_read_rank(ids))

    assert ranks["stale_leader"] is None, (
        "a row nothing has written in 48 hours kept its `rank_change_24h` after "
        "the run. Its delta was already NULL, so statement A cannot select it — "
        "which is exactly why A5 is a separate statement and not a wider `SET` "
        f"on A. Retired {result['rank_expired']} stale rank claims."
    )
    assert result["rank_expired"] == 1, result

    assert ranks["fresh_leader"] == 2, (
        "THE CONTROL FAILED: a fresh, ungraded row with a live delta lost its "
        "rank claim. A genuine overtake KEEPS 'New favorite' — a run in which "
        "no rank claim survives is this ship overshooting, not working. "
        f"got {ranks['fresh_leader']!r}"
    )


def test_a_graded_rank_claim_is_retired_even_with_a_brand_new_stamp() -> None:
    """A6's reason, on rows: `backfill_winners` re-stamps `last_updated` at ~25
    sites every six hours, so a settled board looks fresh to A5 forever and its
    rank arrows are RE-ARMED twice a day. All four repairs in this ship's own
    before/after were this statement's."""
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("graded_fresh", "open", 0, None, None, "kalshi", 0.55, (), 1, 1),
                ("open_fresh", "open", 0, None, None, None, 0.55, (), 1, 1),
            ]
        )
    )
    result = _run_task()
    ranks = asyncio.run(_read_rank(ids))

    assert ranks["graded_fresh"] is None, (
        "a GRADED outcome stamped this second kept its rank claim. A5 gates on "
        "`last_updated` and grading writers bump it, so no age test can ever "
        f"reach this row: {ranks}"
    )
    assert result["rank_graded_retired"] == 1, result

    assert ranks["open_fresh"] == 1, (
        "an OPEN, ungraded, freshly-written row lost its rank claim, so the "
        "graded sweep is not reading `resolution_source` — it is clearing "
        f"everything: {ranks}"
    )


def test_a_self_refuting_row_loses_the_rank_claim_with_the_delta() -> None:
    """A3 must retire the pair together.

    `liar` is open, ungraded and freshly stamped — A5 and A6 structurally cannot
    reach it, which is the whole reason A3 exists — so if A3 does not take the
    rank claim alongside the delta its own arithmetic just refuted, nothing
    does. Price 0.08 against a delta of 0.80 implies a previous price of -0.72,
    which no venue ever quoted (#6536).
    """
    ids = asyncio.run(
        _reset_and_seed([("liar", "open", 0, 0.80, 0.80, None, 0.08, (), 4, 1)])
    )
    result = _run_task()
    read = asyncio.run(_read(ids))
    ranks = asyncio.run(_read_rank(ids))

    assert read["liar"][0] is None, f"A3 did not retire the delta: {read}"
    assert result["impossible_retired"] == 1, result
    assert ranks["liar"] is None, (
        "the self-refuting sweep retired the delta and left the rank claim that "
        "the same writer wrote beside it at the same instant. The row is fresh "
        f"and ungraded, so neither A5 nor A6 will ever reach it: {ranks}"
    )
    assert result["rank_expired"] == 0 and result["rank_graded_retired"] == 0, (
        "A5 or A6 claimed this row, so the case is not proving what it says — "
        f"it must be unreachable by both: {result}"
    )


def test_an_unobserved_move_loses_the_rank_claim_with_the_delta() -> None:
    """A4 must retire the pair together, for A3's reason.

    `overstated` is open, ungraded and freshly stamped, and its implied prior
    (0.60 - 0.40 = 0.20) is a perfectly legal probability — so A3 misses it and
    only the observed series refutes it. A5/A6 cannot reach it either, so A4 is
    the only statement that can take its rank claim.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "overstated", "open", 0, 0.40, 0.40, None, 0.60,
                    ((2, 0.55), (6, 0.58)), 5, 1,
                )
            ]
        )
    )
    result = _run_task()
    read = asyncio.run(_read(ids))
    ranks = asyncio.run(_read_rank(ids))

    assert result["unobserved_retired"] == 1, (
        "A4 did not select the overstated row, so this case proves nothing "
        f"about it: {result}"
    )
    assert read["overstated"][0] is None, f"A4 did not retire the delta: {read}"
    assert ranks["overstated"] is None, (
        "the overstated-move sweep retired a delta the observed series refutes "
        "and left the rank claim written beside it at the same unobserved "
        f"instant: {ranks}"
    )
    assert result["rank_expired"] == 0 and result["rank_graded_retired"] == 0, (
        f"A5 or A6 claimed this row, so it is not A4-only as the case says: {result}"
    )


def test_a_stored_zero_rank_change_is_left_alone() -> None:
    """`!= 0` is load-bearing, and it is where A5/A6 part company with A.

    A clears a stored `0.0` because statement B aggregates `MAX(ABS(delta))`, so
    a surviving zero keeps a market inside that GROUP BY and blocks C from
    lowering it. `rank_change_24h` feeds no aggregate, and every consumer reads
    0 and NULL identically — `futures_highlights` (`rank_change and
    rank_change != 0`), `snippet_angles`, iOS `FuturesDetailView`
    (`rankChange != 0`). Sweeping zeros would rewrite millions of rows on
    production and change nothing a reader can see.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("dead_zero", "open", 72, None, None, "kalshi", 0.30, (), 0, 2),
                ("dead_live", "open", 72, None, None, "kalshi", 0.30, (), 5, 1),
            ]
        )
    )
    _run_task()
    ranks = asyncio.run(_read_rank(ids))

    assert ranks["dead_zero"] == 0, (
        "a stored zero was rewritten to NULL. No reader can tell the two apart, "
        "so this costs a multi-million-row rewrite on production for no visible "
        f"change: {ranks}"
    )
    assert ranks["dead_live"] is None, (
        "the non-zero claim on an equally dead row survived, so the sweep is "
        f"not running at all: {ranks}"
    )


def test_the_rank_sweeps_are_bounded_by_their_own_batches() -> None:
    """Bounded for A's reason: 373,272 rows were retirable when this shipped,
    and one unbounded UPDATE over them blows the task's 120 s soft limit and
    holds locks against four live pollers."""
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("s1", "open", 48, None, None, None, 0.40, (), 3, 1),
                ("s2", "open", 48, None, None, None, 0.40, (), 2, 1),
                ("g1", "open", 0, None, None, "kalshi", 0.40, (), 4, 1),
                ("g2", "open", 0, None, None, "kalshi", 0.40, (), 1, 1),
            ]
        )
    )
    result = _run_task(stale_rank_batch=1, graded_rank_batch=1)
    ranks = asyncio.run(_read_rank(ids))

    assert result["rank_expired"] == 1, (
        f"the stale rank sweep ignored its batch: {result}"
    )
    assert result["rank_graded_retired"] == 1, (
        f"the graded rank sweep ignored its batch: {result}"
    )
    assert result["rank_backlog_drained"] is False, (
        f"both sweeps filled their batch but the backlog read drained: {result}"
    )

    assert len([lbl for lbl in ("s1", "s2") if ranks[lbl] is not None]) == 1, (
        f"the stale batch of 1 retired {ranks}"
    )
    assert len([lbl for lbl in ("g1", "g2") if ranks[lbl] is not None]) == 1, (
        f"the graded batch of 1 retired {ranks}"
    )


def test_the_superset_identity_survives_the_rank_sweeps() -> None:
    """A5/A6 touch no aggregate, so B and C's bound must be untouched.

    `/api/futures/movers` ranks a pool by `max_movement_24h` and LAT-P108 proved
    that pool is a superset of the answer only while
    `max_movement_24h == MAX(ABS(probability_change_24h))` holds. A rank sweep
    has no business moving it; this is the assertion that says so on rows.
    """
    asyncio.run(
        _reset_and_seed(
            [
                ("mover", "open", 1, 0.30, 0.30, None, 0.60, (), 7, 1),
                ("dead_rank", "open", 90, None, 0.30, None, 0.60, (), 7, 1),
                ("graded_rank", "open", 0, None, None, "kalshi", 0.20, (), 3, 2),
            ]
        )
    )
    _run_task()
    violations = asyncio.run(_identity_holds())

    assert violations == [], (
        "the rank sweeps moved the market maximum, which breaks the bound "
        f"`/api/futures/movers` rests on: {violations}"
    )


# ---------------------------------------------------------------------------
# A7 — the CONTRADICTED-DIRECTION sweep (#4079).
#
# A4's cases isolate on DISTANCE: every liar there claims to have travelled
# further than its series allows. This section isolates on DIRECTION, and the
# isolation it needs is the mirror one — every row below claims a move the
# window's extrema can comfortably support, so A4 structurally declines it, and
# what is wrong is which WAY the claim points. A case A4 also retires proves
# nothing about A7, so each one asserts `unobserved_retired == 0` beside its own
# counter rather than trusting the seed.
#
# Every row is fresh (1 hour), ungraded and price-possible for A/A2/A3's sake,
# exactly as A4's are.
# ---------------------------------------------------------------------------


def test_a_claim_the_dated_comparison_contradicts_is_retired() -> None:
    """THE ship, on rows — and its own sibling is the control.

    The production specimen, off `/api/feed?limit=100` at 07:48Z on 2026-09-19:
    "S&P 500 (SPY) closes above ___ on September 21?". The `$745` leg served a
    chip reading DOWN 7.5 points while the outcome had been observed at 0.49
    eighteen hours earlier and was trading at 0.895 — it had RISEN forty points.

    `sibling` is the `$740` leg of the same market, written by the same poll
    against a basis of the same age, whose +39.5 claim matches its +39.5 dated
    move exactly. It is in this seed deliberately and it is the assertion that
    matters most: a predicate that takes `$740` with `$745` is indiscriminate
    rather than working, and no single-row fixture can tell those apart.

    Both legs claim a move the window's extrema support, so A4 declines both.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "liar",
                    "open",
                    1,
                    -0.075,
                    0.075,
                    None,
                    0.895,
                    [(18, 0.49), (12, 0.60), (1, 0.97)],
                ),
                (
                    "sibling",
                    "open",
                    1,
                    0.395,
                    0.395,
                    None,
                    0.895,
                    [(18, 0.50), (12, 0.60), (1, 0.97)],
                ),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert after["liar"][0] is None, (
        "a chip claiming a 7.5-point FALL survived on an outcome observed at "
        "0.49 eighteen hours ago and trading at 0.895 now — a forty-point "
        f"RISE. This is #4079's dated half verbatim. got {after['liar'][0]}"
    )
    assert after["sibling"][0] == pytest.approx(0.395), (
        "A7 retired the honest leg of the same market. Its +39.5 claim IS its "
        "dated move; sweeping it means the predicate keys on something these "
        f"two legs share rather than on the contradiction. got {after['sibling'][0]}"
    )
    assert result["contradicted_retired"] == 1, (
        "the run must report what it retired under its own counter — folded "
        "into `unobserved_retired`, a direction failure would read as an "
        f"overstatement and point at the wrong writer. got {result}"
    )
    assert result["unobserved_retired"] == 0, (
        "A4 retired this row, so the case proves nothing about A7. Both legs "
        f"claim a move their extrema support. got {result}"
    )


def test_a4_keeps_the_row_a7_retires() -> None:
    """Codex's counterexample (0735Z), which is why A7 is a seventh statement.

    23 h ago 0.40, 1 h ago 0.60, now 0.50. The stored per-write delta is -0.10 —
    a true description of the last write, and one that sits comfortably inside
    the window's extrema, so A4 KEEPS it. Over the day the outcome rose ten
    points. The card reads "down 10 points today" about an outcome that went up.

    Measured on production the same morning: of 149 rows whose sign a dated
    comparison materially contradicts, A4 keeps 143. This is that 96% as a row.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "counterexample",
                    "open",
                    1,
                    -0.10,
                    0.10,
                    None,
                    0.50,
                    [(23, 0.40), (1, 0.60)],
                ),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert result["unobserved_retired"] == 0, (
        "A4 retired the counterexample, which would make A7 redundant on the "
        "one case it was written for. The claimed -0.10 is inside "
        f"[current - hi, current - lo] = [-0.10, 0.10]. got {result}"
    )
    assert after["counterexample"][0] is None, (
        "the row A4 provably cannot see survived the run. A7 is the only "
        f"statement in the task that can reach it. got {after['counterexample'][0]}"
    )
    assert result["contradicted_retired"] == 1, f"got {result}"


def test_a_basis_too_fresh_to_date_a_day_is_refused() -> None:
    """"We never looked that far back" is not "it went the other way".

    A7 refutes a claim about TODAY by comparing against the oldest price it
    observed in the window. If that price is two hours old the comparison is a
    statement about two hours, and using it to delete a claim about the day
    would be A7's own error pointed the other way — so the statement declines,
    exactly as A4 declines a row it never observed (gotcha #53).

    `fresh_basis` contradicts hard — claims -0.20, rose 0.30 — and must survive
    anyway. It is the row that proves `DATED_BASIS_MIN_AGE_HOURS` is load-bearing
    rather than decorative: delete that bound and this test reddens.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "fresh_basis",
                    "open",
                    1,
                    -0.20,
                    0.20,
                    None,
                    0.60,
                    [(2, 0.30), (1, 0.80)],
                ),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert after["fresh_basis"][0] == pytest.approx(-0.20), (
        "A7 deleted a claim about the day using a two-hour-old baseline. The "
        "whole point of the statement is that a comparison must be dated "
        f"before it can refute a dated claim. got {after['fresh_basis'][0]}"
    )
    assert result["contradicted_retired"] == 0, f"got {result}"


def test_a_multi_source_outcome_is_refused() -> None:
    """A7 subtracts a blend from ONE row, so it may not run on a blend.

    A4 compares `current_probability` against the EXTREMA of its constituents
    and argues a blend lies between them. A7 compares it against a single
    constituent's row, and that argument is not available to it: a systematic
    offset between two same-scale sources could manufacture a sign on its own.

    `two_books` is that hazard with honest inputs — kalshi and polymarket
    disagreeing by five points across the window while the outcome genuinely
    fell. Measured 2026-09-19, every one of the 2,794 rows in scope was
    single-source, so this guard costs zero coverage today and exists for the
    day one appears.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "two_books",
                    "open",
                    1,
                    -0.10,
                    0.10,
                    None,
                    0.50,
                    [
                        (21, 0.45, "kalshi"),
                        (20, 0.40, "polymarket"),
                        # 0.60 rather than the 0.55 a first draft used: at 0.55
                        # the window's high makes the -0.10 claim an
                        # OVERSTATEMENT and A4 retires the row, which would have
                        # left this case green with `obs.sources = 1` deleted.
                        (1, 0.60, "kalshi"),
                    ],
                ),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert after["two_books"][0] == pytest.approx(-0.10), (
        "A7 condemned a delta using one source's row as the baseline for a "
        "price built from two. Drop `obs.sources = 1` and this reddens. "
        f"got {after['two_books'][0]}"
    )
    assert result["contradicted_retired"] == 0, f"got {result}"


def test_a_vigged_series_can_never_condemn_a_direction_either() -> None:
    """A4's scale guard, restated for A7 so the two cannot drift apart.

    `FuturesOddsSnapshot.probability` is one book's RAW vig-inclusive number and
    #1844 shipped an all-red movers row for months by subtracting it from a
    blend. A de-vigged consensus sits BELOW every raw row it came from, so a
    sportsbook baseline biases `current - basis` downward — which on A7 is not a
    magnitude error but a manufactured DIRECTION.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "vigged",
                    "open",
                    1,
                    0.10,
                    0.10,
                    None,
                    0.50,
                    [(20, 0.58, "draftkings"), (1, 0.60, "draftkings")],
                ),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert after["vigged"][0] == pytest.approx(0.10), (
        "A7 read a vigged sportsbook row as a baseline for a de-vigged price "
        f"and invented a contradiction out of the vig. got {after['vigged'][0]}"
    )
    assert result["contradicted_retired"] == 0, f"got {result}"


def test_a_sub_floor_dated_move_is_not_a_contradiction() -> None:
    """The materiality bar is the CARD FLOOR, and it is the same floor.

    A dated move of half a point in the other direction is noise, not a
    refutation: below `MODERATE_MOVEMENT_THRESHOLD` no chip is drawn at all, so
    A7 will not delete a claim on the strength of a move too small to have been
    worth showing. Anything left standing that is genuinely overstated is A4's.

    `noise` drifted down half a point against an up-claim; `material` fell the
    full floor against the same claim. One survives, one does not, and the only
    difference between them is the size of the dated move.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "noise",
                    "open",
                    1,
                    0.08,
                    0.08,
                    None,
                    0.500,
                    # The 0.42 leg is not decoration: without a low that far
                    # down, a +0.08 claim OVERSTATES what the window supports
                    # and A4 sweeps both rows, so the pair would prove nothing
                    # about where A7's materiality bar sits.
                    [(20, 0.505), (10, 0.42), (1, 0.52)],
                ),
                (
                    "material",
                    "open",
                    1,
                    0.08,
                    0.08,
                    None,
                    0.500,
                    # 0.520 puts the dated fall EXACTLY on the floor, which is
                    # also the boundary A4's comment warns about: bound as a
                    # float the floor is 0.0200000000000000004 and this row
                    # fails its own test.
                    [(20, 0.520), (10, 0.42), (1, 0.53)],
                ),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert after["noise"][0] == pytest.approx(0.08), (
        "a half-point drift deleted a movement claim. Below the card floor "
        f"there is no chip to be wrong. got {after['noise'][0]}"
    )
    assert after["material"][0] is None, (
        "a full-floor fall against an up-claim survived, so the materiality "
        f"bar is not the floor it is documented as. got {after['material'][0]}"
    )
    assert result["contradicted_retired"] == 1, f"got {result}"


def test_a_claim_below_the_card_floor_is_out_of_scope() -> None:
    """The `abs(delta) >= floor` bound is a COST bound, and it is load-bearing.

    Below `MODERATE_MOVEMENT_THRESHOLD` no card names a mover and no chip is
    drawn, so a sub-floor delta cannot reach a reader to lie to them. Bounding
    the statement there is what keeps a snapshot join affordable on a ten-minute
    beat — it is A4's reasoning, inherited deliberately so the two statements
    sweep the same population.

    `tiny` is contradicted exactly as hard as the specimens above — it claims a
    fall on an outcome that rose ten points — and survives only because the
    claim itself is one point. Drop the bound and the statement starts scanning
    the millions of sub-floor rows that no reader can see; this is the row that
    says so.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "tiny",
                    "open",
                    1,
                    -0.01,
                    0.01,
                    None,
                    0.50,
                    [(20, 0.40), (1, 0.55)],
                ),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert after["tiny"][0] == pytest.approx(-0.01), (
        "A7 swept a claim below the floor that decides whether a chip is drawn "
        f"at all. got {after['tiny'][0]}"
    )
    assert result["contradicted_retired"] == 0, f"got {result}"


def test_an_understated_claim_pointing_the_right_way_survives() -> None:
    """One-directional, in A4's sense: A7 fires on sign, never on magnitude.

    `shy` claims +10 points on an outcome that actually rose 40. The claim is
    wrong about the size and RIGHT about the direction, and A7 leaves it alone —
    the asymmetry is the safety property. A delta-blind writer nudging the price
    further the way the claim already points moves the dated change further onto
    the claim's own side, so drift can never turn an honest caption into a swept
    one.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "shy",
                    "open",
                    1,
                    0.10,
                    0.10,
                    None,
                    0.90,
                    [(20, 0.50), (1, 0.88)],
                ),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))

    assert after["shy"][0] == pytest.approx(0.10), (
        "A7 retired a claim that understates a move it got the direction of. "
        "That is a magnitude disagreement, which this statement does not "
        f"judge. got {after['shy'][0]}"
    )
    assert result["contradicted_retired"] == 0, f"got {result}"


def test_the_contradicted_sweep_is_bounded_and_takes_the_biggest_first() -> None:
    """A bounded run retires the loudest liar, like A, A2 and A4 before it.

    The batch exists to keep a regressing writer from blowing the task's 120 s
    `soft_time_limit`, and when it binds the run must spend it on the claim a
    reader is most likely to have seen — `ORDER BY abs(delta) DESC`.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                # Both highs are set so the claim is not ALSO an overstatement:
                # at 0.75 and 0.62 A4 retires both rows and the batch bound
                # under test never runs.
                ("loud", "open", 1, -0.30, 0.30, None, 0.60, [(20, 0.40), (1, 0.90)]),
                ("quiet", "open", 1, -0.05, 0.05, None, 0.60, [(20, 0.40), (1, 0.65)]),
            ]
        )
    )
    result = _run_task(contradicted_batch=1)
    after = asyncio.run(_read(ids))

    assert result["contradicted_retired"] == 1, (
        f"the batch bound was not honoured. got {result['contradicted_retired']}"
    )
    assert after["loud"][0] is None, (
        "the bounded run spent its one slot on the smaller claim. "
        f"got loud={after['loud'][0]} quiet={after['quiet'][0]}"
    )
    assert after["quiet"][0] == pytest.approx(-0.05), (
        f"got quiet={after['quiet'][0]}"
    )


def test_the_superset_identity_survives_the_contradicted_sweep() -> None:
    """A7 clears a delta, so B and C must re-derive the bound over what is left.

    `/api/futures/movers` ranks a pool by `max_movement_24h`, and LAT-P108
    proved that pool is a superset of the answer only while
    `max_movement_24h == MAX(ABS(probability_change_24h))` holds. A7 is the
    fifth statement able to falsify it between the sweep and B.
    """
    asyncio.run(
        _reset_and_seed(
            [
                ("liar", "open", 1, -0.30, 0.30, None, 0.60, [(20, 0.40), (1, 0.90)]),
                ("honest", "open", 1, 0.11, 0.30, None, 0.60, [(20, 0.49), (1, 0.58)]),
            ]
        )
    )
    _run_task()
    violations = asyncio.run(_identity_holds())

    assert violations == [], (
        "the dated-direction sweep left a market maximum describing a delta it "
        f"had just cleared: {violations}"
    )


# ---------------------------------------------------------------------------
# #8594 — A8 banks a basis only if it was a PRICE, not a last trade across an
# empty book.
#
# A7 only deletes, so a junk observation can cost it a retirement at worst. A8
# hands its basis to a card that prints `current - basis` beside the word
# "today", so the one place its bar is stricter than A7's is the book: the basis
# is the oldest in-window observation whose spread sits inside the empty-book
# rail (`FEED_PHANTOM_MIN_SPREAD`, 0.20), a row with no book at all still
# counts, and an outcome with neither banks nothing.
# ---------------------------------------------------------------------------


async def _read_bank(ids) -> dict:
    """`{label: banked cell or None}` — the A8 cell for each case's outcome."""
    import json

    from sqlalchemy import text

    engine = _engine()
    out = {}
    async with engine.connect() as conn:
        for label, (market_id, outcome_id) in ids.items():
            cell = (
                await conn.execute(
                    text(
                        "SELECT market_metadata -> 'dated_movement_basis' "
                        "FROM futures_markets WHERE id = :i"
                    ),
                    {"i": market_id},
                )
            ).scalar()
            if isinstance(cell, str):
                cell = json.loads(cell)
            out[label] = (cell or {}).get(str(outcome_id))
    await engine.dispose()
    return out


def test_a_stale_last_trade_on_an_empty_book_is_never_banked_as_a_basis() -> None:
    """Both production specimens, and the tight-book control beside them.

    `thune` — Polymarket outcome 234680080, "Next US Senate Minority Leader?",
    served on Discover page one 2026-09-25 09:47Z as "John Thune down 66 points
    today". Every observation for a day was 0.84 on an 11c/88c book (a stale
    last trade stored as the price); when the book tightened to 14c/22c the
    price became 0.18. The only tight observation is two hours old — too fresh
    to date a day — so nothing may be banked.

    `impeachment` — Polymarket 112926 "December 31, 2027" (outcome 231225166):
    basis 0.74 on a 58c/88c book, and the book never came inside 30c all day.

    `control` — the same shape on a real book (0.60 @ 59c/61c -> 0.30 @
    29c/31c). It must still bank 0.60, or the predicate is refusing moves rather
    than refusing junk. Every delta here survives A4 and A7 (each claim sits
    inside its extrema and points the way its basis does), so the bank is the
    only thing that can silence the two specimens.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "thune",
                    "open",
                    1,
                    -0.66,
                    0.66,
                    None,
                    0.18,
                    [
                        (20, 0.84, "polymarket", 0.11, 0.88),
                        (16, 0.84, "polymarket", 0.11, 0.87),
                        (15, 0.84, "polymarket", 0.06, 0.85),
                        (2, 0.18, "polymarket", 0.14, 0.22),
                    ],
                ),
                (
                    "impeachment",
                    "open",
                    1,
                    -0.41,
                    0.41,
                    None,
                    0.17,
                    [
                        (23, 0.74, "polymarket", 0.58, 0.88),
                        (16, 0.58, "polymarket", 0.53, 0.89),
                        (12, 0.58, "polymarket", 0.52, 0.89),
                        (1, 0.17, "polymarket", 0.17, 0.87),
                    ],
                ),
                (
                    "control",
                    "open",
                    1,
                    -0.30,
                    0.30,
                    None,
                    0.30,
                    [
                        (20, 0.60, "polymarket", 0.59, 0.61),
                        (1, 0.30, "polymarket", 0.29, 0.31),
                    ],
                ),
            ]
        )
    )
    result = _run_task()
    after = asyncio.run(_read(ids))
    bank = asyncio.run(_read_bank(ids))

    # Preconditions: the deltas are still standing, so the bank is the arm
    # under test and not an earlier statement that already silenced the row.
    assert after["thune"][0] == pytest.approx(-0.66), f"got {after} / {result}"
    assert after["impeachment"][0] == pytest.approx(-0.41), f"got {after} / {result}"
    assert after["control"][0] == pytest.approx(-0.30), f"got {after} / {result}"

    assert bank["thune"] is None, (
        "A8 banked a basis that was a stale 0.84 last trade on an 11c/88c book, "
        "so the card prints 'down 66 points today' about a move no book ever "
        f"quoted. got {bank['thune']}"
    )
    assert bank["impeachment"] is None, (
        "A8 banked 0.74 off a 58c/88c book; the card prints '-57'. "
        f"got {bank['impeachment']}"
    )
    assert bank["control"] is not None and float(bank["control"][0]) == pytest.approx(0.60), (
        "the tight-book control lost its basis — the predicate is refusing "
        f"real moves, not empty books. got {bank['control']}"
    )


def test_the_basis_is_the_oldest_PRICED_observation_not_a_blanket_refusal() -> None:
    """A wide early book does not cost an outcome a later, tight, dated basis.

    20 h ago 0.84 on an 11c/88c book (junk); 14 h ago 0.80 on 79c/81c (a price,
    and old enough to date a day); now 0.18. The honest dated move is 0.18 -
    0.80, so the bank must hold 0.80 and its 14 h stamp — never 0.84, and never
    nothing.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "late_tight",
                    "open",
                    1,
                    -0.62,
                    0.62,
                    None,
                    0.18,
                    [
                        (20, 0.84, "polymarket", 0.11, 0.88),
                        (14, 0.80, "polymarket", 0.79, 0.81),
                        (1, 0.18, "polymarket", 0.17, 0.19),
                    ],
                ),
            ]
        )
    )
    _run_task()
    bank = asyncio.run(_read_bank(ids))
    cell = bank["late_tight"]

    assert cell is not None, "the tight 14 h observation was not banked at all"
    assert float(cell[0]) == pytest.approx(0.80), (
        f"the bank took the wide-book 0.84 rather than the priced 0.80. got {cell}"
    )
    observed = datetime.fromisoformat(cell[1].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - observed).total_seconds() / 3600.0
    assert 13.5 < age < 14.5, (
        "the banked instant is not the priced observation's — a basis paired "
        f"with another row's stamp dates the wrong move. age={age:.2f}h cell={cell}"
    )


def test_a_row_with_no_book_still_banks_and_a_one_sided_book_does_not() -> None:
    """Where the price test draws its line on NULLs, and on the rail itself.

    `no_book` — both sides NULL: the source never publishes a book, so its
    price is its price and it banks exactly as every pre-#8594 row did.
    `one_sided` — a bid is missing and an ask is present: the source recorded a
    book and it was empty on a side, the wide-book case at its limit.
    `on_the_rail` — 39c/59c, a spread of exactly 0.20, which the rail calls
    empty (`>=`). Bound as a Decimal, so the equality is exact.
    `inside_the_rail` — 40c/59c, 0.19, which banks. It is also what keeps the
    three refusals honest: every case is single-source (`kalshi`, the rig's
    default bookmaker), so a refusal here is the book and never `sources = 2`.
    """
    ids = asyncio.run(
        _reset_and_seed(
            [
                ("no_book", "open", 1, -0.30, 0.30, None, 0.30, [(20, 0.60), (1, 0.30)]),
                (
                    "one_sided",
                    "open",
                    1,
                    -0.30,
                    0.30,
                    None,
                    0.30,
                    [(20, 0.60, "kalshi", None, 0.61), (1, 0.30)],
                ),
                (
                    "on_the_rail",
                    "open",
                    1,
                    -0.30,
                    0.30,
                    None,
                    0.20,
                    [(20, 0.50, "kalshi", 0.39, 0.59), (1, 0.20)],
                ),
                (
                    "inside_the_rail",
                    "open",
                    1,
                    -0.30,
                    0.30,
                    None,
                    0.20,
                    [(20, 0.50, "kalshi", 0.40, 0.59), (1, 0.20)],
                ),
            ]
        )
    )
    _run_task()
    after = asyncio.run(_read(ids))
    bank = asyncio.run(_read_bank(ids))

    for label in ids:
        assert after[label][0] is not None, f"precondition: {label} delta retired: {after}"
    assert bank["no_book"] is not None and float(bank["no_book"][0]) == pytest.approx(0.60), (
        "a row with no book stopped banking — every source that never publishes "
        f"one just lost its dated evidence. got {bank['no_book']}"
    )
    assert bank["one_sided"] is None, (
        f"a book empty on one side was banked as a price. got {bank['one_sided']}"
    )
    assert bank["on_the_rail"] is None, (
        "a spread of exactly 0.20 was banked; the rail calls that book empty. "
        f"got {bank['on_the_rail']}"
    )
    assert bank["inside_the_rail"] is not None, (
        f"a 19c spread was refused — the rail moved. got {bank['inside_the_rail']}"
    )


def test_a_market_whose_every_outcome_is_refused_loses_its_old_bank() -> None:
    """The refusal must reach the page on the next run, not a day later.

    Market 112926, 2026-09-25: its bank held ONE cell, the 0.74 junk basis for
    the specimen outcome. A refusal written only into A8's WHERE produces no row
    for a market with nothing left to bank, and A9 does not touch it (the market
    still makes a claim), so the old cell would have gone on serving "-57"
    until the reader's age bound retired it.

    `stale_bank` is that shape, seeded with the pre-fix cell. `never_banked` is
    in claim scope with nothing to bank and no prior cell — it must not be
    given an empty one (that would ride the size-capped load artifact for
    nothing). `control` still banks.
    """
    import json

    from sqlalchemy import text

    ids = asyncio.run(
        _reset_and_seed(
            [
                (
                    "stale_bank",
                    "open",
                    1,
                    -0.41,
                    0.41,
                    None,
                    0.17,
                    [
                        (23, 0.74, "polymarket", 0.58, 0.88),
                        (1, 0.17, "polymarket", 0.17, 0.87),
                    ],
                ),
                (
                    "never_banked",
                    "open",
                    1,
                    -0.41,
                    0.41,
                    None,
                    0.17,
                    [
                        (23, 0.74, "polymarket", 0.58, 0.88),
                        (1, 0.17, "polymarket", 0.17, 0.87),
                    ],
                ),
                ("control", "open", 1, -0.30, 0.30, None, 0.30, [(20, 0.60), (1, 0.30)]),
            ]
        )
    )

    async def _seed_old_bank():
        engine = _engine()
        market_id, outcome_id = ids["stale_bank"]
        old = {
            "other_key": "kept",
            "dated_movement_basis": {str(outcome_id): [0.74, "2026-09-24T11:50:27Z"]},
        }
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE futures_markets SET market_metadata = CAST(:m AS jsonb) WHERE id = :i"),
                {"m": json.dumps(old), "i": market_id},
            )
        await engine.dispose()

    async def _metadata(market_id):
        engine = _engine()
        async with engine.connect() as conn:
            cell = (
                await conn.execute(
                    text("SELECT market_metadata FROM futures_markets WHERE id = :i"),
                    {"i": market_id},
                )
            ).scalar()
        await engine.dispose()
        return json.loads(cell) if isinstance(cell, str) else cell

    asyncio.run(_seed_old_bank())
    _run_task()
    after = asyncio.run(_read(ids))
    stale_meta = asyncio.run(_metadata(ids["stale_bank"][0])) or {}
    never_meta = asyncio.run(_metadata(ids["never_banked"][0])) or {}
    bank = asyncio.run(_read_bank(ids))

    assert after["stale_bank"][0] == pytest.approx(-0.41), (
        f"precondition: the claim still stands, so A9 cannot be the arm. got {after}"
    )
    assert "dated_movement_basis" not in stale_meta, (
        "a market whose every outcome is now refused kept its old bank, so the "
        f"junk 0.74 basis keeps printing '-57'. metadata={stale_meta}"
    )
    assert stale_meta.get("other_key") == "kept", (
        f"removing the bank destroyed the market's other metadata: {stale_meta}"
    )
    assert "dated_movement_basis" not in never_meta, (
        f"an in-scope market with nothing to bank was given an empty cell: {never_meta}"
    )
    assert bank["control"] is not None, f"the control lost its basis: {bank}"
