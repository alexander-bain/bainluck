"""Golf winner-field renormalization (#926 / Queue #53).

Kalshi tournament-WINNER markets are independent per-golfer binaries that sum
well over 100% (gotcha #23). They were being dropped at the >1.5 participation-
market skip, so weekly events with only Kalshi coverage never surfaced on the
golf landing. `_golf_winner_renorm_factor` renormalizes the real winner fields
to sum 1.0 while still dropping genuine participation/threshold markets.
"""

from app.routes.golf import _golf_winner_renorm_factor


class TestGolfWinnerRenormFactor:
    def test_kalshi_winner_field_over_1_5_is_renormalized(self):
        # KLM Open Winner: 157 golfer candidates summing 5.338 → renormalize to 1.0
        f = _golf_winner_renorm_factor("KLM Open Winner", 157, 5.338)
        assert f is not None
        assert abs(f - 1.0 / 5.338) < 1e-9
        # the field would then sum to ~1.0
        assert abs(5.338 * f - 1.0) < 1e-9

    def test_us_womens_open_winner_renormalized(self):
        f = _golf_winner_renorm_factor("U.S. Women's Open Winner", 156, 2.513)
        assert f is not None and abs(2.513 * f - 1.0) < 1e-9

    def test_winner_under_1_5_unchanged(self):
        # U.S. Open Winner sums 1.483 (<1.5) → factor 1.0, used as-is (majors unchanged)
        assert _golf_winner_renorm_factor("U.S. Open Winner", 148, 1.483) == 1.0

    def test_make_cut_still_skipped(self):
        # Participation market summing >1.5 → None (skip), even with golfer candidates
        assert _golf_winner_renorm_factor("KLM Open: To Make the Cut", 153, 5.300) is None

    def test_top_n_finishers_still_skipped(self):
        assert _golf_winner_renorm_factor(
            "The Cj Cup Byron Nelson: Top 20 Finishers", 148, 39.845
        ) is None

    def test_round_leader_still_skipped(self):
        assert _golf_winner_renorm_factor(
            "KLM Open End of Round 1 Leader", 156, 10.085
        ) is None

    def test_round_scores_prop_skipped_no_winner_signal(self):
        # No "winner"/"to win" signal → not a winner field → skip
        assert _golf_winner_renorm_factor(
            "The Memorial Tournament: Round 1 Scores", 68, 33.72
        ) is None

    def test_nationality_of_winner_prop_skipped(self):
        # Has "Winner" but is a prop (_NON_WINNER excludes nationality) → skip
        assert _golf_winner_renorm_factor("Nationality of Winner", 8, 2.0) is None

    def test_small_winner_market_not_renormalized(self):
        # <4 candidates → not treated as a field even if >1.5
        assert _golf_winner_renorm_factor("Some Winner", 3, 2.0) is None
