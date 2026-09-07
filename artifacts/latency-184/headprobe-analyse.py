#!/usr/bin/env python3
"""LAT-P243 second method — what a real user typing a HEAD term actually pays.

The ring census (`cold-head-census.py`) counts cache ENTRIES that were gone when
the warmer arrived. That is a proxy for user-visible coldness, strong but a proxy.
This reads `.lat247-headprobe.jsonl` — real `GET /api/events/typeahead?q=...`
requests against production — so the two can be compared.

READ THE LIMIT BEFORE QUOTING THIS. A multi-second head response has two filed
causes and this probe cannot tell them apart:
  #3398 — the head is wholly expired, so the term pays a full cold build;
  #2304 — the warmer DELETEs each entry before rebuilding it, so a request landing
          inside that window pays its own build (measured there at 2.0-3.7s, 8.6%).
So this corroborates the SYMPTOM and must not be quoted as attribution to either.
The attributing instrument is the ring census.
"""

import json
import statistics
import sys

WARM_CEILING_S = 0.5   # anything under this is a cache hit plus network
COLD_FLOOR_S = 2.0     # #2304's measured cold-build band starts here


def main(path):
    rows = [json.loads(line) for line in open(path)]
    times = [r["time_total_s"] for r in rows]
    ordered = sorted(times)
    print(f"probes           : n={len(times)}  {rows[0]['q']!r} .. {rows[-1]['q']!r}")
    print(
        f"latency          : p50={statistics.median(times) * 1000:.0f}ms "
        f"p95={ordered[int(len(ordered) * 0.95)] * 1000:.0f}ms max={max(times) * 1000:.0f}ms"
    )

    warm = [r for r in rows if r["time_total_s"] <= WARM_CEILING_S]
    cold = [r for r in rows if r["time_total_s"] >= COLD_FLOOR_S]
    middle = len(rows) - len(warm) - len(cold)
    print(f"\nwarm (<={WARM_CEILING_S * 1000:.0f}ms)   : {len(warm):3d}  ({100 * len(warm) / len(rows):.1f}%)")
    print(f"cold (>={COLD_FLOOR_S * 1000:.0f}ms)  : {len(cold):3d}  ({100 * len(cold) / len(rows):.1f}%)")
    print(f"in between       : {middle:3d}  ({100 * middle / len(rows):.1f}%)")
    print(
        "  ^ a near-empty middle is the point: a head term is either a cache hit or a full\n"
        "    build. There is no gradual degradation to tune away."
    )

    if warm:
        wt = sorted(r["time_total_s"] for r in warm)
        print(f"\nwarm band p50    : {statistics.median(wt) * 1000:.0f}ms")
    if cold:
        ct = sorted(r["time_total_s"] for r in cold)
        print(f"cold band p50    : {statistics.median(ct) * 1000:.0f}ms   (#2304 measured 2,000-3,689ms)")

    # Per-term, to show this is the whole head moving together rather than a few
    # unlucky terms — which is what distinguishes starvation from a bad query plan.
    print("\nper-term slow rate (>= cold floor):")
    by_term = {}
    for r in rows:
        by_term.setdefault(r["q"], []).append(r["time_total_s"])
    for term, ts in sorted(by_term.items(), key=lambda kv: -sum(t >= COLD_FLOOR_S for t in kv[1]) / len(kv[1])):
        slow = sum(t >= COLD_FLOOR_S for t in ts)
        print(f"   {slow}/{len(ts)}  {term}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".lat247-headprobe.jsonl")
