"""An open-contract leg the socket sees finalize is graded alone. #10022, real Postgres.

The specimen is the CHC–SD Wild Card ``Series Exact Score`` board (Kalshi
``KXMLBSERIESSCORE-26CHCSDWC``), seeded the way production held it at
06:3xZ 2026-10-01: ``CHC20`` graded by the REST sweep, the other three legs
ungraded and still carrying their closing prices. The unit file
(``tests/test_ws_open_contract_settlement_10022.py``) proves the consumer
routes a frame to :func:`grade_open_contract_leg`; this file lets Postgres
answer what that write does, because the two properties that make it safe ride
on SQL a fake cannot see — the authority guard on the leg, and the
``NOT EXISTS`` over sibling legs that decides whether the board resolves, read
inside the same transaction as the leg write.
"""

from __future__ import annotations

import os

import pytest

#: The #7617 step's disposable database, which #8755 and #9588 also reuse.
#: This file drops and creates only the tables it names, after those steps.
DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set DELAY_CONTRACT_DATABASE_URL to run the real-Postgres open-contract "
        "leg-grade contract (CI job `search-recall` provisions a disposable one)"
    ),
)

MARKET = "KXMLBSERIESSCORE-26CHCSDWC"
LEGS = {
    # name: (ticker suffix, closing price, is_winner, resolution_source)
    "SD20": ("SD20", 0.99, None, None),
    "SD21": ("SD21", 0.14, None, None),
    "CHC21": ("CHC21", 0.04, None, None),
    "CHC20": ("CHC20", 0.0, False, "api_settlement"),
}


@pytest.fixture
async def board():
    """(sessionmaker, market_id, {leg: outcome_id}) on a fresh schema."""
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import FuturesMarket, FuturesOutcome, Sport
    from app.services.database import Base

    wanted = [
        Base.metadata.tables[name]
        for name in (
            "sports",
            "teams",
            "venues",
            "events",
            "futures_markets",
            "futures_outcomes",
        )
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        mlb = Sport(key="baseball_mlb", name="MLB")
        session.add(mlb)
        await session.flush()
        market = FuturesMarket(
            source="kalshi",
            external_id=MARKET,
            sport_id=mlb.id,
            name="Series Exact Score: Chicago Cubs vs San Diego",
            status="open",
        )
        session.add(market)
        await session.flush()
        ids = {}
        for name, (suffix, price, won, source) in LEGS.items():
            leg = FuturesOutcome(
                market_id=market.id,
                external_id=f"{MARKET}-{suffix}",
                name=name,
                current_probability=price,
                is_winner=won,
                resolution_source=source,
            )
            session.add(leg)
            await session.flush()
            ids[name] = leg.id
        # The ORM column default (`is_winner=False`) fills an omitted OR None
        # value; the Kalshi poll's rows are NULL (production: SD20/SD21/CHC21),
        # and NULL is what the open-contract admission reads.
        await session.execute(
            update(FuturesOutcome)
            .where(
                FuturesOutcome.market_id == market.id,
                FuturesOutcome.resolution_source.is_(None),
            )
            .values(is_winner=None)
        )
        await session.commit()
        market_id = market.id

    yield maker, market_id, ids

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
    await engine.dispose()


async def _grade(maker, market_id, outcome_id, won, *, result=None):
    from app.tasks.ws_open_contracts import grade_open_contract_leg

    async with maker() as session:
        graded, resolved = await grade_open_contract_leg(
            session, market_id=market_id, outcome_id=outcome_id,
            state="finalized",
            result=result if result is not None else ("yes" if won else "no"),
        )
        await session.commit()
    return graded, resolved


async def _read(maker, market_id):
    from sqlalchemy import select

    from app.models.models import FuturesMarket, FuturesOutcome

    async with maker() as session:
        market = (
            await session.execute(
                select(FuturesMarket.status, FuturesMarket.settled_at).where(
                    FuturesMarket.id == market_id
                )
            )
        ).one()
        legs = {
            r.name: (r.is_winner, r.resolution_source, float(r.current_probability))
            for r in (
                await session.execute(
                    select(
                        FuturesOutcome.name,
                        FuturesOutcome.is_winner,
                        FuturesOutcome.resolution_source,
                        FuturesOutcome.current_probability,
                    ).where(FuturesOutcome.market_id == market_id)
                )
            ).all()
        }
    return market, legs


@needs_postgres
async def test_a_losing_leg_grades_itself_and_crowns_no_sibling(board):
    maker, market_id, ids = board

    graded, resolved = await _grade(maker, market_id, ids["SD21"], False)

    assert graded is not None and graded.id == ids["SD21"]
    assert resolved is None
    market, legs = await _read(maker, market_id)
    assert market.status == "open" and market.settled_at is None
    assert legs["SD21"] == (False, "api_settlement", 0.0)
    # The two-sided handler would have written True on all three of these.
    assert legs["SD20"] == (None, None, 0.99)
    assert legs["CHC21"] == (None, None, 0.04)
    assert legs["CHC20"] == (False, "api_settlement", 0.0)


@needs_postgres
async def test_three_losers_still_crown_nobody(board):
    maker, market_id, ids = board

    await _grade(maker, market_id, ids["SD21"], False)
    _graded, resolved = await _grade(maker, market_id, ids["CHC21"], False)

    assert resolved is None
    market, legs = await _read(maker, market_id)
    assert market.status == "open"
    assert [n for n, (won, _s, _p) in legs.items() if won] == []


@needs_postgres
async def test_the_board_resolves_on_its_last_leg_and_not_before(board):
    maker, market_id, ids = board

    for name, won in (("SD21", False), ("CHC21", False)):
        _g, resolved = await _grade(maker, market_id, ids[name], won)
        assert resolved is None, f"resolved early on {name}"
    graded, resolved = await _grade(maker, market_id, ids["SD20"], True)

    assert graded is not None
    assert resolved is not None and resolved.id == market_id
    assert resolved.settled_at is not None
    market, legs = await _read(maker, market_id)
    assert market.status == "resolved"
    assert legs["SD20"] == (True, "api_settlement", 1.0)
    assert [n for n, (won, _s, _p) in legs.items() if won] == ["SD20"]


@needs_postgres
async def test_a_redelivered_frame_changes_nothing(board):
    maker, market_id, ids = board

    await _grade(maker, market_id, ids["SD21"], False)
    graded, resolved = await _grade(maker, market_id, ids["SD21"], False)

    assert (graded, resolved) == (None, None)


@needs_postgres
async def test_a_venue_grade_is_never_flipped_by_a_frame(board):
    """CHC20 already carries the sweep's ``api_settlement`` loss."""
    maker, market_id, ids = board

    graded, _resolved = await _grade(maker, market_id, ids["CHC20"], True)

    assert graded is None
    _market, legs = await _read(maker, market_id)
    assert legs["CHC20"] == (False, "api_settlement", 0.0)


@needs_postgres
async def test_a_guess_is_replaced_and_does_not_count_as_graded(board):
    """A price-based guess is not the venue's answer: the frame overwrites it,
    and until then it cannot let the board resolve."""
    from sqlalchemy import update

    from app.models.models import FuturesOutcome

    maker, market_id, ids = board
    async with maker() as session:
        await session.execute(
            update(FuturesOutcome)
            .where(FuturesOutcome.id == ids["SD20"])
            .values(is_winner=False, resolution_source="multi_max_prob")
        )
        await session.commit()

    for name in ("SD21", "CHC21"):
        _g, resolved = await _grade(maker, market_id, ids[name], False)
        assert resolved is None, "a guessed sibling must not count as graded"
    graded, resolved = await _grade(maker, market_id, ids["SD20"], True)

    assert graded is not None and resolved is not None
    _market, legs = await _read(maker, market_id)
    assert legs["SD20"] == (True, "api_settlement", 1.0)


@needs_postgres
async def test_a_frame_for_another_market_id_writes_nothing(board):
    """The leg write is keyed on BOTH ids, so a stale map entry cannot grade a
    row that has moved to another market."""
    maker, market_id, ids = board

    graded, resolved = await _grade(maker, market_id + 1, ids["SD21"], False)

    assert (graded, resolved) == (None, None)
    _market, legs = await _read(maker, market_id)
    assert legs["SD21"] == (None, None, 0.14)


@needs_postgres
async def test_a_scalar_declaration_writes_nothing(board):
    """``finalized``/``scalar`` settles on a number, not a side (#7987): no
    grade, no price change, no board flip."""
    maker, market_id, ids = board

    graded, resolved = await _grade(maker, market_id, ids["SD21"], False, result="scalar")

    assert (graded, resolved) == (None, None)
    _market, legs = await _read(maker, market_id)
    assert legs["SD21"] == (None, None, 0.14)
