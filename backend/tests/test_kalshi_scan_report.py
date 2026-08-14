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


def _report(*, events_new=0, events_existing=0, supplementary_events=0, **kw):
    """A report whose counters ADD UP, so a test reads the verdict it means to.

    Queue 355: `events_fetched` is the whole fetched population and
    `events_new + events_existing` partitions it. Building a report by hand
    without that identity now yields ``instrument_broken`` — which is the point
    of the invariant, and would otherwise make every verdict fixture below a
    test of the invariant instead of a test of the verdict.
    """
    total = events_new + events_existing
    return KalshiScanReport(
        events_new=events_new,
        events_existing=events_existing,
        events_fetched=total,
        main_scan_events=total - supplementary_events,
        supplementary_events=supplementary_events,
        **kw,
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
        r = _report(
            stop_reason="main_scan_deadline",
            events_new=40,
            events_existing=2000,
            events_processed=40,
            unreached_existing=2000,
        )
        assert r.verdict() == "frozen"

    def test_starved_when_the_deadline_cut_off_existing_events(self):
        r = _report(
            stop_reason="main_scan_deadline",
            events_new=40,
            events_existing=2000,
            events_processed=900,
            unreached_existing=1140,
        )
        assert r.verdict() == "starved"

    def test_partial_when_pages_were_dropped(self):
        r = _report(
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
        r = _report(
            stop_reason="max_pages",
            events_new=10,
            events_existing=100,
            events_processed=110,
            unreached_existing=0,
            wrapped=False,
        )
        assert r.verdict() == "partial"

    def test_healthy_only_on_a_clean_exhaustive_walk(self):
        r = _report(
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
        # Queue 355: `events_fetched` must be written over the population it
        # names — the RETURNED list — not snapshotted mid-function before the
        # supplementary rescue adds to it. The main scan gets its own counter.
        assert "main_scan_events" in src
        assert "supplementary_events" in src
        _main_at = src.index('_tel["main_scan_events"]')
        _fetched_at = src.index('_tel["events_fetched"]')
        assert _fetched_at > _main_at, (
            "events_fetched is written before the supplementary loop again — "
            "that is the exact defect queue 355 fixed"
        )

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


class TestReconciliationInvariant:
    """Queue 355 (#1845): the instrument must refuse to name a mechanism it
    cannot add up.

    Beat 1 of the 350-2b gate printed ``verdict: frozen`` directly above
    ``events_new 5,335 + events_existing 5,075 = 10,410`` against
    ``events_fetched 5,000``. The verdict was legible, believable, and derived
    from counters covering three different populations. Nothing in the artifact
    said so; a human had to do the addition.
    """

    def test_beat_ones_exact_numbers_are_refused(self):
        r = KalshiScanReport(
            stop_reason="max_pages",
            events_fetched=5000,
            main_scan_events=5000,
            supplementary_events=0,
            events_new=5335,
            events_existing=5075,
            events_processed=252,
            unreached_existing=5075,
        )
        assert r.reconciles() is False
        assert r.verdict() == "instrument_broken"
        rec = r.reconciliation()
        assert rec["new_plus_existing"] == 10410
        assert rec["new_plus_existing_delta"] == 5410

    def test_instrument_broken_outranks_frozen(self):
        """The dangerous case is a BELIEVABLE verdict over broken counters."""
        r = KalshiScanReport(
            stop_reason="main_scan_deadline",
            events_fetched=100,
            main_scan_events=100,
            events_new=40,
            events_existing=2000,   # cannot be: 40 + 2000 != 100
            events_processed=40,
            unreached_existing=2000,
        )
        assert r.verdict() == "instrument_broken"

    def test_halves_must_also_sum_to_the_whole(self):
        """The main-scan/supplementary split is checked, not just new/existing."""
        r = KalshiScanReport(
            stop_reason="exhausted",
            wrapped=True,
            events_fetched=110,
            main_scan_events=50,
            supplementary_events=10,   # 50 + 10 != 110
            events_new=10,
            events_existing=100,
            events_processed=110,
        )
        assert r.reconciles() is False
        assert r.verdict() == "instrument_broken"

    def test_a_supplemented_scan_reconciles(self):
        """The real shape: main scan + rescue, partitioned into new/existing."""
        r = KalshiScanReport(
            stop_reason="max_pages",
            events_fetched=10410,
            main_scan_events=5000,
            supplementary_events=5410,
            events_new=5335,
            events_existing=5075,
            events_processed=252,
            unreached_existing=5075,
        )
        assert r.reconciles() is True
        assert r.verdict() == "frozen"

    def test_a_cancelled_fetch_is_not_a_broken_instrument(self):
        """`fetch_wall` has no population, so the identity is not checked."""
        r = KalshiScanReport(
            stop_reason="fetch_wall",
            events_fetched=5000,   # partial telemetry from the cancelled call
            main_scan_events=5000,
            events_new=0,
            events_existing=0,
        )
        assert r.reconciliation()["checked"] is False
        assert r.reconciles() is True
        assert r.verdict() == "fetch_wall"

    def test_reconciliation_is_serialized(self):
        r = KalshiScanReport(stop_reason="exhausted", wrapped=True)
        assert r.to_dict()["reconciliation"] == r.reconciliation()

    def test_summary_counts_readable_beats_not_bare_runs(self):
        good = KalshiScanReport(
            stop_reason="max_pages",
            events_fetched=10,
            main_scan_events=10,
            events_new=4,
            events_existing=6,
            events_processed=10,
        ).to_dict()
        bad = KalshiScanReport(
            stop_reason="max_pages",
            events_fetched=5,
            main_scan_events=5,
            events_new=4,
            events_existing=6,
            events_processed=10,
        ).to_dict()
        s = summarize_history([good, bad])
        assert s["runs"] == 2
        assert s["readable_beats"] == 1
        assert s["runs_not_reconciling"] == 1
        assert s["arithmetic_ok"] is False

    def test_pre_fix_beats_count_as_unknown_never_as_passing(self):
        """A beat written before the invariant cannot vouch for itself.

        The >=3-beat gate must not be satisfiable by beats that predate the
        thing being checked — that is the same false-green the whole report
        exists to prevent.
        """
        legacy = {
            "stop_reason": "max_pages",
            "events_fetched": 5000,
            "events_new": 5335,
            "events_existing": 5075,
            "verdict": "frozen",
        }
        s = summarize_history([legacy])
        assert s["runs"] == 1
        assert s["readable_beats"] == 0
        assert s["runs_unknown_reconciliation"] == 1
        assert s["arithmetic_ok"] is False


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
