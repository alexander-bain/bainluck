"""#8627: a player-award page stops printing one player's price as a team's odds.

WHAT A READER SAW, on production 2026-09-25 13:45Z, on `/futures/209` —
**NL MVP Winner?** — whose hero reads 100% for Pete Crow-Armstrong, a Cub.
Under "Games This Week — Each team's odds in this market":

    Today 10:05 AM · Chicago Cubs at Boston Red Sox · Chicago Cubs 1% · Boston Red Sox 1%

`GET /api/futures/209/related-events` served `{team_name: Chicago Cubs,
outcome_name: Nico Hoerner, probability: 0.01}`. `team_outcome_map` was keyed by
`team_id` and written last-wins, so a field with six Cubs kept whichever Cub came
last, and the strip wore his price under the team's name.

═══ THE ARMS ═══

  * **LEADER, BOTH ORDERS**: the Cubs row carries Crow-Armstrong's 0.995 whether
    he is served first or last. The old last-wins map passes one of the two
    orders, so the pair is what makes insertion order irrelevant.
  * **WHOLE MARKET**: the Red Sox row, whose team carries ONE player, is still
    flagged `outcome_is_team: False`. It is one player in a player field, not a
    team price, and a per-team count would have called it a team.
  * **TIE / UNPRICED**: equal prices pick the lower outcome id, and an unpriced
    outcome never outranks a priced one.
  * **CONTROL**: a team field (the World Series, one outcome per team) is served
    with `outcome_is_team: True` and its outcome unchanged. Without it, a route
    that flagged every market would pass everything above.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Event, FuturesMarket, FuturesOutcome, Team
from app.routes.futures import get_related_events

from tests.test_futures_related_events_sport_guard import (  # noqa: E402
    MLB_SPORT,
    _FakeSession,
    _events as _ws_events,
    _market as _ws_market,
)

_SOON = datetime.now(timezone.utc) + timedelta(days=1)

CUBS = Team(id=5101, sport_id=MLB_SPORT.id, name="Chicago Cubs")
RED_SOX = Team(id=5102, sport_id=MLB_SPORT.id, name="Boston Red Sox")


def _outcome(oid, name, team, p):
    return FuturesOutcome(
        id=oid, market_id=209, name=name, team_id=team.id, current_probability=p
    )


def _mvp(outcomes) -> FuturesMarket:
    market = FuturesMarket(
        id=209,
        source="kalshi",
        external_id="KXNLMVP-26",
        name="NL MVP Winner?",
        category="award",
        llm_sport_category="baseball",
        status="open",
    )
    market.outcomes = outcomes
    return market


def _cubs_at_red_sox() -> list[Event]:
    game = Event(
        id=15320001,
        sport_id=MLB_SPORT.id,
        home_team_id=RED_SOX.id,
        away_team_id=CUBS.id,
        home_team_name="Boston Red Sox",
        away_team_name="Chicago Cubs",
        status="scheduled",
        commence_time=_SOON,
    )
    game.sport = MLB_SPORT
    return [game]


def _field():
    """Production's shape: the favourite and a 1% teammate, plus a lone Red Sox."""
    return [
        _outcome(21, "Pete Crow-Armstrong", CUBS, 0.995),
        _outcome(22, "Nico Hoerner", CUBS, 0.01),
        _outcome(23, "Caleb Durbin", RED_SOX, 0.01),
    ]


async def _linked(outcomes):
    payload = await get_related_events(209, db=_FakeSession(_mvp(outcomes), _cubs_at_red_sox()))
    (event,) = payload["events"]
    return {lt["team_name"]: lt for lt in event["linked_teams"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["favourite_first", "favourite_last"])
async def test_the_team_row_carries_its_leading_player_whatever_the_order(order):
    field = _field()
    if order == "favourite_last":
        field = list(reversed(field))

    cubs = (await _linked(field))["Chicago Cubs"]

    assert cubs["outcome_name"] == "Pete Crow-Armstrong", (
        f"the Cubs row carries {cubs['outcome_name']} at {cubs['probability']}: "
        "one arbitrary Cub's price, the #8627 defect"
    )
    assert cubs["probability"] == pytest.approx(0.995)
    assert cubs["outcome_is_team"] is False


@pytest.mark.asyncio
async def test_a_lone_player_in_a_player_field_is_still_not_a_team_price():
    red_sox = (await _linked(_field()))["Boston Red Sox"]

    assert red_sox["outcome_name"] == "Caleb Durbin"
    assert red_sox["outcome_is_team"] is False


@pytest.mark.asyncio
async def test_a_tie_picks_the_lower_id_and_unpriced_never_leads():
    tied = [
        _outcome(32, "Dansby Swanson", CUBS, 0.02),
        _outcome(31, "Ian Happ", CUBS, 0.02),
        _outcome(30, "Unpriced Cub", CUBS, None),
        _outcome(23, "Caleb Durbin", RED_SOX, 0.01),
    ]

    cubs = (await _linked(tied))["Chicago Cubs"]

    assert cubs["outcome_name"] == "Ian Happ"


@pytest.mark.asyncio
async def test_control_a_team_field_is_served_as_before():
    payload = await get_related_events(1, db=_FakeSession(_ws_market(), _ws_events()))

    (event,) = payload["events"]
    (dodgers,) = event["linked_teams"]
    assert dodgers["team_name"] == "Los Angeles Dodgers"
    assert dodgers["outcome_name"] == "Los Angeles Dodgers"
    assert dodgers["probability"] == pytest.approx(0.30)
    assert dodgers["outcome_is_team"] is True
