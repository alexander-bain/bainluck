"""The NYC rain card reads NYC, not whichever city is wettest (ux/1076).

CERT-1855's BLOCK, and it is the "both ends green, ship dead" class: ux/1076
fixed the PRODUCER (the daily KXRAIN series now reaches the guaranteed rescue
in time) while the CONSUMER went on asking for a shape the venue no longer
lists.

Two stored shapes answer "will it rain in NYC tomorrow":

    legacy  KXRAINNYC-*  one binary market per day, "Will it rain in NYC on
                         Sep 6, 2026?", outcomes Yes/No. Zero open at Kalshi
                         today — dormant, not removed.
    live    KXRAIN-*     ONE market per day, "Where will it rain on Sep 6,
                         2026?", carrying 22 CITY outcomes.

`/api/weather/rain` selected only `Will it rain in NYC on%`, so the live event
was invisible to the card no matter how promptly it was ingested. Worse than
invisible if it had matched: `_get_yes_probability` finds no "Yes" leg on a
22-city event and falls through to `_highest_prob`, which returns **the wettest
city in America under an NYC label**. Chicago's forecast, printed as New York's.

The sharp edge these tests exist to hold: on a multi-city event there is ALWAYS
some number available to print, so the failure is silent and confident. The
only correct answer when NYC is absent or unpriced is no row at all.
"""

from datetime import datetime, timedelta, timezone

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
from app.routes.weather import get_rain  # noqa: E402

NOW = datetime.now(timezone.utc)
FRESH = NOW - timedelta(hours=1)


class AsyncDB:
    """Minimal async facade over a sync Session — the same shim ux/1075 uses.

    `get_rain` awaits exactly one thing, `db.execute(query)`, so the REAL
    statement the route builds runs against a real (SQLite) database and the
    route's real post-processing produces the real payload the card reads.
    """

    def __init__(self, session: Session):
        self._session = session

    async def execute(self, query):
        return self._session.execute(query)


def _event(mid: int, external_id: str, name: str, days_out: int) -> FuturesMarket:
    return FuturesMarket(
        id=mid,
        source="kalshi",
        external_id=external_id,
        name=name,
        status="open",
        llm_sport_category="weather",
        resolution_date=NOW + timedelta(days=days_out),
        updated_at=FRESH,
    )


def _city(oid: int, mid: int, city: str, ticker_suffix: str, probability):
    """One city leg of a daily KXRAIN event, in the venue's own shape."""
    return FuturesOutcome(
        id=oid,
        market_id=mid,
        external_id=f"KXRAIN-26SEP06-{ticker_suffix}",
        name=city,
        current_probability=probability,
    )


def _new_session() -> Session:
    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng, tables=[FuturesMarket.__table__, FuturesOutcome.__table__]
    )
    return Session(eng)


async def _rain(session):
    return await get_rain(AsyncDB(session))


# ---------------------------------------------------------------------------
# The catching test CERT-1855 named
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nyc_below_another_city_still_reports_nycs_own_number():
    """The exact shape the BLOCK asked for: NYC is NOT the leader.

    Chicago is soaked, New York is dry. The card is about New York.
    """
    s = _new_session()
    s.add(_event(1, "KXRAIN-26SEP06", "Where will it rain on Sep 6, 2026?", 1))
    s.add(_city(10, 1, "Chicago", "CHI", 0.90))
    s.add(_city(11, 1, "New York City", "NYC", 0.25))
    s.add(_city(12, 1, "Miami", "MIA", 0.60))
    s.commit()

    daily = (await _rain(s))["daily"]

    assert len(daily) == 1, "the live daily event must reach the NYC card"
    assert daily[0]["prob"] == 25, (
        "the card printed %r — the wettest city's forecast under an NYC label "
        "is exactly the defect" % daily[0]["prob"]
    )


@pytest.mark.asyncio
async def test_the_live_daily_event_reaches_the_card_at_all():
    """Before the repair the card's query could not see this shape, so the
    section read 'No live rain markets right now' with the event in hand."""
    s = _new_session()
    s.add(_event(1, "KXRAIN-26SEP06", "Where will it rain on Sep 6, 2026?", 1))
    s.add(_city(10, 1, "New York City", "NYC", 0.42))
    s.commit()

    assert (await _rain(s))["daily"], "the daily KXRAIN event never reached the card"


# ---------------------------------------------------------------------------
# Absence is not a number — ux/1075's rule, one level down
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_event_without_nyc_yields_no_row_rather_than_the_leader():
    """A 22-city event always has SOME number to print. That is the trap."""
    s = _new_session()
    s.add(_event(1, "KXRAIN-26SEP06", "Where will it rain on Sep 6, 2026?", 1))
    s.add(_city(10, 1, "Chicago", "CHI", 0.90))
    s.add(_city(11, 1, "Denver", "DEN", 0.10))
    s.commit()

    assert (await _rain(s))["daily"] == [], (
        "an event with no New York leg produced an NYC row — the number can "
        "only have come from another city"
    )


@pytest.mark.asyncio
async def test_an_unpriced_nyc_leg_yields_no_row():
    """NYC is present but the venue prices no NYC leg. The event as a whole is
    priced, so ux/1075's market-level filter admits it; the city-level absence
    has to be caught here."""
    s = _new_session()
    s.add(_event(1, "KXRAIN-26SEP06", "Where will it rain on Sep 6, 2026?", 1))
    s.add(_city(10, 1, "Chicago", "CHI", 0.90))
    s.add(_city(11, 1, "New York City", "NYC", None))
    s.commit()

    assert (await _rain(s))["daily"] == [], (
        "an unpriced NYC leg printed a number"
    )


@pytest.mark.asyncio
async def test_a_genuine_zero_for_nyc_keeps_its_row():
    """The distinction ux/1075 was built on, and it must survive here: a venue
    that prices New York at zero has told us something, and 0% is the honest
    print. Only absence is silent."""
    s = _new_session()
    s.add(_event(1, "KXRAIN-26SEP06", "Where will it rain on Sep 6, 2026?", 1))
    s.add(_city(10, 1, "Chicago", "CHI", 0.90))
    s.add(_city(11, 1, "New York City", "NYC", 0.0))
    s.commit()

    daily = (await _rain(s))["daily"]
    assert len(daily) == 1 and daily[0]["prob"] == 0


# ---------------------------------------------------------------------------
# Identity: the venue's key, not our prose
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nyc_is_found_by_the_venues_ticker_when_the_name_is_reworded():
    """`-NYC` is Kalshi's own key for the leg. The display name is prose and
    can be re-worded upstream without notice; the card must not go blind when
    it is."""
    s = _new_session()
    s.add(_event(1, "KXRAIN-26SEP06", "Where will it rain on Sep 6, 2026?", 1))
    s.add(_city(10, 1, "Chicago", "CHI", 0.90))
    s.add(_city(11, 1, "NYC (Central Park)", "NYC", 0.31))
    s.commit()

    daily = (await _rain(s))["daily"]
    assert len(daily) == 1 and daily[0]["prob"] == 31


# ---------------------------------------------------------------------------
# The daily series is the daily series
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_weekend_and_monthly_rain_series_are_not_daily_rows():
    """`KXRAIN-%` matches on a literal hyphen precisely so that KXRAINWKND-*
    and the monthly KXRAIN*M-* series — different questions, other cards —
    cannot leak into the 7-day card."""
    s = _new_session()
    s.add(_event(1, "KXRAINWKND-26SEP05",
                 "Where will it rain this weekend (Sep 5 - Sep 6)?", 1))
    s.add(_city(10, 1, "New York City", "NYC", 0.55))
    s.add(_event(2, "KXRAINNYCM-26SEP", "Rain in NYC in Sep 2026?", 2))
    s.add(_city(20, 2, "New York City", "NYC", 0.77))
    s.commit()

    assert (await _rain(s))["daily"] == [], (
        "a weekend or monthly rain market was printed as a daily NYC row"
    )


@pytest.mark.asyncio
async def test_the_legacy_binary_market_still_works():
    """KXRAINNYC-* is dormant at the venue, not removed. If it wakes up, its
    Yes leg is NYC's answer by construction."""
    s = _new_session()
    m = _event(1, "KXRAINNYC-26SEP06", "Will it rain in NYC on Sep 6, 2026?", 1)
    s.add(m)
    s.add(FuturesOutcome(id=10, market_id=1, external_id="KXRAINNYC-26SEP06-Y",
                         name="Yes", current_probability=0.64))
    s.add(FuturesOutcome(id=11, market_id=1, external_id="KXRAINNYC-26SEP06-N",
                         name="No", current_probability=0.36))
    s.commit()

    daily = (await _rain(s))["daily"]
    assert len(daily) == 1 and daily[0]["prob"] == 64


@pytest.mark.asyncio
async def test_one_row_per_day_when_both_shapes_answer_the_same_date():
    """Both series live at once would otherwise print the same Tuesday twice."""
    s = _new_session()
    s.add(_event(1, "KXRAIN-26SEP06", "Where will it rain on Sep 6, 2026?", 1))
    s.add(_city(10, 1, "New York City", "NYC", 0.42))
    legacy = _event(2, "KXRAINNYC-26SEP06", "Will it rain in NYC on Sep 6, 2026?", 1)
    s.add(legacy)
    s.add(FuturesOutcome(id=20, market_id=2, external_id="KXRAINNYC-26SEP06-Y",
                         name="Yes", current_probability=0.44))
    s.commit()

    daily = (await _rain(s))["daily"]
    assert len(daily) == 1, "the same day was printed twice"
