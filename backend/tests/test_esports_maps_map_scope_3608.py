"""#3608 — an esports totals map is a MATCH map, drawn in MAPS.

THE DEFECT, measured on production 2026-09-06 at `GET /api/events/15305595
/game-markets` and `/15305693/game-markets`. Each served exactly two rungs:

    {'threshold':  2.5, 'over_probability': 0.465, 'outcome_name': 'Under'}
    {'threshold': 21.5, 'over_probability': 0.465, 'outcome_name': 'No'}

2.5 is `Games Total: O/U 2.5` — the match total, in MAPS, on a best-of-three.
21.5 is `Map 1 Total Rounds: Over/Under 21.5` — ONE map's total, in ROUNDS.
Both classify `game_total`, so both landed on one rail, and the card rendered
`Projected 3` on an axis running past 25 with `Over 21.5 -> 47%`. A best-of-3
cannot go past 21.5 maps; the probability is real but it answers another
question, which is the #2441/ux-1034 defect exactly — a number read in the
wrong unit looks sourced.

The negative half matters as much as the positive one: `Total Rounds` is the
CORRECT match total for MMA and boxing, so the rule is registered per-sport and
an undeclared sport keeps every rung it has.
"""

from app.routes.events import (
    _is_match_scope_tennis_total,
    _is_match_scope_total,
    _match_scope_totals,
)


def _rung(threshold: float, market_name: str) -> dict:
    return {
        "threshold": threshold,
        "over_probability": 0.465,
        "market_type": "game_total",
        "market_name": market_name,
        "outcome_name": "Over",
    }


class TestEsportsScopePredicate:
    """The per-map / per-round names an esports page actually carries."""

    def test_per_map_rounds_lines_are_not_match_scope(self):
        # Verbatim from futures_markets on events 15305595 / 15305693.
        for name in (
            "Map 1 Total Rounds: Over/Under 21.5",
            "Map 2 Total Rounds: Over/Under 21.5",
            "Map 3 Total Rounds: Over/Under 21.5",
        ):
            assert _is_match_scope_total(name, "esports") is False, name

    def test_the_match_maps_line_survives(self):
        for name in (
            "Games Total: O/U 2.5",
            "O/U 2.5 Games",
            "Counter-Strike: FOKUS vs Nemiga (BO3) - Stake Ranked Episode 4",
        ):
            assert _is_match_scope_total(name, "esports") is True, name

    def test_map_handicap_is_not_swept_up(self):
        # `\bmap\s*\d+\b` must not fire on "Map Handicap" — it is a spread, and
        # a scope rule that ate it would be deleting a market it never judged.
        assert (
            _is_match_scope_total(
                "Map Handicap: FOKUS (-1.5) vs Nemiga (+1.5)", "esports"
            )
            is True
        )


class TestEsportsRailIsDrawnInMaps:
    """The served shape, end to end through the filter."""

    def test_the_rounds_rung_is_dropped_and_the_maps_rung_kept(self):
        rows = [
            _rung(2.5, "Games Total: O/U 2.5"),
            _rung(21.5, "Map 1 Total Rounds: Over/Under 21.5"),
        ]
        kept = _match_scope_totals(rows, "esports")
        assert [r["threshold"] for r in kept] == [2.5]

    def test_fail_open_when_every_rung_is_map_scoped(self):
        # An event whose ONLY totals are per-map rounds keeps its card rather
        # than losing it — the same protection tennis's arm relies on.
        rows = [
            _rung(21.5, "Map 1 Total Rounds: Over/Under 21.5"),
            _rung(21.5, "Map 2 Total Rounds: Over/Under 21.5"),
        ]
        assert _match_scope_totals(rows, "esports") == rows


class TestNonTargetSportsAreUntouched:
    """The negative half — read the sports the predicate is NOT for."""

    def test_mma_and_boxing_keep_their_total_rounds_line(self):
        # "Total Rounds" IS the match total for a fight. A sport-blind version
        # of this rule would delete the one real rung these pages have.
        rows = [_rung(2.5, "Total Rounds: Over/Under 2.5")]
        for prefix in ("mma", "boxing"):
            assert _match_scope_totals(rows, prefix) == rows, prefix
            assert _is_match_scope_total("Total Rounds: Over/Under 2.5", prefix) is True

    def test_undeclared_sports_and_missing_prefix_keep_every_rung(self):
        rows = [
            _rung(2.5, "Map 1 Total Rounds: Over/Under 21.5"),
            _rung(21.5, "Total Sets O/U 3.5"),
        ]
        for prefix in ("basketball", "baseball", "cricket", None, ""):
            assert _match_scope_totals(rows, prefix) == rows, prefix


class Test3161TennisStillHolds:
    """#3161's case, re-proved through the generalised path."""

    def test_set_and_sets_lines_still_dropped_for_tennis(self):
        rows = [
            _rung(36.5, "Paul vs. Alcaraz: Match O/U 36.5"),
            _rung(9.5, "Paul vs. Alcaraz: Set 1 Games O/U 9.5"),
            _rung(3.5, "Paul vs. Alcaraz: Total Sets O/U 3.5"),
        ]
        kept = _match_scope_totals(rows, "tennis")
        assert [r["threshold"] for r in kept] == [36.5]

    def test_the_tennis_entry_point_still_answers(self):
        assert _is_match_scope_tennis_total("Paul vs. Alcaraz: Set 1 Games O/U 9.5") is False
        assert _is_match_scope_tennis_total("Paul vs. Alcaraz: Match O/U 36.5") is True

    def test_an_esports_name_does_not_leak_into_tennis(self):
        # The registry is per-sport in BOTH directions.
        assert _is_match_scope_total("Map 1 Total Rounds: Over/Under 21.5", "tennis") is True
