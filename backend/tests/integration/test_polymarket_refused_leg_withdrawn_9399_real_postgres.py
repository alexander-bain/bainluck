"""#9399 through the REAL hourly-poll writer, against real Postgres.

The unit file (`tests/test_polymarket_refused_leg_withdrawn_9399.py`) answers the
withdrawal's SELECT from a fake. This one runs the SQL: two passes of
``_process_event_batch`` over the Hurricane Nolo field (Gamma event 1075583).

    pass 1 (10:50Z-shaped)  Category 5 quotes a tight book around 0.92 -> stored 0.92
    pass 2 (16:0xZ, verbatim) Category 5 outcomePrices 0.205 on 0.09/0.32, last 0.92
                              -> both prices refused; before #9399 the row kept 0.92

After pass 2 the 0.92 must be gone, Category 4 must carry this pass's 0.72, and a
leg whose stored price its current book does NOT refute must keep it.
"""

from __future__ import annotations

import os

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #9399 poll writer against real "
            "Postgres (CI job `search-recall` provides one)"
        ),
    ),
]

EVENT_ID = "1075583"
CAT3, CAT4, CAT5 = "0xnolo_cat3", "0xnolo_cat4", "0xnolo_cat5"


@pytest.fixture
async def engine(monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    import app.tasks.base as task_base
    from app.services.database import Base

    eng = create_async_engine(DB_URL)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(task_base, "DATABASE_URL", DB_URL)
    yield eng
    await eng.dispose()


def _leg(cid, n, *, prices, bid, ask, last):
    from app.services.polymarket_api import PolymarketMarket

    return PolymarketMarket(
        condition_id=cid,
        question=f"Will Hurricane Nolo reach Category {n}?",
        group_item_title=f"Category {n}",
        outcomes=["Yes", "No"],
        outcome_prices=prices,
        best_bid=bid,
        best_ask=ask,
        last_trade_price=last,
        volume_24h=5_000.0,
    )


def _nolo(cat5, cat3=None):
    from app.services.polymarket_api import PolymarketEvent

    return PolymarketEvent(
        id=EVENT_ID,
        title="How strong will Nolo be?",
        neg_risk=True,
        markets=[
            _leg(CAT4, 4, prices=[0.785, 0.215], bid=0.65, ask=0.92, last=0.72),
            cat5,
            cat3 or _leg(CAT3, 3, prices=[0.025, 0.975], bid=0.02, ask=0.03, last=0.025),
        ],
    )


async def _poll(event):
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.tasks.polymarket import _process_event_batch
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american

    class _Counting(dict):
        def __missing__(self, key):
            return 0

    stats = _Counting(errors=[], by_category={})
    await _process_event_batch(
        [event], stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
        pg_insert, probability_to_american, compute_market_tier,
    )
    assert not stats["errors"], stats["errors"]
    return stats


async def _stored(engine) -> dict:
    from sqlalchemy import text

    async with engine.connect() as conn:
        rows = (
            await conn.execute(text(
                "SELECT o.external_id, o.current_probability::float, "
                "       o.current_american_odds "
                "  FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
                " WHERE m.source = 'polymarket' AND m.external_id = :eid"
            ), {"eid": EVENT_ID})
        ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


async def test_the_refuted_092_is_withdrawn_and_the_field_names_the_venues_favorite(engine):
    tight_092 = _leg(CAT5, 5, prices=[0.92, 0.08], bid=0.91, ask=0.93, last=0.92)
    await _poll(_nolo(tight_092))
    before = await _stored(engine)
    assert before[CAT5][0] == pytest.approx(0.92), "pass 1 must store the specimen's 0.92"

    refused = _leg(CAT5, 5, prices=[0.205, 0.795], bid=0.09, ask=0.32, last=0.92)
    stats = await _poll(_nolo(refused))
    after = await _stored(engine)

    assert stats["legs_withdrawn_book_refuted"] == 1
    assert after[CAT5] == (None, None)
    assert after[CAT4][0] == pytest.approx(0.72)
    priced = {k: v[0] for k, v in after.items() if v[0] is not None}
    assert max(priced, key=priced.get) == CAT4


async def test_a_refused_leg_whose_stored_price_the_book_supports_keeps_it(engine):
    """Control: same refusal shape, but the stored 0.20 sits inside 0.09/0.32."""
    inside = _leg(CAT5, 5, prices=[0.20, 0.80], bid=0.19, ask=0.21, last=0.20)
    await _poll(_nolo(inside))
    refused = _leg(CAT5, 5, prices=[0.205, 0.795], bid=0.09, ask=0.32, last=0.92)
    stats = await _poll(_nolo(refused))

    assert stats["legs_withdrawn_book_refuted"] == 0
    assert (await _stored(engine))[CAT5][0] == pytest.approx(0.20)


async def test_a_graded_leg_is_never_withdrawn(engine):
    from sqlalchemy import text

    tight_092 = _leg(CAT5, 5, prices=[0.92, 0.08], bid=0.91, ask=0.93, last=0.92)
    await _poll(_nolo(tight_092))
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE futures_outcomes SET resolution_source = 'api_settlement' "
            " WHERE external_id = :cid"
        ), {"cid": CAT5})
    refused = _leg(CAT5, 5, prices=[0.205, 0.795], bid=0.09, ask=0.32, last=0.92)
    stats = await _poll(_nolo(refused))

    assert stats["legs_withdrawn_book_refuted"] == 0
    assert (await _stored(engine))[CAT5][0] == pytest.approx(0.92)
