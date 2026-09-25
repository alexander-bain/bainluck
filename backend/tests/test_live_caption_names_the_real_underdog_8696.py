"""#8696 — a live caption names the side that actually opened as the underdog.

PILLAR: TRUTH. Seen on production 2026-09-25 19:51Z (ux D48 walk, `/sports` at
390px, `/api/feed` same minute), UEFA Nations League event 15196508:

    Belgium 1 - 0 Italy   live, capsule "Upset brewing"
        home Italy  0 · away Belgium 1
        opening_odds  home 0.4419  away 0.2885  (three-way board)
        reason = headline = "Italy leading after starting at 44%"

Italy is losing, and Italy was the favourite. `underdog_leads` compared both legs
(#7055) and correctly decided the AWAY underdog leads; the renderer re-derived the
side with `opening_home_prob > 0.5`, got "home is the underdog" on a board where
the home favourite opens under 0.5, and printed the favourite's name and price.

Both now ask `pregame_favorite_side`, so the determination and the name cannot
disagree. Every rejection here is paired with a control.
"""

import pytest

from app.utils.feed_reasons import compose_live_claim
from app.utils.highlights import pregame_favorite_side, underdog_leads

NATIONS_LEAGUE = "soccer_uefa_nations_league"


def _belgium_italy(**overrides):
    kwargs = {
        "home_team": "Italy",
        "away_team": "Belgium",
        "status": "live",
        "home_probability": 0.13,
        "away_probability": 0.87,
        "opening_home_prob": 0.4419,
        "home_score": 0,
        "away_score": 1,
        "sport": NATIONS_LEAGUE,
        "opening_away_prob": 0.2885,
    }
    kwargs.update(overrides)
    return compose_live_claim(**kwargs)


class TestTheProductionSpecimen:
    def test_the_leading_underdog_is_named(self):
        claim = _belgium_italy()
        assert claim is not None
        assert claim.sentence == "Belgium leading after starting at 29%"

    def test_the_favourite_is_never_named_as_the_underdog(self):
        assert "Italy" not in _belgium_italy().sentence

    def test_the_determination_and_the_name_agree(self):
        assert underdog_leads(0.4419, 0, 1, opening_away_prob=0.2885) is True
        assert pregame_favorite_side(0.4419, 0.2885) == "home"


class TestControls:
    def test_the_favourite_ahead_gets_no_underdog_sentence(self):
        claim = _belgium_italy(home_score=1, away_score=0)
        assert claim is None or "leading after starting" not in claim.sentence

    def test_a_home_underdog_on_a_draw_board_is_still_named(self):
        """Mirror: the home side opened as the underdog on a draw board."""
        claim = _belgium_italy(
            opening_home_prob=0.2885, opening_away_prob=0.4419,
            home_probability=0.87, away_probability=0.13,
            home_score=1, away_score=0,
        )
        assert claim is not None
        assert claim.sentence == "Italy leading after starting at 29%"

    @pytest.mark.parametrize(
        "opening_home, score, expected",
        [
            (0.62, (2, 3), "Cincinnati Reds leading after starting at 38%"),
            (0.38, (3, 2), "Milwaukee Brewers leading after starting at 38%"),
        ],
    )
    def test_a_two_way_card_keeps_its_side_and_number(self, opening_home, score, expected):
        claim = compose_live_claim(
            home_team="Milwaukee Brewers",
            away_team="Cincinnati Reds",
            status="live",
            home_probability=0.5,
            away_probability=0.5,
            opening_home_prob=opening_home,
            home_score=score[0],
            away_score=score[1],
            sport="baseball_mlb",
            opening_away_prob=round(1 - opening_home, 4),
        )
        assert claim is not None
        assert claim.sentence == expected

    @pytest.mark.parametrize(
        "home, away, side",
        [(0.4419, 0.2885, "home"), (0.2885, 0.4419, "away"), (0.4, 0.4, "even"),
         (0.6, None, "home"), (0.4, None, "away"), (0.5, None, "even")],
    )
    def test_the_side_rule(self, home, away, side):
        assert pregame_favorite_side(home, away) == side
