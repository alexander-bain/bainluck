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


async def test_the_market_name_path_is_asked_per_side_too(monkeypatch):
    """The same case one fallback later: the outcome reads only `Yes`, so the
    row can reach a card only through its MARKET name. That path takes its own
    identity argument, and handing it the opponent's identity (or a shared one)
    re-admits the Rangers' question to the Islanders — the outcome-name guard
    above cannot see that, because it never reaches the market-name path."""
    event = _event(
        "New York Islanders",
        "New York Rangers",
        sport_key="icehockey_nhl",
        sport_id=NHL,
    )
    rangers_q = _make_market(
        id=97867011, name="Will New York R Make the Stanley Cup Final?", source="polymarket"
    )
    islanders_q = _make_market(
        id=97867012, name="Will New York I Make the Stanley Cup Final?", source="polymarket"
    )
    outcomes = [
        _outcome(97867013, rangers_q, "Yes", 0.12),
        _outcome(97867014, islanders_q, "Yes", 0.09),
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
    assert 97867013 not in home, f"Rangers' question leaked to Islanders: {home}"
    assert 97867013 in away
    assert 97867014 in home
    assert 97867014 not in away, f"Islanders' question leaked to Rangers: {away}"
