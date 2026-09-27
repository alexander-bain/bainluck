"""#9083 executed against a REAL PostgreSQL: Phase 0c and the repair rail.

Two claims, and the database has to answer both:

1. **Phase 0c no longer promotes an empty Polymarket book.** The shipped
   ``PHASE_0C_REPAIR_SQL`` is run over NULL-opening legs. The specimen pair
   (bid NULL / ask 1.00 / last 0.01, and its Under at bid 0.00 / ask NULL) stays
   NULL. A leg that opened empty and later got a two-sided book takes the later
   price. The positive control, a two-sided book, is promoted in the same
   execution, so a Phase 0c that did nothing cannot pass.
2. **The rail withdraws what was already promoted, and only that.** Specimen pair
   → NULL (it leaves the page and the curve); opened-empty-then-traded → the real
   price; the Griffin Jax control (two-sided 0.45/0.51) and a Kalshi row are never
   examined; a row whose opening did not come from the empty snapshot
   (provenance) is never examined. Phase 0c run after the repair re-promotes
   nothing, and the restore puts every row back.

Numeric equality (``bad.probability = fo.opening_probability``) and timestamp
equality (``bad.captured_at = fo.opening_captured_at``) are the safety clauses,
and both are database comparisons. A mock cannot see them.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9083 gate "
        "(CI job `search-recall` provides one)"
    ),
)

FIRST_PITCH = datetime(2026, 9, 26, 23, 15, 0, tzinfo=timezone.utc)
CAPTURE = FIRST_PITCH - timedelta(minutes=7)  # 23:08:11Z in production
SETTLED = FIRST_PITCH + timedelta(hours=4, minutes=12)

PM_MARKET = 9208301        # Trea Turner H+R+RBI O/U 0.5 (resolved)
TRADED_MARKET = 9208302    # opened empty, traded before first pitch
JAX_MARKET = 9208303       # Griffin Jax Strikeouts O/U 4.5 — the control
KALSHI_MARKET = 9208304
NULL_MARKET = 9208305      # Phase 0c's own population

TURNER_OVER = 9208401
TURNER_UNDER = 9208402
TRADED_OVER = 9208403
TRADED_UNDER = 9208404
JAX_OVER = 9208405
KALSHI_LEG = 9208406
NO_PROVENANCE = 9208407    # empty snapshot exists, but the opening is from elsewhere
COPY = 9208408             # calibration_probability is a copy of the bad opening
# NULL-opening legs for Phase 0c
P0C_EMPTY_OVER = 9208501
P0C_EMPTY_UNDER = 9208502
P0C_TRADED = 9208503
P0C_CONTROL = 9208504

ALL_IDS = (
    TURNER_OVER, TURNER_UNDER, TRADED_OVER, TRADED_UNDER, JAX_OVER, KALSHI_LEG,
    NO_PROVENANCE, COPY, P0C_EMPTY_OVER, P0C_EMPTY_UNDER, P0C_TRADED, P0C_CONTROL,
)

#: The specimen's two books, exactly as stored on production.
OVER_EMPTY = (0.01, None, 1.0, 0.01)   # (probability, bid, ask, last)
UNDER_EMPTY = (0.99, 0.0, None, 0.99)
#: A real two-sided book, 30 minutes later but still before first pitch.
OVER_REAL = (0.72, 0.70, 0.74, 0.72)
UNDER_REAL = (0.28, 0.26, 0.30, 0.28)
JAX_BOOK = (0.48, 0.45, 0.51, 0.48)
#: The settlement snapshot, after `resolution_date`: never an opening.
OVER_SETTLED = (0.999, 0.99, 1.0, 0.999)


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


@pytest.fixture
async def session():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base
    from app.tasks.repair_polymarket_empty_book_openings import BAK_TABLE

    engine = create_async_engine(_asyncpg_url(DB_URL))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(f"DROP TABLE IF EXISTS {BAK_TABLE}"))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.execute(text(f"DROP TABLE IF EXISTS {BAK_TABLE}"))
        await s.commit()
    await engine.dispose()


async def _seed(session):
    """The corpus, through the ORM (client-side defaults apply)."""
    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome

    for mid, source in (
        (PM_MARKET, "polymarket"),
        (TRADED_MARKET, "polymarket"),
        (JAX_MARKET, "polymarket"),
        (KALSHI_MARKET, "kalshi"),
        (NULL_MARKET, "polymarket"),
    ):
        session.add(
            FuturesMarket(
                id=mid,
                source=source,
                external_id=f"seed-market-{mid}",
                name=f"seed {mid}",
                llm_sport_category="baseball",
                status="resolved",
                event_id=None,
                commence_time=FIRST_PITCH,
                resolution_date=FIRST_PITCH,
            )
        )
    await session.flush()

    # (id, market, opening, opening_captured_at, calibration, is_winner)
    outcomes = (
        (TURNER_OVER, PM_MARKET, 0.01, CAPTURE, None, True),
        (TURNER_UNDER, PM_MARKET, 0.99, CAPTURE, None, False),
        (TRADED_OVER, TRADED_MARKET, 0.01, CAPTURE, None, True),
        (TRADED_UNDER, TRADED_MARKET, 0.99, CAPTURE, None, False),
        (JAX_OVER, JAX_MARKET, 0.48, CAPTURE, None, True),
        (KALSHI_LEG, KALSHI_MARKET, 0.01, CAPTURE, None, True),
        # Opening 0.30 stamped at CAPTURE, but the snapshot at CAPTURE says 0.01:
        # the opening did not come from that book.
        (NO_PROVENANCE, PM_MARKET, 0.30, CAPTURE, None, False),
        (COPY, PM_MARKET, 0.01, CAPTURE, 0.01, True),
        (P0C_EMPTY_OVER, NULL_MARKET, None, None, None, True),
        (P0C_EMPTY_UNDER, NULL_MARKET, None, None, None, False),
        (P0C_TRADED, NULL_MARKET, None, None, None, True),
        (P0C_CONTROL, NULL_MARKET, None, None, None, True),
    )
    for oid, mid, opening, opened_at, cal, won in outcomes:
        session.add(
            FuturesOutcome(
                id=oid,
                market_id=mid,
                external_id=f"seed-{oid}",
                name=f"leg {oid}",
                opening_probability=opening,
                opening_source=None if opening is None else "first_snapshot",
                opening_captured_at=opened_at,
                calibration_probability=cal,
                is_winner=won,
                resolution_source="api_settlement",
            )
        )
    await session.flush()

    later = CAPTURE + timedelta(minutes=5)
    snapshots = (
        (TURNER_OVER, "polymarket", OVER_EMPTY, CAPTURE),
        (TURNER_OVER, "polymarket", OVER_SETTLED, SETTLED),
        (TURNER_UNDER, "polymarket", UNDER_EMPTY, CAPTURE),
        (TRADED_OVER, "polymarket", OVER_EMPTY, CAPTURE),
        (TRADED_OVER, "polymarket", OVER_REAL, later),
        (TRADED_UNDER, "polymarket", UNDER_EMPTY, CAPTURE),
        (TRADED_UNDER, "polymarket", UNDER_REAL, later),
        (JAX_OVER, "polymarket", JAX_BOOK, CAPTURE),
        # Byte-identical book on another venue: Polymarket's rule must not reach it.
        (KALSHI_LEG, "kalshi", OVER_EMPTY, CAPTURE),
        (NO_PROVENANCE, "polymarket", OVER_EMPTY, CAPTURE),
        (COPY, "polymarket", OVER_EMPTY, CAPTURE),
        (P0C_EMPTY_OVER, "polymarket", OVER_EMPTY, CAPTURE),
        (P0C_EMPTY_UNDER, "polymarket", UNDER_EMPTY, CAPTURE),
        (P0C_TRADED, "polymarket", OVER_EMPTY, CAPTURE),
        (P0C_TRADED, "polymarket", OVER_REAL, later),
        (P0C_CONTROL, "polymarket", JAX_BOOK, CAPTURE),
    )
    for oid, book, (prob, bid, ask, last), at in snapshots:
        session.add(
            FuturesOddsSnapshot(
                outcome_id=oid,
                bookmaker=book,
                probability=prob,
                yes_bid=bid,
                yes_ask=ask,
                last_price=last,
                captured_at=at,
            )
        )
    await session.commit()


async def _row(session, oid):
    """``(curve_price, opening, opening_source, opening_captured_at, calibration)``."""
    from sqlalchemy import text

    got = (
        await session.execute(
            text(
                "SELECT COALESCE(calibration_probability, opening_probability), "
                "opening_probability, opening_source, opening_captured_at, "
                "calibration_probability FROM futures_outcomes WHERE id = :oid"
            ),
            {"oid": oid},
        )
    ).one()
    f = lambda v: None if v is None else float(v)  # noqa: E731
    return (f(got[0]), f(got[1]), got[2], got[3], f(got[4]))


async def _phase_0c(session):
    from sqlalchemy import text

    from app.tasks.backfill_winners import PHASE_0C_REPAIR_SQL

    await session.execute(text(PHASE_0C_REPAIR_SQL))
    await session.commit()


@needs_postgres
async def test_phase_0c_does_not_promote_an_empty_polymarket_book(session):
    await _seed(session)
    await _phase_0c(session)

    assert (await _row(session, P0C_CONTROL))[1] == 0.48, (
        "positive control not promoted — Phase 0c did not run, so nothing below "
        "can testify"
    )
    assert (await _row(session, P0C_EMPTY_OVER))[:3] == (None, None, None), (
        "Phase 0c promoted a 1c trade on a book with no bid and the ask at $1.00"
    )
    assert (await _row(session, P0C_EMPTY_UNDER))[:3] == (None, None, None)


@needs_postgres
async def test_phase_0c_skips_the_empty_snapshot_not_the_leg(session):
    await _seed(session)
    await _phase_0c(session)

    curve, opening, source, opened_at, _ = await _row(session, P0C_TRADED)
    assert (opening, source) == (0.72, "first_snapshot")
    assert opened_at == CAPTURE + timedelta(minutes=5)


@needs_postgres
async def test_the_specimen_pair_leaves_the_page_and_the_curve(session):
    from app.tasks.repair_polymarket_empty_book_openings import repair

    await _seed(session)
    assert (await _row(session, TURNER_OVER))[0] == 0.01, "seed precondition"

    result = await repair(session, apply=True)

    assert result["terminal"] == "changed"
    for oid in (TURNER_OVER, TURNER_UNDER, COPY):
        assert await _row(session, oid) == (None, None, None, None, None), oid


@needs_postgres
async def test_a_leg_that_traded_before_first_pitch_takes_that_price(session):
    from app.tasks.repair_polymarket_empty_book_openings import repair

    await _seed(session)
    await repair(session, apply=True)

    later = CAPTURE + timedelta(minutes=5)
    assert await _row(session, TRADED_OVER) == (0.72, 0.72, "first_snapshot", later, None)
    assert await _row(session, TRADED_UNDER) == (0.28, 0.28, "first_snapshot", later, None)


@needs_postgres
async def test_controls_are_never_examined(session):
    from app.tasks.repair_polymarket_empty_book_openings import repair

    await _seed(session)
    before = {oid: await _row(session, oid) for oid in (JAX_OVER, KALSHI_LEG, NO_PROVENANCE)}

    plan = await repair(session, apply=False)
    planned = {r["outcome_id"] for r in plan["samples"]} | {
        r["outcome_id"] for r in plan["refusals"]
    }
    assert planned == {TURNER_OVER, TURNER_UNDER, TRADED_OVER, TRADED_UNDER, COPY}

    await repair(session, apply=True)
    for oid, row in before.items():
        assert await _row(session, oid) == row, oid


@needs_postgres
async def test_phase_0c_after_the_repair_re_promotes_nothing(session):
    """Fixed point: the withdrawn pair is NULL and back in Phase 0c's population."""
    from app.tasks.repair_polymarket_empty_book_openings import repair

    await _seed(session)
    await repair(session, apply=True)
    await _phase_0c(session)

    assert (await _row(session, P0C_CONTROL))[1] == 0.48, "Phase 0c did not run"
    for oid in (TURNER_OVER, TURNER_UNDER):
        assert (await _row(session, oid))[1] is None, oid
    assert (await _row(session, TRADED_OVER))[1] == 0.72


@needs_postgres
async def test_the_restore_puts_every_row_back(session):
    from app.tasks.repair_polymarket_empty_book_openings import repair, restore

    await _seed(session)
    before = {oid: await _row(session, oid) for oid in ALL_IDS}

    applied = await repair(session, apply=True)
    assert applied["changed"] == 5
    assert (await repair(session, apply=True))["terminal"] == "nothing_to_do"

    restored = await restore(session, apply=True)
    assert restored["restored"] == 5
    after = {oid: await _row(session, oid) for oid in ALL_IDS}
    assert after == before


@needs_postgres
async def test_paging_is_by_markets_examined(session):
    from app.tasks.repair_polymarket_empty_book_openings import repair

    await _seed(session)
    first = await repair(session, apply=False, limit=1)
    assert first["markets_examined"] == 1
    assert first["next_after_id"] == PM_MARKET
    assert first["scan_exhausted"] is False
    assert {r["outcome_id"] for r in first["samples"]} == {TURNER_OVER, TURNER_UNDER, COPY}

    second = await repair(session, apply=False, limit=1, after_id=first["next_after_id"])
    assert second["next_after_id"] == TRADED_MARKET
    assert {r["outcome_id"] for r in second["samples"]} == {TRADED_OVER, TRADED_UNDER}

    tail = await repair(session, apply=False, limit=100, after_id=TRADED_MARKET)
    assert tail["scan_exhausted"] is True
    assert tail["in_scope"] == 0
