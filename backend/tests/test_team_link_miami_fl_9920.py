"""#9920 — The Miami Hurricanes' team page gets Kalshi's college title odds: "Miami (FL)" binds.

WHAT A READER SAW. Production, 2026-09-30: every open Kalshi leg named "Miami
(FL)" had no team — the national title (KXNCAAF-27), playoff (KXNCAAFPLAYOFF-26)
and ACC (KXNCAAFACC-26) boards, the AP-rank, seed and CFP-poll ladders. The same
boards' "Miami (OH)" legs were all bound to the RedHawks (15332).

WHY. Kalshi keeps the state qualifier on both schools; our rows keep it only on
the RedHawks ("Miami (OH) RedHawks"). Dropping the nickname from "Miami
Hurricanes" leaves "Miami", never "Miami (FL)", so every arm of
``match_outcome_to_league_team`` answered nothing. #8980 bridged the same pair
for GAME matching (``_STATE_QUALIFIED_SCHOOL_NAMES``); the team linker never
received it.

The rows are production's own (id, name, ``alternate_names``), read from
``teams`` on 2026-09-30.
"""

from __future__ import annotations

from app.utils.team_linking import match_outcome_to_league_team


def _t(team_id, name, alts, sport_key="americanfootball_ncaaf"):
    return {"id": team_id, "name": name, "alternate_names": alts, "sport_key": sport_key}


HURRICANES = _t(15264, "Miami Hurricanes", ["Miami", "Hurricanes"])
REDHAWKS = _t(15332, "Miami (OH) RedHawks", ["RedHawks", "Miami OH"])
FIU = _t(15339, "Florida International Panthers", ["FIU", "Panthers"])
FLORIDA = _t(15333, "Florida Gators", ["Florida", "Gators"])
CLEMSON = _t(10, "Clemson Tigers", ["Clemson", "Tigers"])

NCAAF = [HURRICANES, REDHAWKS, FIU, FLORIDA, CLEMSON]


def test_miami_fl_binds_to_the_hurricanes():
    assert match_outcome_to_league_team("Miami (FL)", NCAAF) == 15264


def test_miami_oh_still_binds_to_the_redhawks():
    assert match_outcome_to_league_team("Miami (OH)", NCAAF) == 15332


def test_miami_fl_never_reaches_the_redhawks():
    """Without the Hurricanes' row in the league, "Miami (FL)" names no one."""
    assert match_outcome_to_league_team("Miami (FL)", [REDHAWKS, FIU, FLORIDA]) is None


def test_bare_miami_stays_unbound():
    """A bare "Miami" is a shortening of "Miami (OH) RedHawks" too; unchanged."""
    assert match_outcome_to_league_team("Miami", NCAAF) is None


def test_basketball_board_binds_the_same_school():
    ncaab = [
        _t(267, "Miami Hurricanes", ["Miami", "Hurricanes"], "basketball_ncaab"),
        _t(174, "Miami (OH) RedHawks", ["RedHawks", "Miami OH"], "basketball_ncaab"),
    ]
    assert match_outcome_to_league_team("Miami (FL)", ncaab) == 267


def test_a_row_named_miami_fl_is_still_taken_by_the_exact_arm():
    """baseball_ncaa carries a row literally named "Miami (FL)" (14631) beside
    "Miami Hurricanes" (2862). The exact arm answers before the spelling table
    is read, so that league's binding does not move."""
    baseball = [
        _t(14631, "Miami (FL)", ["Miami Hurricanes", "Miami", "Hurricanes"], "baseball_ncaa"),
        _t(2862, "Miami Hurricanes", ["Miami", "Hurricanes"], "baseball_ncaa"),
        _t(10701, "Miami (OH) RedHawks", ["RedHawks", "Miami OH"], "baseball_ncaa"),
        _t(14629, "Miami (OH)", [], "baseball_ncaa"),
    ]
    assert match_outcome_to_league_team("Miami (FL)", baseball) == 14631
