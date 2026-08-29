#!/usr/bin/env python3
"""LAT-P135 — does the anonymous Discover first-paint entry go ABSENT, and how often?

WHY THIS PROBE EXISTS AND WHAT IT IS NOT.

`cold_path_snapshot.py` (LAT-P099, the lane's frozen instrument) reports a p50
over `n` samples per path. On 2026-08-29 against production `ce5f719b` it read:

    Discover web   n=6   p50 all 20.5 ms   p50 cold 2,776.0 ms   cold 17%

One sample in six was a full `X-Feed-Cache: miss` at 2,776 ms on the DEFAULT
LANDING PAGE. A p50 cannot say whether that is a periodic hole a real user falls
into or a single transient, and the difference is the whole finding: the first
is a defect with a cadence, the second is noise. n=6 cannot tell them apart, so
this probe exists to ask the one question the snapshot structurally cannot.

WHAT IT MEASURES. The two Discover first-paint shapes, alternating, through the
REAL cache path — never `debug_timing`, which bypasses the cache and would
measure a build that no user's request performs:

  * `discover_web`    `/api/feed?limit=20&offset=0&event_pct=0.15`, principal
    ANON (no `x-session-id`) — `frontend/app/discover/page.tsx:641`,
    `FEED_PAGE_LIMIT=20`. This is the shape that missed.
  * `discover_native` `/api/feed?limit=50&offset=0&event_pct=0.15`, a FRESH
    `x-session-id` per sample — `APIClient.swift:606`. Carried as the CONTROL:
    it reads the same anonymous shared entry through the LAT-P089 inert-principal
    path, so if a hole is in the shared entry both surfaces see it, and if only
    one surface sees it the hole is in that surface's key.

🔴 THE CONTROL IS THE POINT. A probe of one shape that finds misses cannot say
whether the cause is the shared warm rail or that shape's own key. Two shapes
reading through different key paths can.

CONTAMINATION, declared rather than argued. `/api/feed` is in
`LATENCY_ALWAYS_SAMPLE`, so EVERY request here lands in the `latency-stats`
window a later reader might quote as organic. Take the organic read BEFORE
running this (ruling 127) and subtract `--n` * 2 from the `/api/feed` count.
`X-Bainluck-Origin: harness` is sent throughout; on this route it suppresses no
cache behaviour in either direction and is here only so the request is
attributable.

🔴 THIS PROBE CANNOT WARM WHAT IT MEASURES INTO LOOKING HEALTHY, and that is
load-bearing. A `miss` on the anon shape REBUILDS and REPUBLISHES the shared
entry, so a high-frequency probe would paper over the very hole it is looking
for — it would become the warmer. The cadence is therefore deliberately SLOWER
than the warm rail it is auditing (`FEED_LIVE_REPUBLISH_PERIOD_S = 40s`): at
`--interval 5` this probe touches each shape every 10s, which is frequent enough
to see a hole open and slow enough that the rail, not the probe, is what closes
it. Read `--interval` as an instrument setting, not a knob.

Server time (`x-response-time`) only. This sandbox's transport floor to Heroku
is ~230 ms p50 against entries that hit in ~15 ms; wall time from here reports
the egress proxy and is recorded beside it purely so the floor stays visible.

Exit codes (gotcha #54 — read the VALUE): 0 = ran and NO absence observed.
1 = ran and at least one full `miss` observed. Anything else is the harness.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

#: The two shapes, cited to the client that issues them. `principal` is the
#: property that makes the pair a control rather than two samples of one thing.
SHAPES: tuple[dict, ...] = (
    {
        "label": "discover_web",
        "path": "/api/feed?limit=20&offset=0&event_pct=0.15",
        "principal": "anon",
        "source": "frontend/app/discover/page.tsx:641, FEED_PAGE_LIMIT=20",
    },
    {
        "label": "discover_native",
        "path": "/api/feed?limit=50&offset=0&event_pct=0.15",
        "principal": "fresh_session",
        "source": "APIClient.swift:606 (limit default 50)",
    },
)

#: Cache statuses that mean THE ENTRY WAS THERE. Anything outside this set is
#: the hole this probe exists to count. Listed positively, not as a
#: `!= "miss"` test: a new status string added upstream must read as a hole
#: until someone classifies it, not silently as health.
_SERVED_FROM_CACHE = frozenset(
    {"hit", "stale_hit", "shared_hit", "shared_stale_hit", "last_good"}
)


def _hdr(headers: dict, name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _sample(api: str, shape: dict, timeout: float) -> dict:
    headers = {"X-Bainluck-Origin": "harness"}
    if shape["principal"] == "fresh_session":
        headers["x-session-id"] = str(uuid.uuid4())
    request = urllib.request.Request(f"{api}{shape['path']}", headers=headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_headers, status = dict(response.headers), response.status
            response.read()
    except urllib.error.HTTPError as exc:  # noqa: PERF203 - one shape per call
        raw_headers, status = dict(exc.headers or {}), exc.code
    except Exception as exc:  # noqa: BLE001 - a dead sample is data, not a crash
        return {
            "label": shape["label"],
            "error": f"{type(exc).__name__}: {exc}",
            "wall_ms": round((time.monotonic() - started) * 1000, 1),
        }
    wall_ms = round((time.monotonic() - started) * 1000, 1)

    server_raw = _hdr(raw_headers, "x-response-time")
    server_ms: float | None = None
    if server_raw:
        text = server_raw.strip().lower().removesuffix("ms").strip()
        try:
            server_ms = float(text)
        except ValueError:
            server_ms = None

    return {
        "label": shape["label"],
        "http": status,
        "cache": _hdr(raw_headers, "x-feed-cache"),
        "server_ms": server_ms,
        "wall_ms": wall_ms,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=8.0)
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="seconds between samples; each shape is touched every 2x this. "
        "Deliberately slower than the 40s warm rail — see the docstring.",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    api = os.environ.get("BAINLUCK_API", "").rstrip("/")
    if not api:
        print("BAINLUCK_API unset — `source ~/.claude/.env` in the SAME command.")
        return 2

    deadline = time.monotonic() + args.minutes * 60.0
    samples: list[dict] = []
    index = 0
    print(
        f"# LAT-P135 Discover absence probe — {args.minutes:g} min, "
        f"one sample every {args.interval:g}s alternating {len(SHAPES)} shapes"
    )
    print(f"# api={api}  started={datetime.now(timezone.utc).isoformat()}")
    while time.monotonic() < deadline:
        shape = SHAPES[index % len(SHAPES)]
        row = _sample(api, shape, args.timeout)
        samples.append(row)
        if "error" in row:
            print(f"  {row['label']:16} ERROR {row['error']}")
        else:
            flag = "" if (row["cache"] or "") in _SERVED_FROM_CACHE else "   <-- HOLE"
            server = f"{row['server_ms']:,.0f}" if row["server_ms"] is not None else "?"
            print(
                f"  {row['label']:16} {str(row['cache']):18} "
                f"server {server:>7} ms   wall {row['wall_ms']:>7,.0f} ms{flag}"
            )
        index += 1
        time.sleep(args.interval)

    print()
    holes_total = 0
    for shape in SHAPES:
        rows = [r for r in samples if r["label"] == shape["label"] and "error" not in r]
        if not rows:
            print(f"{shape['label']}: NO SAMPLES")
            continue
        served = [r for r in rows if (r["cache"] or "") in _SERVED_FROM_CACHE]
        holes = [r for r in rows if (r["cache"] or "") not in _SERVED_FROM_CACHE]
        holes_total += len(holes)
        timings = [r["server_ms"] for r in rows if r["server_ms"] is not None]
        hole_timings = [r["server_ms"] for r in holes if r["server_ms"] is not None]
        by_status: dict[str, int] = {}
        for r in rows:
            by_status[str(r["cache"])] = by_status.get(str(r["cache"]), 0) + 1
        print(f"## {shape['label']}  ({shape['principal']})  n={len(rows)}")
        print(f"   {shape['source']}")
        print(f"   cache split      {by_status}")
        if timings:
            print(
                f"   server p50       {statistics.median(timings):,.1f} ms"
                f"   max {max(timings):,.1f} ms"
            )
        print(
            f"   HOLES            {len(holes)} / {len(rows)}"
            f"  ({100.0 * len(holes) / len(rows):.1f} %)"
        )
        if hole_timings:
            print(
                f"   hole cost        p50 {statistics.median(hole_timings):,.1f} ms"
                f"   max {max(hole_timings):,.1f} ms"
            )
        if served and hole_timings:
            served_t = [r["server_ms"] for r in served if r["server_ms"] is not None]
            if served_t:
                print(
                    f"   served cost      p50 {statistics.median(served_t):,.1f} ms"
                    f"  <- what the other {len(served)} paid"
                )
        print()

    if args.out:
        with open(args.out, "w") as handle:
            json.dump({"samples": samples}, handle, indent=1)
        print(f"raw -> {args.out}")

    print(
        f"CONTAMINATION: {len([s for s in samples if 'error' not in s])} /api/feed "
        "requests, ALL always-sampled into latency-stats. Subtract before quoting "
        "that window as organic."
    )
    print()
    if holes_total:
        print(f"## VERDICT: THE ENTRY GOES ABSENT — {holes_total} hole(s) observed")
        return 1
    print("## VERDICT: no absence observed in this window")
    return 0


if __name__ == "__main__":
    sys.exit(main())
