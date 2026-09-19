"""#6430 — a club reaches its own championship market by typing its name.

THE DEFECT, measured on production 2026-09-19 via `GET /api/events/search`:

    q=dodgers   -> row 1 is "MLB World Series Champion 2026"   (0.3050)
    q=yankees   -> row 1 is "MLB World Series Champion 2026"   (0.1050)
    q=red sox   -> ten tier-5 "… Inning Winner" rows, no championship market

The single failing clause is `MIN_CONTENDER_PROBABILITY`: the Red Sox sit at
0.0455 in market 114584 (tier 1 ✓, volume 40,784,846 ✓, status open ✓). The
market has 31 outcomes with a mean of 3.49% and only SEVEN clear the 0.05 floor,
so 24 of 31 MLB clubs cannot reach their own championship question — including
clubs above the field mean (the Red Sox are 9th of 31, 1.3x the average).

WHY THE REPAIR IS AN IDENTITY ANCHOR AND NOT A FIELD-RELATIVE FLOOR. Replaying
`min(0.05, 1/field)` over the live tier-1 volume>=10k corpus admits
`Presidential Election Winner 2028` (128 outcomes) and `Pro Football
Championship Game Matchup` (256 outcomes, top price 0.035) — clause 3's own
LeBron case at scale. Both carry ZERO `team_id`; market 114584 carries 30 of 31.
`TestTheControl` is that measurement, frozen.
"""

import ast
import pathlib

import pytest

from app.utils.search_headline_contender import (
    MIN_ANCHORED_CONTENDER_PROBABILITY,
    MIN_CONTENDER_PROBABILITY,
    MIN_CONTENDER_VOLUME,
    is_contender_outcome,
)

# The live rows, read from production 2026-09-19 (market 114584, "MLB World
# Series Champion 2026", tier 1, volume 40,784,846). `anchored` is
# `futures_outcomes.team_id IS NOT NULL`.
WORLD_SERIES_FIELD = [
    # (club, probability, anchored)
    ("Los Angeles Dodgers", 0.3050, True),
    ("Milwaukee Brewers", 0.1525, True),
    ("New York Yankees", 0.1050, True),
    ("Tampa Bay Rays", 0.0935, True),
    ("San Diego Padres", 0.0575, True),
    ("Atlanta Braves", 0.0565, True),
    ("Chicago Cubs", 0.0555, True),
    ("Philadelphia Phillies", 0.0495, True),
    ("Boston Red Sox", 0.0455, True),
    ("Cleveland Guardians", 0.0315, True),
    ("Houston Astros", 0.0285, True),
    ("Chicago White Sox", 0.0225, True),
]
WORLD_SERIES_VOLUME = 40_784_846


class TestTheDefect:
    """RED on clean master: these are the clubs the 0.05 floor deletes."""

    def test_red_sox_reach_the_world_series_market(self):
        """#6430's reported specimen, at its measured live price."""
        assert is_contender_outcome(0.0455, WORLD_SERIES_VOLUME, team_anchored=True), (
            "the Boston Red Sox are refused a reserved slot in their own "
            "championship market at 4.55% — this is the reported defect"
        )

    def test_the_whole_club_field_reaches_it_not_just_the_favourites(self):
        """The ship is 31 clubs, not one. Seven cleared the floor before."""
        admitted = [
            club
            for club, probability, anchored in WORLD_SERIES_FIELD
            if is_contender_outcome(
                probability, WORLD_SERIES_VOLUME, team_anchored=anchored
            )
        ]
        assert len(admitted) == len(WORLD_SERIES_FIELD), (
            f"only {len(admitted)} of {len(WORLD_SERIES_FIELD)} measured clubs "
            f"reach their own championship market: {admitted}"
        )

    def test_the_favourites_still_reach_it(self):
        """The arm is additive — it must not cost Dodgers/Yankees their row."""
        for club, probability in (("Los Angeles Dodgers", 0.3050), ("New York Yankees", 0.1050)):
            assert is_contender_outcome(probability, WORLD_SERIES_VOLUME), (
                f"{club} lost the slot it already had on a NAME-only verdict"
            )


class TestTheControl:
    """The rows a price-relative floor would have admitted, and must not."""

    @pytest.mark.parametrize(
        "market,probability",
        [
            # 112897 Presidential Election Winner 2028 — 128 outcomes, 0 team_id
            ("Presidential Election Winner 2028", 0.0100),
            # 56775566 Pro Football Championship Game Matchup — 256, 0 team_id
            ("Pro Football Championship Game Matchup", 0.0350),
        ],
    )
    def test_an_unanchored_longshot_is_still_refused(self, market, probability):
        """No `team_id` ⇒ the 0.05 floor is untouched. Clause 3 still governs."""
        assert not is_contender_outcome(probability, 10_000_000), (
            f"{market} earned a reserved slot at {probability} on a bare name "
            "match — this is the LeBron case clause 3 exists to prevent"
        )

    def test_the_anchor_does_not_relax_the_volume_floor(self):
        """Identity answers 'about you', never 'does anyone trade it'."""
        assert not is_contender_outcome(
            0.9, MIN_CONTENDER_VOLUME - 1, team_anchored=True
        )

    def test_dust_below_the_venue_tick_is_still_refused(self):
        """Four live anchored rows sit at 0.0005, under the 1c minimum tick."""
        assert not is_contender_outcome(0.0005, WORLD_SERIES_VOLUME, team_anchored=True)

    def test_the_default_is_the_previous_behaviour_byte_for_byte(self):
        """Every existing caller and replay-corpus row keeps its old verdict."""
        below = MIN_CONTENDER_PROBABILITY - 0.001
        assert not is_contender_outcome(below, MIN_CONTENDER_VOLUME)
        assert is_contender_outcome(MIN_CONTENDER_PROBABILITY, MIN_CONTENDER_VOLUME)

    def test_the_anchored_floor_is_strictly_looser_never_tighter(self):
        """The arm can only ever ADD a market, which bounds the blast radius."""
        assert MIN_ANCHORED_CONTENDER_PROBABILITY < MIN_CONTENDER_PROBABILITY


class TestTheTwoLanesCannotDrift:
    """#3394's lesson: `/search` and `/typeahead` are textual copies.

    That fix landed on the dropdown, the identical arm in the results endpoint
    was left alone, and the same query broke the same way the day after it was
    declared fixed. Both lanes now share ONE helper; this asserts they still do.
    """

    def test_both_headline_lanes_call_the_shared_clause_helper(self):
        source = (
            pathlib.Path(__file__).resolve().parents[1] / "app" / "routes" / "events.py"
        ).read_text()
        tree = ast.parse(source)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_headline_contender_outcome_clause"
        ]
        assert len(calls) == 2, (
            f"expected the search and typeahead headline lanes to share the "
            f"clause helper, found {len(calls)} call site(s) — if a lane was "
            "given its own inline predicate the two will drift, which is #3394"
        )

    def test_the_sql_clause_carries_both_floors(self):
        """Guards the SQL half against silently losing the anchored arm."""
        from app.routes.events import _headline_contender_outcome_clause

        compiled = str(
            _headline_contender_outcome_clause(r"\mred\s+sox\M").compile(
                compile_kwargs={"literal_binds": True}
            )
        )
        assert "team_id IS NOT NULL" in compiled
        assert str(MIN_CONTENDER_PROBABILITY) in compiled
        assert str(MIN_ANCHORED_CONTENDER_PROBABILITY) in compiled
