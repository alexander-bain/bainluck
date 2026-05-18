"""Tests for team identity resolution service.

Tests cover:
- normalize_name: accents, apostrophes, case, empty strings
- _fuzzy_score: exact, containment, last-word, short-string rejection
- TeamIdentityService pure logic (async methods tested with mocks)
- Backfill task helper (_register_mapping)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.team_identity import (
    normalize_name,
    _fuzzy_score,
    TeamIdentityService,
)


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalarResult(self._rows)


# =============================================================================
# normalize_name
# =============================================================================

class TestNormalizeName:
    """Test name normalization for matching."""

    def test_lowercase(self):
        assert normalize_name("Boston Celtics") == "boston celtics"

    def test_strip_accents(self):
        assert normalize_name("Håland") == "haland"

    def test_strip_accents_skarsgard(self):
        assert normalize_name("Skarsgård") == "skarsgard"

    def test_strip_accents_multiple(self):
        assert normalize_name("José María") == "jose maria"

    def test_unify_right_single_quote(self):
        assert normalize_name("Hawai\u2019i") == "hawai'i"

    def test_unify_left_single_quote(self):
        assert normalize_name("O\u2018Brien") == "o'brien"

    def test_unify_modifier_letter(self):
        assert normalize_name("Hawai\u02BBi") == "hawai'i"

    def test_unify_backtick(self):
        assert normalize_name("O`Brien") == "o'brien"

    def test_unify_acute_accent(self):
        assert normalize_name("O\u00B4Brien") == "o'brien"

    def test_strip_whitespace(self):
        assert normalize_name("  Lakers  ") == "lakers"

    def test_empty_string(self):
        assert normalize_name("") == ""

    def test_plain_ascii(self):
        assert normalize_name("Los Angeles Lakers") == "los angeles lakers"

    def test_mixed(self):
        """Accent + apostrophe + case all in one."""
        assert normalize_name("São Paulo FC\u2019s") == "sao paulo fc's"


# =============================================================================
# _fuzzy_score
# =============================================================================

class TestFuzzyScore:
    """Test fuzzy matching score function."""

    def test_exact_match(self):
        assert _fuzzy_score("celtics", "celtics") == 100

    def test_no_match(self):
        assert _fuzzy_score("celtics", "lakers") == 0

    def test_containment_long_strings(self):
        assert _fuzzy_score("celtics", "boston celtics") == 60

    def test_containment_reverse(self):
        assert _fuzzy_score("boston celtics", "celtics") == 60

    def test_containment_rejected_short(self):
        """Short strings should not match via containment."""
        assert _fuzzy_score("la", "los angeles lakers") == 0

    def test_containment_minimum_length(self):
        """4-char strings are long enough for containment."""
        assert _fuzzy_score("lakers", "los angeles lakers") == 60

    def test_last_word_match(self):
        """Single-word candidate matches last word of multi-word target."""
        assert _fuzzy_score("lakers", "los angeles lakers") == 60  # containment wins over last-word

    def test_last_word_match_when_not_contained(self):
        """Last-word match — mascot only."""
        # "bulls" in "chicago bulls" triggers containment (60) since both >= 4
        assert _fuzzy_score("bulls", "chicago bulls") == 60

    def test_last_word_short_rejected(self):
        """Short last-word (<4 chars) should not match."""
        assert _fuzzy_score("fc", "some random fc") == 0

    def test_empty_candidate(self):
        assert _fuzzy_score("", "celtics") == 0

    def test_empty_target(self):
        assert _fuzzy_score("celtics", "") == 0

    def test_both_empty(self):
        assert _fuzzy_score("", "") == 0

    def test_3_char_exact(self):
        """3-char exact matches should score 100."""
        assert _fuzzy_score("ufc", "ufc") == 100

    def test_3_char_no_containment(self):
        """3-char strings should NOT match via containment."""
        assert _fuzzy_score("ufc", "ufc fighters") == 0

    def test_similar_but_not_matching(self):
        """Similar names that should not match."""
        assert _fuzzy_score("warriors", "wizards") == 0

    def test_team_in_city_name(self):
        """Team mascot contained in full name."""
        assert _fuzzy_score("trail blazers", "portland trail blazers") == 60


# =============================================================================
# TeamIdentityService (unit tests with mocks)
# =============================================================================

class TestTeamIdentityServiceResolve:
    """Test the resolve_team logic using mocked database calls."""

    @pytest.fixture
    def service(self):
        return TeamIdentityService()

    @pytest.mark.asyncio
    async def test_resolve_by_source_id_found(self, service):
        """Step 1: exact source_id match should return team."""
        mock_team = MagicMock()
        mock_team.id = 1
        mock_team.name = "Boston Celtics"

        with patch.object(service, "_lookup_by_source_id", return_value=mock_team):
            result = await service.resolve_team(
                AsyncMock(), "espn", "basketball_nba", source_id="2"
            )
            assert result == mock_team

    @pytest.mark.asyncio
    async def test_resolve_by_source_name_found(self, service):
        """Step 2: exact source_name match when source_id fails."""
        mock_team = MagicMock()
        mock_team.id = 1
        mock_team.name = "Boston Celtics"

        with patch.object(service, "_lookup_by_source_id", return_value=None), \
             patch.object(service, "_lookup_by_source_name", return_value=mock_team):
            result = await service.resolve_team(
                AsyncMock(), "odds_api", "basketball_nba",
                source_id="old_id", source_name="Boston Celtics"
            )
            assert result == mock_team

    @pytest.mark.asyncio
    async def test_resolve_fuzzy_mapping_found(self, service):
        """Step 3: fuzzy match on mapping table."""
        mock_team = MagicMock()
        mock_team.id = 1
        mock_team.name = "Boston Celtics"

        with patch.object(service, "_lookup_by_source_id", return_value=None), \
             patch.object(service, "_lookup_by_source_name", return_value=None), \
             patch.object(service, "_fuzzy_match_mappings", return_value=mock_team), \
             patch.object(service, "register_team_identity") as mock_register:
            result = await service.resolve_team(
                AsyncMock(), "statpal", "basketball_nba",
                source_name="Celtics"
            )
            assert result == mock_team
            # Should auto-register
            mock_register.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_fuzzy_teams_found(self, service):
        """Step 4: fuzzy match on teams table."""
        mock_team = MagicMock()
        mock_team.id = 1
        mock_team.name = "Boston Celtics"

        with patch.object(service, "_lookup_by_source_id", return_value=None), \
             patch.object(service, "_lookup_by_source_name", return_value=None), \
             patch.object(service, "_fuzzy_match_mappings", return_value=None), \
             patch.object(service, "_fuzzy_match_teams", return_value=mock_team), \
             patch.object(service, "register_team_identity") as mock_register:
            result = await service.resolve_team(
                AsyncMock(), "polymarket", "basketball_nba",
                source_name="Celtics"
            )
            assert result == mock_team
            mock_register.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_not_found(self, service):
        """Step 5: return None when nothing matches."""
        with patch.object(service, "_lookup_by_source_id", return_value=None), \
             patch.object(service, "_lookup_by_source_name", return_value=None), \
             patch.object(service, "_fuzzy_match_mappings", return_value=None), \
             patch.object(service, "_fuzzy_match_teams", return_value=None):
            result = await service.resolve_team(
                AsyncMock(), "unknown", "unknown_sport",
                source_name="Nonexistent Team"
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_resolve_no_source_id_skips_step1(self, service):
        """When no source_id provided, step 1 is skipped."""
        mock_team = MagicMock()
        with patch.object(service, "_lookup_by_source_id") as mock_id_lookup, \
             patch.object(service, "_lookup_by_source_name", return_value=mock_team):
            result = await service.resolve_team(
                AsyncMock(), "odds_api", "basketball_nba",
                source_name="Boston Celtics"
            )
            assert result == mock_team
            mock_id_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_no_name_returns_none(self, service):
        """When no source_name or abbreviation, fuzzy steps are skipped."""
        with patch.object(service, "_lookup_by_source_id", return_value=None):
            result = await service.resolve_team(
                AsyncMock(), "espn", "basketball_nba",
                source_id="nonexistent"
            )
            assert result is None


class TestTeamIdentityServiceFuzzyTeams:
    """Test real fuzzy matching behavior on Team rows."""

    @pytest.fixture
    def service(self):
        return TeamIdentityService()

    @pytest.mark.asyncio
    async def test_fuzzy_team_match_uses_alternate_names(self, service):
        """Cross-source aliases should resolve against Team.alternate_names."""
        celtics = MagicMock()
        celtics.id = 1
        celtics.name = "Boston Celtics"
        celtics.alternate_names = ["Celts", "Boston C's"]

        session = AsyncMock()
        session.execute.return_value = _FakeExecuteResult([celtics])

        result = await service._fuzzy_match_teams(
            session, "Celts", "basketball_nba"
        )

        assert result == celtics

    @pytest.mark.asyncio
    async def test_resolve_rejects_short_ambiguous_abbreviation(self, service):
        """A short abbreviation like LA must not fuzzy-match same-city aliases."""
        lakers = MagicMock()
        lakers.id = 1
        lakers.name = "Los Angeles Lakers"
        lakers.alternate_names = ["Lakers", "LA Lakers"]
        clippers = MagicMock()
        clippers.id = 2
        clippers.name = "Los Angeles Clippers"
        clippers.alternate_names = ["Clippers", "LA Clippers"]

        session = AsyncMock()
        session.execute.return_value = _FakeExecuteResult([lakers, clippers])

        with patch.object(service, "_lookup_by_source_id", return_value=None), \
             patch.object(service, "_lookup_by_source_name", return_value=None), \
             patch.object(service, "_fuzzy_match_mappings", return_value=None), \
             patch.object(service, "register_team_identity") as mock_register:
            result = await service.resolve_team(
                session, "statpal", "basketball_nba",
                source_abbreviation="LA"
            )

        assert result is None
        mock_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_fuzzy_team_query_is_scoped_to_sport_family(self, service):
        """Fuzzy team scans should stay inside the requested sport family."""
        captured_statements = []

        async def execute(statement):
            captured_statements.append(statement)
            return _FakeExecuteResult([])

        session = AsyncMock()
        session.execute.side_effect = execute

        result = await service._fuzzy_match_teams(
            session, "Giants", "basketball_nba"
        )

        assert result is None
        assert len(captured_statements) == 1
        statement_text = str(captured_statements[0])
        assert "JOIN sports" in statement_text
        assert "sports.key LIKE" in statement_text
        assert list(captured_statements[0].compile().params.values()) == ["basketball%"]


class TestTeamIdentityServiceFindTeams:
    """Test find_teams_for_event and resolve_from_kalshi_ticker."""

    @pytest.fixture
    def service(self):
        return TeamIdentityService()

    @pytest.mark.asyncio
    async def test_find_teams_for_event(self, service):
        """find_teams_for_event delegates to resolve_team twice."""
        mock_home = MagicMock(name="Home")
        mock_away = MagicMock(name="Away")

        call_count = 0
        async def mock_resolve(session, source, sport_key, **kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs.get("source_name") == "Boston Celtics":
                return mock_home
            return mock_away

        with patch.object(service, "resolve_team", side_effect=mock_resolve):
            home, away = await service.find_teams_for_event(
                AsyncMock(), "Boston Celtics", "Golden State Warriors", "basketball_nba"
            )
            assert home == mock_home
            assert away == mock_away
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_resolve_from_kalshi_ticker_valid(self, service):
        """resolve_from_kalshi_ticker parses and resolves both teams."""
        mock_team_a = MagicMock(name="TeamA")
        mock_team_b = MagicMock(name="TeamB")

        call_count = 0
        async def mock_resolve(session, source, sport_key, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_team_a
            return mock_team_b

        with patch.object(service, "resolve_team", side_effect=mock_resolve), \
             patch("app.utils.prediction_market_matching.extract_teams_from_ticker", return_value=("Celtics", "Warriors")), \
             patch("app.utils.sport_keys.get_sport_key_from_ticker", return_value="basketball_nba"):
            a, b = await service.resolve_from_kalshi_ticker(AsyncMock(), "KXNBAGAME-26FEB19BOSGSW")
            assert a == mock_team_a
            assert b == mock_team_b

    @pytest.mark.asyncio
    async def test_resolve_from_kalshi_ticker_unparseable(self, service):
        """resolve_from_kalshi_ticker returns (None, None) for unparseable tickers."""
        with patch("app.utils.prediction_market_matching.extract_teams_from_ticker", return_value=None):
            a, b = await service.resolve_from_kalshi_ticker(AsyncMock(), "INVALID-TICKER")
            assert a is None
            assert b is None


class TestTeamIdentityServiceRegister:
    """Test register_team_identity."""

    @pytest.fixture
    def service(self):
        return TeamIdentityService()

    @pytest.mark.asyncio
    async def test_register_no_id_no_name_is_noop(self, service):
        """Register with neither source_id nor source_name does nothing."""
        mock_session = AsyncMock()
        await service.register_team_identity(
            mock_session, 1, "espn", "basketball_nba"
        )
        mock_session.execute.assert_not_called()


# =============================================================================
# Cross-consistency between normalize_name copies
# =============================================================================

class TestNormNameConsistency:
    """Verify our normalize_name produces same results as team_linking._normalize_name."""

    def test_matches_team_linking(self):
        from app.utils.team_linking import _normalize_name
        test_cases = [
            "Boston Celtics",
            "Skarsgård",
            "Hawai\u2019i Rainbow Warriors",
            "São Paulo FC",
            "  Trimmed  ",
            "",
        ]
        for name in test_cases:
            assert normalize_name(name) == _normalize_name(name), f"Mismatch for: {name!r}"

    def test_espn_sync_uses_same_algorithm(self):
        """espn_sync._normalize_name is a nested function (not importable),
        but uses the same NFD + Mn-stripping + apostrophe-unification algorithm.
        Verify the algorithm produces expected results for the same cases."""
        # These are the exact expected outputs — same algorithm, tested inline
        assert normalize_name("Los Angeles Lakers") == "los angeles lakers"
        assert normalize_name("Skarsgård") == "skarsgard"
        assert normalize_name("O\u2019Brien") == "o'brien"
        assert normalize_name("José") == "jose"


# =============================================================================
# Module-level singleton
# =============================================================================

class TestModuleSingleton:
    def test_singleton_exists(self):
        from app.services.team_identity import team_identity_service
        assert isinstance(team_identity_service, TeamIdentityService)

    def test_singleton_is_same_instance(self):
        from app.services.team_identity import team_identity_service as a
        from app.services.team_identity import team_identity_service as b
        assert a is b
