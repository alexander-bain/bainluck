"""#9161 — closeness on a draw-priced board reads both team legs, not home vs 50%.

Specimen: live Avai @ Criciuma (event 15313505, 2026-09-27 14:56Z) wore
"Virtually even" at home 0.46 — Criciuma opened 0.60, Avai 0.14. On a board
that prices a draw the home leg sits under 0.5 whoever is favoured, so the
home-leg band said nothing about closeness.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.highlights import _closeness_home_share, compute_highlight

NOW = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)
SOCCER = "soccer_brazil_serie_b"
NFL = "americanfootball_nfl"
CLOSE_REASONS = {"close_matchup", "very_close"}


def _live(sport_key, home, away, opening_home, opening_away):
    return compute_highlight(
        status="live",
        commence_time=NOW - timedelta(minutes=30),
        sport_key=sport_key,
        current_home_prob=home,
        current_away_prob=away,
        opening_home_prob=opening_home,
        opening_away_prob=opening_away,
        now=NOW,
    )


class TestDrawPricedBoard:
    @pytest.mark.parametrize("away", [None, 0.54], ids=["away-absent", "away-is-1-minus-home"])
    def test_specimen_home_046_with_no_independent_away_is_not_close(self, away):
        result = _live(SOCCER, 0.46, away, 0.60, 0.14)
        assert not CLOSE_REASONS & set(result.reasons)
        assert not result.flags.is_close_matchup
        assert not result.flags.is_very_close

    def test_clear_home_favourite_with_real_away_leg_is_not_close(self):
        # 0.46 / 0.25 (draw 0.29): home share 0.648 — Criciuma is the favourite.
        result = _live(SOCCER, 0.46, 0.25, 0.60, 0.14)
        assert not CLOSE_REASONS & set(result.reasons)
        assert not result.flags.is_close_matchup

    def test_genuinely_level_three_way_board_is_very_close(self):
        # 0.38 / 0.34 (draw 0.28): home share 0.528 — this IS even.
        result = _live(SOCCER, 0.38, 0.34, 0.40, 0.33)
        assert {"close_matchup", "very_close"} <= set(result.reasons)
        assert result.flags.is_very_close

    def test_close_but_not_very_close_three_way_board(self):
        # 0.40 / 0.30 (draw 0.30): home share 0.571 — close, not a coin flip.
        result = _live(SOCCER, 0.40, 0.30, 0.42, 0.30)
        assert "close_matchup" in result.reasons
        assert "very_close" not in result.reasons

    def test_level_board_whose_home_leg_is_far_below_the_old_band_is_now_seen(self):
        # 0.30 / 0.30 (draw 0.40): the old home-leg band (>= 0.40) missed it.
        result = _live(SOCCER, 0.30, 0.30, 0.31, 0.29)
        assert "very_close" in result.reasons


class TestTwoWayUnchanged:
    def test_two_way_control_at_048_is_still_very_close(self):
        result = _live(NFL, 0.48, 0.52, 0.60, 0.40)
        assert {"close_matchup", "very_close"} <= set(result.reasons)

    def test_two_way_with_absent_away_still_reads_the_home_leg(self):
        result = _live(NFL, 0.48, None, 0.60, None)
        assert {"close_matchup", "very_close"} <= set(result.reasons)

    @pytest.mark.parametrize("home", [0.40, 0.45, 0.55, 0.60, 0.39, 0.61])
    def test_two_way_share_is_the_home_leg_byte_for_byte(self, home):
        assert _closeness_home_share(home, 1 - home, NFL) == home
        assert _closeness_home_share(home, None, NFL) == home


class TestHelper:
    def test_draw_board_share_removes_the_draw(self):
        assert _closeness_home_share(0.38, 0.34, SOCCER) == pytest.approx(0.38 / 0.72)

    def test_draw_board_with_complement_away_has_no_share(self):
        assert _closeness_home_share(0.46, 0.54, SOCCER) is None

    def test_no_home_leg_has_no_share(self):
        assert _closeness_home_share(None, 0.3, SOCCER) is None
        assert _closeness_home_share(None, 0.3, NFL) is None
