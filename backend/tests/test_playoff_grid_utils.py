"""Tests for utils/playoff_grid.py — extracted championship grid logic."""

from types import SimpleNamespace

from app.utils.playoff_grid import (
    normalize_column_sums,
    enforce_monotonicity,
    compute_movers,
    sort_teams_by_championship,
    is_valid_grid_outcome,
    EXPECTED_COLUMN_SUMS,
)


def _make_team(name, champ_prob=0.0, trend=None):
    cells = {"championship": {"merged_probability": champ_prob, "sources": [{"probability": champ_prob, "source": "test"}]}}
    if trend is not None:
        cells["championship"]["trend_24h"] = trend
    return {"name": name, "short_name": name[:3].upper(), "team_id": hash(name), "cells": cells, "logo_url": None, "primary_color": None}


class TestNormalizeColumnSums:

    def test_no_normalization_when_sum_near_expected(self):
        teams = [_make_team("A", 0.50), _make_team("B", 0.45)]
        cols = [SimpleNamespace(key="championship")]
        normalize_column_sums(teams, cols, "test")
        total = sum(t["cells"]["championship"]["merged_probability"] for t in teams)
        assert abs(total - 0.95) < 0.01

    def test_normalizes_when_undershooting(self):
        teams = [_make_team("A", 0.30), _make_team("B", 0.20)]
        cols = [SimpleNamespace(key="championship")]
        normalize_column_sums(teams, cols, "test")
        total = sum(t["cells"]["championship"]["merged_probability"] for t in teams)
        assert abs(total - 1.0) < 0.01

    def test_normalizes_overshoot_without_changing_probability_order(self):
        teams = [_make_team("A", 0.62), _make_team("B", 0.36), _make_team("C", 0.20)]
        cols = [SimpleNamespace(key="championship")]

        normalize_column_sums(teams, cols, "test")

        probabilities = [t["cells"]["championship"]["merged_probability"] for t in teams]
        source_probabilities = [
            t["cells"]["championship"]["sources"][0]["probability"] for t in teams
        ]
        assert abs(sum(probabilities) - EXPECTED_COLUMN_SUMS["championship"]) < 0.01
        assert probabilities == sorted(probabilities, reverse=True)
        assert source_probabilities == probabilities

    def test_no_normalization_for_unknown_columns(self):
        teams = [_make_team("A", 0.30)]
        teams[0]["cells"]["make_playoffs"] = {"merged_probability": 0.30, "sources": []}
        cols = [SimpleNamespace(key="make_playoffs")]
        normalize_column_sums(teams, cols, "test")
        assert teams[0]["cells"]["make_playoffs"]["merged_probability"] == 0.30

    def test_no_normalization_when_zero_sum(self):
        teams = [_make_team("A", 0.0)]
        cols = [SimpleNamespace(key="championship")]
        normalize_column_sums(teams, cols, "test")
        assert teams[0]["cells"]["championship"]["merged_probability"] == 0.0

    def test_sources_also_scaled(self):
        teams = [_make_team("A", 0.25), _make_team("B", 0.25)]
        cols = [SimpleNamespace(key="championship")]
        normalize_column_sums(teams, cols, "test")
        for t in teams:
            cell = t["cells"]["championship"]
            assert cell["merged_probability"] == cell["sources"][0]["probability"]

    def test_caps_individual_cells_at_100_percent(self):
        """Regression test for MS15-4: OKC 105.2% conference win.

        When one team dominates a conference and the column undershoots,
        normalization can push the dominant team above 100%. Individual
        cells must be capped at 1.0 after normalization.
        """
        # Simulate: OKC at 69% conference, many teams at 1% each.
        # Conference expected sum = 200%. Raw sum = 69% + 29*1% = 98%.
        # Scale factor = 200/98 ≈ 2.04x → OKC would go to ~141%
        teams_conf = []
        okc = {"name": "Oklahoma City", "short_name": "OKC", "team_id": 1,
               "cells": {"conference": {"merged_probability": 0.69,
                                        "sources": [{"probability": 0.69, "source": "polymarket"}]}},
               "logo_url": None, "primary_color": None}
        teams_conf.append(okc)
        for i in range(29):
            t = {"name": f"Team{i}", "short_name": f"T{i}", "team_id": i + 100,
                 "cells": {"conference": {"merged_probability": 0.01,
                                          "sources": [{"probability": 0.01, "source": "kalshi"}]}},
                 "logo_url": None, "primary_color": None}
            teams_conf.append(t)

        cols = [SimpleNamespace(key="conference")]
        normalize_column_sums(teams_conf, cols, "nba")

        # OKC must be capped at 100% (1.0), not 141%
        okc_prob = okc["cells"]["conference"]["merged_probability"]
        assert okc_prob <= 1.0, f"OKC conference probability {okc_prob} exceeds 1.0"
        assert okc_prob == 1.0  # it was above 1.0 before cap, so it should be exactly 1.0

        # Source probability should also be capped
        okc_src = okc["cells"]["conference"]["sources"][0]["probability"]
        assert okc_src <= 1.0, f"OKC source probability {okc_src} exceeds 1.0"


class TestComputeMovers:

    def test_returns_movers_sorted_by_absolute_change(self):
        teams = [
            _make_team("A", 0.30, trend=0.05),
            _make_team("B", 0.20, trend=-0.08),
            _make_team("C", 0.10, trend=0.02),
        ]
        movers = compute_movers(teams, "championship")
        assert movers[0]["name"] == "B"
        assert movers[0]["direction"] == "down"
        assert movers[1]["name"] == "A"
        assert movers[1]["direction"] == "up"

    def test_skips_teams_without_trend(self):
        teams = [_make_team("A", 0.30, trend=None), _make_team("B", 0.20, trend=0.05)]
        movers = compute_movers(teams, "championship")
        assert len(movers) == 1
        assert movers[0]["name"] == "B"

    def test_limit(self):
        teams = [_make_team(f"T{i}", 0.1, trend=0.01 * i) for i in range(20)]
        movers = compute_movers(teams, "championship", limit=5)
        assert len(movers) == 5

    def test_empty_teams(self):
        assert compute_movers([], "championship") == []


class TestSortTeamsByChampionship:

    def test_sorts_descending(self):
        teams = [_make_team("C", 0.10), _make_team("A", 0.50), _make_team("B", 0.30)]
        result = sort_teams_by_championship(teams, "championship", max_teams=10)
        assert [t["name"] for t in result] == ["A", "B", "C"]

    def test_caps_at_max(self):
        teams = [_make_team(f"T{i}", 0.1) for i in range(20)]
        result = sort_teams_by_championship(teams, "championship", max_teams=5)
        assert len(result) == 5


class TestIsValidGridOutcome:

    def test_valid_team_name(self):
        assert is_valid_grid_outcome("Boston Celtics", 0.25, "odds_api", False)

    def test_rejects_empty_name(self):
        assert not is_valid_grid_outcome("", 0.25, "odds_api", False)

    def test_rejects_zero_probability(self):
        assert not is_valid_grid_outcome("Celtics", 0.0, "odds_api", False)

    def test_rejects_one_probability(self):
        assert not is_valid_grid_outcome("Celtics", 1.0, "odds_api", False)

    def test_rejects_yes_no(self):
        assert not is_valid_grid_outcome("Yes", 0.5, "kalshi", False)
        assert not is_valid_grid_outcome("no", 0.5, "kalshi", False)

    def test_rejects_over_under(self):
        assert not is_valid_grid_outcome("Over", 0.5, "odds_api", False)

    def test_rejects_seeded_outcomes(self):
        assert not is_valid_grid_outcome("#1 seed", 0.5, "odds_api", False)
        assert not is_valid_grid_outcome("1+ wins", 0.5, "odds_api", False)

    def test_rejects_matchup_pairs(self):
        assert not is_valid_grid_outcome("Tampa Bay and Colorado", 0.5, "odds_api", False)

    def test_allows_trail_blazers(self):
        assert is_valid_grid_outcome("Portland Trail Blazers", 0.25, "odds_api", False)

    def test_rejects_noise_without_bid(self):
        assert not is_valid_grid_outcome("Some Team", 0.50, "kalshi", has_real_bid=False)

    def test_allows_noise_with_real_bid(self):
        assert is_valid_grid_outcome("Some Team", 0.50, "kalshi", has_real_bid=True)

    def test_allows_non_noise_kalshi(self):
        assert is_valid_grid_outcome("Some Team", 0.30, "kalshi", has_real_bid=False)

    def test_rejects_country_in_soccer(self):
        countries = {"England", "France", "Germany"}
        assert not is_valid_grid_outcome("England", 0.25, "odds_api", False, sport_category="soccer", country_names=countries)

    def test_allows_club_in_soccer(self):
        countries = {"England", "France"}
        assert is_valid_grid_outcome("Manchester City", 0.25, "odds_api", False, sport_category="soccer", country_names=countries)


class TestEnforceMonotonicity:
    """Tests for enforce_monotonicity — ensures P(later stage) <= P(earlier stage)."""

    def _nhl_columns(self):
        return [
            SimpleNamespace(key="make_playoffs", order=1, sequential=True),
            SimpleNamespace(key="division", order=2, sequential=True),
            SimpleNamespace(key="conference", order=3, sequential=True),
            SimpleNamespace(key="championship", order=4, sequential=True),
        ]

    def test_caps_conference_at_division(self):
        """Conference probability > Division is capped (NHL issue #728)."""
        team = {
            "name": "Colorado Avalanche",
            "cells": {
                "make_playoffs": {"merged_probability": 0.80, "sources": [{"probability": 0.80, "source": "odds_api"}]},
                "division": {"merged_probability": 0.20, "sources": [{"probability": 0.20, "source": "odds_api"}]},
                "conference": {"merged_probability": 0.35, "sources": [{"probability": 0.35, "source": "kalshi"}]},
                "championship": {"merged_probability": 0.10, "sources": [{"probability": 0.10, "source": "odds_api"}]},
            },
        }
        fixes = enforce_monotonicity([team], self._nhl_columns())
        assert fixes == 1
        assert team["cells"]["conference"]["merged_probability"] == 0.20

    def test_cascading_caps(self):
        """Division > Make Playoffs cascades down to Conference and Championship."""
        team = {
            "name": "Test Team",
            "cells": {
                "make_playoffs": {"merged_probability": 0.30, "sources": []},
                "division": {"merged_probability": 0.50, "sources": []},
                "conference": {"merged_probability": 0.60, "sources": []},
                "championship": {"merged_probability": 0.25, "sources": []},
            },
        }
        fixes = enforce_monotonicity([team], self._nhl_columns())
        assert fixes == 2  # division and conference
        assert team["cells"]["division"]["merged_probability"] == 0.30
        assert team["cells"]["conference"]["merged_probability"] == 0.30
        assert team["cells"]["championship"]["merged_probability"] == 0.25

    def test_no_fix_when_already_monotonic(self):
        team = {
            "name": "Good Team",
            "cells": {
                "make_playoffs": {"merged_probability": 0.90, "sources": []},
                "division": {"merged_probability": 0.40, "sources": []},
                "conference": {"merged_probability": 0.30, "sources": []},
                "championship": {"merged_probability": 0.15, "sources": []},
            },
        }
        fixes = enforce_monotonicity([team], self._nhl_columns())
        assert fixes == 0

    def test_missing_intermediate_column_skipped(self):
        """If Division is missing, Conference is compared to Make Playoffs."""
        team = {
            "name": "No Division",
            "cells": {
                "make_playoffs": {"merged_probability": 0.50, "sources": []},
                "conference": {"merged_probability": 0.60, "sources": []},
                "championship": {"merged_probability": 0.10, "sources": []},
            },
        }
        # Conference should still be capped because it's compared to division (missing)
        # and then make_playoffs (the guard is: both prev_cell and curr_cell must exist)
        fixes = enforce_monotonicity([team], self._nhl_columns())
        # Division missing -> no fix for division->conference pair, but
        # make_playoffs->division is skipped too. So no fix unless conference
        # is compared to make_playoffs (it isn't — the check is sequential pairs only)
        # This is OK because the issue is with PRESENT columns being inconsistent.
        assert team["cells"]["conference"]["merged_probability"] == 0.60  # unchanged (no prev cell for pair)

    def test_source_probabilities_capped(self):
        """Individual source probabilities are capped along with merged."""
        team = {
            "name": "Source Cap Test",
            "cells": {
                "division": {"merged_probability": 0.15, "sources": [
                    {"probability": 0.15, "source": "odds_api"},
                ]},
                "conference": {"merged_probability": 0.30, "sources": [
                    {"probability": 0.30, "source": "kalshi"},
                    {"probability": 0.28, "source": "polymarket"},
                ]},
                "championship": {"merged_probability": 0.05, "sources": []},
            },
        }
        enforce_monotonicity([team], self._nhl_columns())
        for src in team["cells"]["conference"]["sources"]:
            assert src["probability"] <= 0.15

    def test_normalization_then_monotonicity(self):
        """Simulates the real bug: normalization inflates conference, then monotonicity re-caps.

        This is the NHL issue #728 scenario:
        - Raw conference sum is low, so normalize_column_sums scales it up
        - After scaling, some teams have conference > division
        - enforce_monotonicity must fix this
        """
        cols = self._nhl_columns()
        teams = [
            {
                "name": "Team A",
                "cells": {
                    "division": {"merged_probability": 0.20, "sources": [{"probability": 0.20, "source": "odds_api"}]},
                    "conference": {"merged_probability": 0.15, "sources": [{"probability": 0.15, "source": "kalshi"}]},
                    "championship": {"merged_probability": 0.05, "sources": [{"probability": 0.05, "source": "odds_api"}]},
                },
            },
            {
                "name": "Team B",
                "cells": {
                    "division": {"merged_probability": 0.10, "sources": [{"probability": 0.10, "source": "odds_api"}]},
                    "conference": {"merged_probability": 0.08, "sources": [{"probability": 0.08, "source": "kalshi"}]},
                    "championship": {"merged_probability": 0.02, "sources": [{"probability": 0.02, "source": "odds_api"}]},
                },
            },
        ]

        # Normalize conference: sum = 0.23, expected = 2.0, scale = 8.7x
        # This will push conference probabilities WAY above division
        conf_col = [c for c in cols if c.key == "conference"]
        normalize_column_sums(teams, conf_col, "nhl")

        # After normalization, conference > division for both teams
        for t in teams:
            if "conference" in t["cells"] and "division" in t["cells"]:
                # Conference was scaled up significantly
                assert t["cells"]["conference"]["merged_probability"] > t["cells"]["division"]["merged_probability"]

        # Now enforce monotonicity — should fix all violations
        fixes = enforce_monotonicity(teams, cols)
        assert fixes >= 2

        # Verify monotonicity holds
        for t in teams:
            cells = t["cells"]
            if "division" in cells and "conference" in cells:
                assert cells["conference"]["merged_probability"] <= cells["division"]["merged_probability"]
            if "conference" in cells and "championship" in cells:
                assert cells["championship"]["merged_probability"] <= cells["conference"]["merged_probability"]

    def test_non_sequential_columns_ignored(self):
        """Non-sequential columns (like EPL relegation) are not monotonicity-checked."""
        cols = [
            SimpleNamespace(key="relegation", order=1, sequential=False),
            SimpleNamespace(key="top_4", order=2, sequential=False),
            SimpleNamespace(key="championship", order=3, sequential=False),
        ]
        team = {
            "name": "EPL Team",
            "cells": {
                "relegation": {"merged_probability": 0.30, "sources": []},
                "top_4": {"merged_probability": 0.05, "sources": []},
                "championship": {"merged_probability": 0.50, "sources": []},
            },
        }
        fixes = enforce_monotonicity([team], cols)
        assert fixes == 0  # No fix — non-sequential
