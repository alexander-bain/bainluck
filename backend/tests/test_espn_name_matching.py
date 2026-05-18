"""Tests for ESPN team name matching logic.

Tests the espn_names_match module-level function which verifies
that our event team names match ESPN team data during live sync.
"""

from dataclasses import dataclass
from typing import Optional

import pytest

from app.tasks.espn_sync import espn_names_match


@dataclass
class MockESPNTeam:
    display_name: str
    short_name: str = ""
    name: str = ""
    location: str = ""


class TestESPNNamesMatch:
    """Test ESPN name matching with various name formats."""

    def test_exact_match(self):
        team = MockESPNTeam("Boston Celtics", "BOS", "Celtics", "Boston")
        assert espn_names_match(["Boston Celtics"], team)

    def test_la_abbreviation_expansion(self):
        """'LA Clippers' should match 'Los Angeles Clippers' via abbreviation expansion."""
        team = MockESPNTeam("LA Clippers", "LAC", "Clippers", "LA")
        assert espn_names_match(["Los Angeles Clippers"], team)

    def test_short_name_match(self):
        """Short name like 'Clippers' should match full name."""
        team = MockESPNTeam("LA Clippers", "LAC", "Clippers", "LA")
        assert espn_names_match(["Los Angeles Clippers"], team)

    def test_multiple_our_names(self):
        """Should match against any of our name variations."""
        team = MockESPNTeam("Golden State Warriors", "GS", "Warriors", "Golden State")
        assert espn_names_match(["GSW", "Golden State Warriors"], team)

    def test_no_match(self):
        team = MockESPNTeam("Miami Heat", "MIA", "Heat", "Miami")
        assert not espn_names_match(["Boston Celtics"], team)

    def test_our_names_is_list_not_string(self):
        """Ensure our_names must be a list — prevents the TypeError regression."""
        team = MockESPNTeam("Boston Celtics", "BOS", "Celtics", "Boston")
        # This should work with a list
        assert espn_names_match(["Boston Celtics"], team)

    def test_college_teams(self):
        """College team names should match."""
        team = MockESPNTeam("Duke Blue Devils", "DUKE", "Blue Devils", "Duke")
        assert espn_names_match(["Duke Blue Devils"], team)

    def test_ny_abbreviation(self):
        team = MockESPNTeam("NY Knicks", "NYK", "Knicks", "New York")
        assert espn_names_match(["New York Knicks"], team)

    def test_empty_our_names(self):
        team = MockESPNTeam("Boston Celtics", "BOS", "Celtics", "Boston")
        assert not espn_names_match([], team)

    def test_none_in_espn_team_fields(self):
        """Handle None fields in ESPN team data."""
        team = MockESPNTeam("Boston Celtics", "", "", "")
        assert espn_names_match(["Boston Celtics"], team)

    @pytest.mark.parametrize(
        ("our_names", "team"),
        [
            (
                ["Montreal Canadiens"],
                MockESPNTeam("Montréal Canadiens", "MTL", "Canadiens", "Montréal"),
            ),
            (
                ["St Louis Cardinals"],
                MockESPNTeam("St. Louis Cardinals", "STL", "Cardinals", "St. Louis"),
            ),
            (
                ["Sao Paulo"],
                MockESPNTeam("São Paulo FC", "", "São Paulo", "São Paulo"),
            ),
        ],
    )
    def test_punctuation_and_diacritics_normalized(self, our_names, team):
        """ESPN accents and punctuation should not break legitimate team matches."""
        assert espn_names_match(our_names, team)
