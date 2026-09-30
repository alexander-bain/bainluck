"""#9394 — a Polymarket winner crowned by a PRICE is re-graded by the VENUE.

## The defect, as a reader saw it

The settled TOUR Championship page crowned Chris Gotterup. Scottie Scheffler
won: Kalshi `KXPGATOUR-TOC26-SSCH` result=yes, Polymarket Gamma event 890355
Scheffler `outcomePrices ["1","0"]` / Gotterup `["0","1"]`, DataGolf
is_winner. Our Polymarket winner market 59433935 held ONE of the venue's 51
legs — Gotterup, captured 2026-08-22 at 0.99 off a 0.01/0.99 book and never
re-read — and `_backfill_from_current_probability`'s Pass 1 crowned him
(`clean_resolution`, every stored leg at an extreme). The golf settled field
takes `won` from any source's `is_winner`, so the page served two champions
and put Gotterup first.

## Why the venue never corrected it

`clean_resolution` is OVERWRITABLE (`resolution_authority`) — a hard result may
supersede it. The one rail that holds the hard result for Polymarket,
`_backfill_polymarket_winners_from_api`, selected only markets holding a row
that is neither `api_settlement` NOR `clean_resolution`. So the moment Pass 1
stamped every row of a field, Gamma was never asked about it again. The fix
adds one arm: a winner crowned only by `clean_resolution` (resolution date
inside the rail's 90-day bound) is selected.

## Why this is a real-Postgres gate

The fix lives in the HAVING of the rail's population SELECT. Every existing
driver of this function answers that SELECT with a recording double that
matches the SQL string and returns hand-picked rows, so none of them could see
whether a market is selected at all — which is the whole defect. Here the
shipped statement runs against rows in a private schema, the Gamma answer is a
fake of the venue's own payload for 890355, and the assertions read the table
the settled page reads. The last class feeds the rows back through the golf
route's own settled-field assembler, so the claim is about the served field,
not about a column.

Run locally (PG14 is fine — no ORM `create_all` here):

    createdb bl_9394
    SEARCH_TEST_DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost:5432/bl_9394" \\
      python3 -m pytest tests/integration/test_price_crowned_pm_winner_venue_regrade_9394_pg.py -v -rs
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.services.polymarket_api as poly_api_mod
import app.tasks.backfill_winners as bw
import app.tasks.redis_state as redis_state

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9394 "
            "price-crown venue re-grade gate (CI job: search-recall)"
        ),
    ),
]

_SCHEMA = "pm_price_crown_gate_9394"

EVENT_ID = "890355"
GOTTERUP_CID = "0xcd180f2f4a30dc5fe75fe5321e707699d327f65942f549b71cc9c73b8091f5ad"
SCHEFFLER_CID = "0xbfd3e6f4ec0a12c1f19e657627cc7fd9fbd9521e356d50f53704949e46fda6e3"

#: The specimen and its production id.
SPECIMEN = 59433935
#: Venue-verified field: a winner graded `api_settlement`, a loser stamped
#: `clean_resolution`. Already right; the rail must leave it alone.
VERIFIED = 59433990
#: A price crown older than the rail's 90-day bound (Gamma ages out).
AGED = 59433991
#: A field Pass 1 graded all-losers — no winner to verify. Selected before the
#: fix? No, and still no: the new arm is about CROWNS only.
ALL_LOSERS = 59433992

#: Gamma `GET /events/890355`, reduced to the keys the rail reads. Values are the
#: venue's own (read 2026-09-28): both legs closed, Scheffler Yes=1.
GAMMA_890355 = {
    "id": EVENT_ID,
    "title": "PGA Tour: TOUR Championship Winner",
    "closed": True,
    "markets": [
        {
            "conditionId": GOTTERUP_CID,
            "groupItemTitle": "Chris Gotterup",
            "question": "Will Chris Gotterup win the 2026 TOUR Championship?",
            "outcomePrices": '["0", "1"]',
            "closed": True,
        },
        {
            "conditionId": SCHEFFLER_CID,
            "groupItemTitle": "Scottie Scheffler",
            "question": "Will Scottie Scheffler win the 2026 TOUR Championship?",
            "outcomePrices": '["1", "0"]',
            "closed": True,
        },
    ],
}


class _FakeRedis:
    def __init__(self):
        self.store: dict = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = str(value)

    def delete(self, key):
        return 1 if self.store.pop(key, None) is not None else 0

    def sadd(self, key, *vals):
        return None

    def smembers(self, key):
        return set()

    def expire(self, key, ttl):
        return True


@pytest.fixture
async def engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {_SCHEMA}"))
    await admin.dispose()

    eng = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": _SCHEMA}}
    )
    async with eng.begin() as conn:
        # The columns the rail reads and writes, plus the model's NOT NULL set
        # for every raw-INSERT seed (`test_pg_gate_seed_completeness.py`).
        await conn.execute(text("""
            CREATE TABLE futures_markets (
                id integer PRIMARY KEY,
                source varchar(50) NOT NULL,
                external_id varchar(200) NOT NULL,
                name varchar(300) NOT NULL,
                category varchar(50) NOT NULL,
                mutually_exclusive boolean NOT NULL,
                status varchar(20) NOT NULL,
                group_type varchar(30),
                resolution_date timestamptz,
                market_metadata jsonb
            )
        """))
        await conn.execute(text("""
            CREATE TABLE futures_outcomes (
                id serial PRIMARY KEY,
                market_id integer NOT NULL REFERENCES futures_markets(id),
                external_id varchar(200),
                name varchar(300) NOT NULL,
                current_probability numeric(10, 6),
                is_winner boolean,
                resolution_source varchar(40),
                last_updated timestamptz,
                price_changed_at timestamptz
            )
        """))
        await conn.execute(text("""
            INSERT INTO futures_markets
                (id, source, external_id, name, category, mutually_exclusive,
                 status, group_type, resolution_date, market_metadata)
            VALUES
                (59433935, 'polymarket', '890355',
                 'PGA Tour: TOUR Championship Winner', 'golf', true, 'resolved',
                 'negrisk', now() - interval '29 days',
                 '{"polymarket_event_id": "890355"}'::jsonb),
                (59433990, 'polymarket', '890390', 'Verified Field Winner',
                 'golf', true, 'resolved', 'negrisk',
                 now() - interval '29 days',
                 '{"polymarket_event_id": "890390"}'::jsonb),
                (59433991, 'polymarket', '890391', 'Aged Field Winner',
                 'golf', true, 'resolved', 'negrisk',
                 now() - interval '120 days',
                 '{"polymarket_event_id": "890391"}'::jsonb),
                (59433992, 'polymarket', '890392', 'All Losers Field',
                 'golf', true, 'resolved', 'negrisk',
                 now() - interval '29 days',
                 '{"polymarket_event_id": "890392"}'::jsonb)
        """))
        await conn.execute(text("""
            INSERT INTO futures_outcomes
                (market_id, external_id, name, current_probability, is_winner,
                 resolution_source)
            VALUES
                -- the specimen, exactly as production stores it
                (59433935, :gcid, 'Chris Gotterup', 0.990000, true,
                 'clean_resolution'),
                (59433990, '0xv1', 'Verified Winner', 1.000000, true,
                 'api_settlement'),
                (59433990, '0xv2', 'Verified Loser', 0.000000, false,
                 'clean_resolution'),
                (59433991, '0xa1', 'Aged Crown', 0.990000, true,
                 'clean_resolution'),
                (59433992, '0xl1', 'Loser One', 0.010000, false,
                 'clean_resolution'),
                (59433992, '0xl2', 'Loser Two', 0.020000, false,
                 'clean_resolution')
        """), {"gcid": GOTTERUP_CID})
    yield eng
    await eng.dispose()
    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
    await admin.dispose()


@pytest.fixture
def run_rail(engine, monkeypatch):
    """Drive the real Phase-3 rail, scheduled form, against the gate schema."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(engine, expire_on_commit=False)
    rc = _FakeRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: rc)

    class _CM:
        async def __aenter__(self):
            self.s = maker()
            return await self.s.__aenter__()

        async def __aexit__(self, *a):
            return await self.s.__aexit__(*a)

    monkeypatch.setattr(bw, "get_task_session", lambda: _CM())

    asked: list[str] = []

    class _Service:
        def __init__(self, *a, **k):
            pass

        async def get_market_by_condition(self, cid):
            return None

        async def get_event_by_id(self, eid):
            asked.append(str(eid))
            return GAMMA_890355 if str(eid) == EVENT_ID else None

        async def close(self):
            return None

    monkeypatch.setattr(poly_api_mod, "PolymarketAPIService", _Service)

    async def _run():
        stats = await bw._backfill_polymarket_winners_from_api(limit=500)
        return stats, asked

    return _run


async def _rows(engine, market_id):
    async with engine.connect() as conn:
        res = await conn.execute(
            text("""
                SELECT name, external_id, current_probability, is_winner,
                       resolution_source
                  FROM futures_outcomes WHERE market_id = :m ORDER BY id
            """),
            {"m": market_id},
        )
        return [dict(r._mapping) for r in res]


class TestTheVenueGradesAPriceCrown:
    async def test_the_specimen_is_asked_about(self, run_rail):
        _stats, asked = await run_rail()
        # Before #9394 this list held only the markets with a non-clean row, so
        # 890355 was never fetched and Gotterup stayed crowned forever.
        assert EVENT_ID in asked

    async def test_gotterup_is_graded_by_the_venue_as_a_loser(
        self, engine, run_rail
    ):
        await run_rail()
        (row,) = await _rows(engine, SPECIMEN)
        assert row["name"] == "Chris Gotterup"
        assert row["is_winner"] is False
        assert row["resolution_source"] == "api_settlement"
        assert float(row["current_probability"]) == 0.0

    async def test_a_one_leg_field_mints_no_champion(self, engine, run_rail):
        # #6110's floor is kept: a field we hold one leg of is not a field, so
        # the missing Scheffler is NOT minted here. The page's champion comes
        # from Kalshi + DataGolf (next class); fixing the mint floor is not this
        # ship.
        stats, _ = await run_rail()
        names = [r["name"] for r in await _rows(engine, SPECIMEN)]
        assert names == ["Chris Gotterup"]
        assert stats["champion_mint"].get("refused_not_a_field") == 1


class TestWhatTheRailMustNotTouch:
    async def test_a_venue_verified_field_is_not_refetched(
        self, engine, run_rail
    ):
        before = await _rows(engine, VERIFIED)
        _stats, asked = await run_rail()
        assert "890390" not in asked
        assert await _rows(engine, VERIFIED) == before

    async def test_a_price_crown_past_the_90_day_bound_is_left(
        self, engine, run_rail
    ):
        before = await _rows(engine, AGED)
        _stats, asked = await run_rail()
        assert "890391" not in asked
        assert await _rows(engine, AGED) == before

    async def test_an_all_losers_field_is_not_selected(self, engine, run_rail):
        # Unchanged behaviour: the new arm keys on a CROWN, so a field Pass 1
        # graded with no winner stays out of the population.
        before = await _rows(engine, ALL_LOSERS)
        _stats, asked = await run_rail()
        assert "890392" not in asked
        assert await _rows(engine, ALL_LOSERS) == before

    async def test_a_graded_specimen_leaves_the_population(
        self, engine, run_rail
    ):
        await run_rail()
        _stats, asked = await run_rail()
        # Second run: Gotterup is api_settlement now, so nothing re-selects it.
        assert asked.count(EVENT_ID) == 1


def _market(mid, name, source, outcomes):
    return SimpleNamespace(
        id=mid,
        name=name,
        source=source,
        outcomes=[
            SimpleNamespace(
                name=o["name"],
                current_probability=o["current_probability"],
                calibration_probability=None,
                opening_probability=None,
                current_american_odds=None,
                is_winner=o["is_winner"],
                resolution_source=o.get("resolution_source"),
            )
            for o in outcomes
        ],
    )


#: The two other winner markets for the tournament, as production stores them
#: (Kalshi 59490790 api_settlement, DataGolf 59485745 leaderboard).
_KALSHI = [
    {"name": "Scottie Scheffler", "current_probability": 1.0, "is_winner": True},
    {"name": "Chris Gotterup", "current_probability": 0.0, "is_winner": False},
]
_DATAGOLF = [
    {"name": "Scottie Scheffler", "current_probability": 0.182267, "is_winner": True},
    {"name": "Chris Gotterup", "current_probability": 0.0354, "is_winner": False},
]


async def _served_field(engine):
    from app.routes.golf import _assemble_completed_winner_field

    pm = await _rows(engine, SPECIMEN)
    golfers, *_ = _assemble_completed_winner_field([
        # Production's order: the served payload's first-seen prices are
        # Gotterup 0.99 (Polymarket) and Scheffler 0.18 (DataGolf), which is
        # what put the wrong champion at rank 1.
        _market(SPECIMEN, "PGA Tour: TOUR Championship Winner", "polymarket", pm),
        _market(59485745, "TOUR Championship - Winner", "datagolf", _DATAGOLF),
        _market(59490790, "TOUR Championship Winner", "kalshi", _KALSHI),
    ])
    return golfers


class TestTheSettledPageNamesTheRealWinner:
    async def test_before_the_rail_the_field_crowns_two_and_leads_with_gotterup(
        self, engine
    ):
        # The production RED, reproduced from the stored rows: two champions,
        # and the hero (rank 1) is the wrong one.
        golfers = await _served_field(engine)
        assert [g["name"] for g in golfers if g.get("won")] == [
            "Chris Gotterup", "Scottie Scheffler",
        ]
        assert golfers[0]["name"] == "Chris Gotterup"

    async def test_after_the_rail_scheffler_is_the_only_champion(
        self, engine, run_rail
    ):
        await run_rail()
        golfers = await _served_field(engine)
        assert [g["name"] for g in golfers if g.get("won")] == ["Scottie Scheffler"]
        assert golfers[0]["name"] == "Scottie Scheffler"
        assert golfers[0]["probability"] == 1.0
        gott = next(g for g in golfers if g["name"] == "Chris Gotterup")
        assert gott["probability"] == 0.0
        assert gott["sources"]["polymarket"] == 0.0
