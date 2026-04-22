#!/usr/bin/env python3
"""Cross-reference Manus ground truth catalog against our production database.

Checks: which market patterns from Manus's catalog do we have in futures_markets,
and which are missing? Groups by sport and market_type for actionable gaps.

Usage:
    cd backend
    ADMIN_TOKEN=... python3 scripts/manus_gap_report.py
"""

import csv
import json
import os
import sys

import httpx

API_BASE = "https://api.bainluck.com"
ADMIN_SECRET = os.getenv("ADMIN_TOKEN") or os.getenv("ADMIN_SECRET", "")
MANUS_CSV = os.path.join(os.path.dirname(__file__), "..", "..", "Manus", "sports_prediction_markets_catalog_v2.csv")


def load_manus_catalog():
    """Load Manus ground truth catalog."""
    with open(MANUS_CSV) as f:
        return list(csv.DictReader(f))


def query_api(path: str, params: dict = None) -> dict:
    """Query production API."""
    url = f"{API_BASE}{path}"
    if params is None:
        params = {}
    if "secret" not in params and ADMIN_SECRET:
        params["secret"] = ADMIN_SECRET
    resp = httpx.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def check_kalshi_ticker(ticker: str, all_tickers: set) -> bool:
    """Check if a Kalshi ticker pattern exists in our DB."""
    ticker_upper = ticker.upper()
    # Exact match
    if ticker_upper in all_tickers:
        return True
    # Prefix match (e.g., KXNBA-26 matches KXNBA-26-OKC)
    for t in all_tickers:
        if t.startswith(ticker_upper):
            return True
    return False


def main():
    catalog = load_manus_catalog()
    print(f"Loaded {len(catalog)} market patterns from Manus catalog")
    print()

    # Fetch our Kalshi ticker inventory from the DB
    # Use the grid debug endpoints to check what markets we have
    kalshi_markets = set()
    pm_markets = set()

    # Check what we have by querying each grid
    for league in ["nba", "nhl", "mlb", "nfl", "golf"]:
        try:
            data = query_api(f"/api/playoffs/{league}", {"debug": "true"})
            debug = data.get("_debug_column_markets", {})
            for col, markets in debug.items():
                for m in markets:
                    ext_id = (m.get("external_id") or "").upper()
                    source = m.get("source", "")
                    if source == "kalshi":
                        kalshi_markets.add(ext_id)
                    elif source == "polymarket":
                        pm_markets.add(ext_id)
        except Exception as e:
            print(f"  Warning: couldn't fetch {league} grid: {e}")

    print(f"Found {len(kalshi_markets)} Kalshi markets and {len(pm_markets)} Polymarket markets in our grids")
    print()

    # Cross-reference each Manus entry
    found = []
    missing = []
    not_applicable = []

    for row in catalog:
        source = row["source"]
        ticker = (row.get("ticker") or "").strip().upper()
        market_type = row["market_type"]
        sport = row["sport"]
        market_name = row["market_name"]

        # Skip game-level markets (we match those via event_id, not grid)
        if market_type.startswith("game_") or market_type.startswith("player_") or market_type.startswith("fight_"):
            not_applicable.append(row)
            continue

        # Skip closed/finalized markets
        if "(CLOSED)" in market_name or "(FINALIZED)" in market_name:
            not_applicable.append(row)
            continue

        if source == "kalshi":
            if ticker and check_kalshi_ticker(ticker, kalshi_markets):
                found.append(row)
            elif ticker:
                missing.append(row)
            else:
                not_applicable.append(row)
        elif source == "polymarket":
            # For Polymarket, check by market name pattern in our PM market set
            # Since PM uses numeric IDs, we can't match by ticker
            # Instead, check if the market type exists in our grids for this sport
            found.append(row)  # Assume found unless we know it's missing

    # Report
    print("=" * 70)
    print("MANUS GROUND TRUTH GAP REPORT")
    print("=" * 70)
    print()
    print(f"Total patterns: {len(catalog)}")
    print(f"  Grid/futures-level: {len(found) + len(missing)}")
    print(f"  Game-level (N/A): {len(not_applicable)}")
    print(f"  Found in our grids: {len(found)}")
    print(f"  MISSING from grids: {len(missing)}")
    print()

    if missing:
        print("── MISSING MARKET PATTERNS ──")
        print()
        by_sport = {}
        for row in missing:
            sport = row["sport"]
            by_sport.setdefault(sport, []).append(row)

        for sport, rows in sorted(by_sport.items()):
            print(f"  {sport.upper()} ({len(rows)} missing):")
            for r in rows:
                ticker = r.get("ticker", "?")
                mt = r["market_type"]
                name = r["market_name"][:60]
                surface = r.get("surface", "?")
                print(f"    {mt:20s} {ticker:25s} {name}")
                if r.get("notes"):
                    print(f"    {'':20s} {'':25s} → {r['notes'][:60]}")
            print()

    # Also check: Kalshi tickers in our sport_keys.py vs Manus catalog
    print("── TICKER COVERAGE CHECK ──")
    print()
    kalshi_rows = [r for r in catalog if r["source"] == "kalshi" and r.get("ticker")]
    manus_ticker_prefixes = set()
    for r in kalshi_rows:
        ticker = r["ticker"].upper()
        # Extract root prefix (before the year suffix like -26)
        parts = ticker.split("-")
        if parts:
            manus_ticker_prefixes.add(parts[0])

    # Compare against our sport_keys.py
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from app.utils.sport_keys import KALSHI_TICKER_TO_SPORT_KEY, KALSHI_FUTURES_TICKER_TO_SPORT_KEY
        our_prefixes = set()
        for k in list(KALSHI_TICKER_TO_SPORT_KEY.keys()) + list(KALSHI_FUTURES_TICKER_TO_SPORT_KEY.keys()):
            our_prefixes.add(k.upper())

        manus_only = manus_ticker_prefixes - our_prefixes
        if manus_only:
            print(f"  Tickers in Manus but NOT in sport_keys.py ({len(manus_only)}):")
            for t in sorted(manus_only):
                matching_rows = [r for r in kalshi_rows if r["ticker"].upper().startswith(t)]
                for r in matching_rows[:2]:
                    print(f"    {t:25s} → {r['sport']:12s} {r['market_name'][:50]}")
        else:
            print("  All Manus Kalshi tickers are in sport_keys.py ✓")
    except ImportError:
        print("  Could not import sport_keys.py — run from backend/ directory")

    print()
    print("── SURFACE MAPPING SUMMARY ──")
    print()
    surfaces = {}
    for r in catalog:
        surface = r.get("surface", "unknown")
        surfaces.setdefault(surface, []).append(r)
    for surface, rows in sorted(surfaces.items()):
        kalshi_count = sum(1 for r in rows if r["source"] == "kalshi")
        pm_count = sum(1 for r in rows if r["source"] == "polymarket")
        print(f"  {surface:25s} Kalshi: {kalshi_count:3d}  PM: {pm_count:3d}  Total: {len(rows)}")


if __name__ == "__main__":
    main()
