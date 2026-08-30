"""Q452 (#2320): "Ohio St." and "Ohio State Buckeyes" are the same team.

Kalshi writes college team names with the ``St.`` abbreviation ("Ohio St.",
"Ball St.", "Boise St."); our events store the expanded form ("Ohio State
Buckeyes"). The canonical normalizer in ``app/utils/name_normalization.py``
has known this since ``_COLLEGE_ABBREVIATIONS`` was added — ``names_match(
"Ohio St.", "Ohio State Buckeyes")`` is already True — but the prediction-market
matcher never adopted the rule, so it fails the same pair twice:

1. ``_expand_team_search_terms`` emits only ``%Ohio St.%``, which is not a
   substring of "Ohio State Buckeyes", so the candidate fetch in
   ``_find_matching_event`` returns ZERO rows and the event is never seen.
2. ``_fuzzy_team_match("Ball St.", "Ball State Cardinals")`` is False, so even
   when the *other* team pulls the event into the candidate set, the
   both-teams gate in ``_score_candidates`` drops it.

Measured on production 2026-08-30: 115 of 161 upcoming college-football events
carried zero Kalshi markets, and 410 unlinked open Kalshi markets with a
forward resolution date carry a ``St.`` name.

The rule is positional, which is the half the existing ``_COLLEGE_ABBREVIATIONS``
gets wrong: a LEADING ``St.`` is "Saint" ("St. Louis", "St. John's"), a
non-leading one is "State". Expanding it unconditionally makes
``names_match("St. Louis", "Louisiana State")`` return True, which it does today.
"""

import pytest

from app.utils.name_normalization import (
    expand_abbreviations,
    names_match,
)
from app.utils.prediction_market_matching import (
    _expand_team_search_terms,
    _fuzzy_team_match,
    extract_matchup_with_ticker_fallback,
    match_teams_to_event,
)


def _ilike_hits(term_owner: str, event_team: str) -> bool:
    """Does any search term this matcher would emit reach ``event_team``?

    Mirrors ``_find_matching_event``'s ``Event.home_team_name.ilike('%term%')``
    — a substring test, case-insensitive. This is the candidate FETCH, which is
    the half a fuzzy-match fix alone does not repair.
    """
    return any(
        t.lower() in event_team.lower()
        for t in _expand_team_search_terms(term_owner)
    )


# ── The positional rule itself ────────────────────────────────────────────

class TestPositionalStateAbbreviation:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Ohio St.", "ohio state"),
            ("Ball St.", "ball state"),
            ("Michigan St.", "michigan state"),
            ("Boise St", "boise state"),          # some sources omit the period
        ],
    )
    def test_trailing_st_is_state(self, raw, expected):
        assert expand_abbreviations(raw) == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("St. Louis Cardinals", "saint louis cardinals"),
            ("St. John's", "saint john's"),
            ("St. Francis", "saint francis"),
            # The one MEDIAL specimen in the corpus, and it is Saint — which is
            # why the rule keys on "is it the last token", not "is it the first".
            ("Mount St. Mary's", "mount saint mary's"),
        ],
    )
    def test_non_trailing_st_is_saint_not_state(self, raw, expected):
        """A ``St.`` that is not the final token is Saint. Expanding it to
        "state" is what makes ``names_match('St. Louis', 'Louisiana State')``
        true today.

        Measured over the 410 unlinked Kalshi markets carrying a ``St.`` name
        (production, 2026-08-30): 57 distinct team names have it as the FINAL
        token and every one is State; 13 have it leading and every one is
        Saint; exactly one is medial — "Mount St. Mary's" — and it is Saint.
        """
        assert expand_abbreviations(raw) == expected

    def test_st_louis_no_longer_collides_with_louisiana_state(self):
        """The regression the unconditional expansion caused, stated as a test.

        "St. Louis" -> "state louis" and "Louisiana State" -> "louisiana state"
        share the token "state", which is exactly the 0.50 token-overlap
        threshold, so the canonical matcher declared them the same team.
        """
        assert not names_match("St. Louis", "Louisiana State")

    def test_st_louis_still_matches_itself(self):
        """Must-not-regress: the Saint reading still matches its own family."""
        assert names_match("St. Louis", "St. Louis Cardinals")
        assert names_match("St. Louis Cardinals", "St. Louis Cardinals")


# ── Half 1: the candidate FETCH reaches the event ─────────────────────────

class TestSearchTermsReachTheEvent:
    @pytest.mark.parametrize(
        "market_team,event_team",
        [
            ("Ohio St.", "Ohio State Buckeyes"),
            ("Ball St.", "Ball State Cardinals"),
            ("Boise St.", "Boise State Broncos"),
            ("Michigan St.", "Michigan State Spartans"),
            ("Fresno St.", "Fresno State Bulldogs"),
            ("San Jose St.", "San Jose State Spartans"),
        ],
    )
    def test_expanded_term_is_emitted(self, market_team, event_team):
        """RED before the fix: the only term is '%Ohio St.%', which is not a
        substring of 'Ohio State Buckeyes', so the SQL returns no candidates."""
        assert _ilike_hits(market_team, event_team), (
            f"no search term from {market_team!r} reaches {event_team!r}; "
            f"terms were {_expand_team_search_terms(market_team)!r}"
        )

    def test_original_term_is_still_emitted(self):
        """Additive, not a replacement — the un-expanded form must survive so
        sources that already write "Ohio State" keep matching."""
        assert "Ohio St." in _expand_team_search_terms("Ohio St.")

    def test_leading_saint_is_not_expanded_to_state(self):
        assert not _ilike_hits("St. Louis", "Louisiana State Tigers")


# ── Half 2: the both-teams gate in _score_candidates ──────────────────────

class TestFuzzyMatchAcceptsTheAbbreviation:
    @pytest.mark.parametrize(
        "market_team,event_team",
        [
            ("Ohio St.", "Ohio State Buckeyes"),
            ("Ball St.", "Ball State Cardinals"),
            ("Boise St.", "Boise State Broncos"),
            ("Michigan St.", "Michigan State Spartans"),
            ("Sacramento St.", "Sacramento State Hornets"),
            ("North Dakota St.", "North Dakota State Bison"),
        ],
    )
    def test_st_matches_state(self, market_team, event_team):
        assert _fuzzy_team_match(market_team, event_team)

    @pytest.mark.parametrize(
        "market_team,event_team",
        [
            # Must-not-regress: the expansion must not invent a cross-team match.
            ("Ohio St.", "Ohio Bobcats"),
            ("Michigan St.", "Michigan Wolverines"),
            ("Washington St.", "Washington Huskies"),
            ("Ball St.", "Ohio State Buckeyes"),
            ("Boise St.", "Oregon Ducks"),
            ("St. Louis", "Louisiana State Tigers"),
        ],
    )
    def test_expansion_does_not_invent_a_match(self, market_team, event_team):
        assert not _fuzzy_team_match(market_team, event_team)

    def test_pre_existing_matches_are_untouched(self):
        """The new stage is additive — every pair that matched before still does."""
        for a, b in [
            ("Boston Celtics", "Boston Celtics"),
            ("Celtics", "Boston Celtics"),
            ("Purdue", "Purdue Boilermakers"),
            ("Lakers", "Los Angeles Lakers"),
        ]:
            assert _fuzzy_team_match(a, b)
        for a, b in [
            ("LA", "Los Angeles Lakers"),
            ("Warriors", "Boston Celtics"),
            ("Nets", "Boston Celtics"),
        ]:
            assert not _fuzzy_team_match(a, b)


# ── The end-to-end shape: the market lands on the right side ──────────────

class TestSideAssignment:
    @pytest.mark.parametrize(
        "ext,name,home,away,expect_yes_is_home",
        [
            # "Ball St. vs Ohio St." — neither side resolves today, so the
            # market cannot link at all.
            ("KXNCAAFGAME-26SEP05BALLOSU", "Ball St. vs Ohio St.",
             "Ohio State Buckeyes", "Ball State Cardinals", False),
            ("KXNCAAFGAME-26SEP05BSUORE", "Boise St. vs Oregon",
             "Oregon Ducks", "Boise State Broncos", False),
            ("KXNCAAFGAME-26SEP04TOLMSU", "Toledo vs Michigan St.",
             "Michigan State Spartans", "Toledo Rockets", False),
        ],
    )
    def test_yes_side_resolves_to_the_named_team(
        self, ext, name, home, away, expect_yes_is_home
    ):
        matchup = extract_matchup_with_ticker_fallback(name, external_id=ext)
        result = match_teams_to_event(matchup, home, away, external_id=ext)
        assert result is not None, f"{name!r} still resolves to no side"
        assert result["yes_is_home"] is expect_yes_is_home

    def test_same_state_rivalry_picks_one_side_not_both(self):
        """The sharpest case: both teams share a word with both event rows.

        "Washington St. vs Washington" against "Washington Huskies vs
        Washington State Cougars" — the bare "Washington" is a substring of
        BOTH event names. The expansion is what makes "Washington St."
        resolve to exactly one of them, so the Yes side is decidable.
        """
        ext = "KXNCAAFGAME-26SEP06WSUWASH"
        matchup = extract_matchup_with_ticker_fallback(
            "Washington St. vs Washington", external_id=ext
        )
        result = match_teams_to_event(
            matchup, "Washington Huskies", "Washington State Cougars",
            external_id=ext,
        )
        assert result is not None
        # Yes team is "Washington St." = the Cougars = the AWAY row.
        assert result["yes_is_home"] is False
