"""Tests for the data quality watchdog task.

Covers:
- Check definitions are valid (all have required keys)
- Threshold comparison logic
- LLM diagnosis fallback when OpenAI is unavailable
- Redis dedup prevents duplicate alerts
- Email template renders correctly
"""

import sys

import pytest
from unittest.mock import patch, MagicMock

from app.tasks.data_quality_watchdog import (
    CHECKS,
    passes_threshold,
    get_llm_diagnosis,
    _build_alert_email_html,
    _deterministic_fallback,
    _check_redis_dedup,
    _set_redis_dedup,
)


class TestCheckDefinitions:
    """All check definitions must have the required keys."""

    REQUIRED_KEYS = {"name", "query", "threshold", "comparison", "severity", "message"}

    def test_all_checks_have_required_keys(self):
        for check in CHECKS:
            missing = self.REQUIRED_KEYS - set(check.keys())
            assert not missing, (
                f"Check '{check.get('name', '?')}' is missing keys: {missing}"
            )

    def test_all_checks_have_valid_severity(self):
        valid_severities = {"P0", "P1", "P2", "P3"}
        for check in CHECKS:
            assert check["severity"] in valid_severities, (
                f"Check '{check['name']}' has invalid severity '{check['severity']}'"
            )

    def test_all_checks_have_valid_comparison(self):
        valid_comparisons = {"gte", "lte", "eq"}
        for check in CHECKS:
            assert check["comparison"] in valid_comparisons, (
                f"Check '{check['name']}' has invalid comparison '{check['comparison']}'"
            )

    def test_all_checks_have_non_empty_query(self):
        for check in CHECKS:
            assert check["query"].strip(), (
                f"Check '{check['name']}' has empty query"
            )

    def test_all_checks_have_unique_names(self):
        names = [c["name"] for c in CHECKS]
        assert len(names) == len(set(names)), "Duplicate check names found"

    def test_expected_checks_exist(self):
        names = {c["name"] for c in CHECKS}
        expected = {
            "kalshi_freshness",
            "polymarket_freshness",
            "odds_api_freshness",
            "kalshi_winner_coverage",
            "polymarket_winner_coverage",
            "odds_api_sparsity",
        }
        missing = expected - names
        assert not missing, f"Expected checks missing: {missing}"


class TestPassesThreshold:
    """Threshold comparison logic."""

    def test_gte_passes_when_above(self):
        check = {"threshold": 10, "comparison": "gte"}
        assert passes_threshold(15, check) is True

    def test_gte_passes_when_equal(self):
        check = {"threshold": 10, "comparison": "gte"}
        assert passes_threshold(10, check) is True

    def test_gte_fails_when_below(self):
        check = {"threshold": 10, "comparison": "gte"}
        assert passes_threshold(5, check) is False

    def test_lte_passes_when_below(self):
        check = {"threshold": 5, "comparison": "lte"}
        assert passes_threshold(3, check) is True

    def test_lte_passes_when_equal(self):
        check = {"threshold": 5, "comparison": "lte"}
        assert passes_threshold(5, check) is True

    def test_lte_fails_when_above(self):
        check = {"threshold": 5, "comparison": "lte"}
        assert passes_threshold(10, check) is False

    def test_eq_passes_when_equal(self):
        check = {"threshold": 42, "comparison": "eq"}
        assert passes_threshold(42, check) is True

    def test_eq_fails_when_different(self):
        check = {"threshold": 42, "comparison": "eq"}
        assert passes_threshold(43, check) is False

    def test_none_value_fails_for_freshness(self):
        """NULL value should fail freshness checks (gte with threshold >= 1)."""
        check = {"threshold": 1, "comparison": "gte"}
        assert passes_threshold(None, check) is False

    def test_none_value_passes_for_coverage(self):
        """NULL value should pass for coverage (0 resolved = nothing to cover)."""
        check = {"threshold": 99.0, "comparison": "gte"}
        # Threshold >= 1 means freshness-like, so this fails
        assert passes_threshold(None, check) is False

    def test_none_value_passes_for_sparsity(self):
        """NULL value should pass for lte checks."""
        check = {"threshold": 0, "comparison": "lte"}
        assert passes_threshold(None, check) is True

    def test_float_comparison(self):
        check = {"threshold": 99.0, "comparison": "gte"}
        assert passes_threshold(99.5, check) is True
        assert passes_threshold(98.9, check) is False

    def test_zero_value(self):
        check = {"threshold": 1, "comparison": "gte"}
        assert passes_threshold(0, check) is False

    def test_defaults_to_gte_for_unknown_comparison(self):
        check = {"threshold": 10, "comparison": "unknown_op"}
        assert passes_threshold(15, check) is True
        assert passes_threshold(5, check) is False


class TestLLMDiagnosis:
    """LLM diagnosis with OpenAI fallback."""

    def test_fallback_when_no_api_key(self):
        """Without OPENAI_API_KEY, should use deterministic fallback."""
        check = CHECKS[0]  # kalshi_freshness
        with patch.dict("os.environ", {}, clear=False):
            # Ensure no OPENAI_API_KEY
            env = dict(__import__("os").environ)
            env.pop("OPENAI_API_KEY", None)
            with patch.dict("os.environ", env, clear=True):
                result = get_llm_diagnosis(check, 0)
                assert "Root cause" in result or "root cause" in result.lower()
                assert len(result) > 50

    def test_fallback_when_openai_fails(self):
        """If OpenAI raises, should fall back to deterministic template."""
        check = CHECKS[0]
        mock_openai = MagicMock()
        mock_openai.OpenAI.side_effect = Exception("API error")
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"openai": mock_openai}):
                result = get_llm_diagnosis(check, 0)
                assert "Root cause" in result or "root cause" in result.lower()

    def test_deterministic_freshness_diagnosis(self):
        for check in CHECKS:
            if "freshness" in check["name"]:
                result = _deterministic_fallback(check, 0)
                assert "Investigation steps" in result or "investigation" in result.lower()
                assert "celery" in result.lower() or "Celery" in result

    def test_deterministic_winner_coverage_diagnosis(self):
        for check in CHECKS:
            if "winner_coverage" in check["name"]:
                result = _deterministic_fallback(check, 95.0)
                assert "backfill" in result.lower()

    def test_deterministic_sparsity_diagnosis(self):
        for check in CHECKS:
            if "sparsity" in check["name"]:
                result = _deterministic_fallback(check, 5)
                assert "quota" in result.lower() or "snapshot" in result.lower()

    def test_deterministic_unknown_check(self):
        unknown_check = {
            "name": "some_new_check",
            "threshold": 42,
            "severity": "P2",
        }
        result = _deterministic_fallback(unknown_check, 10)
        assert "some_new_check" in result


class TestRedisDedup:
    """Redis dedup prevents duplicate alerts."""

    def test_dedup_returns_false_when_no_key(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        with patch("app.tasks.redis_state.get_redis_client", return_value=mock_redis):
            assert _check_redis_dedup("test_check") is False

    def test_dedup_returns_true_when_key_exists(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"42"
        with patch("app.tasks.redis_state.get_redis_client", return_value=mock_redis):
            assert _check_redis_dedup("test_check") is True

    def test_set_dedup_calls_setex_with_24h_ttl(self):
        mock_redis = MagicMock()
        with patch("app.tasks.redis_state.get_redis_client", return_value=mock_redis):
            _set_redis_dedup("test_check", 123)
            mock_redis.setex.assert_called_once_with(
                "watchdog:alert:test_check", 86400, "123"
            )

    def test_set_dedup_handles_none_issue_number(self):
        mock_redis = MagicMock()
        with patch("app.tasks.redis_state.get_redis_client", return_value=mock_redis):
            _set_redis_dedup("test_check", None)
            mock_redis.setex.assert_called_once_with(
                "watchdog:alert:test_check", 86400, "alerted"
            )

    def test_dedup_check_tolerates_redis_failure(self):
        """Redis failure should not block alerts — returns False (allow alert)."""
        with patch("app.tasks.redis_state.get_redis_client", side_effect=Exception("Redis down")):
            assert _check_redis_dedup("test_check") is False


class TestEmailTemplate:
    """Email template renders correctly."""

    def test_p0_alert_renders_red_header(self):
        check = {
            "name": "kalshi_freshness",
            "severity": "P0",
            "message": "No Kalshi updates in 6h",
            "threshold": 1,
        }
        html_body = _build_alert_email_html(check, 0, "Test diagnosis")
        assert "#dc2626" in html_body  # Red background for P0
        assert "P0 Alert" in html_body
        assert "kalshi_freshness" in html_body

    def test_p1_alert_renders_amber_header(self):
        check = {
            "name": "odds_api_sparsity",
            "severity": "P1",
            "message": "Sparse snapshots",
            "threshold": 0,
        }
        html_body = _build_alert_email_html(check, 3, "Test diagnosis")
        assert "#f59e0b" in html_body  # Amber background for P1
        assert "P1 Alert" in html_body

    def test_template_escapes_html(self):
        check = {
            "name": "test<script>",
            "severity": "P1",
            "message": "XSS attempt <img src=x>",
            "threshold": 1,
        }
        html_body = _build_alert_email_html(check, 0, "<script>alert(1)</script>")
        assert "<script>" not in html_body
        assert "&lt;script&gt;" in html_body

    def test_template_includes_admin_link(self):
        check = {
            "name": "test",
            "severity": "P1",
            "message": "Test",
            "threshold": 1,
        }
        html_body = _build_alert_email_html(check, 0, "diag")
        assert "https://bainluck.com/admin" in html_body

    def test_template_includes_value_and_threshold(self):
        check = {
            "name": "test",
            "severity": "P1",
            "message": "Test",
            "threshold": 99.0,
        }
        html_body = _build_alert_email_html(check, 95.5, "diag")
        assert "95.5" in html_body
        assert "99.0" in html_body
