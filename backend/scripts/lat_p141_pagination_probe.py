#!/usr/bin/env python3
"""LAT-P141 — what a person waits for when they scroll Discover.

PRE-REGISTERED BEFORE THE FIX DEPLOYED. Run identically on both sides; a delta
against a different shape set is not a delta.

WHAT IS MEASURED, AND WHY EACH CONSTANT IS A CLIENT'S AND NOT THIS SCRIPT'S.

A scroll is not one request. The native Discover tab opens at
`limit=50&offset=0&event_pct=0.15` (`DiscoverViewModel.firstPageLimit`) and
`loadMoreIfNeeded` then advances by the SERVER page boundary — `offset + limit`,
not the decoded count (`DiscoverViewModel.swift`), so page 2 is offset=50 and
page 3 is offset=100. The web page does the same at `FEED_PAGE_LIMIT` 20
(`app/discover/page.tsx` -> `nextFeedRequest(loadedItems.length)`).

A FRESH PRINCIPAL PER SAMPLE, for LAT-P099's reason: the feed cache key is
per-principal and a prober that reuses one session id measures its own second
request. A new UUID per sample is exactly a new install's first open. It is not
a cache poison — LAT-P089's inert-principal share lets a fresh session READ the
anonymous entry and republish only to its own private key.

SERVER TIME, NOT WALL TIME. This sandbox's transport floor to Heroku is ~250 ms
against tab loads that can be 15 ms. `x-response-time` is the API's own number;
wall is printed beside it only so the floor stays visible.

`X-Feed-Cache` IS RECORDED ON EVERY SAMPLE and printed under every median,
because ruling 127's general form applies: a p50 over mixed cache states is a
statement about the hit rate, not about latency. After the fix the interesting
value is `page_base_hit`; before it, every page > 0 is `miss`.

CONTAMINATION: `/api/feed` is in `LATENCY_ALWAYS_SAMPLE`, so every request here
lands in the `latency-stats` window a later reader might quote as organic. The
count is printed so it can be subtracted. Take the organic read BEFORE running
this (ruling 127).

Usage:  source ~/.claude/.env && python3 lat_p141_pagination_probe.py --label before --n 5
"""

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid

API = os.environ.get("BAINLUCK_API", "https://api.bainluck.com").rstrip("/")

#: (label, surface, query) — every constant cited to the client that sends it.
SHAPES = [
    ("native p1", "native", "limit=50&offset=0&event_pct=0.15"),
    ("native p2", "native", "limit=50&offset=50&event_pct=0.15"),
    ("native p3", "native", "limit=50&offset=100&event_pct=0.15"),
    ("web p1", "web", "limit=20&offset=0&event_pct=0.15"),
    ("web p2", "web", "limit=20&offset=20&event_pct=0.15"),
    ("web p3", "web", "limit=20&offset=40&event_pct=0.15"),
    ("sports p2", "native", "limit=50&offset=50&mode=sports"),
]


def one(query):
    req = urllib.request.Request(
        f"{API}/api/feed?{query}",
        headers={
            "x-session-id": str(uuid.uuid4()),
            "X-Bainluck-Origin": "harness",
        },
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
            wall = (time.perf_counter() - t0) * 1000
            return {
                "server_ms": float(resp.headers.get("x-response-time", "0ms")
                                   .replace("ms", "")),
                "wall_ms": wall,
                "cache": resp.headers.get("X-Feed-Cache", "?"),
                "items": len(body.get("items") or []),
                "total": body.get("total"),
                "has_more": body.get("has_more"),
            }
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--out")
    args = ap.parse_args()

    print(f"# LAT-P141 — the cost of a scroll   run={args.label}  n={args.n}/shape")
    print(f"# api={API}")

    # Round-robin, not shape-by-shape: a dyno restart or a slow database minute
    # lands on whichever shape happens to be running, and a block-sequential run
    # attributes the whole transient to one page.
    samples = {label: [] for label, _, _ in SHAPES}
    for _ in range(args.n):
        for label, _surface, query in SHAPES:
            samples[label].append(one(query))

    rows = []
    print(f"\n{'shape':<12} {'n':>2} {'p50 srv':>9} {'max':>9}  cache states")
    for label, surface, query in SHAPES:
        got = samples[label]
        ok = [s for s in got if "error" not in s]
        if not ok:
            print(f"{label:<12} {'--':>2} {'REFUSED':>9}   {got[0].get('error')}")
            continue
        srv = sorted(s["server_ms"] for s in ok)
        p50 = statistics.median(srv)
        states = {}
        for s in ok:
            states[s["cache"]] = states.get(s["cache"], 0) + 1
        print(
            f"{label:<12} {len(ok):>2} {p50:>9.1f} {max(srv):>9.1f}  {states}"
        )
        rows.append({
            "shape": label,
            "surface": surface,
            "query": query,
            "n": len(ok),
            "p50_ms": p50,
            "max_ms": max(srv),
            "min_ms": min(srv),
            "cache_states": states,
            "total": ok[0].get("total"),
            "items": ok[0].get("items"),
            "has_more": ok[0].get("has_more"),
        })

    paged = [r for r in rows if not r["shape"].endswith("p1")]
    first = [r for r in rows if r["shape"].endswith("p1")]
    if paged and first:
        print(
            f"\nHEADLINE  first page p50 {statistics.median(r['p50_ms'] for r in first):.1f} ms"
            f"   ·   PAGES 2+ p50 {statistics.median(r['p50_ms'] for r in paged):.1f} ms"
        )
        print(
            "          equal-weighted across shapes — the ratio is the whole finding"
        )

    print(f"\ncontamination: {len(SHAPES) * args.n} /api/feed requests, all "
          f"always-sampled. Subtract before quoting latency-stats as organic.")

    if args.out:
        with open(args.out, "w") as fh:
            json.dump({"label": args.label, "n": args.n, "rows": rows}, fh, indent=1)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
