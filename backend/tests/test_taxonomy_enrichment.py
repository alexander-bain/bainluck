"""Tests for LLM taxonomy enrichment.

Covers:
- enrich_event_taxonomy: LLM call, response validation, error handling
- enrich_market_taxonomy: LLM call, response validation
- Lifecycle caching: stage detection, cache expiry
- Context assembly helpers: standings formatting, injury extraction
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.utils.event_taxonomy import ALLOWED_TAGS, LLM_ENRICHMENT_NAMESPACES


class TestUpsertTaxonomyCacheDedup:
    """#1002: _upsert_taxonomy_cache must not blow up with MultipleResultsFound
    when duplicate (event_id, analysis_type) rows exist — it should update the
    first and self-heal by deleting the rest."""

    def _session(self, rows):
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        session.delete = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.mark.asyncio
    async def test_duplicate_rows_dedup_and_no_crash(self):
        from app.tasks.taxonomy import _upsert_taxonomy_cache
        now = datetime.now(timezone.utc)
        row1 = MagicMock(id=1)
        row2 = MagicMock(id=2)
        session = self._session([row1, row2])
        await _upsert_taxonomy_cache(session, 42, "event_taxonomy", "live", ["x"], now)
        # kept the first, updated it, deleted the dupe
        assert row1.movement_data == {"stage": "live", "llm_tags": ["x"]}
        session.delete.assert_awaited_once_with(row2)
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_single_row_updates_no_delete(self):
        from app.tasks.taxonomy import _upsert_taxonomy_cache
        now = datetime.now(timezone.utc)
        row1 = MagicMock(id=1)
        session = self._session([row1])
        await _upsert_taxonomy_cache(session, 42, "event_taxonomy", "scheduled", ["y"], now)
        assert row1.movement_data == {"stage": "scheduled", "llm_tags": ["y"]}
        session.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_row_inserts(self):
        from app.tasks.taxonomy import _upsert_taxonomy_cache
        now = datetime.now(timezone.utc)
        session = self._session([])
        await _upsert_taxonomy_cache(session, 42, "event_taxonomy", "completed", ["z"], now)
        session.add.assert_called_once()
        session.delete.assert_not_awaited()


# ══════════════════════════════════════════════════════════════════════
# enrich_event_taxonomy
# ══════════════════════════════════════════════════════════════════════

class TestEnrichEventTaxonomy:
    def test_valid_response_parsed(self):
        """Valid LLM JSON response is parsed and validated."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"stakes": ["playoff_race"], "narrative": ["rivalry"], '
            '"audience": ["national_interest"], "competitive_structure": ["head_to_head"]}'
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.services.llm._get_client", return_value=mock_client):
            from app.services.llm import enrich_event_taxonomy

            result = enrich_event_taxonomy(
                home_team="Lakers",
                away_team="Celtics",
                sport_key="basketball_nba",
                status="live",
            )

        assert result is not None
        assert result["stakes"] == ["playoff_race"]
        assert result["narrative"] == ["rivalry"]
        assert result["audience"] == ["national_interest"]
        assert result["competitive_structure"] == ["head_to_head"]

    def test_invalid_values_filtered(self):
        """Invalid tag values are silently dropped."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"stakes": ["playoff_race", "invalid_fake"], '
            '"narrative": ["rivalry", 123], '
            '"audience": [], "competitive_structure": ["unknown"]}'
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.services.llm._get_client", return_value=mock_client):
            from app.services.llm import enrich_event_taxonomy

            result = enrich_event_taxonomy(
                home_team="Lakers",
                away_team="Celtics",
                sport_key="basketball_nba",
                status="live",
            )

        assert result is not None
        assert result["stakes"] == ["playoff_race"]
        assert result["narrative"] == ["rivalry"]
        assert "audience" not in result  # empty after filtering
        assert "competitive_structure" not in result  # "unknown" not valid

    def test_llm_unavailable_returns_none(self):
        """Returns None when OpenAI client is not available."""
        with patch("app.services.llm._get_client", return_value=None):
            from app.services.llm import enrich_event_taxonomy

            result = enrich_event_taxonomy(
                home_team="Lakers",
                away_team="Celtics",
                sport_key="basketball_nba",
                status="live",
            )

        assert result is None

    def test_malformed_json_returns_none(self):
        """Returns None when LLM returns invalid JSON."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.services.llm._get_client", return_value=mock_client):
            from app.services.llm import enrich_event_taxonomy

            result = enrich_event_taxonomy(
                home_team="Lakers",
                away_team="Celtics",
                sport_key="basketball_nba",
                status="live",
            )

        assert result is None

    def test_all_empty_returns_none(self):
        """Returns None when all namespaces have no valid values."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"stakes": [], "narrative": [], "audience": [], "competitive_structure": []}'
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.services.llm._get_client", return_value=mock_client):
            from app.services.llm import enrich_event_taxonomy

            result = enrich_event_taxonomy(
                home_team="Lakers",
                away_team="Celtics",
                sport_key="basketball_nba",
                status="live",
            )

        assert result is None

    def test_context_includes_championship_odds(self):
        """Championship odds are included in the LLM prompt when provided."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"stakes": ["title_defense"]}'

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.services.llm._get_client", return_value=mock_client):
            from app.services.llm import enrich_event_taxonomy

            result = enrich_event_taxonomy(
                home_team="Lakers",
                away_team="Celtics",
                sport_key="basketball_nba",
                status="live",
                home_champ_odds=0.15,
                away_champ_odds=0.08,
            )

        # Verify the prompt included championship odds
        call_args = mock_client.chat.completions.create.call_args
        prompt_content = call_args[1]["messages"][0]["content"]
        assert "15.0%" in prompt_content
        assert "8.0%" in prompt_content

    def test_api_exception_returns_none(self):
        """Returns None on API exception without crashing."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API timeout")

        with patch("app.services.llm._get_client", return_value=mock_client):
            from app.services.llm import enrich_event_taxonomy

            result = enrich_event_taxonomy(
                home_team="Lakers",
                away_team="Celtics",
                sport_key="basketball_nba",
                status="live",
            )

        assert result is None


# ══════════════════════════════════════════════════════════════════════
# enrich_market_taxonomy
# ══════════════════════════════════════════════════════════════════════

class TestEnrichMarketTaxonomy:
    def test_valid_response(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"stakes": ["title_defense"], "narrative": ["legacy_moment"], "audience": ["national_interest"]}'
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.services.llm._get_client", return_value=mock_client):
            from app.services.llm import enrich_market_taxonomy

            result = enrich_market_taxonomy(
                market_name="NBA Championship Winner 2025-26",
                llm_sport_category="basketball",
                market_tier=1,
            )

        assert result is not None
        assert result["stakes"] == ["title_defense"]

    def test_does_not_include_competitive_structure(self):
        """Market enrichment only generates stakes, narrative, audience."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"stakes": ["playoff_race"], "narrative": [], "audience": [], '
            '"competitive_structure": ["bracket"]}'
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.services.llm._get_client", return_value=mock_client):
            from app.services.llm import enrich_market_taxonomy

            result = enrich_market_taxonomy(
                market_name="NBA Championship Winner",
            )

        assert result is not None
        assert "competitive_structure" not in result


# ══════════════════════════════════════════════════════════════════════
# Lifecycle caching helpers
# ══════════════════════════════════════════════════════════════════════

class TestLifecycleCaching:
    @pytest.mark.asyncio
    async def test_enrichment_task_skips_when_llm_unavailable(self):
        """Task returns before opening a DB session when live LLM is unavailable."""
        from app.tasks.taxonomy import _enrich_taxonomy_llm_impl

        with (
            patch("app.services.llm.is_available", return_value=False),
            patch(
                "app.tasks.taxonomy.get_task_session",
                side_effect=AssertionError("DB session should not be opened"),
            ),
        ):
            result = await _enrich_taxonomy_llm_impl(event_limit=5, market_limit=5)

        assert result == {
            "skipped": True,
            "reason": "LLM unavailable (no OPENAI_API_KEY)",
        }

    @pytest.mark.asyncio
    async def test_enrichment_task_uses_valid_event_cache_without_llm_call(self):
        """Fresh same-stage event cache avoids a live LLM call and preserves tags."""
        from app.tasks import taxonomy

        now = datetime.now(timezone.utc)
        cached = {
            "stage": "live",
            "llm_tags": ["stakes:playoff_race"],
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
        }

        class MockEvent:
            id = 42
            status = "live"
            event_tags = ["sport:basketball", "stakes:playoff_race"]

        class MockSessionContext:
            async def __aenter__(self):
                session = MagicMock()
                session.commit = AsyncMock()
                return session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        event = MockEvent()

        with (
            patch("app.services.llm.is_available", return_value=True),
            patch("app.tasks.taxonomy.get_task_session", return_value=MockSessionContext()),
            patch(
                "app.tasks.taxonomy._fetch_enrichment_candidates",
                new=AsyncMock(return_value=[event]),
            ),
            patch(
                "app.tasks.taxonomy._load_taxonomy_caches",
                new=AsyncMock(return_value={event.id: cached}),
            ),
            patch(
                "app.tasks.taxonomy._batch_fetch_championship_odds",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.tasks.taxonomy._fetch_market_enrichment_candidates",
                new=AsyncMock(return_value=[]),
            ),
            patch("app.services.llm.enrich_event_taxonomy") as enrich_event,
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await taxonomy._enrich_taxonomy_llm_impl(event_limit=5, market_limit=0)

        assert result["events_skipped_cached"] == 1
        assert result["events_enriched"] == 0
        assert result["events_no_tags"] == 0
        assert event.event_tags == ["sport:basketball", "stakes:playoff_race"]
        enrich_event.assert_not_called()

    def test_lifecycle_stage_live(self):
        from app.tasks.taxonomy import _lifecycle_stage
        assert _lifecycle_stage("live") == "live"

    def test_lifecycle_stage_completed(self):
        from app.tasks.taxonomy import _lifecycle_stage
        assert _lifecycle_stage("completed") == "completed"

    def test_lifecycle_stage_closed(self):
        from app.tasks.taxonomy import _lifecycle_stage
        assert _lifecycle_stage("closed") == "completed"

    def test_lifecycle_stage_scheduled(self):
        from app.tasks.taxonomy import _lifecycle_stage
        assert _lifecycle_stage("scheduled") == "scheduled"

    def test_cache_not_expired_same_stage(self):
        from app.tasks.taxonomy import _cache_expired
        now = datetime.now(timezone.utc)
        cached = {
            "stage": "live",
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
        }
        assert _cache_expired(cached, "live", now) is False

    def test_cache_expired_by_time(self):
        from app.tasks.taxonomy import _cache_expired
        now = datetime.now(timezone.utc)
        cached = {
            "stage": "live",
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
        }
        assert _cache_expired(cached, "live", now) is True

    def test_cache_expired_stage_change(self):
        from app.tasks.taxonomy import _cache_expired
        now = datetime.now(timezone.utc)
        cached = {
            "stage": "scheduled",
            "expires_at": (now + timedelta(hours=5)).isoformat(),
        }
        # Stage changed from scheduled to live
        assert _cache_expired(cached, "live", now) is True

    def test_completed_never_expires(self):
        from app.tasks.taxonomy import _cache_expired
        now = datetime.now(timezone.utc)
        cached = {
            "stage": "completed",
            "expires_at": None,
        }
        assert _cache_expired(cached, "completed", now) is False


# ══════════════════════════════════════════════════════════════════════
# Context assembly helpers
# ══════════════════════════════════════════════════════════════════════

class TestContextHelpers:
    def test_format_standings(self):
        from app.tasks.taxonomy import _format_standings
        result = _format_standings({
            "position": 3,
            "wins": 45,
            "losses": 22,
            "conference": "Eastern",
            "division": "Atlantic",
        })
        assert "#3" in result
        assert "45-22" in result
        assert "Eastern" in result

    def test_format_standings_empty(self):
        from app.tasks.taxonomy import _format_standings
        result = _format_standings({})
        assert result == ""

    def test_extract_injuries_with_list(self):
        from app.tasks.taxonomy import _extract_injuries_summary

        class MockEvent:
            box_score_data = {
                "injuries": [
                    {"name": "LeBron James", "status": "Out"},
                    {"name": "Anthony Davis", "status": "Questionable"},
                ]
            }

        result = _extract_injuries_summary(MockEvent())
        assert result is not None
        assert "LeBron James (Out)" in result
        assert "Anthony Davis (Questionable)" in result

    def test_extract_injuries_none(self):
        from app.tasks.taxonomy import _extract_injuries_summary

        class MockEvent:
            box_score_data = None

        result = _extract_injuries_summary(MockEvent())
        assert result is None

    def test_extract_injuries_no_key(self):
        from app.tasks.taxonomy import _extract_injuries_summary

        class MockEvent:
            box_score_data = {"leaders": []}

        result = _extract_injuries_summary(MockEvent())
        assert result is None
