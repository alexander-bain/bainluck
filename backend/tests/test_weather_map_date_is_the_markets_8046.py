"""#8046 Half B — each /weather city carries the day its own market is about.

The map chip and every city panel printed `new Date() + 1` from the reader's
machine. On 2026-09-28 ~01:10Z the 48 markets behind the pins were on three
days: Kalshi's (`KXHIGHTBOS-26SEP27`) on Sep 27, Polymarket's
("Highest temperature in NYC on September 29?") mostly on Sep 29. The payload
had no date field, so the page could not have known. Names/tickers below are
production's, verbatim.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

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
from app.routes.weather import _temperature_day, get_cities  # noqa: E402


def _m(name, external_id, resolution_date):
    return SimpleNamespace(
        name=name, external_id=external_id, resolution_date=resolution_date
    )


def test_a_kalshi_day_comes_from_its_ticker_not_its_settlement():
    # Settles 05:00Z the NEXT day; the day it prices is the ticker's.
    m = _m(
        "Highest temperature in Boston on Sep 27, 2026?",
        "KXHIGHTBOS-26SEP27",
        datetime(2026, 9, 28, 5, tzinfo=timezone.utc),
    )
    assert _temperature_day(m).isoformat() == "2026-09-27"


def test_a_yearless_polymarket_name_takes_its_year_from_the_market():
    m = _m(
        "Highest temperature in NYC on September 29?",
        "1090393",
        datetime(2026, 9, 29, 12, tzinfo=timezone.utc),
    )
    assert _temperature_day(m).isoformat() == "2026-09-29"


def test_a_december_question_settling_in_january_keeps_its_year():
    m = _m(
        "Highest temperature in Tokyo on December 31?",
        "1",
        datetime(2027, 1, 1, 12, tzinfo=timezone.utc),
    )
    assert _temperature_day(m).isoformat() == "2026-12-31"


def test_a_market_that_cannot_say_its_day_says_nothing():
    assert _temperature_day(_m("Highest temperature in Tokyo?", "1", None)) is None
    assert (
        _temperature_day(
            _m(
                "Highest temperature in Tokyo on Smarch 3?",
                "1",
                datetime(2026, 9, 29, tzinfo=timezone.utc),
            )
        )
        is None
    )


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


def test_each_city_serves_its_own_markets_day():
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
    specimens = [
        (
            62734098,
            "kalshi",
            "KXHIGHTBOS-26SEP27",
            "Highest temperature in Boston on Sep 27, 2026?",
        ),
        (
            62721466,
            "polymarket",
            "1090393",
            "Highest temperature in NYC on September 29?",
        ),
    ]
    for mid, source, ext, name in specimens:
        session.add(
            FuturesMarket(
                id=mid,
                source=source,
                external_id=ext,
                name=name,
                status="open",
                llm_sport_category="weather",
                # Both still open: resolution in the future, whatever today is.
                resolution_date=NOW + timedelta(days=1),
                updated_at=FRESH,
            )
        )
        for i, (label, p) in enumerate([("70-71°F", 0.4), ("72-73°F", 0.6)]):
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
    session.commit()

    cities = {c["id"]: c for c in asyncio.run(get_cities(AsyncDB(session)))}

    # Boston's day is its ticker's, regardless of the clock this runs on.
    assert cities["boston"]["iso"] == "2026-09-27"
    # New York's is the name's month/day, in the year nearest its settlement.
    nyc = cities["nyc"]["iso"]
    assert nyc is not None and nyc.endswith("-09-29")


def test_the_card_names_the_venue_whose_ladder_it_draws_9260():
    """#9260: New York is quoted by both venues; the 11-bucket Polymarket
    ladder wins, and the badge must say Polymarket, not `sorted(srcs)[0]`."""
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
    ladders = {
        62721466: (
            "polymarket",
            "1090393",
            "Highest temperature in NYC on September 29?",
            11,
        ),
        62734099: (
            "kalshi",
            "KXHIGHNY-26SEP27",
            "Highest temperature in New York on Sep 27, 2026?",
            6,
        ),
    }
    for mid, (source, ext, name, n) in ladders.items():
        session.add(
            FuturesMarket(
                id=mid,
                source=source,
                external_id=ext,
                name=name,
                status="open",
                llm_sport_category="weather",
                resolution_date=NOW + timedelta(days=1),
                updated_at=FRESH,
            )
        )
        for i in range(n):
            session.add(
                FuturesOutcome(
                    id=mid * 100 + i,
                    market_id=mid,
                    external_id=f"o-{mid}-{i}",
                    name=f"{60 + 2 * i}-{61 + 2 * i}°F",
                    current_probability=1.0 / n,
                    last_updated=FRESH,
                )
            )
    session.commit()

    nyc = next(c for c in asyncio.run(get_cities(AsyncDB(session))) if c["id"] == "nyc")

    assert nyc["marketId"] == 62721466
    assert nyc["srcs"] == ["kalshi", "polymarket"]
    assert nyc["src"] == "polymarket"
