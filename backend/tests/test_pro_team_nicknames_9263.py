"""TYPING FINS OR DUBS REACHES THAT TEAM, NOT A NAMESAKE. #9263.

Production 2026-09-28 02:08Z, `/api/events/search`:

    fins     teams Finland · Finnentrop/Bamenohl · Wingate and Finchley FC;
             5 games, all Finland soccer; 0 Dolphins
    dubs     teams Dubai Basketball · Shelbourne Dublin; 9 games; 0 Warriors

Measured before adding (the #8685 / #9076 / #9080 bar): each last-word token
names exactly ONE club in its sport over 120 days of events. Open markets in the
futures arm's category: Dolphins 18/19 football (the 19th, a Swedish basketball
game filed as football, `phins` already reaches), Warriors 4/6 basketball (two
Shinshu Brave Warriors B.League rows — kept, see the config comment). Refused: `celts`, `bolts` — each
is also how another club's fans type their own team. (`avs` was refused here too and
admitted in a later round: `test_avs_avalanche_9263.py`.)
"""

from __future__ import annotations

import pytest

from app.config.team_aliases import (
    CURATED_TEAM_ALIASES,
    _alias_claim_counts,
    team_nickname_event_expansions,
    team_nickname_search_expansions,
)
from app.routes.events import (
    _nickname_names_participant,
    _team_nickname_event_admissions,
    _team_nickname_event_arms,
)

PRO = {
    "fins": ("americanfootball_nfl", "Miami Dolphins"),
    "dubs": ("basketball_nba", "Golden State Warriors"),
}


def _sql(arm) -> str:
    return str(arm.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize("alias,key", sorted(PRO.items()))
def test_each_nickname_is_curated_for_its_club(alias, key) -> None:
    assert alias in CURATED_TEAM_ALIASES[key]


def test_phins_survives_beside_fins() -> None:
    """The Dolphins entry now carries two aliases; #9080's must not be lost."""
    assert CURATED_TEAM_ALIASES[("americanfootball_nfl", "Miami Dolphins")] == ["phins", "fins"]
    assert team_nickname_event_expansions()["phins"] == ("Dolphins", "americanfootball_nfl")


@pytest.mark.parametrize("alias", sorted(PRO))
def test_each_nickname_has_exactly_one_claimant(alias) -> None:
    """A second claimant makes the alias CONTESTED and `_alias_claim_counts`
    (#8084) drops it from BOTH derived maps, silently."""
    assert _alias_claim_counts()[alias] == 1


@pytest.mark.parametrize("alias,key", sorted(PRO.items()))
def test_the_game_arm_is_the_clubs_token_scoped_to_its_sport(alias, key) -> None:
    sport_key, team = key
    token = team.split()[-1]
    assert team_nickname_event_expansions()[alias] == (token, sport_key)

    arms = _team_nickname_event_arms([alias])
    assert len(arms) == 1, f"{alias} produced {len(arms)} arms"
    sql = _sql(arms[0])
    assert token.lower() in sql.lower()
    assert sport_key in sql, f"{alias} built an arm not scoped to {sport_key}"


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("fins", ("Dolphins", "football")),
        ("dubs", ("Warriors", "basketball")),
    ],
)
def test_each_gets_a_futures_arm_scoped_to_its_category(alias, expected) -> None:
    """Neither is spelled inside its token (unlike `phins` in Dol*phins*),
    so the plain ILIKE futures rail reached none of the club's markets."""
    assert team_nickname_search_expansions()[alias] == expected


@pytest.mark.parametrize("alias,key", sorted(PRO.items()))
def test_the_nickname_names_its_own_game(alias, key) -> None:
    sport_key, team = key
    admissions = _team_nickname_event_admissions([alias])
    assert _nickname_names_participant(admissions, sport_key, [team, "Some Opponent"])


@pytest.mark.parametrize(
    "alias,wrong_sport,participants",
    [
        # The namesakes the sport scope exists to refuse — each served on 9/27–28.
        ("fins", "rugbyleague_nrl", ["Dolphins", "Melbourne Storm"]),
        ("dubs", "rugbyleague_nrl", ["New Zealand Warriors", "Penrith Panthers"]),
        ("dubs", "basketball_other", ["Shinshu Brave Warriors", "Yokohama B-Corsairs"]),
    ],
)
def test_the_nickname_does_not_name_another_sports_row(alias, wrong_sport, participants) -> None:
    admissions = _team_nickname_event_admissions([alias])
    assert not _nickname_names_participant(admissions, wrong_sport, participants)


@pytest.mark.parametrize("shared", ["celts", "bolts"])
def test_shared_nicknames_stay_out(shared) -> None:
    """`celts` is also Celtic FC ("the Celts"); `bolts` the Chargers AND the
    Lightning. Curated for one it takes the word from the other. (`avs` was here
    too; it is AVS Futebol's own name, so it takes nothing — see
    `test_avs_avalanche_9263.py`.)"""
    curated = {a.lower() for aliases in CURATED_TEAM_ALIASES.values() for a in aliases}
    assert shared not in curated
