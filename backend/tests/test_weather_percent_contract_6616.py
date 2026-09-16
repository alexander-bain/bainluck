"""#6616: `/weather` stops rounding a live price onto a boundary it is not on.

`_highest_prob` was `round(best * 100)` and every weather card read it, so the
route published an `int` and the page had nothing left to reason with. Measured
on production 2026-09-16 (390px, and `db-query` against
`futures_outcomes.current_probability` for each specimen):

    >99%  Miami, Seattle, NYC and Houston monthly rainfall — all four stored
          0.995000 on an OPEN "Above 1 inch" market, all four printing 100%.
          "Hurricane Marie category?" and "Number of tornadoes in Sep 2026?"
          the same, both still tradeable.
    <1%   96 `dist` rows across 42 cities serving `prob: 0`. Los Angeles
          quotes "63°F or below" AND "64-65°F" at 0.000500 each.

Unlike #6610 on `/entertainment`, this could not be fixed on the client: an
integer cannot be un-rounded. So the RAW probability now travels beside the
integer on every row that prints a percent, and the page applies
`lib/probabilityDisplay.ts`'s boundary rule to the value while keeping the
server's integer as the digits (`probabilityDisplay.ts:99` — "a claim about the
value, not about which arithmetic produced the integer").

THE ICON IS PART OF THE SHIP. `_rain_icon`'s top arm — the umbrella that says
"it is raining, full stop" — was `prob >= 100`, so the same 99.5¢ quote that
printed `100%` also drew the certainty glyph. It keys on the raw value now.

What this file pins, on the REAL route builders over a real (SQLite) database:

  1. every percent-printing row of all six endpoints carries `probability`;
  2. that value is the UNROUNDED price, not a re-derivation of the integer;
  3. `prob` is UNCHANGED — this ship widens the payload, it does not move a
     number, so the page's own guard is what turns 100 into `>99%`;
  4. the icon arm keys on the raw value;
  5. the sibling scans (`_card_probability`, `_get_yes_probability_raw`,
     `_nyc_rain_probability_raw`) agree with the integers they are twinned
     with, and `None` still means absence on the NYC leg.

The corpus is the production specimens above, priced at the values the venue
was quoting when the issue was filed.
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
from app.routes.weather import (  # noqa: E402
    _card_prob,
    _card_probability,
    _get_yes_probability,
    _get_yes_probability_raw,
    _highest_prob,
    _highest_probability,
    _nyc_rain_probability,
    _nyc_rain_probability_raw,
    _rain_icon,
    get_cities,
    get_climate,
    get_events,
    get_featured,
    get_rain,
    get_wildcards,
)

NOW = datetime.now(timezone.utc)
FRESH = NOW - timedelta(hours=1)

#: The half-cent quote behind every `100%` on the live page.
NINETY_NINE_FIVE = 0.995
#: Los Angeles' two coldest temperature buckets, both live, both printing 0.
FIVE_HUNDREDTHS_OF_A_POINT = 0.0005

# Dates are computed, never typed: `get_featured` drops any market whose TITLE
# names a day that has passed, and a literal date turns this file red on a
# calendar rather than on a defect (gotcha #44, and #3736 in this very family).
_TODAY = NOW.date()
_TOMORROW = _TODAY + timedelta(days=1)


def _short_day(d) -> str:
    return f"{d:%b} {d.day}, {d.year}"


def _ticker_day(d) -> str:
    return f"{d:%y%b%d}".upper()


RAIN_Q = f"Where will it rain on {_short_day(_TOMORROW)}?"
RAIN_TICKER = f"KXRAIN-{_ticker_day(_TOMORROW)}"


@pytest.fixture(autouse=True)
def _sqlite_returns_aware_datetimes():
    """SQLite drops the tzinfo a `DateTime(timezone=True)` column carries, and
    the route subtracts `resolution_date - now`. Restores production's shape;
    registered and removed per test so the listener cannot follow
    `FuturesMarket` into another module."""
    fields = ("resolution_date", "updated_at", "created_at", "last_updated")

    def _restore_utc(target, _context):  # pragma: no cover - sqlite shim
        for field in fields:
            value = getattr(target, field, None)
            if isinstance(value, datetime) and value.tzinfo is None:
                setattr(target, field, value.replace(tzinfo=timezone.utc))

    event.listen(FuturesMarket, "load", _restore_utc)
    try:
        yield
    finally:
        event.remove(FuturesMarket, "load", _restore_utc)


class AsyncDB:
    """Minimal async facade over a sync Session — the builders await only
    `db.execute(query)`, so the REAL statements run against a real database."""

    def __init__(self, session: Session):
        self._session = session

    async def execute(self, query):
        return self._session.execute(query)


def _new_session() -> Session:
    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng,
        tables=[
            FuturesMarket.__table__,
            FuturesOutcome.__table__,
            FuturesOddsSnapshot.__table__,
        ],
    )
    return Session(eng)


def _market(
    mid: int,
    external_id: str,
    name: str,
    *,
    days_out: float,
    source: str = "kalshi",
) -> FuturesMarket:
    return FuturesMarket(
        id=mid,
        source=source,
        external_id=external_id,
        name=name,
        status="open",
        llm_sport_category="weather",
        resolution_date=NOW + timedelta(days=days_out),
        updated_at=FRESH,
    )


def _outcome(oid: int, mid: int, name: str, probability, external_id=None):
    return FuturesOutcome(
        id=oid,
        market_id=mid,
        external_id=external_id or f"outcome-{oid}",
        name=name,
        current_probability=probability,
    )


def _stub(session, mid, external_id, name, outcomes, *, days_out=30.0, source="kalshi"):
    session.add(_market(mid, external_id, name, days_out=days_out, source=source))
    for i, (label, prob) in enumerate(outcomes):
        session.add(_outcome(mid * 100 + i, mid, label, prob))


# ---------------------------------------------------------------------------
# The scans: a raw twin for every rounded one, agreeing with it
# ---------------------------------------------------------------------------


def _bare_market(outcomes, external_id="x") -> FuturesMarket:
    m = FuturesMarket(
        id=1, source="kalshi", external_id=external_id, name="Q?", status="open"
    )
    m.outcomes = [
        _outcome(i, 1, label, prob) for i, (label, prob) in enumerate(outcomes)
    ]
    return m


def test_highest_probability_is_the_unrounded_price():
    m = _bare_market([("Above 1 inch", NINETY_NINE_FIVE), ("No", 0.005)])
    assert _highest_probability(m) == NINETY_NINE_FIVE
    # The integer is unchanged by this ship. The `100` is not the bug — printing
    # it as a bare `100%` is, and that is the page's half of the contract.
    assert _highest_prob(m) == 100


def test_the_raw_scan_survives_the_bottom_of_the_ladder():
    """The `<1%` arm, at the value the venue actually quotes."""
    m = _bare_market([("63°F or below", FIVE_HUNDREDTHS_OF_A_POINT)])
    assert _highest_probability(m) == FIVE_HUNDREDTHS_OF_A_POINT
    assert _highest_prob(m) == 0


def test_card_probability_and_card_prob_are_one_scan():
    m = _bare_market([("Category 1 or above", NINETY_NINE_FIVE), ("Cat 4", 0.2)])
    assert _card_probability(m) == NINETY_NINE_FIVE
    assert _card_prob(m) == round(_card_probability(m) * 100)


def test_yes_probability_raw_reads_the_yes_leg_not_the_leader():
    """The monthly rainfall scan. `Yes` wins even when it is not the maximum,
    and the raw twin has to make the same choice or the card would print one
    leg's percent under the other's boundary marker."""
    m = _bare_market([("No", 0.9), ("Yes", 0.1)])
    assert _get_yes_probability_raw(m) == pytest.approx(0.1)
    assert _get_yes_probability(m) == 10

    settled_looking = _bare_market([("Yes", NINETY_NINE_FIVE), ("No", 0.005)])
    assert _get_yes_probability_raw(settled_looking) == NINETY_NINE_FIVE
    assert _get_yes_probability(settled_looking) == 100


def test_unpriced_nyc_leg_is_still_an_absence_not_a_zero():
    """ux/1075's rule, re-pinned because #6616 added a second reader of it."""
    # The live shape: ONE multi-city market per day. The NYC leg is the only
    # one that may answer the card's question.
    m = _bare_market([("Chicago", 0.4)], external_id=RAIN_TICKER)
    assert _nyc_rain_probability_raw(m) is None
    assert _nyc_rain_probability(m) is None

    m2 = _bare_market(
        [("Chicago", 0.4), ("New York City", NINETY_NINE_FIVE)],
        external_id=RAIN_TICKER,
    )
    assert _nyc_rain_probability_raw(m2) == NINETY_NINE_FIVE
    assert _nyc_rain_probability(m2) == 100


# ---------------------------------------------------------------------------
# The icon
# ---------------------------------------------------------------------------

UMBRELLA = "☔"
RAIN_CLOUD = "\U0001F327"
PART_SUN = "⛅"
SUN = "☀️"


def test_the_umbrella_needs_an_actual_certainty():
    """The arm that made this more than a label fix: a 99.5¢ book took the
    certainty branch of the icon chooser as well as the text."""
    assert _rain_icon(NINETY_NINE_FIVE) == RAIN_CLOUD
    assert _rain_icon(0.999) == RAIN_CLOUD
    assert _rain_icon(1.0) == UMBRELLA


@pytest.mark.parametrize(
    "probability,icon",
    [
        (0.8, RAIN_CLOUD),
        (0.65, RAIN_CLOUD),
        (0.5, PART_SUN),
        (0.35, PART_SUN),
        (0.34, SUN),
        (FIVE_HUNDREDTHS_OF_A_POINT, SUN),
        (0.0, SUN),
    ],
)
def test_every_other_icon_threshold_is_where_it_was(probability, icon):
    """The rescale is a rescale, not a redesign: 65 and 35 become 0.65 and 0.35
    and nothing else moves."""
    assert _rain_icon(probability) == icon


# ---------------------------------------------------------------------------
# The payload: every percent-printing row carries its raw value
# ---------------------------------------------------------------------------


def _assert_travels(row, expected_raw, *, expected_prob):
    """A row prints a percent, so it owes the value that percent came from."""
    assert "probability" in row, f"row prints a percent with no raw value: {row}"
    assert row["probability"] == pytest.approx(expected_raw)
    assert row["prob"] == expected_prob
    # The point of the field: it is NOT recoverable from the integer. A raw
    # value equal to `prob / 100` on these specimens would mean the route had
    # re-derived it from the rounding and shipped nothing.
    assert row["probability"] != row["prob"] / 100


def test_monthly_rainfall_carries_the_price_behind_its_hundred():
    session = _new_session()
    for i, city in enumerate(["Miami", "Seattle", "NYC", "Houston"]):
        _stub(
            session,
            10 + i,
            f"KXRAIN{city.upper()}M-26SEP",
            f"Rain in {city} in Sep 2026?",
            [("Yes", NINETY_NINE_FIVE), ("No", 0.005)],
        )
    # A control that is nowhere near a boundary and must not move.
    _stub(
        session,
        20,
        "KXRAINCHIM-26SEP",
        "Rain in Chicago in Sep 2026?",
        [("Yes", 0.95), ("No", 0.05)],
    )
    session.commit()

    rain = asyncio.run(get_rain(AsyncDB(session)))
    by_city = {r["city"]: r for r in rain["monthly"]}
    assert set(by_city) == {"Miami", "Seattle", "NYC", "Houston", "Chicago"}

    for city in ("Miami", "Seattle", "NYC", "Houston"):
        _assert_travels(by_city[city], NINETY_NINE_FIVE, expected_prob=100)

    chicago = by_city["Chicago"]
    assert chicago["prob"] == 95
    assert chicago["probability"] == pytest.approx(0.95)


def test_the_daily_tile_carries_its_price_and_its_icon_agrees():
    session = _new_session()
    session.add(_market(30, RAIN_TICKER, RAIN_Q, days_out=1.4))
    session.add(
        _outcome(3000, 30, "New York City", NINETY_NINE_FIVE, external_id=f"{RAIN_TICKER}-NYC")
    )
    session.add(
        _outcome(3001, 30, "Miami", 0.83, external_id=f"{RAIN_TICKER}-MIA")
    )
    session.commit()

    rain = asyncio.run(get_rain(AsyncDB(session)))
    assert len(rain["daily"]) == 1
    tile = rain["daily"][0]
    _assert_travels(tile, NINETY_NINE_FIVE, expected_prob=100)
    # The whole reason the icon moved: `100` would have drawn the umbrella.
    assert tile["icon"] == RAIN_CLOUD


def test_natural_events_carry_the_price_behind_their_hundred():
    session = _new_session()
    _stub(
        session,
        40,
        "KXHURRMARIE",
        "Hurricane Marie category?",
        [("Category 1 or above", NINETY_NINE_FIVE), ("Category 4 or above", 0.2)],
        days_out=77.0,
    )
    _stub(
        session,
        41,
        "KXTORNADO-26SEP",
        "Number of tornadoes in Sep 2026?",
        [("Above 25", NINETY_NINE_FIVE), ("Above 100", 0.1)],
        days_out=15.0,
    )
    session.commit()

    events = asyncio.run(get_events(AsyncDB(session)))
    _assert_travels(events["hurricane"][0], NINETY_NINE_FIVE, expected_prob=100)
    _assert_travels(events["tornadoes"][0], NINETY_NINE_FIVE, expected_prob=100)


def test_the_city_ladder_carries_a_price_for_every_bucket():
    """The `<1%` arm. Both of Los Angeles' cold buckets are quoted, and both
    arrive as `prob: 0` — a bucket the panel reads as a flat zero draws no bar
    and offers no tooltip, which tells a reader it is impossible by omission."""
    session = _new_session()
    _stub(
        session,
        50,
        "poly-temp-la",
        f"Highest temperature in Los Angeles on {_short_day(_TOMORROW)}?",
        [
            ("63°F or below", FIVE_HUNDREDTHS_OF_A_POINT),
            ("64-65°F", FIVE_HUNDREDTHS_OF_A_POINT),
            ("78-79°F", 0.62),
            ("80-81°F", 0.3795),
        ],
        days_out=0.6,
        source="polymarket",
    )
    session.commit()

    cities = asyncio.run(get_cities(AsyncDB(session)))
    la = next(c for c in cities if c["name"] == "Los Angeles")
    dist = {b["label"]: b for b in la["high"]["dist"]}

    for label in ("63°F or below", "64-65°F"):
        bucket = dist[label]
        assert bucket["prob"] == 0, "the specimen is only interesting while it rounds to 0"
        assert bucket["probability"] == pytest.approx(FIVE_HUNDREDTHS_OF_A_POINT)

    # Controls: the buckets that were never wrong keep both fields agreeing.
    assert dist["78-79°F"]["prob"] == 62
    assert dist["78-79°F"]["probability"] == pytest.approx(0.62)


def test_hero_climate_and_wildcards_all_carry_the_raw_value():
    """The three remaining `_card_prob` surfaces, in one corpus: whatever the
    route decides to feature, the row it emits owes its price."""
    session = _new_session()
    _stub(
        session,
        60,
        "KXARCTIC-26",
        "Lowest daily Arctic sea ice extent in summer 2026",
        [("Below 4.8 million sq km", NINETY_NINE_FIVE), ("Below 4.0", 0.12)],
        days_out=45.0,
    )
    _stub(
        session,
        61,
        "KXHOT-2026",
        "Will 2026 be the hottest year on record?",
        [("Yes", NINETY_NINE_FIVE), ("No", 0.005)],
        days_out=100.0,
    )
    session.commit()
    db = AsyncDB(session)

    wildcards = asyncio.run(get_wildcards(db))
    arctic = next(w for w in wildcards if "Arctic" in w["q"])
    _assert_travels(arctic, NINETY_NINE_FIVE, expected_prob=100)

    climate = asyncio.run(get_climate(db))
    hottest = next(c for c in climate if "hottest" in c["q"])
    _assert_travels(hottest, NINETY_NINE_FIVE, expected_prob=100)

    featured = asyncio.run(get_featured(db))
    assert featured, "the corpus must reach the hero or this arm proves nothing"
    for item in featured:
        assert "probability" in item
        # The integer is a rounding OF the raw value — the relationship the
        # page's `rendered` override depends on — not a second opinion.
        assert round(item["probability"] * 100) == item["prob"]


def test_the_wildcard_card_stops_contradicting_its_own_sparkline():
    """The specimen that needed no database read to be called wrong: the
    headline said 100 while `history` — built by `round(p * 100, 1)` in the same
    function — said 99.5, over the same price. The two readings now come from
    one number."""
    session = _new_session()
    _stub(
        session,
        70,
        "KXARCTIC-26",
        "Lowest daily Arctic sea ice extent in summer 2026",
        [("Below 4.8 million sq km", NINETY_NINE_FIVE)],
        days_out=45.0,
    )
    session.commit()

    card = asyncio.run(get_wildcards(AsyncDB(session)))[0]
    assert card["probability"] * 100 == pytest.approx(99.5)
