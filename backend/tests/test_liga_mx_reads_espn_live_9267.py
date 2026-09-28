"""#9267 — a live Liga MX game gets its minute, its half and its full time from ESPN.

Production 2026-09-28 02:22Z: event 15316429, León v FC Juárez
(`soccer_mexico_ligamx`), served `live` 0–0 with `period` and `game_clock`
NULL — the /sports card and the event page read a bare LIVE, no minute, no
half-time marker — while ESPN's `soccer/mex.1` board read 401876957
STATUS_SECOND_HALF 57'. The key was on no ESPN map, so no pass ever read a Liga
MX board; the row's only score source was the Odds API scores poll. Same class
as #8675 (Nations League) and #8810 (League Two).

Turning the board on is safe only if the live matcher pairs our rows with
ESPN's clubs and with nothing else. The rosters below are the real ones: every
spelling our Liga MX rows carried in the 60 days to 2026-09-28 (28 names across
Odds API, Kalshi and Polymarket rows) and ESPN's 18 `mex.1/teams` entries, both
read 2026-09-28. Unlike #8675 no alias is needed: every spelling already pairs
with exactly its own club.
"""

from datetime import datetime, timezone
from itertools import product
from types import SimpleNamespace

import pytest

from app.utils.name_normalization import names_match
from app.utils.sport_keys import (
    ESPN_SPORT_MAPPING,
    EXPECTED_GAME_STATE_INDICATORS,
    SPORT_LEAGUE_MAP,
)

LMX = "soccer_mexico_ligamx"

#: ESPN `mex.1/teams`: (displayName, shortDisplayName, name, location).
ESPN_CLUBS = [
    ("América", "América", "América", "América"),
    ("Atlante", "Atlante", "Atlante", "Atlante"),
    ("Atlas", "Atlas", "Atlas", "Atlas"),
    ("Atlético de San Luis", "Atl. San Luis", "Atlético de San Luis", "Atlético de San Luis"),
    ("Cruz Azul", "Cruz Azul", "Cruz Azul", "Cruz Azul"),
    ("FC Juarez", "Juarez", "FC Juarez", "FC Juarez"),
    ("Guadalajara", "Guadalajara", "Guadalajara", "Guadalajara"),
    ("León", "León", "León", "León"),
    ("Monterrey", "Monterrey", "Monterrey", "Monterrey"),
    ("Necaxa", "Necaxa", "Necaxa", "Necaxa"),
    ("Pachuca", "Pachuca", "Pachuca", "Pachuca"),
    ("Puebla", "Puebla", "Puebla", "Puebla"),
    ("Pumas UNAM", "UNAM", "Pumas UNAM", "Pumas UNAM"),
    ("Querétaro", "Queretaro", "Querétaro", "Querétaro"),
    ("Santos", "Santos", "Santos", "Santos"),
    ("Tigres UANL", "Tigres", "Tigres UANL", "Tigres UANL"),
    ("Tijuana", "Tijuana", "Tijuana", "Tijuana"),
    ("Toluca", "Toluca", "Toluca", "Toluca"),
]

#: Our row's spelling → the ESPN displayName of the same club.
OURS = {
    "América": "América",
    "Atlante": "Atlante", "Atlante FC": "Atlante",
    "Atlas": "Atlas", "Atlas FC": "Atlas",
    "Atletico San Luis": "Atlético de San Luis",
    "Atlético San Luis": "Atlético de San Luis",
    "San Luis": "Atlético de San Luis",
    "Cruz Azul": "Cruz Azul",
    "Deportivo Toluca FC": "Toluca", "Toluca": "Toluca",
    "FC Juárez": "FC Juarez", "Juarez": "FC Juarez",
    "Guadalajara": "Guadalajara",
    "Leon": "León", "León": "León",
    "Monterrey": "Monterrey",
    "Necaxa": "Necaxa",
    "Pachuca": "Pachuca",
    "Puebla": "Puebla",
    "Pumas": "Pumas UNAM", "Pumas UNAM": "Pumas UNAM",
    "Queretaro": "Querétaro", "Querétaro": "Querétaro",
    "Santos Laguna": "Santos",
    "Tigres": "Tigres UANL", "Tigres de la UANL": "Tigres UANL",
    "Tijuana": "Tijuana",
}


def _espn_team(club):
    display, short, name, location = club
    return SimpleNamespace(
        display_name=display, short_name=short, name=name, location=location,
    )


def test_the_league_is_on_every_espn_map_the_live_pass_reads():
    assert SPORT_LEAGUE_MAP[LMX] == ("soccer", "mex.1")
    assert ESPN_SPORT_MAPPING[LMX] == "soccer/mex.1"
    assert EXPECTED_GAME_STATE_INDICATORS[LMX] == 2
    # `sync_espn_live_events` gates on the copy re-exported through config.
    from app.tasks.config import ESPN_SPORT_MAPPING as TASK_MAP
    assert LMX in TASK_MAP


def test_the_rosters_are_whole():
    assert len(ESPN_CLUBS) == 18
    assert len(OURS) == 28
    assert set(OURS.values()) == {c[0] for c in ESPN_CLUBS}


@pytest.mark.parametrize("ours", sorted(OURS))
def test_every_spelling_pairs_with_its_own_club_and_no_rival(ours):
    """Both live-pass matchers and the registry's `names_match`, both orders,
    over every club on ESPN's board: exactly one hit, and it is the right one."""
    from app.tasks.espn_sync import espn_names_match, espn_team_matches

    live = {c[0] for c in ESPN_CLUBS if espn_names_match([ours], _espn_team(c))}
    backfill = {c[0] for c in ESPN_CLUBS if espn_team_matches([ours], _espn_team(c))}
    registry = {
        c[0] for c in ESPN_CLUBS if names_match(ours, c[0]) or names_match(c[0], ours)
    }
    assert live == backfill == registry == {OURS[ours]}


def test_no_two_espn_clubs_match_each_other():
    names = [c[0] for c in ESPN_CLUBS]
    assert [(a, b) for a, b in product(names, names) if a < b and names_match(a, b)] == []


def _board():
    def game(espn_id, home, away, when):
        return SimpleNamespace(
            espn_id=espn_id,
            home_team=_espn_team(next(c for c in ESPN_CLUBS if c[0] == home)),
            away_team=_espn_team(next(c for c in ESPN_CLUBS if c[0] == away)),
            date=when,
        )
    return [
        game("401876958", "Pumas UNAM", "Atlético de San Luis",
             datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)),
        game("401876957", "León", "FC Juarez", datetime(2026, 9, 28, 1, 0, tzinfo=timezone.utc)),
        game("401876956", "Necaxa", "América", datetime(2026, 9, 28, 3, 10, tzinfo=timezone.utc)),
    ]


def _select(home, away, commence, exclude=()):
    from app.tasks.espn_sync import espn_names_match
    from app.utils.espn_candidate_selection import select_authorized_espn_candidate

    return select_authorized_espn_candidate(
        _board(), commence,
        is_name_match=lambda ee: (
            espn_names_match([home], ee.home_team) and espn_names_match([away], ee.away_team)
        ),
        exclude_ids=exclude,
    )


def test_the_specimen_pairs_with_tonights_espn_game():
    """15316429 León v FC Juárez, listed 01:05Z, ESPN kickoff 01:00Z."""
    matched, reason = _select("León", "FC Juárez", datetime(2026, 9, 28, 1, 5, tzinfo=timezone.utc))
    assert reason == "ok"
    assert matched.espn_id == "401876957"


def test_a_same_teams_row_is_refused_once_the_game_is_claimed():
    """Control: 15314917 is a Kalshi row for the same game listed 04:00Z. It is
    inside the name-only window, so what keeps it off the real row's ESPN game
    is the pass's claimed-id set — the same guard every mapped league relies on."""
    commence = datetime(2026, 9, 28, 4, 0, tzinfo=timezone.utc)
    assert _select("Leon", "Juarez", commence)[0].espn_id == "401876957"
    assert _select("Leon", "Juarez", commence, exclude={"401876957"}) == (None, "no-name-match")
