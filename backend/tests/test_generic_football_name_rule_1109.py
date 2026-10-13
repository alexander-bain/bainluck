"""#1109 — a generic phrase is not football evidence on an unmapped Kalshi ticker.

"Coach of the year", "wins total", "playoff spot", "draft pick" and "first
pick" answer ``football`` inside ``categorize_by_rules`` because the NFL is the
commonest case. When the ticker is unmapped and the venue published no sport
tag, that phrase is the only evidence, and #1888's coalesce upsert keeps the
first non-``other`` label: a Hawks playoff market stamped football stays
football on the Accuracy page and everywhere it is badged.

Each case below goes through the real ``_categorize_kalshi_market`` cascade.
"""

import re

import pytest

from app.tasks.kalshi import _categorize_kalshi_market
from app.utils.futures_categorization import (
    GENERIC_FOOTBALL_DEFAULT_SOURCES,
    SPORT_PATTERNS,
    categorize_by_rules,
    football_evidence_is_generic_only,
)
from app.utils.sport_keys import get_sport_key_from_ticker

# A ticker no map knows: the name and the venue's words are all that is left.
UNMAPPED = "KXZZUNMAPPED-26OCT13"

GENERIC_FOOTBALL_SHAPED_NAMES = [
    "Will the Hawks clinch a playoff spot?",
    "Will the Vipers make a playoff berth?",
    "Coach of the Year",
    "Who will win Head Coach of the Year?",
    "Most wins total over 50.5",
    "Draft pick #1 overall",
    "Who will be the first pick?",
    "Will he be the 1st pick in the draft class?",
]


def test_the_unmapped_ticker_really_is_unmapped():
    assert get_sport_key_from_ticker(UNMAPPED) is None


@pytest.mark.parametrize("name", GENERIC_FOOTBALL_SHAPED_NAMES)
def test_the_rules_still_say_football_so_the_kalshi_gate_is_load_bearing(name):
    # If a rule stops answering football the Kalshi assertions below pass for
    # the wrong reason; this pins the precondition.
    assert categorize_by_rules(name) == "football"
    assert football_evidence_is_generic_only(name)


@pytest.mark.parametrize("name", GENERIC_FOOTBALL_SHAPED_NAMES)
@pytest.mark.parametrize("kalshi_category", [None, "Sports"])
def test_generic_name_on_unmapped_ticker_is_not_football(name, kalshi_category):
    assert _categorize_kalshi_market(name, kalshi_category, UNMAPPED) == "other"


@pytest.mark.parametrize("name", GENERIC_FOOTBALL_SHAPED_NAMES)
def test_the_venue_saying_football_still_makes_it_football(name):
    # Football authority from the venue, not the phrase: category or tag.
    assert _categorize_kalshi_market(name, "Football", UNMAPPED) == "football"
    assert (
        _categorize_kalshi_market(name, "Sports", UNMAPPED, series_tag="Football")
        == "football"
    )


@pytest.mark.parametrize(
    "name",
    [
        "Will the Chiefs clinch a playoff spot?",
        "NFL Coach of the Year",
        "Who will be the first pick in the NFL draft?",
        "College football playoff berth: Ohio State?",
        "Who will lead the league in passing yards?",
        "Heisman winner",
        "Sugar Bowl winner",
    ],
)
def test_a_specific_football_word_keeps_football(name):
    assert not football_evidence_is_generic_only(name)
    assert _categorize_kalshi_market(name, "Sports", UNMAPPED) == "football"


@pytest.mark.parametrize("ticker", ["KXNFLWINS-26KC", "KXNCAAFPLAYOFF-26"])
def test_mapped_football_tickers_are_untouched(ticker):
    # NFL / NCAAF positives come from the ticker map, above the name rules.
    assert get_sport_key_from_ticker(ticker) is not None
    assert _categorize_kalshi_market("Most wins total over 10.5", "Sports", ticker) == "football"


def test_cfl_keeps_football_through_the_venue_tag():
    # CFL has no ticker mapping; Kalshi tags the series `Football` (#5637).
    ticker = "KXCFLTOTAL-26OCT13HAMTOR"
    assert get_sport_key_from_ticker(ticker) is None
    assert (
        _categorize_kalshi_market(
            "Will the Tiger-Cats clinch a playoff spot?", "Sports", ticker, series_tag="Football"
        )
        == "football"
    )


def test_another_sports_generic_name_is_not_football():
    # The leak's other direction: an NBA name on an unmapped ticker.
    assert (
        _categorize_kalshi_market("Will the Hawks make a playoff berth?", "Sports", UNMAPPED)
        != "football"
    )
    # ...and a league word next to the phrase answers through the rules.
    assert (
        _categorize_kalshi_market("NBA draft lottery: first pick?", "Sports", UNMAPPED)
        == "basketball"
    )


class TestIssueControls:
    """The issue's named families, through the same cascade."""

    @pytest.mark.parametrize(
        "ticker",
        ["KXITFMATCH-26JUL19VELKIM", "KXITFWMATCH-26JUL19VELKIM",
         "KXITFDOUBLES-26JUL19VELKIM", "KXITFWDOUBLES-26JUL19VELKIM"],
    )
    @pytest.mark.parametrize("name", ["Velcz vs Kimhi", "Most wins total over 1.5"])
    def test_itf_is_tennis_even_under_a_football_shaped_name(self, ticker, name):
        assert _categorize_kalshi_market(name, "Sports", ticker) == "tennis"

    def test_otd_basketball_is_basketball_when_the_venue_tags_it(self):
        # KXOTDBASKETBALL is unmapped; its sport comes from the venue's tag.
        ticker = "KXOTDBASKETBALL-26JUL19"
        assert get_sport_key_from_ticker(ticker) is None
        for name in ("Lakers vs Celtics", "Most wins total over 50.5"):
            assert (
                _categorize_kalshi_market(name, "Sports", ticker, series_tag="Basketball")
                == "basketball"
            )

    def test_otd_basketball_without_a_tag_is_never_football(self):
        ticker = "KXOTDBASKETBALL-26JUL19"
        for name in GENERIC_FOOTBALL_SHAPED_NAMES:
            assert _categorize_kalshi_market(name, "Sports", ticker) != "football"


def test_every_generic_source_is_still_a_football_rule():
    # Keyed by pattern source: an edit to one of these rules must redden here,
    # not silently fall out of the set and start answering football again.
    football_sources = {p.pattern for p, c in SPORT_PATTERNS if c == "football"}
    missing = GENERIC_FOOTBALL_DEFAULT_SOURCES - football_sources
    assert not missing, missing
    for source in GENERIC_FOOTBALL_DEFAULT_SOURCES:
        re.compile(source)
