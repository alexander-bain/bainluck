"""#2311 — the 40-name roster cap keeps the players markets are written about.

`teams.roster_players` arrives alphabetical by first name, and the prop-family
route searches at most `_MAX_ROSTER_PATTERNS` (40) names. Only football rosters
exceed that, so on production 2026-09-24 the Chiefs (65 names) searched "Alohi
Gilman" through "Matt Araiza" and never searched Patrick Mahomes, Travis Kelce,
Rashee Rice or Xavier Worthy — while Kelce alone had 13 open markets naming him
("Travis Kelce 2026-27 Regular Season Receiving Yards", ...), none of which
reached the Chiefs page.

The cap and its cost are unchanged (LAT-P138: each pattern is ~325 ms on
futures_outcomes). What changes is WHICH 40: a football roster over the cap is
filled QB/RB/WR/TE first, then kickers, then defense, with linemen, long
snappers and punters last. Any other roster keeps its stored order.
"""

from types import SimpleNamespace

from app.routes import prop_families as route
from tests.test_prop_families_cache_lat_p138 import _build

_STARS = {"Patrick Mahomes", "Travis Kelce", "Rashee Rice", "Xavier Worthy"}


def _chiefs_shaped_roster() -> list[dict]:
    """65 names in the production shape: alphabetical, positions attached, and
    the four stars all past the 40th name."""
    early = (
        [{"name": f"Aaron Lineman{i:02d}", "position": "OT"} for i in range(17)]
        + [{"name": f"Bobby Guard{i:02d}", "position": "G"} for i in range(6)]
        + [{"name": f"Carl Corner{i:02d}", "position": "CB"} for i in range(8)]
        + [{"name": f"Dan Backer{i:02d}", "position": "LB"} for i in range(8)]
        + [{"name": "Eli Snapper", "position": "LS"}, {"name": "Matt Araiza", "position": "P"}]
        + [{"name": f"Moe Safety{i:02d}", "position": "S"} for i in range(4)]
    )
    late = [
        {"name": "Patrick Mahomes", "position": "QB"},
        {"name": "Rashee Rice", "position": "WR"},
        {"name": "Travis Kelce", "position": "TE"},
        {"name": "Xavier Worthy", "position": "WR"},
    ] + [{"name": f"Zed Tackle{i:02d}", "position": "DT"} for i in range(16)]
    roster = early + late
    assert len(roster) == 65
    return roster


def _team(roster: list, tid: int = 560) -> SimpleNamespace:
    return SimpleNamespace(
        id=tid, name="Kansas City Chiefs", slug="kansas-city-chiefs", roster_players=roster
    )


class TestWhichFortyTheCapKeeps:
    def test_the_chiefs_stars_are_searched(self):
        names, total = route._roster_name_coverage(_team(_chiefs_shaped_roster()))
        assert total == 65
        assert len(names) == route._MAX_ROSTER_PATTERNS == 40
        assert _STARS <= set(names), sorted(_STARS - set(names))

    def test_the_before_state_dropped_them(self):
        """Control: the first 40 in stored order — what the route searched
        before #2311 — contains none of the four."""
        first_40 = {p["name"] for p in _chiefs_shaped_roster()[:40]}
        assert not (_STARS & first_40)

    def test_never_propped_positions_are_what_the_cap_drops(self):
        names, _ = route._roster_name_coverage(_team(_chiefs_shaped_roster()))
        dropped = {p["name"] for p in _chiefs_shaped_roster()} - set(names)
        positions = {p["name"]: p["position"] for p in _chiefs_shaped_roster()}
        assert {positions[n] for n in dropped} <= {"OT", "G", "LS", "P"}, dropped

    def test_ties_keep_roster_order(self):
        names, _ = route._roster_name_coverage(_team(_chiefs_shaped_roster()))
        assert names[:4] == ["Patrick Mahomes", "Rashee Rice", "Travis Kelce", "Xavier Worthy"]

    def test_a_non_football_roster_over_the_cap_keeps_stored_order(self):
        """"C" and "P" are catchers and pitchers in MLB. Without a football-only
        code on the roster, nothing is reordered."""
        roster = [
            {"name": f"Player Number{i:02d}", "position": ("C" if i >= 40 else "P")}
            for i in range(45)
        ]
        names, total = route._roster_name_coverage(_team(roster))
        assert total == 45
        assert names == [p["name"] for p in roster[:40]]

    def test_a_football_roster_under_the_cap_is_unchanged(self):
        roster = [
            {"name": "Aaron Tackle", "position": "OT"},
            {"name": "Patrick Mahomes", "position": "QB"},
        ]
        names, total = route._roster_name_coverage(_team(roster))
        assert (names, total) == (["Aaron Tackle", "Patrick Mahomes"], 2)

    def test_string_rosters_and_short_names_behave_as_before(self):
        roster = ["Abe", "Travis Kelce", {"name": "Patrick Mahomes"}, 7]
        assert route._roster_player_names(_team(roster)) == [
            "Travis Kelce",
            "Patrick Mahomes",
        ]


class TestPayloadDeclaresTheSearch:
    async def test_a_capped_roster_declares_truncation(self):
        (payload, _degraded), _db = await _build(_team(_chiefs_shaped_roster()))
        assert payload["roster_search"] == {"searched": 40, "total": 65, "truncated": True}

    async def test_a_roster_under_the_cap_declares_it_whole(self):
        (payload, _degraded), _db = await _build(
            _team([{"name": "Patrick Mahomes", "position": "QB"}])
        )
        assert payload["roster_search"] == {"searched": 1, "total": 1, "truncated": False}

    async def test_a_rosterless_team_payload_is_unchanged(self):
        (payload, _degraded), _db = await _build(_team([]))
        assert "roster_search" not in payload
        assert set(payload) == {"team", "families", "total_families"}

    async def test_the_route_searches_the_stars(self):
        """End to end through the builder: the roster branches bind the stars'
        patterns, not the first 40 alphabetically."""
        from sqlalchemy.dialects import postgresql

        from tests.test_prop_families_cache_lat_p138 import _branch_stmts

        (_payload, _degraded), db = await _build(_team(_chiefs_shaped_roster()))
        bound: list[str] = []
        for stmt in _branch_stmts(db):
            for v in stmt.compile(dialect=postgresql.dialect()).params.values():
                if isinstance(v, list):
                    bound.extend(str(x) for x in v)
        for star in _STARS:
            assert f"%{star}%" in bound, star
        assert "%Matt Araiza%" not in bound
