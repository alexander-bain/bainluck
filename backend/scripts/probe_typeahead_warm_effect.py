#!/usr/bin/env python3
"""Simulate the `/typeahead` warmer's effect WITHOUT deploying it (#1866, LAT-P056).

A program lane never pushes, so the fix's "after" number is normally owed to a
future window's deploy. But the fix's *mechanism* is testable today, because the
warmer does nothing a `curl` cannot do: it calls the endpoint, which leaves both
the 45s response cache AND the shared index pages warm. Only one of those two
expires on a timer.

So the experiment writes itself:

    T0   MISS #1   cold cache, cold pages            -> the status quo
         (the same call warms cache + pages)
    ...  wait > 45s: the RESPONSE CACHE expires, the PAGES do not
    T1   MISS #2   cold cache, HOT pages             -> what the warmer delivers

Both legs are genuine cache misses, so the comparison isolates page residency
from cache-hit rate — which matters, because "the warmer just adds cache hits"
is the obvious wrong reading of this fix and would predict no difference here.

THE CONTROL IS NOT OPTIONAL. A whole-database improvement between T0 and T1 —
a quieter box, a finished background job — would produce the same drop with no
mechanism at all. So a second arm of queries is touched for the FIRST time at
T1: cold cache, cold pages, same instant as the warmed arm's second leg. If the
warmed arm is fast at T1 and the control arm is still slow at T1, the difference
is residency and nothing else.

Usage::

    python3 scripts/probe_typeahead_warm_effect.py --out /tmp/warm_effect.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any

#: Warmed arm: touched at T0, re-measured at T1.
DEFAULT_WARMED = ["red sox", "patriots", "celtics", "yankees"]

#: Control arm: NEVER touched before T1. Must stay disjoint from the warmed arm
#: and from anything the run itself has already requested.
DEFAULT_CONTROL = ["bruins", "world cup", "masters", "election"]

#: `/typeahead`'s response-cache TTL is 45s (`routes/events.py`). The gap must
#: exceed it, or leg 2 is a cache HIT and the experiment measures nothing.
CACHE_TTL_S = 45

_CURL_FMT = (
    "%{http_code} %{time_pretransfer} %{time_starttransfer} %{time_total} "
    "%{size_download}"
)


def _api_base() -> str:
    base = os.environ.get("BAINLUCK_API")
    if not base:
        sys.exit("BAINLUCK_API is unset. `source ~/.claude/.env` first.")
    return base.rstrip("/")


def _server_ms(base: str, q: str) -> dict[str, Any] | None:
    """One request. `server` = TTFB - pretransfer, i.e. TLS/connect excluded."""
    url = f"{base}/api/events/typeahead?q={q.replace(' ', '%20')}"
    proc = subprocess.run(
        # LAT-P118: declare machine traffic — this probe measures the warm
        # effect, so it must not also CAUSE one by voting in the head.
        ["curl", "-s", "-o", "/dev/null", "-w", _CURL_FMT,
         "-H", "X-Bainluck-Origin: harness", "--max-time", "40", url],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    f = proc.stdout.strip().split()
    if len(f) != 5:
        return None
    code, pre, ttfb, total, size = int(f[0]), *(float(x) for x in f[1:4]), int(f[4])
    return {
        "http_code": code,
        "server_ms": round((ttfb - pre) * 1000, 3),
        "total_ms": round(total * 1000, 3),
        "bytes": size,
    }


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    mid = len(s) // 2
    return round(s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2, 3)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--warmed", nargs="*", default=DEFAULT_WARMED)
    ap.add_argument("--control", nargs="*", default=DEFAULT_CONTROL)
    ap.add_argument("--gap-s", type=float, default=CACHE_TTL_S + 15)
    ap.add_argument("--spacing-s", type=float, default=0.8)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    overlap = set(args.warmed) & set(args.control)
    if overlap:
        sys.exit(f"warmed and control arms overlap on {sorted(overlap)} — the "
                 f"control would be warmed by the warmed arm and prove nothing")

    base = _api_base()

    t0 = []
    for q in args.warmed:
        r = _server_ms(base, q)
        t0.append({"query": q, **(r or {"transport_error": True})})
        time.sleep(args.spacing_s)

    time.sleep(args.gap_s)

    t1_warmed, t1_control = [], []
    # Interleave so the two arms share the same instant, rather than the control
    # trailing the warmed arm through a minute of unrelated drift.
    for w, c in zip(args.warmed, args.control):
        r = _server_ms(base, w)
        t1_warmed.append({"query": w, **(r or {"transport_error": True})})
        time.sleep(args.spacing_s)
        r = _server_ms(base, c)
        t1_control.append({"query": c, **(r or {"transport_error": True})})
        time.sleep(args.spacing_s)

    def _vals(rows):
        return [r["server_ms"] for r in rows if "server_ms" in r]

    p50_t0 = _median(_vals(t0))
    p50_w = _median(_vals(t1_warmed))
    p50_c = _median(_vals(t1_control))

    payload = {
        "captured_at_local": time.strftime("%Y-%m-%dT%H:%M:%S %Z"),
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api": base,
        "cache_ttl_s": CACHE_TTL_S,
        "gap_s": args.gap_s,
        "t0_cold_cold": t0,
        "t1_warmed_cold_cache_hot_pages": t1_warmed,
        "t1_control_cold_cache_cold_pages": t1_control,
        "summary": {
            "t0_warmed_arm_server_p50_ms": p50_t0,
            "t1_warmed_arm_server_p50_ms": p50_w,
            "t1_control_arm_server_p50_ms": p50_c,
            "warmed_speedup_vs_own_t0": (
                round(p50_t0 / p50_w, 2) if p50_t0 and p50_w else None
            ),
            "warmed_vs_control_at_t1": (
                round(p50_c / p50_w, 2) if p50_c and p50_w else None
            ),
        },
    }
    verdict = (
        "MECHANISM CONFIRMED" if (p50_c and p50_w and p50_c > p50_w * 1.5)
        else "NOT CONFIRMED — warmed arm is not meaningfully faster than the "
             "control at the same instant"
    )
    payload["verdict"] = verdict

    text = json.dumps(payload, indent=2)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text)
        print(f"wrote {args.out}")
    print(json.dumps(payload["summary"], indent=2))
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
