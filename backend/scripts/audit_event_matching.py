#!/usr/bin/env python3
"""Four-layer event matching accuracy audit.

Layer 1: Event existence — does the game exist with all sources?
Layer 2: Market → event linking — are game markets linked correctly?
Layer 3: Futures surfacing — do season futures show on event pages?
Layer 4: Market completeness — are we showing every market we should?

Usage:
    # Layer 2 only (internal, no Manus needed)
    python3 scripts/audit_event_matching.py --layer2-only --sport baseball_mlb

    # Full audit with Manus ground truth
    python3 scripts/audit_event_matching.py --ground-truth path/to/gt.json

    # Self-check (Layer 1+2 from feed, no Manus)
    python3 scripts/audit_event_matching.py --self-check
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

API_BASE = "https://api.bainluck.com"
RESULTS_DIR = Path(__file__).parent / "audit_results"

# Game-level Kalshi ticker prefixes by sport
# (from sport_keys.py KALSHI_TICKER_TO_SPORT_KEY)
GAME_TICKER_PREFIXES: dict[str, list[str]] = {
    "baseball_mlb": [
        "kxmlbgame", "kxmlbspread", "kxmlbtotal", "kxmlbteamtotal",
        "kxmlbf5", "kxmlbf5spread", "kxmlbf5total",
        "kxmlbhit", "kxmlbhr", "kxmlbks", "kxmlbtb", "kxmlbhrr", "kxmlbrfi",
    ],
    "basketball_nba": [
        "kxnbagame", "kxnbaspread", "kxnbatotal", "kxnbateamtotal",
        "kxnba1hwinner", "kxnba1hspread", "kxnba1htotal",
        "kxnbapts", "kxnbaast", "kxnbareb", "kxnbablk", "kxnbastl", "kxnba3pt",
        "kxnbapa", "kxnbapr", "kxnbapra", "kxnbara",
        "kxnba2d", "kxnbato", "kxnbafb",
    ],
    "icehockey_nhl": [
        "kxnhlgame", "kxnhlspread", "kxnhltotal",
        "kxnhlgoals", "kxnhlsaves", "kxnhlsog",
    ],
}


def api_get(path: str) -> dict:
    url = f"{API_BASE}{path}"
    with urlopen(url, timeout=30) as resp:
        return json.loads(resp.read())


def get_feed_events(sport: str | None = None) -> list[dict]:
    """Get today's events from the feed."""
    data = api_get("/api/feed?limit=200")
    events = []
    for item in data.get("items", []):
        ev = item.get("data", {})
        ev_sport = ev.get("sport", "")
        if sport and ev_sport != sport:
            continue
        status = ev.get("status", "")
        if status in ("live", "scheduled", "open", "completed"):
            events.append(ev)
    return events


def get_game_markets(event_id: int) -> dict:
    """Get game markets for an event."""
    try:
        return api_get(f"/api/events/{event_id}/game-markets")
    except Exception:
        return {}


def get_related_futures(event_id: int) -> dict:
    """Get related futures for an event."""
    try:
        return api_get(f"/api/events/{event_id}/related-futures")
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Layer 2: Market → Event Linking
# ---------------------------------------------------------------------------

@dataclass
class MarketLinkResult:
    ticker_prefix: str
    ticker_pattern: str
    status: str  # linked, unlinked, mislinked, not_in_db
    event_id: int | None = None
    expected_event_id: int | None = None
    market_name: str = ""
    actual_event_id: int | None = None


@dataclass
class Layer2Report:
    event_id: int
    event_name: str
    sport: str
    total_expected: int = 0
    linked: int = 0
    unlinked: int = 0
    mislinked: int = 0
    not_in_db: int = 0
    details: list = field(default_factory=list)
    root_causes: dict = field(default_factory=lambda: Counter())


def find_markets_for_event(event_id: int, sport: str) -> dict:
    """Query the game-markets endpoint to see what's linked."""
    gm = get_game_markets(event_id)
    markets_by_source = defaultdict(list)

    for section in ["player_props", "totals", "other"]:
        for item in gm.get(section, []):
            markets_by_source[item.get("source", "unknown")].append(item)

    # Also check spreads and team_totals
    for item in gm.get("spreads", []):
        markets_by_source[item.get("source", "unknown")].append(item)
    for item in gm.get("team_totals", []):
        markets_by_source[item.get("source", "unknown")].append(item)

    return dict(markets_by_source)


def audit_layer2_for_event(event: dict) -> Layer2Report:
    """Check all expected Kalshi game tickers for an event."""
    event_id = event.get("id")
    home = event.get("home_team", "")
    away = event.get("away_team", "")
    sport = event.get("sport", "")
    event_name = f"{away} @ {home}"

    report = Layer2Report(
        event_id=event_id,
        event_name=event_name,
        sport=sport,
    )

    prefixes = GAME_TICKER_PREFIXES.get(sport, [])
    if not prefixes:
        return report

    # Get what's actually showing on the game-markets endpoint
    gm = get_game_markets(event_id)
    kalshi_market_names = set()
    for section in ["player_props", "totals", "spreads", "team_totals", "other"]:
        for item in gm.get(section, []):
            if item.get("source") == "kalshi":
                kalshi_market_names.add(item.get("market_name", "").lower())

    # Count unique Kalshi markets showing
    kalshi_count = 0
    all_items = []
    for section in ["player_props", "totals", "spreads", "team_totals", "other"]:
        all_items.extend(gm.get(section, []))
    kalshi_markets = set()
    for item in all_items:
        if item.get("source") == "kalshi":
            kalshi_markets.add(item.get("market_name", ""))
    kalshi_count = len(kalshi_markets)

    report.total_expected = len(prefixes)
    report.linked = kalshi_count  # approximate — markets showing = linked + surfacing

    # Summary
    total_props = len(gm.get("player_props", []))
    total_totals = len(gm.get("totals", []))
    total_spreads = len(gm.get("spreads", []))
    total_other = len(gm.get("other", []))

    report.details.append({
        "summary": f"{kalshi_count} Kalshi markets showing, {total_props} player props, {total_totals} totals, {total_spreads} spreads, {total_other} other",
    })

    return report


# ---------------------------------------------------------------------------
# Layer 3: Futures Surfacing
# ---------------------------------------------------------------------------

@dataclass
class Layer3Report:
    event_id: int
    event_name: str
    sport: str
    home_futures: dict = field(default_factory=dict)
    away_futures: dict = field(default_factory=dict)
    leaks: list = field(default_factory=list)
    missing: list = field(default_factory=list)

# Expected market types per sport. Each entry is a human-readable name
# mapped to a regex that matches against clean_label values in the API response.
# This checks for specific markets, not just display_category buckets.
EXPECTED_MARKET_TYPES: dict[str, list[tuple[str, re.Pattern]]] = {
    "baseball_mlb": [
        ("championship", re.compile(r"World Series Champion", re.I)),
        ("pennant", re.compile(r"(AL|NL|American League|National League) Champion", re.I)),
        ("division", re.compile(r"(AL|NL)\s+(East|West|Central)\s+Winner", re.I)),
        ("make_playoffs", re.compile(r"Make.*Playoffs|Playoff Qualif", re.I)),
    ],
    "basketball_nba": [
        ("championship", re.compile(r"NBA Champ", re.I)),
        ("conference", re.compile(r"(Eastern|Western) Conference Champion", re.I)),
        ("division", re.compile(r"Division", re.I)),
        ("make_playoffs", re.compile(r"Make.*Playoffs|Playoff Qualif", re.I)),
    ],
    "icehockey_nhl": [
        ("championship", re.compile(r"Stanley Cup", re.I)),
        ("conference", re.compile(r"(Eastern|Western) Conference", re.I)),
        ("division", re.compile(r"Division", re.I)),
    ],
}


def audit_layer3_for_event(event: dict) -> Layer3Report:
    """Check related futures surfacing on an event detail page.

    Uses label-level matching: instead of checking display_category names,
    checks whether specific market labels (e.g., "World Series Champion",
    "NL Champion") appear in the related futures response.
    """
    event_id = event.get("id")
    home = event.get("home_team", "")
    away = event.get("away_team", "")
    sport = event.get("sport", "")

    report = Layer3Report(
        event_id=event_id,
        event_name=f"{away} @ {home}",
        sport=sport,
    )

    rf = get_related_futures(event_id)
    if not rf:
        report.missing.append("related_futures_endpoint_failed")
        return report


    expected = EXPECTED_MARKET_TYPES.get(sport, [])

    for side, key in [("home", "home_team_futures"), ("away", "away_team_futures")]:
        futures = rf.get(key, [])
        labels = [f.get("clean_label", "") for f in futures]

        target = report.home_futures if side == "home" else report.away_futures
        for market_type, pattern in expected:
            found = any(pattern.search(label) for label in labels)
            target[market_type] = found
            if not found:
                report.missing.append(f"{side}_{market_type}")

    return report


# ---------------------------------------------------------------------------
# Self-check mode (Layer 1 + 2, no Manus)
# ---------------------------------------------------------------------------

def run_self_check(sport: str | None = None):
    """Quick internal audit using feed events as ground truth."""
    print(f"\n{'='*60}")
    print(f"  EVENT MATCHING SELF-CHECK")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    if sport:
        print(f"  Sport: {sport}")
    print(f"{'='*60}\n")

    events = get_feed_events(sport)
    print(f"  Feed events: {len(events)}")

    # Layer 1: Source coverage
    print(f"\n  LAYER 1 — SOURCE COVERAGE:")
    source_stats = Counter()
    for ev in events:
        has_odds = bool(ev.get("bookmaker_odds"))
        has_espn = bool(ev.get("espn", {}).get("espn_id"))
        sources = []
        if has_odds:
            sources.append("odds_api")
        if has_espn:
            sources.append("espn")
        # Check win probability sources
        wps = ev.get("win_probability_sources", {})
        for src in wps:
            if src not in sources:
                sources.append(src)

        source_count = len(sources)
        source_stats[source_count] += 1

    for count in sorted(source_stats.keys(), reverse=True):
        print(f"    {source_stats[count]:3d} events with {count} sources")

    # Layer 2: Game markets
    print(f"\n  LAYER 2 — GAME MARKETS (sampling up to 10 events):")
    sample = [e for e in events if e.get("sport") in GAME_TICKER_PREFIXES][:10]
    total_kalshi = 0
    total_props = 0
    total_other = 0
    events_with_zero_kalshi = 0

    for ev in sample:
        gm = get_game_markets(ev["id"])
        props = gm.get("player_props", [])
        totals = gm.get("totals", [])
        spreads = gm.get("spreads", [])
        other = gm.get("other", [])
        team_totals = gm.get("team_totals", [])

        all_items = props + totals + spreads + other + team_totals
        kalshi_items = [i for i in all_items if i.get("source") == "kalshi"]
        kalshi_unique_markets = len(set(i.get("market_name", "") for i in kalshi_items))

        total_kalshi += kalshi_unique_markets
        total_props += len(props)
        total_other += len(other)

        if kalshi_unique_markets == 0:
            events_with_zero_kalshi += 1

        status = ev.get("status", "?")
        home = ev.get("home_team", "?")
        away = ev.get("away_team", "?")
        print(f"    {away[:15]:15s} @ {home[:15]:15s}  [{status:9s}]  {kalshi_unique_markets:3d} Kalshi mkts, {len(props):3d} props, {len(other):2d} other")

    if sample:
        print(f"\n    Avg: {total_kalshi/len(sample):.0f} Kalshi markets/event, {total_props/len(sample):.0f} props/event")
        if events_with_zero_kalshi:
            print(f"    ⚠ {events_with_zero_kalshi}/{len(sample)} events with ZERO Kalshi markets")

    # Layer 3: Related futures (sample 5)
    print(f"\n  LAYER 3 — RELATED FUTURES (sampling up to 5 events):")
    sample3 = [e for e in events if e.get("sport") in EXPECTED_MARKET_TYPES][:5]
    for ev in sample3:
        report = audit_layer3_for_event(ev)
        missing_str = ", ".join(report.missing) if report.missing else "✓ all present"
        home = ev.get("home_team", "?")
        away = ev.get("away_team", "?")
        print(f"    {away[:15]:15s} @ {home[:15]:15s}  {missing_str}")

    # Layer 4: Market type coverage (sample 3 live/scheduled events)
    print(f"\n  LAYER 4 — MARKET TYPE COVERAGE (sampling up to 3 events):")
    # Only check live events — scheduled games may not have all market types yet
    sample4 = [e for e in events if e.get("sport") in GAME_TICKER_PREFIXES
               and e.get("status") == "live"][:3]
    expected_types = {
        "baseball_mlb": ["player_props", "totals", "spreads"],
        "basketball_nba": ["player_props", "totals", "spreads"],
        "icehockey_nhl": ["player_props", "totals"],
    }
    for ev in sample4:
        gm = get_game_markets(ev["id"])
        home = ev.get("home_team", "?")
        away = ev.get("away_team", "?")
        missing_types = []
        for mtype in expected_types.get(ev.get("sport", ""), []):
            if not gm.get(mtype):
                missing_types.append(mtype)
        if missing_types:
            print(f"    {away[:15]:15s} @ {home[:15]:15s}  missing: {', '.join(missing_types)}")
        else:
            print(f"    {away[:15]:15s} @ {home[:15]:15s}  ✓ all types present")

    print()


# ---------------------------------------------------------------------------
# Layer 2 only mode
# ---------------------------------------------------------------------------

def run_layer2_only(sport: str):
    """Detailed Layer 2 audit for a single sport."""
    print(f"\n{'='*60}")
    print(f"  LAYER 2 AUDIT — {sport.upper()}")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    events = get_feed_events(sport)
    if not events:
        print(f"  No events found for {sport}")
        return

    # Filter to events that should have Kalshi markets
    eligible = [e for e in events if e.get("status") in ("live", "scheduled", "open", "completed")]
    print(f"  Events in feed: {len(eligible)}")

    prefixes = GAME_TICKER_PREFIXES.get(sport, [])
    print(f"  Expected ticker prefixes: {len(prefixes)}")
    print(f"  Prefixes: {', '.join(prefixes)}")
    print()

    total_kalshi_markets = 0
    total_props = 0
    events_with_kalshi = 0
    events_without = 0
    all_market_sources = Counter()

    for ev in eligible:
        event_id = ev["id"]
        home = ev.get("home_team", "")
        away = ev.get("away_team", "")
        status = ev.get("status", "?")

        gm = get_game_markets(event_id)
        props = gm.get("player_props", [])
        totals = gm.get("totals", [])
        spreads = gm.get("spreads", [])
        other = gm.get("other", [])
        team_totals = gm.get("team_totals", [])
        all_items = props + totals + spreads + other + team_totals

        # Count by source
        sources = Counter()
        for item in all_items:
            sources[item.get("source", "?")] += 1

        kalshi_count = sources.get("kalshi", 0)
        for src, count in sources.items():
            all_market_sources[src] += count

        if kalshi_count > 0:
            events_with_kalshi += 1
        else:
            events_without += 1

        total_kalshi_markets += kalshi_count
        total_props += len(props)

        # Show per-event summary
        src_str = ", ".join(f"{s}:{c}" for s, c in sources.most_common())
        icon = "✓" if kalshi_count > 0 else "✗"
        print(f"  {icon} {away[:18]:18s} @ {home[:18]:18s} [{status:9s}]  {src_str}")

    print(f"\n  SUMMARY:")
    print(f"    Events with Kalshi markets: {events_with_kalshi}/{len(eligible)} ({100*events_with_kalshi/max(len(eligible),1):.0f}%)")
    print(f"    Total Kalshi market items: {total_kalshi_markets}")
    print(f"    Total player props: {total_props}")
    print(f"    Market sources: {dict(all_market_sources.most_common())}")

    if events_without > 0:
        print(f"\n  ⚠ {events_without} events have ZERO Kalshi markets — these need investigation")

    print()


# ---------------------------------------------------------------------------
# Full four-layer audit with Manus ground truth
# ---------------------------------------------------------------------------

MANUS_RESULTS = Path(__file__).parent / ".." / ".." / "Manus" / "audit_results"


def run_full_audit(gt_path_str: str, save: bool = False, compare: bool = False):
    """Full four-layer audit using Manus ground truth."""
    if gt_path_str == "latest":
        gt_path = MANUS_RESULTS / "latest" / "event_matching_ground_truth.json"
    else:
        gt_path = Path(gt_path_str)

    if not gt_path.exists():
        print(f"Ground truth not found: {gt_path}", file=sys.stderr)
        print("Run: MANUS_API_KEY=... python3 scripts/manus_health_suite.py --modules event_matching", file=sys.stderr)
        sys.exit(1)

    gt = json.loads(gt_path.read_text())
    gt_date = gt.get("date", "unknown")

    print(f"\n{'='*60}")
    print(f"  FOUR-LAYER EVENT MATCHING AUDIT")
    print(f"  Ground truth: {gt_date}")
    print(f"  Compared at:  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")

    # Get feed events for matching
    feed_events = get_feed_events()

    # --- Layer 1: Event Existence ---
    games = gt.get("games_today", [])
    print(f"\n  LAYER 1 — EVENT EXISTENCE ({len(games)} games in ground truth):")

    l1_found = 0
    l1_partial = 0
    l1_missing = 0

    for game in games:
        sport = game.get("sport", "")
        home = game.get("home_team", "")
        away = game.get("away_team", "")
        gt_sources = game.get("sources", {})

        # Find matching event in feed
        matched_event = None
        for ev in feed_events:
            ev_sport = ev.get("sport", "")
            ev_home = ev.get("home_team", "")
            ev_away = ev.get("away_team", "")
            if ev_sport != sport:
                continue
            # Fuzzy team match
            home_match = (home.lower() in ev_home.lower() or ev_home.lower() in home.lower() or
                         home.split()[-1].lower() in ev_home.lower())
            away_match = (away.lower() in ev_away.lower() or ev_away.lower() in away.lower() or
                         away.split()[-1].lower() in ev_away.lower())
            if home_match and away_match:
                matched_event = ev
                break

        if matched_event:
            # Check source coverage
            has_odds = bool(matched_event.get("bookmaker_odds"))
            has_espn = bool(matched_event.get("espn", {}).get("espn_id"))
            wps = matched_event.get("win_probability_sources", {})
            source_count = len(wps)

            if source_count >= 3:
                l1_found += 1
                icon = "✓"
            else:
                l1_partial += 1
                icon = "⚠"
            sources_str = ", ".join(sorted(wps.keys()))
            print(f"    {icon} {away[:18]:18s} @ {home[:18]:18s}  {source_count} sources ({sources_str})")
        else:
            l1_missing += 1
            print(f"    ✗ {away[:18]:18s} @ {home[:18]:18s}  NOT FOUND in our DB")

    total_l1 = len(games)
    print(f"\n    Score: {l1_found}/{total_l1} fully covered, {l1_partial} partial, {l1_missing} missing")

    # --- Layer 3+4: Deep Audits ---
    deep_audits = gt.get("deep_audits", [])
    if deep_audits:
        print(f"\n  LAYER 3+4 — DEEP AUDITS ({len(deep_audits)} games):")

        for audit in deep_audits:
            home = audit.get("home_team", "")
            away = audit.get("away_team", "")
            sport = audit.get("sport", "")
            event_url = audit.get("bainluck_event_url", "")

            print(f"\n    {away} @ {home}:")

            # Layer 4: Market completeness
            gt_kalshi = audit.get("kalshi_markets", [])
            gt_poly = audit.get("polymarket_markets", [])

            if gt_kalshi:
                # Extract event ID from URL
                event_id = None
                if event_url:
                    parts = event_url.strip("/").split("/")
                    if parts:
                        try:
                            event_id = int(parts[-1])
                        except ValueError:
                            pass

                if event_id:
                    gm = get_game_markets(event_id)
                    all_items = []
                    for section in ["player_props", "totals", "spreads", "team_totals", "other"]:
                        all_items.extend(gm.get(section, []))
                    our_kalshi_names = set(i.get("market_name", "").lower() for i in all_items if i.get("source") == "kalshi")

                    print(f"      Layer 4 (Kalshi): {len(gt_kalshi)} markets on Kalshi, {len(our_kalshi_names)} showing on bainluck")
                    for m in gt_kalshi:
                        ticker = m.get("ticker", "")
                        name = m.get("name", "")
                        if not any(name.lower() in n or n in name.lower() for n in our_kalshi_names if n):
                            print(f"        ✗ NOT SHOWING: {ticker} — {name}")

            # Layer 3: Related futures
            bl_detail = audit.get("bainluck_event_detail", {})
            rf = bl_detail.get("related_futures", {})
            if rf:
                missing_cats = []
                for cat in ["championship", "conference_or_pennant", "division", "make_playoffs"]:
                    if not rf.get(cat):
                        missing_cats.append(cat)
                leaks = rf.get("wrong_sport_leaks", [])

                if missing_cats:
                    print(f"      Layer 3: Missing futures: {', '.join(missing_cats)}")
                else:
                    print(f"      Layer 3: ✓ All expected futures categories present")
                if leaks:
                    print(f"      Layer 3: ⚠ Wrong-sport leaks: {leaks}")

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"  Layer 1 (Event Existence): {l1_found + l1_partial}/{total_l1} ({100*(l1_found+l1_partial)/max(total_l1,1):.0f}%)")
    if deep_audits:
        print(f"  Layer 3+4: See deep audit details above")
    print(f"{'='*60}\n")

    if save:
        RESULTS_DIR.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        result = {
            "ground_truth_date": gt_date,
            "compared_at": datetime.now(timezone.utc).isoformat(),
            "layer1": {"total": total_l1, "found": l1_found, "partial": l1_partial, "missing": l1_missing},
            "deep_audits": len(deep_audits),
        }
        out_path = RESULTS_DIR / f"event_matching_{ts}.json"
        out_path.write_text(json.dumps(result, indent=2))
        print(f"Saved: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Event matching accuracy audit")
    parser.add_argument("--ground-truth", help="Path to ground truth JSON, or 'latest'")
    parser.add_argument("--layer2-only", action="store_true", help="Run Layer 2 only (internal)")
    parser.add_argument("--self-check", action="store_true", help="Quick self-check (no Manus)")
    parser.add_argument("--sport", help="Filter to specific sport (e.g., baseball_mlb)")
    parser.add_argument("--save", action="store_true", help="Save results")
    parser.add_argument("--compare", action="store_true", help="Compare vs previous")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--api-base", default=API_BASE, help="API base URL")
    args = parser.parse_args()

    if args.api_base != API_BASE:
        # Override module-level API_BASE for all functions
        import scripts.audit_event_matching as _self
        _self.API_BASE = args.api_base

    if args.self_check:
        run_self_check(args.sport)
    elif args.layer2_only:
        if not args.sport:
            print("--layer2-only requires --sport", file=sys.stderr)
            sys.exit(1)
        run_layer2_only(args.sport)
    elif args.ground_truth:
        run_full_audit(args.ground_truth, args.save, args.compare)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
