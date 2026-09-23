"""Independent reviewer counterexample: both opposing teams share a city."""

from tests.integration.test_route_related_futures_team_paths_7867 import (
    _event,
    _make_market,
    _outcome,
    _session,
    _get,
    _ids,
    HOCKEY,
    NHL,
)


async def test_an_opponents_longer_alias_is_not_our_city(monkeypatch):
    event = _event(
        "New York Islanders",
        "New York Rangers",
        sport_key="icehockey_nhl",
        sport_id=NHL,
    )
    market = _make_market(
        id=97867001, name="Stanley Cup Final Matchup", source="polymarket"
    )
    outcomes = [
        _outcome(97867002, market, "New York R and Colorado", 0.15),
        _outcome(97867003, market, "New York I and Colorado", 0.20),
    ]
    body = await _get(
        monkeypatch,
        _session(
            event,
            outcomes,
            roster=HOCKEY,
            home_team_id=54,
            away_team_id=57,
            sport_ids=[NHL],
        ),
        event.id,
    )
    home = _ids(body, "home_team_futures")
    away = _ids(body, "away_team_futures")
    assert 97867002 not in home, f"Rangers' matchup leaked to Islanders: {home}"
    assert 97867002 in away
    assert 97867003 in home
    assert 97867003 not in away, f"Islanders' matchup leaked to Rangers: {away}"
