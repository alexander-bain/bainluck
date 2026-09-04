"""Guard tests for the name-verdict memo (LAT-P225, #3030).

`compute_futures_highlight` used to ask between 13 and 36 regular-expression
questions of the market NAME on every call, and the Discover build re-asked them
about the same names on every rebuild. `_name_verdicts` answers them once and
memoises on the name.

The class of bug a memo introduces is **a key that does not cover everything the
value depends on**. These tests make that argument mechanical rather than
prose-only:

  * every field of `_NameVerdicts` equals a direct search of its own pattern, so
    the memo cannot quietly answer a different question;
  * the memo takes exactly ONE input and it is the name, so a future edit that
    makes a verdict depend on category / status / time / price has to change the
    signature and trip this test;
  * the scorer contains no regex search of its own any more, so a per-call
    pattern cannot creep back in beside the memo;
  * a rename is a different key, so a renamed market can never be served the old
    market's verdict.
"""

import inspect
import re

import pytest

from app.utils import futures_highlights as FH
from app.utils.futures_highlights import (
    _name_verdicts,
    _NameVerdicts,
    compute_futures_highlight,
    is_minor_league_market,
    is_top_tier_soccer_market,
)

# One name per pattern family, so every field is exercised in both polarities.
NAMES = [
    "",
    "AHL Championship Winner",
    "EFL Championship Winner",
    "Premier League Winner",
    "Ligue 2 Winner",
    "Hackney mayoral election winner",
    "US Presidential Election Winner 2028",
    "Oregon Senate election winner",
    "Andalusia election winner",
    "UK general election winner",
    "# of tweets by Trump this week",
    "margin of victory",
    "Coca-Cola 600 winner",
    "Korn Ferry Tour winner",
    "Oscars 2027 Best Picture",
    "#1 song on Billboard Hot 100",
    "Will Russia invade Ukraine",
    "Who will win the Super Bowl",
    "Stanley Cup winner",
    "Will the Lakers advance to the NBA Finals",
    "Taylor Swift wedding",
    "NBA Championship",
    "NFL MVP",
]

# (field name, the module pattern that field is supposed to be reporting)
FIELD_PATTERNS = [
    ("boring", "_BORING_PATTERNS"),
    ("obscure_election", "_OBSCURE_ELECTION_PATTERNS"),
    ("minor_sport_event", "_MINOR_SPORT_EVENT_PATTERNS"),
    ("election_market", "_ELECTION_MARKET_RE"),
    ("major_election", "_MAJOR_ELECTION_RE"),
    ("non_major_election_keyword", "_NON_MAJOR_ELECTION_KEYWORD_RE"),
    ("cultural_gravity_t1", "_CULTURAL_GRAVITY_T1"),
    ("cultural_gravity_t2", "_CULTURAL_GRAVITY_T2"),
    ("sports_postseason_story", "_SPORTS_POSTSEASON_STORY_RE"),
    ("minor_league", "_MINOR_LEAGUE_PATTERNS"),
    ("top_tier_soccer", "_TOP_TIER_SOCCER_RE"),
]


class TestNameVerdictsAnswerTheirOwnPattern:
    @pytest.mark.parametrize("field,pattern_name", FIELD_PATTERNS)
    def test_field_matches_a_direct_search(self, field, pattern_name):
        pattern = getattr(FH, pattern_name)
        for name in NAMES:
            assert getattr(_name_verdicts(name), field) == bool(
                pattern.search(name)
            ), f"{field} disagrees with {pattern_name} on {name!r}"

    def test_compelling_hits_is_the_full_count(self):
        for name in NAMES:
            expected = sum(1 for p in FH._COMPELLING_PATTERNS if p.search(name))
            assert _name_verdicts(name).compelling_hits == expected

    def test_every_verdict_field_is_covered_by_a_test(self):
        """A new verdict field must arrive with its own equivalence check."""
        covered = {f for f, _ in FIELD_PATTERNS} | {"compelling_hits"}
        assert set(_NameVerdicts._fields) == covered

    def test_helpers_read_the_memo_and_still_agree_with_their_patterns(self):
        for name in NAMES:
            assert is_minor_league_market(name) == bool(
                FH._MINOR_LEAGUE_PATTERNS.search(name)
            )
            assert is_top_tier_soccer_market(name) == bool(
                FH._TOP_TIER_SOCCER_RE.search(name)
            )
        # The None tolerance of is_top_tier_soccer_market is preserved.
        assert is_top_tier_soccer_market(None) is False


class TestTheKeyCoversTheInput:
    def test_the_memo_takes_exactly_one_input_and_it_is_the_name(self):
        """The staleness argument, mechanised.

        The memo is safe because its value depends on the name and nothing else.
        If a verdict ever needs the category, the status, the price or the clock,
        that input has to join the key — and this test is what forces the
        conversation instead of letting a stale answer ship.
        """
        params = list(inspect.signature(_name_verdicts.__wrapped__).parameters)
        assert params == ["market_name"]

    def test_a_rename_is_a_different_key(self):
        minor = "AHL Championship Winner"
        major = "NBA Championship Winner"
        assert _name_verdicts(minor).minor_league is True
        assert _name_verdicts(major).minor_league is False
        # ...and asking again after the other name has been cached does not
        # bleed one verdict into the other.
        assert _name_verdicts(minor).minor_league is True

    def test_patterns_are_module_constants_compiled_once(self):
        """No pattern is rebuilt per call, so no verdict can drift mid-process."""
        for _, pattern_name in FIELD_PATTERNS:
            assert isinstance(getattr(FH, pattern_name), re.Pattern)
        assert all(isinstance(p, re.Pattern) for p in FH._COMPELLING_PATTERNS)


class TestTheScorerAsksNothingItself:
    def test_compute_futures_highlight_contains_no_regex_search(self):
        """Every name question goes through the memo — no strays beside it."""
        src = inspect.getsource(compute_futures_highlight)
        assert ".search(" not in src
        assert "re.search(" not in src
        assert "re.match(" not in src
        assert "re.findall(" not in src

    def test_repeat_calls_on_one_name_ask_nothing_new(self):
        _name_verdicts.cache_clear()
        name = "Who will win the Super Bowl"
        compute_futures_highlight(market_name=name, sport_category="football")
        after_first = _name_verdicts.cache_info()
        for _ in range(20):
            compute_futures_highlight(market_name=name, sport_category="football")
        after_many = _name_verdicts.cache_info()
        assert after_many.misses == after_first.misses
        assert after_many.hits > after_first.hits

    def test_one_market_costs_at_most_one_miss(self):
        _name_verdicts.cache_clear()
        for name in NAMES:
            compute_futures_highlight(market_name=name, sport_category="politics")
            compute_futures_highlight(market_name=name, sport_category="soccer")
        assert _name_verdicts.cache_info().misses == len(set(NAMES))

    def test_the_cache_is_bounded(self):
        assert _name_verdicts.cache_info().maxsize is not None
