"""The `/weather` hero answers the question its own headline asks (ux/1086, #3307).

`/weather`'s headline is the largest type on the page:

    What are the odds it rains tomorrow?

Beside it sits a five-slide featured carousel. `get_featured` scored every
eligible weather market `len(outcomes) / days_to_resolution` and took the top
five, which on production at 2026-09-05 14:20 PT produced:

    44.73  27 out  0.60d  Which cities face tornado risk on September 5?
    18.22  11 out  0.60d  Highest temperature in Moscow on September 6?
    18.22  11 out  0.60d  Highest temperature in Manila on September 6?
    18.22  11 out  0.60d  … ELEVEN more, every one of them 18.22
    ~15.1  22 out  1.46d  Where will it rain on Sep 6, 2026?

Three defects, and each one has its own tests below.

1. THE TIE. Thirteen Polymarket city-temperature ladders, all 11 buckets, all
   closing at the same instant, all scoring 18.22. Four of the five slides came
   out of that tie and the tie broke on database row order — which is why the
   opening slide was Manila on one load and Miami on the next.

2. THE UNREACHABLE ANSWER. The daily rain market scores BELOW the tie, so the
   only question the headline names could never reach the hero at all. #3231
   moved the rain SECTION up the page; this is the card beside the headline.

3. THE WRONG CITY'S NUMBER. The daily rain market is a 22-city event whose
   `_highest_prob` is Miami. Pinning it naively would have printed **83%**
   directly above a rain section printing **38%** — NYC's — for the same
   question, on the same day, off the same market. One question, one number:
   the hero reads the leg the rain card reads (ux/1076, ux/1078).

The trap these tests exist to hold: on a 22-city event there is ALWAYS some
number to print, and the wrong one looks exactly as confident as the right one.
"""

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
    _highest_prob,
    _leader_outcome_name,
    get_featured,
)

NOW = datetime.now(timezone.utc)
FRESH = NOW - timedelta(hours=1)

# 🔴 A TITLE THIS FILE FEEDS TO `get_featured` IS AN INPUT TO THE CODE UNDER TEST,
# AND ONE OF THE THINGS THAT CODE READS IS TODAY. So the dates inside those titles
# are OFFSET FROM `NOW`, never spelled (gotcha #44).
#
# What happened when they were spelled (#3739, 2026-09-07 00:00Z): `get_featured`
# drops any market `is_title_implied_stale()` flags, and that helper parses the
# bare "<Month> <day>?" form and calls it stale once the day is past. The tornado
# fixture below was named "…on September 5?", so at the UTC rollover it became
# `stale_explicit_title_date` and vanished from the pool — taking with it the
# highest-scoring row that two tests here need. Both went red, on EVERY branch in
# the repo simultaneously, and `deploy` is gated behind `backend-tests`, so for
# the length of that outage nothing could ship. Nobody had touched weather.
#
# SCOPED BY THE SWEEP, NOT BY A PROBE. The first cut of this comment said the
# helper flags only the bare "<Month> <day>?" form, because a probe one day past
# the incident showed "Where will it rain on Sep 6, 2026?" returning `None`. That
# was true and it was not the question: `clock_sweep.py` then failed SIX tests at
# 2026-12-05 and 2027-10-11, where the same title is `stale_explicit_title_date`.
# A one-day probe cannot see a rule with a grace window. So the rain title is
# derived too, and the scope is whatever the 12-point sweep says it is.
#
# What stays verbatim is only what never reaches `get_featured`: the weekend RANGE
# form and "Rain in NYC in Sep 2026?" live in a pure `_card_prob` test that reads
# no clock, and the docstring above is a transcript of the production incident —
# rewriting a transcript to be clock-safe destroys the record without fixing
# anything. If either of those is ever routed through `get_featured`, derive it
# first; the sweep will say so.
#
# TOMORROW rather than today, and that is not arbitrary: a title naming TODAY is
# one second away from naming yesterday, so a suite that starts at 23:59:59Z would
# reintroduce exactly this bug in a form that reproduces once a day. Offset first,
# then format — an anchor containing an `if` is not a fixed anchor.
_TITLE_DAY = NOW + timedelta(days=1)
_TITLE_DATE = f"{_TITLE_DAY:%B} {_TITLE_DAY.day}"

TORNADO_Q = f"Which cities face tornado risk on {_TITLE_DATE}?"
RAIN_Q = f"Where will it rain on {_TITLE_DAY:%b} {_TITLE_DAY.day}, {_TITLE_DAY.year}?"


def _temp_q(city: str) -> str:
    """The title of one of the thirteen identical city-temperature ladders."""
    return f"Highest temperature in {city} on {_TITLE_DATE}?"


@pytest.fixture(autouse=True)
def _sqlite_returns_aware_datetimes():
    """SQLite has no timezone type, so a `DateTime(timezone=True)` column comes
    back naive and `get_featured`'s `resolution_date - now` raises. Postgres
    returns aware values, so this restores production's shape rather than
    papering over a real bug.

    Registered and REMOVED per test: a mapper-level listener left installed
    would follow `FuturesMarket` into every other module pytest imports.
    """
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
    """Minimal async facade over a sync Session — the shim ux/1075 introduced.

    `get_featured` awaits exactly two things, both `db.execute(query)`, so the
    REAL statements the route builds run against a real (SQLite) database and
    the route's real post-processing produces the real payload the hero reads.
    """

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
        # NOT NULL in the real schema, and the NYC rule prefers the venue's key
        # over the display name — so a placeholder here must not accidentally
        # end in the NYC suffix the rule looks for.
        external_id=external_id or f"outcome-{oid}",
        name=name,
        current_probability=probability,
    )


def _daily_rain_event(session, mid: int, cities: list[tuple[str, object]]):
    """The live shape: ONE market per day carrying a leg per city.

    `cities` is (city, probability) in the venue's own order — deliberately not
    sorted, because the defect is about which leg the card picks, not which is
    listed first.

    The day is `_TITLE_DAY`, not an argument: every caller passed the same "06"
    and it reached both the ticker and the title, so the only thing the parameter
    ever did was let a spelled date into the pool (#3739). `KXRAIN-` keeps its
    literal hyphen — that prefix is what `_card_prob` keys the daily-rain rule on,
    and the sibling series below deliberately do not have it.
    """
    ticker = f"KXRAIN-{_TITLE_DAY:%y%b%d}".upper()
    session.add(_market(mid, ticker, RAIN_Q, days_out=1.4))
    for i, (city, prob) in enumerate(cities):
        session.add(
            _outcome(
                mid * 100 + i,
                mid,
                city,
                prob,
                external_id=f"{ticker}-{city[:3].upper()}",
            )
        )


def _temperature_ladder(session, mid: int, city: str, buckets: int = 11):
    """One of the thirteen identical Polymarket city-temperature markets."""
    session.add(
        _market(
            mid,
            f"poly-temp-{mid}",
            _temp_q(city),
            days_out=0.6,
            source="polymarket",
        )
    )
    for i in range(buckets):
        session.add(_outcome(mid * 100 + i, mid, f"{20 + i}°C", 0.1 + i * 0.01))


async def _featured(session):
    return await get_featured(AsyncDB(session))


# ---------------------------------------------------------------------------
# 2. The headline's question reaches the hero, and reaches it FIRST
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_rain_market_leads_even_though_it_scores_lowest():
    """The production shape, reproduced: tornado 44.73, thirteen temps at 18.22,
    rain ~15.1. Score alone puts rain nowhere; the headline names it."""
    s = _new_session()
    s.add(_market(1, "poly-tornado", TORNADO_Q, days_out=0.6, source="polymarket"))
    for i in range(27):
        s.add(_outcome(9000 + i, 1, f"City {i}", 0.2))
    for n, city in enumerate(
        ["Moscow", "Manila", "Jeddah", "Istanbul", "Busan", "Qingdao",
         "Karachi", "Guangzhou", "Cape Town", "Kuala Lumpur", "Helsinki",
         "Amsterdam", "Shenzhen"],
        start=10,
    ):
        _temperature_ladder(s, n, city)
    _daily_rain_event(s, 40, [("Miami", 0.835), ("New York City", 0.385), ("Chicago", 0.025)])
    s.commit()

    items = await _featured(s)

    assert items, "the hero rendered no slides at all"
    assert items[0]["q"] == RAIN_Q, (
        "slide one is %r — the page's headline asks about rain tomorrow and the "
        "card beside it is about something else" % items[0]["q"]
    )


@pytest.mark.asyncio
async def test_no_question_family_owns_more_than_two_of_the_five_slides():
    """Defect 1: four of five slides came out of one thirteen-way tie."""
    s = _new_session()
    s.add(_market(1, "poly-tornado", TORNADO_Q, days_out=0.6, source="polymarket"))
    for i in range(27):
        s.add(_outcome(9000 + i, 1, f"City {i}", 0.2))
    for n, city in enumerate(
        ["Moscow", "Manila", "Jeddah", "Istanbul", "Busan", "Qingdao",
         "Karachi", "Guangzhou", "Cape Town", "Kuala Lumpur", "Helsinki",
         "Amsterdam", "Shenzhen"],
        start=10,
    ):
        _temperature_ladder(s, n, city)
    _daily_rain_event(s, 40, [("Miami", 0.835), ("New York City", 0.385)])
    s.add(_market(50, "KXHURR-1", "Hurricane Marie category?", days_out=3))
    s.add(_outcome(5000, 50, "Category 4 or above", 0.95))
    s.add(_outcome(5001, 50, "Category 5 or above", 0.31))
    s.commit()

    items = await _featured(s)

    temps = [i for i in items if i["tag"] == "Temperature"]
    assert len(temps) <= 2, (
        "%d of the five slides are the same question in different cities: %r"
        % (len(temps), [i["q"] for i in temps])
    )


@pytest.mark.asyncio
async def test_the_cap_does_not_shrink_the_carousel():
    """Gotcha #43, the other direction. A pool of nothing BUT temperature
    ladders — thirteen of them and little else is the real corpus — must still
    fill five slides. A diversity rule that empties the surface it diversifies
    has replaced one bug with a worse one."""
    s = _new_session()
    for n, city in enumerate(
        ["Moscow", "Manila", "Jeddah", "Istanbul", "Busan", "Qingdao", "Karachi"],
        start=10,
    ):
        _temperature_ladder(s, n, city)
    s.commit()

    items = await _featured(s)

    assert len(items) == 5, (
        "the carousel rendered %d slides from a seven-market pool — the cap ate "
        "the surface" % len(items)
    )


@pytest.mark.asyncio
async def test_a_pool_smaller_than_the_carousel_is_not_padded():
    """The converse: five slots is a ceiling, not a quota. Three eligible
    markets yield three slides, not three plus two repeats."""
    s = _new_session()
    for n, city in enumerate(["Moscow", "Manila", "Jeddah"], start=10):
        _temperature_ladder(s, n, city)
    s.commit()

    items = await _featured(s)

    assert len(items) == 3
    assert len({i["market_id"] for i in items}) == 3, "a slide was repeated"


# ---------------------------------------------------------------------------
# 3. Whose number is it — the leg the rest of the page reads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_rain_slide_prints_new_yorks_number_not_the_wettest_citys():
    """Miami 83.5, New York 38.5 — production's own prices for Sep 6.

    83% under "what are the odds it rains tomorrow?", two hundred pixels above
    a rain card reading 38% off the same market, is the defect.
    """
    s = _new_session()
    _daily_rain_event(
        s, 40,
        [("Miami", 0.835), ("Los Angeles", 0.775), ("New York City", 0.385), ("Chicago", 0.025)],
    )
    s.commit()

    lead = (await _featured(s))[0]

    assert lead["prob"] == 38, (
        "the hero printed %r%% — Miami's forecast under the reader's own question"
        % lead["prob"]
    )
    assert lead["leader"] == "New York City", (
        "the number is unattributed (%r): a bare 38%% on a 22-city market says "
        "nothing about whose 38%% it is" % lead["leader"]
    )


@pytest.mark.asyncio
async def test_the_sparkline_charts_the_same_leg_the_number_comes_from():
    """The number, the name and the line are one seam (`_card_outcome`) or the
    card draws Miami's history under New York's percentage — the ux/1069 defect
    with real data instead of invented data, which is no better."""
    s = _new_session()
    _daily_rain_event(s, 40, [("Miami", 0.835), ("New York City", 0.385)])
    miami_leg, nyc_leg = 4000, 4001
    for i in range(6):
        captured = NOW - timedelta(hours=12 - i)
        s.add(FuturesOddsSnapshot(
            id=100 + i, outcome_id=miami_leg, bookmaker="kalshi",
            probability=0.80 + i * 0.01, captured_at=captured,
        ))
        s.add(FuturesOddsSnapshot(
            id=200 + i, outcome_id=nyc_leg, bookmaker="kalshi",
            probability=0.30 + i * 0.01, captured_at=captured,
        ))
    s.commit()

    lead = (await _featured(s))[0]

    assert lead["history"], "the rain slide drew no line despite six captures"
    assert max(lead["history"]) < 50, (
        "the line is %r — those are Miami's captures under New York's number"
        % lead["history"]
    )


@pytest.mark.asyncio
async def test_an_event_without_a_new_york_price_is_not_pinned():
    """A 22-city event always has SOME number. When it is not New York's, the
    honest move is not to PIN it — a card may quote Miami as long as it says
    Miami, but not under the reader's own question.

    The tornado market outscores this rain market, so the pin is the only thing
    that could put rain first: if rain leads here, the pin fired on a market we
    hold no New York price for.
    """
    s = _new_session()
    _daily_rain_event(s, 40, [("Miami", 0.835), ("Chicago", 0.025)])
    s.add(_market(1, "poly-tornado", TORNADO_Q, days_out=0.6, source="polymarket"))
    for i in range(27):
        s.add(_outcome(9000 + i, 1, f"City {i}", 0.2))
    s.commit()

    items = await _featured(s)

    assert items[0]["q"] == TORNADO_Q, (
        "the hero led with %r — a rain market we hold no New York price for"
        % items[0]["q"]
    )
    rain = next(i for i in items if i["q"] == RAIN_Q)
    assert (rain["prob"], rain["leader"]) == (84, "Miami"), (
        "the rain slide quotes %r%% as %r — a card may quote Miami, but it has "
        "to say Miami" % (rain["prob"], rain["leader"])
    )


@pytest.mark.asyncio
async def test_a_new_york_leg_with_no_price_is_absence_not_zero():
    """ux/1075's rule at this seam: an unpriced leg must never become a
    confident 0%, and must not silently promote the wettest city either."""
    s = _new_session()
    _daily_rain_event(s, 40, [("Miami", 0.835), ("New York City", None)])
    s.commit()

    items = await _featured(s)

    assert items[0]["prob"] != 0, "an unpriced New York leg rendered as a red 0%"


# ---------------------------------------------------------------------------
# The rule is keyed on the daily rain question and nothing else
# ---------------------------------------------------------------------------


def test_the_weekend_and_monthly_rain_series_are_different_questions():
    """`KXRAIN-` with the literal hyphen. Both of these are about rain; neither
    is about tomorrow, and neither carries a New York leg to read."""
    weekend = _market(
        60, "KXRAINWKND-26SEP05",
        "Where will it rain this weekend (Sep 5 - Sep 6)?", days_out=1.6,
    )
    weekend.outcomes = [
        _outcome(6000, 60, "Miami", 0.99),
        _outcome(6001, 60, "New York City", 0.42),
    ]
    monthly = _market(61, "KXRAINNYCM-26SEP", "Rain in NYC in Sep 2026?", days_out=26)
    monthly.outcomes = [_outcome(6100, 61, "Yes", 0.98)]

    for m in (weekend, monthly):
        assert _card_prob(m) == _highest_prob(m), (
            "%r was treated as the daily rain question" % m.name
        )


def test_a_market_that_is_not_about_rain_is_untouched():
    """The seam is shared by every weather card, so a temperature ladder must
    come out of it exactly as it went in."""
    ladder = _market(70, "poly-temp-70", _temp_q("Manila"), days_out=0.6, source="polymarket")
    ladder.outcomes = [
        _outcome(7000, 70, "29°C", 0.36),
        _outcome(7001, 70, "30°C", 0.44),
        _outcome(7002, 70, "31°C", 0.20),
    ]

    assert _card_prob(ladder) == _highest_prob(ladder) == 44
    assert _leader_outcome_name(ladder) == "30°C"
