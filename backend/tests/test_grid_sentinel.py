"""Tests for the Grid Sentinel (Queue #196).

The whole point is RED == REAL: the raw grid health score cried wolf on
blend-hidden source disagreement (mlb-66 was 67/100 with ZERO real defects).
These tests lock in the classification that fixes it — plausibility findings are
WATCH (never RED), seasonal structural findings are EXPLAINED in a quiet window,
and only genuine corruption / impossible values file — plus the ground-truth
envelope self-check and its two false-positive guards (noise-floor sources,
inversion correction).
"""

import importlib
from datetime import datetime, timezone

# Import the MODULE explicitly — `app.tasks.grid_sentinel` as a bare attribute
# resolves to the Celery task object of the same name registered in
# app/tasks/__init__.py, which shadows the module. importlib gets the module.
gs = importlib.import_module("app.tasks.grid_sentinel")


def _d(month, day):
    return datetime(2026, month, day, 12, 0, tzinfo=timezone.utc)


def _cell(merged, sources, trend=None):
    return {"merged_probability": merged, "sources": sources, "trend_24h": trend}


def _src(source, prob, name="m"):
    return {"source": source, "probability": prob, "market_name": name}


def _grid(teams, columns):
    return {"teams": teams, "columns": [{"key": k, "label": k} for k in columns],
            "sources_available": ["kalshi", "polymarket", "odds_api"]}


# ---------------------------------------------------------------------------
# Envelope invariant (the ground-truth self-check) + false-positive guards
# ---------------------------------------------------------------------------
class TestEnvelopeInvariant:
    def test_median_of_two_sources_is_inside(self):
        # The Braves NL-East case: [51.5%, 81.5%] median 66.5% — MUST NOT flag.
        # (Regression: an earlier noise-floor filter dropped the 51.5% and flagged.)
        grid = _grid([
            {"name": "Braves", "cells": {"division": _cell(
                0.665, [_src("polymarket", 0.515), _src("kalshi", 0.815)])}},
        ], ["division"])
        findings, stats = gs.check_envelope_invariant(grid, "mlb")
        assert findings == []
        assert stats["cells_self_checked"] == 1

    def test_outlier_drop_min_is_inside(self):
        # 2-source >10x outlier drop returns the low value — inside [lo, hi].
        grid = _grid([
            {"name": "Hawks", "cells": {"championship": _cell(
                0.0187, [_src("odds_api", 0.0187), _src("kalshi", 0.4727)])}},
        ], ["championship"])
        findings, _ = gs.check_envelope_invariant(grid, "nba")
        assert findings == []

    def test_single_source_corruption_flags(self):
        # One source at 81.5% but merged 66.5% — no blend can produce this.
        grid = _grid([
            {"name": "X", "cells": {"division": _cell(0.665, [_src("kalshi", 0.815)])}},
        ], ["division"])
        findings, _ = gs.check_envelope_invariant(grid, "mlb")
        assert len(findings) == 1
        assert findings[0]["check"] == "grid_envelope_violation"
        assert findings[0]["severity"] == "critical"
        assert findings[0]["seasonal_ok"] is False  # never excusable

    def test_inversion_corrected_multi_source_is_tolerated(self):
        # Sources [0.9, 0.1] (one is the "No" side); pipeline inverts → merged 0.9,
        # which sits in the reflected envelope. Multi-source → NOT flagged.
        grid = _grid([
            {"name": "Y", "cells": {"championship": _cell(
                0.9, [_src("kalshi", 0.9), _src("polymarket", 0.1)])}},
        ], ["championship"])
        findings, _ = gs.check_envelope_invariant(grid, "nba")
        assert findings == []

    def test_genuine_multi_source_corruption_flags(self):
        # merged 0.30 with sources [0.70, 0.80] is outside both [0.70,0.80] and the
        # reflected [0.20,0.30]... 0.30 is inside reflected → NOT flagged. Use 0.45.
        grid = _grid([
            {"name": "Z", "cells": {"championship": _cell(
                0.45, [_src("kalshi", 0.70), _src("polymarket", 0.80)])}},
        ], ["championship"])
        findings, _ = gs.check_envelope_invariant(grid, "nba")
        assert len(findings) == 1


# ---------------------------------------------------------------------------
# Structural checks
# ---------------------------------------------------------------------------
class TestStructuralChecks:
    def test_empty_grid_is_critical(self):
        f = gs.check_teams_present(_grid([], ["championship"]), "mlb")
        assert len(f) == 1 and f[0]["check"] == "grid_empty"
        assert f[0]["seasonal_ok"] is False

    def test_missing_teams_is_seasonal(self):
        teams = [{"name": f"t{i}", "cells": {}} for i in range(20)]
        f = gs.check_teams_present(_grid(teams, ["championship"]), "mlb")
        assert len(f) == 1 and f[0]["check"] == "grid_missing_teams"
        assert f[0]["seasonal_ok"] is True

    def test_full_roster_no_finding(self):
        teams = [{"name": f"t{i}", "cells": {}} for i in range(30)]
        assert gs.check_teams_present(_grid(teams, ["championship"]), "mlb") == []

    def test_monotonicity_violation_always_real(self):
        grid = _grid([
            {"name": "T", "cells": {
                "pennant": _cell(0.20, [_src("kalshi", 0.20)]),
                "championship": _cell(0.40, [_src("kalshi", 0.40)]),  # later > earlier
            }},
        ], ["pennant", "championship"])
        f = gs.check_monotonicity(grid, "mlb")
        assert len(f) == 1
        assert f[0]["severity"] == "critical" and f[0]["seasonal_ok"] is False

    def test_monotonicity_ok_within_eps(self):
        grid = _grid([
            {"name": "T", "cells": {
                "pennant": _cell(0.40, [_src("kalshi", 0.40)]),
                "championship": _cell(0.41, [_src("kalshi", 0.41)]),  # +1pp within eps
            }},
        ], ["pennant", "championship"])
        assert gs.check_monotonicity(grid, "mlb") == []

    def test_prob_sum_over_100_is_real(self):
        teams = [{"name": f"t{i}", "cells": {"championship": _cell(0.10, [_src("kalshi", 0.10)])}}
                 for i in range(13)]  # sums to 130%
        f = gs.check_prob_sum(_grid(teams, ["championship"]), "nba")
        assert len(f) == 1
        assert f[0]["seasonal_ok"] is False  # over-count never excusable

    def test_prob_sum_under_100_is_seasonal(self):
        teams = [{"name": f"t{i}", "cells": {"championship": _cell(0.10, [_src("kalshi", 0.10)])}}
                 for i in range(8)]  # sums to 80%
        f = gs.check_prob_sum(_grid(teams, ["championship"]), "nba")
        assert len(f) == 1
        assert f[0]["seasonal_ok"] is True  # incomplete coverage excusable when quiet

    def test_fill_rate_low_is_seasonal(self):
        teams = [{"name": f"t{i}", "cells": ({"championship": _cell(0.1, [_src("kalshi", 0.1)])}
                                             if i < 3 else {})} for i in range(30)]
        f = gs.check_fill_rate(_grid(teams, ["championship"]), "nba")
        assert len(f) == 1 and f[0]["seasonal_ok"] is True


# ---------------------------------------------------------------------------
# Plausibility checks → WATCH
# ---------------------------------------------------------------------------
class TestPlausibility:
    def test_source_disagreement_is_watch_tier(self):
        grid = _grid([
            {"name": "T", "cells": {"make_playoffs": _cell(
                0.325, [_src("polymarket", 0.20), _src("kalshi", 0.45)])}},
        ], ["make_playoffs"])
        f = gs.check_source_disagreement(grid, "mlb")
        assert len(f) == 1
        assert f[0]["tier"] == "plausibility"
        assert f[0]["check"] == "grid_source_disagreement"

    def test_extreme_disagreement_flagged_but_plausibility(self):
        grid = _grid([
            {"name": "Hawks", "cells": {"championship": _cell(
                0.02, [_src("odds_api", 0.02), _src("kalshi", 0.47)])}},
        ], ["championship"])
        f = gs.check_source_disagreement(grid, "nba")
        assert len(f) == 1
        assert f[0]["check"] == "grid_source_disagreement_extreme"
        assert f[0]["tier"] == "plausibility"

    def test_noise_floor_sources_not_disagreement(self):
        # Two illiquid ~0.50 defaults are not a real divergence.
        grid = _grid([
            {"name": "T", "cells": {"championship": _cell(
                0.50, [_src("kalshi", 0.49), _src("polymarket", 0.51)])}},
        ], ["championship"])
        assert gs.check_source_disagreement(grid, "nba") == []

    def test_illiquid_extreme_is_watch(self):
        grid = _grid([
            {"name": "T", "cells": {"division": _cell(1.0, [_src("polymarket", 1.0)])}},
        ], ["division"])
        f = gs.check_illiquid_extremes(grid, "nhl")
        assert len(f) == 1 and f[0]["tier"] == "plausibility"


# ---------------------------------------------------------------------------
# Artifact registry — REAL vs EXPLAINED vs WATCH
# ---------------------------------------------------------------------------
class TestClassifyFindings:
    def test_plausibility_always_watch(self):
        findings = [gs._finding("grid_source_disagreement", "info", "gap",
                                seasonal_ok=True, tier="plausibility")]
        # Even in-season, plausibility never goes RED.
        out = gs.classify_findings(findings, "mlb", _d(5, 1))
        assert out["real"] == [] and len(out["watch"]) == 1

    def test_seasonal_structural_explained_when_quiet(self):
        findings = [gs._finding("grid_missing_column", "warning", "no make_playoffs",
                                seasonal_ok=True, tier="structural")]
        out = gs.classify_findings(findings, "nba", _d(7, 14))  # offseason
        assert out["explained"] and out["real"] == []

    def test_seasonal_structural_real_when_active(self):
        findings = [gs._finding("grid_fill_rate", "critical", "low fill",
                                seasonal_ok=True, tier="structural")]
        out = gs.classify_findings(findings, "mlb", _d(5, 1))  # in season
        assert out["real"] and out["explained"] == []

    def test_non_seasonal_always_real(self):
        findings = [gs._finding("grid_monotonicity", "critical", "impossible",
                                seasonal_ok=False, tier="structural")]
        out = gs.classify_findings(findings, "nba", _d(7, 14))  # offseason
        assert out["real"] and out["explained"] == []

    def test_verdict_red_when_real(self):
        out = {"real": [{"x": 1}], "explained": [], "watch": []}
        assert gs.grid_verdict(out) == "red"

    def test_verdict_green_when_only_watch_and_explained(self):
        out = {"real": [], "explained": [{"x": 1}], "watch": [{"y": 2}]}
        assert gs.grid_verdict(out) == "green"


# ---------------------------------------------------------------------------
# Freshness self-check findings
# ---------------------------------------------------------------------------
class TestFreshness:
    def test_stale_when_active_is_real(self):
        fresh = {"newest": "2026-05-01T00:00:00+00:00", "age_hours": 30.0,
                 "stale": True, "seasonal_ok": False}
        f = gs.freshness_findings(fresh, "mlb")
        assert len(f) == 1 and f[0]["seasonal_ok"] is False

    def test_no_open_futures_when_active_is_critical(self):
        fresh = {"newest": None, "age_hours": None, "stale": True, "seasonal_ok": False}
        f = gs.freshness_findings(fresh, "mlb")
        assert len(f) == 1 and f[0]["check"] == "grid_no_open_futures"

    def test_skipped_no_finding(self):
        assert gs.freshness_findings({"skipped": True}, "mlb") == []

    def test_fresh_no_finding(self):
        fresh = {"newest": "x", "age_hours": 2.0, "stale": False, "seasonal_ok": False}
        assert gs.freshness_findings(fresh, "mlb") == []


# ---------------------------------------------------------------------------
# Filing helpers
# ---------------------------------------------------------------------------
class TestFilingHelpers:
    def test_fingerprint_stable_and_per_league(self):
        assert gs.grid_fingerprint("mlb") == gs.grid_fingerprint("mlb")
        assert gs.grid_fingerprint("mlb") != gs.grid_fingerprint("nba")
        assert len(gs.grid_fingerprint("mlb")) == 12

    def test_severity_p1_on_critical(self):
        assert gs.severity_for_grid([{"severity": "critical"}]) == "P1"
        assert gs.severity_for_grid([{"severity": "warning"}]) == "P2"

    def test_issue_body_has_fingerprint_and_sections(self):
        classified = {
            "league": "mlb", "phase": "in_season",
            "real": [{"severity": "critical", "detail": "envelope broke"}],
            "explained": [{"detail": "missing col", "explained_by": "offseason"}],
            "watch": [{"check": "grid_source_disagreement_extreme", "detail": "45pp gap"}],
        }
        body = gs.build_grid_issue_body(classified)
        assert "grid-sentinel-fingerprint:" in body
        assert "envelope broke" in body
        assert "45pp gap" in body  # extreme watch surfaced

    def test_title_reports_counts(self):
        title = gs.build_grid_issue_title("nba", [{"severity": "critical"}, {"severity": "warning"}])
        assert "NBA" in title and "2 real" in title
