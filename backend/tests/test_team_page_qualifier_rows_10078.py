"""#10078 — the team page served Miami's Playoff Qualifiers 83.5% and never showed it.

Production, 2026-10-01 16:48Z, after `28739c3e8b` went live: `/api/teams/15264`
listed "College Football Playoff Qualifiers" 0.835 (tier 4) and "College
Football ACC Championship Game Qualifiers" 0.90 (tier 1); the 390px page listed
neither. The page drops every tier 1/2/4 row once a championship path exists,
and the stored tiers are wrong for these families (#7189). The path refuses
them (`_answers_its_tier`), so they were in neither place.

`_display_tier` serves the tier the row is SHOWN at; the stored tier is not
rewritten (Related Futures and the playoff grid read tier 4 as "make playoffs").
"""

import inspect

import pytest

from app.routes import teams
from app.routes.teams import (
    _AWARD_QUESTION,
    _NOT_A_TITLE_QUESTION,
    _display_tier,
)


@pytest.mark.parametrize(
    "tier, name, shown",
    [
        # The production specimens (Miami 15264, Lions 567), stored tier → shown.
        (4, "College Football Playoff Qualifiers", 5),
        (1, "College Football ACC Championship Game Qualifiers", 5),
        (1, "College Football National Championship Qualifiers", 5),
        (4, "Pro Football Playoff Qualifiers", 5),
        (4, "Pro Football: Team to Make Postseason", 5),
        (2, "Pro Football: NFC Team to advance to Divisional Round", 5),
        (2, "Pro Football Playoffs: NFC #2 Seed", 5),
        (1, "Protector of the Year Winner?", 3),
        (1, "NL Reliever of the Year Winner?", 3),
        # Real path questions keep their tier — the path shows them, the list must not.
        (1, "College Football National Championship Winner", 1),
        (2, "NCAA Football 2026 ACC Conference: Winner", 2),
        (4, "NFC North Division Winner", 4),
        (4, "Pro Football: NFC North Champion", 4),
        # Tiers outside the path are never touched, whatever the name says.
        (5, "College Football Playoff Quarterfinals Qualifiers", 5),
        (3, "Heisman Trophy Winner", 3),
        (None, "Pro Football Playoff Qualifiers", None),
    ],
)
def test_display_tier_on_the_production_specimens(tier, name, shown):
    assert _display_tier(tier, name) == shown


def test_every_award_fragment_is_a_refused_path_question():
    """An award fragment the path does not refuse would never reach `_display_tier`'s
    award arm — its row would stay hidden at tier 1/2/4."""
    assert set(_AWARD_QUESTION) <= set(_NOT_A_TITLE_QUESTION)


def test_the_team_route_stamps_display_tier_on_every_futures_row():
    """The stamp lives in the route body; a route that stops calling it serves no
    `display_tier`, and the page falls back to hiding the qualifier row."""
    source = inspect.getsource(teams)
    assert 'item["display_tier"] = _display_tier(' in source
    assert 'item.get("market_tier"), item.get("market_name")' in source
