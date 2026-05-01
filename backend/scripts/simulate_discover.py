"""
Simulate the Discover feed locally without deploying.

Fetches the live feed from the API, applies proposed scoring
adjustments, and shows what the feed WOULD look like. Use this
to iterate on weights before pushing to production.

Usage:
    python3 scripts/simulate_discover.py
"""

import json
import sys
import os
import re

# Allow running from repo root or backend/
if os.path.exists("backend/scripts"):
    os.chdir("backend")

import httpx

API = "https://api.bainluck.com"


def fetch_feed():
    """Fetch the raw feed from the live API."""
    resp = httpx.get(f"{API}/api/feed?limit=200&event_pct=0.15", timeout=30)
    return resp.json().get("items", [])


def is_exceptional_event(item: dict) -> bool:
    """Does this event have a signal that makes it genuinely interesting for DISCOVER?

    Most events belong in the Sports feed. Only truly remarkable events
    belong in Discover — things a non-sports-fan would care about.
    "Playoff game" and "Recent upset" are normal sports content.
    """
    data = item.get("data", {})

    # EI above 85 = top 5% most exciting games ever
    ei = data.get("ei") or data.get("pulse")
    if ei and ei.get("score", 0) >= 85:
        return True

    # Only LIVE events with extreme signals (not completed "recent upsets")
    status = data.get("status", "")
    if status != "live":
        return False

    headline = (item.get("headline") or "").lower()
    # Only live events with these truly exceptional signals
    if any(kw in headline for kw in ["elimination", "buzzer", "walk-off", "historic", "incredible"]):
        return True

    return False


BORING_FUTURES = re.compile(
    r"(# ?(posts|tweets|truths)"
    r"|weekly streams"
    r"|photographed every"
    r"|(posts|tweets)\s+(april|may|june)"
    r"|white house #"
    r"|(map \d|bo3|bo5).*(winner|map)"
    r"|stage \d.+\d{4}:"
    r"|pro football.*(pick|draft position)"
    r"|team to draft"
    r"|overall pick"
    r"|volvo china open"
    r"|temperature in .+ on apr"
    r"|highest temperature in"
    r"|round \d (scores|top \d|leader)"
    r"|to make the cut"
    r"|pitcher of the month"
    r"|player of the month"
    r"|top \d+ finishers"
    r"|ag-pro \d+"
    r"|lottery \d+"
    r"|runner-up .+ on spotify"
    r"|will trump (say|post) \".+\" (this week|on truth)"
    r"|will trump post .+ on truth social this"
    r"|trump say .+ this week"
    r"|net worth on (april|may|june|january)"
    r"|close price on (may|june|april)"
    r"|compute price (up|down)"
    r"|earthquake.*(april|may|june))",
    re.IGNORECASE,
)

SPORTS_CATS = {"basketball", "football", "baseball", "hockey", "soccer", "golf",
               "mma", "boxing", "tennis", "cricket", "motorsports", "esports",
               "rugby", "lacrosse", "aussierules", "americanfootball", "icehockey"}


def get_category(item):
    if item["type"] == "event":
        return (item["data"].get("sport") or "?").split("_")[0]
    elif item["type"] == "futures":
        return (item["data"].get("llm_sport_category") or "other").lower()
    return "tournament"


def simulate(items: list, event_cap: int = 40) -> list:
    """Apply Discover-mode scoring adjustments and re-rank."""
    adjusted = []
    for item in items:
        score = item.get("score", 0)
        cat = get_category(item)
        name = item.get("data", {}).get("name", "")

        # Demote ordinary events
        if item["type"] == "event":
            if is_exceptional_event(item):
                pass  # keep score
            else:
                score = min(score, event_cap)

        # Demote boring futures
        if item["type"] == "futures" and BORING_FUTURES.search(name):
            score = min(score, 20)

        # Demote stale tournaments (golf tournaments months away)
        if item["type"] == "tournament":
            score = min(score, 50)  # tournaments shouldn't outrank top futures

        adjusted.append({**item, "adjusted_score": score})

    adjusted.sort(key=lambda x: -x["adjusted_score"])
    return adjusted


def display(items: list, top_n: int = 30):
    """Show the simulated feed."""
    from collections import Counter
    types = Counter()
    cats = Counter()
    is_sport = Counter()

    print(f"\n{'='*70}")
    print(f"SIMULATED DISCOVER FEED (top {top_n})")
    print(f"{'='*70}\n")

    for i, item in enumerate(items[:top_n]):
        t = item["type"]
        cat = get_category(item)
        orig = item.get("score", 0)
        adj = item["adjusted_score"]
        types[t] += 1
        cats[cat] += 1
        sport = "S" if cat in SPORTS_CATS else "W"
        is_sport[sport] += 1

        if t == "event":
            name = f'{item["data"].get("away_team","?")} @ {item["data"].get("home_team","?")}'
        else:
            name = item["data"].get("name", "?")

        changed = f" (was {orig})" if adj != orig else ""
        print(f"  #{i+1:2d} score={adj:3d}{changed:12s} [{t:10s}] [{cat:12s}] {name[:50]}")

    total = sum(is_sport.values())
    s = is_sport.get("S", 0)
    w = is_sport.get("W", 0)
    print(f"\n  Sports: {s}/{total} ({s*100//total}%)  |  World: {w}/{total} ({w*100//total}%)")
    print(f"  Types: {dict(types)}")
    print(f"  Categories: {dict(cats.most_common(8))}")


def main():
    print("Fetching live feed...")
    items = fetch_feed()
    print(f"Got {len(items)} items")

    # Try different event caps
    for cap in [40, 30, 20]:
        print(f"\n{'#'*70}")
        print(f"  EVENT CAP = {cap} (ordinary events capped at this score)")
        print(f"{'#'*70}")
        result = simulate(items, event_cap=cap)
        display(result)


if __name__ == "__main__":
    main()
