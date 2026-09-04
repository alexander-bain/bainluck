"""The NFL team rule: equality after normalization, and the cost of anything looser.

`app/utils/nfl_team_matching` is short because NFL names genuinely agree — the
measurement it documents is 32/32 exact. A short rule is easy to weaken later
"just for this one case", so these tests are built in PAIRS: every shape that
must match is accompanied by a near-miss that must be refused, and a CONTROL arm
executes the looser rule anyone would reach for and shows it leaking.

The near-misses are not invented. `Los Angeles Rams` / `Los Angeles Chargers` and
`New York Giants` / `New York Jets` are the specimen pairs, and production held
two Week-1 rows at one kickoff — `Los Angeles Rams v Arizona Cardinals` and
`Los Angeles Chargers v Arizona Cardinals` — where StatPal has only the Chargers
game (2026-09-04 measurement, #2693).
"""

from __future__ import annotations

import pytest

from app.utils.nfl_team_matching import (
    NFL_TEAM_NAMES,
    is_known_nfl_team,
    normalize_team,
    pair_matches,
    team_matches,
)

#: Renderings that must all read as the same franchise. Case, doubled spaces,
#: a trailing period, and a non-breaking space in a copied string.
RENDERING_NOISE = [
    ("San Francisco 49ers", "San Francisco 49ers"),
    ("san francisco 49ers", "San Francisco 49ers"),
    ("SAN FRANCISCO 49ERS", "San Francisco 49ers"),
    ("San  Francisco   49ers", "San Francisco 49ers"),
    (" San Francisco 49ers ", "San Francisco 49ers"),
    ("San Francisco 49ers", "San Francisco 49ers"),
    ("New York Giants.", "New York Giants"),
]

#: Pairs that share a city, a nickname shape, or a token run, and are DIFFERENT
#: franchises. Every one of these is a real pair in the 2026 league.
NEAR_MISSES = [
    ("Los Angeles Rams", "Los Angeles Chargers"),
    ("Los Angeles Chargers", "Los Angeles Rams"),
    ("New York Giants", "New York Jets"),
    ("New York Jets", "New York Giants"),
    ("Washington Commanders", "Washington"),
    ("Los Angeles Rams", "Los Angeles"),
    ("New England Patriots", "New England"),
    ("Carolina Panthers", "Detroit Lions"),
]


@pytest.mark.parametrize("statpal,ours", RENDERING_NOISE)
def test_rendering_noise_is_absorbed(statpal, ours):
    assert team_matches(statpal, ours) is True


@pytest.mark.parametrize("statpal,ours", NEAR_MISSES)
def test_near_misses_are_refused(statpal, ours):
    assert team_matches(statpal, ours) is False


def test_the_strictness_is_load_bearing_not_decorative():
    """CONTROL: the looser rule anyone would reach for, shown leaking.

    A guard that only exercises the strict arm cannot tell a strict rule from a
    vacuous one. This runs the plausible alternative — match on the last token,
    i.e. the nickname — over the SAME two corpora, and asserts it passes
    everything the real rule passes AND admits near-misses the real rule refuses.

    If this test ever fails because the control stops leaking, the near-miss
    corpus has lost its teeth and needs a harder specimen, not a deletion.
    """

    def city_token_match(a: str, b: str) -> bool:
        """The tempting fallback: same first token (the city)."""
        ta, tb = normalize_team(a).split(), normalize_team(b).split()
        return bool(ta) and bool(tb) and ta[0] == tb[0]

    # It agrees with the real rule on everything that should match...
    for statpal, ours in RENDERING_NOISE:
        assert city_token_match(statpal, ours) is True

    # ...and admits things the real rule refuses. That gap is the whole value of
    # full-name equality.
    leaks = [p for p in NEAR_MISSES if city_token_match(*p)]
    assert len(leaks) >= 5, (
        "the city-token control leaked fewer near-misses than expected; the "
        f"corpus may have gone soft. leaks={leaks}"
    )
    for statpal, ours in leaks:
        assert team_matches(statpal, ours) is False


def test_empty_is_never_a_match():
    """Two broken rows must not pair with each other and call it a link."""
    assert team_matches(None, None) is False
    assert team_matches("", "") is False
    assert team_matches("   ", "Los Angeles Rams") is False
    assert team_matches("Los Angeles Rams", None) is False
    assert normalize_team(None) == ""
    assert normalize_team("  ") == ""


def test_pair_requires_the_same_orientation():
    """Home matches home. The reverse fixture is a real, different game."""
    statpal = ("Seattle Seahawks", "New England Patriots")  # home, away
    assert pair_matches(statpal, ("Seattle Seahawks", "New England Patriots")) is True
    # The same two teams, swapped: their other meeting in the season.
    assert pair_matches(statpal, ("New England Patriots", "Seattle Seahawks")) is False
    # One side right, one side wrong is not a match either.
    assert pair_matches(statpal, ("Seattle Seahawks", "New York Jets")) is False


def test_the_roster_reports_and_does_not_gate():
    """`is_known_nfl_team` labels a miss; `team_matches` never consults it.

    Both halves are asserted, because the value is in the SEPARATION. If the
    match started consulting the roster, a franchise renamed on both sides would
    stop linking — a rename should link fine and go stale loudly, not break.
    """
    assert len(NFL_TEAM_NAMES) == 32
    assert is_known_nfl_team("Las Vegas Raiders") is True
    assert is_known_nfl_team("las  vegas raiders") is True
    assert is_known_nfl_team("Oakland Raiders") is False

    # Two names neither side has ever used — and they still match each other.
    assert is_known_nfl_team("San Diego Chargers") is False
    assert team_matches("San Diego Chargers", "San Diego Chargers") is True
