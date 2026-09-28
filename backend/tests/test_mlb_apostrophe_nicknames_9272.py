"""TYPING O'S, A'S, M'S OR ROX REACHES THAT CLUB. #9272.

Production 2026-09-28 ~02:50Z, `/api/events/search`:

    o's    teams O Elvas CAD · O'Higgins; 1 boxing bout; 0 Orioles
    a's    teams (none); 0 games — while the Athletics row holds "A's"
    m's    teams Texas A&M · Alabama A&M · East Texas A&M · Florida A&M; A&M football
    rox    teams (none); 0 games

The games and markets rails get the curated-alias treatment every earlier
nickname got. The TEAMS card needed a mechanism of its own: its recall is FTS,
and under the English config `a's` reduces to no lexeme and `m's` to `m` — so no
stored alias can ever match them, which `a's` proved by carding nothing beside a
row that already held `A's`. `_team_nickname_team_arms` recalls the named row by
the (sport, name) key the map is written in; `_team_row_aliases` hands the
scorer the curated aliases so the recalled row wins on the word typed.

Measured before adding: each last-word token names exactly ONE baseball_mlb club
over 120 days of events (Orioles 115, Athletics 113, Mariners 107, Rockies 110).
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from app.config import team_aliases
from app.config.team_aliases import (
    CURATED_TEAM_ALIASES,
    _alias_claim_counts,
    curated_team_aliases,
    team_nickname_event_expansions,
    team_nickname_search_expansions,
    team_nickname_team_rows,
)
from app.routes import events as ev
from app.routes.events import (
    _nickname_names_participant,
    _team_card_keyed,
    _team_nickname_event_admissions,
    _team_nickname_team_arms,
    _team_nickname_team_order,
    _team_row_aliases,
)

CURLY = "’"

MLB = {
    "o's": ("baseball_mlb", "Baltimore Orioles"),
    f"o{CURLY}s": ("baseball_mlb", "Baltimore Orioles"),
    "a's": ("baseball_mlb", "Athletics"),
    f"a{CURLY}s": ("baseball_mlb", "Athletics"),
    "m's": ("baseball_mlb", "Seattle Mariners"),
    f"m{CURLY}s": ("baseball_mlb", "Seattle Mariners"),
    "rox": ("baseball_mlb", "Colorado Rockies"),
}


def _sql(clause) -> str:
    return str(clause.compile(compile_kwargs={"literal_binds": True}))


def _code_lines(fn) -> str:
    return "\n".join(
        line for line in inspect.getsource(fn).splitlines()
        if not line.lstrip().startswith("#")
    )


@pytest.mark.parametrize("alias,key", sorted(MLB.items()))
def test_each_nickname_is_curated_for_its_club_with_one_claimant(alias, key) -> None:
    assert alias in CURATED_TEAM_ALIASES[key]
    assert _alias_claim_counts()[alias] == 1


@pytest.mark.parametrize("alias,key", sorted(MLB.items()))
def test_games_and_markets_reach_the_clubs_token_in_its_sport(alias, key) -> None:
    sport_key, team = key
    token = team.split()[-1]
    assert team_nickname_event_expansions()[alias] == (token, sport_key)
    assert team_nickname_search_expansions()[alias] == (token, "baseball")
    admissions = _team_nickname_event_admissions([alias])
    assert _nickname_names_participant(admissions, sport_key, [team, "Some Opponent"])


@pytest.mark.parametrize(
    "alias,wrong_sport,participants",
    [
        ("m's", "soccer_australia_aleague", ["Central Coast Mariners", "Newcastle Jets FC"]),
        ("a's", "baseball_ncaa", ["Athletics", "Some College"]),
    ],
)
def test_the_namesakes_outside_mlb_are_not_named(alias, wrong_sport, participants) -> None:
    admissions = _team_nickname_event_admissions([alias])
    assert not _nickname_names_participant(admissions, wrong_sport, participants)


@pytest.mark.parametrize("alias,key", sorted(MLB.items()))
def test_the_team_arm_names_exactly_that_row(alias, key) -> None:
    sport_key, team = key
    assert team_nickname_team_rows()[alias] == key
    arms = _team_nickname_team_arms([alias])
    assert len(arms) == 1
    sql = _sql(arms[0])
    assert f"sports.key = '{sport_key}'" in sql
    assert team.replace("'", "''") in sql


def test_the_team_arm_composes_and_dedupes() -> None:
    """`a's game` still names the Athletics; the same club twice is one arm."""
    assert len(_team_nickname_team_arms(["a's", "game"])) == 1
    assert len(_team_nickname_team_arms(["a's", f"a{CURLY}s"])) == 1
    assert len(_team_nickname_team_arms(["o's", "m's"])) == 2


@pytest.mark.parametrize("q", [["athletics"], ["yankees"], ["texas", "a&m"], ["o'higgins"], []])
def test_a_query_without_a_nickname_changes_no_sql(q) -> None:
    """No arm and no ORDER BY prefix: both routes compile what they did before."""
    assert _team_nickname_team_arms(q) == []
    assert _team_nickname_team_order([]) == []


def test_the_order_prefix_puts_the_named_rows_first() -> None:
    order = _team_nickname_team_order(_team_nickname_team_arms(["m's"]))
    assert len(order) == 1
    sql = _sql(order[0])
    assert sql.startswith("CASE WHEN") and "Seattle Mariners" in sql
    assert "THEN 0 ELSE 1 END" in sql


def test_a_contested_alias_names_no_row(monkeypatch) -> None:
    """Two claimants: guessing one row is the fan-out the map refuses (#8084)."""
    contested = dict(CURATED_TEAM_ALIASES)
    contested[("icehockey_nhl", "Tampa Bay Lightning")] = ["bolts"]
    contested[("americanfootball_nfl", "Los Angeles Chargers")] = ["bolts"]
    monkeypatch.setattr(team_aliases, "CURATED_TEAM_ALIASES", contested)
    assert "bolts" not in team_aliases.team_nickname_team_rows()
    # The rows still own it — evidence is per row, like `alternate_names`.
    assert team_aliases.curated_team_aliases("icehockey_nhl", "Tampa Bay Lightning") == ("bolts",)


def test_both_teams_queries_use_the_arm_and_the_order() -> None:
    search = _code_lines(ev.search_events)
    assert "_team_nickname_rows = _team_nickname_team_arms(terms)" in search
    assert "team_filter = or_(team_filter, *_team_nickname_rows)" in search
    assert "*_team_nickname_team_order(_team_nickname_rows)," in search
    assert "_build_team_search_filter(_q_identity),\n" not in search

    typeahead = _code_lines(ev.typeahead_search)
    assert "_ta_team_nickname_rows = _team_nickname_team_arms(terms)" in typeahead
    assert "team_filter = or_(team_filter, *_ta_team_nickname_rows)" in typeahead
    assert "*_team_nickname_team_order(_ta_team_nickname_rows)," in typeahead


def test_both_card_builders_hand_the_scorer_the_curated_aliases() -> None:
    assert '"_aliases": _team_row_aliases(row),' in _code_lines(_team_card_keyed)
    assert '"_aliases": _team_row_aliases(row)\n' in _code_lines(ev.typeahead_search)


def _card(rows, q) -> list[dict]:
    return [card for _key, card in _team_card_keyed(rows, q)]


def _row(id_, name, sport_key, aliases):
    return SimpleNamespace(
        id=id_, name=name, slug=None, abbreviation=None, logo_url_small=None,
        current_record=None, sport_key=sport_key, alternate_names=aliases,
        team_rank=0.0, standings_updated_at=None,
    )


# The `m's` window: every A&M row FTS matched on `m`, plus the row the arm recalls
# (its stored names, production 2026-09-28: ['Seattle', 'Mariners']).
M_WINDOW = [
    _row(1, "Texas A&M Aggies", "americanfootball_ncaaf", ["Aggies", "Texas A&M"]),
    _row(2, "Alabama A&M Bulldogs", "basketball_ncaab", ["Bulldogs", "Alabama A&M"]),
    _row(3, "East Texas A&M Lions", "basketball_ncaab", ["Lions"]),
    _row(4, "Florida A&M Rattlers", "americanfootball_ncaaf", ["Rattlers", "FAMU"]),
    _row(10743, "Seattle Mariners", "baseball_mlb", ["Seattle", "Mariners"]),
]


@pytest.mark.parametrize("q", ["m's", f"m{CURLY}s"])
def test_m_s_cards_the_mariners_first(q) -> None:
    card = _card(M_WINDOW, q)
    assert card[0]["name"] == "Seattle Mariners", [c["name"] for c in card]


def test_without_the_curated_evidence_the_a_and_m_rows_would_lead(monkeypatch) -> None:
    """The control: strip the injection and the same window leads with an A&M
    row — so the test above is measuring `_team_row_aliases`, not the fixture."""
    monkeypatch.setattr(ev, "curated_team_aliases", lambda *_: ())
    card = _card(M_WINDOW, "m's")
    assert card[0]["name"] != "Seattle Mariners"


def test_a_s_cards_the_athletics_first() -> None:
    window = [
        _row(11494, "Athletics", "baseball_mlb", ["A's"]),
        _row(5, "Athletic Bilbao", "soccer_spain_la_liga", ["Athletic"]),
    ]
    assert _card(window, "a's")[0]["name"] == "Athletics"


def test_the_literal_a_and_m_query_still_leads_with_a_and_m() -> None:
    card = _card(M_WINDOW, "texas a&m")
    assert card[0]["name"] == "Texas A&M Aggies"


def test_evidence_adds_the_map_aliases_to_the_stored_ones() -> None:
    row = _row(10738, "Baltimore Orioles", "baseball_mlb", ["Baltimore", "Orioles"])
    assert _team_row_aliases(row) == ["Baltimore", "Orioles", "o's", f"o{CURLY}s"]
    assert curated_team_aliases(None, None) == ()


@pytest.mark.parametrize("refused", ["chisox", "os"])
def test_refused_nicknames_stay_out(refused) -> None:
    """`chisox` would expand to `Sox` (the Red Sox too); `os` is Os Marialvas."""
    curated = {a.lower() for aliases in CURATED_TEAM_ALIASES.values() for a in aliases}
    assert refused not in curated
