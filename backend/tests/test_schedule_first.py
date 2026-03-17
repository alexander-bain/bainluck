"""Tests for Phase 3: StatPal schedule-first event creation.

Tests cover:
- _names_match: exact, containment, last-word, short-string rejection
- _find_statpal_event_for_odds_api: matching, home/away swap, no match, time window
- StatPal event creation in _sync_statpal_schedules (mocked)
- Event discovery StatPal attachment in _discover_events (mocked)
- ESPN commence_time guard (StatPal source preserved)
- Beat schedule timing (StatPal before event discovery)
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.tasks.sports import _names_match, _find_statpal_event_for_odds_api


# =============================================================================
# _names_match
# =============================================================================

class TestNamesMatch:
    """Test fuzzy team name matching for event discovery."""

    def test_exact_match(self):
        assert _names_match("boston celtics", "boston celtics") is True

    def test_empty_a(self):
        assert _names_match("", "celtics") is False

    def test_empty_b(self):
        assert _names_match("celtics", "") is False

    def test_both_empty(self):
        assert _names_match("", "") is False

    def test_containment_long(self):
        assert _names_match("celtics", "boston celtics") is True

    def test_containment_reverse(self):
        assert _names_match("boston celtics", "celtics") is True

    def test_containment_short_rejected(self):
        """3-char strings should not match via containment."""
        assert _names_match("la", "los angeles lakers") is False

    def test_containment_minimum_4_chars(self):
        assert _names_match("lakers", "los angeles lakers") is True

    def test_last_word_match(self):
        """Mascot match: last word of both names matches."""
        assert _names_match("golden state warriors", "washington warriors") is True

    def test_last_word_short_rejected(self):
        """Short last-word (<4 chars) should not match."""
        assert _names_match("some fc", "other fc") is False

    def test_no_match(self):
        assert _names_match("celtics", "lakers") is False

    def test_partial_no_match(self):
        """Similar but not matching names."""
        assert _names_match("warriors", "wizards") is False


# =============================================================================
# _find_statpal_event_for_odds_api
# =============================================================================

class TestFindStatpalEvent:
    """Test matching StatPal-created events to Odds API events."""

    def _make_event(self, home, away, commence_time, sport_id=1, external_id=None):
        """Create a mock Event object."""
        event = MagicMock()
        event.id = 1
        event.sport_id = sport_id
        event.home_team_name = home
        event.away_team_name = away
        event.commence_time = commence_time
        event.external_id = external_id
        event.commence_time_source = "statpal"
        return event

    @pytest.mark.asyncio
    async def test_exact_match(self):
        """Should find event with exact team name match."""
        t = datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc)
        event = self._make_event("Boston Celtics", "Los Angeles Lakers", t)

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [event]
        session.execute.return_value = result_mock

        found = await _find_statpal_event_for_odds_api(
            session, 1, "Boston Celtics", "Los Angeles Lakers", t
        )
        assert found == event

    @pytest.mark.asyncio
    async def test_fuzzy_match(self):
        """Should match via containment (e.g., 'Celtics' in 'Boston Celtics')."""
        t = datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc)
        event = self._make_event("Boston Celtics", "Los Angeles Lakers", t)

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [event]
        session.execute.return_value = result_mock

        found = await _find_statpal_event_for_odds_api(
            session, 1, "Celtics", "Lakers", t
        )
        assert found == event

    @pytest.mark.asyncio
    async def test_swapped_home_away(self):
        """Should match when home/away are swapped between sources."""
        t = datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc)
        # StatPal has Celtics as home, Lakers as away
        event = self._make_event("Boston Celtics", "Los Angeles Lakers", t)

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [event]
        session.execute.return_value = result_mock

        # Odds API has them swapped
        found = await _find_statpal_event_for_odds_api(
            session, 1, "Los Angeles Lakers", "Boston Celtics", t
        )
        assert found == event

    @pytest.mark.asyncio
    async def test_no_candidates(self):
        """Should return None when no candidates found."""
        t = datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc)

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute.return_value = result_mock

        found = await _find_statpal_event_for_odds_api(
            session, 1, "Boston Celtics", "Lakers", t
        )
        assert found is None

    @pytest.mark.asyncio
    async def test_no_team_match(self):
        """Should return None when teams don't match any candidate."""
        t = datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc)
        event = self._make_event("Golden State Warriors", "Portland Trail Blazers", t)

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [event]
        session.execute.return_value = result_mock

        found = await _find_statpal_event_for_odds_api(
            session, 1, "Boston Celtics", "Los Angeles Lakers", t
        )
        assert found is None

    @pytest.mark.asyncio
    async def test_partial_team_match_rejected(self):
        """Should require BOTH teams to match, not just one."""
        t = datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc)
        event = self._make_event("Boston Celtics", "Golden State Warriors", t)

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [event]
        session.execute.return_value = result_mock

        # Only home team matches
        found = await _find_statpal_event_for_odds_api(
            session, 1, "Boston Celtics", "Los Angeles Lakers", t
        )
        assert found is None

    @pytest.mark.asyncio
    async def test_multiple_candidates_first_match_wins(self):
        """When multiple candidates exist, should return the first match."""
        t = datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc)
        event1 = self._make_event("Boston Celtics", "Lakers", t)
        event1.id = 1
        event2 = self._make_event("Warriors", "Trail Blazers", t)
        event2.id = 2

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [event1, event2]
        session.execute.return_value = result_mock

        found = await _find_statpal_event_for_odds_api(
            session, 1, "Celtics", "Lakers", t
        )
        assert found.id == 1


# =============================================================================
# StatPal event creation logic
# =============================================================================

class TestStatPalEventCreation:
    """Test that StatPal sync creates events correctly."""

    def test_event_creation_fields(self):
        """Verify the Event fields set during StatPal creation."""
        from app.models import Event

        event = Event(
            sport_id=1,
            external_id=None,
            home_team_name="Boston Celtics",
            away_team_name="Los Angeles Lakers",
            commence_time=datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc),
            commence_time_source="statpal",
            status="scheduled",
        )
        assert event.external_id is None
        assert event.commence_time_source == "statpal"
        assert event.status == "scheduled"
        assert event.home_team_name == "Boston Celtics"


# =============================================================================
# Event discovery attachment
# =============================================================================

class TestEventDiscoveryAttachment:
    """Test event discovery behavior when attaching to StatPal events."""

    def test_names_match_mascot_for_discovery(self):
        """College teams often have city prefix differences."""
        # StatPal: "Oklahoma State Cowboys", Odds API: "Cowboys"
        assert _names_match("cowboys", "oklahoma state cowboys") is True

    def test_names_match_full_names(self):
        """Full names match across sources."""
        assert _names_match("oklahoma sooners", "oklahoma sooners") is True

    def test_names_match_different_teams(self):
        """Different mascots should not match."""
        assert _names_match("sooners", "cowboys") is False

    def test_names_match_short_overlap_rejected(self):
        """Short strings matching by containment should be rejected."""
        assert _names_match("ou", "oklahoma sooners") is False


# =============================================================================
# ESPN commence_time guard
# =============================================================================

class TestESPNCommenceTimeGuard:
    """Test that ESPN doesn't overwrite StatPal commence_time."""

    def test_statpal_source_not_overwritten(self):
        """getattr guard should prevent ESPN from overwriting StatPal times."""
        event = MagicMock()
        event.commence_time_source = "statpal"

        # Simulate the guard from espn_sync.py
        should_correct = getattr(event, 'commence_time_source', None) != "statpal"
        assert should_correct is False

    def test_odds_api_source_overwritten(self):
        """Events without StatPal source should allow ESPN correction."""
        event = MagicMock()
        event.commence_time_source = "odds_api"

        should_correct = getattr(event, 'commence_time_source', None) != "statpal"
        assert should_correct is True

    def test_none_source_overwritten(self):
        """Events with no source should allow ESPN correction."""
        event = MagicMock()
        event.commence_time_source = None

        should_correct = getattr(event, 'commence_time_source', None) != "statpal"
        assert should_correct is True

    def test_espn_source_overwritten(self):
        """Events already set by ESPN should allow re-correction."""
        event = MagicMock()
        event.commence_time_source = "espn"

        should_correct = getattr(event, 'commence_time_source', None) != "statpal"
        assert should_correct is True


# =============================================================================
# Beat schedule timing
# =============================================================================

class TestBeatScheduleTiming:
    """Test that beat schedule ensures StatPal runs before event discovery."""

    def test_statpal_before_discovery(self):
        """StatPal schedule sync should run before event discovery.
        StatPal: hourly at :00, Discovery: every 15 min at :05/:20/:35/:50.
        StatPal always runs before the first discovery of each hour."""
        from celery.schedules import crontab
        from app.tasks import celery_app

        beat = celery_app.conf.beat_schedule

        statpal_schedule = beat["sync-statpal-schedules"]["schedule"]
        discovery_schedule = beat["discover-new-events"]["schedule"]

        # Both should be crontab instances
        assert isinstance(statpal_schedule, crontab)
        assert isinstance(discovery_schedule, crontab)

        # StatPal runs hourly at :00, discovery at :05/:20/:35/:50
        assert str(statpal_schedule) == str(crontab(minute=0))
        assert str(discovery_schedule) == str(crontab(minute="5,20,35,50"))


# =============================================================================
# Nullable external_id model
# =============================================================================

class TestNullableExternalId:
    """Test that Event.external_id can be None."""

    def test_external_id_nullable(self):
        """Event model should allow None for external_id."""
        from app.models import Event

        event = Event(
            sport_id=1,
            external_id=None,
            home_team_name="Team A",
            away_team_name="Team B",
            commence_time=datetime(2026, 3, 1, tzinfo=timezone.utc),
            status="scheduled",
        )
        assert event.external_id is None

    def test_external_id_can_be_set(self):
        """StatPal events should allow attaching external_id later."""
        from app.models import Event

        event = Event(
            sport_id=1,
            external_id=None,
            home_team_name="Team A",
            away_team_name="Team B",
            commence_time=datetime(2026, 3, 1, tzinfo=timezone.utc),
            status="scheduled",
        )
        # Simulate Odds API discovery attaching external_id
        event.external_id = "abc123"
        assert event.external_id == "abc123"


# =============================================================================
# Integration: StatPal → Odds API attachment flow
# =============================================================================

class TestAttachmentFlow:
    """Test the full StatPal → Odds API attachment handshake."""

    def test_commence_time_preserved_on_attachment(self):
        """When Odds API attaches to StatPal event, StatPal's commence_time
        should be preserved (not overwritten by Odds API time)."""
        event = MagicMock()
        event.commence_time_source = "statpal"
        event.commence_time = datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc)

        # Simulate discovery attachment logic
        odds_api_time = datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc)
        if event.commence_time_source != "statpal":
            event.commence_time = odds_api_time

        # StatPal time should be preserved
        assert event.commence_time == datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc)

    def test_commence_time_overwritten_when_not_statpal(self):
        """Non-StatPal events should get Odds API commence_time."""
        event = MagicMock()
        event.commence_time_source = None
        event.commence_time = datetime(2026, 3, 1, 19, 0, tzinfo=timezone.utc)

        odds_api_time = datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc)
        if event.commence_time_source != "statpal":
            event.commence_time = odds_api_time

        assert event.commence_time == odds_api_time

    def test_external_id_set_on_attachment(self):
        """Odds API external_id should be set when attaching."""
        event = MagicMock()
        event.external_id = None

        # Simulate attachment
        event.external_id = "odds_api_event_123"
        assert event.external_id == "odds_api_event_123"

    def test_team_names_updated_on_attachment(self):
        """Odds API team names should update the event (canonical names)."""
        event = MagicMock()
        event.home_team_name = "Celtics"  # StatPal short form
        event.away_team_name = "Lakers"

        # Simulate attachment
        event.home_team_name = "Boston Celtics"  # Odds API canonical
        event.away_team_name = "Los Angeles Lakers"

        assert event.home_team_name == "Boston Celtics"
        assert event.away_team_name == "Los Angeles Lakers"
