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


# ---------------------------------------------------------------------------
# #10298 — the same writer, reached through the non-negRisk GAME branch (C1 + C2)
# ---------------------------------------------------------------------------
#
# Lions–Packers (Polymarket game market 61040985) printed "Packers 53%" over a
# 0.15/0.52 book. Two passes of the real poll over a game event: pass 1 stores a
# moneyline, pass 2 serves the specimen book. Production writer of 0.53: UNKNOWN —
# this is the admitted failure shape, not a claim about which writer stored it.

GAME_ID = "61040985"
ML, SPREAD = "0xlp_ml", "0xlp_spread"


def _game_leg(cid, question, *, prices, bid, ask, last, title=None):
    from app.services.polymarket_api import PolymarketMarket

    return PolymarketMarket(
        condition_id=cid,
        question=question,
        group_item_title=title,
        outcomes=["Packers", "Lions"] if title is None else ["Yes", "No"],
        outcome_prices=prices,
        best_bid=bid,
        best_ask=ask,
        last_trade_price=last,
        volume_24h=5_000.0,
    )


def _game(moneyline=None, *, spread_price=0.29):
    from app.services.polymarket_api import PolymarketEvent

    spread = _game_leg(
        SPREAD, "Spread: Packers (-5.5)", title="Spread -5.5",
        prices=[spread_price, 1 - spread_price],
        bid=spread_price - 0.01, ask=spread_price + 0.01, last=spread_price,
    )
    markets = [spread] if moneyline is None else [moneyline, spread]
    return PolymarketEvent(
        id=GAME_ID, title="Lions vs. Packers", neg_risk=False, markets=markets,
    )


def _ml(raw, bid, ask, last=None):
    return _game_leg(ML, "Lions vs. Packers", prices=[raw, round(1 - raw, 4)],
                     bid=bid, ask=ask, last=last)


async def _wrapper_rows(engine) -> dict:
    """Every leg of the WRAPPER market (external_id = the Gamma event id)."""
    from sqlalchemy import text

    async with engine.connect() as conn:
        rows = (
            await conn.execute(text(
                "SELECT o.external_id, o.current_probability::float, "
                "       o.current_american_odds, o.opening_probability::float, "
                "       o.price_changed_at, o.last_updated "
                "  FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
                " WHERE m.source = 'polymarket' AND m.external_id = :eid"
            ), {"eid": GAME_ID})
        ).fetchall()
    return {
        r[0]: {"p": r[1], "odds": r[2], "opening": r[3], "changed": r[4], "touched": r[5]}
        for r in rows
    }


async def _other_rows(engine) -> dict:
    """Every outcome NOT under the wrapper — the decomposed per-sub-market rows."""
    from sqlalchemy import text

    async with engine.connect() as conn:
        rows = (
            await conn.execute(text(
                "SELECT m.external_id, o.external_id, o.current_probability::float "
                "  FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
                " WHERE m.external_id <> :eid"
            ), {"eid": GAME_ID})
        ).fetchall()
    return {(r[0], r[1]): r[2] for r in rows}


async def test_10298_a_moneyline_its_own_book_refutes_is_withdrawn(engine):
    """(d)/(f1): stored 0.53, fresh 0.15/0.52 book, raw 0.53 → NULL on the wrapper."""
    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    before = await _wrapper_rows(engine)
    assert before[ML]["p"] == pytest.approx(0.53), "pass 1 must store the 0.53"
    others_before = await _other_rows(engine)

    stats = await _poll(_game(_ml(0.53, 0.15, 0.52, last=0.53), spread_price=0.30))
    after = await _wrapper_rows(engine)

    assert stats["legs_withdrawn_book_refuted"] == 1
    assert (after[ML]["p"], after[ML]["odds"]) == (None, None)
    assert after[ML]["changed"] is not None
    assert after[ML]["changed"] != before[ML]["changed"]
    assert after[ML]["opening"] == before[ML]["opening"]
    assert after[ML]["touched"] == before[ML]["touched"]
    assert after[SPREAD]["p"] == pytest.approx(0.30), "the side leg keeps this pass's write"
    # identity: only the wrapper's own leg — no decomposed row was withdrawn
    others_after = await _other_rows(engine)
    assert {k for k, v in others_after.items() if v is None} <= {
        k for k, v in others_before.items() if v is None
    }


async def test_10298_a_refuted_raw_with_a_surviving_trade_is_still_withdrawn(engine):
    """(f2): last 0.40 sits inside 0.15/0.52 — it is NOT substituted."""
    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    stats = await _poll(_game(_ml(0.53, 0.15, 0.52, last=0.40)))
    after = await _wrapper_rows(engine)
    assert stats["legs_withdrawn_book_refuted"] == 1
    assert after[ML]["p"] is None


async def test_10298_a_raw_price_inside_its_book_is_written_unchanged(engine):
    """(f3) control: 0.40 on 0.38/0.42 → written, nothing withdrawn."""
    await _poll(_game(_ml(0.41, 0.40, 0.42, last=0.41)))
    stats = await _poll(_game(_ml(0.40, 0.38, 0.42, last=0.40)))
    assert stats["legs_withdrawn_book_refuted"] == 0
    assert (await _wrapper_rows(engine))[ML]["p"] == pytest.approx(0.40)


async def test_10298_a_refused_moneyline_whose_stored_price_the_book_supports_keeps_it(engine):
    """Stored 0.40 sits inside 0.15/0.52: the raw 0.53 is refused, the 0.40 retained."""
    await _poll(_game(_ml(0.40, 0.39, 0.41, last=0.40)))
    stats = await _poll(_game(_ml(0.53, 0.15, 0.52, last=0.53)))
    assert stats["legs_withdrawn_book_refuted"] == 0
    assert (await _wrapper_rows(engine))[ML]["p"] == pytest.approx(0.40)


@pytest.mark.parametrize("column, value", [
    ("resolution_source", "'api_settlement'"),
    ("is_winner", "TRUE"),
])
async def test_10298_graded_and_crowned_moneylines_are_never_withdrawn(engine, column, value):
    from sqlalchemy import text

    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    async with engine.begin() as conn:
        await conn.execute(text(
            f"UPDATE futures_outcomes SET {column} = {value} WHERE external_id = :cid"
        ), {"cid": ML})
    stats = await _poll(_game(_ml(0.53, 0.15, 0.52, last=0.53)))
    assert stats["legs_withdrawn_book_refuted"] == 0
    assert (await _wrapper_rows(engine))[ML]["p"] == pytest.approx(0.53)


async def test_10298_a_truncated_payload_withdraws_nothing(engine):
    """Pass 2 omits the moneyline entirely: nothing is inferred from its absence."""
    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    stats = await _poll(_game(None))
    assert stats["legs_withdrawn_book_refuted"] == 0
    assert (await _wrapper_rows(engine))[ML]["p"] == pytest.approx(0.53)


async def test_10298_a_price_changed_underfoot_is_not_withdrawn(engine):
    """CAS: another writer stores 0.20 between the withdrawal's read and its write."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.tasks.polymarket import _refused_leg_books, _withdraw_book_refuted_legs

    await _poll(_game(_ml(0.53, 0.52, 0.54, last=0.53)))
    async with engine.connect() as conn:
        market_id = (await conn.execute(text(
            "SELECT id FROM futures_markets WHERE source='polymarket' AND external_id=:e"
        ), {"e": GAME_ID})).scalar_one()

    books = _refused_leg_books(_game(_ml(0.53, 0.15, 0.52, last=0.53)))
    assert books == {ML: (0.15, 0.52)}

    class _Underfoot:
        """Commits a competing write right after the withdrawal's SELECT."""

        def __init__(self, session):
            self.session, self.fired = session, False

        async def execute(self, statement, *a, **kw):
            result = await self.session.execute(statement, *a, **kw)
            if not self.fired:
                self.fired = True
                async with engine.begin() as other:
                    await other.execute(text(
                        "UPDATE futures_outcomes SET current_probability = 0.20 "
                        " WHERE market_id = :m AND external_id = :c"
                    ), {"m": market_id, "c": ML})
            return result

    async with AsyncSession(engine) as session:
        n = await _withdraw_book_refuted_legs(_Underfoot(session), market_id, books)
        await session.commit()
    assert n == 0
    assert (await _wrapper_rows(engine))[ML]["p"] == pytest.approx(0.20)
