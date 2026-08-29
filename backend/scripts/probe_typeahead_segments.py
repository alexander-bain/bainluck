#!/usr/bin/env python3
"""#1866 — decompose ONE `/typeahead` miss end-to-end, by SEGMENT.

WHY THIS EXISTS, and why it is not `?debug_timing=1`.

LAT-P054 shipped a server-side `?debug_timing=1` on `/typeahead`. It is on
`program/latency-50`, which is UNMERGED and therefore NOT DEPLOYED — production
answered `da5e7992` with `['suggestions', 'query']` and no timing key while this
was written. So the instrument that would split *backend compute* from
*serialization* does not exist on the measured surface yet.

Everything ELSE in the segment list is measurable from the client today, with no
deploy, because it happens at the transport boundary where curl can see it:

    dns        time_namelookup
    connect    time_connect      - time_namelookup
    tls        time_appconnect   - time_connect
    server     time_starttransfer- time_pretransfer   <- compute + serialization
    transfer   time_total        - time_starttransfer

`server` is the only segment that stays fused, and the fusion is BOUNDED rather
than assumed: FastAPI's default `JSONResponse` serializes the whole body before
the first byte leaves, so serialization is inside `server`, and `transfer`
measures the wire for a payload this script records the exact size of. A 2 KB
body whose transfer segment measures sub-millisecond cannot be hiding a large
serialization cost behind it.

THE PAIRED DESIGN. #1866's subject is the MISS COST — what a user pays for a
cache miss OVER a hit — not the wall time of one request. The cache TTL is 45s
(`events.py`), so within a round each query's first touch is a miss and the
immediate repeat is a hit; the difference, per segment, is the miss cost with
the network floor subtracted rather than estimated.

It refuses to launder a pre-warmed query into a miss: real user traffic can warm
a popular prefix between rounds, and such a request is a hit wearing a miss's
label. `--warm-threshold-ms` flags it and the summary excludes it, loudly, by
name (gotcha #53 — a run that measured nothing must not look like a run with
nothing to measure).

Usage::

    python3 scripts/probe_typeahead_segments.py --rounds 3 --out /tmp/seg.json
    python3 scripts/probe_typeahead_segments.py --reuse-arm     # TLS-tax control
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from typing import Any

#: The identical 8-query arm LAT-P054 used, held fixed so numbers compose.
DEFAULT_ARM = [
    "red sox",
    "patriots",
    "celtics",
    "yankees",
    "bruins",
    "world cup",
    "masters",
    "election",
]

#: Cache TTL on `bainluck:typeahead:{q}` (events.py). A round must be spaced by
#: more than this or the "miss" leg is reading the previous round's write.
CACHE_TTL_S = 45

#: The budget `/typeahead` states twice in `events.py`, and the thing #1866 is
#: measured against.
BUDGET_MS = 150

#: A "miss" whose server segment lands under this was almost certainly served
#: from a cache warmed by somebody else. Not an error — a disclosure.
DEFAULT_WARM_THRESHOLD_MS = 150

_CURL_FMT = (
    "%{http_code} %{time_namelookup} %{time_connect} %{time_appconnect} "
    "%{time_pretransfer} %{time_starttransfer} %{time_total} "
    "%{size_download} %{num_connects}"
)


def _api_base() -> str:
    base = os.environ.get("BAINLUCK_API")
    if not base:
        sys.exit(
            "BAINLUCK_API is unset. Run `source ~/.claude/.env` first — this "
            "probe reads production and will not guess a host."
        )
    return base.rstrip("/")


def _segments(fields: list[str]) -> dict[str, Any]:
    """Turn curl's cumulative timestamps into disjoint, additive segments."""
    code = int(fields[0])
    dns, conn, tls, pre, ttfb, total = (float(x) for x in fields[1:7])
    size, num_connects = int(fields[7]), int(fields[8])

    # curl reports 0 for appconnect on a reused connection: there was no
    # handshake, so the segment is genuinely zero rather than unmeasured.
    tls_seg = (tls - conn) if tls > 0 else 0.0
    conn_seg = (conn - dns) if conn > 0 else 0.0

    return {
        "http_code": code,
        "bytes": size,
        "num_connects": num_connects,
        "reused_connection": num_connects == 0,
        "seg_ms": {
            "dns": round(dns * 1000, 3),
            "connect": round(conn_seg * 1000, 3),
            "tls": round(tls_seg * 1000, 3),
            "server": round((ttfb - pre) * 1000, 3),
            "transfer": round((total - ttfb) * 1000, 3),
        },
        "total_ms": round(total * 1000, 3),
    }


def _one(url: str, timeout_s: int = 30) -> dict[str, Any] | None:
    """One request, one connection. Returns None on transport failure.

    LAT-P118: declares machine traffic, so this probe stops voting in
    `search:trending:24h` — the zset that supplies half the warmer's 40-slot
    head. It changes no timing: the header is read only by the trending
    recorder, never by the cache on either side.
    """
    proc = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", _CURL_FMT,
         "-H", "X-Bainluck-Origin: harness", "--max-time",
         str(timeout_s), url],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    fields = proc.stdout.strip().split()
    if len(fields) != 9:
        return None
    return _segments(fields)


def _pair_on_one_connection(url: str, timeout_s: int = 30) -> list[dict[str, Any]]:
    """Both legs down ONE connection — the connection-reuse control.

    This is the arm that prices the TLS tax directly instead of arguing about
    it: leg 2 pays no handshake, so `tls` is 0 by construction and the delta
    against leg 1's `tls` IS what connection reuse would save.
    """
    proc = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", _CURL_FMT + "\n",
         "-o", "/dev/null", "-w", _CURL_FMT + "\n",
         "-H", "X-Bainluck-Origin: harness",  # LAT-P118, as in `_one`
         "--max-time", str(timeout_s), url, url],
        capture_output=True,
        text=True,
    )
    out = []
    for line in proc.stdout.strip().splitlines():
        fields = line.strip().split()
        if len(fields) == 9:
            out.append(_segments(fields))
    return out


def _pctl(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    idx = min(int(round(p * (len(ordered) - 1))), len(ordered) - 1)
    return round(ordered[idx], 3)


def run_round(
    base: str,
    arm: list[str],
    round_idx: int,
    warm_threshold_ms: float,
    gap_s: float,
) -> list[dict[str, Any]]:
    rows = []
    for q in arm:
        # LAT-P118: `X-Bainluck-Origin` is set inside `_one`; the URL is unchanged.
        url = f"{base}/api/events/typeahead?q={q.replace(' ', '%20')}"
        miss = _one(url)
        time.sleep(gap_s)
        hit = _one(url)
        time.sleep(gap_s)
        if miss is None or hit is None:
            rows.append({"round": round_idx, "query": q, "transport_error": True})
            continue

        pre_warmed = miss["seg_ms"]["server"] < warm_threshold_ms
        rows.append({
            "round": round_idx,
            "query": q,
            "miss": miss,
            "hit": hit,
            "pre_warmed": pre_warmed,
            "miss_cost_ms": {
                k: round(miss["seg_ms"][k] - hit["seg_ms"][k], 3)
                for k in miss["seg_ms"]
            },
            "miss_cost_total_ms": round(miss["total_ms"] - hit["total_ms"], 3),
        })
    return rows


def summarize(rows: list[dict[str, Any]], warm_threshold_ms: float) -> dict[str, Any]:
    usable = [r for r in rows if not r.get("transport_error") and not r["pre_warmed"]]
    excluded = [r["query"] for r in rows if r.get("pre_warmed")]
    errored = [r["query"] for r in rows if r.get("transport_error")]

    seg_names = ["dns", "connect", "tls", "server", "transfer"]
    summary: dict[str, Any] = {
        "n_pairs_attempted": len(rows),
        "n_pairs_usable": len(usable),
        "excluded_pre_warmed": excluded,
        "excluded_transport_error": errored,
        "budget_ms": BUDGET_MS,
    }
    if not usable:
        # gotcha #53: an empty run must never read as a clean one.
        summary["verdict"] = "NO USABLE PAIRS — this run measured nothing."
        return summary

    for label, getter in (
        ("miss_total", lambda r, k: r["miss"]["seg_ms"][k]),
        ("hit_total", lambda r, k: r["hit"]["seg_ms"][k]),
        ("miss_cost", lambda r, k: r["miss_cost_ms"][k]),
    ):
        summary[label] = {
            k: {
                "p50": _pctl([getter(r, k) for r in usable], 0.50),
                "min": round(min(getter(r, k) for r in usable), 3),
                "max": round(max(getter(r, k) for r in usable), 3),
            }
            for k in seg_names
        }

    summary["miss_cost_total_ms"] = {
        "p50": _pctl([r["miss_cost_total_ms"] for r in usable], 0.50),
        "min": round(min(r["miss_cost_total_ms"] for r in usable), 3),
        "max": round(max(r["miss_cost_total_ms"] for r in usable), 3),
    }
    summary["miss_total_wall_ms"] = {
        "p50": _pctl([r["miss"]["total_ms"] for r in usable], 0.50),
        "min": round(min(r["miss"]["total_ms"] for r in usable), 3),
        "max": round(max(r["miss"]["total_ms"] for r in usable), 3),
    }
    summary["bytes_p50"] = _pctl([float(r["miss"]["bytes"]) for r in usable], 0.50)

    # The whole point: name the segment that owns the miss cost.
    costs = {k: summary["miss_cost"][k]["p50"] or 0.0 for k in seg_names}
    largest = max(costs, key=lambda k: costs[k])
    total_cost = sum(v for v in costs.values() if v > 0) or 1.0
    summary["largest_miss_cost_segment"] = {
        "segment": largest,
        "p50_ms": costs[largest],
        "share_of_miss_cost": round(costs[largest] / total_cost, 4),
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--arm", nargs="*", default=DEFAULT_ARM)
    ap.add_argument("--gap-s", type=float, default=0.6,
                    help="Spacing between requests. The public API allows 60/min; "
                         "a throttled response parses as a false null (see the "
                         "rate-limit gotcha), so do not drive this to 0.")
    ap.add_argument("--round-gap-s", type=float, default=CACHE_TTL_S + 10,
                    help="Must exceed the 45s cache TTL or round N+1's 'miss' "
                         "leg reads round N's write.")
    ap.add_argument("--warm-threshold-ms", type=float,
                    default=DEFAULT_WARM_THRESHOLD_MS)
    ap.add_argument("--reuse-arm", action="store_true",
                    help="Also run the one-connection control that prices the TLS tax.")
    ap.add_argument("--label", default="", help="Free-text hour-class label for the capture.")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    base = _api_base()
    rows: list[dict[str, Any]] = []
    for i in range(args.rounds):
        if i:
            time.sleep(args.round_gap_s)
        rows.extend(run_round(base, args.arm, i, args.warm_threshold_ms, args.gap_s))

    payload: dict[str, Any] = {
        "captured_at_unix": int(time.time()),
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "captured_at_local": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
        "label": args.label,
        "api": base,
        "arm": args.arm,
        "rounds": args.rounds,
        "rows": rows,
        "summary": summarize(rows, args.warm_threshold_ms),
    }

    if args.reuse_arm:
        control = []
        for q in args.arm[:3]:
            # LAT-P118: the header is set inside `_pair_on_one_connection`.
            url = f"{base}/api/events/typeahead?q={q.replace(' ', '%20')}"
            legs = _pair_on_one_connection(url)
            control.append({"query": q, "legs": legs})
            time.sleep(args.gap_s)
        tls_saved = [
            leg["seg_ms"]["tls"]
            for c in control for leg in c["legs"] if not leg["reused_connection"]
        ]
        payload["reuse_control"] = {
            "pairs": control,
            "tls_ms_paid_on_fresh_connection_p50": _pctl(tls_saved, 0.50),
            "note": "leg 2 is the same connection: tls == 0 by construction, so "
                    "leg 1's tls IS the saving connection reuse would deliver.",
        }

    text = json.dumps(payload, indent=2)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text)
        print(f"wrote {args.out}")
    print(json.dumps(payload["summary"], indent=2))
    if "reuse_control" in payload:
        print("reuse control tls p50 ms:",
              payload["reuse_control"]["tls_ms_paid_on_fresh_connection_p50"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
