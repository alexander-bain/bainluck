"""Tests for the unified team/player/market name normalization module."""

import pytest
from app.utils.name_normalization import (
    clean_slug,
    match_key,
    names_match,
    normalize_name,
    normalize_team_name,
    token_overlap_score,
)


# =============================================================================
# normalize_name tests
# =============================================================================

class TestNormalizeName:
    """Tests for normalize_name()."""

    def test_basic_lowercase(self):
        assert normalize_name("Boston Celtics") == "boston celtics"

    def test_strip_whitespace(self):
        assert normalize_name("  Boston Red Sox  ") == "boston red sox"

    def test_strip_diacritics_acute(self):
        assert normalize_name("Skarsgård") == "skarsgard"

    def test_strip_diacritics_tilde(self):
        assert normalize_name("São Paulo") == "sao paulo"

    def test_strip_diacritics_umlaut(self):
        assert normalize_name("München") == "munchen"

    def test_strip_diacritics_cedilla(self):
        assert normalize_name("Fenerbahçe") == "fenerbahce"

    def test_unify_smart_quotes(self):
        assert normalize_name("Hawai\u2019i") == "hawai'i"

    def test_strip_reserve_suffix_ii(self):
        assert normalize_name("Boston Celtics II") == "boston celtics"

    def test_strip_reserve_suffix_reserves(self):
        assert normalize_name("Manchester United Reserves") == "manchester united"

    def test_strip_reserve_suffix_b(self):
        assert normalize_name("Real Madrid B") == "real madrid"

    def test_strip_reserve_suffix_u23(self):
        assert normalize_name("Liverpool U23") == "liverpool"

    def test_strip_reserve_suffix_youth(self):
        assert normalize_name("Chelsea Youth") == "chelsea"

    def test_strip_reserve_suffix_academy(self):
        assert normalize_name("Arsenal Academy") == "arsenal"

    def test_strip_reserve_suffix_women(self):
        assert normalize_name("Barcelona Women") == "barcelona"

    def test_strip_reserve_suffix_w(self):
        assert normalize_name("Chelsea W") == "chelsea"

    def test_no_strip_non_suffix_b(self):
        """'B' at the start should not be stripped."""
        assert normalize_name("BC Lions") == "bc lions"

    def test_empty_string(self):
        assert normalize_name("") == ""

    def test_all_caps(self):
        assert normalize_name("NEW YORK YANKEES") == "new york yankees"

    def test_strip_reserve_suffix_iii(self):
        assert normalize_name("Team Name III") == "team name"

    def test_strip_reserve_suffix_2(self):
        assert normalize_name("Team Name 2") == "team name"


# =============================================================================
# normalize_team_name tests
# =============================================================================

class TestNormalizeTeamName:
    """Tests for team-specific normalization used by event matching."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("St. Louis Cardinals", "st louis cardinals"),
            ("Oklahoma City Thunder.", "oklahoma city thunder"),
            ("Borussia Dortmund (Res)", "borussia dortmund"),
            ("Borussia Dortmund (W)", "borussia dortmund"),
        ],
    )
    def test_team_source_formatting_noise(self, raw, expected):
        assert normalize_team_name(raw) == expected

    def test_team_apostrophe_preserved_for_athletics_abbreviation(self):
        """A's is a meaningful MLB source abbreviation, not punctuation noise."""
        assert normalize_team_name("A's") == "a's"


# =============================================================================
# match_key tests
# =============================================================================

class TestMatchKey:
    """Tests for player/nominee dedup keys used across market sources."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Luka Dončić", "luka doncic"),
            ("J.J. McCarthy", "jj mccarthy"),
            ("D'Angelo Russell", "dangelo russell"),
            ("D\u2019Angelo Russell", "dangelo russell"),
            ("Shohei Ohtani: 2+ hits", "shohei ohtani"),
        ],
    )
    def test_player_name_keys_strip_source_formatting(self, raw, expected):
        assert match_key(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("The Masters", "masters"),
            ("The Open Championship: Winner", "open championship"),
            ("Best Picture: Anora", "best picture"),
        ],
    )
    def test_market_or_nominee_keys_drop_prefixes_and_suffixes(self, raw, expected):
        assert match_key(raw) == expected


# =============================================================================
# clean_slug tests
# =============================================================================

class TestCleanSlug:
    """Tests for market/tournament slug normalization."""

    def test_strips_presented_by_sponsor_suffix(self):
        assert clean_slug("Valero Texas Open presented by Mastercard") == "valero-texas-open"

    def test_strips_powered_by_sponsor_suffix(self):
        assert clean_slug("NBA Cup powered by Emirates") == "nba-cup"

    def test_market_punctuation_becomes_single_hyphen_boundaries(self):
        assert clean_slug("The Open Championship: Winner") == "the-open-championship-winner"


# =============================================================================
# names_match tests — positive cases
# =============================================================================

class TestNamesMatchPositive:
    """Cases where names_match() should return True."""

    def test_exact_same_string(self):
        assert names_match("Boston Celtics", "Boston Celtics")

    def test_case_insensitive(self):
        assert names_match("boston celtics", "BOSTON CELTICS")

    def test_diacritics_match(self):
        assert names_match("Skarsgård", "Skarsgard")

    def test_suffix_containment_celtics(self):
        """'Celtics' is a suffix of 'Boston Celtics'."""
        assert names_match("Celtics", "Boston Celtics")

    def test_suffix_containment_red_sox(self):
        """'Red Sox' is a suffix of 'Boston Red Sox'."""
        assert names_match("Red Sox", "Boston Red Sox")

    def test_suffix_containment_reversed(self):
        """Order shouldn't matter."""
        assert names_match("Boston Celtics", "Celtics")

    def test_reserve_suffix_stripped(self):
        assert names_match("Boston Celtics II", "Boston Celtics")

    def test_fc_barcelona_vs_barcelona(self):
        """FC Barcelona matches Barcelona — 'FC' is a stopword, 'barcelona'
        overlaps as the only meaningful token. Score = 1.0."""
        assert names_match("FC Barcelona", "Barcelona")

    def test_containment_with_diacritics(self):
        assert names_match("São Paulo FC", "São Paulo")

    def test_same_after_reserve_strip(self):
        assert names_match("Arsenal Reserves", "Arsenal Academy")

    def test_south_carolina_vs_south_carolina_state(self):
        """Token overlap is ~0.67 (>0.5) — these match.
        This is technically a false positive (different teams) but is consistent
        with the existing behavior in both feed.py and espn_sync.py."""
        assert names_match("South Carolina", "South Carolina State")

    def test_la_lakers_vs_los_angeles_lakers(self):
        """City abbreviation expansion: 'LA' -> 'Los Angeles'.
        Token overlap after expansion: {'los', 'angeles', 'lakers'} = 1.0."""
        assert names_match("LA Lakers", "Los Angeles Lakers")

    def test_st_louis_period_variants_match(self):
        assert names_match("St.Louis Cardinals", "St Louis Cardinals")

    def test_city_abbreviation_matches_full_team_name(self):
        assert names_match("NY Knicks", "New York Knicks")
        assert names_match("KC Chiefs", "Kansas City Chiefs")

    def test_womens_suffix_matches_shared_source_name(self):
        assert names_match("Manchester City Women", "Manchester City")


# =============================================================================
# names_match tests — negative cases
# =============================================================================

class TestNamesMatchNegative:
    """Cases where names_match() should return False."""

    def test_air_force_vs_atlanta_falcons(self):
        """Different teams with shared mascot — token overlap ~0.33."""
        assert not names_match("Air Force Falcons", "Atlanta Falcons")

    def test_eastern_kentucky_vs_kentucky(self):
        """Partial location match — should not match."""
        assert not names_match("Eastern Kentucky Colonels", "Kentucky Wildcats")

    def test_empty_string_a(self):
        assert not names_match("", "Boston Celtics")

    def test_empty_string_b(self):
        assert not names_match("Boston Celtics", "")

    def test_both_empty(self):
        assert not names_match("", "")

    def test_completely_different(self):
        assert not names_match("Boston Celtics", "Los Angeles Lakers")

    def test_short_substring_rejected(self):
        """Short substrings (<4 chars) should not match via suffix containment."""
        assert not names_match("New", "New England Patriots")

    def test_new_vs_new_york(self):
        assert not names_match("New", "New York Yankees")

    def test_georgia_southern_vs_south_florida_bulls(self):
        assert not names_match("Georgia Southern Eagles", "South Florida Bulls")


# =============================================================================
# names_match edge cases
# =============================================================================

class TestNamesMatchEdgeCases:
    """Edge cases and documented behaviors."""

    def test_unicode_chinese(self):
        assert normalize_name("北京国安") == "北京国安"
        assert names_match("北京国安", "北京国安")

    def test_unicode_cyrillic(self):
        assert names_match("ЦСКА Москва", "ЦСКА Москва")
        assert names_match("цска москва", "ЦСКА Москва")

    def test_single_word_teams(self):
        assert names_match("Liverpool", "Liverpool")

    def test_reserve_vs_reserve(self):
        """Both with reserve suffix should match after stripping."""
        assert names_match("Arsenal Reserves", "Arsenal II")

    def test_mascot_suffix_match(self):
        """Mascot name (suffix) should match full team name."""
        assert names_match("Yankees", "New York Yankees")

    def test_multi_word_suffix_match(self):
        """Multi-word suffix should match."""
        assert names_match("Red Sox", "Boston Red Sox")

    def test_single_word_location_matches_full_name(self):
        """Single-word location matches full team name at >=0.5 threshold.
        Token overlap: 'boston' vs 'boston celtics' = min(1/1, 1/2) = 0.5.
        This is acceptable because ESPN sync requires BOTH teams to match."""
        assert names_match("Boston", "Boston Celtics")


# =============================================================================
# token_overlap_score tests
# =============================================================================

class TestTokenOverlapScore:
    """Tests for the exposed token_overlap_score() function."""

    def test_identical_names(self):
        assert token_overlap_score("Boston Celtics", "Boston Celtics") == 1.0

    def test_air_force_vs_atlanta_falcons(self):
        score = token_overlap_score("Air Force Falcons", "Atlanta Falcons")
        # air(2), force(5), falcons(7) vs atlanta(7), falcons(7)
        # Overlap: {falcons} = 1. min(1/3, 1/2) = 0.333
        assert score < 0.5

    def test_south_carolina_state(self):
        score = token_overlap_score("South Carolina State", "South Carolina")
        # south(5), carolina(8), state(5) vs south(5), carolina(8)
        # Overlap: {south, carolina} = 2. min(2/3, 2/2) = 0.667
        assert 0.6 < score < 0.7

    def test_empty_returns_zero(self):
        assert token_overlap_score("", "Boston") == 0.0

    def test_stopwords_only(self):
        assert token_overlap_score("FC SC", "AC US") == 0.0

    def test_score_is_float(self):
        score = token_overlap_score("Boston Celtics", "Boston Lakers")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_boston_celtics_vs_boston_lakers(self):
        """Only 'boston' overlaps: min(1/2, 1/2) = 0.5."""
        score = token_overlap_score("Boston Celtics", "Boston Lakers")
        assert score == 0.5

    def test_perfect_overlap_different_stopwords(self):
        """'Barcelona' is the only non-stopword in both."""
        score = token_overlap_score("FC Barcelona", "Barcelona SC")
        assert score == 1.0

    def test_st_dot_expands_to_state(self):
        """'St.' should expand to 'State' for college team matching."""
        score = token_overlap_score("Michigan St.", "Michigan State Spartans")
        # michigan, state vs michigan, state, spartans → min(2/2, 2/3) = 0.67
        assert score >= 0.6

    def test_college_abbreviations(self):
        """College abbreviations: St., Mt., etc."""
        assert token_overlap_score("Utah St.", "Utah State Aggies") >= 0.6
        assert token_overlap_score("Wichita St.", "Wichita State Shockers") >= 0.6
        assert token_overlap_score("Kennesaw St.", "Kennesaw State Owls") >= 0.6

    def test_single_token_name(self):
        """Single-token names like UCLA score 0.5 against 2-token ESPN names."""
        assert token_overlap_score("UCLA", "UCLA Bruins") == 0.5
        assert token_overlap_score("VCU", "VCU Rams") == 0.5
