#!/usr/bin/env python3
"""native/011 Item 1 — the window check AND the discrimination check, in one command.

Why this is more than "is anything live": the G4 failure this item hunts is a card that
draws the OPENING number while looking completely fine in a screenshot. That check only
has teeth on a card where the live number and the opener differ by more than rounding.

On 2026-09-04 at 14:12Z, Kostyuk read current=75 / prematch=74 — one point apart, and
therefore worthless as evidence: a card drawing either number looks identical. This ranks
candidates by that gap so the shoot picks the match where a stale opener is actually visible.

Usage:  source ~/.claude/.env && python3 tools/native_tennis_window.py
"""
import datetime
import json
import os
import sys
import urllib.request

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com")


def fetch():
    url = f"{API}/api/feed?sport=tennis&limit=25"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def main():
    items = fetch().get("items", [])
    rows = []
    for it in items:
        x = it.get("data") or {}
        if not x.get("home_team"):
            continue  # futures rows carry no players
        co = x.get("current_odds") or {}
        pm = x.get("prematch_odds") or {}
        cur, pre = co.get("home_rendered_percent"), pm.get("home_rendered_percent")
        gap = abs(cur - pre) if isinstance(cur, int) and isinstance(pre, int) else None
        rows.append({
            "id": x.get("id"),
            "status": x.get("status"),
            "start": str(x.get("commence_time"))[:19],
            "match": f"{x.get('home_team')} vs {x.get('away_team')}",
            "cur": cur, "pre": pre, "gap": gap,
            "score": f"{x.get('home_score')}-{x.get('away_score')}",
            "faces": bool(x.get("home_image_url")) and bool(x.get("away_image_url")),
        })

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%SZ")
    live = [r for r in rows if r["status"] not in ("completed", "scheduled")]
    print(f"now={now}  matches={len(rows)}  live={len(live)}")
    if not live:
        print("WINDOW SHUT — every tennis card is completed or scheduled.")

    print()
    print(f"{'id':>9} {'status':10} {'cur':>4} {'pre':>4} {'gap':>4} {'faces':5} "
          f"{'score':9} {'start':19} match")
    for r in sorted(rows, key=lambda r: (-(r["gap"] if r["gap"] is not None else -1), r["start"])):
        if r["status"] == "completed":
            continue
        print(f"{str(r['id']):>9} {str(r['status']):10} {str(r['cur']):>4} {str(r['pre']):>4} "
              f"{str(r['gap']):>4} {str(r['faces']):5} {r['score']:9} {r['start']:19} {r['match']}")

    print()
    shootable = [r for r in live if (r["gap"] or 0) >= 3]
    if shootable:
        best = max(shootable, key=lambda r: r["gap"])
        print(f"SHOOT id={best['id']} ({best['match']}) — gap {best['gap']}pt "
              f"(live {best['cur']} vs opener {best['pre']}): a stale opener would be visible.")
    elif live:
        print("LIVE but every gap < 3pt — a screenshot CANNOT tell the live number from the "
              "opener. Say so rather than claiming the check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
