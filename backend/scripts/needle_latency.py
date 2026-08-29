#!/usr/bin/env python3
"""THE LATENCY NEEDLE — one equal-weighted cold p50.

Spec: `.claude/handoff/NEEDLE-SPEC.md`.

Alex's 2026-08-28 needle ruling, as amended the same day, gives this lane
exactly ONE glanceable number:

    latency: cold p50 load in ms across the three graded surfaces (Discover
             open, tab loads, cold search), with each graded surface weighted
             ONCE — the median of the per-path cold medians, never a median
             over pooled raw samples.

This script IS that number. It exists so the reading is reproducible by a
session that was not present when it was first taken: same paths, same
principals, same cold filter, same pool membership, same statistic, same
output line.

🔴 WHY THE STATISTIC CHANGED, AND WHERE THE SERIES RESTARTS.
The first form of this instrument (LAT-P106, 2026-08-28) published the RAW
POOLED median over every cold sample, because that is what the spec first
ratified. It then measured that form moving 711 ms → 536 ms (−25 %) on
identical code, same slug, ten minutes apart — not because anything got
faster, but because the feed paths' cold share collapsed and the genuinely-
uncached ~12 ms `my_stuff_stats` went from 5/22 of the pool to 5/11, dragging
the median through the fast mode while Discover's own cold open got twice as
SLOW. The equal-weighted statistic moved 1 % across the same pair. Alex ruled
"option b": the equal-weighted form is the published needle, and the raw pool
is demoted to a printed cross-check.

**The comparable series therefore restarts at LAT-P106's own two equal-weighted
readings, 882 ms → 873 ms.** The 711/536 raw-pool numbers are a different
statistic and must never be quoted in the same series — ruling 127: a delta
between two measurements must not be a delta of instruments.

WHICH "SURFACE" IS WEIGHTED ONCE, WRITTEN DOWN SO IT CANNOT DRIFT.
The unit is the MEMBER PATH — the seven rows below — not the three surface
GROUPS. That is what produced 882 and 873, and 882/873 is what Alex ruled on.
Weighting the three groups instead is a different number and would be a silent
re-base of the series; it takes another ruling, not an edit.

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

🔴 A RAW POOL IS COMPOSITION-SENSITIVE. THAT IS THE WHOLE REASON FOR OPTION B.
If Discover's misses dry up while the fast uncached endpoints keep missing, a
raw pooled median falls without a single request getting faster. The published
statistic weights each member path once, so it is immune to that: a path that
missed twice and a path that missed five times contribute one number each.

What the equal-weighting does NOT fix is a member DROPPING OUT — a path with no
cold sample at all is absent from the median, not counted as slow, and the
median then describes a smaller population. So every run still prints (a) the
per-path cold n and p50, (b) which members produced nothing, and (c) the raw
pooled p50 as a demoted cross-check, so a move can be attributed rather than
assumed. And the refusal floors below are expressed in the statistic's OWN
terms: member count and surface coverage, not just a total sample count.

🔴 YOU CANNOT TAKE TWO READINGS BACK TO BACK, AND THIS IS MEASURED, NOT FEARED.
The four graded feed shapes are pre-warmed on a schedule (`FEED_PREWARM_SHAPES`),
and this instrument's own `anon`-principal samples publish to the shared key on
a miss, refreshing its TTL every round-robin pass. So a run started inside the
anon response TTL of the previous run measures what the previous run warmed.
On 2026-08-28, a read taken about a minute after a 22-cold-sample read returned
ZERO cold samples on six of seven member paths and one 11 ms sample on the
seventh; the floors below refused it, which is the only reason an 11 ms "needle"
was not published. Note that equal weighting does not rescue that case — the
median of a single 11 ms member IS 11 ms — which is exactly why `MIN_COLD_MEMBERS`
and `MIN_SURFACES` exist alongside the sample-count floor. Leave a real gap
between runs. A sudden collapse in cold share is a statement about the cache,
not about the product.

RE-RUN IT LIKE THIS (the reading is not comparable if you change these):

    source ~/.claude/.env
    python3 backend/scripts/needle_latency.py --label "<queue-id>" \\
        --n 5 --n-search 6 --out /tmp/needle.json

Defaults are the frozen ones. `--n` and `--n-search` are exposed for a quick
smoke read, but a PUBLISHED needle uses the defaults; the output labels any
run that does not.

CONTAMINATION. Inherited and declared by the underlying snapshot: this run's
`/api/feed` requests land in the always-sampled `latency-stats` window. Cold
search is a graded surface, so `--with-search` is not optional here — it is
forced on, and the request count is printed.

🔴 LAT-P118 CLOSED THE OTHER HALF, AND IT WAS THE HALF THAT COULD HAVE EATEN THE
NUMBER. Every cold-search sample used to write a `search_query_logs` row (#1916),
and that table is the 30-day head `typeahead_warmer.resolve_head` warms from. On
2026-08-29 the probe term `cremonese` held **slot 40 of the 40 warm slots** on 42
rows, all of them harness votes, displacing `president` (42) and `nba finals`
(41). Left running, this instrument would eventually have warmed the very terms
it probes — and `search_cold` is the LARGEST member of the needle pool, so the
published number would have fallen with nothing having got faster. The snapshot
now sends `X-Bainluck-Origin: harness` on every request, which suppresses the
write and touches no cache in either direction (`?debug_timing=1` would have
suppressed nothing here and bypassed the cache both ways).

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

from cold_path_snapshot import (  # noqa: E402
    PATHS,
    REJECTED,
    _fmt,
    _p50,
    measure,
    rejection_counts,
)

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

#: 🔴 The floors that the EQUAL-WEIGHTED statistic needs and a raw pool did not.
#: Equal weighting removes the "which path missed most" bias but not the "which
#: path missed at all" one: a member with zero cold samples is absent from the
#: median rather than counted slow, and the median of one surviving 11 ms member
#: IS 11 ms. So a published needle must be a median over a MAJORITY of the seven
#: member paths (4), and every one of the three graded surfaces must be
#: represented by at least one member — otherwise the line would claim "across
#: the three graded surfaces" while describing one or two of them.
MIN_COLD_MEMBERS = 4
MIN_SURFACES = 3


def _cold(rows: list[dict]) -> list[float]:
    """Server-time ms for the samples the ROUTE itself reported as cold."""
    return [
        r["server_ms"]
        for r in rows
        if r.get("class") == "cold" and r.get("server_ms") is not None
    ]


def _graded(rows: list[dict]) -> list[float]:
    """Server time for the samples that are latency observations at all.

    A 429 carries an `x-response-time`, so "has a server_ms" was not enough of a
    test and the rate limiter counted itself into `n_graded` — see
    `cold_path_snapshot._classify`, #2260.
    """
    return [
        r["server_ms"]
        for r in rows
        if r.get("server_ms") is not None and r.get("class") != REJECTED
    ]


#: 🔴 THE SERIES BREAK, AND ALEX'S RULING THAT CAUSED IT (2026-08-28, option c).
#:
#: The warmer landed and won. Five of the seven member paths could no longer be
#: driven cold at all, so the cold-only statistic refused seven reads running —
#: correctly, because a median over one surviving 12 ms member is not a needle.
#: But a metric that refuses because the product got FASTER is measuring the
#: wrong thing. Alex ruled a strict division:
#:
#:   NEEDLE  — what a brand-new install actually waits, per ruling 137's
#:             definition of a first load, WHATEVER CACHE SERVES IT. One number,
#:             his dial, the one-number-per-lane guardrail.
#:   DIAG    — the build cost, cold. It continues as a diagnostic in lane
#:             reports ONLY, so a build regression cannot hide behind the
#:             warmer. It never appears on the dial.
#:
#: Both lines are emitted with distinct names. **The old cold series
#: 882 -> 873 -> 940 -> 1273 ENDS HERE** and belongs to DIAG from now on; the
#: NEEDLE series starts fresh. Ruling 127 says a delta must not be a delta of
#: instruments — so this break is declared in the output of every run rather
#: than left for a reader to notice.
#:
#: The statistic is otherwise UNCHANGED: still the median of per-member p50s,
#: still each member path weighted once (option b's lesson — a raw pool moved
#: 25% on identical code from sample mix alone). Only the sample filter moves,
#: from "cold samples" to "every served sample".
MIN_WAIT_MEMBERS = 6
MIN_WAIT_SURFACES = 3


def _served(rows: list[dict]) -> list[float]:
    """Every sample the server actually answered — any cache state.

    This is the NEEDLE's filter. A fresh principal takes whatever the cache has
    for it, and that IS the wait; discarding the warm ones would report the bad
    half as though it were the whole (which is what the cold-only form did once
    the warmer made the bad half rare).

    `_graded` already excludes REJECTED, so a 429 cannot be counted as a fast
    wait here either — #2260.
    """
    return _graded(rows)


def user_wait(snap: dict) -> dict:
    """THE NEEDLE. What a brand-new install waits, per member, equal-weighted.

    Same shape as `needle()` below, same equal weighting, different filter.
    """
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
                    "served": _served(rows),
                    "n_cold": len(_cold(rows)),
                    "rejections": rejection_counts(rows),
                }
            )
    rows = snap["search_cold_samples"]
    members.append(
        {
            "surface": "cold search",
            "key": "search_cold",
            "path": "/api/events/search?q=",
            "served": _served(rows),
            "n_cold": len(_cold(rows)),
            "rejections": rejection_counts(rows),
        }
    )

    per_member_p50 = [_p50(m["served"]) for m in members if m["served"]]
    surfaces = sorted({m["surface"] for m in members if m["served"]})
    return {
        "schema": "latency-needle-user-wait/1",
        "taken_at": snap.get("taken_at"),
        "commit": snap.get("commit"),
        "uptime_seconds": snap.get("uptime_seconds"),
        "warm_slug": snap.get("warm_slug"),
        "canonical": snap.get("canonical"),
        "members": members,
        "needle_ms": _p50(per_member_p50),
        "n_members": len(per_member_p50),
        "n_total_members": len(members),
        "surfaces": surfaces,
        "pool_n": sum(len(m["served"]) for m in members),
    }


def wait_refusals(uw: dict) -> list[str]:
    """Why this run cannot publish a NEEDLE, in the statistic's own terms.

    The floors are LOOSER than DIAG's on purpose: every member should produce
    served samples on a healthy run, because "served" no longer depends on
    catching a cache miss. A member missing here means the harness could not
    reach it, not that the product was fast — so the bar is 6 of 7 rather than
    a bare majority.
    """
    out: list[str] = []
    if uw["n_members"] < MIN_WAIT_MEMBERS:
        out.append(
            f"only {uw['n_members']} of {uw['n_total_members']} member paths "
            f"were SERVED (floor {MIN_WAIT_MEMBERS}) — the median would describe "
            f"a subset of what a person opens"
        )
    if len(uw["surfaces"]) < MIN_WAIT_SURFACES:
        # parenthesised: `-` binds TIGHTER than `|` on sets, so the
        # unparenthesised form computed `POOL | (X - served)` and listed
        # every surface as missing including the ones that were served.
        missing = sorted((set(POOL) | {"cold search"}) - set(uw["surfaces"]))
        out.append(
            f"only {len(uw['surfaces'])} of {MIN_WAIT_SURFACES} graded surfaces "
            f"were served (missing: {', '.join(missing)}) — the line would claim "
            f"three and describe fewer"
        )
    throttled = sorted(
        m["key"] for m in uw["members"] if (m.get("rejections") or {}).get("429")
    )
    if throttled:
        out.append(
            f"RATE LIMITED: {', '.join(throttled)} — the server refused these, "
            f"so they are unmeasured, not fast (#2260)"
        )
    return out


def needle(snap: dict) -> dict:
    """Fold a cold-path snapshot into the BUILD-COST number and its provenance.

    🔴 This is the DIAG line now, not the needle — Alex's option-c ruling. It
    keeps the cold-only filter and the old floors, because its job is unchanged:
    catch a build regression that the warmer would otherwise hide. What changed
    is where it appears (lane reports) and what it is called
    (`DIAG: latency-build`). The 882 -> 873 -> 940 -> 1273 series is ITS series.
    """
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
                    "rejections": rejection_counts(rows),
                }
            )

    members.append(
        {
            "surface": "cold search",
            "key": "search_cold",
            "path": "/api/events/search?q=",
            "cold": _cold(snap["search_cold_samples"]),
            "n_graded": len(_graded(snap["search_cold_samples"])),
            "rejections": rejection_counts(snap["search_cold_samples"]),
        }
    )

    pool = [v for m in members for v in m["cold"]]
    #: THE PUBLISHED STATISTIC: one number per member path, then the median of
    #: those. A path that missed five times counts exactly as much as one that
    #: missed twice; a path that never missed is absent, not zero.
    per_path_p50 = [_p50(m["cold"]) for m in members if m["cold"]]
    equal_weighted = statistics.median(per_path_p50) if per_path_p50 else None

    return {
        # /2: the published statistic changed from the raw pool to the
        # equal-weighted median (Alex, 2026-08-28, "option b"). A consumer that
        # reads `needle_ms` off a /1 payload would be reading the other number.
        "schema": "latency-needle/2",
        "taken_at": snap["taken_at"],
        "commit": snap["commit"],
        "uptime_seconds": snap["uptime_seconds"],
        "warm_slug": snap["warm_slug"],
        "canonical": snap["canonical"],
        "members": members,
        # The published number. Duplicated under its own key so a consumer
        # never has to know which of the two statistics is current.
        "needle_ms": equal_weighted,
        "equal_weighted_p50_ms": equal_weighted,
        "n_cold_members": len(per_path_p50),
        "surfaces_cold": sorted({m["surface"] for m in members if m["cold"]}),
        # Demoted to a cross-check, still computed and still printed.
        "pool_n": len(pool),
        "pool_p50_ms": _p50(pool),
        "pool_max_ms": max(pool) if pool else None,
        "n_surfaces_cold": sum(1 for m in members if m["cold"]),
        "n_surfaces": len(members),
    }


def report(snap: dict, nd: dict, uw: dict | None = None) -> int:
    print(
        "# THE LATENCY NEEDLE — what a brand-new install waits — and the "
        "BUILD-COST diagnostic beneath it"
    )
    print("spec   : .claude/handoff/NEEDLE-SPEC.md (Alex, 2026-08-28, option c)")
    print(
        "stat   : NEEDLE = median of the per-path p50s over EVERY SERVED sample, "
        "each member path weighted ONCE, whatever cache answered."
    )
    print(
        "       : DIAG   = the same statistic over COLD samples only. Report-only; "
        "it exists so a build regression cannot hide behind the warmer."
    )
    print(
        "series : 🔴 BROKEN BY RULING, 2026-08-28. The cold series "
        "882 -> 873 -> 940 -> 1273 belongs to DIAG from here; the NEEDLE series "
        "starts fresh. Never plot a point from one against the other."
    )
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

    if uw is not None:
        print("## THE NEEDLE — every served sample, one row per member path")
        print(
            f"{'surface':14s} {'path key':17s} {'served':>6s} {'cold':>5s} "
            f"{'p50 wait':>9s}"
        )
        last_s = None
        for m in uw["members"]:
            label = m["surface"] if m["surface"] != last_s else ""
            last_s = m["surface"]
            print(
                f"{label:14s} {m['key']:17s} {len(m['served']):>6d} "
                f"{m['n_cold']:>5d} {_fmt(_p50(m['served'])):>9s}"
            )
        for m in uw["members"]:
            rej = m.get("rejections") or {}
            if rej and not m["served"]:
                detail = ", ".join(f"{n}x HTTP {k}" for k, n in sorted(rej.items()))
                print(
                    f"   🔴 {m['key']} was REFUSED BY THE SERVER — {detail}. "
                    f"UNMEASURED, which is not the same as fast."
                )
        wr = wait_refusals(uw)
        if wr:
            print("   🔴 NEEDLE REFUSED:")
            for why in wr:
                print(f"      - {why}")
        else:
            print(
                f"   ➡️  NEEDLE = {uw['needle_ms']:,.1f} ms   (median of "
                f"{uw['n_members']} per-path p50s, all "
                f"{len(uw['surfaces'])} graded surfaces served)"
            )
        print()

    print("## DIAG (build cost) — cold samples only, one row per member path")
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
        if m["cold"]:
            continue
        rej = m.get("rejections") or {}
        if rej:
            # 🔴 A THROTTLED member is not a warm one, and saying so is the
            # whole of #2260's second half. Three consecutive refusals were
            # filed as "the pool went warm" while this member's six samples
            # were 429s that the grader had scored as fast warm searches.
            detail = ", ".join(f"{n}x HTTP {k}" for k, n in sorted(rej.items()))
            print(
                f"   🔴 {m['key']} was REFUSED BY THE SERVER, not warm — "
                f"{detail}. This surface was UNMEASURABLE this run; that is a "
                f"different fact from 'it was fast'."
            )
        else:
            print(
                f"   ⚠️  {m['key']} produced NO cold sample this run — it is "
                f"absent from the median, not counted as fast."
            )
    throttled = sorted(
        m["key"] for m in nd["members"] if (m.get("rejections") or {}).get("429")
    )
    if throttled:
        print(
            f"   🔴 RATE LIMITED: {len(throttled)} member(s) — {', '.join(throttled)}. "
            f"The API allows 60 req/min per IP and this run issued "
            f"{sum(nd['requests'].values()) if 'requests' in nd else 'many'}; the "
            f"searches go last, so they are what gets refused. A latency lane "
            f"running EXPLAINs from the same IP throttles its own harness "
            f"(parked P110-4 — pacing needs a ruling, not a patch)."
        )

    print()
    print(
        f"## demoted cross-check: RAW POOLED cold p50 (every sample weighted "
        f"equally) = {_fmt(nd['pool_p50_ms'])} ms over n={nd['pool_n']} samples, "
        f"max {_fmt(nd['pool_max_ms'])} ms"
    )
    print(
        "   This was the headline until Alex's option-b ruling; it is printed "
        "because it is composition-sensitive and the headline is not. If the "
        "two diverge between runs, the move is which surfaces missed, not speed."
    )

    print()
    refusals = []
    if nd["needle_ms"] is None:
        refusals.append("no member path produced a cold sample at all")
    if nd["n_cold_members"] < MIN_COLD_MEMBERS:
        refusals.append(
            f"only {nd['n_cold_members']} of {nd['n_surfaces']} member paths "
            f"produced a cold sample (floor {MIN_COLD_MEMBERS}) — the median "
            f"would describe a minority of the pool"
        )
    if len(nd["surfaces_cold"]) < MIN_SURFACES:
        missing = [s for s in (*POOL, "cold search") if s not in nd["surfaces_cold"]]
        refusals.append(
            f"only {len(nd['surfaces_cold'])} of {MIN_SURFACES} graded surfaces "
            f"went cold (missing: {', '.join(missing)}) — the line would claim "
            f"three and describe fewer"
        )
    if nd["pool_n"] < MIN_POOL_N:
        refusals.append(
            f"n={nd['pool_n']} cold samples underneath the medians "
            f"(floor {MIN_POOL_N})"
        )

    if refusals:
        print(
            "## 🔴 DIAG POOL TOO THIN — no build-cost number. A null is not a "
            "fast number. (This does NOT block the NEEDLE above.)"
        )
        for why in refusals:
            print(f"   - {why}")
    else:
        print(
            f"## DIAG build cost, EQUAL-WEIGHTED COLD p50 = {nd['needle_ms']:,.1f} ms   "
            f"(median of {nd['n_cold_members']} per-path cold medians, "
            f"{nd['n_surfaces_cold']}/{nd['n_surfaces']} member paths, "
            f"all {MIN_SURFACES} graded surfaces represented)"
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
        f"   /api/events/search     {r['search']:>4d} — `X-Bainluck-Origin: harness` "
        "SENT on every one (LAT-P118); 0 `search_query_logs` rows once that ship is "
        "deployed, one row each until then. This line reports what the CLIENT sent, "
        "not what the server did. Forced on: cold search is graded."
    )
    print(
        f"   /api/events/typeahead  {r['typeahead']:>4d} — debug_timing AND origin, "
        "0 votes into search:trending:24h (debug_timing alone already guaranteed that "
        "on any slug). Measured by the snapshot, NOT in the pool."
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

    # 🔴 TWO LINES, DISTINCT NAMES, AND THE NEEDLE GOES LAST.
    #
    # Alex's option-c ruling. `DIAG` is report-only and its refusal must NOT
    # suppress the needle — that coupling is what let seven consecutive reads
    # publish nothing while the product was, in fact, fast. The exit code
    # follows the NEEDLE alone, because the needle is the deliverable
    # (gotcha #54: 1 is a result — here, "no needle").
    print()
    if refusals:
        print(
            f"DIAG: latency-build REFUSED @ {nd['taken_at']} — "
            f"{'; '.join(refusals)}"
        )
    else:
        print(f"DIAG: latency-build {nd['needle_ms']:.0f} ms @ {nd['taken_at']}")

    if uw is None:
        print(
            "NEEDLE: latency NOT COMPUTED — this caller did not pass the "
            "user-wait fold. That is a harness fault, not a reading."
        )
        return 2
    wr = wait_refusals(uw)
    if wr:
        print(f"NEEDLE: latency REFUSED @ {uw['taken_at']} — {'; '.join(wr)}")
        return 1
    print(f"NEEDLE: latency {uw['needle_ms']:.0f} ms @ {uw['taken_at']}")
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
    uw = user_wait(snap)
    if args.out:
        with open(args.out, "w") as fh:
            json.dump({"needle": uw, "build_diag": nd, "snapshot": snap}, fh, indent=2)
    return report(snap, nd, uw)


if __name__ == "__main__":
    raise SystemExit(main())
