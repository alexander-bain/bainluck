"""#6949 — R8 ("#1 yes, #2 no") must know the `<ordinal> Place` title form.

Page one on 2026-09-18 opened with 1st, 2nd and 3rd place in one Brazilian
election. The two runner-up rows (`futures_markets` 129271 / 129272) were served
at ranks 1 and 3 with `quality_class == "compelling"` (+12) because
`_RUNNER_UP_RE` knew `second place` spelled in words and `finish 2nd`, but not
the bare `2nd Place` / `3rd Place` heading both venues actually write.

Measured on production the same morning, over the 228 open markets whose name
carries an ordinal beside "place": the old pattern claimed 3, the new one claims
174, none of the 54 rows naming 1st/first place is claimed, and nothing the old
pattern claimed is lost. The specimens below are real names from that census.

The negative half is the load-bearing half: R8 exists to keep the WINNER market
eligible, so a pattern that swept up "1st Place" would be worse than the defect.
"""

import pytest

from app.utils.feed_market_quality import (
    _is_runner_up_rank,
    classify_market_quality,
    quality_score_adjustment,
)

# Production names, 2026-09-18 census. Non-#1 ranking markets, every one.
RUNNER_UP_NAMES = [
    "Brazil Presidential Election First Round: 2nd Place",
    "Brazil Presidential Election First Round: 3rd Place",
    "Big Brother Season 28 · 3rd place ",
    "Victoria parliamentary election: 3rd place?",
    "Sweden Riksdag election: 7th place (vote share)",
    "Berlin State Election: 4th Place",
    "Premier League: 17th Place (Relegation Survivor) 2026-27",
    "Serie A: 3rd Place Finish 2026-27",
    "Quebec General Election: Third Place",
    "Dancing with the Stars Season 35 · 2nd Place",
    "2nd place in the NJ-11 special election Democratic primary?",
    "Brazil presidential election: 5th place (1st round)",
]

# Winner markets from the same census — R8 must leave every one of them alone.
WINNER_NAMES = [
    "Brazil Presidential Election First Round: 1st Place in Tocantins",
    "Brazil Presidential Election First Round: 1st Place in Minas Gerais",
    "Paraná Senate Election: 1st Place",
    "São Paulo Senate Election: 1st Place",
    "Bahia Senate Election: 1st Place",
]


class TestTheOrdinalPlaceFormIsRunnerUp:
    @pytest.mark.parametrize("name", RUNNER_UP_NAMES)
    def test_non_first_ordinal_place_is_a_runner_up_rank(self, name):
        assert _is_runner_up_rank(name), name

    @pytest.mark.parametrize(
        "name",
        # The Sweden row is held out on purpose: it is a vote-SHARE market, which
        # an earlier branch of the same chain suppresses outright, so asserting
        # `low_quality` on it would assert another rule's answer.
        [n for n in RUNNER_UP_NAMES if "vote share" not in n],
    )
    def test_it_reaches_the_class_and_the_penalty_not_just_the_predicate(self, name):
        # The predicate is not the ship: R8 pays out through `quality_class`,
        # and a `compelling` row would carry +12 instead of the -35 intended.
        quality = classify_market_quality(market_name=name, sport_category="politics")
        assert quality.quality_class == "low_quality", name
        assert "runner_up_rank" in quality.reasons, name
        assert quality_score_adjustment(quality) <= -35, name

    def test_a_stronger_earlier_rule_still_wins_where_one_applies(self):
        # `7th place (vote share)` is both a runner-up rank and a vote-percent
        # ladder; the vote-percent branch is earlier and harder, and #6949 does
        # not move it. Recorded so the held-out specimen above is not a gap.
        quality = classify_market_quality(
            market_name="Sweden Riksdag election: 7th place (vote share)",
            sport_category="politics",
        )
        assert quality.quality_class == "suppress"
        assert "runner_up_rank" in quality.reasons


class TestTheWinnerMarketStaysEligible:
    @pytest.mark.parametrize("name", WINNER_NAMES)
    def test_first_place_is_never_claimed(self, name):
        assert not _is_runner_up_rank(name), name

    @pytest.mark.parametrize("name", WINNER_NAMES)
    def test_first_place_is_not_downranked_by_r8(self, name):
        quality = classify_market_quality(market_name=name, sport_category="politics")
        assert "runner_up_rank" not in quality.reasons, name

    def test_first_round_in_a_title_is_not_first_place(self):
        # The exemption keys on "first PLACE", not on the word "first" — every
        # Brazilian specimen above contains "First Round", and exempting those
        # would make the whole fix inert.
        assert _is_runner_up_rank("Brazil Presidential Election First Round: 2nd Place")

    def test_a_top_two_market_is_not_a_runner_up(self):
        # "1st or 2nd place" includes winning, so it is not the thing R8 demotes.
        assert not _is_runner_up_rank("Will X finish 1st or 2nd place?")


class TestItDoesNotClaimTheWordPlaceOnItsOwn:
    @pytest.mark.parametrize(
        "name",
        [
            "Will the debate take place before October?",
            "Will the summit take place in Geneva?",
            "Which party will win the Senate in 2026?",
            "Will Drake have the #1 song on Billboard?",
        ],
    )
    def test_place_without_an_ordinal_is_untouched(self, name):
        assert not _is_runner_up_rank(name), name


class TestTheOldSpelledFormsStillFire:
    """Nothing the pre-#6949 pattern claimed may be lost."""

    @pytest.mark.parametrize(
        "name",
        [
            "Will this song be #2 on the Hot 100?",
            "Will the album finish second this week?",
            "Runner-up at the box office?",
            "Peru presidential election: first round second place?",
            "Denmark general election: second place",
        ],
    )
    def test_still_claimed(self, name):
        assert _is_runner_up_rank(name), name
