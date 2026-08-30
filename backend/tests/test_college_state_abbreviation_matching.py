"""Q454 (#TBD): a Kalshi college market named "Ball St." must reach the event
called "Ball State Cardinals".

Kalshi writes every college team's trailing "State" as "St." — "Ball St.",
"Ohio St.", "Boise St.". Nothing on the linking path expanded it, so both gates
that stand between a market and its event failed on the same two characters:

  gate 1  the ILIKE candidate query (`_expand_team_search_terms`) searched only
          "%Ball St.%", which no event row has ever contained, so the query
          returned zero candidates and there was nothing left to score;
  gate 2  the both-teams comparator (`_fuzzy_team_match`) compared
          "ball st." against "ball state cardinals" and said no.

Measured on production 2026-08-30: of 60 linked KXNCAAFGAME markets exactly one
contained "St." — and that one was linked to the WRONG game. 118 of the 258
unlinked ones contained it.

The expansion is position-guarded on purpose. The same two letters mean "Saint"
when they LEAD a name ("St. Louis Cardinals", "St. Francis Fighting Saints"),
and expanding those would invent teams. Only a trailing abbreviation expands.
"""

import pytest

from app.utils.name_normalization import (
    expand_trailing_state_abbrev,
    normalize_team_name_for_matching,
)
from app.utils.prediction_market_matching import (
    _expand_team_search_terms,
    _fuzzy_team_match,
    extract_matchup,
    match_teams_to_event,
)


# ── The abbreviation expander itself ─────────────────────────────────────────

class TestExpandTrailingStateAbbrev:
    """Trailing "St." is State. Leading "St." is Saint. Nothing else moves."""

    @pytest.mark.parametrize("raw,expected", [
        ("Ball St.", "Ball State"),
        ("Ohio St.", "Ohio State"),
        ("Boise St.", "Boise State"),
        ("Michigan St", "Michigan State"),          # some feeds omit the period
        ("Southeast Missouri St.", "Southeast Missouri State"),
        ("Mississippi Valley St.", "Mississippi Valley State"),
    ])
    def test_trailing_abbreviation_expands(self, raw, expected):
        assert expand_trailing_state_abbrev(raw) == expected

    @pytest.mark.parametrize("raw", [
        "St. Louis Cardinals",            # leading — Saint, not State
        "St. Francis (IL) Fighting Saints",
        "St. John's Red Storm",
        "Mount St. Mary's",               # interior — Saint
        "Ball State Cardinals",           # already expanded
        "Stanford Cardinal",
        "TCU Horned Frogs",
        "St.",                            # the whole name; nothing to qualify
        "",
    ])
    def test_leading_interior_and_irrelevant_names_are_untouched(self, raw):
        assert expand_trailing_state_abbrev(raw) == raw

    def test_case_and_diacritics_are_preserved(self):
        # The ILIKE path feeds this straight into a pattern, so it must not
        # strip accents the way normalize_name() does.
        assert expand_trailing_state_abbrev("Querétaro") == "Querétaro"
        assert expand_trailing_state_abbrev("SAN JOSE ST.") == "SAN JOSE State"


class TestNormalizeTeamNameForMatching:
    def test_expands_trailing_state_and_lowercases(self):
        assert normalize_team_name_for_matching("Ball St.") == "ball state"

    def test_interior_abbreviation_expands_too(self):
        # "Youngstown St Penguins" is a real event row: the abbreviation sits
        # INTERIOR. The comparator canonicalises both sides, so it expands here
        # as well — otherwise the market never reaches its own event.
        assert normalize_team_name_for_matching("Youngstown St Penguins") == (
            "youngstown state penguins"
        )

    def test_token_trailing_periods_are_dropped(self):
        assert normalize_team_name_for_matching("Stephen F. Austin") == (
            "stephen f austin"
        )

    def test_leading_saint_is_not_turned_into_state(self):
        assert "state" not in normalize_team_name_for_matching("St. Louis Cardinals")
        assert "state" not in normalize_team_name_for_matching("St. Francis Terriers")

    def test_a_wrong_but_consistent_expansion_still_matches_itself(self):
        # "Mount St. Mary's" is Saint, not State, and the interior rule gets it
        # wrong. That is tolerable precisely because BOTH sides get it wrong the
        # same way — what must never happen is the school failing to match its
        # own event, or colliding with a different one.
        assert _fuzzy_team_match("Mount St. Mary's", "Mount St. Mary's Mountaineers")
        assert not _fuzzy_team_match("Mount St. Mary's", "Michigan State Spartans")

    def test_empty_is_empty(self):
        assert normalize_team_name_for_matching("") == ""


# ── Gate 2: the both-teams comparator ────────────────────────────────────────

class TestFuzzyTeamMatchCollegeState:

    @pytest.mark.parametrize("market_team,event_team", [
        ("Ball St.", "Ball State Cardinals"),
        ("Ohio St.", "Ohio State Buckeyes"),
        ("Boise St.", "Boise State Broncos"),
        ("San Jose St.", "San Jose State Spartans"),
        ("New Mexico St.", "New Mexico State Aggies"),
        ("Texas St.", "Texas State Bobcats"),
        ("Penn St.", "Penn State Nittany Lions"),
        ("Southeast Missouri St.", "Southeast Missouri State Redhawks"),
        ("Youngstown St.", "Youngstown St Penguins"),   # interior, period-only
    ])
    def test_college_state_market_matches_its_event(self, market_team, event_team):
        assert _fuzzy_team_match(market_team, event_team) is True

    @pytest.mark.parametrize("market_team,event_team", [
        # The flagship-vs-directional trap. These are DIFFERENT schools and the
        # expansion must not collapse them.
        ("Ohio St.", "Ohio Bobcats"),
        ("Washington St.", "Washington Huskies"),
        ("Michigan St.", "Michigan Wolverines"),
        ("Oregon St.", "Oregon Ducks"),
        ("Arizona St.", "Arizona Wildcats"),
        ("Iowa St.", "Iowa Hawkeyes"),
        ("Kansas St.", "Kansas Jayhawks"),
        # Same qualifier, different school.
        ("Ball St.", "Ohio State Buckeyes"),
        ("Idaho St.", "Idaho Vandals"),
        # Saint, not State.
        ("St. Louis", "Louisiana State Tigers"),
        ("St. Francis", "San Francisco State Gators"),
    ])
    def test_different_schools_still_do_not_match(self, market_team, event_team):
        assert _fuzzy_team_match(market_team, event_team) is False

    def test_the_wrong_game_bind_is_still_refused(self):
        # Production 2026-08-30: KXNCAAFGAME-26AUG29MORGNCAT ("Morgan St. vs
        # North Carolina A&T") was bound to event 416565, which is North
        # Carolina Tar Heels vs TCU Horned Frogs. Neither side may match after
        # the expansion either — the fix must not launder this bind.
        assert _fuzzy_team_match("Morgan St.", "North Carolina Tar Heels") is False
        assert _fuzzy_team_match("Morgan St.", "TCU Horned Frogs") is False
        assert _fuzzy_team_match("North Carolina A&T", "North Carolina Tar Heels") is False
        assert _fuzzy_team_match("North Carolina A&T", "TCU Horned Frogs") is False


# ── Gate 1: the ILIKE candidate query ────────────────────────────────────────

class TestExpandTeamSearchTermsCollegeState:

    def test_trailing_state_expansion_is_offered_to_the_ilike_query(self):
        terms = _expand_team_search_terms("Ball St.")
        assert "Ball St." in terms, "the original term must survive"
        assert "Ball State" in terms, (
            "without this the ILIKE is %Ball St.%, which matches no event row"
        )

    def test_the_bare_word_state_is_never_offered_as_a_term(self):
        # "%State%" would drag in every state school in the database. The
        # mascot rule reads the ORIGINAL name, where the last word is "St."
        # (3 chars, under the 5-char floor), so it must stay silent.
        for name in ("Ball St.", "Ohio St.", "Boise St."):
            assert "State" not in _expand_team_search_terms(name)

    def test_names_without_the_abbreviation_are_unchanged(self):
        assert _expand_team_search_terms("Clemson") == ["Clemson"]
        assert "State" not in " ".join(_expand_team_search_terms("St. Louis Cardinals"))


# ── End to end through the real matchup parser ───────────────────────────────

class TestNextSaturdaySlate:
    """The games a user is actually looking at, driven through the real parser."""

    @pytest.mark.parametrize("market_name,away,home", [
        ("Ball St. vs Ohio St.", "Ball State Cardinals", "Ohio State Buckeyes"),
        ("Boise St. vs Oregon", "Boise State Broncos", "Oregon Ducks"),
        ("Texas St. vs Texas", "Texas State Bobcats", "Texas Longhorns"),
        ("Marshall vs Penn St.", "Marshall Thundering Herd", "Penn State Nittany Lions"),
        ("Kent St. vs South Carolina", "Kent State Golden Flashes", "South Carolina Gamecocks"),
        ("Washington St. vs Washington", "Washington State Cougars", "Washington Huskies"),
        ("Nicholls St. vs Kansas St.", "Nicholls State Colonels", "Kansas State Wildcats"),
    ])
    def test_the_card_finds_its_teams(self, market_name, away, home):
        matchup = extract_matchup(market_name)
        assert matchup is not None and matchup.team_b, market_name

        a_ok = (
            _fuzzy_team_match(matchup.team_a, home)
            or _fuzzy_team_match(matchup.team_a, away)
        )
        b_ok = (
            _fuzzy_team_match(matchup.team_b, home)
            or _fuzzy_team_match(matchup.team_b, away)
        )
        assert a_ok and b_ok, f"{market_name} still fails the both-teams gate"

        assert match_teams_to_event(matchup, home, away) is not None

    def test_washington_state_is_not_washington(self):
        # Both teams play each other in the Apple Cup, so a collapse here would
        # bind a market to its own opponent.
        matchup = extract_matchup("Washington St. vs Washington")
        resolved = match_teams_to_event(
            matchup, "Washington Huskies", "Washington State Cougars",
        )
        assert resolved is not None
        # "Washington St." is the YES team and it is the AWAY side here.
        assert resolved["yes_is_home"] is False
