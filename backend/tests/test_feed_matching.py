"""Tests for _team_name_matches() in feed.py.

Verifies suffix-based word matching prevents false positives like
"Celtic" matching "Boston Celtics" and "England" matching "New England Patriots"
while preserving valid matches.

The function is duplicated here (it's a pure function with zero dependencies)
to avoid importing the full routes package which requires Python 3.10+ and
many backend dependencies. Any changes to _team_name_matches in feed.py must
be mirrored here.
"""

import pytest


def _team_name_matches(user_team: str, candidate: str) -> bool:
    """Check if a user's followed team name matches a candidate team name."""
    user_lower = user_team.lower().strip()
    cand_lower = candidate.lower().strip()
    if not user_lower or not cand_lower:
        return False
    if user_lower == cand_lower:
        return True
    # user team name appears in candidate (safe — full name is specific)
    if user_lower in cand_lower:
        return True
    # candidate appears in user team (dangerous — require suffix word match)
    if cand_lower in user_lower:
        user_words = user_lower.split()
        cand_words = cand_lower.split()
        if len(cand_words) <= len(user_words):
            if user_words[-len(cand_words):] == cand_words:
                return True
    return False


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

    def test_middle_word_rejected(self):
        """'England' is a middle word, not a suffix."""
        assert _team_name_matches("New England Patriots", "New England") is False

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
