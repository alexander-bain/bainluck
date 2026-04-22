#!/usr/bin/env python3
"""Verify grid market routing against Manus ground truth.

Cross-references the Manus Kalshi sweep CSV (which ticker belongs to which
sport/league/market_type) against our grid's actual market-to-column routing
(from the debug endpoint). Flags any mismatch where a ticker that SHOULD be
in a grid column is missing or routed to the wrong column.

Usage:
    cd backend
    python3 scripts/verify_grid_markets.py

    # Check specific league:
    python3 scripts/verify_grid_markets.py --league nhl
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import httpx

API_BASE = "https://api.bainluck.com"
MANUS_CSV = Path(__file__).parent / ".." / ".." / "Manus" / "kalshi_sweep_april22.csv"

# Map Manus market_type to our grid column keys
MARKET_TYPE_TO_COLUMN = {
    "championship": "championship",
    "conference": "conference",
    "division": "division",
    "make_playoffs": "make_playoffs",
    "relegation": "relegation",
    "top_4": "top_4",
}

# Map Manus league names to our grid slugs
LEAGUE_TO_SLUG = {
    "NBA": "nba",
    "NHL": "nhl",
    "NFL": "nfl",
    "MLB": "mlb",
    "WNBA": "wnba",
    "NCAA Basketball": "ncaa-basketball",
    "NCAA Football": "ncaa-football",
    "EPL": "epl",
    "La Liga": "la-liga",
    "Champions League": "champions-league",
    "Bundesliga": "bundesliga",
    "MLS": "mls",
}

# Tickers that are NOT grid markets (awards, series, props, game-level)
NON_GRID_TYPES = {
    "game_moneyline", "game_spread", "game_total",
    "player_prop", "player_points", "player_assists", "player_rebounds",
    "series", "award", "draft", "futures", "Grand Slam",
}

# Kalshi ticker prefixes that are awards/props/non-grid despite being
# classified as "championship" in the Manus CSV
NON_GRID_TICKER_PATTERNS = {
    "KXMLBALCY", "KXMLBNLCY",           # Cy Young
    "KXMLBALMOTY", "KXMLBNLMOTY",       # Manager of the Year
    "KXMLBALRELOTY", "KXMLBNLRELOTY",   # Reliever of the Year
    "KXMLBALCPOTY", "KXMLBNLCPOTY",     # Comeback Player
    "KXMLBALHAARON", "KXMLBNLHAARON",   # Hank Aaron
    "KXMLBEOTY",                         # Executive of the Year
    "KXMLBPITCHEROTM", "KXMLBPLAYEROTM", # Monthly awards
    "KXMLBSTATCOUNT", "KXMLBSTAT",       # Season stats
    "KXMLBLSTREAK", "KXMLBWSTREAK",      # Streaks
    "KXMLBWORSTRECORD", "KXMLBBESTRECORD", # Records
    "KXTEAMSINWS", "KXTEAMSINSC",        # "Teams in Finals" (meta-markets)
    "KXNHLHART", "KXNHLCALDER",          # NHL awards
    "KXNHLNORRIS", "KXNHLVEZINA",
    "KXNHLADAMS", "KXNHLROSS",
    "KXNHLPLAYOFFGOALS",                 # Playoff goal leader
    "KXCONNSMYTHE",                      # Conn Smythe
    "KXCANADACUP",                       # "Canada winning" (binary, not grid)
    "KXNEXTTEAMNHL",                     # "Next team" (meta-market)
}

# Column name aliases (our grid may use different column keys than Manus)
COLUMN_ALIASES = {
    ("MLB", "pennant"): "conference",     # AL/NL pennant = conference column
    ("MLB", "make_playoffs"): "make_playoffs",
}


def load_manus_ground_truth() -> list[dict]:
    """Load Manus Kalshi sweep CSV as ground truth."""
    with open(MANUS_CSV) as f:
        return list(csv.DictReader(f))


def fetch_grid_debug(slug: str) -> dict | None:
    """Fetch grid with debug info from prod API."""
    try:
        resp = httpx.get(f"{API_BASE}/api/playoffs/{slug}?debug=true", timeout=30)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception as e:
        print(f"  ERROR fetching {slug}: {e}")
        return None


def extract_grid_tickers(grid_data: dict) -> dict[str, set[str]]:
    """Extract column → set of Kalshi tickers from grid debug data."""
    result: dict[str, set[str]] = defaultdict(set)
    debug = grid_data.get("_debug_column_markets", {})
    for col, markets in debug.items():
        for m in markets:
            if m.get("source") == "kalshi":
                ext_id = (m.get("external_id") or "").upper()
                if ext_id:
                    result[col].add(ext_id)
    return dict(result)


def get_ticker_prefix(ticker: str) -> str:
    """Extract prefix from a ticker like KXNHL-26 → KXNHL."""
    parts = ticker.split("-")
    return parts[0] if parts else ticker


def main():
    parser = argparse.ArgumentParser(description="Verify grid market routing")
    parser.add_argument("--league", help="Check specific league slug")
    args = parser.parse_args()

    ground_truth = load_manus_ground_truth()
    print(f"Loaded {len(ground_truth)} market patterns from Manus ground truth")
    print()

    # Group ground truth by league → market_type → tickers
    gt_by_league: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in ground_truth:
        league = row.get("league", "").strip()
        market_type = row.get("market_type", "").strip()
        if market_type in NON_GRID_TYPES:
            continue
        gt_by_league[league][market_type].append(row)

    # Determine which leagues to check
    if args.league:
        leagues_to_check = {args.league: args.league}
    else:
        leagues_to_check = LEAGUE_TO_SLUG

    total_expected = 0
    total_found = 0
    total_missing = 0
    total_wrong_column = 0
    all_issues: list[str] = []

    for league_name, slug in sorted(leagues_to_check.items()):
        gt = gt_by_league.get(league_name, {})
        if not gt:
            continue

        print(f"{'=' * 60}")
        print(f"  {league_name} (/{slug})")
        print(f"{'=' * 60}")

        grid_data = fetch_grid_debug(slug)
        if not grid_data:
            print(f"  SKIP: Grid not available for {slug}")
            print()
            continue

        grid_tickers = extract_grid_tickers(grid_data)
        all_grid_kalshi = set()
        for tickers in grid_tickers.values():
            all_grid_kalshi.update(tickers)

        # For each ground truth market type, check if the tickers are in the right column
        for market_type, rows in sorted(gt.items()):
            expected_column = MARKET_TYPE_TO_COLUMN.get(market_type)
            if not expected_column:
                continue

            for row in rows:
                ticker_prefix = row.get("ticker_prefix", "").strip().upper()
                market_name = row.get("market_name", "").strip()
                if not ticker_prefix:
                    continue

                # Skip non-grid markets (awards, stats, meta-markets)
                if ticker_prefix in NON_GRID_TICKER_PATTERNS:
                    continue

                total_expected += 1

                # Find this ticker in our grid (by prefix match)
                found_in_column = None
                matched_ticker = None
                for col, tickers in grid_tickers.items():
                    for t in tickers:
                        if get_ticker_prefix(t) == ticker_prefix:
                            found_in_column = col
                            matched_ticker = t
                            break
                    if found_in_column:
                        break

                if found_in_column is None:
                    for t in all_grid_kalshi:
                        if get_ticker_prefix(t) == ticker_prefix:
                            found_in_column = "???"
                            matched_ticker = t
                            break

                # Check column match with aliases
                columns_match = False
                if found_in_column == expected_column:
                    columns_match = True
                elif (league_name, found_in_column) in COLUMN_ALIASES:
                    columns_match = COLUMN_ALIASES[(league_name, found_in_column)] == expected_column

                if found_in_column is None:
                    total_missing += 1
                    issue = f"  MISSING: {ticker_prefix:25s} → expected in [{expected_column}]  ({market_name})"
                    print(issue)
                    all_issues.append(f"[{league_name}] {issue.strip()}")
                elif not columns_match:
                    total_wrong_column += 1
                    issue = f"  WRONG:   {ticker_prefix:25s} → in [{found_in_column}] should be [{expected_column}]  ({market_name})"
                    print(issue)
                    all_issues.append(f"[{league_name}] {issue.strip()}")
                else:
                    total_found += 1
                    print(f"  OK:      {ticker_prefix:25s} → [{found_in_column}]  ({market_name})")

        # Also check: are there Kalshi tickers in the grid that Manus DIDN'T catalog?
        gt_prefixes = set()
        for rows in gt.values():
            for row in rows:
                tp = row.get("ticker_prefix", "").strip().upper()
                if tp:
                    gt_prefixes.add(tp)

        for col, tickers in grid_tickers.items():
            for t in tickers:
                prefix = get_ticker_prefix(t)
                if prefix not in gt_prefixes:
                    print(f"  EXTRA:   {t:25s} in [{col}] — not in Manus catalog")

        print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Expected (from Manus):  {total_expected}")
    print(f"  Found in correct col:   {total_found}")
    print(f"  Missing from grid:      {total_missing}")
    print(f"  Wrong column:           {total_wrong_column}")
    accuracy = total_found / total_expected * 100 if total_expected > 0 else 0
    print(f"  Accuracy:               {accuracy:.1f}%")
    print()

    if all_issues:
        print("ALL ISSUES:")
        for issue in all_issues:
            print(f"  {issue}")

    # Exit code: non-zero if any issues
    sys.exit(1 if (total_missing + total_wrong_column) > 0 else 0)


if __name__ == "__main__":
    main()
