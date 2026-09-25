"""T10-1 (#5439) — a live "Odds moved" card says HOW the odds moved.

PILLAR: DISCOVER (on TRUTH) · SHIP: the card at the top of Discover gives a reason
a reader can restate, not two words.

THE SPECIMEN, production 2026-09-25 22:42Z, `GET /api/feed?limit=40`, rank 1:
Chicago Cubs @ Boston Red Sox (game 2 of a doubleheader, event 15318545), live,
0-0 in the bottom 4th. Opened Boston 0.4792 / Chicago 0.5208, live Boston 0.532.

    headline = "Odds moved"          data.highlight.label = "Odds moved"

The web card printed "Odds moved" as its sentence — a price claim with neither
number in it. The two ladders disagreed about the evidence: `get_highlight_label`
serves "Odds moved" on ANY live favourite switch, while `select_live_claim`'s
movement arm needed a 15-point swing, so the claim came back None and the feed's
headline fell back to the bare pill text.

The fix gives the flip its own movement arm (two-way boards only), so the
headline now reads "Boston Red Sox chance rose from 48% to 53%". The pill and
the ranking are unchanged: `_discover_event_is_exception` reads the pill.

Every rejection below is paired with the case that still speaks.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.feed_reasons import compose_live_claim, generate_event_reason
from app.utils.highlights import compute_highlight, get_highlight_label, select_live_claim

NOW = datetime(2026, 9, 25, 22, 42, tzinfo=timezone.utc)

SPECIMEN = dict(
    home_team="Boston Red Sox",
    away_team="Chicago Cubs",
    status="live",
    home_probability=0.532,
    away_probability=0.468,
    opening_home_prob=0.4792,
    opening_away_prob=0.5208,
    home_score=0,
    away_score=0,
    sport="baseball_mlb",
)


def _claim(**overrides):
    return compose_live_claim(**{**SPECIMEN, **overrides})


def _pill(*, sport, opening_home, opening_away, current_home, home_score=0, away_score=0):
    """A real `compute_highlight` run, so a change to the pill's own rule shows up here."""
    return get_highlight_label(
        compute_highlight(
            status="live",
            commence_time=NOW - timedelta(minutes=70),
            sport_key=sport,
            opening_home_prob=opening_home,
            opening_away_prob=opening_away,
            opening_favorite=None,
            current_home_prob=current_home,
            current_away_prob=1 - current_home,
            home_score=home_score,
            away_score=away_score,
            completed_at=None,
            now=NOW,
        )
    )


class TestTheSpecimen:
    def test_the_specimen_still_wears_the_odds_moved_pill(self):
        """The pill is the half this ship does NOT touch — proves the specimen
        reaches the case, so the sentence test below is not vacuous."""
        assert _pill(
            sport="baseball_mlb", opening_home=0.4792, opening_away=0.5208, current_home=0.532
        ) == "Odds moved"

    def test_the_specimen_names_both_endpoints(self):
        claim = _claim()
        assert claim is not None
        assert claim.claim_type == "movement"
        assert claim.sentence == "Boston Red Sox chance rose from 48% to 53%"

    def test_the_mirror_flip_names_the_away_side(self):
        claim = _claim(
            opening_home_prob=0.5208, opening_away_prob=0.4792,
            home_probability=0.468, away_probability=0.532,
        )
        assert claim is not None
        assert claim.sentence == "Chicago Cubs chance rose from 48% to 53%"

    def test_the_reason_field_carries_the_same_sentence(self):
        text = generate_event_reason(
            home_team="Boston Red Sox",
            away_team="Chicago Cubs",
            status="live",
            highlight_reasons=["favorite_switched"],
            home_probability=0.532,
            away_probability=0.468,
            opening_home_prob=0.4792,
            opening_away_prob=0.5208,
            home_score=0,
            away_score=0,
            sport="baseball_mlb",
        )
        assert text == "Boston Red Sox chance rose from 48% to 53%"


class TestWhatTheFlipArmRefuses:
    def test_no_flip_no_claim(self):
        """Pirates @ Tigers on the same page: opened Detroit 0.5174, live 0.52 —
        the favourite never changed, so nothing is claimed (the pill says
        "Coin flip" and keeps saying it)."""
        assert _claim(
            opening_home_prob=0.5174, opening_away_prob=0.4826,
            home_probability=0.52, away_probability=0.48,
        ) is None

    def test_a_price_that_prints_50_is_not_a_visible_flip(self):
        assert _claim(home_probability=0.503, away_probability=0.497) is None
        # …and half a point further is.
        assert _claim(home_probability=0.506, away_probability=0.494) is not None

    def test_an_even_opening_had_no_favourite_to_lose(self):
        """0.49 / 0.51 is inside FAVORITE_MARGIN — `compute_highlight` calls it
        even and serves no "Odds moved"; the sentence arm agrees."""
        assert _claim(opening_home_prob=0.49, opening_away_prob=0.51) is None

    def test_a_draw_priced_board_is_not_read_as_a_flip(self):
        """#7055 — on a three-way board the home leg is under 0.5 whoever is
        favoured. Home opened the favourite (0.40 v 0.30, draw 0.30) and sits at
        0.45: still the favourite, but a one-leg read of 0.45 says "away" and
        would call it a flip. Five points is under the 15-point arm, so silent."""
        assert _claim(
            sport="soccer_epl",
            opening_home_prob=0.40, opening_away_prob=0.30,
            home_probability=0.45, away_probability=0.55,
        ) is None

    def test_a_draw_priced_board_still_gets_the_big_move(self):
        assert _claim(
            sport="soccer_epl",
            opening_home_prob=0.30, opening_away_prob=0.45,
            home_probability=0.52, away_probability=0.48,
        ) is not None

    def test_one_leg_callers_keep_the_old_behaviour(self):
        assert select_live_claim(
            status="live", opening_home_prob=0.4792, current_home_prob=0.532,
            home_score=0, away_score=0,
        ) is None

    def test_an_underdog_lead_still_outranks_the_flip(self):
        claim = _claim(home_score=2, away_score=0)
        assert claim is not None and claim.claim_type == "underdog_lead"


class TestThePillNeverStandsAlone:
    """On a two-way board, every live "Odds moved" pill now has a numbered
    sentence under it, so the feed's `headline` never falls back to the pill
    text. The grid spans flips under and over the 15-point arm, both sides."""

    @pytest.mark.parametrize("opening_home", [0.30, 0.44, 0.47, 0.53, 0.56, 0.70])
    @pytest.mark.parametrize("current_home", [0.25, 0.46, 0.49, 0.51, 0.54, 0.75])
    @pytest.mark.parametrize("scores", [(0, 0), (None, None), (3, 3)])
    def test_odds_moved_always_has_its_numbers(self, opening_home, current_home, scores):
        pill = _pill(
            sport="baseball_mlb", opening_home=opening_home, opening_away=1 - opening_home,
            current_home=current_home, home_score=scores[0], away_score=scores[1],
        )
        claim = _claim(
            opening_home_prob=opening_home, opening_away_prob=1 - opening_home,
            home_probability=current_home, away_probability=1 - current_home,
            home_score=scores[0], away_score=scores[1],
        )
        if pill == "Odds moved":
            assert claim is not None, (opening_home, current_home, scores)
            assert claim.sentence.count("%") == 2

    def test_the_grid_reaches_the_pill_below_the_big_move_arm(self):
        """Without a small flip in the grid the invariant would hold on the
        15-point arm alone and prove nothing about this fix."""
        assert _pill(
            sport="baseball_mlb", opening_home=0.47, opening_away=0.53, current_home=0.51
        ) == "Odds moved"
