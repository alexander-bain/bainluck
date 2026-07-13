"""Unit tests for the Flow Sentinel (#1078) pure logic.

These cover the per-flow correctness predicates and the evidence-pack rendering —
the parts that decide whether a flow passed, which entities regressed, whether an
event is a duplicate, and what the filed issue says. The live HTTP flows + httpx
filing are exercised via the admin inline endpoint / a live run, not here.
"""

from app.tasks.flow_sentinel import (
    CANARY_QUERY,
    GOLD_SET,
    build_flow_issue_body,
    build_flow_issue_title,
    chart_density_verdict,
    event_dup_key,
    feed_quality_failures,
    find_duplicate_events,
    flow_fingerprint,
    future_settled_events,
    game_markets_empty,
    gold_set_recoveries,
    gold_set_regressions,
    search_found,
    severity_for_flow,
    stale_live_events,
)


class TestGoldSet:
    def test_frozen_25_entities(self):
        assert len(GOLD_SET) == 25

    def test_baseline_bucket_split(self):
        # 14 expected-found (OK + UNREADABLE), 11 expected-miss (UNFINDABLE + MISSING)
        found = sum(1 for _, e in GOLD_SET if e)
        assert found == 14
        assert len(GOLD_SET) - found == 11


class TestSearchFound:
    def test_found_via_futures(self):
        assert search_found({"futures": [{"id": 1}], "results": [], "event_concepts": []}) is True

    def test_found_via_concept(self):
        assert search_found({"event_concepts": [{"key": "event:golf:x"}]}) is True

    def test_not_found_when_all_empty(self):
        assert search_found({"futures": [], "results": [], "event_concepts": [],
                             "futures_families": []}) is False

    def test_not_found_non_dict(self):
        assert search_found(None) is False


class TestRegressionsAndRecoveries:
    def _results(self):
        return [
            {"query": "nba champion", "expected_found": True, "found": True},    # ok
            {"query": "world series", "expected_found": True, "found": False},   # REGRESSION
            {"query": "lebron james", "expected_found": False, "found": False},  # known miss
            {"query": "masters winner", "expected_found": False, "found": True}, # RECOVERY
        ]

    def test_regression_is_expected_found_now_missing(self):
        regs = gold_set_regressions(self._results())
        assert [r["query"] for r in regs] == ["world series"]

    def test_recovery_is_expected_miss_now_found(self):
        recs = gold_set_recoveries(self._results())
        assert [r["query"] for r in recs] == ["masters winner"]

    def test_healthy_baseline_has_no_regressions(self):
        # every entity resolving to its baseline expectation → zero regressions
        results = [{"query": q, "expected_found": e, "found": e} for q, e in GOLD_SET]
        assert gold_set_regressions(results) == []


class TestDuplicateEvents:
    def test_same_game_twice_is_duplicate(self):
        events = [
            {"id": 1, "sport": "baseball_mlb", "home_team": "Dodgers",
             "away_team": "Padres", "commence_time": "2026-07-13T23:10:00Z"},
            {"id": 2, "sport": "baseball_mlb", "home_team": "Padres",  # home/away swapped
             "away_team": "Dodgers", "commence_time": "2026-07-13T23:10:00Z"},
        ]
        dups = find_duplicate_events(events)
        assert len(dups) == 1
        assert sorted(dups[0]["event_ids"]) == [1, 2]

    def test_distinct_games_not_duplicate(self):
        events = [
            {"id": 1, "sport": "baseball_mlb", "home_team": "Dodgers",
             "away_team": "Padres", "commence_time": "2026-07-13T23:10:00Z"},
            {"id": 2, "sport": "baseball_mlb", "home_team": "Yankees",
             "away_team": "Red Sox", "commence_time": "2026-07-13T23:10:00Z"},
        ]
        assert find_duplicate_events(events) == []

    def test_doubleheader_different_times_not_duplicate(self):
        # Same teams, same DAY, DIFFERENT start times → legit doubleheader, NOT a
        # duplicate (minute-granularity key must not false-positive these).
        events = [
            {"id": 1, "sport": "baseball_mlb", "home_team": "Cubs",
             "away_team": "Reds", "commence_time": "2026-07-13T17:10:00Z"},
            {"id": 2, "sport": "baseball_mlb", "home_team": "Cubs",
             "away_team": "Reds", "commence_time": "2026-07-13T20:40:00Z"},
        ]
        assert find_duplicate_events(events) == []

    def test_missing_fields_skipped_not_false_positive(self):
        events = [{"id": 1, "sport": "baseball_mlb", "home_team": "", "away_team": "",
                   "commence_time": None}] * 2
        assert event_dup_key(events[0]) is None
        assert find_duplicate_events(events) == []


class TestResolvedState:
    def _now(self):
        from datetime import datetime, timezone
        return datetime(2026, 7, 13, 22, 0, tzinfo=timezone.utc)

    def test_stale_live_flagged(self):
        events = [
            {"id": 1, "status": "live", "sport": "baseball_mlb",
             "home_team": "A", "away_team": "B", "commence_time": "2026-07-13T05:00:00Z"},  # 17h ago
            {"id": 2, "status": "live", "sport": "baseball_mlb",
             "home_team": "C", "away_team": "D", "commence_time": "2026-07-13T21:30:00Z"},  # 0.5h ago
        ]
        stale = stale_live_events(events, self._now(), max_age_hours=12.0)
        assert [s["event_id"] for s in stale] == [1]

    def test_completed_events_not_stale_live(self):
        # a completed event long past must NOT be flagged (only status='live' counts)
        events = [{"id": 9, "status": "completed", "sport": "baseball_mlb",
                   "home_team": "A", "away_team": "B", "commence_time": "2026-07-01T05:00:00Z"}]
        assert stale_live_events(events, self._now(), max_age_hours=12.0) == []

    def test_future_settled_flagged(self):
        events = [
            {"id": 1, "status": "completed", "sport": "nba", "home_team": "A", "away_team": "B",
             "commence_time": "2026-08-01T00:00:00Z"},  # settled but in the future
            {"id": 2, "status": "completed", "sport": "nba", "home_team": "C", "away_team": "D",
             "commence_time": "2026-07-12T00:00:00Z"},  # settled in the past (fine)
        ]
        fut = future_settled_events(events, self._now())
        assert [f["event_id"] for f in fut] == [1]


class TestGameMarketsEmpty:
    def test_all_sections_empty_is_empty(self):
        gm = {"event_id": 1, "totals": [], "player_props": [], "spreads": [],
              "matchups": [], "other": [], "pace": None}
        assert game_markets_empty(gm) is True

    def test_any_section_populated_is_not_empty(self):
        assert game_markets_empty({"spreads": [{"threshold": -1.5}]}) is False


class TestChartDensityVerdict:
    def test_below_threshold_passes(self):
        passed, ev = chart_density_verdict(
            {"overall_below_bar_pct": 87.2, "bar_points_per_hour": 1.0, "by_source": []}, 95.0)
        assert passed is True
        assert ev["overall_below_bar_pct"] == 87.2

    def test_above_threshold_fails(self):
        passed, _ = chart_density_verdict({"overall_below_bar_pct": 97.5}, 95.0)
        assert passed is False

    def test_missing_tile_fails_with_reason(self):
        passed, ev = chart_density_verdict({"error": "boom"}, 95.0)
        assert passed is False
        assert "reason" in ev


class TestFeedQualityFailures:
    def test_all_targets_met_no_failures(self):
        summary = {"boring_count": 0, "ladder_count": 0, "duplicate_family_count": 0,
                   "explanation_ok_count": 20}
        assert feed_quality_failures(summary, top_n=20) == []

    def test_target_misses_reported(self):
        summary = {"boring_count": 2, "ladder_count": 0, "duplicate_family_count": 1,
                   "explanation_ok_count": 18}
        metrics = {f["metric"] for f in feed_quality_failures(summary, top_n=20)}
        assert "boring-rate@20" in metrics
        assert "duplicate-family-rate@20" in metrics
        assert "explanation-coverage@20" in metrics
        assert "ladder-rate@20" not in metrics


class TestFingerprintAndSeverity:
    def test_fingerprint_stable_per_flow(self):
        assert flow_fingerprint("search_gold_set") == flow_fingerprint("search_gold_set")
        assert flow_fingerprint("search_gold_set") != flow_fingerprint("chart_density")

    def test_severity_broad_break_is_p1(self):
        assert severity_for_flow("search_gold_set", failed_count=6, checked=10) == "P1"

    def test_severity_narrow_break_is_p2(self):
        assert severity_for_flow("search_gold_set", failed_count=1, checked=10) == "P2"

    def test_chart_density_caps_at_p2(self):
        assert severity_for_flow("chart_density", failed_count=1, checked=1) == "P2"


class TestIssueRendering:
    def _failing_flow(self):
        return {
            "flow": "search_gold_set",
            "checked": 26,
            "passed": False,
            "failures": [{"query": CANARY_QUERY, "detail": "expected-found entity now returns nothing"}],
            "evidence": {"found": 14, "total": 26, "regressions": [CANARY_QUERY]},
        }

    def test_title_names_flow_and_counts(self):
        title = build_flow_issue_title(self._failing_flow())
        assert "Flow Sentinel" in title
        assert "search" in title.lower()

    def test_body_has_fingerprint_and_evidence(self):
        body = build_flow_issue_body(self._failing_flow())
        assert f"flow-sentinel-fingerprint:{flow_fingerprint('search_gold_set')}" in body
        assert "Failures" in body
        assert "Evidence" in body
