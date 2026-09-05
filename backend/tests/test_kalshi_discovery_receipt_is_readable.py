"""The #2927 discovery receipt reaches a reader, not just a dict (#2927).

`test_kalshi_series_discovery.py::test_the_receipt_reaches_telemetry` was green
the whole time the receipt was unreadable. It asserted the producer end — the
fetch writes `_tel["series_discovery"]` — and there was no test of the consumer
end, so nothing noticed that `poll_kalshi_markets` built its `KalshiScanReport`
from an explicit keyword list that did not include the receipt. The measurement
was taken every beat and dropped on the floor.

That is the same defect the report's own `market_backfill_*` block was added to
fix one ship earlier ("the fields existed in the fetch's telemetry dict and no
caller ever copied them here"), and the same shape as lane1b/037: two green ends
around a chain that does not connect.

So these tests are named after the chain, not the ends. The invariant is that a
number measured on the dyno can be READ from the artifact a human opens —
`/api/admin/kalshi/scan-report`. A test that stops at the telemetry dict is the
test that already passed.
"""

import ast
import asyncio
import json
from pathlib import Path

import pytest

from app.utils.kalshi_scan_report import KalshiScanReport
from app.utils.kalshi_series_selection import (
    discovery_dead_series,
    summarize_discovery_receipt,
)


#: A receipt shaped exactly like the live one: scalars, the two nested
#: sub-receipts, and the bounded detail maps.
def _live_shaped_receipt(**over):
    receipt = {
        "source": "live",
        "discovered": 140,
        "with_open_events": 39,
        "selected": ["KXATPDOUBLES", "KXWTADOUBLES", "KXHONEYDEUCE"],
        "selected_count": 3,
        "selected_open_events": 61,
        "skipped": {"no_open_events": 101, "heavy_payload_shape": 8},
        "skipped_detail": {"KXATPSETWINNER": "heavy_payload_shape"},
        "dormant_sample": ["KXAAA", "KXBBB"],
        "catalog": {"tags": ["Tennis"], "per_tag": {"Tennis": 140}, "requests": 1},
        "census": {"pages": 72, "events": 14000, "series": 1263, "exhausted": True},
        "series_fetched": 3,
        "events_added": 207,
        "series_results": {
            "KXATPDOUBLES": {"expected": 32, "returned": 32, "unique_added": 32,
                             "truncated": False},
            "KXWTADOUBLES": {"expected": 30, "returned": 30, "unique_added": 30,
                             "truncated": False},
            "KXHONEYDEUCE": {"expected": 1, "returned": 1, "unique_added": 1,
                             "truncated": False},
        },
    }
    receipt.update(over)
    return receipt


def _results(**series):
    """A receipt whose only interesting content is its per-series results."""
    return _live_shaped_receipt(series_results=dict(series))


class TestTheReceiptSurvivesPersistence:
    """The projection keeps what a reader is here for."""

    def test_source_and_events_added_are_kept(self):
        """The two numbers the whole receipt exists to report."""
        out = summarize_discovery_receipt(_live_shaped_receipt())
        assert out["source"] == "live"
        assert out["events_added"] == 207

    def test_the_counters_that_explain_a_surprising_number_are_kept(self):
        out = summarize_discovery_receipt(_live_shaped_receipt())
        assert out["discovered"] == 140
        assert out["with_open_events"] == 39
        assert out["selected_count"] == 3
        assert out["selected_open_events"] == 61
        assert out["series_fetched"] == 3
        assert out["skipped"]["heavy_payload_shape"] == 8
        assert out["skipped_detail"]["KXATPSETWINNER"] == "heavy_payload_shape"

    def test_the_nested_sub_receipts_are_dropped(self):
        """48 ring entries of catalog+census detail bury the counters."""
        out = summarize_discovery_receipt(_live_shaped_receipt())
        assert "catalog" not in out
        assert "census" not in out
        assert "dormant_sample" not in out

    def test_but_census_exhaustion_survives_as_a_flag(self):
        """A partial census is the one thing that makes a small
        `selected_count` expected rather than alarming. A reader who cannot see
        it misreads the beat, so it is the one sub-receipt fact kept."""
        assert summarize_discovery_receipt(
            _live_shaped_receipt()
        )["census_exhausted"] is True
        assert summarize_discovery_receipt(
            _live_shaped_receipt(census={"exhausted": False})
        )["census_exhausted"] is False

    def test_a_failed_stage_keeps_its_error(self):
        out = summarize_discovery_receipt(
            {"source": "failed", "error": "TimeoutError: venue down"}
        )
        assert out["source"] == "failed"
        assert "venue down" in out["error"]

    def test_the_uncacheable_reason_survives(self):
        out = summarize_discovery_receipt(
            _live_shaped_receipt(not_cached="census_partial")
        )
        assert out["not_cached"] == "census_partial"

    def test_a_truncated_fetch_survives(self):
        """`fetch_truncated_after` is how a spent reserve names itself."""
        out = summarize_discovery_receipt(
            _live_shaped_receipt(fetch_truncated_after=2)
        )
        assert out["fetch_truncated_after"] == 2


class TestTheProjectionIsBounded:
    """A growing catalog must not turn telemetry into a memory problem."""

    def test_the_selected_list_is_capped_and_says_so(self):
        out = summarize_discovery_receipt(
            _live_shaped_receipt(selected=[f"KXS{i:03d}" for i in range(100)])
        )
        assert len(out["selected"]) == 24
        assert out["selected_truncated"] == 76

    def test_the_detail_map_is_capped_and_says_so(self):
        out = summarize_discovery_receipt(
            _live_shaped_receipt(
                skipped_detail={f"KXS{i:03d}": "heavy_payload_shape"
                                for i in range(100)}
            )
        )
        assert len(out["skipped_detail"]) == 24
        assert out["skipped_detail_truncated"] == 76

    def test_a_bounded_receipt_is_small_enough_for_48_ring_entries(self):
        """The ring keeps 48 of these in a shared 100MB Redis."""
        blob = json.dumps(
            summarize_discovery_receipt(
                _live_shaped_receipt(
                    selected=[f"KXSERIES{i:04d}" for i in range(500)],
                    skipped_detail={f"KXSERIES{i:04d}": "too_many_open_events"
                                    for i in range(500)},
                )
            )
        )
        assert len(blob) < 4096, f"persisted receipt is {len(blob)} bytes"


class TestTheProjectionNeverBreaksTheReportItRidesOn:
    """Telemetry that can fail its carrier is worse than no telemetry."""

    def test_an_absent_receipt_says_absent_rather_than_vanishing(self):
        """gotcha #53: the empty case must still be a reading."""
        assert summarize_discovery_receipt(None) == {"source": "absent"}
        assert summarize_discovery_receipt({}) == {"source": "absent"}

    def test_a_receipt_with_no_source_still_reports_one(self):
        assert summarize_discovery_receipt({"events_added": 3})["source"] == "unknown"

    def test_garbage_members_do_not_raise(self):
        out = summarize_discovery_receipt(
            {"source": "live", "selected": "not-a-list",
             "skipped": 7, "skipped_detail": None, "census": "nope"}
        )
        assert out["source"] == "live"

    def test_an_exploding_receipt_degrades_to_a_reading(self):
        class _Hostile(dict):
            def get(self, *a, **k):
                raise RuntimeError("boom")

        assert summarize_discovery_receipt(
            _Hostile(source="live")
        ) == {"source": "unsummarizable"}


class TestTheAlarmIsPerSeries:
    """CERT-953. The aggregate `events_added` fails in BOTH directions."""

    def test_a_dead_series_is_named_even_when_a_sibling_is_healthy(self):
        """The half-outage the aggregate hides: the men's draw vanishes off the
        site while the women's draw keeps the total non-zero."""
        dead = discovery_dead_series(_results(
            KXATPDOUBLES={"expected": 32, "returned": 0, "unique_added": 0},
            KXWTADOUBLES={"expected": 30, "returned": 30, "unique_added": 30},
        ))
        assert dead == ["KXATPDOUBLES"]

    def test_a_healthy_series_the_main_scan_already_held_does_not_alarm(self):
        """The false positive the aggregate invents: `unique_added == 0` only
        means we already had the events, which is not a fault."""
        assert discovery_dead_series(_results(
            KXATPDOUBLES={"expected": 32, "returned": 32, "unique_added": 0},
        )) == []

    def test_every_dead_series_is_named_not_just_the_first(self):
        dead = discovery_dead_series(_results(
            KXATPDOUBLES={"expected": 32, "returned": 0, "unique_added": 0},
            KXWTADOUBLES={"expected": 30, "returned": 0, "unique_added": 0},
            KXHONEYDEUCE={"expected": 1, "returned": 1, "unique_added": 1},
        ))
        assert dead == ["KXATPDOUBLES", "KXWTADOUBLES"]

    def test_an_errored_series_alarms_even_if_it_returned_something(self):
        assert discovery_dead_series(_results(
            KXATPDOUBLES={"expected": 32, "returned": 4, "unique_added": 4,
                          "error": "TimeoutError: venue down"},
        )) == ["KXATPDOUBLES"]

    def test_a_series_the_reserve_never_reached_does_not_alarm(self):
        """`fetch_truncated_after` already says this precisely. Alarming here
        turns a budget signal into a coverage alarm."""
        assert discovery_dead_series(_results(
            KXATPDOUBLES={"expected": 32, "returned": 0, "unique_added": 0,
                          "truncated": True},
        )) == []

    def test_a_parse_timeout_does_not_alarm_as_a_dead_draw(self):
        assert discovery_dead_series(_results(
            KXATPDOUBLES={"expected": 32, "returned": 0, "unique_added": 0,
                          "parse_failed": True},
        )) == []

    def test_a_series_the_census_said_was_empty_does_not_alarm(self):
        assert discovery_dead_series(_results(
            KXMIXEDDOUBLES={"expected": 0, "returned": 0, "unique_added": 0},
        )) == []

    def test_a_cache_served_beat_alarms_on_the_same_evidence(self):
        """A poisoned cache is the likeliest way this goes quiet, so a cached
        source must not be exempt."""
        assert discovery_dead_series(_results(
            KXATPDOUBLES={"expected": 32, "returned": 0, "unique_added": 0},
        ) | {"source": "cache"}) == ["KXATPDOUBLES"]

    def test_a_healthy_beat_is_silent(self):
        assert discovery_dead_series(_live_shaped_receipt()) == []

    def test_a_quiet_night_is_silent(self):
        """Firing every night the tournament is dark is how an alarm gets
        ignored on the night it matters."""
        assert discovery_dead_series(
            _live_shaped_receipt(selected_count=0, selected=[],
                                 events_added=0, series_results={})
        ) == []

    def test_stages_that_already_name_their_own_failure_do_not_fire(self):
        for source in ("not_wired", "disabled", "failed", "absent"):
            assert discovery_dead_series(
                _results(KXATPDOUBLES={"expected": 32, "returned": 0})
                | {"source": source}
            ) == [], source

    def test_it_never_raises(self):
        assert discovery_dead_series(None) == []
        assert discovery_dead_series({}) == []
        assert discovery_dead_series({"source": "live",
                                      "series_results": "nope"}) == []
        assert discovery_dead_series({"source": "live", "series_results": {
            "KXATPDOUBLES": {"expected": "many", "returned": None}}}) == []


class TestTheDeadSeriesSurvivePersistence:
    """A per-series result a reader cannot see is the original defect again."""

    def test_the_per_series_results_are_persisted(self):
        out = summarize_discovery_receipt(_live_shaped_receipt())
        assert out["series_results"]["KXATPDOUBLES"]["returned"] == 32
        assert out["series_results"]["KXATPDOUBLES"]["expected"] == 32

    def test_the_alarm_still_fires_off_the_PERSISTED_copy(self):
        """The projection is what the task reads. If the bounding dropped the
        fields the alarm needs, the alarm would go quiet on the real path while
        every unit test above stayed green."""
        persisted = summarize_discovery_receipt(_results(
            KXATPDOUBLES={"expected": 32, "returned": 0, "unique_added": 0},
            KXWTADOUBLES={"expected": 30, "returned": 30, "unique_added": 30},
        ))
        assert discovery_dead_series(persisted) == ["KXATPDOUBLES"]

    def test_a_dead_series_survives_the_cap_ahead_of_healthy_ones(self):
        """Bounded, but never at the cost of the reading that matters."""
        series = {f"KXHEALTHY{i:03d}": {"expected": 5, "returned": 5,
                                        "unique_added": 5} for i in range(100)}
        series["KXATPDOUBLES"] = {"expected": 32, "returned": 0,
                                  "unique_added": 0}
        persisted = summarize_discovery_receipt(_results(**series))
        assert "KXATPDOUBLES" in persisted["series_results"]
        assert discovery_dead_series(persisted) == ["KXATPDOUBLES"]

    def test_the_bound_still_holds_with_per_series_results(self):
        series = {f"KXSERIES{i:04d}": {"expected": 5, "returned": 0,
                                       "unique_added": 0, "truncated": False}
                  for i in range(500)}
        blob = json.dumps(summarize_discovery_receipt(_results(**series)))
        assert len(blob) < 4096, f"persisted receipt is {len(blob)} bytes"


class TestTheChainReachesTheArtifact:
    """The half that was missing. Each step is the one that was not tested."""

    def test_the_report_declares_the_field(self):
        assert "series_discovery" in KalshiScanReport.__dataclass_fields__

    def test_the_field_reaches_the_serialized_form(self):
        """`to_dict` is what `save_scan_report` persists and the admin
        endpoint returns — if the field stops here, no reader ever sees it."""
        report = KalshiScanReport(
            series_discovery=summarize_discovery_receipt(_live_shaped_receipt())
        )
        data = report.to_dict()
        assert data["series_discovery"]["source"] == "live"
        assert data["series_discovery"]["events_added"] == 207

    def test_the_serialized_form_is_json_round_trippable(self):
        """Redis stores JSON; a field that cannot serialize takes the whole
        report down (`save_scan_report` swallows, so the loss would be
        silent — which is how this class of bug survives)."""
        report = KalshiScanReport(
            series_discovery=summarize_discovery_receipt(_live_shaped_receipt())
        )
        revived = json.loads(json.dumps(report.to_dict()))
        assert revived["series_discovery"]["events_added"] == 207

    def test_a_report_built_without_a_receipt_still_serializes(self):
        assert KalshiScanReport().to_dict()["series_discovery"] == {}

    def test_the_poll_task_actually_copies_the_receipt_into_the_report(self):
        """THE guard. Every other test here passes with the bug present.

        The defect was never in the report or the receipt — both were correct.
        It was that the one call site joining them omitted the keyword, and no
        test looked at the call site. Parsed with `ast` rather than grepped so
        it survives reformatting and cannot be satisfied by the word appearing
        in a comment.
        """
        src = (Path(__file__).resolve().parents[1]
               / "app" / "tasks" / "kalshi.py").read_text()
        tree = ast.parse(src)

        constructions = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "KalshiScanReport"
        ]
        assert constructions, "poll_kalshi no longer builds a KalshiScanReport"

        for call in constructions:
            kwargs = {kw.arg for kw in call.keywords if kw.arg}
            assert "series_discovery" in kwargs, (
                "KalshiScanReport is built without series_discovery — the "
                "receipt is measured every beat and dropped on the floor "
                "again. This is the #2927 defect verbatim."
            )

    def test_the_task_also_alarms_on_a_dead_series(self):
        """The receipt being readable is not enough: nobody reads it nightly.
        The dead-draw case has to page itself."""
        src = (Path(__file__).resolve().parents[1]
               / "app" / "tasks" / "kalshi.py").read_text()
        tree = ast.parse(src)
        called = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "discovery_dead_series" in called


class TestTheRealFetchPathAlarmsCorrectly:
    """CERT-953's required catching test: the ACTUAL fetch, not a fixture.

    Every test above builds a receipt by hand. That is exactly how the aggregate
    bug survived — the hand-built receipt agreed with the hand-built theory. So
    these two drive the real `_fetch_all_events_unfiltered`, take whatever
    receipt it actually produces, push it through the real projection into a
    real `KalshiScanReport`, and ask the real alarm.
    """

    @pytest.fixture(autouse=True)
    def _no_pacing(self, monkeypatch):
        """Drop the inter-page politeness sleeps — same reason as the discovery
        suite's own fixture: the pacing is the venue's concern, the counters
        are ours, and paying it here makes this a 47s CI item."""
        real_sleep = asyncio.sleep

        async def _instant(delay, *a, **kw):
            return await real_sleep(0, *a, **kw)

        monkeypatch.setattr(asyncio, "sleep", _instant)

    @staticmethod
    def _fetch_then_report(svc):
        """fetch -> telemetry -> projection -> report -> serialized artifact."""
        tel: dict = {}
        asyncio.run(svc._fetch_all_events_unfiltered(
            deadline=None, telemetry=tel, save_discovery=lambda _p: None,
        ))
        report = KalshiScanReport(
            series_discovery=summarize_discovery_receipt(
                tel.get("series_discovery")
            )
        )
        # Round-trip through JSON: this is what Redis stores and what the admin
        # endpoint hands a reader, so the alarm is asked of that, not of a live
        # Python object that never left the process.
        return json.loads(json.dumps(report.to_dict()))["series_discovery"]

    def test_a_dead_doubles_draw_is_named_though_its_sibling_is_healthy(self):
        """The men's draw returns nothing; the women's draw returns its full 22.
        The aggregate would read `events_added > 0` and stay silent."""
        disc = _sd()
        svc = disc._FetchService(
            # Scope the census so these two are the ONLY selected series —
            # otherwise the other live tennis series return nothing (nothing is
            # configured for them) and are correctly flagged too, which would
            # let this test pass without proving anything about the sibling.
            census={"KXATPDOUBLES": 32, "KXWTADOUBLES": 22},
            per_series={
                "KXATPDOUBLES": [],
                "KXWTADOUBLES": [f"KXWTADOUBLES-26SEP05X{i}" for i in range(22)],
            },
        )
        persisted = self._fetch_then_report(svc)

        assert persisted["events_added"] > 0, (
            "precondition: the sibling must make the AGGREGATE look healthy, "
            "otherwise this test would pass under the old aggregate alarm too"
        )
        assert "KXATPDOUBLES" in discovery_dead_series(persisted)
        assert "KXWTADOUBLES" not in discovery_dead_series(persisted)

    def test_a_doubles_draw_the_main_scan_already_held_does_not_alarm(self):
        """Every event the discovered fetch returns is already in the map from
        the main scan, so unique additions are zero and nothing is wrong."""
        shared = [f"KXATPDOUBLES-26SEP05X{i}" for i in range(32)]
        disc = _sd()
        svc = disc._FetchService(
            census={"KXATPDOUBLES": 32},
            main_scan=shared,
            per_series={"KXATPDOUBLES": shared},
        )
        persisted = self._fetch_then_report(svc)

        result = (persisted.get("series_results") or {}).get("KXATPDOUBLES")
        assert result is not None, "the series must appear in the receipt"
        assert result["returned"] == 32
        assert result["unique_added"] == 0, (
            "precondition: unique additions must be zero, which is what would "
            "have tripped the aggregate alarm"
        )
        assert discovery_dead_series(persisted) == []


def _sd():
    """The discovery test module, imported lazily to keep its fixtures there."""
    import tests.test_kalshi_series_discovery as mod
    return mod
