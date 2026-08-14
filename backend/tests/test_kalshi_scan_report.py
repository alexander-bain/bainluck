"""Main-scan telemetry for poll_kalshi_markets (#1586 / #1845).

The queue's order of work is not negotiable: instrument the cursor FIRST, so the
freeze's mechanism is read off a measurement, then fix capture. These tests lock
down the measurement — specifically that it cannot report a comfortable answer
for an uncomfortable state, which is how the previous five mechanisms survived.
"""

import pytest

from app.utils.kalshi_scan_report import (
    KalshiScanReport,
    cursor_fingerprint,
    summarize_history,
)


class TestCursorFingerprint:
    def test_none_and_empty_are_none(self):
        assert cursor_fingerprint(None) is None
        assert cursor_fingerprint("") is None

    def test_stable_and_short(self):
        a = cursor_fingerprint("opaque-cursor-blob")
        b = cursor_fingerprint("opaque-cursor-blob")
        assert a == b
        assert len(a) == 12

    def test_different_cursors_differ(self):
        assert cursor_fingerprint("a") != cursor_fingerprint("b")


class TestVerdict:
    """"It returned" is not "it worked" (gotcha #53)."""

    def test_frozen_when_no_existing_event_was_reached(self):
        # The displayed-market population got zero updates this beat.
        r = KalshiScanReport(
            stop_reason="main_scan_deadline",
            events_new=40,
            events_existing=2000,
            events_processed=40,
            unreached_existing=2000,
        )
        assert r.verdict() == "frozen"

    def test_starved_when_the_deadline_cut_off_existing_events(self):
        r = KalshiScanReport(
            stop_reason="main_scan_deadline",
            events_new=40,
            events_existing=2000,
            events_processed=900,
            unreached_existing=1140,
        )
        assert r.verdict() == "starved"

    def test_partial_when_pages_were_dropped(self):
        r = KalshiScanReport(
            stop_reason="exhausted",
            events_new=10,
            events_existing=100,
            events_processed=110,
            unreached_existing=0,
            wrapped=True,
            pages_skipped=1,
        )
        assert r.verdict() == "partial"

    def test_partial_when_the_walk_never_wrapped(self):
        r = KalshiScanReport(
            stop_reason="max_pages",
            events_new=10,
            events_existing=100,
            events_processed=110,
            unreached_existing=0,
            wrapped=False,
        )
        assert r.verdict() == "partial"

    def test_healthy_only_on_a_clean_exhaustive_walk(self):
        r = KalshiScanReport(
            stop_reason="exhausted",
            events_new=10,
            events_existing=100,
            events_processed=110,
            unreached_existing=0,
            wrapped=True,
            pages_skipped=0,
        )
        assert r.verdict() == "healthy"

    def test_not_run_is_not_healthy(self):
        """An empty read must never render as a good one."""
        assert KalshiScanReport().verdict() == "not_run"

    def test_verdict_is_serialized(self):
        r = KalshiScanReport(stop_reason="exhausted", wrapped=True)
        assert r.to_dict()["verdict"] == r.verdict()


class TestSummarizeHistory:
    """The readings that can only be taken ACROSS runs."""

    def test_empty_history(self):
        assert summarize_history([]) == {"runs": 0}

    def test_detects_a_stuck_cursor(self):
        history = [
            {"start_cursor_fp": "aaaaaaaaaaaa", "stop_reason": "main_scan_deadline"}
            for _ in range(6)
        ]
        s = summarize_history(history)
        assert s["distinct_start_cursors"] == 1
        assert s["cursor_appears_stuck"] is True

    def test_an_advancing_cursor_is_not_flagged(self):
        history = [
            {"start_cursor_fp": f"cursor{i:06d}", "stop_reason": "main_scan_deadline"}
            for i in range(6)
        ]
        s = summarize_history(history)
        assert s["distinct_start_cursors"] == 6
        assert s["cursor_appears_stuck"] is False

    def test_never_wrapped_is_surfaced(self):
        """If the walk never wraps, the tail is never revisited — a freeze even
        though every individual page succeeded."""
        history = [{"wrapped": False, "stop_reason": "main_scan_deadline"}] * 10
        s = summarize_history(history)
        assert s["wraps"] == 0
        assert s["never_wrapped"] is True

    def test_wrapping_history_is_not_flagged(self):
        history = [{"wrapped": True, "stop_reason": "exhausted"}] * 3
        s = summarize_history(history)
        assert s["never_wrapped"] is False

    def test_stop_reason_and_verdict_histograms(self):
        history = [
            {"stop_reason": "main_scan_deadline", "verdict": "starved"},
            {"stop_reason": "main_scan_deadline", "verdict": "starved"},
            {"stop_reason": "exhausted", "verdict": "healthy"},
        ]
        s = summarize_history(history)
        assert s["stop_reasons"] == {"main_scan_deadline": 2, "exhausted": 1}
        assert s["verdicts"] == {"starved": 2, "healthy": 1}

    def test_unreached_existing_accumulates(self):
        history = [{"unreached_existing": 100}, {"unreached_existing": 250}]
        assert summarize_history(history)["total_unreached_existing"] == 350

    def test_two_runs_alone_do_not_declare_a_stuck_cursor(self):
        """Guard against crying wolf on a thin sample."""
        history = [{"start_cursor_fp": "same"}, {"start_cursor_fp": "same"}]
        assert summarize_history(history)["cursor_appears_stuck"] is False


class TestScanTelemetryIsWired:
    """Structural: the telemetry must survive future edits to the scan."""

    def test_fetch_records_stop_reason_and_cursor_fingerprints(self):
        import inspect

        from app.services.kalshi_api import KalshiAPIService

        src = inspect.getsource(KalshiAPIService._fetch_all_events_unfiltered)
        assert "cursor_fingerprint" in src
        # Every loop exit must name itself.
        for reason in ("exhausted", "main_scan_deadline", "page_error"):
            assert reason in src, f"stop reason {reason!r} is not recorded"
        assert "parse_timeout" in src, "a dropped page must be counted"

    def test_poll_task_records_the_update_starvation_measurement(self):
        import inspect

        from app.tasks.kalshi import _poll_kalshi_markets

        src = inspect.getsource(_poll_kalshi_markets)
        assert "unreached_existing" in src
        assert "save_scan_report" in src

    def test_admin_endpoint_exists(self):
        from app.routes import admin_providers

        paths = {r.path for r in admin_providers.router.routes}
        assert "/kalshi/scan-report" in paths


class TestUnreachedExistingArithmetic:
    """The measurement itself, on the ordering that produces it.

    The upsert loop is `new_events + existing_events`, new first, breaking on a
    per-event deadline. Everything the deadline cuts off is therefore in the
    EXISTING tail — the displayed population.
    """

    @staticmethod
    def _unreached_existing(n_new, n_existing, processed):
        reached_existing = max(0, processed - n_new)
        return max(0, n_existing - reached_existing)

    def test_deadline_inside_the_new_block_strands_every_existing_event(self):
        assert self._unreached_existing(100, 2000, 40) == 2000

    def test_deadline_inside_the_existing_block(self):
        assert self._unreached_existing(100, 2000, 900) == 1200

    def test_full_pass_strands_nothing(self):
        assert self._unreached_existing(100, 2000, 2100) == 0

    def test_never_negative(self):
        assert self._unreached_existing(100, 2000, 99999) == 0
