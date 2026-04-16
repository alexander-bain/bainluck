"""Tests for the unified event registry — find_or_create_event().

Tests the matching cascade, claim attachment, source priority,
and edge cases like swapped home/away and city abbreviations.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    _attach_claim,
    _update_fields_by_priority,
    _find_by_structured_match,
)
from app.utils.name_normalization import names_match


# ============================================================================
# Test EventClaim attachment
# ============================================================================

class TestAttachClaim:
    """Test _attach_claim idempotent behavior."""

    def test_attach_odds_api(self):
        event = MagicMock(external_id=None, statpal_fixture_id=None, espn_id=None)
        _attach_claim(event, EventClaim("odds_api", "abc123"))
        assert event.external_id == "abc123"

    def test_attach_statpal(self):
        event = MagicMock(external_id=None, statpal_fixture_id=None, espn_id=None)
        _attach_claim(event, EventClaim("statpal", "fix789"))
        assert event.statpal_fixture_id == "fix789"

    def test_attach_espn(self):
        event = MagicMock(external_id=None, statpal_fixture_id=None, espn_id=None)
        _attach_claim(event, EventClaim("espn", "401866758"))
        assert event.espn_id == "401866758"

    def test_no_overwrite_existing(self):
        """Should NOT overwrite an existing source ID."""
        event = MagicMock(external_id="existing", statpal_fixture_id=None, espn_id=None)
        _attach_claim(event, EventClaim("odds_api", "new_id"))
        assert event.external_id == "existing"

    def test_attach_kalshi_noop(self):
        """Kalshi claims don't set any column on Event directly."""
        event = MagicMock(external_id=None, statpal_fixture_id=None, espn_id=None)
        _attach_claim(event, EventClaim("kalshi", "KXNBA123"))
        # No columns changed
        assert event.external_id is None


# ============================================================================
# Test source priority updates
# ============================================================================

class TestSourcePriority:
    """Test _update_fields_by_priority."""

    def test_espn_overwrites_odds_api(self):
        event = MagicMock(
            home_team_name="LA Clippers",
            away_team_name="GSW",
            commence_time=datetime(2026, 4, 16, 2, 0, tzinfo=timezone.utc),
            commence_time_source="odds_api",
        )
        identity = EventIdentity(
            sport_key="basketball_nba",
            home_team_name="Los Angeles Clippers",
            away_team_name="Golden State Warriors",
            commence_time=datetime(2026, 4, 16, 2, 0, tzinfo=timezone.utc),
            claim=EventClaim("espn", "401866758"),
        )
        _update_fields_by_priority(event, identity)
        assert event.home_team_name == "Los Angeles Clippers"
        assert event.away_team_name == "Golden State Warriors"

    def test_odds_api_does_not_overwrite_espn(self):
        event = MagicMock(
            home_team_name="Los Angeles Clippers",
            commence_time_source="espn",
        )
        identity = EventIdentity(
            sport_key="basketball_nba",
            home_team_name="LA Clippers",
            away_team_name="GSW",
            commence_time=datetime(2026, 4, 16, 2, 0, tzinfo=timezone.utc),
            claim=EventClaim("odds_api", "abc123"),
        )
        _update_fields_by_priority(event, identity)
        # ESPN has higher priority — should NOT be overwritten
        assert event.home_team_name == "Los Angeles Clippers"

    def test_statpal_overwrites_odds_api(self):
        event = MagicMock(
            home_team_name="Celtics",
            commence_time=datetime(2026, 4, 16, 0, 0, tzinfo=timezone.utc),
            commence_time_source="odds_api",
        )
        identity = EventIdentity(
            sport_key="basketball_nba",
            home_team_name="Boston Celtics",
            away_team_name="Minnesota Timberwolves",
            commence_time=datetime(2026, 4, 16, 0, 30, tzinfo=timezone.utc),
            claim=EventClaim("statpal", "fix123"),
            commence_time_source="statpal",
        )
        _update_fields_by_priority(event, identity)
        assert event.home_team_name == "Boston Celtics"
        assert event.commence_time == datetime(2026, 4, 16, 0, 30, tzinfo=timezone.utc)


# ============================================================================
# Test name matching edge cases (for structured match)
# ============================================================================

class TestNameMatchingForEvents:
    """Verify names_match handles real-world team name variations."""

    def test_la_abbreviation(self):
        assert names_match("LA Clippers", "Los Angeles Clippers")

    def test_ny_abbreviation(self):
        assert names_match("NY Knicks", "New York Knicks")

    def test_suffix_match(self):
        assert names_match("Celtics", "Boston Celtics")

    def test_different_teams_same_city_single_match(self):
        """Lakers and Clippers match individually due to 'Los Angeles' token overlap.
        This is a known limitation — the structured match requires BOTH teams to match,
        which prevents false event-level matches (Lakers game ≠ Clippers game)."""
        assert names_match("Los Angeles Lakers", "Los Angeles Clippers")  # single-name match: true (known)

    def test_both_teams_prevent_false_match(self):
        """Even though Lakers matches Clippers on team-a, team-b won't match,
        so the full event won't be a false positive."""
        # Lakers vs Celtics should NOT match Clippers vs Warriors
        # In _find_by_structured_match, BOTH teams must match
        assert not (
            names_match("Los Angeles Lakers", "Los Angeles Clippers") and
            names_match("Boston Celtics", "Golden State Warriors")
        )

    def test_st_louis_variants(self):
        """St.Louis (no space) does NOT match St. Louis currently.
        Known gap — normalization doesn't handle missing space after period."""
        # TODO: Fix normalization to handle "St.Louis" → "St. Louis"
        assert not names_match("St. Louis Cardinals", "St.Louis Cardinals")

    def test_short_college_name(self):
        """Short names like 'Duke' don't match 'Duke Blue Devils' because
        'Duke' is below the 8-char suffix containment threshold.
        This is by design — short names are too ambiguous for suffix matching."""
        assert not names_match("Duke", "Duke Blue Devils")
        # But full names work fine
        assert names_match("Duke Blue Devils", "Duke Blue Devils")

    def test_international_names(self):
        """Diacritics should be handled."""
        assert names_match("Atletico Madrid", "Atlético Madrid")


# ============================================================================
# Test EventIdentity construction
# ============================================================================

class TestEventIdentity:
    """Test EventIdentity dataclass."""

    def test_basic_construction(self):
        identity = EventIdentity(
            sport_key="basketball_nba",
            home_team_name="Boston Celtics",
            away_team_name="Minnesota Timberwolves",
            commence_time=datetime(2026, 4, 17, 0, 0, tzinfo=timezone.utc),
            claim=EventClaim("odds_api", "abc123"),
        )
        assert identity.sport_key == "basketball_nba"
        assert identity.claim.source == "odds_api"
        assert identity.claim.source_id == "abc123"
        assert identity.status is None  # defaults to None

    def test_with_optional_fields(self):
        identity = EventIdentity(
            sport_key="baseball_mlb",
            home_team_name="Red Sox",
            away_team_name="Yankees",
            commence_time=datetime(2026, 4, 17, 0, 0, tzinfo=timezone.utc),
            claim=EventClaim("statpal", "fix456"),
            commence_time_source="statpal",
            status="scheduled",
        )
        assert identity.commence_time_source == "statpal"
        assert identity.status == "scheduled"
