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


class TestBackfillTruncationIsRead:
    """The cutoff is truthful per beat (#3148); these say a READER can get it.

    The 24-beat ring of 2026-09-05 was `exhausted` + `healthy` on every beat
    while the market backfill was cut off on every beat. Both the one-word
    verdict and the across-beats summary have to say so, or the raw field is
    another number the code knows and nobody reads (#2214, #2927, #3149).
    """

    def _clean_walk(self, **kw):
        """A beat that is `healthy` on every axis except the one under test."""
        return _report(
            stop_reason="exhausted",
            events_new=10,
            events_existing=100,
            events_processed=110,
            unreached_existing=0,
            wrapped=True,
            pages_skipped=0,
            **kw,
        )

    def test_a_clean_walk_with_a_cut_backfill_is_not_healthy(self):
        r = self._clean_walk(market_backfill_truncated_after=467)
        assert r.verdict() == "backfill_starved"

    def test_a_backfill_that_never_started_is_not_healthy_either(self):
        """The other half of the same disease: candidates owed, none reached."""
        r = self._clean_walk(market_backfill_skipped_past_deadline=True)
        assert r.verdict() == "backfill_starved"

    def test_a_backfill_that_finished_its_list_stays_healthy(self):
        """`None` under a present field means it worked — not that it was cut."""
        r = self._clean_walk(market_backfill_truncated_after=None)
        assert r.verdict() == "healthy"

    def test_a_cut_backfill_never_outranks_a_starved_scan(self):
        """The main scan's own starvation is the worse reading and stays first."""
        r = _report(
            stop_reason="main_scan_deadline",
            events_new=10,
            events_existing=100,
            events_processed=110,
            unreached_existing=90,
            wrapped=False,
            market_backfill_truncated_after=467,
        )
        assert r.verdict() == "starved"

    def test_summary_counts_the_beats_that_were_cut(self):
        history = [
            {"market_backfill_truncated_after": 467, "market_backfill_candidates": 10901},
            {"market_backfill_truncated_after": 452, "market_backfill_candidates": 10420},
            {"market_backfill_truncated_after": None, "market_backfill_candidates": 12},
        ]
        s = summarize_history(history)
        assert s["runs_backfill_truncated"] == 2
        assert s["runs_backfill_complete"] == 1
        assert s["runs_backfill_unknown"] == 0
        assert s["backfill_truncated_after_max"] == 467
        assert s["backfill_truncated_every_measured_beat"] is False

    def test_summary_says_when_every_measured_beat_was_cut(self):
        history = [
            {"market_backfill_truncated_after": 400 + i, "market_backfill_candidates": 10901}
            for i in range(24)
        ]
        s = summarize_history(history)
        assert s["runs_backfill_truncated"] == 24
        assert s["backfill_truncated_every_measured_beat"] is True

    def test_a_beat_predating_the_field_is_unknown_not_complete(self):
        """Silence is absence of measurement, never proof of headroom."""
        history = [{"stop_reason": "exhausted", "wrapped": True}] * 5
        s = summarize_history(history)
        assert s["runs_backfill_unknown"] == 5
        assert s["runs_backfill_complete"] == 0
        assert s["backfill_truncated_every_measured_beat"] is False
        assert s["backfill_candidates_latest"] is None
        assert s["backfill_unreached_latest"] is None

    def test_summary_states_what_the_newest_beat_left_on_the_floor(self):
        """The #3149 number, off the newest beat that can say."""
        history = [
            {"market_backfill_truncated_after": 467, "market_backfill_candidates": 10901},
            {"market_backfill_truncated_after": 100, "market_backfill_candidates": 200},
        ]
        s = summarize_history(history)
        assert s["backfill_candidates_latest"] == 10901
        assert s["backfill_unreached_latest"] == 10434

    def test_a_finished_backfill_leaves_nothing_on_the_floor(self):
        history = [{"market_backfill_truncated_after": None, "market_backfill_candidates": 12}]
        s = summarize_history(history)
        assert s["backfill_unreached_latest"] == 0

    def test_the_newest_beat_that_can_say_is_the_one_read(self):
        """A ring whose newest entries predate the field still reports."""
        history = [
            {"stop_reason": "exhausted"},
            {"market_backfill_truncated_after": 467, "market_backfill_candidates": 10901},
        ]
        s = summarize_history(history)
        assert s["runs_backfill_unknown"] == 1
        assert s["backfill_candidates_latest"] == 10901
        assert s["backfill_unreached_latest"] == 10434


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


# ==========================================================================
# Queue 359 (#1586): the counter that actually explains the capture gap
# ==========================================================================


class TestMarketlessEventTelemetry:
    """13,513 events fetched, 356 processed — and no counter said why.

    The scan report's `unreached_existing` reads as "the loop ran out of time
    before the tail", and it is an artifact: it is derived as
    ``n_existing - max(0, processed - n_new)``, i.e. it treats
    ``events_processed`` as a POSITION in the fetched list. It is not a
    position — it is only incremented after a market upsert succeeds, and the
    loop's first statement is ``if not event.markets: continue``. Because
    ``processed`` (356) is always far below ``n_new`` (7,198), the clamp makes
    ``unreached_existing`` identically equal to ``events_existing`` on every
    beat, which is exactly what all 24 beats in the production ring show.
    ``loop_deadline_hit`` is False on all 24 — the loop reached everything.

    So the real number is how many fetched events carry no markets at all, and
    these tests keep it recorded.
    """

    def _source(self):
        import inspect

        from app.services.kalshi_api import KalshiAPIService

        return inspect.getsource(KalshiAPIService._fetch_all_events_unfiltered)

    def test_marketless_events_are_counted(self):
        src = self._source()
        assert '_tel["events_without_markets"]' in src
        assert "if not e.markets" in src

    def test_the_backfill_records_whether_it_ran_at_all(self):
        """A step that never executes and a step with nothing to do return the
        same silence (gotcha #53). One of them is a defect."""
        src = self._source()
        assert '_tel["market_backfill_candidates"]' in src
        assert '_tel["market_backfill_skipped_past_deadline"]' in src
        assert '_tel["market_backfill_filled"]' in src

    def test_a_skipped_backfill_is_loud(self):
        src = self._source()
        skipped = src.index("market_backfill_skipped_past_deadline")
        assert "logger.warning" in src[skipped:skipped + 900]

    def test_the_count_is_retaken_after_the_backfill_runs(self):
        """Reporting the pre-backfill number would credit the backfill with
        work it did not do."""
        src = self._source()
        assert src.count('_tel["events_without_markets"] = sum(') == 2
