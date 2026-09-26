"""#2753 — "Recent upset" needs the winner to have been a REAL underdog.

The chip had a direction (#6279 a winner, #6529 the underdog won, #7055 both
legs) and never a size. Served on Discover 2026-09-25 23:44Z, slot 11:

    15318549  Chicago Cubs 3 @ Boston Red Sox 4   opening 0.4704 / 0.5296
    headline  Recent upset
    reason    Boston Red Sox won as a 49% underdog     score 68

while the live card two slots above it called a 49/51 board "Coin flip". The
bar is ``CLOSE_MATCHUP_MIN`` on the winner's SHARE of the opening pair, and the
settled sentence declines at the same printed bar (#6477's line, reused).

Measured over production feeds the same minute (Discover 0/60, sports
0/60/120): 15 finished cards chipped, 3 lose it — the Red Sox (0.470),
Valencia Basket (0.472) and Ukraine (three-way 0.3194 vs 0.3729, share 0.461);
the other 12 opened at or under 0.392 and keep everything.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_taxonomy import _extract_signals
from app.utils.feed_reasons import generate_event_reason
from app.utils.highlights import (
    CLOSE_MATCHUP_MIN,
    WEIGHTS,
    compute_highlight,
    get_highlight_label,
    should_highlight,
    winner_opened_as_a_real_underdog,
)

NOW = datetime(2026, 9, 25, 23, 44, tzinfo=timezone.utc)


def _finished(
    *,
    home_score,
    away_score,
    opening_home_prob,
    opening_away_prob=None,
    current_home_prob,
    sport_key="baseball_mlb",
):
    if opening_away_prob is None:
        opening_away_prob = 1 - opening_home_prob
    return compute_highlight(
        status="completed",
        commence_time=NOW - timedelta(hours=5),
        completed_at=NOW - timedelta(hours=2),
        sport_key=sport_key,
        opening_home_prob=opening_home_prob,
        opening_away_prob=opening_away_prob,
        opening_favorite="home" if opening_home_prob > opening_away_prob else "away",
        current_home_prob=current_home_prob,
        current_away_prob=1 - current_home_prob,
        home_score=home_score,
        away_score=away_score,
        now=NOW,
    )


def _the_specimen():
    """15318549 — Cubs 3 @ Red Sox 4, as served (aggregate 0.9379 at the read)."""
    return _finished(
        home_score=4, away_score=3, opening_home_prob=0.4704, current_home_prob=0.9379
    )


def _signals(result) -> set[str]:
    tags: set[str] = set()
    _extract_signals(result.flags, tags)
    return tags


# ── A. THE SPECIMEN LOSES EVERY UPSET SIGNAL ──────────────────────────────────


class TestTheSpecimen:
    def test_the_price_switch_still_fired(self):
        """The direction clauses all pass — this is a size refusal, not theirs."""
        result = _the_specimen()
        assert result.flags.favorite_switched is True
        assert result.flags.underdog_is_leading is True
        assert result.flags.winner_was_a_real_underdog is False

    def test_no_chip(self):
        result = _the_specimen()
        assert result.flags.is_upset is False
        assert "upset" not in result.reasons
        assert get_highlight_label(result) != "Recent upset"

    def test_no_bonus_no_force_highlight_no_tag(self):
        result = _the_specimen()
        real = _finished(
            home_score=4, away_score=3, opening_home_prob=0.3634, current_home_prob=0.9379
        )
        assert real.flags.is_upset is True
        assert "recent_finish_upset" in WEIGHTS
        assert "signal:upset" not in _signals(result)
        assert "signal:upset" in _signals(real)
        assert should_highlight(result, min_score=101) is False
        assert should_highlight(real, min_score=101) is True

    def test_no_sentence(self):
        """The chip is gone, so the #6477 branch answers — and declines at 49."""
        result = _the_specimen()
        text = generate_event_reason(
            home_team="Boston Red Sox",
            away_team="Chicago Cubs",
            status="completed",
            highlight_reasons=result.reasons,
            opening_home_prob=0.4704,
            home_score=4,
            away_score=3,
            prematch_percents={"home": 49, "away": 51},
        )
        assert text == ""


# ── B. THE SAME READ'S OTHER REFUSALS, AND WHY SHARE NOT LEG ──────────────────


class TestTheOtherRefusals:
    def test_valencia_basket(self):
        """15296967 Valencia 96 @ Besiktas 94, opening 0.5284 / 0.4716."""
        result = _finished(
            home_score=94,
            away_score=96,
            opening_home_prob=0.5284,
            current_home_prob=0.02,
            sport_key="basketball_euroleague",
        )
        assert result.flags.is_upset is False

    def test_a_draw_priced_board_is_read_as_a_share(self):
        """15290675 Ukraine 1 @ Hungary 0, opening 0.3729 / 0.3194 (draw ~0.31).

        The raw away leg is under 0.40; set the draw aside and it is a 46/54
        board. A bar on the raw leg would keep this chip — the share refuses it.
        """
        assert 0.3194 < CLOSE_MATCHUP_MIN
        result = _finished(
            home_score=0,
            away_score=1,
            opening_home_prob=0.3729,
            opening_away_prob=0.3194,
            current_home_prob=0.02,
            sport_key="soccer_uefa_nations_league",
        )
        assert result.flags.winner_was_a_real_underdog is False
        assert result.flags.is_upset is False

    @pytest.mark.parametrize(
        "home_score,away_score,opening_home_prob,current_home_prob",
        [
            # Moved out of #6529's "every true upset keeps its chip" list:
            # winners opened at 43.5%, 45.3%, 43.8%.
            (3, 6, 0.5649, 0.20),  # 15312654 Cubs - Braves
            (5, 7, 0.5472, 0.10),  # 15312653 Mets - Orioles
            (1, 10, 0.5624, 0.05),  # 15312873 Blue Jays - Tigers
        ],
    )
    def test_the_6529_close_band_winners(
        self, home_score, away_score, opening_home_prob, current_home_prob
    ):
        result = _finished(
            home_score=home_score,
            away_score=away_score,
            opening_home_prob=opening_home_prob,
            current_home_prob=current_home_prob,
        )
        assert result.flags.favorite_switched is True
        assert result.flags.is_upset is False


# ── C. CONTROLS — GREEN ON BOTH TREES ─────────────────────────────────────────


class TestTheControls:
    @pytest.mark.parametrize(
        "home_score,away_score,opening_home_prob,opening_away_prob,sport_key",
        [
            (4, 6, 0.6366, 0.3634, "baseball_mlb"),  # 15318086 Angels @ Mariners
            (2, 4, 0.6083, 0.3917, "baseball_mlb"),  # 15317977 Padres @ Dodgers
            (14, 35, 0.675, 0.325, "americanfootball_nfl"),  # 14780546 Falcons
            (1, 2, 0.7619, 0.2381, "tennis_wta"),  # 15317920 Fernandez
            # 15290672 N. Ireland @ Georgia — three-way, share 0.278.
            (0, 1, 0.5199, 0.1998, "soccer_uefa_nations_league"),
        ],
    )
    def test_the_same_reads_real_upsets_keep_the_chip(
        self, home_score, away_score, opening_home_prob, opening_away_prob, sport_key
    ):
        result = _finished(
            home_score=home_score,
            away_score=away_score,
            opening_home_prob=opening_home_prob,
            opening_away_prob=opening_away_prob,
            current_home_prob=0.02,
            sport_key=sport_key,
        )
        assert result.flags.is_upset is True
        assert get_highlight_label(result) == "Recent upset"

    def test_an_unreadable_scoreboard_keeps_its_chip(self):
        """None is not a denial (#6279's convention, inherited)."""
        result = _finished(
            home_score=None, away_score=None, opening_home_prob=0.4704, current_home_prob=0.94
        )
        assert result.flags.winner_was_a_real_underdog is None
        assert result.flags.is_upset is True


# ── D. THE BAR ITSELF ─────────────────────────────────────────────────────────


class TestTheBar:
    def test_the_line_is_close_matchup_min_and_exclusive(self):
        assert winner_opened_as_a_real_underdog(0.60, 0, 1, 0.40) is False
        assert winner_opened_as_a_real_underdog(0.6001, 0, 1, 0.3999) is True
        assert winner_opened_as_a_real_underdog(0.3999, 1, 0, 0.6001) is True

    def test_the_winner_is_read_off_the_scoreboard(self):
        """Same pair, other winner: the favourite winning is never "real"."""
        assert winner_opened_as_a_real_underdog(0.30, 1, 0, 0.70) is True
        assert winner_opened_as_a_real_underdog(0.30, 0, 1, 0.70) is False

    def test_a_missing_away_leg_is_the_complement(self):
        assert winner_opened_as_a_real_underdog(0.65, 0, 1) is True
        assert winner_opened_as_a_real_underdog(0.55, 0, 1) is False

    @pytest.mark.parametrize(
        "args",
        [
            (None, 1, 0, 0.5),
            (0.3, None, 0, 0.7),
            (0.3, 1, None, 0.7),
            (0.3, 1, 1, 0.7),  # a draw is score_is_decided's refusal, not this one
            (0.0, 1, 0, 0.0),
        ],
    )
    def test_unanswerable_is_none(self, args):
        assert winner_opened_as_a_real_underdog(*args) is None


# ── E. THE PRICE-GATED SENTENCE HOLDS THE SAME PRINTED BAR ────────────────────


class TestTheSentence:
    def _upset_reason(self, printed_winner: int):
        return generate_event_reason(
            home_team="Home FC",
            away_team="Away FC",
            status="completed",
            highlight_reasons=["upset"],
            opening_home_prob=0.30,
            home_score=2,
            away_score=1,
            prematch_percents={"home": printed_winner, "away": 100 - printed_winner},
        )

    def test_under_the_bar_is_stated(self):
        assert self._upset_reason(39) == "Home FC won as a 39% underdog"

    def test_at_the_bar_declines(self):
        """15290672's shape: opening share 0.28 keeps the chip, but the printed
        three-way row reads 46 — no sentence states a close-matchup number."""
        assert self._upset_reason(40) == ""
        assert self._upset_reason(46) == ""

    def test_unknown_printed_percent_keeps_the_old_wording(self):
        text = generate_event_reason(
            home_team="Home FC",
            away_team="Away FC",
            status="completed",
            highlight_reasons=["upset"],
            opening_home_prob=0.30,
            home_score=2,
            away_score=1,
            prematch_percents=None,
        )
        assert text == "Home FC won as a 30% underdog"
