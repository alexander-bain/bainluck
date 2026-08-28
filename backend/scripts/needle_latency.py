#!/usr/bin/env python3
"""THE LATENCY NEEDLE — one pooled cold p50, per `.claude/handoff/NEEDLE-SPEC.md`.

Alex's 2026-08-28 needle ruling gives this lane exactly ONE glanceable number:

    latency: p50 cold load in ms across the three graded surfaces (Discover
             open, tab loads, cold search) — one pooled p50, cold only.

This script IS that number. It exists so the reading is reproducible by a
session that was not present when it was first taken: same paths, same
principals, same cold filter, same pool membership, same output line.

WHY THIS IS A WRAPPER AND NOT A NEW INSTRUMENT.
`cold_path_snapshot.py` (LAT-P099) already establishes what a first load IS —
a fresh principal per sample, the cache state READ from the route's own
`X-Feed-Cache` header rather than assumed, server time rather than this
sandbox's ~250 ms transport floor, and round-robin sampling so a transient
minute cannot be misread as a finding about one tab. Every one of those
disciplines was paid for by an earlier queue. Re-typing them here would fork
the definition on the first edit and nobody would see it happen, so this file
imports `measure()` and adds exactly one thing: the pool, and the line.

THE POOL, DECLARED BY KEY AND NOT BY PREDICATE.
Membership is a frozen literal, not "every blocking path" — if `PATHS` grows a
tab tomorrow, a predicate would silently re-base the series and the needle
would move for a reason that is not latency. A new surface joins this pool by
an explicit edit, which is a visible commit.

    Discover open   discover_native   /api/feed?limit=50&event_pct=0.15
                    discover_web      /api/feed?limit=20&event_pct=0.15
    tab loads       sports_native     /api/feed?limit=50&mode=sports
                    sports_web        /api/feed?limit=20&mode=sports
                    search_trending   /api/events/search/trending
                    my_stuff_stats    /api/predictions/stats
    cold search     (search samples)  /api/events/search?q=

Only the request that GATES FIRST PAINT is in the pool. The siblings a tab also
issues (`/api/predictions/resolutions`, the 200-row event backfill,
`/api/futures/grouped-feed`, the `requires_auth` my-teams feed) are measured by
the underlying snapshot and printed there, but a person does not wait on them,
and a needle that averaged them would be describing traffic rather than a wait.

Browse contributes nothing, on purpose: it issues ZERO requests on appear
(`Views/LeaguesView.swift:55-78`). Printing 0 ms for a request that is never
issued would flatter the pool with a fact that is not a measurement.

Typeahead is NOT in the pool. It is a keystroke, not a load; it carries its own
500 ms bar; and the non-voting `debug_timing` mode this program must use to
sample it without stuffing the trending head reads ~2.2x low. Mixing it in
would drag the needle down for a methodological reason.

WHAT "COLD ONLY" MEANS HERE, AND THE HAZARD IT CARRIES.
A sample is cold when the ROUTE said so — `X-Feed-Cache` in `COLD_STATUSES`,
or, on the endpoints that have no response cache at all, a non-zero query
count. Warm samples are discarded from the needle (they are still printed, as
context, because the cold share is the other half of the story: a surface that
misses 20 % of the time is not the same product as one that misses 90 %).

🔴 The pool is therefore composition-sensitive, and this script says so in its
own output rather than leaving a later reader to discover it. If Discover's
misses dry up and the fast uncached endpoints keep missing, the pooled median
falls without a single request getting faster. So every run prints (a) the
per-path cold n and p50, and (b) a BALANCED cross-check — the median of the
per-path cold medians, which weights each surface equally regardless of how
many times it happened to miss. The headline stays the raw pooled p50 because
that is what the spec ratified; the cross-check is there so a move can be
attributed rather than assumed.

🔴 YOU CANNOT TAKE TWO READINGS BACK TO BACK, AND THIS IS MEASURED, NOT FEARED.
The four graded feed shapes are pre-warmed on a schedule (`FEED_PREWARM_SHAPES`),
and this instrument's own `anon`-principal samples publish to the shared key on
a miss, refreshing its TTL every round-robin pass. So a run started inside the
anon response TTL of the previous run measures what the previous run warmed.
On 2026-08-28, a read taken about a minute after a 22-cold-sample read returned
ZERO cold samples on six of seven member paths and one 11 ms sample on the
seventh; the pool floor below refused it, which is the only reason an 11 ms
"needle" was not published. Leave a real gap between runs. A sudden collapse in
cold share is a statement about the cache, not about the product.

RE-RUN IT LIKE THIS (the reading is not comparable if you change these):

    source ~/.claude/.env
    python3 backend/scripts/needle_latency.py --label "<queue-id>" \\
        --n 5 --n-search 6 --out /tmp/needle.json

Defaults are the frozen ones. `--n` and `--n-search` are exposed for a quick
smoke read, but a PUBLISHED needle uses the defaults; the output labels any
run that does not.

CONTAMINATION. Inherited and declared by the underlying snapshot: this run's
`/api/feed` requests land in the always-sampled `latency-stats` window, and
each cold-search sample writes one `search_query_logs` row (#1916). Cold search
is a graded surface, so `--with-search` is not optional here — it is forced on,
and the row count is printed.

Exit codes (gotcha #54 — read the VALUE): 0 = a needle was produced. 1 = the
run completed but the pool was too thin to publish a median. Anything else is
the harness failing, not a verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from cold_path_snapshot import PATHS, _fmt, _p50, measure  # noqa: E402

#: The three graded surfaces, by the snapshot's own path keys. Frozen: a new
#: surface joins by an explicit edit to this literal, never by a predicate.
POOL: dict[str, tuple[str, ...]] = {
    "Discover open": ("discover_native", "discover_web"),
    "tab loads": ("sports_native", "sports_web", "search_trending", "my_stuff_stats"),
    # "cold search" is not a PATHS entry — it lives in `search_cold_samples`
    # and is folded in separately below.
}

#: The frozen sampling depth for a PUBLISHED reading. A run at other values is
#: still printed, but it is labelled non-canonical so it is never quoted as a
#: point in the series.
CANONICAL_N = 5
CANONICAL_N_SEARCH = 6

#: Fewer cold samples than this and there is no median worth publishing. Not a
#: quality bar — a sample-count floor, in the spirit of `latency-stats`'
#: min_samples: a null is a different fact from a fast number.
MIN_POOL_N = 8


def _cold(rows: list[dict]) -> list[float]:
    """Server-time ms for the samples the ROUTE itself reported as cold."""
    return [
        r["server_ms"]
        for r in rows
        if r.get("class") == "cold" and r.get("server_ms") is not None
    ]


def _graded(rows: list[dict]) -> list[float]:
    return [r["server_ms"] for r in rows if r.get("server_ms") is not None]


def needle(snap: dict) -> dict:
    """Fold a cold-path snapshot into the one number and its provenance."""
    by_key = {p.key: p for p in PATHS}
    members: list[dict] = []

    for surface, keys in POOL.items():
        for key in keys:
            rows = snap["tab_samples"][key]
            members.append(
                {
                    "surface": surface,
                    "key": key,
                    "path": by_key[key].path,
                    "cold": _cold(rows),
                    "n_graded": len(_graded(rows)),
                }
            )

    members.append(
        {
            "surface": "cold search",
            "key": "search_cold",
            "path": "/api/events/search?q=",
            "cold": _cold(snap["search_cold_samples"]),
            "n_graded": len(_graded(snap["search_cold_samples"])),
        }
    )

    pool = [v for m in members for v in m["cold"]]
    per_path_p50 = [_p50(m["cold"]) for m in members if m["cold"]]

    return {
        "schema": "latency-needle/1",
        "taken_at": snap["taken_at"],
        "commit": snap["commit"],
        "uptime_seconds": snap["uptime_seconds"],
        "warm_slug": snap["warm_slug"],
        "canonical": snap["canonical"],
        "members": members,
        "pool_n": len(pool),
        "pool_p50_ms": _p50(pool),
        "pool_max_ms": max(pool) if pool else None,
        "balanced_p50_ms": statistics.median(per_path_p50) if per_path_p50 else None,
        "n_surfaces_cold": sum(1 for m in members if m["cold"]),
        "n_surfaces": len(members),
    }


def report(snap: dict, nd: dict) -> int:
    print("# THE LATENCY NEEDLE — pooled cold p50 across the three graded surfaces")
    print("spec   : .claude/handoff/NEEDLE-SPEC.md (Alex, 2026-08-28)")
    print(
        f"slug   : {nd['commit']}  uptime {nd['uptime_seconds']}s  "
        f"warm_slug={nd['warm_slug']}"
    )
    print(f"run    : {snap['label']}   term set `{snap['term_set']}`")
    print(
        f"floor  : sandbox transport wall p50 "
        f"{_fmt(snap['transport_floor_wall_p50_ms'])} ms — the needle is SERVER "
        f"time (`x-response-time`), not wall."
    )
    if not nd["warm_slug"]:
        print(
            "⚠️  SLUG IS YOUNGER THAN 5 MINUTES. A cold process reads as a "
            "regression (post-deploy latency is not evidence). Re-run."
        )
    if not nd["canonical"]:
        print(
            f"⚠️  NON-CANONICAL DEPTH. A published needle uses --n "
            f"{CANONICAL_N} --n-search {CANONICAL_N_SEARCH}. This run did not; "
            f"do not quote it as a point in the series."
        )
    print()

    print("## the pool — cold samples only, one row per member path")
    print(
        f"{'surface':14s} {'path key':17s} {'graded':>6s} {'cold':>5s} "
        f"{'cold%':>6s} {'p50 cold':>9s}"
    )
    last = None
    for m in nd["members"]:
        share = len(m["cold"]) / m["n_graded"] if m["n_graded"] else None
        label = m["surface"] if m["surface"] != last else ""
        last = m["surface"]
        print(
            f"{label:14s} {m['key']:17s} {m['n_graded']:>6d} "
            f"{len(m['cold']):>5d} "
            f"{('—' if share is None else f'{share:.0%}'):>6s} "
            f"{_fmt(_p50(m['cold'])):>9s}"
        )
    print(
        "               Browse            —      —      —         — "
        " (zero requests on appear — nothing to measure)"
    )
    for m in nd["members"]:
        if not m["cold"]:
            print(
                f"   ⚠️  {m['key']} produced NO cold sample this run — it is "
                f"absent from the pool, not counted as fast."
            )

    print()
    print(
        f"## composition cross-check: balanced p50 (each member weighted "
        f"equally) = {_fmt(nd['balanced_p50_ms'])} ms"
    )
    print(
        "   The headline below is the RAW pool, per spec. If the two diverge "
        "between runs, the move is composition (which surfaces missed), not "
        "speed."
    )

    print()
    if nd["pool_p50_ms"] is None or nd["pool_n"] < MIN_POOL_N:
        print(
            f"## 🔴 POOL TOO THIN TO PUBLISH — n={nd['pool_n']} cold samples, "
            f"floor is {MIN_POOL_N}. A null is not a fast number. Re-run."
        )
        return 1

    print(
        f"## POOLED COLD p50 = {nd['pool_p50_ms']:,.1f} ms   "
        f"(n={nd['pool_n']} cold samples across "
        f"{nd['n_surfaces_cold']}/{nd['n_surfaces']} member paths; "
        f"max {_fmt(nd['pool_max_ms'])} ms)"
    )

    print()
    r = snap["requests"]
    print("## contamination declared by this run")
    print(
        f"   /api/feed              {r.get('feed', 0):>4d} requests — all land in "
        "the always-sampled `latency-stats` window; subtract before quoting "
        "that window as organic."
    )
    print(f"   other tab endpoints    {r.get('other', 0):>4d} — read-only")
    print(
        f"   /api/events/search     {r['search']:>4d} — one `search_query_logs` "
        "row each (#1916). Forced on: cold search is a graded surface."
    )
    print(
        f"   /api/events/typeahead  {r['typeahead']:>4d} — debug_timing, 0 votes "
        "into search:trending:24h. Measured by the snapshot, NOT in the pool."
    )
    print(f"   /api/health            {r['health']:>4d}")
    if snap.get("stats_before"):
        print(
            f"   organic latency-stats read taken BEFORE this run: {snap['stats_before']}"
        )
    else:
        print(
            "   ⚠️  no --stats-before recorded (ruling 127's organic-first "
            "protocol)."
        )

    print()
    print(f"NEEDLE: latency {nd['pool_p50_ms']:.0f} ms @ {nd['taken_at']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", required=True)
    ap.add_argument("--n", type=int, default=CANONICAL_N)
    ap.add_argument("--n-search", type=int, default=CANONICAL_N_SEARCH)
    ap.add_argument("--term-set", default="obscure")
    ap.add_argument("--stats-before", help="path to the latency-stats JSON read FIRST")
    ap.add_argument("--out")
    args = ap.parse_args()

    if not os.environ.get("BAINLUCK_API"):
        print("source ~/.claude/.env first", file=sys.stderr)
        return 2

    snap = measure(
        args.n,
        args.label,
        args.term_set,
        args.n_search,
        True,  # cold search is a graded surface — never optional here
        args.stats_before,
    )
    snap["taken_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snap["canonical"] = (
        args.n == CANONICAL_N
        and args.n_search == CANONICAL_N_SEARCH
        and args.term_set == "obscure"
    )

    nd = needle(snap)
    if args.out:
        with open(args.out, "w") as fh:
            json.dump({"needle": nd, "snapshot": snap}, fh, indent=2)
    return report(snap, nd)


if __name__ == "__main__":
    raise SystemExit(main())
