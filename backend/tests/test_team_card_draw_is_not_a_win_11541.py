"""#11541 — a soccer team page must not count the draw as its club's win.

WHAT A READER SAW (production, Sun Nov 8, 4:01 PM PT). Arsenal's team page said
82% to win at Newcastle (event 15340934). The game's own page had Newcastle at
18% and printed no Arsenal number; Arsenal's own three-way price was 59%.

WHY. The blend states the HOME side's chance, and `_format_event_brief` turned
it team-relative for an away row as `1 - home`. On a two-way sport that is the
away side's chance. On a sport that prices a draw it is "home does not win",
which is the away side's chance PLUS the draw: 1 - 0.178 = 0.822. Its comment
said every sport was two-way normalised, measured 2026-09-11; #1011 made soccer
three-way five days later.

THE RULE NOW. On a draw-priced sport (the shared `sport_prices_a_draw`) an away
row never serves `1 - home`. Before kickoff it serves the club's own price: the
stored away leg, which since #1011 is de-vigged over the whole board, but only
while its pair still leaves a draw (`printable_away`). Otherwise it serves
nothing, because a pre-kickoff price is not a live chance.

The fixture is the production row: its values verbatim, its times as offsets
from the real clock, because the formatter and the blend read the real clock
(gotcha #44).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.routes.teams import _format_event_brief
from app.utils.aggregation import compute_aggregate_probability

#: Production event 15340934 (Newcastle United v Arsenal, EPL), read Sun Nov 8,
#: 4:05 PM PT. Values verbatim; each stamp keeps its age at the read (the books
#: 20 minutes old, Polymarket 10 h 26 min older).
READ_AT = datetime.now(timezone.utc) - timedelta(minutes=20)
NEWCASTLE_ARSENAL_SOURCES = {
    "betting": {"value": 0.1779, "updated_at": READ_AT.isoformat()},
    "polymarket": {
        "value": 0.16,
        "updated_at": (READ_AT - timedelta(hours=10, minutes=26)).isoformat(),
    },
    "betting_book_count": 7,
}
OPENING_HOME = Decimal("0.1779")
OPENING_AWAY = Decimal("0.5943")


class FakeSport:
    def __init__(self, key):
        self.key = key


class FakeTeam:
    def __init__(self, *, id, name):
        self.id = id
        self.name = name


class FakeEvent:
    """What `_format_event_brief` reads, and no more."""

    def __init__(
        self,
        *,
        sport_key="soccer_epl",
        status="scheduled",
        kickoff_in=timedelta(days=13),
        opening_home=OPENING_HOME,
        opening_away=OPENING_AWAY,
        sources=NEWCASTLE_ARSENAL_SOURCES,
    ):
        self.id = 15340934
        self.sport = FakeSport(sport_key)
        self.home_team_id = 1
        self.away_team_id = 2
        self.home_team_name = "Newcastle United"
        self.away_team_name = "Arsenal"
        self.commence_time = datetime.now(timezone.utc) + kickoff_in
        self.completed_at = None
        self.status = status
        self.home_score = self.away_score = None
        self.win_probability_sources = sources
        self.opening_home_probability = opening_home
        self.opening_away_probability = opening_away


NEWCASTLE = FakeTeam(id=1, name="Newcastle United")
ARSENAL = FakeTeam(id=2, name="Arsenal")


def test_the_away_club_reads_its_own_price_not_the_draw_folded_in():
    """The headline: 59%, not 82%."""
    card = _format_event_brief(FakeEvent(), ARSENAL)
    assert card["is_home"] is False
    assert card["win_probability"] == pytest.approx(0.594)
    assert card["win_probability"] != pytest.approx(0.822, abs=0.01)


def test_the_home_club_still_reads_the_blend_its_game_page_shows():
    """The home row was right and must stay the event page's own number."""
    event = FakeEvent()
    card = _format_event_brief(event, NEWCASTLE)
    assert card["win_probability"] == pytest.approx(
        round(compute_aggregate_probability(event), 3)
    )
    assert card["win_probability"] == pytest.approx(0.178, abs=0.002)


def test_the_three_numbers_leave_room_for_the_draw():
    event = FakeEvent()
    home = _format_event_brief(event, NEWCASTLE)["win_probability"]
    away = _format_event_brief(event, ARSENAL)["win_probability"]
    assert home + away < 0.99, "home and away still sum to one: the draw is folded in"


def test_a_live_away_row_serves_nothing():
    """The stored away leg is the last pre-kickoff consensus, not a live chance."""
    card = _format_event_brief(
        FakeEvent(status="live", kickoff_in=-timedelta(minutes=30)), ARSENAL
    )
    assert card["win_probability"] is None


def test_a_row_still_marked_scheduled_after_kickoff_serves_nothing():
    """The status beat can lag kickoff; the clock decides, not the label."""
    card = _format_event_brief(FakeEvent(kickoff_in=-timedelta(minutes=10)), ARSENAL)
    assert card["win_probability"] is None


def test_an_away_leg_that_is_only_the_complement_is_withheld():
    """A pair that sums to one carries no draw, so its away leg is `1 - home`
    again under another name (`printable_away`)."""
    card = _format_event_brief(
        FakeEvent(opening_home=Decimal("0.4100"), opening_away=Decimal("0.5900")), ARSENAL
    )
    assert card["win_probability"] is None


@pytest.mark.parametrize("opening_home,opening_away", [(None, OPENING_AWAY), (OPENING_HOME, None)])
def test_half_a_pair_is_not_a_price(opening_home, opening_away):
    card = _format_event_brief(
        FakeEvent(opening_home=opening_home, opening_away=opening_away), ARSENAL
    )
    assert card["win_probability"] is None


def test_a_two_way_sport_keeps_the_complement():
    """The control: outside draw sports `1 - home` IS the away side's chance."""
    event = FakeEvent(sport_key="basketball_nba")
    home = _format_event_brief(event, NEWCASTLE)["win_probability"]
    away = _format_event_brief(event, ARSENAL)["win_probability"]
    assert away == pytest.approx(round(1.0 - compute_aggregate_probability(event), 3))
    assert home + away == pytest.approx(1.0, abs=0.0015)
