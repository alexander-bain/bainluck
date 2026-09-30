"""#9897 — a bare city names no one club, so #8738's lead key stops sinking NFL games.

`chicago` on production 2026-09-30: the card (Blackhawks, Bulls, Cubs, Sky, White
Sox) carried the alias `Chicago` on every row and the Bears carried only `Bears`,
so the lead tier was five sports and Jets @ Bears this Sunday sat under Bulls
games in late October. The route arm, with an in-rig strawman, is
`tests/integration/test_search_city_lead_tier_pg_9897.py`. These pin the helper.
"""

from types import SimpleNamespace

import pytest

from app.routes.events import (
    _alias_restates_name_prefix,
    _team_card_keyed,
    _team_card_lead_sport_keys,
)


def _team(tid, name, sport_key, aliases, team_rank=0.2):
    return SimpleNamespace(
        id=tid, name=name, slug=None, abbreviation=None, logo_url_small=None,
        current_record=None, sport_key=sport_key, alternate_names=aliases,
        standings_updated_at=None, team_rank=team_rank,
    )


# Production's rows (db-query 2026-09-30), in the window's arrival order: the
# city-aliased rows out-rank the Bears on `ts_rank_cd`.
CHICAGO = [
    _team(576, "Chicago Blackhawks", "icehockey_nhl", ["Blackhawks", "Chicago"]),
    _team(36, "Chicago Bulls", "basketball_nba", ["Bulls", "Chicago"]),
    _team(10714, "Chicago Cubs", "baseball_mlb", ["Cubs", "cubbies", "Chicago"]),
    _team(13467, "Chicago Sky", "basketball_wnba", ["Chicago", "Sky"]),
    _team(10734, "Chicago White Sox", "baseball_mlb", ["White Sox", "Chicago"]),
    _team(16, "Chicago Fire", "soccer_usa_mls", ["Chicago", "Chicago Fire FC"]),
    _team(561, "Chicago Bears", "americanfootball_nfl", ["Bears"], 0.1),
]

LOS_ANGELES = [
    _team(64, "Los Angeles Kings", "icehockey_nhl",
          ["Los Angeles Kings", "Los Angeles", "Kings"]),
    _team(10712, "Los Angeles Angels", "baseball_mlb", ["Los Angeles", "Angels", "halos"]),
    _team(10707, "Los Angeles Dodgers", "baseball_mlb", ["Los Angeles", "Dodgers"]),
    _team(49, "Los Angeles Lakers", "basketball_nba", ["Los Angeles", "Lakers"]),
    _team(537, "Los Angeles Clippers", "basketball_nba",
          ["LA", "Clippers", "LA Clippers", "Los Angeles C"]),
    _team(544, "Los Angeles Rams", "americanfootball_nfl", ["Rams"], 0.1),
    _team(556, "Los Angeles Chargers", "americanfootball_nfl", ["Chargers"], 0.1),
]


@pytest.mark.parametrize("rows,query", [(CHICAGO, "chicago"), (LOS_ANGELES, "los angeles")])
def test_a_city_query_no_longer_sinks_the_nfl_club(rows, query):
    """NFL joins the lead tier, or every club ties and the key disarms (None —
    the games list is then time-ordered). Either way no Bears/Rams game sorts
    under a basketball game because of the key."""
    keys = _team_card_lead_sport_keys(rows, query)
    assert keys is None or "americanfootball_nfl" in keys, keys


def test_a_less_prominent_club_still_sinks_under_a_city():
    """Still a key, not a disarm: MLS (and the teamless Nueva Chicago) sort after
    the prominent leagues' games, as before."""
    keys = _team_card_lead_sport_keys(CHICAGO, "chicago")
    assert "soccer_usa_mls" not in keys


@pytest.mark.parametrize("rows,query", [(CHICAGO, "chicago"), (LOS_ANGELES, "los angeles")])
def test_the_card_does_not_move(rows, query, monkeypatch):
    """The stripped aliases reach only the lead tier: with the helper made a
    no-op the card is identical, row for row."""
    from app.routes import events as ev

    card = [c["name"] for _k, c in _team_card_keyed(rows, query)]
    monkeypatch.setattr(ev, "_alias_restates_name_prefix", lambda alias, name: False)
    assert [c["name"] for _k, c in _team_card_keyed(rows, query)] == card
    assert "Chicago Bears" not in card and "Los Angeles Rams" not in card, (
        "the card half is a separate call (#9897); this ship moves only the games"
    )


def test_a_nickname_query_keeps_its_one_club():
    """`bulls` names the Bulls; nothing about a city alias reaches it."""
    assert _team_card_lead_sport_keys(CHICAGO, "bulls") == frozenset({"basketball_nba"})


def test_a_school_named_like_its_state_still_leads_alone():
    """`texas`: the Rangers lead (MLB is prominent, NCAAF is not), so the key the
    #9040 fix reads is still the Rangers' sport."""
    rows = [
        _team(10742, "Texas Rangers", "baseball_mlb", ["Rangers", "Texas"]),
        _team(834, "Texas Longhorns", "americanfootball_ncaaf", ["Longhorns", "Texas"]),
        _team(14125, "Texas Tech Red Raiders", "americanfootball_ncaaf", ["Red Raiders"]),
    ]
    assert _team_card_lead_sport_keys(rows, "texas") == frozenset({"baseball_mlb"})


@pytest.mark.parametrize("alias,name,expected", [
    ("Chicago", "Chicago Bulls", True),
    ("Los Angeles", "Los Angeles Kings", True),
    ("new york", "New York Knicks", True),
    ("Bulls", "Chicago Bulls", False),            # a nickname is a suffix
    ("Los Angeles Kings", "Los Angeles Kings", False),  # the name itself
    ("Los Angeles C", "Los Angeles Clippers", False),   # not whole words
    ("Chicago Fire FC", "Chicago Fire", False),   # longer than the name
    ("LA", "Los Angeles Clippers", False),
    ("", "Chicago Bulls", False),
])
def test_what_counts_as_restating_the_name(alias, name, expected):
    assert _alias_restates_name_prefix(alias, name) is expected
