#!/usr/bin/env python3
"""Market accuracy audit — validates monotonicity and cross-game contamination.

Uses Manus ground truth JSON from market_accuracy_ground_truth.md prompt.

Usage:
    # Validate against Manus ground truth
    python3 scripts/audit_market_accuracy.py --ground-truth path/to/gt.json

    # Self-check: scan live events for monotonicity violations
    python3 scripts/audit_market_accuracy.py --self-check --sport basketball_nba
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

API_BASE = "https://api.bainluck.com"


def api_get(path: str) -> dict:
    url = f"{API_BASE}{path}"
    with urlopen(url, timeout=30) as resp:
        return json.loads(resp.read())


def check_monotonicity(items: list[dict], prob_key: str = "over_probability") -> list[dict]:
    """Check if probabilities decrease as thresholds increase. Returns violations."""
    violations = []
    for i in range(1, len(items)):
        prev_prob = items[i - 1].get(prob_key)
        curr_prob = items[i].get(prob_key)
        prev_threshold = items[i - 1].get("threshold")
        curr_threshold = items[i].get("threshold")
        if prev_prob is not None and curr_prob is not None and curr_prob > prev_prob:
            violations.append({
                "threshold": curr_threshold,
                "probability": curr_prob,
                "prev_threshold": prev_threshold,
                "prev_probability": prev_prob,
                "delta": round(curr_prob - prev_prob, 4),
            })
    return violations


def self_check(sport: str | None = None):
    """Scan live/scheduled events for monotonicity violations and cross-game contamination signals."""
    print(f"\n{'=' * 60}")
    print(f"  MARKET ACCURACY SELF-CHECK")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    if sport:
        print(f"  Sport: {sport}")
    print(f"{'=' * 60}\n")

    # Get feed events
    data = api_get("/api/feed?limit=200")
    events = []
    for item in data.get("items", []):
        ev = item.get("data", {})
        ev_sport = ev.get("sport", "")
        if sport and ev_sport != sport:
            continue
        if ev.get("status") in ("live", "scheduled", "completed", "closed"):
            events.append(ev)

    print(f"  Events: {len(events)}")

    total_violations = 0
    total_events_checked = 0
    events_with_issues = 0

    for ev in events[:5]:
        event_id = ev["id"]
        home = ev.get("home_team", "?")
        away = ev.get("away_team", "?")
        status = ev.get("status", "?")

        try:
            gm = api_get(f"/api/events/{event_id}/game-markets")
        except Exception:
            continue

        total_events_checked += 1
        issues = []

        # Check game_total monotonicity
        game_totals = [t for t in gm.get("totals", []) if t.get("market_type") == "game_total"]
        game_totals.sort(key=lambda x: x.get("threshold", 0))
        gt_violations = check_monotonicity(game_totals)
        if gt_violations:
            issues.append(f"game_total: {len(gt_violations)} violations")
            total_violations += len(gt_violations)

        # Check period_markets monotonicity (grouped by market_name)
        pm_by_market: dict[str, list[dict]] = defaultdict(list)
        for pm in gm.get("period_markets", []):
            pm_by_market[pm.get("market_name", "")].append(pm)

        for mkt_name, items in pm_by_market.items():
            items.sort(key=lambda x: x.get("threshold", 0) or 0)
            prob_key = "over_probability" if "over_probability" in (items[0] if items else {}) else "probability"
            pm_violations = check_monotonicity(items, prob_key)
            if pm_violations:
                short_name = mkt_name.split(":")[-1].strip() if ":" in mkt_name else mkt_name
                issues.append(f"{short_name}: {len(pm_violations)} violations")
                total_violations += len(pm_violations)

                # Check for cross-game contamination signal
                market_ids = set(i.get("_market_id") for i in items if i.get("_market_id"))
                if len(market_ids) > 1:
                    issues.append(f"  ⚠ CROSS-GAME: {len(market_ids)} different market IDs in same group!")

        # Check player props monotonicity
        props_by_player: dict[str, list[dict]] = defaultdict(list)
        for pp in gm.get("player_props", []):
            key = f"{pp.get('player_name', pp.get('outcome_name', '?'))}:{pp.get('stat_type', pp.get('market_name', '?'))}"
            props_by_player[key].append(pp)

        for player_key, items in props_by_player.items():
            items.sort(key=lambda x: x.get("threshold", 0) or 0)
            pp_violations = check_monotonicity(items)
            if pp_violations:
                issues.append(f"prop {player_key[:25]}: {len(pp_violations)} violations")
                total_violations += len(pp_violations)

        if issues:
            events_with_issues += 1
            print(f"\n  ✗ {away[:18]:18s} @ {home[:18]:18s} [{status}]")
            for issue in issues:
                print(f"    {issue}")
        else:
            print(f"  ✓ {away[:18]:18s} @ {home[:18]:18s} [{status}]")

    print(f"\n  SUMMARY:")
    print(f"    Events checked: {total_events_checked}")
    print(f"    Events with issues: {events_with_issues}")
    print(f"    Total violations: {total_violations}")
    if total_violations == 0:
        print(f"    ✓ ALL CLEAN — no monotonicity violations found")
    print()


def validate_ground_truth(gt_path: str):
    """Validate against Manus ground truth JSON."""
    gt = json.loads(Path(gt_path).read_text())
    print(f"\n{'=' * 60}")
    print(f"  MARKET ACCURACY VALIDATION")
    print(f"  Ground truth: {gt.get('date', '?')}")
    print(f"{'=' * 60}\n")

    events = gt.get("events_audited", [])
    total_violations = 0
    total_contamination = 0

    for ev in events:
        url = ev.get("bainluck_url", "?")
        teams = ev.get("teams", "?")
        print(f"\n  {teams} ({url}):")

        # Projected scoring
        ps = ev.get("projected_scoring", {})
        if not ps.get("monotonic", True):
            violations = ps.get("violations", [])
            total_violations += len(violations)
            print(f"    ✗ Projected scoring: {len(violations)} monotonicity violations")
            for v in violations:
                print(f"      {v}")
        else:
            print(f"    ✓ Projected scoring: monotonic")

        # Period markets
        for pm in ev.get("period_markets", {}).get("markets", []):
            if not pm.get("monotonic", True):
                violations = pm.get("violations", [])
                total_violations += len(violations)
                print(f"    ✗ {pm.get('name', '?')}: {len(violations)} violations")
            else:
                print(f"    ✓ {pm.get('name', '?')}: monotonic")

        # Cross-game contamination
        cc = ev.get("cross_game_contamination", {})
        if cc.get("contamination_found"):
            total_contamination += 1
            print(f"    ✗ CROSS-GAME CONTAMINATION DETECTED")
        elif cc:
            print(f"    ✓ No cross-game contamination (checked {cc.get('kalshi_events_for_matchup', '?')} events)")

    print(f"\n  SUMMARY:")
    print(f"    Events audited: {len(events)}")
    print(f"    Monotonicity violations: {total_violations}")
    print(f"    Cross-game contamination: {total_contamination}")
    if total_violations == 0 and total_contamination == 0:
        print(f"    ✓ ALL CLEAN")
    print()


def main():
    parser = argparse.ArgumentParser(description="Market accuracy audit")
    parser.add_argument("--ground-truth", help="Path to Manus ground truth JSON")
    parser.add_argument("--self-check", action="store_true", help="Self-check live events")
    parser.add_argument("--sport", help="Filter to sport (e.g., basketball_nba)")
    args = parser.parse_args()

    if args.self_check:
        self_check(args.sport)
    elif args.ground_truth:
        validate_ground_truth(args.ground_truth)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
