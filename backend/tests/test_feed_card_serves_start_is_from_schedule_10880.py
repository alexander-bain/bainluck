"""#10880 — a feed card says whether its start came from a schedule.

The iPhone "Add to Calendar" item writes a game's start into the reader's own
calendar. Nothing of ours can correct that entry once it is saved, so the item
may only use a start that a sports schedule provider published. Before this
change the client could not tell: `/api/feed` served `commence_time` with no
provenance. On a Kalshi-born row that instant is the expected EXPIRATION, three
hours after a soccer kick-off (`app/utils/event_completion.py`). On a
Polymarket-listed row it is the listing stamp, which read 11-18h early.

THESE TESTS DRIVE `_score_events`, NOT ONLY THE SERIALIZER (the #5324 rule): a
`format_event_data` guard keeps passing when the route stops handing over the
provenance, so the wiring is asserted on the card the route actually builds.

Every True arm has a control of the same shape that reads False, so a card that
always serves True (or never serves the key) fails.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from app.routes.feed import _score_events
from app.utils.feed_scoring import format_event_data
from app.utils.personalization import PersonalizationContext
from app.utils.proven_duplicates import FoldedBlendView
from app.utils.scheduled_start import (
    SCHEDULE_START_SOURCES,
    loaded_commence_time_source,
    start_is_from_schedule,
)

NOW = datetime(2026, 10, 16, 21, 0, 0, tzinfo=timezone.utc)

#: Every non-schedule value a writer stamps today (`event_completion.py`,
#: `tasks/polymarket.py`, `tasks/kalshi.py`), plus NULL and an unknown word.
NOT_A_SCHEDULE = (
    "kalshi",
    "kalshi_ticker",
    "kalshi_ticker_time",
    "kalshi_occurrence",
    "polymarket",
    "polymarket_venue",
    None,
    "",
    "some_future_source",
)


def _sport():
    s = MagicMock()
    s.key = "americanfootball_nfl"
    s.name = "NFL"
    return s


def _event(event_id, *, commence_time_source, status="scheduled"):
    e = MagicMock()
    e.id = event_id
    e.status = status
    e.commence_time = NOW + timedelta(days=2)
    e.home_team_id = 10 + event_id
    e.away_team_id = 20 + event_id
    e.home_team_name = "Kansas City Chiefs"
    # A different opponent per row, so the fixture de-duplication (#2065)
    # keeps every card.
    e.away_team_name = f"Opponent {event_id}"
    e.opening_home_probability = 0.55
    e.opening_away_probability = 0.45
    e.win_probability_sources = {"betting": {"home_probability": 0.55}}
    e.opening_home_spread = None
    e.opening_over_under = None
    e.opening_favorite = "Kansas City Chiefs"
    e.llm_importance = "marquee"
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.sport = _sport()
    e.statpal_end_time = None
    e.completed_at = None
    e.period = None
    e.game_clock = None
    e.raw_ei = 90.0
    e.ei_metadata = None
    e.home_score = None
    e.away_score = None
    e.external_id = f"ext-{event_id}"
    e.broadcast_info = None
    e.event_tags = []
    e.image_url = None
    if commence_time_source is not _UNLOADED:
        e.commence_time_source = commence_time_source
    return e


#: Marks a row whose `commence_time_source` column was never loaded.
_UNLOADED = object()


def _mock_db(events):
    db = AsyncMock()

    def make_result(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.all.return_value = []
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "win_prob_snapshots" in s:
            return make_result([])
        if "events" in s:
            return make_result(events)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _cards(events):
    """The real card loop, My Teams rail (`min_score = 0`, see the #5324 file)."""
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ):
        items = await _score_events(
            _mock_db(events),
            NOW,
            None,
            PersonalizationContext(),
            True,
            ["Kansas City Chiefs"],
        )
    cards = {i["data"]["id"]: i["data"] for i in items if i["type"] == "event"}
    assert cards, "no card was built at all — the test proves nothing as written"
    return cards


@pytest.mark.asyncio
async def test_a_schedule_providers_start_is_served_as_from_schedule():
    cards = await _cards(
        [
            _event(101, commence_time_source="espn"),
            _event(102, commence_time_source="statpal"),
            _event(103, commence_time_source="odds_api"),
            _event(104, commence_time_source="kalshi"),
            _event(105, commence_time_source="polymarket_venue"),
        ]
    )
    for event_id in (101, 102, 103):
        assert cards[event_id].get("start_is_from_schedule") is True, (
            f"card {event_id}: a schedule provider's start was not served as one — "
            "the Calendar item would never appear on a real fixture"
        )
    for event_id in (104, 105):
        assert cards[event_id].get("start_is_from_schedule") is False, (
            f"card {event_id}: a market's time was served as a schedule start — "
            "a reader's calendar would get an expiration or a venue claim"
        )


@pytest.mark.asyncio
async def test_an_unloaded_column_serves_false_without_a_lazy_load():
    """`__dict__`, not `getattr`: an expired row must not lazy-load per item."""
    row = _event(201, commence_time_source=_UNLOADED)
    type(row).commence_time_source = PropertyMock(
        side_effect=AssertionError("the serializer triggered a lazy load")
    )
    cards = await _cards([row, _event(202, commence_time_source="espn")])
    assert cards[201].get("start_is_from_schedule") is False
    assert (
        cards[202].get("start_is_from_schedule") is True
    ), "control: the healthy sibling must still serve True (gotcha #42)"


async def _price_cards(views):
    """The `/api/feed/price-cards` door: `feed_prices._event_cards` hands the
    scorer `FoldedBlendView`s, never bare rows."""
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ):
        items = await _score_events(
            _mock_db([]),
            NOW,
            None,
            PersonalizationContext(),
            price_refresh_events=views,
        )
    cards = {i["data"]["id"]: i["data"] for i in items if i["type"] == "event"}
    assert cards, "no price card was built — the test proves nothing as written"
    return cards


def _view(row):
    return FoldedBlendView(row, row.win_probability_sources)


@pytest.mark.asyncio
async def test_the_price_refresh_door_serves_the_same_provenance_as_the_feed():
    """lane1b's B1 on PR #11145: the refresh replaced the card wholesale and the
    Calendar item vanished from a Discover game after its first price update."""
    espn, kalshi = _event(301, commence_time_source="espn"), _event(
        302, commence_time_source="kalshi"
    )
    cards = await _price_cards([_view(espn), _view(kalshi)])
    assert cards[301].get("start_is_from_schedule") is True, (
        "the price refresh served False for an ESPN-started game — iOS adopts "
        "that card and the Calendar item disappears"
    )
    assert (
        cards[302].get("start_is_from_schedule") is False
    ), "control: a Kalshi time behind the same view must still serve False"


@pytest.mark.asyncio
async def test_an_unloaded_column_behind_the_view_serves_false_without_a_lazy_load():
    row = _event(303, commence_time_source=_UNLOADED)
    type(row).commence_time_source = PropertyMock(
        side_effect=AssertionError("the serializer triggered a lazy load")
    )
    cards = await _price_cards(
        [_view(row), _view(_event(304, commence_time_source="espn"))]
    )
    assert cards[303].get("start_is_from_schedule") is False
    assert cards[304].get("start_is_from_schedule") is True


def test_the_loaded_read_looks_through_views_and_nothing_else():
    row = _event(305, commence_time_source="statpal")
    assert loaded_commence_time_source(row) == "statpal"
    assert loaded_commence_time_source(_view(row)) == "statpal"
    assert loaded_commence_time_source(_view(_view(row))) == "statpal"
    assert (
        loaded_commence_time_source(_view(_event(306, commence_time_source=None)))
        is None
    )
    assert loaded_commence_time_source(None) is None
    assert loaded_commence_time_source(object()) is None, "no __dict__ reads as None"


@pytest.mark.parametrize("source", sorted(SCHEDULE_START_SOURCES))
def test_each_schedule_source_counts(source):
    assert start_is_from_schedule(source) is True


@pytest.mark.parametrize("source", NOT_A_SCHEDULE)
def test_market_times_and_unknowns_do_not_count(source):
    assert start_is_from_schedule(source) is False


def test_the_schedule_set_is_exactly_the_three_providers():
    """A new member must be added by name, here, with its writer cited."""
    assert SCHEDULE_START_SOURCES == frozenset({"espn", "statpal", "odds_api"})


def _serialize(**extra):
    return format_event_data(
        event_id=1,
        external_id="e-1",
        sport_key="americanfootball_nfl",
        sport_name="NFL",
        home_team="Kansas City Chiefs",
        away_team="Buffalo Bills",
        commence_time=NOW + timedelta(days=2),
        status="scheduled",
        home_score=None,
        away_score=None,
        current_home_prob=None,
        current_away_prob=None,
        opening_home_prob=None,
        opening_away_prob=None,
        opening_favorite=None,
        win_probability_sources=None,
        prob_source=None,
        game_clock=None,
        period=None,
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
        **extra,
    )


def test_a_caller_that_omits_provenance_serves_false():
    assert _serialize()["start_is_from_schedule"] is False
    assert _serialize(commence_time_source="espn")["start_is_from_schedule"] is True
