"""Tests for utils/playoff_grid.py — extracted championship grid logic."""

import logging
from types import SimpleNamespace

from app.utils.playoff_grid import (
    normalize_column_sums,
    enforce_monotonicity,
    compute_movers,
    sort_teams_by_championship,
    is_valid_grid_outcome,
    EXPECTED_COLUMN_SUMS,
    MOVER_FLOOR_24H,
)


def _make_team(name, champ_prob=0.0, trend=None):
    cells = {"championship": {"merged_probability": champ_prob, "sources": [{"probability": champ_prob, "source": "test"}]}}
    if trend is not None:
        cells["championship"]["trend_24h"] = trend
    return {"name": name, "short_name": name[:3].upper(), "team_id": hash(name), "cells": cells, "logo_url": None, "primary_color": None}


def _make_eliminated_team(name, team_id):
    """A club whose championship cell EXISTS and says it is out.

    A settled cell carries no probability, so it reaches the sort's fallback
    branch — the same branch a row with no cell at all used to reach.
    """
    return {
        "name": name, "short_name": name[:3].upper(), "team_id": team_id,
        "cells": {"championship": {"state": "eliminated", "sources": []}},
        "logo_url": None, "primary_color": None,
    }


def _make_row_without_championship_cell(name):
    """The #7754 phantom: a venue name that resolved to no club in `teams`.

    It reached the grid on a division market and has no championship cell, no
    crest, no record and a null `team_id`.
    """
    return {
        "name": name, "short_name": name[:3].upper(), "team_id": None,
        "cells": {"division": {"merged_probability": 0.002, "state": "live"}},
        "logo_url": None, "primary_color": None,
    }


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


class TestAMoversRailContainsOnlyTeamsThatMoved:
    """#7742 — `limit` is a ceiling on the rail, never a quota to fill.

    Every specimen here carries an admitted control beside the refused rows, so
    a filter that simply returned nothing would fail each one.
    """

    def test_a_team_that_did_not_move_is_not_published_as_a_mover(self):
        teams = [
            _make_team("Real Mover", 0.30, trend=0.02),
            _make_team("Flat A", 0.20, trend=0.0),
            _make_team("Flat B", 0.10, trend=0.0),
            _make_team("Flat C", 0.10, trend=0.0),
        ]

        movers = compute_movers(teams, "championship")

        assert [m["name"] for m in movers] == ["Real Mover"]

    def test_negative_zero_is_not_published_as_a_decline(self):
        # Production stamped `direction: "down"` on a -0.0 change: the ternary
        # sent every non-positive value down, and -0.0 is not > 0.
        teams = [
            _make_team("Genuine Decline", 0.30, trend=-0.02),
            _make_team("Unmoved", 0.20, trend=-0.0),
        ]

        movers = compute_movers(teams, "championship")

        assert [m["name"] for m in movers] == ["Genuine Decline"]
        assert movers[0]["direction"] == "down"
        assert all(m["change_24h"] != 0 for m in movers)

    def test_the_floor_itself_is_published_and_just_below_it_is_not(self):
        teams = [
            _make_team("Big", 0.40, trend=0.05),
            _make_team("At Floor", 0.30, trend=MOVER_FLOOR_24H),
            _make_team("Below Floor", 0.20, trend=MOVER_FLOOR_24H - 0.0001),
            _make_team("Below Floor Negative", 0.10, trend=-(MOVER_FLOOR_24H - 0.0001)),
        ]

        movers = compute_movers(teams, "championship")

        assert sorted(m["name"] for m in movers) == ["At Floor", "Big"]

    def test_a_rail_of_genuine_movers_is_not_thinned(self):
        # The control for over-filtering: when everything really moved, the
        # rail keeps all of it.
        teams = [_make_team(f"T{i}", 0.1, trend=0.01 * (i + 1)) for i in range(5)]

        movers = compute_movers(teams, "championship")

        assert len(movers) == 5

    def test_the_production_ncaab_rail_shrinks_to_its_two_real_movers(self):
        # The served /api/playoffs/ncaab payload of 2026-09-21 07:10Z: ten
        # published "movers", seven of them exactly zero and one at 0.06pp. The
        # league page sized its chrome on that ten and printed a header over the
        # two chips that survived the client floor.
        teams = [
            _make_team("Eastern Michigan Eagles", 0.02, trend=0.0126),
            _make_team("Texas Tech Red Raiders", 0.02, trend=-0.0091),
            _make_team("Mississippi St Bulldogs", 0.02, trend=0.0006),
            _make_team("Florida Gators", 0.05, trend=0.0),
            _make_team("Duke Blue Devils", 0.05, trend=0.0),
            _make_team("UConn Huskies", 0.05, trend=0.0),
            _make_team("Illinois Fighting Illini", 0.04, trend=0.0),
            _make_team("Texas Longhorns", 0.03, trend=-0.0),
            _make_team("Arizona Wildcats", 0.03, trend=-0.0),
            _make_team("Michigan St Spartans", 0.03, trend=-0.0),
        ]

        movers = compute_movers(teams, "championship")

        assert [m["name"] for m in movers] == [
            "Eastern Michigan Eagles",
            "Texas Tech Red Raiders",
        ]
        # CHROME_MOVERS_MIN is 3: a truthful length is what lets the league
        # page's gate suppress a strip that has nothing to say.
        assert len(movers) < 3


class TestSortTeamsByChampionship:

    def test_sorts_descending(self):
        teams = [_make_team("C", 0.10), _make_team("A", 0.50), _make_team("B", 0.30)]
        result = sort_teams_by_championship(teams, "championship", max_teams=10)
        assert [t["name"] for t in result] == ["A", "B", "C"]

    def test_caps_at_max(self):
        teams = [_make_team(f"T{i}", 0.1) for i in range(20)]
        result = sort_teams_by_championship(teams, "championship", max_teams=5)
        assert len(result) == 5

    def test_a_row_with_no_cell_sorts_below_an_eliminated_club(self):
        # #7754. `_championship_sort_value` returned 0.0 both for a club whose
        # championship cell says `eliminated` and for a row with no
        # championship cell at all. Those are not the same fact, and because
        # `list.sort` is stable the tie fell to arrival order.
        #
        # TWO rows tied at 0.0 under the old rule is the whole specimen, and
        # the assertion is on ORDER, not membership: a one-row fixture passes
        # whether or not the tie is broken. The phantom is listed FIRST so
        # arrival order alone would keep it above the real club.
        phantom = _make_row_without_championship_cell("Oakland Athletics")
        reds = _make_eliminated_team("Cincinnati Reds", team_id=10713)

        result = sort_teams_by_championship(
            [phantom, reds], "championship", max_teams=10
        )

        assert [t["name"] for t in result] == ["Cincinnati Reds", "Oakland Athletics"]

    def test_the_last_seat_goes_to_the_decided_club_not_the_undecided_row(self):
        # The reader-visible half: MLB's cap is exactly the league size, so the
        # 31st candidate always costs somebody their row.
        phantom = _make_row_without_championship_cell("Oakland Athletics")
        reds = _make_eliminated_team("Cincinnati Reds", team_id=10713)

        result = sort_teams_by_championship([phantom, reds], "championship", max_teams=1)

        assert [t["name"] for t in result] == ["Cincinnati Reds"]

    def test_a_tie_at_the_cap_goes_to_the_row_that_resolved_to_a_real_club(self):
        # Both rows are eliminated, so both score 0.0 on merit. Arrival order
        # favours the unidentified one; the tie-break must not.
        unidentified = _make_eliminated_team("Oakland Athletics", team_id=None)
        reds = _make_eliminated_team("Cincinnati Reds", team_id=10713)

        result = sort_teams_by_championship(
            [unidentified, reds], "championship", max_teams=1
        )

        assert [t["name"] for t in result] == ["Cincinnati Reds"]

    def test_an_unidentified_row_that_outranks_on_a_real_price_keeps_its_seat(self):
        # The tie-break must not become a blanket preference for a non-null
        # `team_id`. Measured on production 2026-09-21: wncaab carries three
        # rows with a null `team_id` that are REAL tournament schools our name
        # matching missed — `Ohio St.`, `North Carolina St.`, `Iowa St.` — and
        # mls carries `New York RB`. Every one holds a real championship price.
        # Cutting them for a lower-priced club would be #7754 pointed the other
        # way.
        ohio_state = _make_team("Ohio St.", 0.08)
        ohio_state["team_id"] = None
        longshot = _make_team("Rutgers Scarlet Knights", 0.01)

        result = sort_teams_by_championship(
            [longshot, ohio_state], "championship", max_teams=1
        )

        assert [t["name"] for t in result] == ["Ohio St."]

    def test_the_cap_logs_what_it_dropped(self, caplog):
        # `teams[:max_teams]` was a `.slice` doing a filter's job in silence,
        # while `team_count` still reported a full grid. A lost club now leaves
        # a trace.
        teams = [_make_team(f"T{i}", 0.5 - i * 0.01) for i in range(8)]

        with caplog.at_level(logging.INFO, logger="app.utils.playoff_grid"):
            sort_teams_by_championship(teams, "championship", max_teams=5)

        assert "8 candidates for 5 seats, dropped 3" in caplog.text
        assert "T7" in caplog.text

    def test_the_cap_is_silent_when_it_drops_nothing(self):
        teams = [_make_team("A", 0.5), _make_team("B", 0.4)]
        result = sort_teams_by_championship(teams, "championship", max_teams=30)
        assert [t["name"] for t in result] == ["A", "B"]

    # ---- #8209: rows tied on every other term get ONE fixed order ----------
    #
    # Production 2026-09-23: `ncaa-basketball` serves 23 of 68 rows at an
    # identical championship of 0.0005 and the cap is 68, so the cap cuts
    # through the tie. The assertions below are on ORDER and on CAP MEMBERSHIP
    # under a PERMUTED input — an assertion that merely sorts one fixture
    # passes just as happily with no tiebreak at all, because `list.sort` is
    # stable and a single fixture has only one arrival order.

    def test_a_tie_on_every_other_term_is_ordered_the_same_whatever_order_it_arrives_in(self):
        names = [f"Longshot {i:02d}" for i in range(12)]
        forward = sort_teams_by_championship(
            [_make_team(n, 0.0005) for n in names], "championship", max_teams=50
        )
        reversed_arrival = sort_teams_by_championship(
            [_make_team(n, 0.0005) for n in reversed(names)], "championship", max_teams=50
        )

        assert [t["name"] for t in forward] == [t["name"] for t in reversed_arrival]

    def test_the_cap_keeps_the_same_teams_when_the_same_tie_arrives_in_a_different_order(self):
        # The reader-visible half, and the one the issue is named for: three
        # schools left /playoffs/ncaa-basketball and three joined it with every
        # displayed percentage unchanged. Membership, not just order.
        names = [f"Longshot {i:02d}" for i in range(23)]
        forward = sort_teams_by_championship(
            [_make_team(n, 0.0005) for n in names], "championship", max_teams=20
        )
        reversed_arrival = sort_teams_by_championship(
            [_make_team(n, 0.0005) for n in reversed(names)], "championship", max_teams=20
        )

        assert len(forward) == len(reversed_arrival) == 20
        assert {t["name"] for t in forward} == {t["name"] for t in reversed_arrival}

    def test_the_name_tiebreak_never_outranks_a_real_price(self):
        # CONTROL, opposite branch of term 1: if name leaked ahead of the
        # probability the whole grid would go alphabetical. "Akron" is named to
        # sort first and priced to sort last.
        akron = _make_team("Akron Zips", 0.01)
        zags = _make_team("Zzz Bulldogs", 0.90)

        result = sort_teams_by_championship([akron, zags], "championship", max_teams=10)

        assert [t["name"] for t in result] == ["Zzz Bulldogs", "Akron Zips"]

    def test_the_name_tiebreak_never_outranks_the_identified_club_rule(self):
        # CONTROL, opposite branch of term 2: #7754's tie-break must still win
        # over the new term. Both rows are eliminated so term 1 ties, and the
        # UNIDENTIFIED row is named to sort first alphabetically — so if name
        # were checked before `team_id is None`, the phantom would take the
        # seat and #7754 would be silently reopened.
        unidentified = _make_eliminated_team("Aaa Athletics", team_id=None)
        reds = _make_eliminated_team("Cincinnati Reds", team_id=10713)

        result = sort_teams_by_championship(
            [unidentified, reds], "championship", max_teams=1
        )

        assert [t["name"] for t in result] == ["Cincinnati Reds"]


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
    """enforce_monotonicity caps a stage at the stage that BOUNDS it.

    Every column below is an undeclared one — no `depends_on` — so the bound is
    the column before it, which is the default and the whole of what this class
    exercises. The four real leagues that carry a `division` column no longer
    look like this: they declare conference/pennant bounded by `make_playoffs`,
    because a wild card does not win its division. The names here say
    "division"/"conference" for readability only; for the real configs' rule
    see `test_playoff_grid_division_is_not_a_prerequisite_7076.py` (#7076).
    """

    def _chained_columns(self):
        return [
            SimpleNamespace(key="make_playoffs", order=1, sequential=True),
            SimpleNamespace(key="division", order=2, sequential=True),
            SimpleNamespace(key="conference", order=3, sequential=True),
            SimpleNamespace(key="championship", order=4, sequential=True),
        ]

    def test_caps_conference_at_division(self):
        """An undeclared column is capped at the column before it.

        Named for NHL issue #728, whose real configs no longer chain this way
        (#7076); the rule under test is the default bound, not NHL's.
        """
        team = {
            "name": "Colorado Avalanche",
            "cells": {
                "make_playoffs": {"merged_probability": 0.80, "sources": [{"probability": 0.80, "source": "odds_api"}]},
                "division": {"merged_probability": 0.20, "sources": [{"probability": 0.20, "source": "odds_api"}]},
                "conference": {"merged_probability": 0.35, "sources": [{"probability": 0.35, "source": "kalshi"}]},
                "championship": {"merged_probability": 0.10, "sources": [{"probability": 0.10, "source": "odds_api"}]},
            },
        }
        fixes = enforce_monotonicity([team], self._chained_columns())
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
        fixes = enforce_monotonicity([team], self._chained_columns())
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
        fixes = enforce_monotonicity([team], self._chained_columns())
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
        fixes = enforce_monotonicity([team], self._chained_columns())
        # Division missing -> no fix for division->conference pair, but
        # make_playoffs->division is skipped too. So no fix unless conference
        # is compared to make_playoffs (it isn't — the check is sequential pairs only)
        # This is OK because the issue is with PRESENT columns being inconsistent.
        assert team["cells"]["conference"]["merged_probability"] == 0.60  # unchanged (no prev cell for pair)

    def test_capped_cell_keeps_each_markets_quote_and_names_its_bound(self):
        """#8251: the merged number is capped; the sources are NOT.

        Each `sources` entry names a market and a reader taps the row to read
        what that market says (D91). Clamping them credited the CFP semifinal
        market with a number it never quoted. The cap is announced instead, by
        `capped_by` naming the bound column, so a client (or a withholding rule,
        #8243) can tell an inherited bound from a quote.
        """
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
        enforce_monotonicity([team], self._chained_columns())
        conf = team["cells"]["conference"]
        assert conf["merged_probability"] == 0.15
        assert [s["probability"] for s in conf["sources"]] == [0.30, 0.28]
        assert conf["capped_by"] == "division"
        # the bound itself and an uncapped cell carry no marker
        assert "capped_by" not in team["cells"]["division"]
        assert "capped_by" not in team["cells"]["championship"]

    def test_normalization_then_monotonicity(self):
        """Simulates the real bug: normalization inflates conference, then monotonicity re-caps.

        This is the NHL issue #728 scenario:
        - Raw conference sum is low, so normalize_column_sums scales it up
        - After scaling, some teams have conference > division
        - enforce_monotonicity must fix this
        """
        cols = self._chained_columns()
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
