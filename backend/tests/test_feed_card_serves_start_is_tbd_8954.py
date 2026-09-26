"""#8954 / #8841 — a feed card says when a start is a placeholder, like every other route.

The related rail under a game page (`RelatedByTag`) printed no start at all for an
upcoming game — "Oregon @ USC 63% / 37%" an hour before kickoff. The web half gives
it the Discover card's start line. But both of those cards are fed by `/api/feed`,
and the feed was the one event payload that did not serve `start_is_tbd` (#8841:
`/api/events` and the team page do). So giving the rail a clock would have printed
StatPal's placeholder hour as a real start: "Tue 1:00 PM" on the Red Sox @ Yankees
Wild Card game (15319235, `commence_time 2026-09-29 20:00Z`, tagged
`provenance:start-placeholder:statpal:2026-09-29T20:00Z`) that MLB has not scheduled.

THESE TESTS DRIVE `_score_events`, NOT ONLY THE SERIALIZER (the #5324 rule): a
`format_event_data` guard keeps passing when the route stops handing it the stored
tags, so the wiring is asserted on the card the route actually builds. The stored
tags are the point — `inline_tags` are recomputed and never carry the mark.

Every flag-true arm has a control on the same shape that reads False, so a card
that always served True (or never served the key) fails.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_events
from app.utils.feed_scoring import format_event_data
from app.utils.personalization import PersonalizationContext

NOW = datetime(2026, 9, 26, 22, 30, 0, tzinfo=timezone.utc)
SPECIMEN_START = datetime(2026, 9, 29, 20, 0, 0, tzinfo=timezone.utc)
SPECIMEN_TAG = "provenance:start-placeholder:statpal:2026-09-29T20:00Z"


def _sport():
    s = MagicMock()
    s.key = "baseball_mlb"
    s.name = "MLB"
    return s


def _event(event_id, *, commence_time, event_tags, status="scheduled"):
    e = MagicMock()
    e.id = event_id
    e.status = status
    e.commence_time = commence_time
    e.home_team_id = 10 + event_id
    e.away_team_id = 20 + event_id
    e.home_team_name = "New York Yankees"
    e.away_team_name = "Boston Red Sox"
    e.opening_home_probability = 0.55
    e.opening_away_probability = 0.45
    e.win_probability_sources = {"betting": {"home_probability": 0.55}}
    e.opening_home_spread = None
    e.opening_over_under = None
    e.opening_favorite = "New York Yankees"
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
    e.event_tags = event_tags
    e.image_url = None
    return e


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
            ["New York Yankees"],
        )
    cards = {i["data"]["id"]: i["data"] for i in items if i["type"] == "event"}
    assert cards, "no card was built at all — the test proves nothing as written"
    return cards


@pytest.mark.asyncio
async def test_the_wild_card_specimen_card_serves_start_is_tbd():
    specimen = _event(15319235, commence_time=SPECIMEN_START, event_tags=[SPECIMEN_TAG])
    control = _event(
        15319300,
        commence_time=NOW + timedelta(hours=2),
        event_tags=["provenance:source:statpal"],
    )
    cards = await _cards([specimen, control])

    assert cards[15319235].get("start_is_tbd") is True, (
        "the feed card for a placeholder start did not say so — the rail and the "
        f"Discover card will print its hour as a clock: {cards[15319235].get('start_is_tbd')!r}"
    )
    assert cards[15319300].get("start_is_tbd") is False, (
        "an announced start was served as TBD — every feed card would lose its clock"
    )


@pytest.mark.asyncio
async def test_a_tag_vouching_for_a_different_instant_is_not_tbd():
    """Another rail moved the start after StatPal's mark: the stamp is real now."""
    moved = _event(
        15319235,
        commence_time=SPECIMEN_START + timedelta(hours=3, minutes=8),
        event_tags=[SPECIMEN_TAG],
    )
    assert (await _cards([moved]))[15319235].get("start_is_tbd") is False


def _serialize(status, stored_tags):
    return format_event_data(
        event_id=1,
        external_id="e-1",
        sport_key="baseball_mlb",
        sport_name="MLB",
        home_team="New York Yankees",
        away_team="Boston Red Sox",
        commence_time=SPECIMEN_START,
        status=status,
        home_score=None,
        away_score=None,
        current_home_prob=0.55,
        current_away_prob=0.45,
        opening_home_prob=None,
        opening_away_prob=None,
        opening_favorite=None,
        win_probability_sources=None,
        prob_source="aggregate",
        game_clock=None,
        period=None,
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[SPECIMEN_TAG],
        ended_at=None,
        stored_tags=stored_tags,
    )


@pytest.mark.parametrize("status", ["live", "completed", "closed"])
def test_a_started_game_is_never_tbd(status):
    assert _serialize(status, [SPECIMEN_TAG])["start_is_tbd"] is False


def test_the_flag_reads_the_stored_tags_not_the_inline_ones():
    """`inline_tags` carries the mark here and `stored_tags` does not: False."""
    assert _serialize("scheduled", [])["start_is_tbd"] is False
    assert _serialize("scheduled", [SPECIMEN_TAG])["start_is_tbd"] is True
