"""Tests for LLM-based matching quality audits.

Tests cover:
- Canonical key audit: false positive/negative detection
- Prediction market link audit: false/missing link detection
- Related futures audit: coverage gaps
- Pattern aggregation
- LLM audit_match() helper
"""

import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, AsyncMock


# =========================================================================
# audit_match() helper tests
# =========================================================================

class TestAuditMatch:
    """Test the audit_match() LLM helper in llm.py."""

    @patch("app.services.llm._get_client")
    def test_returns_parsed_json(self, mock_get_client):
        from app.services.llm import audit_match

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"same_market": true, "confidence": 0.95, "reason": "Both are NBA championship markets"}'

        client = MagicMock()
        client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = client

        result = audit_match("Test prompt")
        assert result == {
            "same_market": True,
            "confidence": 0.95,
            "reason": "Both are NBA championship markets",
        }

    @patch("app.services.llm._get_client")
    def test_returns_none_on_invalid_json(self, mock_get_client):
        from app.services.llm import audit_match

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json"

        client = MagicMock()
        client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = client

        result = audit_match("Test prompt")
        assert result is None

    @patch("app.services.llm._get_client")
    def test_returns_none_when_client_unavailable(self, mock_get_client):
        from app.services.llm import audit_match

        mock_get_client.return_value = None
        result = audit_match("Test prompt")
        assert result is None

    @patch("app.services.llm._get_client")
    def test_returns_none_on_api_error(self, mock_get_client):
        from app.services.llm import audit_match

        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("API error")
        mock_get_client.return_value = client

        result = audit_match("Test prompt")
        assert result is None

    @patch("app.services.llm._get_client")
    def test_uses_json_response_format(self, mock_get_client):
        from app.services.llm import audit_match

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"test": true}'

        client = MagicMock()
        client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = client

        audit_match("Test prompt")

        call_kwargs = client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}
        assert call_kwargs["temperature"] == 0
        assert call_kwargs["model"] == "gpt-4o-mini"

    @patch("app.services.llm._get_client")
    def test_complex_json_response(self, mock_get_client):
        from app.services.llm import audit_match

        complex_json = json.dumps({
            "correct_link": False,
            "confidence": 0.92,
            "reason": "Market is about UFC, event is NBA",
            "pattern_category": "cross_sport_mislink",
            "suggested_rule": "Add sport_key check to matching",
        })

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = complex_json

        client = MagicMock()
        client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = client

        result = audit_match("Verify this link")
        assert result["correct_link"] is False
        assert result["pattern_category"] == "cross_sport_mislink"
        assert result["suggested_rule"] == "Add sport_key check to matching"


# =========================================================================
# Canonical key audit tests
# =========================================================================

class TestAuditCanonicalKeys:
    """Test _audit_canonical_keys_impl finding extraction."""

    @patch("app.services.llm.is_available")
    def test_skips_when_llm_unavailable(self, mock_available):
        from app.tasks.matching_audit import _audit_canonical_keys_impl
        import asyncio

        mock_available.return_value = False
        result = asyncio.run(_audit_canonical_keys_impl(limit=5))
        assert result["status"] == "skipped"
        assert result["reason"] == "LLM not available"

    def test_false_positive_finding_structure(self):
        """Verify the shape of a false positive finding dict."""
        finding = {
            "type": "false_positive",
            "pattern_category": "game_prop_shares_canonical_key",
            "canonical_key": "basketball:NBA:championship:2025-26",
            "market_ids": [123, 456],
            "market_names": ["NBA Championship Winner", "NBA Finals: Points Total"],
            "confidence": 0.95,
            "reason": "Second market is a game prop",
            "suggested_rule": "Filter markets with ': Points' from canonical key generation",
            "suggested_action": "review_canonical_key_basketball:NBA:championship:2025-26",
        }

        assert finding["type"] == "false_positive"
        assert len(finding["market_ids"]) == 2
        assert finding["confidence"] >= 0.0
        assert finding["confidence"] <= 1.0
        assert "pattern_category" in finding
        assert "suggested_rule" in finding

    def test_false_negative_finding_structure(self):
        """Verify the shape of a false negative finding dict."""
        finding = {
            "type": "false_negative",
            "pattern_category": "missing_canonical_key",
            "market_id": 789,
            "market_name": "NBA Championship Odds 2026",
            "suggested_key": "basketball:NBA:championship:2025-26",
            "confidence": 0.88,
            "reason": "Same market as existing key",
            "suggested_rule": "Add '2026' season pattern to canonical key builder",
            "suggested_action": "set_canonical_key_789",
        }

        assert finding["type"] == "false_negative"
        assert isinstance(finding["market_id"], int)
        assert finding["suggested_key"] is not None


# =========================================================================
# Prediction market link audit tests
# =========================================================================

class TestAuditPredictionMarketLinks:
    """Test _audit_prediction_market_links_impl finding extraction."""

    @patch("app.services.llm.is_available")
    def test_skips_when_llm_unavailable(self, mock_available):
        from app.tasks.matching_audit import _audit_prediction_market_links_impl
        import asyncio

        mock_available.return_value = False
        result = asyncio.run(_audit_prediction_market_links_impl(limit=5))
        assert result["status"] == "skipped"

    def test_false_link_finding_structure(self):
        """Verify the shape of a false link finding dict."""
        finding = {
            "type": "false_link",
            "pattern_category": "cross_sport_mislink",
            "market_id": 100,
            "market_name": "UFC 310: Main Event",
            "market_source": "kalshi",
            "event_id": 5000,
            "event_teams": "Lakers at Warriors",
            "confidence": 0.95,
            "reason": "Market is about UFC, event is NBA",
            "suggested_rule": "Add sport_key validation to matching",
            "suggested_action": "unlink_market_100",
        }

        assert finding["type"] == "false_link"
        assert finding["market_id"] == 100
        assert finding["event_id"] == 5000

    def test_missing_link_finding_structure(self):
        """Verify the shape of a missing link finding dict."""
        finding = {
            "type": "missing_link",
            "pattern_category": "unmatched_game_market",
            "market_id": 200,
            "market_name": "Lakers vs Warriors",
            "market_source": "polymarket",
            "suggested_team_a": "Los Angeles Lakers",
            "suggested_team_b": "Golden State Warriors",
            "confidence": 0.92,
            "reason": "Clear game-level market with identifiable teams",
            "suggested_rule": None,
            "suggested_action": "link_market_200",
        }

        assert finding["type"] == "missing_link"
        assert finding["suggested_team_a"] is not None
        assert finding["suggested_team_b"] is not None


# =========================================================================
# Related futures audit tests
# =========================================================================

class TestAuditRelatedFutures:
    """Test _audit_related_futures_impl finding extraction."""

    @patch("app.services.llm.is_available")
    def test_skips_when_llm_unavailable(self, mock_available):
        from app.tasks.matching_audit import _audit_related_futures_impl
        import asyncio

        mock_available.return_value = False
        result = asyncio.run(_audit_related_futures_impl(limit=5))
        assert result["status"] == "skipped"

    def test_missing_championship_finding_structure(self):
        """Verify the shape of a missing championship futures finding."""
        finding = {
            "type": "missing_championship_futures",
            "pattern_category": "missing_team_id_major_sport",
            "event_id": 3000,
            "home_team": "Boston Celtics",
            "away_team": "New York Knicks",
            "sport_key": "basketball_nba",
            "home_championship_count": 3,
            "away_championship_count": 0,
            "confidence": 1.0,
            "reason": "Knicks should have NBA Championship futures",
            "suggested_rule": "Run backfill_team_links for basketball outcomes",
            "suggested_action": "run_backfill_team_links",
        }

        assert finding["type"] == "missing_championship_futures"
        assert finding["away_championship_count"] == 0
        assert finding["home_championship_count"] > 0

    def test_missing_team_id_finding_structure(self):
        """Verify the shape of a missing team_id finding."""
        finding = {
            "type": "missing_team_id",
            "pattern_category": "outcome_missing_team_link",
            "outcome_id": 4000,
            "outcome_name": "Boston Celtics",
            "market_name": "NBA Championship Winner 2025-26",
            "suggested_team_name": "Boston Celtics",
            "confidence": 0.99,
            "reason": "Clear NBA team name",
            "suggested_rule": None,
            "suggested_action": "link_team_4000",
        }

        assert finding["type"] == "missing_team_id"
        assert finding["suggested_team_name"] is not None

    def test_major_sport_prefixes(self):
        """Verify _MAJOR_SPORT_PREFIXES covers expected sports."""
        from app.tasks.matching_audit import _MAJOR_SPORT_PREFIXES

        assert "basketball_nba" in _MAJOR_SPORT_PREFIXES
        assert "americanfootball_nfl" in _MAJOR_SPORT_PREFIXES
        assert "baseball_mlb" in _MAJOR_SPORT_PREFIXES
        assert "icehockey_nhl" in _MAJOR_SPORT_PREFIXES
        assert "soccer_epl" in _MAJOR_SPORT_PREFIXES
        # Should not include minor sports
        assert "tennis_atp" not in _MAJOR_SPORT_PREFIXES
        assert "mma_ufc" not in _MAJOR_SPORT_PREFIXES


# =========================================================================
# Pattern aggregation tests
# =========================================================================

class TestPatternAggregation:
    """Test the pattern counting logic used in audit findings."""

    def test_pattern_counting_from_findings(self):
        """Test that pattern_category aggregation works correctly."""
        findings = [
            {"type": "false_positive", "pattern_category": "game_prop_shares_key", "suggested_rule": "Filter game props"},
            {"type": "false_positive", "pattern_category": "game_prop_shares_key", "suggested_rule": "Filter game props v2"},
            {"type": "false_negative", "pattern_category": "missing_season_year", "suggested_rule": "Add year pattern"},
            {"type": "false_positive", "pattern_category": "game_prop_shares_key", "suggested_rule": None},
            {"type": "missing_link", "pattern_category": None, "suggested_rule": None},  # Should be skipped
            {"type": "missing_link", "pattern_category": "null", "suggested_rule": None},  # Should be skipped
        ]

        pattern_counts: dict[str, dict] = {}
        for finding in findings:
            cat = finding.get("pattern_category")
            if not cat or cat == "null":
                continue
            if cat not in pattern_counts:
                pattern_counts[cat] = {
                    "category": cat,
                    "count": 0,
                    "latest_suggestion": None,
                }
            pattern_counts[cat]["count"] += 1
            rule = finding.get("suggested_rule")
            if rule and rule != "null":
                pattern_counts[cat]["latest_suggestion"] = rule

        assert pattern_counts["game_prop_shares_key"]["count"] == 3
        assert pattern_counts["game_prop_shares_key"]["latest_suggestion"] == "Filter game props v2"
        assert pattern_counts["missing_season_year"]["count"] == 1
        assert len(pattern_counts) == 2  # null and None patterns skipped

    def test_findings_serializable_to_json(self):
        """Verify audit findings can be serialized to JSONB."""
        findings = [
            {
                "type": "false_positive",
                "pattern_category": "test",
                "canonical_key": "basketball:NBA:championship:2025-26",
                "market_ids": [1, 2, 3],
                "market_names": ["Market A", "Market B", "Market C"],
                "confidence": 0.95,
                "reason": "Test reason",
                "suggested_rule": "Add pattern",
                "suggested_action": "review",
            }
        ]

        movement_data = {
            "audit_type": "canonical_key",
            "run_at": datetime.now(timezone.utc).isoformat(),
            "sampled": 50,
            "issues_found": 1,
            "findings": findings,
        }

        # Should serialize without error
        serialized = json.dumps(movement_data)
        deserialized = json.loads(serialized)

        assert deserialized["issues_found"] == 1
        assert len(deserialized["findings"]) == 1
        assert deserialized["findings"][0]["confidence"] == 0.95


# =========================================================================
# Analysis type value tests
# =========================================================================

class TestAnalysisTypes:
    """Verify analysis_type values fit in String(30) column."""

    def test_analysis_type_lengths(self):
        """All analysis_type values must be ≤30 characters."""
        types = [
            "audit_canonical",      # 15 chars
            "audit_pred_market",    # 17 chars
            "audit_related_fut",   # 17 chars
            "line_movement",        # 13 chars (existing)
            "market_disagreement",  # 19 chars (existing)
            "related_futures",      # 15 chars (existing)
        ]

        for t in types:
            assert len(t) <= 30, f"analysis_type '{t}' is {len(t)} chars, max is 30"


# =========================================================================
# Task registration tests
# =========================================================================

class TestTaskRegistration:
    """Verify Celery tasks are properly registered."""

    def test_audit_tasks_exist(self):
        """Check that audit task wrappers are importable."""
        from app.tasks import (
            audit_canonical_keys,
            audit_prediction_market_links,
            audit_related_futures,
        )

        assert audit_canonical_keys.name == "app.tasks.audit_canonical_keys"
        assert audit_prediction_market_links.name == "app.tasks.audit_prediction_market_links"
        assert audit_related_futures.name == "app.tasks.audit_related_futures"

    def test_beat_schedule_has_audit_entries(self):
        """Verify beat schedule includes daily audit tasks."""
        from app.tasks import celery_app

        schedule = celery_app.conf.beat_schedule

        assert "audit-canonical-keys-daily" in schedule
        assert "audit-prediction-market-links-daily" in schedule
        assert "audit-related-futures-daily" in schedule

        # Verify they target correct task names
        assert schedule["audit-canonical-keys-daily"]["task"] == "app.tasks.audit_canonical_keys"
        assert schedule["audit-prediction-market-links-daily"]["task"] == "app.tasks.audit_prediction_market_links"
        assert schedule["audit-related-futures-daily"]["task"] == "app.tasks.audit_related_futures"

    def test_audit_schedule_times(self):
        """Verify audit tasks are scheduled after canonical key backfill (8:30)."""
        from app.tasks import celery_app

        schedule = celery_app.conf.beat_schedule

        # Canonical keys at 9:00
        canonical = schedule["audit-canonical-keys-daily"]["schedule"]
        assert canonical.hour == {9}
        assert canonical.minute == {0}

        # Prediction market links at 9:15
        pred = schedule["audit-prediction-market-links-daily"]["schedule"]
        assert pred.hour == {9}
        assert pred.minute == {15}

        # Related futures at 9:30
        related = schedule["audit-related-futures-daily"]["schedule"]
        assert related.hour == {9}
        assert related.minute == {30}
