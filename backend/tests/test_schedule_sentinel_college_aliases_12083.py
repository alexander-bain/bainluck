"""#12083, part 2: a college club ESPN spells differently pairs with our row.

The first Schedule Sentinel run on ESPN's full Division I board (Mon Nov 9,
12:04 AM PT) filed 2 REAL for NCAAB. Both were one real game under two
spellings:

* 15344398 "Merrimack Warriors @ Albany Great Danes", 73-60; ESPN lists
  "Merrimack Warriors @ UAlbany Great Danes" at the same time.
* 15343887 "North Dakota St Bison @ CSU Bakersfield Roadrunners", 80-91; ESPN
  lists "North Dakota State Bison @ Cal State Bakersfield Roadrunners".

Each filed our row as a result "for a game the authority says never happened"
and ESPN's game as one we don't hold. Both claims were false.

The fold reads ESPN's spelling as ours: college feeds only, whole tokens only.
Every pair is measured: our team row (read-only SQL) on one side, ESPN's full
board on the other. The last five are the residual spellings from the replay
behind #12381.

Gotcha #44: every instant is a frozen constant and ``now`` is injected.
"""

import importlib
from datetime import datetime, timedelta, timezone

import pytest

ss = importlib.import_module("app.tasks.schedule_sentinel")

NOW = datetime(2026, 11, 9, 8, 4, tzinfo=timezone.utc)  # the first full-board run
TIPOFF = NOW - timedelta(hours=13)

NCAAB = next(s for s in ss.SCHEDULE_LEAGUES if s.slug == "ncaab")

# (our team row, ESPN's displayName)
ALIASES = [
    ("Albany Great Danes", "UAlbany Great Danes"),
    ("CSU Bakersfield Roadrunners", "Cal State Bakersfield Roadrunners"),
    ("CSU Northridge Matadors", "Cal State Northridge Matadors"),
    ("CSU Fullerton Titans", "Cal State Fullerton Titans"),
    ("LIU Sharks", "Long Island University Sharks"),
    ("GW Revolutionaries", "George Washington Revolutionaries"),
    ("IUPUI Jaguars", "IU Indianapolis Jaguars"),
    ("Tenn-Martin Skyhawks", "UT Martin Skyhawks"),
    ("Grand Canyon Antelopes", "Grand Canyon Lopes"),
]


@pytest.mark.parametrize("ours,espn", ALIASES)
def test_espns_spelling_reads_as_our_club(ours, espn):
    assert ss.name_similarity(ours, espn, college=True) == 1.0


@pytest.mark.parametrize("ours,espn", ALIASES)
def test_the_fold_is_college_only(ours, espn):
    """A pro feed keeps today's reading, so no pro club gains an alias."""
    assert ss.name_similarity(ours, espn) < 1.0


@pytest.mark.parametrize(
    "a,b",
    [
        ("Albany Great Danes", "Albany State Golden Rams"),
        ("CSU Bakersfield Roadrunners", "Cal State Fullerton Titans"),
        ("Colorado St Rams", "Cal State Fullerton Titans"),
        ("George Mason Patriots", "George Washington Revolutionaries"),
        ("UT Arlington Mavericks", "UT Martin Skyhawks"),
        ("Long Beach St 49ers", "Long Island University Sharks"),
    ],
)
def test_different_clubs_stay_apart(a, b):
    assert ss.name_similarity(a, b, college=True) < ss.MATCH_BAR


def test_cal_st_abbreviated_reads_as_csu_too():
    """The "St" -> "State" rule runs first, so "Cal St" reaches the same club."""
    assert ss.name_similarity(
        "CSU Bakersfield Roadrunners", "Cal St Bakersfield Roadrunners", college=True
    ) == 1.0


def _truth(home, away, hs, aws, key):
    return ss.TruthGame(
        key=key, home=home, away=away, start=TIPOFF, state="final",
        raw_state="STATUS_FINAL", home_score=hs, away_score=aws,
    )


def _ours(eid, home, away, hs, aws):
    return ss.OurEvent(
        id=eid, home_name=home, away_name=away, home_team_id=1, away_team_id=2,
        home_fk_name=home, away_fk_name=away, status="completed",
        home_score=hs, away_score=aws, commence_time=TIPOFF + timedelta(minutes=3),
        espn_id=None, external_id=f"odds{eid}",
    )


def _real_checks(truth, ours):
    findings, _stats = ss.reconcile(truth, ours, NCAAB, now=NOW)
    classified = ss.classify_findings(findings, NCAAB, now=NOW)
    return sorted(f["check"] for f in classified["real"])


@pytest.mark.parametrize(
    "ours,truth",
    [
        (
            _ours(15344398, "Albany Great Danes", "Merrimack Warriors", 73, 60),
            _truth("UAlbany Great Danes", "Merrimack Warriors", 73, 60, "401800001"),
        ),
        (
            _ours(15343887, "CSU Bakersfield Roadrunners", "North Dakota St Bison", 91, 80),
            _truth("Cal State Bakersfield Roadrunners", "North Dakota State Bison", 91, 80, "401800002"),
        ),
    ],
)
def test_tonights_two_specimens_pair_and_file_nothing(ours, truth):
    assert _real_checks([truth], [ours]) == []


def test_a_real_extra_still_files():
    """The control: a row with no game on the board is still an EXTRA."""
    lone = _ours(15344999, "Albany Great Danes", "Siena Saints", 70, 61)
    other = _truth("Vermont Catamounts", "Maine Black Bears", 80, 66, "401800003")
    assert "schedule_extra" in _real_checks([other], [lone])
