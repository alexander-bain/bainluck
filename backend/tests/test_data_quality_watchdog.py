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
            "espn_capture_gap",
        }
        missing = expected - names
        assert not missing, f"Expected checks missing: {missing}"

    def test_no_check_queries_the_phantom_events_updated_at(self):
        """#1001 regression: the events table has NO updated_at column. Any check
        that pairs `events` with `updated_at` raises UndefinedColumn, aborts the
        transaction, and cascades — the bug that produced ~2,585 Sentry events."""
        for check in CHECKS:
            q = check["query"].lower()
            if " events" in q or "from events" in q:
                assert "updated_at" not in q, (
                    f"Check '{check['name']}' references events.updated_at, which "
                    "does not exist (schema drift). Use a snapshot table's "
                    "captured_at instead."
                )

    def test_repointed_freshness_checks_use_valid_tables(self):
        """#1001: the three previously-broken freshness checks now read real
        snapshot tables instead of the phantom events.updated_at."""
        by_name = {c["name"]: c["query"].lower() for c in CHECKS}
        assert "odds_snapshots" in by_name["odds_api_freshness"]
        assert "win_prob_snapshots" in by_name["espn_freshness"]
        assert "score_snapshots" in by_name["statpal_freshness"]

    def test_espn_capture_gap_scope(self):
        """#1132 (#215E carryover): the granular per-live-game ESPN gap detector
        now INCLUDES baseball — ESPN does capture MLB win-prob (prod: 1,538
        espn baseball_mlb rows), so excluding it was a false NEGATIVE that blinded
        the detector to live-MLB ESPN gaps. To avoid the false-POSITIVE class
        (games ESPN never covers), it's gated on `EXISTS(prior espn snapshot)` so
        it fires only on a real mid-game capture STOP. Self-gated by status='live'."""
        by_name = {c["name"]: c["query"].lower() for c in CHECKS}
        q = by_name["espn_capture_gap"]
        assert "status = 'live'" in q            # self-gates off-season
        assert "source = 'espn'" in q
        assert "basketball%" in q and "americanfootball%" in q and "icehockey%" in q
        assert "baseball%" in q                   # #1132: MLB now covered
        assert "exists" in q                      # only fires if ESPN was covering it
        gap = next(c for c in CHECKS if c["name"] == "espn_capture_gap")
        assert gap["comparison"] == "lte" and gap["threshold"] == 0

    def test_espn_and_mlb_freshness_are_live_gated(self):
        """#215E: the coarse espn/mlb win-prob freshness checks must be LIVE-GATED —
        they fire only when a coverable game existed AND produced no snapshots, not
        merely because the slate was empty (the daily/off-season crying-wolf class
        that fired false P0 #1149 + false P1 #1150 while capture was healthy)."""
        by_name = {c["name"]: c for c in CHECKS}

        espn = by_name["espn_freshness"]
        q = espn["query"].lower()
        assert espn["comparison"] == "lte" and espn["threshold"] == 0
        assert "win_prob_snapshots" in q and "source = 'espn'" in q
        assert "espn_id is not null" in q          # season-agnostic coverable-game gate
        assert "exists" in q                        # only fires if a game existed
        assert "e.status = 'live'" in q             # live or recently-completed

        mlb = by_name["mlb_win_prob_freshness"]
        q = mlb["query"].lower()
        assert mlb["comparison"] == "lte" and mlb["threshold"] == 0
        assert "win_prob_snapshots" in q and "source = 'mlb'" in q
        assert "baseball_mlb" in q                  # gated on a real MLB game existing
        assert "exists" in q

    def test_odds_sparsity_is_tier1_scoped(self):
        """#215E: the sparsity check's message says 'Tier 1' but the old query
        counted EVERY sport, paging on upstream gaps we don't own (esports/NPB).
        It must now be scoped to the real Tier-1 leagues."""
        sparsity = next(c for c in CHECKS if c["name"] == "odds_api_sparsity")
        q = sparsity["query"].lower()
        assert "baseball_mlb" in q and "basketball_nba" in q
        assert "americanfootball_nfl" in q and "icehockey_nhl" in q
        assert "esports" not in q


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

    def test_diagnosis_never_hallucinates_schema_or_urls(self):
        """#215E: the removed LLM diagnosis hallucinated fake tables (`espn_data`),
        fake endpoints (`/api/admin/logs`), and placeholder URLs
        (`<your-platform-url>`, `yourdomain.com`) into live alerts (#1149/#1151).
        Every deterministic diagnosis must cite ONLY the real admin surface."""
        BANNED = [
            "<your-platform-url>",
            "yourdomain.com",
            "your-api-token",
            "espn_data",           # phantom table
            "/api/admin/logs",     # nonexistent endpoint
            "api.espn.com",        # wrong upstream
        ]
        for check in CHECKS:
            diag = get_llm_diagnosis(check, 0)
            low = diag.lower()
            for bad in BANNED:
                assert bad.lower() not in low, (
                    f"Check '{check['name']}' diagnosis contains hallucinated "
                    f"reference '{bad}'"
                )
            # Must cite the real admin base + a real endpoint.
            assert "$bainluck_api" in low
            assert "/api/admin/" in low

    def test_get_llm_diagnosis_makes_no_network_call(self):
        """#215E: the LLM path was removed. get_llm_diagnosis must return the
        deterministic diagnosis even with OPENAI_API_KEY set and never import
        or call openai."""
        check = next(c for c in CHECKS if c["name"] == "espn_freshness")
        mock_openai = MagicMock()
        mock_openai.OpenAI.side_effect = AssertionError("openai must not be called")
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"openai": mock_openai}):
                result = get_llm_diagnosis(check, 0)
        assert "Root cause" in result
        mock_openai.OpenAI.assert_not_called()


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


class TestCockpitDataQualityTile:
    """#1132 / L2-140: the watchdog verdict must reach the Alex Cockpit as a tile.
    A P0/P1 that only emails + files an issue is a silent alert (the #1091 lesson);
    the cockpit is the always-open eye. RED on any P0/P1 failing; None before the
    first run (so the tile renders 'unknown', never a false green).

    Queue #294 note: the tile now reads through the typed ``_read_state``
    boundary, so these patch that seam. The reason is the point of the change —
    "the watchdog has never run" and "we cannot read the watchdog's state" used
    to be the same ``None``, and both rendered the same tile."""

    @staticmethod
    def _state(status, value=None):
        from app.utils import health_reads as hr

        return hr.RedisRead(
            status=status, key="bainluck:data_quality_watchdog:last", value=value
        )

    def test_tile_unknown_before_first_run(self):
        # Never None (L2-140 accesses per_check) — 'unknown' + empty list, never a
        # false green, before the first run is cached.
        import app.routes.admin_cockpit as cockpit
        from app.utils import health_reads as hr

        with patch.object(
            cockpit, "_read_state", return_value=self._state(hr.MISSING)
        ):
            tile = cockpit._data_quality_group()
        assert tile["status"] == "unknown" and tile["per_check"] == []
        # A never-run is NOT a dependency failure.
        assert tile["unreadable"] is False

    def test_tile_unknown_with_cause_when_state_unreadable(self):
        """Queue #294: unreadable must not borrow the never-run wording."""
        import app.routes.admin_cockpit as cockpit
        from app.utils import health_reads as hr

        with patch.object(
            cockpit, "_read_state", return_value=self._state(hr.UNAVAILABLE)
        ):
            tile = cockpit._data_quality_group()
        assert tile["status"] == "unknown"
        assert tile["unreadable"] is True
        assert tile["per_check"] == []

    def test_tile_red_on_p1_failure_matches_l2140_contract(self):
        import app.routes.admin_cockpit as cockpit

        summary = {
            "status": "red",
            "computed_at": "2026-07-21T17:00:00Z",
            "checks_run": 10,
            "checks_passed": 9,
            "alerts_fired": 1,
            "self_error": False,
            "failing": [
                {"name": "espn_capture_gap", "severity": "P1", "value": 2.0,
                 "threshold": 0, "message": "gap", "issue": 1132},
            ],
        }
        with patch.object(
            cockpit, "_read_state", return_value=self._state("ok", summary)
        ):
            tile = cockpit._data_quality_group()
        assert tile["status"] == "red"
        assert tile["last_run"] == "2026-07-21T17:00:00Z"
        assert tile["alerts_fired"] == 1
        # L2-140 reads per_check[].{name,severity,message,value,threshold,status,issue,issue_url}
        row = tile["per_check"][0]
        assert row["name"] == "espn_capture_gap" and row["status"] == "red"
        assert row["severity"] == "P1" and row["threshold"] == 0
        assert row["issue_url"] and "1132" in row["issue_url"]

    def test_tile_green_when_all_clear(self):
        import app.routes.admin_cockpit as cockpit

        summary = {"status": "green", "checks_run": 10, "checks_passed": 10,
                   "alerts_fired": 0, "self_error": False, "failing": []}
        with patch.object(
            cockpit, "_read_state", return_value=self._state("ok", summary)
        ):
            tile = cockpit._data_quality_group()
        assert tile["status"] == "green" and tile["per_check"] == []
