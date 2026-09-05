"""A weather market we hold no price for must never print a number (ux/1075).

Every card on `/weather` prints a probability, and every one of them derives it
from a scan that opens at ``0.0`` (``_highest_prob``). So a market carrying no
priced outcome rendered as a confident red **0%** — indistinguishable from a
market the venue really prices at zero.

Six of those were live on production on 2026-09-05, measured off a phone-width
screenshot and confirmed by db-query (50 of 480 markets passing the shared
weather query held no priced outcome at all):

    Tornadoes         Number of tornadoes in Sep 2026?                    0%
    Tornadoes         Number of tornadoes in Oct 2026?                    0%
    Tornadoes         Number of tornadoes in Nov 2026?                    0%
    Tornadoes         Number of tornadoes in Dec 2026?                    0%
    Seismic activity  Where will a 6.0+ magnitude earthquake occur ...?   0%
    Monthly rainfall  NYC - Dec 2026 ("Above 1 inch of rain")             0%

Zero tornadoes in the United States in September. These tests pin the fix at the
one choke point every card reads through, and — the part that matters — they pin
the distinction the fix must NOT flatten: **absence is not zero, and a genuine
0.0 is a price that keeps its row.**
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, FuturesMarket, FuturesOutcome  # noqa: E402
from app.routes.weather import _open_weather_query, get_rain  # noqa: E402

NOW = datetime.now(timezone.utc)
FRESH = NOW - timedelta(hours=1)
FUTURE = NOW + timedelta(days=30)


class AsyncDB:
    """Minimal async facade over a sync Session.

    ``get_rain`` awaits exactly one thing — ``db.execute(query)`` — so this shim
    runs the REAL statement the route builds against a real (SQLite) database,
    then lets the route's real Python post-processing produce the real payload
    the card reads. Nothing about the answer is mocked.
    """

    def __init__(self, session: Session):
        self._session = session

    async def execute(self, query):
        return self._session.execute(query)


def _market(mid: int, name: str) -> FuturesMarket:
    return FuturesMarket(
        id=mid,
        source="kalshi",
        external_id=f"MKT-{mid}",
        name=name,
        status="open",
        llm_sport_category="weather",
        resolution_date=FUTURE,
        updated_at=FRESH,
    )


def _outcome(oid: int, mid: int, name: str, probability) -> FuturesOutcome:
    return FuturesOutcome(
        id=oid,
        market_id=mid,
        external_id=f"OUT-{oid}",
        name=name,
        current_probability=probability,
    )


@pytest.fixture()
def session():
    """Four markets, one per class the filter has to tell apart."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng, tables=[FuturesMarket.__table__, FuturesOutcome.__table__]
    )
    s = Session(eng)

    # 1. NO OUTCOMES AT ALL — the four live NYC monthly rain markets.
    s.add(_market(1, "Rain in NYC in Dec 2026?"))

    # 2. OUTCOMES, BUT NONE PRICED — the same absence wearing a different shape.
    s.add(_market(2, "Rain in Boston in Dec 2026?"))
    s.add(_outcome(20, 2, "Yes", None))
    s.add(_outcome(21, 2, "No", None))

    # 3. PRICED AT A GENUINE ZERO — a price, and it keeps its row.
    s.add(_market(3, "Rain in Phoenix in Dec 2026?"))
    s.add(_outcome(30, 3, "Yes", 0.0))
    s.add(_outcome(31, 3, "No", 1.0))

    # 4. ORDINARILY PRICED — the control.
    s.add(_market(4, "Rain in Seattle in Dec 2026?"))
    s.add(_outcome(40, 4, "Yes", 0.63))
    s.add(_outcome(41, 4, "No", 0.37))

    s.commit()
    return s


def _names(session) -> set:
    rows = session.execute(_open_weather_query()).scalars().unique().all()
    return {m.name for m in rows}


# ---------------------------------------------------------------------------
# The choke point: one query, every card
# ---------------------------------------------------------------------------


def test_a_market_with_no_outcomes_never_reaches_a_card(session):
    assert "Rain in NYC in Dec 2026?" not in _names(session), (
        "a market with no outcomes reached a card, where it prints 0%"
    )


def test_outcomes_with_no_price_are_still_no_price(session):
    assert "Rain in Boston in Dec 2026?" not in _names(session), (
        "outcomes existing is not the same as a price existing"
    )


def test_a_genuine_zero_is_a_price_and_keeps_its_row(session):
    """The distinction the fix must not flatten.

    Were the predicate written as ``> 0`` instead of ``IS NOT NULL``, this row
    would vanish too — and the page would then hide real markets the venue
    prices at zero, which is a different lie, not a fix.
    """
    assert "Rain in Phoenix in Dec 2026?" in _names(session)


def test_an_ordinarily_priced_market_is_untouched(session):
    assert "Rain in Seattle in Dec 2026?" in _names(session)


# ---------------------------------------------------------------------------
# The chain: what the card actually receives
# ---------------------------------------------------------------------------


def test_the_monthly_rainfall_card_prints_no_fabricated_zero(session):
    """Drive the real route and read the real payload the card renders."""
    payload = asyncio.run(get_rain(AsyncDB(session)))
    monthly = payload["monthly"]
    cities = {row["city"]: row["prob"] for row in monthly}

    assert "NYC" not in cities, (
        f"NYC has no priced monthly market, yet the card was handed {cities}"
    )
    assert "Boston" not in cities
    # The zero-priced city survives and honestly prints its zero.
    assert cities.get("Phoenix") == 0
    assert cities.get("Seattle") == 63


def test_a_card_left_with_nothing_is_handed_an_empty_list_not_a_zero(session):
    """Honest empty beats an invented number.

    With every priced market gone, the route hands back `[]` — which
    `RainForecast.tsx` renders as "No live rainfall markets right now" — rather
    than a row reading 0%.
    """
    session.execute(FuturesOutcome.__table__.delete())
    session.commit()

    payload = asyncio.run(get_rain(AsyncDB(session)))
    assert payload["monthly"] == []
    assert payload["daily"] == []


# ---------------------------------------------------------------------------
# The call-site guard: no section may build its own bypass
# ---------------------------------------------------------------------------


def test_every_weather_section_reads_through_the_shared_query():
    """Six cards, one filter.

    The fix is worth exactly as much as the number of sections that cannot
    route around it. `get_events`, `get_climate` and the wildcards each print a
    probability too; they are covered here because there is only ONE place in
    the module that selects a FuturesMarket. A new section that builds its own
    select would reintroduce the fabricated zero on its own card, silently, so
    this guard fails on the source text rather than waiting for a screenshot.
    """
    source = (
        Path(__file__).resolve().parents[1] / "app" / "routes" / "weather.py"
    ).read_text()

    selects = source.count("select(FuturesMarket)")
    assert selects == 1, (
        f"weather.py builds {selects} FuturesMarket selects; every weather "
        "section must read through _open_weather_query() so the priceless-"
        "market filter cannot be bypassed"
    )
    assert "def _open_weather_query()" in source
