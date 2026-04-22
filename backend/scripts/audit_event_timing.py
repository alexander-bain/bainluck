#!/usr/bin/env python3
"""
Event timing quality audit for BainLuck.

Sweeps completed events from the production API and measures how well chart
start/end times align with actual game boundaries. Reports by sport and by
source coverage (ESPN+Odds API vs Odds-API-only).

Usage:
    cd backend
    python3 scripts/audit_event_timing.py

Options:
    --days N          Days of completed events to scan (default: 7)
    --sport KEY       Filter by sport key (e.g., basketball_nba)
    --event-id ID     Audit a single event
    --limit N         Max events to audit (default: 100)
    --verbose         Print per-event details
    --json            Output JSON report
    --save            Save results to audit_results/
    --compare         Compare against last timing audit baseline
"""

import argparse
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

API_BASE = "https://api.bainluck.com"
RESULTS_DIR = Path(__file__).parent / "audit_results"

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

SEVERITY_PENALTY = {
    SEVERITY_CRITICAL: 10,
    SEVERITY_WARNING: 3,
    SEVERITY_INFO: 1,
}

EXPECTED_DURATIONS_MIN = {
    "basketball": 150,
    "baseball": 195,
    "americanfootball": 210,
    "icehockey": 165,
    "soccer": 120,
    "mma": 180,
    "boxing": 150,
    "tennis": 180,
    "golf": 300,
    "lacrosse": 150,
}
DEFAULT_DURATION_MIN = 180


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AuditFinding:
    check: str
    severity: str
    category: str
    description: str
    details: dict = field(default_factory=dict)

    def __str__(self):
        icon = {"critical": "\U0001f534", "warning": "\U0001f7e1", "info": "\U0001f535"}
        return f"{icon.get(self.severity, '?')} [{self.check}] {self.description}"


@dataclass
class TimingMetrics:
    event_id: int = 0
    sport_key: str = ""
    home_team: str = ""
    away_team: str = ""
    commence_time: str = ""
    status: str = ""

    has_espn: bool = False
    has_statpal_end: bool = False
    espn_snapshot_count: int = 0
    odds_snapshot_count: int = 0
    win_prob_source_count: int = 0
    period_marker_count: int = 0

    data_start_offset_min: float = 0.0
    first_data_point: Optional[str] = None
    first_espn_point: Optional[str] = None

    data_end_offset_min: float = 0.0
    last_odds_point: Optional[str] = None
    last_espn_point: Optional[str] = None
    last_game_signal: Optional[str] = None
    smart_end_time: Optional[str] = None
    smart_end_accuracy_min: Optional[float] = None

    chart_duration_min: float = 0.0
    expected_duration_min: float = 0.0
    duration_ratio: float = 0.0

    max_gap_min: float = 0.0
    gap_count_5min: int = 0
    gap_count_10min: int = 0
    gaps: list = field(default_factory=list)

    odds_domain_start: Optional[str] = None
    odds_domain_end: Optional[str] = None
    score_domain_start: Optional[str] = None
    score_domain_end: Optional[str] = None
    domain_agreement: bool = True
    domain_start_diff_min: float = 0.0
    domain_end_diff_min: float = 0.0


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(path: str, params: dict = None) -> dict:
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_ts(ts_str: str) -> datetime:
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    return datetime.fromisoformat(ts_str)


def ts_diff_min(a: str, b: str) -> float:
    return abs((parse_ts(a) - parse_ts(b)).total_seconds()) / 60.0


# ---------------------------------------------------------------------------
# Event fetching
# ---------------------------------------------------------------------------

def fetch_completed_events(days: int, sport_filter: str = None, limit: int = 100) -> list[dict]:
    feed = api_get("/api/feed", {"limit": str(limit)})
    items = feed.get("items", [])

    events = []
    for item in items:
        data = item.get("data", {})
        if not data or not data.get("id"):
            continue
        status = data.get("status", "")
        if status not in ("completed", "closed"):
            continue

        sport = data.get("sport", "")
        sport_key = sport.get("key", "") if isinstance(sport, dict) else (sport or "")

        if sport_filter and not sport_key.startswith(sport_filter):
            continue

        events.append(data)

    return events[:limit]


# ---------------------------------------------------------------------------
# Timing analysis helpers
# ---------------------------------------------------------------------------

def get_expected_duration(sport_key: str) -> float:
    for prefix, dur in EXPECTED_DURATIONS_MIN.items():
        if sport_key.startswith(prefix):
            return dur
    return DEFAULT_DURATION_MIN


GAME_END_SOURCES = {"espn", "stat_model", "fangraphs", "mlb", "betting"}


def compute_smart_end_time(history: dict, commence_time: str = None) -> Optional[str]:
    """Replicates OddsChart.tsx smartEndTime logic server-side.

    Excludes kalshi/polymarket — they keep getting re-snapshotted after game end.
    Must stay in sync with frontend/components/OddsChart.tsx:210-242.
    """
    candidates = []

    espn_history = history.get("espn_history") or []
    if espn_history:
        candidates.append(espn_history[-1].get("timestamp"))

    win_prob_history = history.get("win_prob_history") or {}
    for source, points in win_prob_history.items():
        if points and source in GAME_END_SOURCES:
            candidates.append(points[-1].get("timestamp"))

    # aggregate_line excluded — it blends all sources including kalshi/polymarket,
    # so it extends to stale prediction market data.

    candidates = [c for c in candidates if c]

    if candidates:
        latest = max(candidates, key=lambda t: parse_ts(t))
        buffered = parse_ts(latest) + timedelta(minutes=2)
        return buffered.isoformat()

    # Fallback for Odds-API-only events: cap at commence_time + 4 hours.
    # Must stay in sync with frontend/components/OddsChart.tsx smartEndTime.
    if commence_time:
        fallback = parse_ts(commence_time) + timedelta(hours=4)
        return fallback.isoformat()

    return None


def analyze_gaps(timestamps: list[str]) -> tuple[float, int, int, list]:
    if len(timestamps) < 2:
        return 0.0, 0, 0, []

    sorted_ts = sorted(timestamps, key=lambda t: parse_ts(t))
    max_gap = 0.0
    count_5 = 0
    count_10 = 0
    gap_details = []

    for i in range(1, len(sorted_ts)):
        diff = (parse_ts(sorted_ts[i]) - parse_ts(sorted_ts[i - 1])).total_seconds() / 60.0
        if diff > max_gap:
            max_gap = diff
        if diff > 5.0:
            count_5 += 1
            gap_details.append({
                "start": sorted_ts[i - 1],
                "end": sorted_ts[i],
                "duration_min": round(diff, 1),
            })
        if diff > 10.0:
            count_10 += 1

    return max_gap, count_5, count_10, gap_details


def compute_score_domain(history: dict, commence_time: str) -> tuple[Optional[str], Optional[str]]:
    """Approximate the ScoreDifferentialChart's effective domain."""
    all_ts = []

    for pt in (history.get("score_history") or []):
        if pt.get("timestamp"):
            all_ts.append(pt["timestamp"])
    for pt in (history.get("espn_history") or []):
        if pt.get("home_score") is not None and pt.get("timestamp"):
            all_ts.append(pt["timestamp"])

    if not all_ts:
        return None, None

    sorted_ts = sorted(all_ts, key=lambda t: parse_ts(t))

    start = commence_time
    if sorted_ts and parse_ts(sorted_ts[0]) < parse_ts(commence_time):
        start = sorted_ts[0]

    return start, sorted_ts[-1]


# ---------------------------------------------------------------------------
# Per-event analysis
# ---------------------------------------------------------------------------

def analyze_event(event_data: dict) -> tuple[TimingMetrics, list[AuditFinding]]:
    findings = []
    m = TimingMetrics()

    eid = event_data.get("id")
    m.event_id = eid

    sport = event_data.get("sport", "")
    m.sport_key = sport.get("key", "") if isinstance(sport, dict) else (sport or "")
    m.home_team = event_data.get("home_team", "?")
    m.away_team = event_data.get("away_team", "?")
    m.commence_time = event_data.get("commence_time", "")
    m.status = event_data.get("status", "")

    try:
        history = api_get(f"/api/events/{eid}/history")
    except Exception as e:
        findings.append(AuditFinding(
            check="history_unavailable",
            severity=SEVERITY_CRITICAL,
            category="timing",
            description=f"Could not fetch history for {m.away_team} @ {m.home_team} (ID: {eid}): {e}",
            details={"event_id": eid},
        ))
        return m, findings

    odds_history = history.get("history") or []
    espn_history = history.get("espn_history") or []
    win_prob_history = history.get("win_prob_history") or {}
    score_history = history.get("score_history") or []
    period_markers = history.get("period_markers") or []
    aggregate_line = history.get("aggregate_line") or []

    # Source coverage
    m.has_espn = len(espn_history) > 0
    m.espn_snapshot_count = len(espn_history)
    m.odds_snapshot_count = len(odds_history)
    m.win_prob_source_count = len(win_prob_history)
    m.period_marker_count = len(period_markers)
    m.expected_duration_min = get_expected_duration(m.sport_key)

    # Check for statpal end time in event detail
    try:
        detail = api_get(f"/api/events/{eid}")
        end_time_str = detail.get("end_time") or detail.get("statpal_end_time")
        if end_time_str:
            m.has_statpal_end = True
    except Exception:
        detail = {}
        end_time_str = None

    # Collect ALL timestamps for gap analysis
    all_timestamps = set()
    for pt in odds_history:
        if pt.get("timestamp"):
            all_timestamps.add(pt["timestamp"])
    for pt in espn_history:
        if pt.get("timestamp"):
            all_timestamps.add(pt["timestamp"])
    for source_pts in win_prob_history.values():
        for pt in source_pts:
            if pt.get("timestamp"):
                all_timestamps.add(pt["timestamp"])

    if not all_timestamps or not m.commence_time:
        findings.append(AuditFinding(
            check="no_data_points",
            severity=SEVERITY_CRITICAL,
            category="timing",
            description=f"No data points for {m.away_team} @ {m.home_team} (ID: {eid})",
            details={"event_id": eid},
        ))
        return m, findings

    sorted_all = sorted(all_timestamps, key=lambda t: parse_ts(t))

    # --- Start timing ---
    commence_dt = parse_ts(m.commence_time)
    since_start_ts = [t for t in sorted_all if parse_ts(t) >= commence_dt]
    if since_start_ts:
        m.first_data_point = since_start_ts[0]
        m.data_start_offset_min = (parse_ts(since_start_ts[0]) - commence_dt).total_seconds() / 60.0
    else:
        m.first_data_point = sorted_all[0]
        m.data_start_offset_min = (parse_ts(sorted_all[0]) - commence_dt).total_seconds() / 60.0

    if espn_history:
        m.first_espn_point = espn_history[0].get("timestamp")

    # --- End timing ---
    if odds_history:
        m.last_odds_point = odds_history[-1].get("timestamp")
    if espn_history:
        m.last_espn_point = espn_history[-1].get("timestamp")

    # Smart end time (replicating frontend logic)
    m.smart_end_time = compute_smart_end_time(history, m.commence_time)

    # Last game signal = max of ESPN, win_prob, aggregate
    game_signal_ts = []
    if m.last_espn_point:
        game_signal_ts.append(m.last_espn_point)
    for pts in win_prob_history.values():
        if pts:
            game_signal_ts.append(pts[-1].get("timestamp"))
    if aggregate_line:
        game_signal_ts.append(aggregate_line[-1].get("timestamp"))
    game_signal_ts = [t for t in game_signal_ts if t]
    if game_signal_ts:
        m.last_game_signal = max(game_signal_ts, key=lambda t: parse_ts(t))

    # Data end offset: how much stale bookmaker data extends past last game signal
    if m.last_odds_point and m.last_game_signal:
        odds_end = parse_ts(m.last_odds_point)
        signal_end = parse_ts(m.last_game_signal)
        m.data_end_offset_min = max(0.0, (odds_end - signal_end).total_seconds() / 60.0)

    # Smart end accuracy vs statpal ground truth
    if end_time_str and m.smart_end_time:
        m.smart_end_accuracy_min = ts_diff_min(m.smart_end_time, end_time_str)

    # --- Duration ---
    effective_start = m.commence_time
    effective_end = m.smart_end_time or (m.last_odds_point or sorted_all[-1])
    m.chart_duration_min = (parse_ts(effective_end) - parse_ts(effective_start)).total_seconds() / 60.0
    if m.expected_duration_min > 0:
        m.duration_ratio = m.chart_duration_min / m.expected_duration_min

    # --- Gap analysis (only "Since Start" portion, matching frontend default) ---
    in_game_ts = [t for t in sorted_all if parse_ts(t) >= commence_dt]
    if m.smart_end_time:
        smart_end_dt = parse_ts(m.smart_end_time)
        in_game_ts = [t for t in in_game_ts if parse_ts(t) <= smart_end_dt]

    m.max_gap_min, m.gap_count_5min, m.gap_count_10min, m.gaps = analyze_gaps(in_game_ts)

    # --- Score chart domain comparison ---
    score_start, score_end = compute_score_domain(history, m.commence_time)
    m.score_domain_start = score_start
    m.score_domain_end = score_end

    # Odds chart domain: commence_time to smart_end (or last data point)
    m.odds_domain_start = m.commence_time
    m.odds_domain_end = m.smart_end_time or sorted_all[-1]

    if score_start and score_end and m.odds_domain_start and m.odds_domain_end:
        m.domain_start_diff_min = ts_diff_min(score_start, m.odds_domain_start)
        m.domain_end_diff_min = ts_diff_min(score_end, m.odds_domain_end)
        m.domain_agreement = m.domain_start_diff_min < 5.0 and m.domain_end_diff_min < 5.0
    elif not score_start:
        m.domain_agreement = False

    # --- Generate findings ---
    label = f"{m.away_team} @ {m.home_team} (ID: {eid})"

    if m.data_start_offset_min > 30:
        findings.append(AuditFinding(
            check="late_data_start",
            severity=SEVERITY_WARNING,
            category="timing",
            description=f"Data starts {m.data_start_offset_min:.0f}min after commence_time: {label}",
            details={"event_id": eid, "offset_min": round(m.data_start_offset_min, 1), "sport": m.sport_key},
        ))

    if m.data_end_offset_min > 20:
        sev = SEVERITY_CRITICAL if m.data_end_offset_min > 30 else SEVERITY_WARNING
        findings.append(AuditFinding(
            check="stale_data_tail",
            severity=sev,
            category="timing",
            description=f"Bookmaker data extends {m.data_end_offset_min:.0f}min past game end: {label}",
            details={"event_id": eid, "offset_min": round(m.data_end_offset_min, 1), "sport": m.sport_key, "has_espn": m.has_espn},
        ))

    if m.max_gap_min > 10:
        findings.append(AuditFinding(
            check="large_data_gap",
            severity=SEVERITY_WARNING,
            category="timing",
            description=f"Gap of {m.max_gap_min:.0f}min in chart data: {label}",
            details={"event_id": eid, "max_gap_min": round(m.max_gap_min, 1), "gap_count": m.gap_count_5min},
        ))

    if m.duration_ratio > 1.5:
        findings.append(AuditFinding(
            check="chart_too_long",
            severity=SEVERITY_WARNING,
            category="timing",
            description=f"Chart {m.chart_duration_min:.0f}min vs expected {m.expected_duration_min:.0f}min ({m.duration_ratio:.1f}x): {label}",
            details={"event_id": eid, "ratio": round(m.duration_ratio, 2), "sport": m.sport_key},
        ))

    if not m.domain_agreement:
        findings.append(AuditFinding(
            check="chart_domain_mismatch",
            severity=SEVERITY_WARNING,
            category="timing",
            description=f"Odds/score chart domains differ by {m.domain_end_diff_min:.0f}min (end): {label}",
            details={"event_id": eid, "start_diff": round(m.domain_start_diff_min, 1), "end_diff": round(m.domain_end_diff_min, 1)},
        ))

    if m.period_marker_count == 0:
        findings.append(AuditFinding(
            check="no_period_markers",
            severity=SEVERITY_CRITICAL if m.has_espn else SEVERITY_WARNING,
            category="timing",
            description=f"No game state indicators: {label}",
            details={"event_id": eid, "has_espn": m.has_espn, "sport": m.sport_key},
        ))

    return m, findings


# ---------------------------------------------------------------------------
# Aggregation and reporting
# ---------------------------------------------------------------------------

def aggregate_by_sport(all_metrics: list[TimingMetrics]) -> dict:
    by_sport = defaultdict(list)
    for m in all_metrics:
        by_sport[m.sport_key].append(m)

    result = {}
    for sport, metrics in sorted(by_sport.items()):
        n = len(metrics)
        espn_pct = sum(1 for m in metrics if m.has_espn) / n * 100 if n else 0
        result[sport] = {
            "count": n,
            "espn_pct": round(espn_pct, 0),
            "avg_start_offset": round(sum(m.data_start_offset_min for m in metrics) / n, 1) if n else 0,
            "avg_end_offset": round(sum(m.data_end_offset_min for m in metrics) / n, 1) if n else 0,
            "avg_max_gap": round(sum(m.max_gap_min for m in metrics) / n, 1) if n else 0,
            "avg_markers": round(sum(m.period_marker_count for m in metrics) / n, 1) if n else 0,
            "pct_with_gaps": round(sum(1 for m in metrics if m.gap_count_5min > 0) / n * 100, 0) if n else 0,
            "avg_duration_ratio": round(sum(m.duration_ratio for m in metrics) / n, 2) if n else 0,
        }
    return result


def aggregate_by_coverage(all_metrics: list[TimingMetrics]) -> dict:
    groups = {"ESPN + Odds API": [], "Odds API only": []}
    for m in all_metrics:
        key = "ESPN + Odds API" if m.has_espn else "Odds API only"
        groups[key].append(m)

    result = {}
    for label, metrics in groups.items():
        n = len(metrics)
        if n == 0:
            continue
        result[label] = {
            "count": n,
            "avg_end_offset": round(sum(m.data_end_offset_min for m in metrics) / n, 1),
            "avg_max_gap": round(sum(m.max_gap_min for m in metrics) / n, 1),
            "avg_markers": round(sum(m.period_marker_count for m in metrics) / n, 1),
            "avg_start_offset": round(sum(m.data_start_offset_min for m in metrics) / n, 1),
        }
    return result


def generate_recommendations(all_metrics: list[TimingMetrics]) -> list[str]:
    recs = []
    n = len(all_metrics)
    if n == 0:
        return recs

    with_ground_truth = [m for m in all_metrics if m.smart_end_accuracy_min is not None]
    if with_ground_truth:
        accuracies = sorted(m.smart_end_accuracy_min for m in with_ground_truth)
        median_acc = accuracies[len(accuracies) // 2]
        if median_acc > 10:
            recs.append(
                f"ADD completed_at COLUMN: smartEndTime median error is {median_acc:.1f}min vs ground truth. "
                "Add a completed_at column to Event, populated from StatPal/ESPN/staleness detection, "
                "and use it directly for chart end boundary."
            )

    odds_only = [m for m in all_metrics if not m.has_espn]
    if odds_only:
        avg_tail = sum(m.data_end_offset_min for m in odds_only) / len(odds_only)
        if avg_tail > 15:
            recs.append(
                f"CAP CHART END FOR ODDS-ONLY: Odds-only events average {avg_tail:.0f}min of stale data past game end. "
                "Use commence_time + expected_duration + 30min as a ceiling when no ESPN/win_prob signals exist."
            )

    pct_gaps = sum(1 for m in all_metrics if m.gap_count_5min > 0) / n * 100
    if pct_gaps > 30:
        recs.append(
            f"SURFACE GAP INDICATORS: {pct_gaps:.0f}% of events have 5min+ data gaps. "
            "Show a subtle 'data gap' indicator on charts where gaps > 5 min exist."
        )

    pct_no_markers = sum(1 for m in all_metrics if m.period_marker_count == 0) / n * 100
    if pct_no_markers > 20:
        recs.append(
            f"EXPAND PERIOD MARKERS: {pct_no_markers:.0f}% of completed events lack game state indicators. "
            "Derive period boundaries from score change patterns for non-ESPN events."
        )

    pct_mismatch = sum(1 for m in all_metrics if not m.domain_agreement) / n * 100
    if pct_mismatch > 10:
        recs.append(
            f"FIX CHART DOMAIN SYNC: {pct_mismatch:.0f}% of events have odds/score chart domain mismatch. "
            "Consider computing the domain server-side in the history endpoint."
        )

    return recs


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_summary(all_metrics: list[TimingMetrics], findings: list[AuditFinding],
                  by_sport: dict, by_coverage: dict, recommendations: list[str]):
    n = len(all_metrics)
    print()
    print("=" * 72)
    print(f"EVENT TIMING QUALITY AUDIT ({n} events)")
    print("=" * 72)

    # Health score
    penalty = sum(SEVERITY_PENALTY.get(f.severity, 0) for f in findings)
    score = max(0, 100 - penalty)
    crit = sum(1 for f in findings if f.severity == SEVERITY_CRITICAL)
    warn = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
    info = sum(1 for f in findings if f.severity == SEVERITY_INFO)
    print(f"Health Score: {score}/100")
    print(f"  \U0001f534 Critical: {crit}  \U0001f7e1 Warning: {warn}  \U0001f535 Info: {info}")
    print()

    # By sport table
    print(f"{'Sport':<28s} {'Events':>6s} {'ESPN%':>6s} {'Start\u00b1':>7s} {'End\u00b1':>7s} {'MaxGap':>7s} {'Markers':>8s} {'Dur\u00d7':>6s}")
    print("\u2500" * 72)
    for sport, stats in by_sport.items():
        short = sport[:27]
        print(f"{short:<28s} {stats['count']:>6d} {stats['espn_pct']:>5.0f}% "
              f"{stats['avg_start_offset']:>6.1f}m {stats['avg_end_offset']:>6.1f}m "
              f"{stats['avg_max_gap']:>6.1f}m {stats['avg_markers']:>7.1f} "
              f"{stats['avg_duration_ratio']:>5.2f}")
    print()

    # By coverage table
    print(f"{'Coverage':<24s} {'Events':>6s} {'Start\u00b1':>7s} {'End\u00b1':>7s} {'MaxGap':>7s} {'Markers':>8s}")
    print("\u2500" * 56)
    for label, stats in by_coverage.items():
        print(f"{label:<24s} {stats['count']:>6d} "
              f"{stats['avg_start_offset']:>6.1f}m {stats['avg_end_offset']:>6.1f}m "
              f"{stats['avg_max_gap']:>6.1f}m {stats['avg_markers']:>7.1f}")
    print()

    # Ground truth accuracy
    with_gt = [m for m in all_metrics if m.smart_end_accuracy_min is not None]
    if with_gt:
        accuracies = sorted(m.smart_end_accuracy_min for m in with_gt)
        median = accuracies[len(accuracies) // 2]
        p95 = accuracies[int(len(accuracies) * 0.95)] if len(accuracies) > 1 else accuracies[0]
        worst = accuracies[-1]
        print(f"GROUND TRUTH ({len(with_gt)} events with statpal_end_time)")
        print(f"  smartEndTime accuracy: median {median:.1f}m, p95 {p95:.1f}m, worst {worst:.1f}m")
        print()

    # Findings
    if findings:
        print(f"FINDINGS ({len(findings)})")
        print("\u2500" * 72)
        for f in sorted(findings, key=lambda x: {"critical": 0, "warning": 1, "info": 2}.get(x.severity, 9)):
            print(f"  {f}")
        print()

    # Recommendations
    if recommendations:
        print("RECOMMENDATIONS")
        print("\u2500" * 72)
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")
        print()


def print_verbose_event(m: TimingMetrics, findings: list[AuditFinding]):
    label = f"{m.away_team} @ {m.home_team}"
    espn_tag = " [ESPN]" if m.has_espn else ""
    finding_icons = ""
    if findings:
        crit = sum(1 for f in findings if f.severity == SEVERITY_CRITICAL)
        warn = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
        if crit:
            finding_icons += f" \U0001f534\u00d7{crit}"
        if warn:
            finding_icons += f" \U0001f7e1\u00d7{warn}"

    print(f"  [{m.sport_key:>22s}] {label:<45s}{espn_tag}{finding_icons}")
    print(f"    Start\u00b1: {m.data_start_offset_min:>5.1f}m  End\u00b1: {m.data_end_offset_min:>5.1f}m  "
          f"MaxGap: {m.max_gap_min:>5.1f}m  Markers: {m.period_marker_count}  "
          f"Duration: {m.chart_duration_min:.0f}m ({m.duration_ratio:.2f}\u00d7)")
    if m.smart_end_accuracy_min is not None:
        print(f"    Ground truth error: {m.smart_end_accuracy_min:.1f}m")
    if not m.domain_agreement:
        print(f"    \u26a0\ufe0f  Chart domain mismatch: start {m.domain_start_diff_min:.1f}m, end {m.domain_end_diff_min:.1f}m")


# ---------------------------------------------------------------------------
# Baseline save/load/compare
# ---------------------------------------------------------------------------

def save_baseline(all_metrics: list[TimingMetrics], findings: list[AuditFinding],
                  by_sport: dict, by_coverage: dict, recommendations: list[str]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=None).strftime("%Y%m%d_%H%M%S")

    penalty = sum(SEVERITY_PENALTY.get(f.severity, 0) for f in findings)
    score = max(0, 100 - penalty)

    data = {
        "timestamp": datetime.now(tz=None).isoformat(),
        "type": "timing_audit",
        "event_count": len(all_metrics),
        "health_score": score,
        "by_sport": by_sport,
        "by_coverage": by_coverage,
        "recommendations": recommendations,
        "findings": [
            {"check": f.check, "severity": f.severity, "category": f.category,
             "description": f.description, "details": f.details}
            for f in findings
        ],
        "metrics": [
            {k: v for k, v in asdict(m).items() if k != "gaps"}
            for m in all_metrics
        ],
    }

    path = RESULTS_DIR / f"timing_{ts}.json"
    path.write_text(json.dumps(data, indent=2, default=str))

    latest = RESULTS_DIR / "timing_latest.json"
    latest.write_text(json.dumps(data, indent=2, default=str))

    return path


def load_baseline() -> Optional[dict]:
    latest = RESULTS_DIR / "timing_latest.json"
    if latest.exists():
        return json.loads(latest.read_text())
    return None


def print_comparison(current_score: int, baseline: dict):
    prev_score = baseline.get("health_score", 100)
    prev_count = baseline.get("event_count", 0)
    prev_ts = baseline.get("timestamp", "unknown")

    delta = current_score - prev_score
    arrow = "\u2191" if delta > 0 else "\u2193" if delta < 0 else "\u2192"
    print(f"  vs last run ({prev_ts[:16]}, {prev_count} events): {prev_score}/100 {arrow} {current_score}/100 ({delta:+d})")

    # Compare by-sport
    prev_sport = baseline.get("by_sport", {})
    current_findings = set()
    prev_findings = set()
    # Simple: compare finding counts
    for f in baseline.get("findings", []):
        prev_findings.add(f"{f.get('check')}|{f.get('details', {}).get('event_id', '')}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Event timing quality audit for BainLuck",
        epilog="""
Examples:
  python3 scripts/audit_event_timing.py
  python3 scripts/audit_event_timing.py --days 7 --save --verbose
  python3 scripts/audit_event_timing.py --sport basketball_nba
  python3 scripts/audit_event_timing.py --event-id 12345 --verbose
  python3 scripts/audit_event_timing.py --compare
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--days", type=int, default=7, help="Days of history (default: 7)")
    parser.add_argument("--sport", help="Filter by sport key prefix (e.g., basketball_nba)")
    parser.add_argument("--event-id", type=int, help="Audit a single event")
    parser.add_argument("--limit", type=int, default=100, help="Max events (default: 100)")
    parser.add_argument("--verbose", action="store_true", help="Print per-event details")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--save", action="store_true", help="Save results as baseline")
    parser.add_argument("--compare", action="store_true", help="Compare against last baseline")
    args = parser.parse_args()

    # Fetch events
    if args.event_id:
        print(f"Auditing single event: {args.event_id}")
        try:
            event_data = api_get(f"/api/events/{args.event_id}")
            events = [event_data]
        except Exception as e:
            print(f"ERROR: Could not fetch event {args.event_id}: {e}")
            sys.exit(1)
    else:
        print(f"Fetching completed events (last {args.days} days, limit {args.limit})...")
        events = fetch_completed_events(args.days, args.sport, args.limit)
        print(f"Found {len(events)} completed events")

    if not events:
        print("No completed events found.")
        sys.exit(0)

    # Analyze each event
    all_metrics = []
    all_findings = []

    for i, ev in enumerate(events):
        metrics, findings = analyze_event(ev)
        all_metrics.append(metrics)
        all_findings.extend(findings)

        if args.verbose:
            print_verbose_event(metrics, findings)

        if i < len(events) - 1:
            time.sleep(0.5)

    # Aggregate
    by_sport = aggregate_by_sport(all_metrics)
    by_coverage = aggregate_by_coverage(all_metrics)
    recommendations = generate_recommendations(all_metrics)

    # Output
    if args.json:
        penalty = sum(SEVERITY_PENALTY.get(f.severity, 0) for f in all_findings)
        score = max(0, 100 - penalty)
        output = {
            "event_count": len(all_metrics),
            "health_score": score,
            "by_sport": by_sport,
            "by_coverage": by_coverage,
            "recommendations": recommendations,
            "findings": [
                {"check": f.check, "severity": f.severity, "description": f.description, "details": f.details}
                for f in all_findings
            ],
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print_summary(all_metrics, all_findings, by_sport, by_coverage, recommendations)

    # Comparison
    if args.compare:
        baseline = load_baseline()
        if baseline:
            penalty = sum(SEVERITY_PENALTY.get(f.severity, 0) for f in all_findings)
            print_comparison(max(0, 100 - penalty), baseline)
        else:
            print("  (no previous timing baseline found)")

    # Save
    if args.save:
        path = save_baseline(all_metrics, all_findings, by_sport, by_coverage, recommendations)
        print(f"Baseline saved: {path}")


if __name__ == "__main__":
    main()
