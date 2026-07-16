"""Golf tournament-page render fixes (Queue #80 — #954 / #955).

#954: Bubble Watch make-cut read a blind cross-source average that blended
DataGolf's differentiated make_cut with one-sided ~0.5 Polymarket/Kalshi
placeholder "To Make the Cut" markets, flattening everyone to ~50%. The fix
prefers DataGolf (_prefer_datagolf_merge).

#955: the Win-chart contenders series plotted "Winner Nationality" (it matches
the "winner" type) instead of golfer winner fields. The fix excludes any name
matching _NON_WINNER_MARKET_RE from the evolution-market selection.
"""

from app.routes.golf import (
    _prefer_datagolf_merge,
    _NON_CONTENDER_WINNER_RE,
    _detect_market_type,
    _tournament_market_type,
)


class TestPreferDataGolfMerge:
    def test_first_value_seeds(self):
        assert _prefer_datagolf_merge(None, False, 0.40, True) == (0.40, True)

    def test_datagolf_overrides_placeholder(self):
        # existing placeholder 0.51, DataGolf 0.85 arrives → take DataGolf
        val, is_dg = _prefer_datagolf_merge(0.51, False, 0.85, True)
        assert val == 0.85 and is_dg is True

    def test_datagolf_kept_over_later_placeholder(self):
        # existing DataGolf 0.85, placeholder 0.50 arrives → keep DataGolf
        val, is_dg = _prefer_datagolf_merge(0.85, True, 0.50, False)
        assert val == 0.85 and is_dg is True

    def test_same_class_values_average(self):
        # two non-DataGolf sources still average (prior behavior preserved)
        val, is_dg = _prefer_datagolf_merge(0.30, False, 0.50, False)
        assert val == 0.40 and is_dg is False

    def test_two_datagolf_values_average(self):
        val, is_dg = _prefer_datagolf_merge(0.80, True, 0.90, True)
        assert abs(val - 0.85) < 1e-9 and is_dg is True

    def test_differentiation_survives_real_values(self):
        # Scheffler: DataGolf 0.85 must not be diluted by the 0.51 placeholder
        scheffler, _ = _prefer_datagolf_merge(0.85, True, 0.51, False)
        # Puig: DataGolf 0.40 must not be lifted toward 0.5
        puig, _ = _prefer_datagolf_merge(0.40, True, 0.485, False)
        assert scheffler == 0.85 and puig == 0.40
        assert scheffler - puig > 0.4  # real spread preserved, not flat ~0.5


class TestWinnerChartExclusion:
    def test_nationality_market_excluded(self):
        assert _NON_CONTENDER_WINNER_RE.search("2026 U.S. Open: Winner Nationality")

    def test_country_and_tour_of_winner_excluded(self):
        assert _NON_CONTENDER_WINNER_RE.search("Country of Winner")
        assert _NON_CONTENDER_WINNER_RE.search("Tour of Winner")

    def test_real_winner_markets_not_excluded(self):
        # Critically, "PGA Tour: ... Winner" must survive — the broad
        # _NON_WINNER_MARKET_RE ("tour .* winner") would wrongly drop it.
        for name in (
            "PGA Tour: U.S. Open Winner",
            "U.S. Open - Winner",
            "U.S. Open Winner",
            "U.S. Open: Winner",
        ):
            assert not _NON_CONTENDER_WINNER_RE.search(name), name

    def test_nationality_classifies_as_winner_type(self):
        # This is WHY the name-exclusion is needed: the nationality market is
        # typed "winner" (it contains "Winner"), so the >5-outcome filter alone
        # let its 26 outcomes through into the contenders chart.
        type_key, _ = _detect_market_type("2026 U.S. Open: Winner Nationality")
        assert type_key == "winner"


class TestTournamentMarketType:
    """L2-89: the detail-grouping reclass — non-contender-winner props and
    last-chance qualifier fields move OUT of the winner group into `other`, so
    they surface in Related Futures instead of vanishing."""

    def test_real_winner_field_stays_winner(self):
        for name in (
            "The Open Championship Winner",
            "The Open Winner",
            "U.S. Open Winner",
        ):
            assert _tournament_market_type(name)[0] == "winner", name

    def test_qualifier_winner_downgraded_to_other(self):
        # "The Open: Last-Chance Qualifier Winner" is a separate qualifying field,
        # not the tournament winner — it must not pollute the winner group.
        assert _tournament_market_type("The Open: Last-Chance Qualifier Winner")[0] == "other"
        assert _tournament_market_type("U.S. Open Final Qualifying Winner")[0] == "other"

    def test_nationality_winner_downgraded_to_other(self):
        assert _tournament_market_type("Winner Nationality - Europe")[0] == "other"
        assert _tournament_market_type("2026 U.S. Open: Winner Nationality")[0] == "other"

    def test_placement_families_unaffected(self):
        # The reclass only touches "winner"-typed markets; placement families are
        # detected before it and pass through unchanged.
        assert _tournament_market_type("The Open Championship: Top 5 Finishers")[0] == "top_5"
        # Alex's ruling (The Open 2026): Top 40 is a per-golfer placement column
        # in the ONE golfer grid, not an "other" wall in Related Futures.
        assert _tournament_market_type("The Open Championship: Top 40 Finishers")[0] == "top_40"
        # Round-scoped Top 40 must still classify round_top, never the grid column.
        assert _tournament_market_type("The Open: Round 2 Top 40 Finishers")[0] == "round_top"
        assert _tournament_market_type("The Open Championship: To Make the Cut")[0] == "make_cut"
        assert _tournament_market_type("The Open Championship End of Round 1 Leader")[0] == "round_leader"
