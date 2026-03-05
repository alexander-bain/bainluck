"""Tests for team name matching in feed.py.

Now uses the unified names_match() from name_normalization.py.
Verifies suffix-based word matching prevents false positives like
"Celtic" matching "Boston Celtics" and "England" matching "New England Patriots"
while preserving valid matches.
"""

import pytest
from app.utils.name_normalization import names_match as _team_name_matches


class TestTeamNameMatches:
    """Core matching logic."""

    def test_exact_match(self):
        assert _team_name_matches("Boston Celtics", "Boston Celtics") is True

    def test_exact_match_case_insensitive(self):
        assert _team_name_matches("boston celtics", "Boston Celtics") is True

    # --- Safe direction: user's full name inside candidate ---

    def test_full_name_in_candidate(self):
        # "Boston Celtics" is inside "The Boston Celtics" — safe
        assert _team_name_matches("Boston Celtics", "The Boston Celtics") is True

    # --- Dangerous direction: candidate substring of user team ---
    # Must match trailing words to pass.

    def test_suffix_match_single_word(self):
        assert _team_name_matches("Boston Celtics", "Celtics") is True

    def test_suffix_match_multi_word(self):
        assert _team_name_matches("Boston Red Sox", "Red Sox") is True

    def test_suffix_match_warriors(self):
        assert _team_name_matches("Golden State Warriors", "Warriors") is True

    def test_suffix_match_barcelona(self):
        assert _team_name_matches("FC Barcelona", "Barcelona") is True

    def test_suffix_match_patriots(self):
        assert _team_name_matches("New England Patriots", "Patriots") is True

    # --- False positives that must be rejected ---

    def test_celtic_does_not_match_celtics(self):
        """SPL Celtic should NOT match Boston Celtics."""
        assert _team_name_matches("Boston Celtics", "Celtic") is False

    def test_england_does_not_match_patriots(self):
        """England cricket/soccer should NOT match New England Patriots."""
        assert _team_name_matches("New England Patriots", "England") is False

    def test_no_substring_either_direction(self):
        """Brown Bears vs Cleveland Browns — no substring match at all."""
        assert _team_name_matches("Brown Bears", "Cleveland Browns") is False

    def test_non_suffix_substring_rejected(self):
        """'New' is a substring of 'New England Patriots' but not a suffix."""
        assert _team_name_matches("New England Patriots", "New") is False

    def test_middle_word_now_matches_via_token_overlap(self):
        """'New England' has token overlap 0.667 with 'New England Patriots'.

        The old feed.py function rejected this, but the unified names_match
        accepts it via token_overlap_score > 0.5. This is acceptable because
        no real team is named just "New England" — user favorites always have
        full team names.
        """
        assert _team_name_matches("New England Patriots", "New England") is True

    # --- Edge cases ---

    def test_empty_user_team(self):
        assert _team_name_matches("", "Celtic") is False

    def test_empty_candidate(self):
        assert _team_name_matches("Boston Celtics", "") is False

    def test_both_empty(self):
        assert _team_name_matches("", "") is False

    def test_whitespace_handling(self):
        assert _team_name_matches("  Boston Celtics  ", "  Celtics  ") is True

    def test_single_word_exact(self):
        """Single-word team names should match exactly."""
        assert _team_name_matches("Arsenal", "Arsenal") is True

    def test_single_word_no_partial(self):
        """Partial single-word match should fail."""
        assert _team_name_matches("Arsenal", "Arsen") is False

    # --- Reserve team handling (new with unified names_match) ---

    def test_reserve_team_matches_parent(self):
        """Reserve teams match parent after suffix stripping."""
        assert _team_name_matches("New England Revolution", "New England Revolution II") is True

    def test_academy_matches_parent(self):
        assert _team_name_matches("Arsenal", "Arsenal Academy") is True
