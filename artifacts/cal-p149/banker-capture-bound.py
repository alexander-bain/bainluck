#!/usr/bin/env python3
"""CAL-P149 — the promotion bracket's risk is the BANKER's miss rate, not the serve's.

WHY THIS EXISTS
---------------
CAL-P148 quantified how often a published census is never served by any web
worker: ~1 beat in 203, ~1 promotion bracket in 102. That number then got
carried as "the risk to the promotion bracket". It is not.

The bracket does not depend on a census being *served*. It depends on the
CAL-P147 render banker POLLING at an instant when some worker happens to be
serving it. That is a second sampling layer stacked on top of the serve, and
nobody had put a number on it — the banker was built (CAL-P147) before the two
worker clocks were discovered (CAL-P148), so its capture rate has never been
reconciled against the mechanism it actually samples.

Its empirical rate cannot answer this yet: the banker's `--watch` era is ~25
minutes old and contains exactly ONE census. n=1 is not a reading (CAL-P146's
lesson). So this bounds it from measured inputs instead, and — the point of
making it an instrument rather than a paragraph — it RE-READS those inputs
every run, so if the poll interval is raised or CACHE_TTL is lowered the bound
moves and the guard goes red on its own.

THE MECHANISM, AS MEASURED NOT ASSUMED
--------------------------------------
`routes/calibration.py` tier 1 serves from a per-process memo for a full
CACHE_TTL once an unmarked copy is admitted (`:1128-1164`). The one path that
shortens a hold is a *stale-marked* payload, which is deliberately excluded
from tier 1 (`:1133-1136`) so each request re-attempts Redis. So any census a
worker actually pins is exposed by that worker for a full CACHE_TTL.

The banker therefore gets floor(CACHE_TTL / interval) chances at it. Each poll
lands on one worker; the worst case for the banker is a *random* balancer
(round-robin is strictly better — it would hit every worker within `clocks`
polls). Under random balancing the banker misses only if every one of those
polls lands on a worker that never pinned the census.

EXIT CODES
----------
0  the banker's own sampling layer is negligible against the serve's rate
4  it is NOT negligible — the bracket's risk is no longer just the serve's,
   and the carried 1-in-102 understates it
1  harness (bad inputs); per gotcha #124 that is a story, not a result

    python3 banker-capture-bound.py
    python3 banker-capture-bound.py --interval 600     # what-if a slower poll
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ROUTE = os.path.join(ROOT, "backend", "app", "routes", "calibration.py")
PROBE_LOG = os.path.join(ROOT, "artifacts", "cal-p148", "serve-phase-log.jsonl")

BANKER_TOKEN = "CAL-P147-RENDER-BANKER"

#: CAL-P148 §2, Monte Carlo over the 16 measured beat gaps at the measured
#: clock count. Carried as a constant because re-deriving it needs that
#: session's gap sample; it is the thing this bound is compared AGAINST.
SERVE_MISS_PER_BEAT = 0.0049
SERVE_MISS_PER_BRACKET = 0.0098

#: The banker's layer counts as negligible while it is under this share of the
#: serve's. At 10% the carried 1-in-102 is still the honest headline; above it,
#: the headline is wrong and the bracket needs a different number.
NEGLIGIBLE_SHARE = 0.10


def route_cache_ttl() -> int | None:
    """CACHE_TTL as the deployed route defines it — never a number typed here."""
    try:
        with open(ROUTE) as fh:
            src = fh.read()
    except OSError:
        return None
    m = re.search(r"^CACHE_TTL\s*=\s*(\d+)", src, re.MULTILINE)
    return int(m.group(1)) if m else None


def live_banker_interval() -> int | None:
    """The interval the RUNNING banker actually uses, read from its argv.

    Not the script's default. The default is 240 and the live process was
    started at 180; a bound computed from the default would describe a banker
    that is not running.

    `-lf`, never `-af`. On macOS BSD pgrep `-a` does NOT mean "show args" (that
    is `-l`); it means "include pgrep's own ANCESTORS in the match". Since the
    lane token appears in the argv of the shell running the check, `-af` reports
    this session's own bash processes as extra hits — measured here at 6 pids
    against a true 2, on both this token and the watcher's. See CAL-P149 README.
    """
    try:
        out = subprocess.run(
            ["pgrep", "-lf", BANKER_TOKEN], capture_output=True, text=True, timeout=20
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        m = re.search(r"--interval\s+(\d+)", line)
        if m:
            return int(m.group(1))
    return None


def observed_clocks() -> tuple[int, int]:
    """(clocks, backward_moves) from CAL-P148's probe log.

    A backward move in the served stamp is impossible for a single memo, so
    >0 proves >1 independent clock. This deliberately reports the OBSERVED
    lower bound rather than trusting WEB_CONCURRENCY: a second dyno would add
    clocks that no config value here would show.
    """
    if not os.path.exists(PROBE_LOG):
        return 0, 0
    served = []
    with open(PROBE_LOG) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("served"):
                served.append(rec["served"])
    backward = sum(1 for a, b in zip(served, served[1:]) if b < a)
    # Each backward move is a hand-off to a clock holding something older; with
    # oscillation between k censuses the distinct concurrent censuses seen is
    # the floor on clock count.
    distinct = len(set(served))
    return (max(distinct, 2) if backward else max(distinct, 1)), backward


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interval", type=int, help="override the live banker poll interval (s)")
    ap.add_argument("--ttl", type=int, help="override CACHE_TTL (s)")
    args = ap.parse_args()

    ttl = args.ttl or route_cache_ttl()
    interval = args.interval or live_banker_interval()
    clocks, backward = observed_clocks()

    print("=" * 88)
    print("CAL-P149 — does the render banker's own sampling add risk to the promotion bracket?")
    print("=" * 88)

    if ttl is None:
        print("could not read CACHE_TTL from the route — harness, not a result", file=sys.stderr)
        return 1
    if interval is None:
        print(
            "no running banker to read an interval from; pass --interval to model one",
            file=sys.stderr,
        )
        return 1
    if clocks < 1:
        print("no probe samples — cannot bound the clock count", file=sys.stderr)
        return 1

    polls = ttl // interval
    # Worst case: random balancing, and only ONE of the `clocks` workers ever
    # pinned this census (if more pinned it the banker's odds only improve).
    p_all_polls_miss = ((clocks - 1) / clocks) ** polls if clocks > 1 else 0.0
    added_share = p_all_polls_miss / SERVE_MISS_PER_BEAT if SERVE_MISS_PER_BEAT else float("inf")

    print(f"  CACHE_TTL (read from {os.path.relpath(ROUTE, ROOT)}:35)   {ttl} s")
    print(f"  banker poll interval (read from live argv)          {interval} s")
    print(f"  worker clocks observed (probe log)                  {clocks}"
          f"   [{backward} backward move(s)]")
    print()
    print(f"  a pinned census is exposed by its worker for       {ttl} s")
    print(f"  banker polls landing inside that hold              {polls}")
    print(f"  P(every poll lands on a worker that never pinned)  {p_all_polls_miss:.3e}")
    print()
    print(f"  CAL-P148 serve miss / beat                         {SERVE_MISS_PER_BEAT:.4f}"
          f"   (1 in {1 / SERVE_MISS_PER_BEAT:.0f})")
    print(f"  banker layer adds                                  {p_all_polls_miss:.3e}"
          f"   ({added_share * 100:.4f}% of the serve's)")
    print()
    print(f"  bracket risk, carried (CAL-P148)                   {SERVE_MISS_PER_BRACKET:.4f}"
          f"   (1 in {1 / SERVE_MISS_PER_BRACKET:.0f})")

    if added_share <= NEGLIGIBLE_SHARE:
        print()
        print("VERDICT: the banker's sampling layer is negligible. The promotion bracket's")
        print("         risk is the SERVE's alone, and the carried 1-in-102 stands as the")
        print("         honest headline. Nothing to fix; nothing to re-derive.")
        print("EXIT 0")
        return 0

    print()
    print("🔴 VERDICT: the banker's sampling is NO LONGER negligible against the serve's.")
    print("   The carried 1-in-102 describes the serve and now UNDERSTATES the bracket.")
    print(f"   Cheapest correction is a shorter --interval: at {ttl // 20} s the layer returns")
    print("   to noise. This is a banker restart, NOT a change to any frozen file.")
    print("EXIT 4")
    return 4


if __name__ == "__main__":
    sys.exit(main())
