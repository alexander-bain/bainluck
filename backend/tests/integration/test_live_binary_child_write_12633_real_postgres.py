"""A live binary quote cannot overwrite a newer read, grade or identity."""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FuturesMarket, FuturesOutcome
from app.tasks.prediction_market_matching import _write_live_polymarket_child
from tests.integration.test_polymarket_refused_leg_withdrawn_9399_real_postgres import (
    engine as engine,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.environ.get("SEARCH_TEST_DATABASE_URL"),
        reason="requires the isolated PostgreSQL search test database",
    ),
]
CONDITION = "0x12633_live_child"


async def seed(engine):
    stamp = datetime.now(timezone.utc) - timedelta(minutes=90)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        market = FuturesMarket(
            source="polymarket",
            external_id=CONDITION,
            name="Named spread",
            status="open",
        )
        session.add(market)
        await session.flush()
        outcome = FuturesOutcome(
            market_id=market.id,
            external_id=CONDITION + "_yes",
            name="Wake Forest",
            current_probability=0.19,
            current_yes_bid=0.18,
            current_yes_ask=0.20,
            opening_probability=0.235,
            last_updated=stamp,
            price_changed_at=stamp,
        )
        session.add(outcome)
        await session.commit()
        return outcome.id, market.id, stamp


def quote_values():
    return {
        "current_probability": 0.83,
        "current_yes_bid": 0.82,
        "current_yes_ask": 0.84,
        "current_american_odds": -488,
        "probability_change_24h": 0.64,
        "last_updated": datetime.now(timezone.utc),
    }


async def test_success_is_not_followed_by_an_unguarded_orm_flush(engine):
    oid, _, stamp = await seed(engine)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        outcome = await session.get(FuturesOutcome, oid)
        grade_before = (outcome.is_winner, outcome.resolution_source)
        assert await _write_live_polymarket_child(
            session, outcome, CONDITION, quote_values()
        )
        assert outcome not in session.dirty
        assert outcome.current_probability == 0.83
        assert outcome.price_changed_at > stamp
        assert (outcome.is_winner, outcome.resolution_source) == grade_before
        await session.commit()
    async with AsyncSession(engine) as session:
        outcome = await session.get(FuturesOutcome, oid)
        assert float(outcome.current_probability) == 0.83
        assert float(outcome.opening_probability) == 0.235
        assert outcome.last_updated > stamp
        assert outcome.price_changed_at > stamp
        assert (outcome.is_winner, outcome.resolution_source) == grade_before


@pytest.mark.parametrize("probability", [0.19, 0.19000001])
async def test_unchanged_stored_price_keeps_its_move_time(engine, probability):
    oid, _, stamp = await seed(engine)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        outcome = await session.get(FuturesOutcome, oid)
        values = {**quote_values(), "current_probability": probability}
        assert await _write_live_polymarket_child(session, outcome, CONDITION, values)
        assert outcome.price_changed_at == stamp
        assert outcome.last_updated > stamp
        assert outcome not in session.dirty
        await session.commit()
    async with AsyncSession(engine) as session:
        outcome = await session.get(FuturesOutcome, oid)
        assert outcome.price_changed_at == stamp
        assert outcome.last_updated > stamp


@pytest.mark.parametrize(
    "mutation",
    [
        "same_price_read",
        "price_time",
        "price",
        "book",
        "name",
        "winner",
        "loser",
        "closed_market",
        "market_identity",
    ],
)
async def test_a_concurrent_writer_or_grade_wins(engine, mutation):
    oid, mid, stamp = await seed(engine)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        outcome = await session.get(FuturesOutcome, oid)
        changes = {
            "same_price_read": {"last_updated": stamp + timedelta(seconds=1)},
            "price_time": {"price_changed_at": stamp + timedelta(seconds=1)},
            "price": {"current_probability": 0.21},
            "book": {"current_yes_ask": 0.22},
            "name": {"name": "Another team"},
            "winner": {"is_winner": True},
            "loser": {"is_winner": False, "resolution_source": "api_settlement"},
        }
        async with engine.begin() as other:
            if mutation in ("closed_market", "market_identity"):
                values = (
                    {"status": "resolved"}
                    if mutation == "closed_market"
                    else {"external_id": "0xother"}
                )
                await other.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == mid)
                    .values(**values)
                )
            else:
                await other.execute(
                    update(FuturesOutcome)
                    .where(FuturesOutcome.id == oid)
                    .values(**changes[mutation])
                )
        assert not await _write_live_polymarket_child(
            session, outcome, CONDITION, quote_values()
        )
        assert outcome not in session.dirty
        await session.commit()
    async with engine.connect() as conn:
        actual = await conn.scalar(
            select(FuturesOutcome.current_probability).where(FuturesOutcome.id == oid)
        )
        assert float(actual) == (0.21 if mutation == "price" else 0.19)


async def test_rollback_preserves_the_prior_price_and_observation(engine):
    oid, _, stamp = await seed(engine)
    async with AsyncSession(engine) as session:
        outcome = await session.get(FuturesOutcome, oid)
        assert await _write_live_polymarket_child(
            session, outcome, CONDITION, quote_values()
        )
        await session.rollback()
    async with AsyncSession(engine) as session:
        outcome = await session.get(FuturesOutcome, oid)
        assert float(outcome.current_probability) == 0.19
        assert outcome.last_updated == stamp
