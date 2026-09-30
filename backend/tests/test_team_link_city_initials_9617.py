"""#9617 — a shared city's club written with its nickname's initials binds to that club.

WHAT A READER SAW. ``/api/teams/49`` (the Lakers) and ``/api/teams/537`` (the
Clippers) carried no Kalshi NBA title price: read 2026-09-30 01:20Z, both
payloads held Polymarket's and the sportsbooks' champion prices and no KXNBA-27
or KXNBAWEST-27 market. Kalshi names them "Los Angeles L" and "Los Angeles C"
(outcomes 198632425 / 198632436 on KXNBA-27, 198632756 / 198632764 on
KXNBAWEST-27), all four ``team_id IS NULL``. KXMLB-26's "Chicago WS" (outcome
2335) was NULL the same way.

WHY. ``normalize_name`` strips a trailing " C" and keeps " L": "Los Angeles C"
reads as "los angeles" (the Lakers' alias, and the Clippers' city), and
"los angeles l" names nothing. No arm read the capitals.

The team rows are production's shapes (``teams`` read 2026-09-30), including
the #6974 fragment row 12649 "Los Angeles C" beside the real Clippers.
"""

from __future__ import annotations

import pytest

from app.utils import team_linking
from app.utils.team_linking import match_outcome_to_league_team


def _t(team_id, name, alts):
    return {"id": team_id, "name": name, "alternate_names": alts}


BULLS = _t(36, "Chicago Bulls", ["Bulls", "Chicago"])
LA_C_FRAGMENT = _t(12649, "Los Angeles C", ["Clippers", "LA Clippers"])
CLIPPERS = _t(537, "Los Angeles Clippers", ["LA", "Clippers", "LA Clippers"])
LAKERS = _t(49, "Los Angeles Lakers", ["Los Angeles", "Lakers"])
KNICKS = _t(108, "New York Knicks", ["New York", "Knicks", "New York Knicks"])
NBA = [BULLS, LA_C_FRAGMENT, CLIPPERS, LAKERS, KNICKS]

CUBS = _t(10714, "Chicago Cubs", ["Chicago", "Cubs", "cubbies"])
WHITE_SOX = _t(10734, "Chicago White Sox", ["Chicago", "White Sox"])
ANGELS = _t(10712, "Los Angeles Angels", ["Los Angeles", "Angels", "halos"])
DODGERS = _t(10707, "Los Angeles Dodgers", ["Los Angeles", "Dodgers"])
METS = _t(10737, "New York Mets", ["New York", "Mets"])
YANKEES = _t(6610, "New York Yankees", ["New York", "yanks", "Yankees"])
MLB = [CUBS, WHITE_SOX, ANGELS, DODGERS, METS, YANKEES]

BEARS = _t(561, "Chicago Bears", ["Bears"])
CHARGERS = _t(556, "Los Angeles Chargers", ["Chargers"])
RAMS = _t(544, "Los Angeles Rams", ["Rams"])
GIANTS = _t(547, "New York Giants", ["Giants"])
JETS = _t(550, "New York Jets", ["Jets"])
NFL = [BEARS, CHARGERS, RAMS, GIANTS, JETS]


# --- the specimens ----------------------------------------------------------


def test_the_lakers_and_the_clippers_bind_by_their_initial():
    assert match_outcome_to_league_team("Los Angeles L", NBA) == LAKERS["id"]
    assert match_outcome_to_league_team("Los Angeles C", NBA) == CLIPPERS["id"]


def test_a_two_letter_initial_reads_a_two_word_nickname():
    assert match_outcome_to_league_team("Chicago WS", MLB) == WHITE_SOX["id"]
    assert match_outcome_to_league_team("Chicago C", MLB) == CUBS["id"]


def test_the_fragment_row_never_wins_the_clippers_outcome():
    # 12649 "Los Angeles C" is a #6974 fragment. Its own name has a
    # one-capital nickname; the page a reader opens is 537's. Were the
    # fragment a candidate, the NBA specimen above would read two hits.
    arm = team_linking._match_league_team_by_city_initials
    assert arm("Los Angeles C", [LA_C_FRAGMENT]) is None
    assert arm("Los Angeles C", NBA) == CLIPPERS["id"]


# --- control: every letter outcome production ALREADY links agrees ---------


@pytest.mark.parametrize(
    "outcome, league, stored_team_id",
    [
        # team_id as stored on production 2026-09-30, linked by earlier paths.
        ("Los Angeles A", MLB, 10712),
        ("Los Angeles D", MLB, 10707),
        ("New York M", MLB, 10737),
        ("New York Y", MLB, 6610),
        ("Chicago C", MLB, 10714),
        ("Los Angeles C", NFL, 556),
        ("Los Angeles R", NFL, 544),
        ("New York G", NFL, 547),
        ("New York J", NFL, 550),
    ],
)
def test_the_arm_agrees_with_every_letter_link_already_stored(outcome, league, stored_team_id):
    assert match_outcome_to_league_team(outcome, league) == stored_team_id


# --- refusals ----------------------------------------------------------------


def test_an_initial_no_club_in_that_city_carries_binds_nothing():
    assert match_outcome_to_league_team("Los Angeles X", NBA) is None
    assert match_outcome_to_league_team("Boston C", NBA) is None


def test_two_clubs_with_one_initial_in_one_city_bind_neither():
    twins = [_t(1, "Springfield Cats", []), _t(2, "Springfield Comets", [])]
    assert match_outcome_to_league_team("Springfield C", twins) is None


def test_only_capitals_are_initials():
    # A lowercase or three-letter last word, or one with punctuation, is a
    # name, not an initial: "A&M", "USC", "St".
    assert match_outcome_to_league_team("Los Angeles l", NBA) is None
    assert match_outcome_to_league_team("Los Angeles LAK", NBA) is None
    tamu = [_t(3, "Texas A&M Aggies", ["Texas A&M"]), _t(4, "Texas Longhorns", ["Texas"])]
    assert match_outcome_to_league_team("Texas A", tamu) is None
    assert match_outcome_to_league_team("L", NBA) is None


def test_a_bare_city_is_still_refused():
    # The arm only reads a trailing capital; "Los Angeles" still names both.
    assert match_outcome_to_league_team("Los Angeles", NBA) is None


# --- strawman: the arm is what binds them -----------------------------------


def test_without_the_arm_the_specimens_stay_unlinked(monkeypatch):
    monkeypatch.setattr(team_linking, "_match_league_team_by_city_initials", lambda *a: None)
    assert match_outcome_to_league_team("Los Angeles L", NBA) is None
    assert match_outcome_to_league_team("Los Angeles C", NBA) is None
    assert match_outcome_to_league_team("Chicago WS", MLB) is None
