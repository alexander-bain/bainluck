"""TYPING PHINS, STROS OR HALOS REACHES THAT TEAM'S GAME. #9080.

Production 2026-09-27 ~06:50Z, `/api/events/search`:

    phins    0 events (Dolphins–Chiefs is today; `dolphins` -> 24, that game first)
    stros    0 events (`astros` -> 22, Athletics–Astros today first)
    halos    0 events (`angels` -> 23, Mariners–Angels today first)

`/search?q=phins` did show Dolphins market rows, but only because `phins` is
spelled inside `Dolphins`; there was no game card, and an NRL Dolphins futures
card sat among the six. `CURATED_TEAM_ALIASES` had `pats`/`jags` and
`yanks`/`phils` but not these three.

Measured before adding (the #8685 / #9076 bar): each last-word token names
exactly ONE club in its sport over 120 days of events, and every open baseball
futures market holding `Astros` (18) or `Angels` (34) is that club's.
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
    "phins": ("americanfootball_nfl", "Miami Dolphins"),
    "stros": ("baseball_mlb", "Houston Astros"),
    "halos": ("baseball_mlb", "Los Angeles Angels"),
}


def _sql(arm) -> str:
    return str(arm.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize("alias,key", sorted(PRO.items()))
def test_each_nickname_is_curated_for_its_club(alias, key) -> None:
    assert alias in CURATED_TEAM_ALIASES[key]


@pytest.mark.parametrize("alias", sorted(PRO))
def test_each_nickname_has_exactly_one_claimant(alias) -> None:
    """A second claimant (the preseason sport key, say) makes the alias CONTESTED
    and `_alias_claim_counts` (#8084) drops it from BOTH derived maps — the game
    arm this issue exists for would vanish while the config still lists it."""
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


def test_only_halos_gets_a_futures_arm() -> None:
    """`phins` and `stros` are spelled inside their tokens (Dol*phins*, A*stros*),
    so the plain ILIKE futures arm already reaches them — the `9ers` rule. The
    game arm keeps both because it word-matches."""
    s = team_nickname_search_expansions()
    assert s["halos"] == ("Angels", "baseball")
    for inside in ("phins", "stros"):
        assert inside not in s


@pytest.mark.parametrize("alias,key", sorted(PRO.items()))
def test_the_nickname_names_its_own_game(alias, key) -> None:
    """The typeahead admission/promotion test (#4847/#4986) admits the club's game."""
    sport_key, team = key
    admissions = _team_nickname_event_admissions([alias])
    assert _nickname_names_participant(admissions, sport_key, [team, "Some Opponent"])


@pytest.mark.parametrize(
    "alias,wrong_sport,participants",
    [
        # The namesakes the sport scope exists to refuse.
        ("phins", "rugbyleague_nrl", ["Dolphins", "Melbourne Storm"]),
        ("halos", "soccer_england_league2", ["Tonbridge Angels FC", "Torquay United FC"]),
        ("stros", "basketball_other", ["Astros de Jalisco", "Halcones de Xalapa"]),
    ],
)
def test_the_nickname_does_not_name_another_sports_row(alias, wrong_sport, participants) -> None:
    admissions = _team_nickname_event_admissions([alias])
    assert not _nickname_names_participant(admissions, wrong_sport, participants)


def test_friars_stays_out() -> None:
    """Production sends `friars` to the Providence Friars team card, which is
    their actual name; curating it for the Padres would take it from them."""
    curated = {a.lower() for aliases in CURATED_TEAM_ALIASES.values() for a in aliases}
    assert "friars" not in curated
