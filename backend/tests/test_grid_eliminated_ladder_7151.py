"""The playoff grid's ladder, in both directions (#7151).

Measured on production 2026-09-20 22:0xZ, `/api/playoffs/mlb`:

  * **The false alarm.** The Grid Sentinel read its ladder off ADJACENT
    columns, so every MLB wild-card contender tripped "AL / NL Champ >
    Division" — the Yankees at 22.2% pennant / 2.8% division. A wild card wins
    the pennant without winning its division; #7076 fixed that reading on the
    serving side with `GridColumn.depends_on` and the sentinel never learned
    it, filing six *critical* REDs a day against a correct grid.

  * **The real defect the false alarm was hiding.** The Pirates (79-77),
    Cardinals (76-80) and Marlins (76-80) rendered ✗ for Make Playoffs and ✗
    for Division — venue-settled, and all three mathematically out with six
    games to play — beside a live 0.5% for the pennant and 0.1% for the World
    Series. `enforce_monotonicity` could not see it: a settled cell carries no
    probability, so the numeric bound skips the pair.

Both halves are the same rule — you cannot win the pennant without making the
playoffs — applied to the number and to the state.
"""

import importlib

from app.config.league_configs import LEAGUE_CONFIGS, GridColumn
from app.utils.playoff_grid import monotonic_pairs, propagate_elimination

gs = importlib.import_module("app.tasks.grid_sentinel")


def _cell(prob=None, state="live", sources=None):
    return {"merged_probability": prob, "sources": sources if sources is not None
            else ([{"source": "kalshi", "probability": prob, "market_name": "m"}]
                  if prob is not None else []),
            "trend_24h": None, "state": state}


#: The MLB grid as production served it, trimmed to the three rows that matter.
def _mlb_grid():
    return {
        "columns": [
            {"key": "make_playoffs", "label": "Make Playoffs"},
            {"key": "division", "label": "Division"},
            {"key": "pennant", "label": "AL / NL Champ"},
            {"key": "championship", "label": "World Series"},
        ],
        "teams": [
            {   # the wild card: pennant far above division, and correct
                "name": "New York Yankees",
                "cells": {"make_playoffs": _cell(None, "won"),
                          "division": _cell(0.0275),
                          "pennant": _cell(0.2225),
                          "championship": _cell(0.0957)},
            },
            {   # eliminated, still priced to win the pennant
                "name": "Pittsburgh Pirates",
                "cells": {"make_playoffs": _cell(None, "eliminated"),
                          "division": _cell(None, "eliminated"),
                          "pennant": _cell(0.0055),
                          "championship": _cell(0.001)},
            },
            {   # a clean contender: nothing to say about it
                "name": "Cleveland Guardians",
                "cells": {"make_playoffs": _cell(0.9475),
                          "division": _cell(0.5875),
                          "pennant": _cell(0.1343),
                          "championship": _cell(0.0445)},
            },
        ],
        "sources_available": ["kalshi", "polymarket", "odds_api"],
    }


class TestSentinelReadsTheDeclaredLadder:
    """#7151: the six critical REDs were the wild-card path, not a defect."""

    def test_pennant_above_division_is_not_a_finding(self):
        findings = gs.check_monotonicity(_mlb_grid(), "mlb")
        assert findings == [], (
            "A wild card wins the pennant without winning its division: "
            f"{[f['detail'] for f in findings]}"
        )

    def test_pennant_above_its_own_prerequisite_is_still_critical(self):
        """The check must still bite — `make_playoffs` DOES bound the pennant."""
        grid = _mlb_grid()
        grid["teams"][2]["cells"]["pennant"] = _cell(0.99)  # > make_playoffs 0.9475
        findings = gs.check_monotonicity(grid, "mlb")
        assert len(findings) == 1
        assert findings[0]["severity"] == "critical"
        assert findings[0]["seasonal_ok"] is False
        assert "Make Playoffs" in findings[0]["detail"]

    def test_championship_above_pennant_is_still_critical(self):
        grid = _mlb_grid()
        grid["teams"][2]["cells"]["championship"] = _cell(0.50)  # > pennant 0.1343
        findings = gs.check_monotonicity(grid, "mlb")
        assert len(findings) == 1 and findings[0]["severity"] == "critical"

    def test_pairs_come_from_the_config_not_from_adjacency(self):
        """The sentinel and the page must read ONE ladder. If they diverge, the
        page's cap and the sentinel's alarm disagree about what is impossible."""
        grid = _mlb_grid()
        assert gs._ladder_pairs(grid, "mlb") == monotonic_pairs(
            LEAGUE_CONFIGS["mlb"].columns
        )
        assert ("division", "pennant") not in gs._ladder_pairs(grid, "mlb")

    def test_no_league_bounds_a_stage_by_its_division(self):
        """Across every configured league, for the same reason."""
        for slug, config in LEAGUE_CONFIGS.items():
            bounds = {bound for bound, _col in monotonic_pairs(config.columns)}
            assert "division" not in bounds, (
                f"{slug} bounds a later stage by its division column — a wild "
                "card reaches the conference final without winning a division"
            )

    def test_a_bound_absent_from_the_payload_drops_rather_than_re_points(self):
        """The re-pointing IS the defect: falling back to 'the column before it'
        is how adjacency got read as the ladder in the first place."""
        grid = _mlb_grid()
        grid["columns"] = [c for c in grid["columns"] if c["key"] != "make_playoffs"]
        pairs = gs._ladder_pairs(grid, "mlb")
        assert ("division", "pennant") not in pairs
        assert all(bound != "make_playoffs" for bound, _ in pairs)

    def test_unconfigured_grid_still_gets_the_adjacent_ladder(self):
        """A tournament draw has no LeagueConfig; adjacency is all we know, and
        it is right there — R32 does bound the Sweet 16."""
        grid = {"columns": [{"key": "round_of_32", "label": "R32"},
                            {"key": "sweet_16", "label": "S16"}],
                "teams": [{"name": "T", "cells": {"round_of_32": _cell(0.20),
                                                  "sweet_16": _cell(0.60)}}]}
        findings = gs.check_monotonicity(grid, "not-a-configured-league")
        assert len(findings) == 1 and findings[0]["severity"] == "critical"


class TestSentinelSeesTheEliminatedLeak:
    """The defect the false alarm was masking — and the check that finds it."""

    def test_eliminated_team_priced_downstream_is_critical(self):
        findings = gs.check_eliminated_ladder(_mlb_grid(), "mlb")
        details = [f["detail"] for f in findings]
        assert len(findings) == 2, details  # pennant (from MP) + WS (from MP)
        assert all(f["severity"] == "critical" for f in findings)
        assert all(f["seasonal_ok"] is False for f in findings)
        assert any("Pittsburgh Pirates" in d and "AL / NL Champ" in d
                   for d in details), details

    def test_no_finding_once_the_page_propagates(self):
        grid = _mlb_grid()
        propagate_elimination(grid["teams"], LEAGUE_CONFIGS["mlb"].columns)
        assert gs.check_eliminated_ladder(grid, "mlb") == []

    def test_a_live_prerequisite_is_never_a_finding(self):
        """A 0.8% Make Playoffs is a price, not an elimination."""
        grid = _mlb_grid()
        grid["teams"][1]["cells"]["make_playoffs"] = _cell(0.008)
        grid["teams"][1]["cells"]["division"] = _cell(0.005)
        assert gs.check_eliminated_ladder(grid, "mlb") == []


class TestPropagateElimination:
    """The serving-side half: the grid stops making the claim."""

    def test_eliminated_run_ends_the_whole_ladder(self):
        grid = _mlb_grid()
        assert propagate_elimination(grid["teams"], LEAGUE_CONFIGS["mlb"].columns) == 2
        pirates = grid["teams"][1]["cells"]
        for key in ("pennant", "championship"):
            assert pirates[key]["state"] == "eliminated"
            assert pirates[key]["merged_probability"] is None
            assert pirates[key]["sources"] == []
            assert pirates[key]["trend_24h"] is None

    def test_it_carries_the_length_of_the_ladder_in_one_pass(self):
        """`championship` is bounded by `pennant`, which is only eliminated by
        this same pass — a one-directional loop must still reach it."""
        grid = _mlb_grid()
        propagate_elimination(grid["teams"], LEAGUE_CONFIGS["mlb"].columns)
        assert grid["teams"][1]["cells"]["championship"]["state"] == "eliminated"

    def test_a_live_team_is_untouched(self):
        grid = _mlb_grid()
        propagate_elimination(grid["teams"], LEAGUE_CONFIGS["mlb"].columns)
        yankees = grid["teams"][0]["cells"]
        assert yankees["pennant"]["merged_probability"] == 0.2225
        assert yankees["division"]["merged_probability"] == 0.0275
        guardians = grid["teams"][2]["cells"]
        assert guardians["championship"]["merged_probability"] == 0.0445

    def test_a_venue_settlement_outranks_the_inference(self):
        """Contradictory, but a grade is evidence and this is an inference: the
        settled cell keeps its own word and the sentinel keeps reporting it."""
        grid = _mlb_grid()
        grid["teams"][1]["cells"]["pennant"] = _cell(None, "won")
        propagate_elimination(grid["teams"], LEAGUE_CONFIGS["mlb"].columns)
        assert grid["teams"][1]["cells"]["pennant"]["state"] == "won"

    def test_idempotent(self):
        grid = _mlb_grid()
        first = propagate_elimination(grid["teams"], LEAGUE_CONFIGS["mlb"].columns)
        second = propagate_elimination(grid["teams"], LEAGUE_CONFIGS["mlb"].columns)
        assert first == 2 and second == 0

    def test_division_elimination_does_not_end_the_pennant(self):
        """The wild-card path, on the write side. Boston is out of the AL East
        and 11.3% to win the pennant — #7076's specimen, and the reason this
        walks `depends_on` rather than the column order."""
        grid = {"columns": _mlb_grid()["columns"],
                "teams": [{"name": "Boston Red Sox",
                           "cells": {"make_playoffs": _cell(0.9972),
                                     "division": _cell(None, "eliminated"),
                                     "pennant": _cell(0.1133),
                                     "championship": _cell(0.0545)}}]}
        assert propagate_elimination(grid["teams"], LEAGUE_CONFIGS["mlb"].columns) == 0
        assert grid["teams"][0]["cells"]["pennant"]["merged_probability"] == 0.1133

    def test_no_columns_no_work(self):
        teams = [{"name": "T", "cells": {"championship": _cell(0.1)}}]
        assert propagate_elimination(teams, [GridColumn("championship", "C", 1)]) == 0
        assert teams[0]["cells"]["championship"]["merged_probability"] == 0.1
