"""#9208 — a postponed game's feed card carries ESPN's stoppage word.

The rained-out ALCS Game 4 (15330795, ESPN 401908026 `STATUS_POSTPONED`, stored
`status=suspended`, `period="Postponed"`) led /sports as "No result reported ·
last score 0-0 · Oct 16" while its own page said Postponed. `/api/events/{id}`
serves `espn.period = "Postponed"`; `/api/feed` built the card's `espn` block
only for a LIVE row, so a suspended card carried no word and the web card's
`authorityStoppageLabel(espn.period)` fell back to "No result reported".

THESE TESTS DRIVE `_score_events`, NOT ONLY THE SERIALIZER (the #5324 rule): a
`format_event_data` guard keeps passing when the route stops handing it the
stored period. Every arm that serves the word has a control on the same shape
that does not: a live period left on a row that went dark is not a stoppage.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_events
from app.utils.feed_scoring import format_event_data
from app.utils.personalization import PersonalizationContext

NOW = datetime(2026, 10, 17, 2, 45, 0, tzinfo=timezone.utc)


def _sport():
    s = MagicMock()
    s.key = "baseball_mlb"
    s.name = "MLB"
    return s


def _event(
    event_id, *, status, period, home_score=0, away_score=0, away="Tampa Bay Rays"
):
    e = MagicMock()
    e.id = event_id
    e.status = status
    e.commence_time = NOW - timedelta(hours=1)
    e.home_team_id = 10 + event_id
    e.away_team_id = 20 + event_id
    e.home_team_name = "Cleveland Guardians"
    e.away_team_name = away
    e.opening_home_probability = 0.52
    e.opening_away_probability = 0.48
    e.win_probability_sources = {"betting": {"home_probability": 0.52}}
    e.opening_home_spread = None
    e.opening_over_under = None
    e.opening_favorite = "Cleveland Guardians"
    e.llm_importance = "marquee"
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.sport = _sport()
    e.statpal_end_time = None
    e.completed_at = None
    e.period = period
    e.game_clock = "0:00"
    e.raw_ei = 90.0
    e.ei_metadata = None
    e.home_score = home_score
    e.away_score = away_score
    e.external_id = f"ext-{event_id}"
    e.broadcast_info = None
    e.event_tags = []
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
    """The real card loop, My Teams rail (`min_score = 0`, see the #5324 file).

    The blend is pinned: the specimen served a probability on production, and a
    suspended 0-0 row with none is skipped before serialization (live/048).
    """
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ), patch("app.routes.feed._compute_aggregate_probability", return_value=0.52):
        items = await _score_events(
            _mock_db(events),
            NOW,
            None,
            PersonalizationContext(),
            True,
            ["Cleveland Guardians"],
        )
    cards = {i["data"]["id"]: i["data"] for i in items if i["type"] == "event"}
    assert cards, "no card was built at all — the test proves nothing as written"
    return cards


@pytest.mark.asyncio
async def test_the_alcs_specimen_card_says_postponed():
    specimen = _event(15330795, status="suspended", period="Postponed")
    canceled = _event(
        15319530, status="suspended", period="cancelled", away="New York Yankees"
    )
    dark = _event(
        15330800,
        status="suspended",
        period="Top 5th",
        home_score=2,
        away_score=1,
        away="Detroit Tigers",
    )
    # Three distinct matchups: the feed folds two rows for one pairing into one card.
    cards = await _cards([specimen, canceled, dark])

    assert cards[15330795]["status"] == "suspended"
    assert cards[15330795].get("espn") == {"period": "Postponed"}, (
        "the postponed game's feed card carries no stoppage word — /sports prints "
        f"'No result reported · last score 0-0': {cards[15330795].get('espn')!r}"
    )
    assert cards[15319530].get("espn") == {"period": "Canceled"}
    assert (
        "espn" not in cards[15330800]
    ), "a live inning left on a row that went dark was served as a stoppage word"


def _serialize(status, period, game_clock="0:00"):
    return format_event_data(
        event_id=1,
        external_id="e-1",
        sport_key="baseball_mlb",
        sport_name="MLB",
        home_team="Cleveland Guardians",
        away_team="Tampa Bay Rays",
        commence_time=NOW,
        status=status,
        home_score=0,
        away_score=0,
        current_home_prob=0.52,
        current_away_prob=0.48,
        opening_home_prob=None,
        opening_away_prob=None,
        opening_favorite=None,
        win_probability_sources=None,
        prob_source="aggregate",
        game_clock=game_clock,
        period=period,
        broadcast_info="FS1",
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
    )


@pytest.mark.parametrize("status", ["scheduled", "completed", "closed"])
def test_only_a_suspended_row_carries_the_word(status):
    assert "espn" not in _serialize(status, "Postponed")


@pytest.mark.parametrize(
    "period", [None, "", "Delayed", "Rain Delay", "Suspended", "Top 5th"]
)
def test_a_suspended_row_without_an_allowlisted_word_serves_no_block(period):
    assert "espn" not in _serialize("suspended", period)


def test_the_suspended_block_is_the_word_alone():
    """No filler clock, no broadcast: a called-off game has neither."""
    assert _serialize("suspended", " POSTPONED ")["espn"] == {"period": "Postponed"}


def test_a_live_row_is_unchanged():
    assert _serialize("live", "Top 5th", "1 out")["espn"] == {
        "period": "Top 5th",
        "broadcast": "FS1",
    }
