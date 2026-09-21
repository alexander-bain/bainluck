"""The complement of a clinch, across a division cohort (#7695).

Measured on production 2026-09-21 05:30Z, `/api/playoffs/mlb` (payload
`last_updated` 05:26:17Z — post-#7663, post-release v4849). The National League
table said both of these, six rows apart:

    Atlanta Braves         East    won          <- ESPN: Clinched Division
    Philadelphia Phillies  East    1.0% live    <- still priced to win it

Two clubs cannot both win one division.

Philadelphia is the only row in baseball where this shows, and the reason is
worth keeping: every other club in a clinched division already reads
``eliminated`` because the venue graded its division leg, and ESPN marks only
the club that clinched — it publishes nothing about that club's rivals.
Philadelphia carries no ``clincher`` at all, which is correct, because it is
still alive for a wild card. So neither authority speaks, and until this the
grid computed nothing: ``propagate_elimination`` walks the ``depends_on``
ladder, which is VERTICAL within one row, and this is HORIZONTAL across a
cohort.

The specimens below are the real served rows. The AL East is carried alongside
the NL East on purpose: it had no winner on 2026-09-21 (Tampa Bay live at 98%,
the Yankees at 1.7%), so it is the control that proves this writes only into a
decided cohort — and, pooled on the division LABEL instead of
``(conference, division)``, it is the cohort that a careless version eliminates
five clubs from on Atlanta's clinch.
"""

import logging

from app.config.league_configs import LEAGUE_CONFIGS, GridColumn
from app.utils.playoff_grid import (
    DECIDED_STATES,
    propagate_division_complement,
)


def _cell(prob=None, state="live"):
    return {
        "merged_probability": prob,
        "sources": ([{"source": "kalshi", "probability": prob, "market_name": "m"}]
                    if prob is not None else []),
        "trend_24h": 0.004 if prob is not None else None,
        "state": state,
    }


def _team(name, conference, division, division_cell):
    return {
        "name": name,
        "conference": conference,
        "division": division,
        "cells": {"make_playoffs": _cell(0.5), "division": division_cell},
    }


#: MLB's four columns, as `LEAGUE_CONFIGS["mlb"]` declares them.
_MLB_COLUMNS = [
    GridColumn(key="make_playoffs", label="Make Playoffs", order=1),
    GridColumn(key="division", label="Division", order=2),
    GridColumn(key="pennant", label="AL / NL Champ", order=3, depends_on="make_playoffs"),
    GridColumn(key="championship", label="World Series", order=4),
]


def _nl_east_and_al_east():
    """The two East cohorts exactly as production served them at 05:26:17Z."""
    return [
        # --- NL East: Atlanta has clinched; Philadelphia is the defect --------
        _team("Atlanta Braves", "National League", "East", _cell(None, "won")),
        _team("Philadelphia Phillies", "National League", "East", _cell(0.01)),
        _team("New York Mets", "National League", "East", _cell(None, "eliminated")),
        _team("Miami Marlins", "National League", "East", _cell(None, "eliminated")),
        _team("Washington Nationals", "National League", "East",
              _cell(None, "eliminated")),
        # --- AL East: nobody has clinched. Nothing here may move. ------------
        _team("Tampa Bay Rays", "American League", "East", _cell(0.98)),
        _team("New York Yankees", "American League", "East", _cell(0.017)),
        _team("Boston Red Sox", "American League", "East", _cell(None, "eliminated")),
        _team("Toronto Blue Jays", "American League", "East",
              _cell(None, "eliminated")),
        _team("Baltimore Orioles", "American League", "East",
              _cell(None, "eliminated")),
    ]


def _by_name(teams):
    return {t["name"]: t for t in teams}


def _division_cell(teams, name):
    return _by_name(teams)[name]["cells"]["division"]


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------

def test_philadelphia_stops_being_priced_for_a_division_atlanta_has_won():
    teams = _nl_east_and_al_east()

    written = propagate_division_complement(teams, _MLB_COLUMNS)

    assert written == 1, "exactly one live cell sat in a decided cohort"
    phi = _division_cell(teams, "Philadelphia Phillies")
    assert phi["state"] == "eliminated"
    # The price, its sourcing and its trend all go with the claim — a settled
    # cell that keeps a number is how the two halves drift back apart.
    assert phi["merged_probability"] is None
    assert phi["sources"] == []
    assert phi["trend_24h"] is None


def test_the_clinching_club_keeps_its_own_won_cell():
    teams = _nl_east_and_al_east()

    propagate_division_complement(teams, _MLB_COLUMNS)

    assert _division_cell(teams, "Atlanta Braves")["state"] == "won"


def test_no_live_cell_survives_in_a_cohort_that_has_a_winner():
    """The invariant the reader actually cares about, asserted over the grid."""
    teams = _nl_east_and_al_east()

    propagate_division_complement(teams, _MLB_COLUMNS)

    cohorts = {}
    for team in teams:
        key = (team["conference"], team["division"])
        cohorts.setdefault(key, []).append(team)

    for key, cohort in cohorts.items():
        decided = any(
            t["cells"]["division"]["state"] == "won" for t in cohort
        )
        if not decided:
            continue
        live = [
            t["name"] for t in cohort
            if t["cells"]["division"]["state"] not in DECIDED_STATES
        ]
        assert live == [], f"{key} has a winner and still prices {live}"


# ---------------------------------------------------------------------------
# The control: the cohort key is (conference, division), not the label
# ---------------------------------------------------------------------------

def test_the_american_league_east_is_untouched_by_a_national_league_clinch():
    """Pooling on the label alone eliminates five clubs on another's clinch.

    This is the whole reason the key carries the conference. Both cohorts are
    called "East"; only one of them has a winner.
    """
    teams = _nl_east_and_al_east()
    before = {
        name: dict(_division_cell(teams, name))
        for name in ("Tampa Bay Rays", "New York Yankees")
    }

    propagate_division_complement(teams, _MLB_COLUMNS)

    for name, cell in before.items():
        after = _division_cell(teams, name)
        assert after == cell, f"{name} moved on another conference's clinch"
    assert _division_cell(teams, "Tampa Bay Rays")["merged_probability"] == 0.98


def test_a_cohort_with_no_winner_is_left_entirely_alone():
    teams = [t for t in _nl_east_and_al_east()
             if t["conference"] == "American League"]

    assert propagate_division_complement(teams, _MLB_COLUMNS) == 0


# ---------------------------------------------------------------------------
# The refusals
# ---------------------------------------------------------------------------

def test_a_venue_grade_is_never_overwritten():
    """A rival the venue already decided keeps the venue's word, not ours."""
    teams = _nl_east_and_al_east()
    # The venue graded the Mets `lost` rather than `eliminated`; both are
    # readings of a real result and neither is this function's to restate.
    _division_cell(teams, "New York Mets")["state"] = "lost"

    propagate_division_complement(teams, _MLB_COLUMNS)

    assert _division_cell(teams, "New York Mets")["state"] == "lost"


def test_two_winners_in_one_cohort_is_a_contradiction_this_refuses_to_resolve(caplog):
    """Picking one would eliminate a club an authority says has won."""
    teams = _nl_east_and_al_east()
    _division_cell(teams, "Philadelphia Phillies")["state"] = "won"

    with caplog.at_level(logging.WARNING, logger="app.utils.playoff_grid"):
        written = propagate_division_complement(teams, _MLB_COLUMNS)

    assert written == 0
    # The other three NL East clubs keep the states they came in with.
    for name in ("New York Mets", "Miami Marlins", "Washington Nationals"):
        assert _division_cell(teams, name)["state"] == "eliminated"
    assert any("has 2 clubs marked won" in r.getMessage()
               for r in caplog.records), "the contradiction must be findable"


def test_an_absent_cell_is_not_invented():
    """Absent is not eliminated (#6442)."""
    teams = _nl_east_and_al_east()
    del _by_name(teams)["Philadelphia Phillies"]["cells"]["division"]

    assert propagate_division_complement(teams, _MLB_COLUMNS) == 0
    assert "division" not in _by_name(teams)["Philadelphia Phillies"]["cells"]


def test_clubs_missing_only_the_conference_are_not_pooled_by_division_alone():
    """Half the guard, with a specimen that bites.

    `_extract_standings_label` reads conference and division separately and
    either can come back empty, so partial metadata is a real state, not a
    hypothetical. Two clubs that kept "East" but lost their conference are the
    AL/NL collision again in miniature: pooled, one club's clinch eliminates a
    rival from a division it was never in.
    """
    teams = [
        _team("Clinched East", None, "East", _cell(None, "won")),
        _team("Other East", None, "East", _cell(0.31)),
    ]

    assert propagate_division_complement(teams, _MLB_COLUMNS) == 0
    assert _division_cell(teams, "Other East")["merged_probability"] == 0.31


def test_clubs_missing_only_the_division_are_not_pooled_by_conference_alone():
    """The other half. A conference is not a single-winner cohort for this
    column — pooling on it would eliminate every club in the league whose
    division we failed to read, on one unrelated clinch."""
    teams = [
        _team("Clinched Somewhere NL", "National League", None, _cell(None, "won")),
        _team("Unknown Division NL", "National League", None, _cell(0.27)),
    ]

    assert propagate_division_complement(teams, _MLB_COLUMNS) == 0
    assert _division_cell(teams, "Unknown Division NL")["merged_probability"] == 0.27


def test_two_unplaced_clubs_do_not_become_a_cohort_of_their_own():
    """The hazard the falsy guard actually defends against.

    Nulling ONE club's conference is not the test: its key becomes
    `(None, "East")`, which matches nothing, so it is spared by accident and a
    deleted guard still passes. The real specimen is clubs missing BOTH halves —
    `_get_team_metadata` initialises conference and division to None together,
    so they fail as a pair — which pool into one `(None, None)` bucket. One of
    them reading `won` would then eliminate every other unplaced club in the
    grid, across divisions and conferences that have nothing to do with it.
    """
    teams = [
        _team("Clinched Somewhere", None, None, _cell(None, "won")),
        _team("Unplaced Contender", None, None, _cell(0.42)),
    ]

    assert propagate_division_complement(teams, _MLB_COLUMNS) == 0
    assert _division_cell(teams, "Unplaced Contender")["state"] == "live"
    assert _division_cell(teams, "Unplaced Contender")["merged_probability"] == 0.42


def test_a_grid_without_a_division_column_is_not_touched():
    """EPL's columns are relegation / top_4 / championship — no cohort at all."""
    epl_columns = LEAGUE_CONFIGS["epl"].columns
    assert "division" not in {c.key for c in epl_columns}

    teams = _nl_east_and_al_east()

    assert propagate_division_complement(teams, epl_columns) == 0
    assert _division_cell(teams, "Philadelphia Phillies")["merged_probability"] == 0.01


def test_it_is_idempotent():
    teams = _nl_east_and_al_east()

    assert propagate_division_complement(teams, _MLB_COLUMNS) == 1
    assert propagate_division_complement(teams, _MLB_COLUMNS) == 0


# ---------------------------------------------------------------------------
# The premise, over the real configs
# ---------------------------------------------------------------------------

def test_only_conference_structured_leagues_carry_a_division_column():
    """A tripwire on the cohort key, not a restatement of the config.

    The complement is only arithmetic because a division has exactly one winner
    and `(conference, division)` names it uniquely. Today every league with a
    `division` column has conferences, so the key is always well formed. If a
    league without them grows one, this fires and whoever added it has to decide
    what the cohort is — the function itself fails closed and would simply write
    nothing, which is safe but silent.

    Note what is deliberately NOT in this list: `top_4` (four winners) and
    `make_playoffs` (many). A complement belongs only in a single-winner column.
    """
    with_division = {
        slug for slug, cfg in LEAGUE_CONFIGS.items()
        if "division" in {c.key for c in cfg.columns}
    }

    assert with_division == {"mlb", "nfl", "nba", "nhl"}
