"""Guard tests for cross-league team-name logo collisions (Queue #238).

A bare mascot ("Panthers", "Saints") is an alternate name for teams across
multiple leagues. The team-name → logo lookup must NOT resolve such a bare
name to an arbitrary cross-league team (which produced wrong logos — e.g. a
college Panthers logo on an NFL card — in Alex's native Discover screenshot).
"""

from dataclasses import dataclass, field

from app.routes.events import _dedupe_team_name_lookup


@dataclass
class _FakeTeam:
    id: int
    name: str
    sport_id: int
    alternate_names: list = field(default_factory=list)


def test_bare_mascot_across_leagues_is_dropped():
    """'Panthers' maps to teams in NFL, NHL and NCAAF → ambiguous → no logo."""
    teams = [
        _FakeTeam(1, "Carolina Panthers", sport_id=1, alternate_names=["Panthers"]),
        _FakeTeam(2, "Florida Panthers", sport_id=4, alternate_names=["Panthers"]),
        _FakeTeam(3, "Pittsburgh Panthers", sport_id=760, alternate_names=["Panthers"]),
    ]
    lookup = _dedupe_team_name_lookup(teams)
    # Bare mascot must be absent (colored-box fallback, never a wrong logo).
    assert "Panthers" not in lookup
    # Full, unambiguous names still resolve to the correct team.
    assert lookup["Carolina Panthers"].id == 1
    assert lookup["Florida Panthers"].id == 2
    assert lookup["Pittsburgh Panthers"].id == 3


def test_saints_collision_dropped():
    teams = [
        _FakeTeam(10, "New Orleans Saints", sport_id=1, alternate_names=["Saints"]),
        _FakeTeam(11, "Siena Saints", sport_id=3, alternate_names=["Saints"]),
    ]
    lookup = _dedupe_team_name_lookup(teams)
    assert "Saints" not in lookup
    assert lookup["New Orleans Saints"].id == 10
    assert lookup["Siena Saints"].id == 11


def test_same_league_duplicate_name_kept():
    """A name shared within ONE league is not ambiguous — first wins, kept."""
    teams = [
        _FakeTeam(20, "Rangers", sport_id=4, alternate_names=[]),
    ]
    lookup = _dedupe_team_name_lookup(teams)
    assert lookup["Rangers"].id == 20


def test_unique_mascot_still_resolves():
    """A mascot unique to one league must still resolve to that team's logo."""
    teams = [
        _FakeTeam(30, "Green Bay Packers", sport_id=1, alternate_names=["Packers"]),
        _FakeTeam(31, "Chicago Bears", sport_id=1, alternate_names=["Bears"]),
    ]
    lookup = _dedupe_team_name_lookup(teams)
    assert lookup["Packers"].id == 30
    assert lookup["Bears"].id == 31
