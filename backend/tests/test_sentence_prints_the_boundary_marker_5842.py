"""#5842 — a Discover sentence states `>99%` / `<1%` where its card does.

PILLAR: FORMATTING · SHIP: a reader stops seeing "rose from 74% to 100%" three
millimetres under a hero that reads `>99%` on the same card.

THE DEFECT, production 2026-09-13 07:21Z, iPhone Discover cold open
(`artifacts-native-020/n140-1b-discover.png`):

    <1%        Win Probability        >99%
    Hawaii Rainbow Warriors chance rose from 74% to 100%

`_display_pct` returned a bare integer, and both clients print the same value
through a boundary rule instead (`probabilityParts` on web, `FormattingUtilities`
on native): rounds to 100 but is not 1 → `>99%`; rounds to 0 but is not 0 →
`<1%`. The sentence was the only surface that could say 100% or 0%.

Every rejection is paired with a control: the interior, and the exact
boundaries (which ARE the boundaries and print plainly, as on both clients).
"""

import pytest

from app.utils.feed_reasons import (
    _display_pct,
    _underdog_sentence,
    compose_live_claim,
)


def movement(opening_home: float, home_now: float):
    return compose_live_claim(
        home_team="Hawaii Rainbow Warriors",
        away_team="Portland State Vikings",
        status="live",
        home_probability=home_now,
        away_probability=1 - home_now,
        opening_home_prob=opening_home,
        home_score=35,
        away_score=7,
        sport="americanfootball_ncaaf",
    )


class TestTheSpecimen:
    def test_a_near_certain_rise_ends_on_the_marker_the_hero_prints(self):
        claim = movement(0.74, 0.997)
        assert claim is not None
        assert claim.sentence == "Hawaii Rainbow Warriors chance rose from 74% to >99%"

    def test_100_percent_is_gone_from_the_specimen(self):
        assert "100%" not in movement(0.74, 0.997).sentence

    def test_CONTROL_an_interior_move_is_byte_identical(self):
        assert (
            movement(0.52, 0.72).sentence
            == "Hawaii Rainbow Warriors chance rose from 52% to 72%"
        )


class TestTheRule:
    """The same rule as `probabilityParts`, run on the probability."""

    @pytest.mark.parametrize(
        "probability, expected",
        [
            (0.996, ">99"),
            (0.9999, ">99"),
            (0.004, "<1"),
            (0.0001, "<1"),
            # Controls: the boundaries themselves, and their neighbours inside.
            (1.0, "100"),
            (0.0, "0"),
            (0.994, "99"),
            (0.006, "1"),
            (0.5, "50"),
        ],
    )
    def test_rounded_boundary_is_marked(self, probability, expected):
        assert _display_pct(probability) == expected

    def test_a_printed_100_over_a_probability_below_1_is_still_marked(self):
        """The web client's composition: `rendered` overrides the INTEGER, not
        the rule (`probabilityParts`, UX-P114)."""
        assert _display_pct(0.996, 100) == ">99"
        assert _display_pct(0.004, 0) == "<1"

    def test_CONTROL_a_printed_interior_percent_is_stated_as_printed(self):
        """#2060: a complement's printed percent is derived, never re-rounded."""
        assert _display_pct(0.7049, 71) == "71"


class TestTheUnderdogArticle:
    def test_a_below_one_underdog_reads_a_less_than_one(self):
        assert _underdog_sentence("Valencia", "<1") == "Valencia won as a <1% underdog"

    def test_CONTROL_the_vowel_readings_still_take_an(self):
        assert _underdog_sentence("Valencia", "18") == "Valencia won as an 18% underdog"
        assert _underdog_sentence("Valencia", "44") == "Valencia won as a 44% underdog"
