"""A coach's surname does not turn their award into another club's future."""

from types import SimpleNamespace

from app.routes import futures as futures_route
from app.routes.user import _query_team_futures
from tests.test_team_futures_cross_sport_link_2593 import _DB, _market, _outcome, _result


BLUES = 3705
CANADIENS = 568
MARTIN_ST_LOUIS = 237995079
ROBERT_THOMAS = 238012432
BLUES_80_POINTS = 238303228


class _TeamFuturesDB(_DB):
    def __init__(self, team, markets):
        super().__init__(markets, team_sport_key="icehockey_nhl")
        self.team = team

    async def execute(self, stmt, *args, **kwargs):
        sql = str(stmt)
        if "FROM teams JOIN sports" in sql:
            return _result([(self.team, self.team_sport_key)])
        if "futures_outcomes.team_id IN" in sql and "futures_markets" in sql:
            return _result([
                (outcome, market, None)
                for market in self.markets for outcome in market.outcomes
                if outcome.team_id == self.team.id
            ])
        return await super().execute(stmt, *args, **kwargs)


def _team(team_id, name, alternate_names, roster):
    return SimpleNamespace(
        id=team_id, name=name, sport_id=4, alternate_names=alternate_names,
        espn_id=None, roster_players=roster, logo_url_small=None, logo_url=None,
        primary_color=None,
    )


def _coach_award(team_id):
    row = _outcome(MARTIN_ST_LOUIS, "Martin St. Louis", 0.12, team_id=team_id)
    market = _market(63115864, "NHL Jack Adams Award", "hockey", [row], tier=3)
    market.external_id = "KXNHLADAMS-27"
    return market


async def _serve(monkeypatch, team, markets):
    async def _no_unsupported_prices(_db, loaded_markets):
        return {market.id: set() for market in loaded_markets}

    monkeypatch.setattr(
        futures_route, "withheld_price_outcome_ids_for_markets", _no_unsupported_prices,
    )
    return await _query_team_futures([team.id], _TeamFuturesDB(team, markets), limit=30)


async def test_blues_rail_rejects_the_canadiens_coach_and_keeps_club_and_player(monkeypatch):
    # Public St Louis team page and the retained #1511 club aliases. The
    # fixture models the stored-FK branch that can produce the bad public row.
    blues = _team(
        BLUES, "St Louis Blues", ["Blues", "St. Louis", "St. Louis Blues"], ["Robert Thomas"],
    )
    club = _market(62861755, "NHL: Teams to Record 80+ Points", "hockey", [
        _outcome(BLUES_80_POINTS, "St. Louis Blues", 0.84, team_id=BLUES),
    ], tier=5)
    player = _market(63068141, "NHL: Players to Record 80+ Points", "hockey", [
        _outcome(ROBERT_THOMAS, "Robert Thomas", 0.34, team_id=BLUES),
    ], tier=5)
    club.source = player.source = "polymarket"

    data = await _serve(monkeypatch, blues, [_coach_award(BLUES), club, player])

    assert {row["outcome_id"]: row["matched_team"]["id"] for row in data["items"]} == {
        BLUES_80_POINTS: BLUES,
        ROBERT_THOMAS: BLUES,
    }


async def test_canadiens_coach_keeps_a_link_to_his_own_club(monkeypatch):
    canadiens = _team(
        CANADIENS, "Montreal Canadiens", ["Montreal", "Canadiens"], ["Nick Suzuki"],
    )

    data = await _serve(monkeypatch, canadiens, [_coach_award(CANADIENS)])

    assert [(row["outcome_id"], row["matched_team"]["id"]) for row in data["items"]] == [
        (MARTIN_ST_LOUIS, CANADIENS),
    ]


async def test_independent_roster_match_keeps_a_city_surname(monkeypatch):
    blues = _team(
        BLUES, "St Louis Blues", ["St. Louis"], ["Alex St. Louis"],
    )
    roster_control = _coach_award(BLUES)
    roster_control.outcomes[0].name = "Alex St. Louis"

    data = await _serve(monkeypatch, blues, [roster_control])

    assert [row["outcome_name"] for row in data["items"]] == ["Alex St. Louis"]
