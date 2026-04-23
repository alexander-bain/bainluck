#!/usr/bin/env python3
"""Grid accuracy audit — compares our championship grids against ground truth.

Two measurements:
1. STRUCTURAL CORRECTNESS: Is the right market in the right cell?
   Compare our market tickers per cell against ground truth tickers.
   This is the hill-climb target → 100%.

2. NUMERICAL FRESHNESS: For correct markets, is the probability close?
   Tracked separately — a polling/freshness concern, not classification.

Usage:
    python3 scripts/audit_grid_accuracy.py --ground-truth path/to/gt.json
    python3 scripts/audit_grid_accuracy.py --ground-truth latest --league nhl
    python3 scripts/audit_grid_accuracy.py --ground-truth latest --save --compare
"""

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional
from urllib.request import urlopen

GRID_API_BASE = "https://api.bainluck.com"
LEAGUES = ["nba", "nhl", "mlb"]
RESULTS_DIR = Path(__file__).parent / "audit_results"
MANUS_RESULTS = Path(__file__).parent / ".." / ".." / "Manus" / "audit_results"

# Known name mismatches between source sites and our grid.
# Populated as mismatches are discovered during hill-climbing.
TEAM_NAME_ALIASES: dict[str, str] = {
    # Kalshi uses city-only names; our grid uses full names
    "oklahoma city": "oklahoma city thunder",
    "golden state": "golden state warriors",
    "los angeles l": "los angeles lakers",
    "los angeles c": "los angeles clippers",
    "new york k": "new york knicks",
    "new york n": "new york knicks",
    "san antonio": "san antonio spurs",
    "minnesota": "minnesota timberwolves",
    "indiana": "indiana pacers",
    "cleveland": "cleveland cavaliers",
    "denver": "denver nuggets",
    "dallas": "dallas mavericks",
    "houston": "houston rockets",
    "memphis": "memphis grizzlies",
    "milwaukee": "milwaukee bucks",
    "phoenix": "phoenix suns",
    "portland": "portland trail blazers",
    "sacramento": "sacramento kings",
    "orlando": "orlando magic",
    "detroit": "detroit pistons",
    "atlanta": "atlanta hawks",
    "boston": "boston celtics",
    "brooklyn": "brooklyn nets",
    "charlotte": "charlotte hornets",
    "chicago": "chicago bulls",
    "miami": "miami heat",
    "philadelphia": "philadelphia 76ers",
    "toronto": "toronto raptors",
    "washington": "washington wizards",
    "new orleans": "new orleans pelicans",
    "utah": "utah jazz",
}


@dataclass
class StructuralCheck:
    league: str
    column: str
    source: str
    gt_market_ticker: str
    gt_market_name: str
    found_in_correct_column: bool
    found_in_wrong_column: Optional[str] = None
    found_in_grid_at_all: bool = False
    status: str = ""  # "correct", "wrong_column", "wrong_sport", "missing"
    our_external_id: Optional[str] = None


@dataclass
class NumericalCheck:
    league: str
    column: str
    team: str
    source: str
    gt_prob: float
    our_prob: Optional[float]
    delta: Optional[float] = None
    status: str = ""  # "match" (<2pp), "close" (2-5pp), "stale" (>=5pp), "missing"


@dataclass
class LeagueReport:
    league: str
    structural_total: int = 0
    structural_correct: int = 0
    structural_wrong_column: int = 0
    structural_missing: int = 0
    structural_details: list = field(default_factory=list)
    numerical_match: int = 0
    numerical_close: int = 0
    numerical_stale: int = 0
    numerical_missing: int = 0
    numerical_details: list = field(default_factory=list)
    extra_markets_in_grid: list = field(default_factory=list)

    @property
    def structural_pct(self) -> float:
        return 100 * self.structural_correct / self.structural_total if self.structural_total else 0


def load_ground_truth(path: Path) -> dict:
    with open(path) as f:
        data = json.load(f)
    if "leagues" not in data:
        raise ValueError("Ground truth JSON must have 'leagues' key")
    return data


def fetch_grid_api(league: str, debug: bool = True, base_url: str = GRID_API_BASE) -> dict:
    url = f"{base_url}/api/playoffs/{league}"
    if debug:
        url += "?debug=true"
    with urlopen(url, timeout=30) as resp:
        return json.loads(resp.read())


def normalize(name: str) -> str:
    if not name:
        return ""
    return name.lower().strip().replace(".", "").replace("'", "")


def reconcile_team_name(source_name: str, grid_teams: list[str], league: str) -> tuple[Optional[str], str]:
    """Match a ground truth team name to a grid team name.

    Returns (matched_grid_name, match_method).
    """
    sn = normalize(source_name)

    # 1. Exact match
    for gt in grid_teams:
        if normalize(gt) == sn:
            return gt, "exact"

    # 2. Alias lookup
    alias_target = TEAM_NAME_ALIASES.get(sn)
    if alias_target:
        for gt in grid_teams:
            if normalize(gt) == normalize(alias_target):
                return gt, "alias"

    # 3. Suffix match (last word): "Thunder" matches "Oklahoma City Thunder"
    sn_last = sn.split()[-1] if sn.split() else ""
    if len(sn_last) >= 4:
        matches = [gt for gt in grid_teams if normalize(gt).endswith(sn_last)]
        if len(matches) == 1:
            return matches[0], "suffix"

    # 4. Prefix/contains match
    for gt in grid_teams:
        gn = normalize(gt)
        if sn in gn or gn in sn:
            return gt, "contains"

    # 5. Fuzzy match (>85% similarity)
    best_match = None
    best_ratio = 0.0
    for gt in grid_teams:
        ratio = SequenceMatcher(None, sn, normalize(gt)).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = gt
    if best_ratio >= 0.85:
        return best_match, "fuzzy"

    return None, "unmatched"


def check_structural_correctness(
    league: str,
    gt_league: dict,
    debug_columns: dict,
) -> list[StructuralCheck]:
    """For each ground truth market, check if it appears in the correct grid column."""
    checks = []

    # Build a reverse index: external_id → column it appears in
    ext_id_to_column: dict[str, str] = {}
    ext_id_to_info: dict[str, dict] = {}
    for col_key, markets in debug_columns.items():
        for m in markets:
            eid = (m.get("external_id") or "").lower()
            if eid:
                ext_id_to_column[eid] = col_key
                ext_id_to_info[eid] = m

    for col_key, col_data in gt_league.items():
        for source_name, source_data in col_data.items():
            ticker = (source_data.get("market_ticker") or source_data.get("external_id") or "").lower()
            market_name = source_data.get("market_name", "")

            if not ticker:
                continue

            check = StructuralCheck(
                league=league,
                column=col_key,
                source=source_name,
                gt_market_ticker=ticker,
                gt_market_name=market_name,
                found_in_correct_column=False,
            )

            actual_column = ext_id_to_column.get(ticker)
            if actual_column == col_key:
                check.found_in_correct_column = True
                check.found_in_grid_at_all = True
                check.status = "correct"
                check.our_external_id = ticker
            elif actual_column is not None:
                check.found_in_grid_at_all = True
                check.found_in_wrong_column = actual_column
                check.status = "wrong_column"
                check.our_external_id = ticker
            else:
                check.status = "missing"

            checks.append(check)

    return checks


def check_numerical_freshness(
    league: str,
    gt_league: dict,
    grid_data: dict,
) -> list[NumericalCheck]:
    """For each team in ground truth, compare probability against grid."""
    checks = []
    grid_teams_raw = grid_data.get("teams", [])
    grid_team_names = [t.get("name", "") for t in grid_teams_raw]
    grid_by_name = {t.get("name", ""): t for t in grid_teams_raw}

    for col_key, col_data in gt_league.items():
        for source_name, source_data in col_data.items():
            outcomes = source_data.get("outcomes", {})
            for team_name, gt_prob in outcomes.items():
                matched_name, method = reconcile_team_name(team_name, grid_team_names, league)

                if not matched_name:
                    checks.append(NumericalCheck(
                        league=league, column=col_key, team=team_name,
                        source=source_name, gt_prob=gt_prob, our_prob=None,
                        status="missing",
                    ))
                    continue

                grid_team = grid_by_name.get(matched_name, {})
                cell = grid_team.get("cells", {}).get(col_key, {})

                # Try to find this specific source's probability
                our_prob = None
                for s in cell.get("sources", []):
                    if s.get("source") == source_name:
                        our_prob = s.get("probability")
                        break
                if our_prob is None:
                    our_prob = cell.get("merged_probability")

                if our_prob is None:
                    status = "missing"
                    delta = None
                else:
                    delta = abs(our_prob - gt_prob)
                    if delta < 0.02:
                        status = "match"
                    elif delta < 0.05:
                        status = "close"
                    else:
                        status = "stale"

                checks.append(NumericalCheck(
                    league=league, column=col_key, team=team_name,
                    source=source_name, gt_prob=gt_prob, our_prob=our_prob,
                    delta=delta, status=status,
                ))

    return checks


def find_extra_markets(debug_columns: dict, gt_league: dict) -> list[dict]:
    """Find markets in our grid that aren't in ground truth (potential wrong-sport leaks)."""
    gt_tickers = set()
    for col_data in gt_league.values():
        for source_data in col_data.values():
            ticker = (source_data.get("market_ticker") or "").lower()
            if ticker:
                gt_tickers.add(ticker)

    extras = []
    for col_key, markets in debug_columns.items():
        for m in markets:
            eid = (m.get("external_id") or "").lower()
            if eid and eid not in gt_tickers:
                extras.append({
                    "column": col_key,
                    "external_id": m.get("external_id"),
                    "source": m.get("source"),
                    "name": m.get("name"),
                    "concern": "not_in_ground_truth",
                })
    return extras


def audit_league(league: str, gt_league: dict, grid_data: dict) -> LeagueReport:
    report = LeagueReport(league=league)

    debug_columns = grid_data.get("_debug_column_markets", {})

    # Structural checks
    structural = check_structural_correctness(league, gt_league, debug_columns)
    report.structural_total = len(structural)
    for s in structural:
        if s.status == "correct":
            report.structural_correct += 1
        elif s.status == "wrong_column":
            report.structural_wrong_column += 1
        else:
            report.structural_missing += 1
    report.structural_details = [asdict(s) for s in structural if s.status != "correct"]

    # Numerical checks
    numerical = check_numerical_freshness(league, gt_league, grid_data)
    for n in numerical:
        if n.status == "match":
            report.numerical_match += 1
        elif n.status == "close":
            report.numerical_close += 1
        elif n.status == "stale":
            report.numerical_stale += 1
        else:
            report.numerical_missing += 1
    report.numerical_details = [asdict(n) for n in numerical if n.status in ("stale", "missing")]

    # Extra markets (potential leaks)
    report.extra_markets_in_grid = find_extra_markets(debug_columns, gt_league)

    return report


def print_report(reports: list[LeagueReport], gt_captured_at: str):
    print(f"\n{'='*60}")
    print(f"  GRID ACCURACY AUDIT")
    print(f"  Ground truth: {gt_captured_at}")
    print(f"  Compared at:  {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}\n")

    total_struct = sum(r.structural_total for r in reports)
    total_correct = sum(r.structural_correct for r in reports)
    overall_pct = 100 * total_correct / total_struct if total_struct else 0

    print(f"  STRUCTURAL CORRECTNESS: {total_correct}/{total_struct} ({overall_pct:.0f}%)\n")

    for r in reports:
        print(f"  {r.league.upper()}: {r.structural_correct}/{r.structural_total} correct ({r.structural_pct:.0f}%)")
        if r.structural_wrong_column:
            print(f"    ⚠ {r.structural_wrong_column} in wrong column")
        if r.structural_missing:
            print(f"    ✗ {r.structural_missing} missing from grid")
        if r.extra_markets_in_grid:
            print(f"    ? {len(r.extra_markets_in_grid)} extra markets not in ground truth")
    print()

    # Structural mismatches detail
    any_issues = False
    for r in reports:
        for d in r.structural_details:
            if not any_issues:
                print("  STRUCTURAL ISSUES:")
                any_issues = True
            status_icon = "⚠" if d["status"] == "wrong_column" else "✗"
            detail = f"should be {d['column']}, found in {d['found_in_wrong_column']}" if d["status"] == "wrong_column" else "not in grid"
            print(f"    {status_icon} [{r.league.upper()}] {d['gt_market_name'][:50]} ({d['gt_market_ticker']}) — {detail}")

    # Extra markets detail
    for r in reports:
        for e in r.extra_markets_in_grid:
            if not any_issues:
                print("  STRUCTURAL ISSUES:")
                any_issues = True
            print(f"    ? [{r.league.upper()}] Extra in {e['column']}: {e['name'][:50]} ({e['external_id']})")

    if not any_issues:
        print("  ✓ No structural issues found")

    # Numerical freshness summary
    print(f"\n  NUMERICAL FRESHNESS:")
    total_num = sum(r.numerical_match + r.numerical_close + r.numerical_stale + r.numerical_missing for r in reports)
    total_fresh = sum(r.numerical_match + r.numerical_close for r in reports)
    total_stale = sum(r.numerical_stale for r in reports)
    if total_num:
        print(f"    {total_fresh}/{total_num} within 5pp ({100*total_fresh/total_num:.0f}%), {total_stale} stale")
    if total_stale:
        print(f"\n  WORST STALE VALUES:")
        all_stale = []
        for r in reports:
            all_stale.extend(r.numerical_details)
        all_stale.sort(key=lambda x: abs(x.get("delta") or 0), reverse=True)
        for s in all_stale[:10]:
            d = s.get("delta")
            if d is not None:
                print(f"    {s['league'].upper()} {s['column']}: {s['team']} ({s['source']}) gt={s['gt_prob']:.1%} ours={s['our_prob']:.1%} Δ={d:.1%}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Audit grid accuracy against ground truth")
    parser.add_argument("--ground-truth", required=True, help="Path to ground truth JSON, or 'latest'")
    parser.add_argument("--league", help="Single league to audit (nba, nhl, mlb)")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    parser.add_argument("--save", action="store_true", help="Save results to audit_results/")
    parser.add_argument("--compare", action="store_true", help="Compare against previous run")
    parser.add_argument("--api-base", default=GRID_API_BASE, help="API base URL")
    args = parser.parse_args()

    api_base = args.api_base

    # Resolve ground truth path
    if args.ground_truth == "latest":
        gt_path = MANUS_RESULTS / "latest" / "grid_ground_truth.json"
    else:
        gt_path = Path(args.ground_truth)

    if not gt_path.exists():
        print(f"Ground truth file not found: {gt_path}", file=sys.stderr)
        sys.exit(1)

    gt = load_ground_truth(gt_path)
    leagues = [args.league] if args.league else LEAGUES

    reports = []
    for league in leagues:
        gt_league = gt.get("leagues", {}).get(league)
        if not gt_league:
            print(f"No ground truth for {league}, skipping", file=sys.stderr)
            continue

        grid_data = fetch_grid_api(league, debug=True, base_url=api_base)
        report = audit_league(league, gt_league, grid_data)
        reports.append(report)

    # Output
    result = {
        "captured_at": gt.get("captured_at", "unknown"),
        "compared_at": datetime.now(timezone.utc).isoformat(),
        "leagues": {r.league: {
            "structural_correctness": {
                "total": r.structural_total,
                "correct": r.structural_correct,
                "wrong_column": r.structural_wrong_column,
                "missing": r.structural_missing,
                "pct": round(r.structural_pct, 1),
            },
            "numerical_freshness": {
                "match": r.numerical_match,
                "close": r.numerical_close,
                "stale": r.numerical_stale,
                "missing": r.numerical_missing,
            },
            "extra_markets": r.extra_markets_in_grid,
            "structural_issues": r.structural_details,
            "numerical_issues": r.numerical_details,
        } for r in reports},
        "overall_structural_pct": round(
            100 * sum(r.structural_correct for r in reports) /
            max(sum(r.structural_total for r in reports), 1), 1
        ),
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_report(reports, gt.get("captured_at", "unknown"))

    if args.save:
        RESULTS_DIR.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = RESULTS_DIR / f"grid_accuracy_{ts}.json"
        out_path.write_text(json.dumps(result, indent=2))
        latest = RESULTS_DIR / "grid_accuracy_latest.json"
        latest.write_text(json.dumps(result, indent=2))
        print(f"Saved: {out_path}")

    if args.compare:
        latest_path = RESULTS_DIR / "grid_accuracy_latest.json"
        if latest_path.exists():
            prev = json.loads(latest_path.read_text())
            prev_pct = prev.get("overall_structural_pct", 0)
            curr_pct = result["overall_structural_pct"]
            delta = curr_pct - prev_pct
            arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
            print(f"\n  vs previous: {prev_pct}% → {curr_pct}% ({arrow}{abs(delta):.1f}pp)")


if __name__ == "__main__":
    main()
