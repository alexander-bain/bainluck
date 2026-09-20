"""#7188 — a repoint may never land a leg on a preseason twin or a junk row.

THE CLASS THIS GUARDS. `repair_7188_futures_leg_bound_to_a_city_sibling.py`
moves 32 futures legs off a same-city rival by an EXPLICIT table of team ids —
the only honest way to place a truncated label like `'New York M'`, which no
correct matcher will ever bind. Explicit ids are exactly the thing that rots:
the two ways to get them wrong were both live while the script was written.

    863   New York Mets   sport 33178 (baseball_mlb_preseason)
    10737 New York Mets   sport 53232 (the real one, and a HIGHER id)

A name lookup for "New York Mets" returns 863 FIRST. Every MLB club has this
preseason twin, so "look up the club by name" is a trap with a 50% hit rate.

    12649 'Los Angeles C'  sport 2   <- a junk row whose NAME IS THE FRAGMENT
    556   Los Angeles Chargers sport 1

12649 passes the name-prefix guard perfectly — it is *named* the leg's label —
and fails only on sport. So the two guards are not redundant: each one is the
only thing standing between a real trap and 15 mis-pointed legs.

The team rows below are the production values read on 2026-09-19. A change that
widens either guard has to make one of these fail.
"""
from types import SimpleNamespace

from scripts.repair_7188_futures_leg_bound_to_a_city_sibling import (
    REPOINTS,
    Repoint,
    is_prefix_of,
    plan_violations,
    wrong_app_refusal,
)


def _team(team_id, name, sport_id):
    return SimpleNamespace(id=team_id, name=name, sport_id=sport_id)


#: Production `teams` rows, 2026-09-19, for every id this repair names or is
#: endangered by.
REAL_TEAMS = {
    537: _team(537, "Los Angeles Clippers", 2),
    544: _team(544, "Los Angeles Rams", 1),
    556: _team(556, "Los Angeles Chargers", 1),
    863: _team(863, "New York Mets", 33178),
    6610: _team(6610, "New York Yankees", 53232),
    10707: _team(10707, "Los Angeles Dodgers", 53232),
    10712: _team(10712, "Los Angeles Angels", 53232),
    10737: _team(10737, "New York Mets", 53232),
    12649: _team(12649, "Los Angeles C", 2),
}


# --- the shipped table ------------------------------------------------------

def test_the_shipped_repoint_table_is_clean_against_production_rows():
    """The three families this repair actually moves."""
    assert plan_violations(REPOINTS, REAL_TEAMS) == []


def test_the_shipped_table_covers_the_three_measured_families():
    """32 legs: Mets 9, Dodgers 8, Chargers 15. Guards the ids, not the counts."""
    assert {(rp.wrong, rp.right) for rp in REPOINTS} == {
        (6610, 10737),  # Yankees -> Mets
        (10712, 10707),  # Angels  -> Dodgers
        (544, 556),  # Rams    -> Chargers
    }


# --- trap 1: the preseason twin ---------------------------------------------

def test_the_preseason_mets_twin_is_refused_as_a_target():
    """863 is `New York Mets` too, and a name lookup returns it first."""
    bad = (Repoint(("New York M", "New York Mets"), wrong=6610, right=863, why="x"),)
    problems = plan_violations(bad, REAL_TEAMS)
    assert problems, "863 is sport 33178 (preseason); the repoint must be refused"
    assert any("different" in p and "sport" in p for p in problems)


# --- trap 2: the junk row whose name IS the fragment ------------------------

def test_the_name_guard_alone_would_admit_the_junk_row():
    """Proves guard 3 is load-bearing rather than belt-and-braces.

    12649 is literally named `'Los Angeles C'`, so the prefix test says yes.
    If the sport guard were dropped, nothing else would refuse it.
    """
    assert is_prefix_of("Los Angeles C", REAL_TEAMS[12649].name) is True


def test_the_junk_los_angeles_c_row_is_refused_as_a_target():
    """…and the sport guard is what actually refuses it (NFL 1 vs NBA 2)."""
    bad = (Repoint(("Los Angeles C",), wrong=544, right=12649, why="x"),)
    problems = plan_violations(bad, REAL_TEAMS)
    assert problems
    assert any("sport" in p for p in problems)


# --- guard 2: a correct binding is not a defect -----------------------------

def test_a_leg_that_matches_its_current_club_is_not_moved():
    """`'Los Angeles R'` belongs on the Rams; refusing to move it is the point.

    Without this arm the script would "repair" correctly-bound rows — the
    failure mode of every repoint table that only checks its destination.
    """
    bad = (Repoint(("Los Angeles R",), wrong=544, right=556, why="x"),)
    problems = plan_violations(bad, REAL_TEAMS)
    assert problems
    assert any("not obviously wrong" in p for p in problems)


def test_a_target_the_leg_does_not_name_is_refused():
    """Mistyped destination: `'New York M'` names no Dodger."""
    bad = (Repoint(("New York M",), wrong=6610, right=10707, why="x"),)
    problems = plan_violations(bad, REAL_TEAMS)
    assert problems
    assert any("not a prefix" in p for p in problems)


def test_a_missing_team_is_refused_not_skipped():
    bad = (Repoint(("New York M",), wrong=6610, right=99999999, why="x"),)
    problems = plan_violations(bad, REAL_TEAMS)
    assert problems == ["team 99999999 does not exist"]


# --- the prefix rule itself -------------------------------------------------

def test_prefix_admits_the_venues_mid_word_truncation():
    assert is_prefix_of("New York M", "New York Mets")
    assert is_prefix_of("Los Angeles D", "Los Angeles Dodgers")
    assert is_prefix_of("Los Angeles C", "Los Angeles Chargers")
    assert is_prefix_of("New York Mets", "New York Mets")


def test_prefix_is_a_prefix_and_not_a_substring():
    """"Angeles D" is inside "Los Angeles Dodgers" and names no club."""
    assert not is_prefix_of("Angeles D", "Los Angeles Dodgers")
    assert not is_prefix_of("New York M", "New York Yankees")
    assert not is_prefix_of("Los Angeles C", "Los Angeles Rams")


def test_prefix_is_case_insensitive_but_refuses_empties():
    assert is_prefix_of("new york m", "New York Mets")
    assert not is_prefix_of("", "New York Mets")
    assert not is_prefix_of("New York M", "")


# --- the app gate -----------------------------------------------------------

def test_plan_only_needs_no_app(monkeypatch):
    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    assert wrong_app_refusal(SimpleNamespace(apply=False, backup=False)) is None


def test_a_write_off_the_dyno_is_refused(monkeypatch):
    """Unset means a laptop pointed at production — the case the gate exists for."""
    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    refusal = wrong_app_refusal(SimpleNamespace(apply=True, backup=True))
    assert refusal and "HEROKU_APP_NAME is unset" in refusal


def test_a_write_on_the_wrong_app_is_refused(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    refusal = wrong_app_refusal(SimpleNamespace(apply=True, backup=True))
    assert refusal and "bainluck-heavy" in refusal


def test_a_write_on_the_producer_app_is_allowed(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert wrong_app_refusal(SimpleNamespace(apply=True, backup=True)) is None


def test_the_backup_alone_earns_the_gate(monkeypatch):
    """--backup writes DDL, so it is a write and the undo's parser has no --apply."""
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert wrong_app_refusal(SimpleNamespace(backup=True)) is not None
