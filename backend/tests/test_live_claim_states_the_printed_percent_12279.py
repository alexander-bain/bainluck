"""#12279 — a live Discover card's movement sentence states the percent the card prints.

**SHIP: a live game card stops printing two numbers for one team — "Arsenal 33%"
above "Arsenal chance fell from 50% to 34%".** (Pillar: TRUTH.)

The card prints `current_odds.*_rendered_percent`: the pair rounded ONCE as a duel
(`graded_card.rendered_duel_percents`), which keeps the leader's rounding and DERIVES
the trailer as ``100 - leader``. The live sentence rounded its own side alone with
`rendered_percent`. The two agree on the leader and on every value off the
half-percent grid; on a trailing side that sits on a half-percent they do not —
0.335 is 33 on the card (``100 - 67``) and 34 in the sentence. Swept over every
5-decimal probability, the two disagree on exactly the 100 values ``0.005, 0.015,
… 0.995``, every one on the trailing side. The venues quote half-cents, so the blend
lands there often.

The fix is #6181's, live: the route hands the composer the card's own printed pair
(`duel_percents_by_side`, the serializer's rounding), and the card is told which
percent its sentence states (`live_claim_percent`) so the web card can hide the
sentence when it repaints the number before the next read (the other half of
#12279, in `useDiscoverPriceStream`).

THESE TESTS DRIVE `_score_events` (as `test_feed_card_live_latch_5324` does): a
`format_event_data` or `compose_live_claim` guard keeps passing when the route
stops handing the percents over, and the route is where the two numbers meet.

WHAT EACH TEST DEFENDS:

* 🔴 the specimen shape, draw-priced: the home trailer at 0.335 — card 33, sentence 33;
* 🔴 two-way, home rising to a trailing 0.335, and away rising to a trailing 0.335;
* `reason` states the same number as `headline` (it is composed separately);
* the leader, and a value off the half-percent grid, read as before;
* an underdog-lead sentence states no current percent, so it carries none;
* the composer without the percents reads as before (its other callers).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_events
from app.utils.feed_reasons import compose_live_claim
from app.utils.personalization import PersonalizationContext

NOW = datetime(2026, 11, 7, 16, 22, 0, tzinfo=timezone.utc)
HOME, AWAY = "Arsenal", "Hull City"


def _sport(key):
    s = MagicMock()
    s.key = key
    s.name = key
    return s


def _event(event_id, *, sport_key, opening_home, opening_away, home_score=0, away_score=0):
    """A live row shaped like the specimen (15335208, Hull City @ Arsenal)."""
    e = MagicMock()
    e.id = event_id
    e.status = "live"
    e.commence_time = NOW - timedelta(minutes=82)
    e.home_team_id = 10 + event_id
    e.away_team_id = 20 + event_id
    e.home_team_name = HOME
    e.away_team_name = AWAY
    e.opening_home_probability = opening_home
    e.opening_away_probability = opening_away
    e.closing_home_probability = None
    e.win_probability_sources = {}
    e.opening_home_spread = None
    e.opening_over_under = None
    e.opening_favorite = HOME
    e.llm_importance = "marquee"
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.sport = _sport(sport_key)
    e.statpal_end_time = None
    e.completed_at = None
    e.period = "2nd Half"
    e.game_clock = "62'"
    e.raw_ei = 90.0
    e.ei_metadata = None
    e.home_score = home_score
    e.away_score = away_score
    # No current score observation: the field claim is refused (#10561), so the
    # card's one claim is the price movement under test.
    e.score_source = None
    e.score_observed_at = None
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


async def _card(event, blend):
    """The card the route builds for ``event`` with its blend at ``blend``.

    `my_teams_only=True` only lowers the admission bar to 0 (see the 5324 test);
    the claim and the serializer are the same code on every rail.
    """
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ), patch("app.routes.feed._compute_aggregate_probability", return_value=blend):
        items = await _score_events(
            _mock_db([event]), now=NOW, sport_filter=None, ctx=PersonalizationContext(),
            my_teams_only=True, my_team_names=[HOME],
        )
    cards = [i for i in items if i["type"] == "event" and i["data"]["id"] == event.id]
    assert cards, "no card was built at all — the test proves nothing as written"
    return cards[0]


def _printed(card, side):
    return card["data"]["current_odds"][f"{side}_rendered_percent"]


# ── 🔴 THE DEFECT: the trailing side on a half-percent ───────────────────────


@pytest.mark.asyncio
async def test_draw_priced_home_trailer_states_the_printed_33_not_34():
    card = await _card(
        _event(1, sport_key="soccer_epl", opening_home=0.50, opening_away=0.25), 0.335,
    )
    assert _printed(card, "home") == 33
    assert card["headline"] == "Arsenal chance fell from 50% to 33%"
    assert card["live_claim_percent"] == {"side": "home", "percent": 33}


@pytest.mark.asyncio
async def test_two_way_home_rising_to_a_trailing_half_percent():
    card = await _card(
        _event(2, sport_key="americanfootball_nfl", opening_home=0.15, opening_away=0.85),
        0.335,
    )
    assert _printed(card, "home") == 33
    assert card["headline"] == "Arsenal chance rose from 15% to 33%"
    assert card["live_claim_percent"] == {"side": "home", "percent": 33}


@pytest.mark.asyncio
async def test_two_way_away_rising_to_a_trailing_half_percent():
    # Home 0.665 is the leader; away is `round(1 - 0.665, 6)` = 0.335, derived 33.
    card = await _card(
        _event(3, sport_key="americanfootball_nfl", opening_home=0.85, opening_away=0.15),
        0.665,
    )
    assert _printed(card, "away") == 33
    assert card["headline"] == "Hull City chance rose from 15% to 33%"
    assert card["live_claim_percent"] == {"side": "away", "percent": 33}


@pytest.mark.asyncio
async def test_reason_states_the_same_number_as_the_headline():
    card = await _card(
        _event(4, sport_key="soccer_epl", opening_home=0.50, opening_away=0.25), 0.335,
    )
    assert card["reason"] == card["headline"]


# ── controls: what was already right stays right ─────────────────────────────


@pytest.mark.asyncio
async def test_the_leader_on_a_half_percent_reads_as_before():
    """The issue's own 66.5% case: the leader keeps its rounding on both."""
    card = await _card(
        _event(5, sport_key="soccer_epl", opening_home=0.8313, opening_away=0.05), 0.665,
    )
    assert _printed(card, "home") == 67
    assert card["headline"] == "Arsenal chance fell from 83% to 67%"
    assert card["live_claim_percent"] == {"side": "home", "percent": 67}


@pytest.mark.asyncio
async def test_a_value_off_the_half_percent_grid_reads_as_before():
    card = await _card(
        _event(6, sport_key="soccer_epl", opening_home=0.8313, opening_away=0.05), 0.6612,
    )
    assert _printed(card, "home") == 66
    assert card["headline"] == "Arsenal chance fell from 83% to 66%"


@pytest.mark.asyncio
async def test_an_underdog_lead_states_no_current_percent():
    """"Hull City leading after starting at 5%" quotes the kickoff price only."""
    event = _event(7, sport_key="soccer_epl", opening_home=0.8313, opening_away=0.05,
                   home_score=0, away_score=1)
    event.score_source = "espn"
    event.score_observed_at = NOW - timedelta(seconds=20)
    card = await _card(event, 0.335)
    assert card["headline"] == "Hull City leading after starting at 5%"
    assert "live_claim_percent" not in card


def test_the_composer_without_printed_percents_reads_as_before():
    """`compose_live_claim`'s other callers pass no percents and keep their sentence."""
    claim = compose_live_claim(
        home_team=HOME, away_team=AWAY, status="live", home_probability=0.335,
        away_probability=0.665, opening_home_prob=0.50, home_score=0, away_score=0,
        sport="soccer_epl", opening_away_prob=0.25,
    )
    assert claim.sentence == "Arsenal chance fell from 50% to 34%"
    assert (claim.stated_side, claim.stated_percent) == ("home", 34)
