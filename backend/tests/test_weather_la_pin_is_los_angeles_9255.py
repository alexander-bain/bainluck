"""#9255 — the /weather Los Angeles pin shows Los Angeles, not Manila.

`_resolve_city` took the first alias that was a SUBSTRING of the market name,
and "la" is the fourth alias. Every "Highest temperature in …" market whose
city contains the letters "la" was filed under Los Angeles; `get_cities` then
kept the most-bucketed ladder, which on 2026-09-28 was Manila's (market
62689937) — the LA panel read 91°F over Manila's forecast, and eight cities
with coordinates never reached the map.

The names below are production's, verbatim, from the 124 open temperature
markets of 2026-09-28 ~01:10Z.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import (  # noqa: E402
    Base,
    FuturesMarket,
    FuturesOddsSnapshot,
    FuturesOutcome,
)
from app.routes.weather import CITY_COORDS, _resolve_city, get_cities  # noqa: E402

SWALLOWED_BY_LA = {
    "Highest temperature in Manila on September 29?": "manila",
    "Highest temperature in Dallas on Sep 27, 2026?": "dallas",
    "Highest temperature in Atlanta on Sep 27, 2026?": "atlanta",
    "Highest temperature in Milan on September 29?": "milan",
    "Highest temperature in Kuala Lumpur on September 29?": "kuala_lumpur",
    "Highest temperature in Las Vegas on Sep 27, 2026?": "las_vegas",
    "Highest temperature in Oklahoma City on Sep 27, 2026?": "okc",
    "Highest temperature in Philadelphia on Sep 27, 2026?": "philadelphia",
}

# Names that resolved correctly before and must not move.
UNCHANGED = {
    "Highest temperature in Los Angeles on Sep 27, 2026?": "la",
    "Highest temperature in Los Angeles on September 29?": "la",
    "Highest temperature in NYC on September 29?": "nyc",
    "Highest temperature in Washington DC on Sep 27, 2026?": "dc",
    "Highest temperature in Seoul (Incheon) on September 29?": "seoul",
    "Highest temperature in Sao Paulo on September 29?": "sao_paulo",
    "Highest temperature in Panama City on September 29?": "panama_city",
    "Highest temperature in Mexico City on September 28?": "mexico_city",
    "Highest temperature in San Antonio on Sep 27, 2026?": "san_antonio",
}


@pytest.mark.parametrize("name,city_id", sorted(SWALLOWED_BY_LA.items()))
def test_a_city_containing_la_is_its_own_city(name, city_id):
    assert _resolve_city(name) == city_id
    # Each has a pin to land on, so fixing the filing puts it on the map.
    assert city_id in CITY_COORDS


@pytest.mark.parametrize("name,city_id", sorted(UNCHANGED.items()))
def test_names_that_resolved_correctly_still_do(name, city_id):
    assert _resolve_city(name) == city_id


def test_a_bare_la_still_reads_as_los_angeles():
    assert _resolve_city("Highest temperature in LA on Sep 27, 2026?") == "la"


def test_a_city_we_do_not_map_stays_unresolved():
    # "San Diego" / "Guangzhou" have no alias: no pin, never a neighbour's.
    assert _resolve_city("Highest temperature in San Diego on September 29?") is None
    assert _resolve_city("Highest temperature in Guangzhou on September 29?") is None


# ── the served payload ─────────────────────────────────────────────────────

NOW = datetime.now(timezone.utc)
FRESH = NOW - timedelta(hours=1)


@pytest.fixture(autouse=True)
def _sqlite_returns_aware_datetimes():
    fields = ("resolution_date", "updated_at", "created_at", "last_updated")

    def _restore_utc(target, _context):  # pragma: no cover - sqlite shim
        for field in fields:
            value = getattr(target, field, None)
            if isinstance(value, datetime) and value.tzinfo is None:
                setattr(target, field, value.replace(tzinfo=timezone.utc))

    event.listen(FuturesMarket, "load", _restore_utc)
    event.listen(FuturesOutcome, "load", _restore_utc)
    try:
        yield
    finally:
        event.remove(FuturesMarket, "load", _restore_utc)
        event.remove(FuturesOutcome, "load", _restore_utc)


class AsyncDB:
    def __init__(self, session: Session):
        self._session = session

    async def execute(self, query):
        return self._session.execute(query)


def _market(session, mid, source, name, ladder):
    session.add(
        FuturesMarket(
            id=mid,
            source=source,
            external_id=f"{source}-temp-{mid}",
            name=name,
            status="open",
            llm_sport_category="weather",
            resolution_date=NOW + timedelta(days=1),
            updated_at=FRESH,
        )
    )
    for i, (label, p) in enumerate(ladder):
        session.add(
            FuturesOutcome(
                id=mid * 100 + i,
                market_id=mid,
                external_id=f"o-{mid}-{i}",
                name=label,
                current_probability=p,
                last_updated=FRESH,
            )
        )


def test_the_la_pin_serves_los_angeles_and_manila_gets_its_own_pin():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng,
        tables=[
            FuturesMarket.__table__,
            FuturesOutcome.__table__,
            FuturesOddsSnapshot.__table__,
        ],
    )
    session = Session(eng)
    # Manila carries MORE buckets, which is exactly why it won the LA pin.
    _market(
        session,
        62689937,
        "polymarket",
        "Highest temperature in Manila on September 29?",
        [
            (f"{t}°C", p)
            for t, p in zip(range(28, 39), [0.01] * 5 + [0.52, 0.26] + [0.01] * 4)
        ],
    )
    _market(
        session,
        62734103,
        "kalshi",
        "Highest temperature in Los Angeles on Sep 27, 2026?",
        [
            ("73°F or below", 0.1),
            ("74-75°F", 0.55),
            ("76-77°F", 0.3),
            ("78°F or above", 0.05),
        ],
    )
    session.commit()

    cities = {c["id"]: c for c in asyncio.run(get_cities(AsyncDB(session)))}

    assert cities["la"]["marketId"] == 62734103
    assert cities["la"]["srcs"] == ["kalshi"]
    assert cities["la"]["high"]["mode"] == 74.5
    assert cities["manila"]["marketId"] == 62689937
    assert cities["manila"]["high"]["unit"] == "C"
