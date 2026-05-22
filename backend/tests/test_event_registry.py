"""Tests for the unified event registry — find_or_create_event().

Tests the matching cascade, claim attachment, source priority,
and edge cases like swapped home/away and city abbreviations.
"""

import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    _attach_claim,
    _find_by_source_id,
    _update_fields_by_priority,
    _find_by_structured_match,
    find_or_create_event,
    _sport_id_cache,
)
from app.models import Event
from app.utils.name_normalization import names_match


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeExecuteResult:
    def __init__(self, *, scalar=None, rows=None, first_row=None):
        self._scalar = scalar
        self._rows = rows or []
        self._first_row = first_row

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return _FakeScalarResult(self._rows)

    def first(self):
        return self._first_row


class _FakeRegistrySession:
    """Small async session double for event registry query shapes."""

    def __init__(self, *, source_matches=None, structured_candidates=None, sport_id=1):
        self.source_matches = source_matches or {}
        self.structured_candidates = structured_candidates or []
        self.sport_id = sport_id
        self.added = []
        self.flushed = 0
        self.statements = []
        self.structured_params = None

    async def execute(self, statement):
        self.statements.append(statement)
        statement_text = str(statement)

        if "pg_advisory_xact_lock" in statement_text:
            return _FakeExecuteResult()

        compiled_params = statement.compile().params

        if "FROM sports" in statement_text:
            return _FakeExecuteResult(first_row=SimpleNamespace(id=self.sport_id))

        if "FROM events" in statement_text and (
            "WHERE events.external_id =" in statement_text
            or "WHERE events.statpal_fixture_id =" in statement_text
            or "WHERE events.espn_id =" in statement_text
        ):
            source_id = next(iter(compiled_params.values()))
            return _FakeExecuteResult(scalar=self.source_matches.get(source_id))

        if "FROM events" in statement_text and "events.commence_time BETWEEN" in statement_text:
            self.structured_params = compiled_params
            start = compiled_params["commence_time_1"]
            end = compiled_params["commence_time_2"]
            statuses = compiled_params["status_1"]
            sport_id = compiled_params["sport_id_1"]
            rows = [
                candidate
                for candidate in self.structured_candidates
                if candidate.sport_id == sport_id
                and start <= candidate.commence_time <= end
                and candidate.status in statuses
            ]
            return _FakeExecuteResult(rows=rows)

        raise AssertionError(f"Unexpected statement: {statement}")

    def add(self, event):
        if event.id is None:
            event.id = 100 + len(self.added)
        self.added.append(event)

    async def flush(self):
        self.flushed += 1


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
        """St.Louis (no space) matches St. Louis — normalization adds space after period."""
        assert names_match("St. Louis Cardinals", "St.Louis Cardinals")

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


# ============================================================================
# Guardrails for cross-source event matching
# ============================================================================

class TestCrossSourceEventMatching:
    """Guardrail tests for the matching cascade used by source pollers."""

    @pytest.mark.asyncio
    async def test_exact_source_id_reuses_event_before_structured_matching(self):
        """A known source ID wins even if names/time are noisy."""
        existing = Event(
            id=11,
            sport_id=1,
            external_id="odds-game-123",
            home_team_name="Boston Celtics",
            away_team_name="New York Knicks",
            commence_time=datetime(2026, 4, 17, 0, 0, tzinfo=timezone.utc),
            status="scheduled",
            commence_time_source="odds_api",
        )
        session = _FakeRegistrySession(source_matches={"odds-game-123": existing})
        _sport_id_cache.clear()

        event, was_created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="basketball_nba",
                home_team_name="Typo Home",
                away_team_name="Typo Away",
                commence_time=datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc),
                claim=EventClaim("odds_api", "odds-game-123"),
            ),
        )

        assert event is existing
        assert was_created is False
        assert session.added == []
        assert session.flushed == 1
        assert existing.external_id == "odds-game-123"
        assert session.structured_params is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("claim", "column_name"),
        [
            (EventClaim("odds_api", "odds-1"), "events.external_id"),
            (EventClaim("statpal", "fixture-1"), "events.statpal_fixture_id"),
            (EventClaim("espn", "401866758"), "events.espn_id"),
        ],
    )
    async def test_source_id_lookup_uses_source_specific_columns(self, claim, column_name):
        existing = Event(
            id=12,
            sport_id=1,
            home_team_name="Boston Celtics",
            away_team_name="New York Knicks",
            commence_time=datetime(2026, 4, 17, 0, 0, tzinfo=timezone.utc),
            status="scheduled",
        )
        session = _FakeRegistrySession(source_matches={claim.source_id: existing})

        event = await _find_by_source_id(session, claim)

        assert event is existing
        assert column_name in str(session.statements[-1])
        assert claim.source_id in session.statements[-1].compile().params.values()

    @pytest.mark.asyncio
    async def test_prediction_market_claims_do_not_run_source_id_lookup(self):
        session = _FakeRegistrySession()

        event = await _find_by_source_id(session, EventClaim("kalshi", "KXNBA-EXAMPLE"))

        assert event is None
        assert session.statements == []

    @pytest.mark.asyncio
    async def test_structured_match_allows_swapped_home_away_with_team_variants(self):
        """Sources can disagree on home/away while still describing one game."""
        existing = Event(
            id=21,
            sport_id=1,
            home_team_name="Golden State Warriors",
            away_team_name="Los Angeles Clippers",
            commence_time=datetime(2026, 4, 16, 2, 0, tzinfo=timezone.utc),
            status="scheduled",
        )
        session = _FakeRegistrySession(structured_candidates=[existing])

        event = await _find_by_structured_match(
            session,
            1,
            "LA Clippers",
            "Golden State Warriors",
            datetime(2026, 4, 16, 2, 5, tzinfo=timezone.utc),
        )

        assert event is existing

    @pytest.mark.asyncio
    async def test_structured_match_respects_timezone_aware_window(self):
        """The ±28h window includes the boundary across timezone offsets."""
        incoming_pacific = datetime(
            2026, 4, 15, 19, 0, tzinfo=timezone(timedelta(hours=-7))
        )
        boundary_match = Event(
            id=22,
            sport_id=1,
            home_team_name="Boston Celtics",
            away_team_name="New York Knicks",
            commence_time=datetime(2026, 4, 17, 5, 0, tzinfo=timezone.utc),
            status="scheduled",
        )
        just_outside = Event(
            id=23,
            sport_id=1,
            home_team_name="Boston Celtics",
            away_team_name="New York Knicks",
            commence_time=datetime(2026, 4, 17, 7, 0, 1, tzinfo=timezone.utc),
            status="scheduled",
        )

        session = _FakeRegistrySession(structured_candidates=[boundary_match])
        event = await _find_by_structured_match(
            session,
            1,
            "Boston Celtics",
            "NY Knicks",
            incoming_pacific,
        )
        assert event is boundary_match
        assert session.structured_params["commence_time_1"] == incoming_pacific - timedelta(hours=28)
        assert session.structured_params["commence_time_2"] == incoming_pacific + timedelta(hours=28)

        outside_session = _FakeRegistrySession(structured_candidates=[just_outside])
        event = await _find_by_structured_match(
            outside_session,
            1,
            "Boston Celtics",
            "NY Knicks",
            incoming_pacific,
        )
        assert event is None

    @pytest.mark.asyncio
    async def test_find_or_create_attaches_new_source_claim_without_duplicate_event(self):
        """Structured cross-source matches should attach IDs, not insert another event."""
        existing = Event(
            id=31,
            sport_id=1,
            external_id="odds-game-456",
            home_team_name="Los Angeles Clippers",
            away_team_name="Golden State Warriors",
            commence_time=datetime(2026, 4, 16, 2, 0, tzinfo=timezone.utc),
            status="scheduled",
            commence_time_source="odds_api",
        )
        session = _FakeRegistrySession(structured_candidates=[existing])
        _sport_id_cache.clear()

        event, was_created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="basketball_nba",
                home_team_name="LA Clippers",
                away_team_name="Golden State Warriors",
                commence_time=datetime(2026, 4, 16, 2, 10, tzinfo=timezone.utc),
                claim=EventClaim("espn", "401866758"),
                commence_time_source="espn",
            ),
        )

        assert event is existing
        assert was_created is False
        assert existing.espn_id == "401866758"
        assert existing.home_team_name == "LA Clippers"
        assert existing.away_team_name == "Golden State Warriors"
        assert session.added == []
        assert session.flushed == 1
