"""#4541 — the Sports tab could not rank a marquee GAME.

Measured on production 2026-09-09, seven minutes after the NFL season opener
kicked off: `GET /api/feed?mode=sports&limit=60` put Patriots at Seahawks at
**rank 30, score 66**, behind eight futures, a FINISHED MLB game at 91, eight
routine live MLB games, and six MMA prelim fights at 93-98.

The card was not missing signals. It carried `tier:1`, `class:pro_major`,
`league:nfl`, `timing:primetime`, `timing:national_tv`, `audience:national_interest`,
`confidence_tier: high` and twenty sportsbooks. It scored 66 because every term in
the model measures DRAMA — closeness, upsets, swings, lead changes — and a 0-0
first quarter has none of it, while a routine Tuesday MLB game clears 98 simply by
being a coin flip. The model had no term for how much a fixture MATTERS.

Two mechanisms were measured and both are covered here:

1. `_marquee_pin` — the one instrument that can put a card at the top regardless
   of score — was written at exactly two sites, both keyed on
   `majors_calendar.yaml` **concept_keys**. No `type: "event"` card could ever
   carry it, so the marquee prefix ran in Sports mode with nothing to pin.

2. The season-progress term actively PENALISED the opener. `get_season_multiplier`
   ramps 0.8 (early) to 1.2 (late), which is right for a pennant race and exactly
   backwards for an opener: on the night, NFL scored a season bonus of **-3** while
   a routine September MLB game scored **+2**. That is asserted below as a
   characterisation — the fix here does not change it, and the test exists so the
   next person to touch the ramp sees what it does to openers.

WHY A PIN AND NOT A SCORE BOOST. The drama stack tops out at the 98 display cap,
so an additive term big enough to guarantee the lead would be big enough to distort
everything it touches. A pin buys position and changes no score: the opener still
reads 66, it just reads it at rank 1. `compose_lead` already emitted
`pinned + games + tail` and already anticipated this case in its own comment
("A marquee that is itself an eligible game is already leading").

The window logic lives in `tests/test_feed_marquee_pin.py::TestFixturePinWindow`.
THIS file exists for the other half: that `_score_events` actually STAMPS the pin.
Deleting the stamp leaves every window test green, so the wiring needs its own
red — the ship would otherwise be inert.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_events
from app.utils.highlights import get_league_tier, get_season_multiplier
from app.utils.personalization import PersonalizationContext
from app.utils.tonights_games import MARQUEE_PIN_KEY, compose_lead


# Kickoff 00:20 UTC on 2026-09-10 — Wednesday EVENING in America. The calendar
# entry is dated by the UTC day, which is the trap the entry's own note calls out.
KICKOFF = datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc)
NOW = KICKOFF + timedelta(minutes=7)  # the moment the LIVE defect was measured

# #4541's headline measurement: the opener at rank 43 / score 58, forty-nine
# minutes before kickoff — and 29 minutes BEFORE the kickoff's UTC midnight,
# which is the boundary the window's first version keyed on (CERT-2432).
PREGAME_SPECIMEN = KICKOFF - timedelta(minutes=49)

FIXTURE_ENTRIES = [
    {
        "name": "Test Kickoff Game",
        "marquee": True,
        "fixture": {"sport_key": "americanfootball_nfl"},
        "start": "2026-09-10",
        "end": "2026-09-10",
    }
]


def _sport(key, name):
    s = MagicMock()
    s.key = key
    s.name = name
    return s


def _game(event_id, *, sport_key, sport_name, commence, home_prob):
    """A live game in production's shape, at the opener's real probabilities."""
    e = MagicMock()
    e.id = event_id
    e.status = "live"
    e.commence_time = commence
    e.completed_at = None
    e.statpal_end_time = None
    e.home_team_id = 100 + event_id
    e.away_team_id = 200 + event_id
    e.home_team_name = f"Home{event_id}"
    e.away_team_name = f"Away{event_id}"
    e.opening_home_probability = home_prob
    e.opening_away_probability = 1 - home_prob
    e.win_probability_sources = {"betting": {"home_probability": home_prob}}
    e.opening_home_spread = -3.5
    e.opening_over_under = 44.5
    e.opening_favorite = f"Home{event_id}"
    e.llm_importance = "regular_season"
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.sport = _sport(sport_key, sport_name)
    e.period = "11:07 - 1st Quarter"
    e.raw_ei = 0.33
    e.ei_metadata = None
    e.home_score = 0
    e.away_score = 0
    e.external_id = f"ext-{event_id}"
    e.game_clock = "11:07"
    e.broadcast_info = "NBC"
    e.event_tags = []
    return e


def _opener():
    return _game(
        1,
        sport_key="americanfootball_nfl",
        sport_name="NFL",
        commence=KICKOFF,
        home_prob=0.60,
    )


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


async def _run(events, *, now=NOW, entries=FIXTURE_ENTRIES):
    """Drive the real `_score_events` with a synthetic calendar.

    The calendar is patched rather than read from disk so these assertions do not
    rot when the dated NFL 2026 entry is eventually removed.
    """
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ), patch(
        "app.utils.majors_calendar.marquee_fixture_entries",
        return_value=entries,
    ):
        return await _score_events(
            _mock_db(events), now, None, PersonalizationContext()
        )


class TestScoreEventsStampsThePin:
    """The wiring. Delete the stamp in `_score_events` and these go red."""

    @pytest.mark.asyncio
    async def test_the_opener_is_stamped(self):
        items = await _run([_opener()])
        assert len(items) == 1
        assert items[0][MARQUEE_PIN_KEY] is True

    @pytest.mark.asyncio
    async def test_stamped_at_the_reported_49_minutes_before_kickoff(self):
        """CERT-2432, through the real `_score_events` rather than the primitive.

        #4541's headline measurement is PRE-GAME — the opener at rank 43 with
        score 58, forty-nine minutes before kickoff — and that is the case the
        pin most has to serve, because a scheduled game has no in-game drama by
        definition and is structurally capped. 23:31Z is also 29 minutes BEFORE
        the kickoff's UTC midnight, which is what the first version of the window
        keyed on and why it missed.
        """
        pregame = _game(
            1,
            sport_key="americanfootball_nfl",
            sport_name="NFL",
            commence=KICKOFF,
            home_prob=0.61,
        )
        pregame.status = "scheduled"
        pregame.period = None
        pregame.game_clock = None
        pregame.home_score = None
        pregame.away_score = None

        items = await _run([pregame], now=PREGAME_SPECIMEN)
        assert len(items) == 1, "the scheduled game must be served, not filtered"
        assert items[0][MARQUEE_PIN_KEY] is True

    @pytest.mark.asyncio
    async def test_an_unlisted_game_is_not_stamped(self):
        """The negative control, and it is the one that matters.

        Without it a stamp applied unconditionally would pass every other test
        in this file — and would pin the whole slate.
        """
        mlb = _game(
            2,
            sport_key="baseball_mlb",
            sport_name="MLB",
            commence=KICKOFF - timedelta(hours=2),
            home_prob=0.50,
        )
        items = await _run([mlb])
        assert len(items) == 1
        assert MARQUEE_PIN_KEY not in items[0]

    @pytest.mark.asyncio
    async def test_exactly_one_card_is_pinned_out_of_a_mixed_slate(self):
        mlb = _game(2, sport_key="baseball_mlb", sport_name="MLB",
                    commence=KICKOFF - timedelta(hours=2), home_prob=0.50)
        mls = _game(3, sport_key="soccer_usa_mls", sport_name="MLS",
                    commence=KICKOFF - timedelta(hours=1), home_prob=0.48)
        items = await _run([_opener(), mlb, mls])
        assert len(items) == 3
        assert sum(1 for i in items if i.get(MARQUEE_PIN_KEY)) == 1

    @pytest.mark.asyncio
    async def test_the_pin_is_released_once_the_tail_expires(self):
        items = await _run([_opener()], now=KICKOFF + timedelta(hours=7))
        assert len(items) == 1, "the game must still be SERVED, just not pinned"
        assert MARQUEE_PIN_KEY not in items[0]

    @pytest.mark.asyncio
    async def test_an_empty_calendar_stamps_nothing_and_still_serves(self):
        items = await _run([_opener()], entries=[])
        assert len(items) == 1
        assert MARQUEE_PIN_KEY not in items[0]

    @pytest.mark.asyncio
    async def test_the_pin_does_not_change_the_score(self):
        """A pin buys position, not points.

        Same event, same clock, calendar on and off — the score must be identical.
        If a future edit turns this into a boost, this is the test that says so.
        """
        pinned = (await _run([_opener()]))[0]
        unpinned = (await _run([_opener()], entries=[]))[0]
        assert pinned[MARQUEE_PIN_KEY] is True
        assert pinned["score"] == unpinned["score"]
        assert pinned["_rank_score"] == unpinned["_rank_score"]


class TestThePinnedOpenerLeadsTheTab:
    """`_score_events` + `compose_lead`, composed as the Sports route composes
    them: the reader-visible property, not an internal flag."""

    @pytest.mark.asyncio
    async def test_the_opener_leads_a_slate_of_higher_scoring_games(self):
        rivals = [
            _game(i, sport_key="baseball_mlb", sport_name="MLB",
                  commence=KICKOFF - timedelta(hours=2), home_prob=0.50)
            for i in range(2, 6)
        ]
        items = await _run([*rivals, _opener()])
        # The premise: without the pin the opener does NOT lead on score.
        opener = next(i for i in items if i["data"]["sport"] == "americanfootball_nfl")
        assert any(i["score"] > opener["score"] for i in items), (
            "vacuous — the opener already outscores the slate, so leading proves nothing"
        )

        out = compose_lead(items, include_tonights_games=False, now=NOW)
        assert out[0]["data"]["sport"] == "americanfootball_nfl"
        assert len(out) == len(items)


class TestTheSeasonRampPenalisesOpeners:
    """Characterisation of mechanism 2 — measured, unfixed, and deliberately so.

    A pin puts the opener at rank 1; it does not repair the score that put it at
    rank 30, and the two are separate ships. This records the number so the next
    person to touch the ramp is told what it does to a season's first game rather
    than having to rediscover it on a Wednesday night.
    """

    def test_the_nfl_opener_is_penalised_while_september_mlb_is_rewarded(self):
        def season_bonus(sport_key):
            mult = get_season_multiplier(sport_key, KICKOFF)
            tier = get_league_tier(sport_key)
            if mult == 1.0 or tier not in (1, 2):
                return 0
            return int((20 if tier == 1 else 10) * (mult - 1.0))

        nfl = season_bonus("americanfootball_nfl")
        mlb = season_bonus("baseball_mlb")
        assert nfl < 0, "the season opener is scored as 'early season, matters less'"
        assert mlb > 0, "a routine September MLB game is scored as 'late season, matters more'"
        assert nfl < mlb
