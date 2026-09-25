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
  * **ONE MISLINK** (after-check, 2026-09-25 16:55Z): production's World Series
    market 114584 links outcome 1634490 "Los Angeles Angels" to the Dodgers'
    team id. Under the first #8627 rule that made the Dodgers group two outcomes
    and the whole market a "player field": every row of `/futures/114584` read
    "Each team's leading player" over team names. A group holding an outcome
    that names its own team is a team row, priced by that outcome.
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
DODGERS = Team(id=5103, sport_id=MLB_SPORT.id, name="Los Angeles Dodgers")
TEAMS = (CUBS, RED_SOX, DODGERS)


class _TeamAwareSession(_FakeSession):
    """The shared fake, plus an answer to the route's team-name read.

    The route asks for team names only when a group holds several outcomes. That
    statement is answered here from `TEAMS` and kept out of `statements`, whose
    count the shared fake uses to tell the market read from the event read.
    """

    def __init__(self, market, events, teams=TEAMS):
        super().__init__(market, events)
        self._teams = teams
        self.team_reads = 0

    async def execute(self, statement):
        cols = getattr(statement, "column_descriptions", None) or []
        if cols and all(c.get("entity") is Team for c in cols) and len(cols) == 2:
            self.team_reads += 1
            return _Rows([(t.id, t.name) for t in self._teams])
        return await super().execute(statement)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


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
    payload = await get_related_events(209, db=_TeamAwareSession(_mvp(outcomes), _cubs_at_red_sox()))
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


def _world_series(outcomes) -> FuturesMarket:
    market = FuturesMarket(
        id=114584,
        source="polymarket",
        external_id="mlb-world-series-champion-2026",
        name="MLB World Series Champion 2026",
        category="championship",
        llm_sport_category="baseball",
        status="open",
    )
    market.outcomes = outcomes
    return market


def _dodgers_at_red_sox() -> list[Event]:
    game = Event(
        id=15320002,
        sport_id=MLB_SPORT.id,
        home_team_id=RED_SOX.id,
        away_team_id=DODGERS.id,
        home_team_name="Boston Red Sox",
        away_team_name="Los Angeles Dodgers",
        status="scheduled",
        commence_time=_SOON,
    )
    game.sport = MLB_SPORT
    return [game]


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["team_first", "mislink_first"])
async def test_one_mislinked_outcome_does_not_turn_a_team_field_into_players(order):
    field = [
        FuturesOutcome(id=1634465, market_id=114584, name="Los Angeles Dodgers",
                       team_id=DODGERS.id, current_probability=0.305),
        FuturesOutcome(id=1634490, market_id=114584, name="Los Angeles Angels",
                       team_id=DODGERS.id, current_probability=0.0),
        FuturesOutcome(id=1634470, market_id=114584, name="Boston Red Sox",
                       team_id=RED_SOX.id, current_probability=0.0535),
    ]
    if order == "mislink_first":
        field = list(reversed(field))
    session = _TeamAwareSession(_world_series(field), _dodgers_at_red_sox())

    payload = await get_related_events(114584, db=session)

    (event,) = payload["events"]
    rows = {lt["team_name"]: lt for lt in event["linked_teams"]}
    assert session.team_reads == 1
    dodgers, red_sox = rows["Los Angeles Dodgers"], rows["Boston Red Sox"]
    assert (dodgers["outcome_name"], dodgers["outcome_is_team"]) == ("Los Angeles Dodgers", True), (
        f"one Angels outcome on the Dodgers' id made the market a player field: {dodgers}"
    )
    assert dodgers["probability"] == pytest.approx(0.305)
    assert red_sox["outcome_is_team"] is True, (
        f"the Red Sox row reads as a player in a team market: {red_sox}"
    )


@pytest.mark.parametrize(
    "outcome, team, expected",
    [
        ("Los Angeles Dodgers", "Los Angeles Dodgers", True),
        ("Dodgers", "Los Angeles Dodgers", True),
        ("St.Louis Cardinals", "St. Louis Cardinals", True),
        ("Los Angeles Angels", "Los Angeles Dodgers", False),
        ("Pete Crow-Armstrong", "Chicago Cubs", False),
        ("Sox", "Boston Red Sox", False),
        (None, "Chicago Cubs", False),
        ("Chicago Cubs", None, False),
    ],
)
def test_an_outcome_names_its_team_only_by_full_name_or_nickname(outcome, team, expected):
    from app.routes.futures import _outcome_names_its_team

    assert _outcome_names_its_team(outcome, team) is expected
